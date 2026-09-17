"""Run a seeded SYNTHETIC NUMERIC smoke fixture, not a voice-quality experiment.

From the repository: python scripts/ml_demo.py
Requires the project installed with its ML optional dependencies.
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from voicefont.pipeline import run_pipeline
from voicefont.training import TrainingConfig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/ml-demo"))
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rng = np.random.default_rng(args.seed)
    latent = rng.normal(size=(160, 1))
    features = latent @ np.array([[1.0, -2.0, 0.5, 3.0]])
    features += rng.normal(scale=0.01, size=features.shape)
    groups = [f"synthetic-recording-{row // 4}" for row in range(160)]
    report = run_pipeline(
        features,
        groups,
        output_dir=args.output_dir,
        config=TrainingConfig(seed=args.seed, bottleneck=1),
        provenance="SYNTHETIC NUMERIC SMOKE FIXTURE: seeded low-rank matrix plus noise; "
        "no audio, private data, voice-quality or speaker-identity claims",
    )
    path = args.output_dir / "report.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"report": str(path.resolve()), **report}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
