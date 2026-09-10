#!/usr/bin/env python3
"""Qualify the isolated CPU-only BEX2 research environment without market data."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research/btc/contracts/btc-breakout-model-dependencies-v2.json"
REQUIREMENTS = ROOT / "requirements-breakout-research-v2.txt"
OUTPUT = (
    ROOT
    / "artifacts/agent-level-experiment/btc-focused/upside-compression-breakout-v1/dependency-v2"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def deterministic_predictions() -> dict[str, str]:
    rng = np.random.default_rng(20260901)
    x = rng.normal(size=(360, 14))
    y = np.tile(np.asarray((0, 1, 2)), 120)

    def fit_hist() -> np.ndarray:
        model = HistGradientBoostingClassifier(
            early_stopping=False,
            l2_regularization=1.0,
            learning_rate=0.03,
            max_bins=64,
            max_iter=25,
            max_leaf_nodes=3,
            min_samples_leaf=20,
            random_state=20260901,
        )
        return model.fit(x, y).predict_proba(x[:24])

    def fit_xgb() -> np.ndarray:
        model = XGBClassifier(
            colsample_bytree=1.0,
            device="cpu",
            learning_rate=0.03,
            max_depth=1,
            min_child_weight=20,
            n_estimators=25,
            n_jobs=1,
            objective="multi:softprob",
            random_state=20260901,
            reg_lambda=1.0,
            subsample=1.0,
            tree_method="hist",
        )
        return model.fit(x, y).predict_proba(x[:24])

    hist_a, hist_b = fit_hist(), fit_hist()
    xgb_a, xgb_b = fit_xgb(), fit_xgb()
    if not np.array_equal(hist_a, hist_b) or not np.array_equal(xgb_a, xgb_b):
        raise RuntimeError("fixed-seed model replay is not byte-identical")
    return {
        "M2_prediction_sha256": hashlib.sha256(hist_a.tobytes()).hexdigest(),
        "M3_prediction_sha256": hashlib.sha256(xgb_a.tobytes()).hexdigest(),
    }


def distribution_records() -> list[dict[str, str]]:
    records = []
    for distribution in sorted(
        importlib.metadata.distributions(), key=lambda item: item.metadata["Name"].lower()
    ):
        name = distribution.metadata["Name"]
        if name.lower().startswith("nvidia-"):
            raise RuntimeError("GPU/NVIDIA distribution present in CPU-only environment")
        record = distribution.locate_file("RECORD")
        metadata = distribution.locate_file("METADATA")
        files = list(distribution.files or ())
        record_candidates = [distribution.locate_file(path) for path in files if str(path).endswith(".dist-info/RECORD")]
        metadata_candidates = [distribution.locate_file(path) for path in files if str(path).endswith(".dist-info/METADATA")]
        record = record_candidates[0] if record_candidates else record
        metadata = metadata_candidates[0] if metadata_candidates else metadata
        records.append(
            {
                "metadata_sha256": sha256(metadata) if metadata.is_file() else "unavailable",
                "name": name,
                "record_sha256": sha256(record) if record.is_file() else "unavailable",
                "version": distribution.version,
            }
        )
    return records


def main() -> int:
    expected_suffix = "/.venv-breakout-v2/bin/python"
    if not sys.executable.endswith(expected_suffix):
        raise RuntimeError(f"wrong interpreter: {sys.executable}")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    versions = {
        "numpy": importlib.metadata.version("numpy"),
        "scikit-learn": importlib.metadata.version("scikit-learn"),
        "xgboost-cpu": importlib.metadata.version("xgboost-cpu"),
    }
    expected = {"numpy": "2.5.2", "scikit-learn": "1.9.0", "xgboost-cpu": "3.4.1"}
    if versions != expected:
        raise RuntimeError(f"top-level version mismatch: {versions}")
    report = {
        "contract": {"path": str(CONTRACT.relative_to(ROOT)), "sha256": sha256(CONTRACT)},
        "cpu_only": True,
        "deterministic_predictions": deterministic_predictions(),
        "distributions": distribution_records(),
        "environment": str(Path(sys.executable).parents[1].relative_to(ROOT)),
        "network_or_market_data_accessed": False,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "requirements": {
            "path": str(REQUIREMENTS.relative_to(ROOT)),
            "sha256": sha256(REQUIREMENTS),
        },
        "schema_version": "btc-breakout-model-environment-qualification-v1",
        "status": "passed_synthetic_dependency_qualification",
        "versions": versions,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "environment-manifest.json"
    if path.exists():
        raise RuntimeError(f"refusing to overwrite {path.relative_to(ROOT)}")
    path.write_text(canonical(report), encoding="utf-8")
    print(canonical({"output": str(path.relative_to(ROOT)), "sha256": sha256(path), "status": report["status"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
