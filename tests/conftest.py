"""Synthetic signal fixtures only, not evidence of speaker or synthesis quality."""

import io
import wave

import numpy as np
import pytest


@pytest.fixture
def signal_wav():
    def make(frequency=440, sr=16000, duration=0.25, channels=1, width=2, amplitude=0.3):
        signal = amplitude * np.sin(2 * np.pi * frequency * np.arange(int(sr * duration)) / sr)
        signal = np.repeat(signal[:, None], channels, axis=1).reshape(-1)
        if width == 1:
            raw = np.rint(signal * 127 + 128).astype("uint8").tobytes()
        elif width == 3:
            values = np.rint(signal * (2**23 - 1)).astype("<i4")
            raw = values.view("uint8").reshape(-1, 4)[:, :3].tobytes()
        else:
            raw = np.rint(signal * (2 ** (width * 8 - 1) - 1)).astype(f"<i{width}").tobytes()
        result = io.BytesIO()
        with wave.open(result, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(sr)
            wav.writeframes(raw)
        return result.getvalue()

    return make
