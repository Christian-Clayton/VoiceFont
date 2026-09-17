"""Numeric synthetic smoke tests, not voice-quality evidence."""

import json

import numpy as np
import pytest

from voicefont.training import (
    TrainingConfig,
    evaluate,
    passes_gate,
    preprocess,
    save_model,
    train_autoencoder,
    validate_dataset,
)


def synthetic_features(seed=7):
    rng = np.random.default_rng(seed)
    latent = rng.normal(size=(160, 1))
    features = latent @ np.array([[1.0, -2.0, 0.5, 3.0]])
    features += rng.normal(scale=0.01, size=features.shape)
    return features, [f"synthetic-recording-{i // 4}" for i in range(len(features))]


def test_autoencoder_learns_heldout_features_without_recording_leakage():
    features, groups = synthetic_features()
    config = TrainingConfig(seed=7, bottleneck=1, max_iter=250)
    prepared = preprocess(features, groups, config)
    assert set(prepared.train_groups).isdisjoint(prepared.validation_groups)
    np.testing.assert_allclose(prepared.scaler.mean_, features[prepared.train_indices].mean(0))
    model = train_autoencoder(prepared, config)
    metrics = evaluate(model, prepared)
    assert metrics["validation_mse"] < metrics["baseline_mse"] * 0.1
    assert np.isfinite(model.loss_curve_).all()


def test_rows_sharing_a_recording_id_stay_on_one_side_of_the_split():
    features, groups = synthetic_features(seed=11)
    prepared = preprocess(features, groups, TrainingConfig(seed=3))
    for group in set(groups):
        sides = {i in prepared.train_indices for i, g in enumerate(groups) if g == group}
        assert len(sides) == 1


@pytest.mark.parametrize(
    "features", [[], [1, 2], np.zeros((2, 2, 2)), np.zeros((10_001, 4)), np.full((8, 4), 1e20)]
)
def test_rejects_invalid_shape_size_or_magnitude(features):
    with pytest.raises(ValueError):
        preprocess(features, ["a", "b"], TrainingConfig())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bottleneck": 0},
        {"max_iter": 0},
        {"max_iter": 100_000},
        {"seed": True},
        {"max_validation_mse": float("nan")},
    ],
)
def test_rejects_invalid_training_configuration(kwargs):
    with pytest.raises(ValueError):
        TrainingConfig(**kwargs).validated()


def test_seeded_training_is_reproducible():
    features, groups = synthetic_features()
    config = TrainingConfig(bottleneck=1, max_iter=20)
    first = preprocess(features, groups, config)
    second = preprocess(features, groups, config)
    np.testing.assert_array_equal(first.train_indices, second.train_indices)
    first_model = train_autoencoder(first, config)
    second_model = train_autoencoder(second, config)
    np.testing.assert_array_equal(first_model.coefs_[0], second_model.coefs_[0])


def test_rejects_nonfinite_features():
    features, groups = synthetic_features()
    features[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        validate_dataset(features, groups, TrainingConfig())


def test_rejects_row_count_mismatch_and_oversized_dims():
    features, groups = synthetic_features()
    with pytest.raises(ValueError, match="rows"):
        validate_dataset(features, groups[:-1], TrainingConfig())
    wide = np.zeros((4, 100_001))
    with pytest.raises(ValueError, match="dimension"):
        validate_dataset(wide, ["a", "b", "c", "d"], TrainingConfig())


def test_rejects_insufficient_recordings():
    features, _ = synthetic_features()
    with pytest.raises(ValueError, match="recording"):
        validate_dataset(features, ["one"] * len(features), TrainingConfig())


def test_rejects_invalid_split_fraction():
    with pytest.raises(ValueError, match="validation_fraction"):
        TrainingConfig(validation_fraction=1.0).validated()
    with pytest.raises(ValueError, match="validation_fraction"):
        TrainingConfig(validation_fraction=0.0).validated()
    with pytest.raises(ValueError, match="seed"):
        TrainingConfig(seed=-1).validated()


def test_gate_accepts_clear_improvement_and_rejects_weak_or_nonfinite_metrics():
    config = TrainingConfig()
    assert passes_gate({"validation_mse": 0.1, "baseline_mse": 1.0}, config)
    assert not passes_gate({"validation_mse": 0.9, "baseline_mse": 1.0}, config)
    assert not passes_gate({"validation_mse": float("nan"), "baseline_mse": 1.0}, config)


def test_saved_model_uses_pickle_free_npz_and_json_metadata(tmp_path):
    features, groups = synthetic_features()
    config = TrainingConfig(seed=7, bottleneck=1, max_iter=250)
    prepared = preprocess(features, groups, config)
    model = train_autoencoder(prepared, config)
    metrics = evaluate(model, prepared)
    npz_path, meta_path = save_model(model, prepared, config, tmp_path / "model", metrics)
    with np.load(npz_path, allow_pickle=False) as payload:
        assert set(payload.files) == {"w0", "b0", "w1", "b1", "scaler_mean", "scaler_scale"}
        np.testing.assert_allclose(payload["scaler_mean"], prepared.scaler.mean_)
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    assert metadata["model_kind"] == "numeric_feature_reconstruction_autoencoder"
    assert metadata["disclaimer"].startswith("Not")
    assert metadata["config"]["seed"] == 7
    assert metadata["metrics"]["validation_mse"] == pytest.approx(metrics["validation_mse"])
