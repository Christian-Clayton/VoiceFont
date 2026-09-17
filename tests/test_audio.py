import hashlib

import numpy as np
import pytest

from voicefont.audio import AudioError, extract_features, read_audio


@pytest.mark.parametrize("width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2])
def test_pcm_signal_decoding_preserves_original(signal_wav, tmp_path, width, channels):
    raw = signal_wav(width=width, channels=channels)
    source = tmp_path / "signal.wav"
    source.write_bytes(raw)
    audio = read_audio(source)
    assert audio.samples.shape == (4000,)
    assert audio.sample_rate == 16000
    assert audio.channels == channels
    assert audio.sample_width == width
    assert audio.duration_seconds == 0.25
    assert audio.raw_bytes == raw
    assert audio.sha256 == hashlib.sha256(raw).hexdigest()
    assert max(audio.samples) == pytest.approx(0.3, abs=0.01)


@pytest.mark.parametrize(
    "kwargs",
    [dict(amplitude=0), dict(amplitude=1), dict(sr=4000), dict(channels=3), dict(duration=0.01)],
)
def test_invalid_signal_rejected(signal_wav, kwargs):
    with pytest.raises(AudioError):
        read_audio(signal_wav(**kwargs))


def test_malformed_truncated_and_size_limits(signal_wav):
    raw = signal_wav()
    for data in (b"not wav", raw[:-10]):
        with pytest.raises(AudioError):
            read_audio(data)
    with pytest.raises(AudioError, match="bytes"):
        read_audio(raw, max_bytes=100)
    with pytest.raises(AudioError, match="duration"):
        read_audio(raw, max_duration=0.2)


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_clipping_is_checked_at_each_pcm_bit_depth(signal_wav, width):
    with pytest.raises(AudioError, match="clipping"):
        read_audio(signal_wav(width=width, amplitude=1))


def test_acoustic_features_are_deterministic_finite_nonzero(signal_wav):
    audio = read_audio(signal_wav())
    vector = extract_features(audio)
    assert vector.shape == (16,)
    assert np.isfinite(vector).all()
    assert np.linalg.norm(vector) == pytest.approx(1)
    np.testing.assert_array_equal(vector, extract_features(audio))
    other = extract_features(read_audio(signal_wav(frequency=2400)))
    assert np.dot(vector, other) < 0.95


def test_empty_nonfinite_and_silent_feature_arrays_rejected(signal_wav):
    from dataclasses import replace

    audio = read_audio(signal_wav())
    for samples in (np.array([]), np.array([np.nan, 1]), np.zeros(50)):
        with pytest.raises(AudioError):
            extract_features(replace(audio, samples=samples))
