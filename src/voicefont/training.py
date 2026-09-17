"""Small numeric-feature autoencoder experiment, not voice or identity training."""

import json
from dataclasses import asdict, dataclass

import numpy as np
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

MAX_FEATURE_DIMS = 256
MAX_ROWS = 10_000
MIN_TRAIN_RECORDINGS = 2
GATE_MARGIN = 0.5
DISCLAIMER = (
    "Not voice cloning and not speaker identity training."
    " Reconstructs numeric acoustic feature vectors only."
)


@dataclass(frozen=True)
class TrainingConfig:
    seed: int = 7
    validation_fraction: float = 0.25
    bottleneck: int = 2
    max_iter: int = 250
    max_validation_mse: float = 0.5

    def validated(self) -> "TrainingConfig":
        if not 0.0 < self.validation_fraction < 1.0:
            raise ValueError("validation_fraction must be strictly between 0 and 1")
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError("seed must be an integer in [0, 2**32)")
        if type(self.bottleneck) is not int or not 1 <= self.bottleneck <= 64:
            raise ValueError("bottleneck must be an integer between 1 and 64")
        if type(self.max_iter) is not int or not 1 <= self.max_iter <= 1000:
            raise ValueError("max_iter must be an integer between 1 and 1000")
        if not np.isfinite(self.max_validation_mse) or self.max_validation_mse < 0:
            raise ValueError("max_validation_mse must be finite and non-negative")
        return self


@dataclass
class PreparedData:
    train: np.ndarray
    validation: np.ndarray
    scaler: StandardScaler
    train_indices: np.ndarray
    validation_indices: np.ndarray
    train_groups: list[str]
    validation_groups: list[str]


def validate_dataset(features, recording_ids, config: TrainingConfig) -> None:
    """Reject non-finite, oversized, or too-little-data inputs before training."""
    config.validated()
    features = np.asarray(features)
    if features.ndim != 2 or features.dtype.kind not in "fiu":
        raise ValueError("features must be a numeric 2D matrix")
    if not 2 <= features.shape[1] <= MAX_FEATURE_DIMS:
        raise ValueError(f"feature dimension must be between 2 and {MAX_FEATURE_DIMS}")
    if config.bottleneck >= features.shape[1]:
        raise ValueError("bottleneck must be smaller than feature dimension")
    if not 2 <= len(features) <= MAX_ROWS:
        raise ValueError(f"row count must be between 2 and {MAX_ROWS}, got {len(features)}")
    if len(features) != len(recording_ids):
        raise ValueError("features rows and recording_ids must have the same length")
    if not np.isfinite(features).all():
        raise ValueError("features must be finite (no NaN or inf)")
    if np.max(np.abs(features)) > 1e12:
        raise ValueError("feature magnitude must not exceed 1e12")
    if any(
        not isinstance(group, str) or not group.strip() or len(group) > 256
        for group in recording_ids
    ):
        raise ValueError("recording ids must be nonempty strings of at most 256 characters")
    unique = set(recording_ids)
    if len(unique) < MIN_TRAIN_RECORDINGS:
        raise ValueError(
            f"need at least {MIN_TRAIN_RECORDINGS} distinct recording ids, got {len(unique)}"
        )


def preprocess(features, recording_ids, config: TrainingConfig) -> PreparedData:
    """Split original recording groups before fitting the feature scaler."""
    validate_dataset(features, recording_ids, config)
    features = np.asarray(features, dtype=np.float64)
    groups = np.asarray(recording_ids)
    config = config.validated()
    splitter = GroupShuffleSplit(
        n_splits=1, test_size=config.validation_fraction, random_state=config.seed
    )
    train_idx, val_idx = next(splitter.split(features, groups=groups))
    scaler = StandardScaler().fit(features[train_idx])
    return PreparedData(
        scaler.transform(features[train_idx]),
        scaler.transform(features[val_idx]),
        scaler,
        train_idx,
        val_idx,
        groups[train_idx].tolist(),
        groups[val_idx].tolist(),
    )


def train_autoencoder(prepared: PreparedData, config: TrainingConfig) -> MLPRegressor:
    """Fit a tanh bottleneck MLP to reconstruct train-only standardized features."""
    model = MLPRegressor(
        hidden_layer_sizes=(config.bottleneck,),
        activation="tanh",
        solver="adam",
        learning_rate_init=0.02,
        max_iter=config.max_iter,
        random_state=config.seed,
        early_stopping=False,
        tol=1e-7,
        n_iter_no_change=30,
    )
    return model.fit(prepared.train, prepared.train)


def evaluate(model: MLPRegressor, prepared: PreparedData) -> dict[str, float]:
    """Heldout MSE in train-scaled units, against the train-mean predictor (zero)."""
    prediction = model.predict(prepared.validation)
    return {
        "validation_mse": float(np.mean((prediction - prepared.validation) ** 2)),
        "baseline_mse": float(np.mean(prepared.validation**2)),
    }


def passes_gate(metrics: dict[str, float], config: TrainingConfig) -> bool:
    """Accept only finite metrics beating the baseline by the gate margin."""
    try:
        mse = float(metrics["validation_mse"])
        baseline = float(metrics["baseline_mse"])
    except (KeyError, TypeError, ValueError):
        return False
    if not (np.isfinite(mse) and np.isfinite(baseline) and baseline > 0):
        return False
    return 0 <= mse <= min(baseline * GATE_MARGIN, config.max_validation_mse)


def save_model(model, prepared: PreparedData, config: TrainingConfig, out_path, metrics):
    """Write weights as an allow_pickle=False-safe npz and metadata as JSON."""
    npz_path = out_path.with_suffix(".npz")
    meta_path = out_path.with_suffix(".json")
    np.savez(
        npz_path,
        w0=model.coefs_[0],
        b0=model.intercepts_[0],
        w1=model.coefs_[1],
        b1=model.intercepts_[1],
        scaler_mean=prepared.scaler.mean_,
        scaler_scale=prepared.scaler.scale_,
    )
    metadata = {
        "model_kind": "numeric_feature_reconstruction_autoencoder",
        "disclaimer": DISCLAIMER,
        "config": asdict(config),
        "metrics": metrics,
        "train_rows": int(len(prepared.train)),
        "validation_rows": int(len(prepared.validation)),
    }
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return npz_path, meta_path
