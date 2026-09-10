#!/usr/bin/env python3
"""Fresh-process, CPU-only dependency qualification for BEX2."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path


for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements-breakout-research-v2.txt"
OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/upside-compression-breakout-v1/dependency-v3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def probe() -> dict[str, object]:
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from threadpoolctl import threadpool_info
    from xgboost import XGBClassifier

    rng = np.random.default_rng(20260901)
    x = rng.normal(size=(360, 14))
    y = np.tile(np.asarray((0, 1, 2)), 120)
    hist = HistGradientBoostingClassifier(
        early_stopping=False,
        l2_regularization=1.0,
        learning_rate=0.03,
        max_bins=64,
        max_iter=25,
        max_leaf_nodes=3,
        min_samples_leaf=20,
        random_state=20260901,
    ).fit(x, y)
    xgb = XGBClassifier(
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
    ).fit(x, y)
    pools = threadpool_info()
    if not pools or any(item.get("num_threads") != 1 for item in pools):
        raise RuntimeError(f"thread pool is not single-threaded: {pools}")
    library = Path(importlib.metadata.distribution("xgboost-cpu").locate_file("xgboost/lib/libxgboost.so"))
    if not library.is_file():
        raise RuntimeError("xgboost-cpu shared library is missing")
    linked = subprocess.run(
        ["ldd", str(library)], check=True, capture_output=True, text=True, env={**os.environ}
    ).stdout
    if "cuda" in linked.lower() or "nccl" in linked.lower():
        raise RuntimeError("xgboost-cpu library links CUDA/NCCL")
    payload = np.concatenate((hist.predict_proba(x[:24]), xgb.predict_proba(x[:24])), axis=1)
    normalized_linked = re.sub(r"\(0x[0-9a-fA-F]+\)", "(0xADDR)", linked)
    return {
        "linked_libraries_sha256": hashlib.sha256(normalized_linked.encode()).hexdigest(),
        "prediction_sha256": hashlib.sha256(payload.tobytes()).hexdigest(),
        "threadpools": pools,
        "xgboost_library_sha256": sha256(library),
    }


def distributions() -> list[dict[str, str]]:
    output = []
    for item in sorted(importlib.metadata.distributions(), key=lambda value: value.metadata["Name"].lower()):
        name = item.metadata["Name"]
        if name.lower().startswith("nvidia-"):
            raise RuntimeError("GPU/NVIDIA distribution present")
        files = list(item.files or ())
        records = [item.locate_file(path) for path in files if str(path).endswith(".dist-info/RECORD")]
        metadata = [item.locate_file(path) for path in files if str(path).endswith(".dist-info/METADATA")]
        output.append(
            {
                "metadata_sha256": sha256(metadata[0]) if metadata else "unavailable",
                "name": name,
                "record_sha256": sha256(records[0]) if records else "unavailable",
                "version": item.version,
            }
        )
    return output


def fresh_probe() -> dict[str, object]:
    environment = {**os.environ}
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        environment[name] = "1"
    process = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--probe"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return json.loads(process.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    if args.probe:
        print(json.dumps(probe(), allow_nan=False, sort_keys=True, separators=(",", ":")))
        return 0
    if args.contract is None:
        raise RuntimeError("--contract is required for qualification")
    contract = args.contract.resolve(strict=True)
    if not sys.executable.endswith("/.venv-breakout-v3/bin/python"):
        raise RuntimeError(f"wrong interpreter: {sys.executable}")
    expected = {"numpy": "2.5.2", "scikit-learn": "1.9.0", "xgboost-cpu": "3.4.1"}
    versions = {name: importlib.metadata.version(name) for name in expected}
    if versions != expected:
        raise RuntimeError(f"top-level version mismatch: {versions}")
    first, second = fresh_probe(), fresh_probe()
    if first != second:
        raise RuntimeError("two fresh fixed-seed probe processes differ")
    report = {
        "contract": {"path": str(contract.relative_to(ROOT)), "sha256": sha256(contract)},
        "cpu_only": True,
        "distributions": distributions(),
        "environment": ".venv-breakout-v3",
        "network_or_market_data_accessed": False,
        "platform": platform.platform(),
        "probe": first,
        "python": platform.python_version(),
        "qualification_script": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": sha256(Path(__file__).resolve()),
        },
        "requirements": {
            "path": str(REQUIREMENTS.relative_to(ROOT)),
            "sha256": sha256(REQUIREMENTS),
        },
        "schema_version": "btc-breakout-model-environment-qualification-v2",
        "status": "passed_fresh_process_CPU_only_dependency_qualification",
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
