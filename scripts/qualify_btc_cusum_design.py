#!/usr/bin/env python3
"""Synthetic-only Monte Carlo qualification for the frozen Page-CUSUM design."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from trading_platform.btc_cusum_trend_events import (
    CUSUM_DRIFT,
    CUSUM_THRESHOLD,
    MINIMUM_ACTIVE_HOURS,
    MINIMUM_POSITIVE_CONTRIBUTORS,
    Z_CLIP,
)


SEED = 20260901
PATHS = 10_000
MAX_HOURS = 3_000
MEAN_TOLERANCE = 0.01
EXPECTED = {
    "0.0": {"mean": 125.15, "median": 89.0},
    "0.5": {"mean": 16.55, "median": 14.0},
}


def simulate(mean: float) -> dict[str, Any]:
    """Generate the full matrix so RNG ordering is part of the frozen design."""

    rng = np.random.default_rng(SEED)
    draws = rng.normal(mean, 1.0, size=(PATHS, MAX_HOURS))
    first_passages: list[int] = []
    for path in draws:
        state = 0.0
        contributors = 0
        active_hours = 0
        for hour, raw in enumerate(path, start=1):
            contribution = float(np.clip(raw, -Z_CLIP, Z_CLIP)) - CUSUM_DRIFT
            before = state
            state = max(0.0, state + contribution)
            if state == 0.0:
                contributors = 0
                active_hours = 0
                continue
            active_hours += 1
            if contribution > 0.0:
                contributors += 1
            if (
                before < CUSUM_THRESHOLD <= state
                and contributors >= MINIMUM_POSITIVE_CONTRIBUTORS
                and active_hours >= MINIMUM_ACTIVE_HOURS
            ):
                first_passages.append(hour)
                break
        else:
            first_passages.append(MAX_HOURS + 1)
    values = np.asarray(first_passages, dtype=np.float64)
    return {
        "censored_paths": int(np.sum(values == MAX_HOURS + 1)),
        "mean_first_passage_hours": float(np.mean(values)),
        "median_first_passage_hours": float(np.median(values)),
    }


def qualify() -> dict[str, Any]:
    results = {key: simulate(float(key)) for key in EXPECTED}
    checks: dict[str, bool] = {}
    for key, expected in EXPECTED.items():
        observed = results[key]
        checks[f"mean_{key}"] = (
            abs(observed["mean_first_passage_hours"] - expected["mean"])
            <= MEAN_TOLERANCE
        )
        checks[f"median_{key}"] = (
            observed["median_first_passage_hours"] == expected["median"]
        )
        checks[f"uncensored_{key}"] = observed["censored_paths"] == 0
    return {
        "checks": checks,
        "parameters": {
            "clip": Z_CLIP,
            "drift": CUSUM_DRIFT,
            "maximum_hours": MAX_HOURS,
            "minimum_active_hours": MINIMUM_ACTIVE_HOURS,
            "minimum_positive_contributors": MINIMUM_POSITIVE_CONTRIBUTORS,
            "paths_per_mean": PATHS,
            "seed": SEED,
            "threshold": CUSUM_THRESHOLD,
        },
        "passed": all(checks.values()),
        "results": results,
        "synthetic_only": True,
    }


def main() -> None:
    result = qualify()
    print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
