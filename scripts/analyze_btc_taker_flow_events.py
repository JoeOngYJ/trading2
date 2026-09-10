#!/usr/bin/env python3
"""Leakage-safe BTC taker-trade-flow continuation/reversal event study."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

HORIZONS = (1, 3, 12, 48)
BAR_MS = 300_000


@dataclass(frozen=True)
class Bar:
    open_time_ms: int
    close: float
    imbalance: float


def load(path: Path) -> list[Bar]:
    bars: list[Bar] = []
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            bars.append(Bar(int(row["open_time_ms"]), float(row["close"]), float(row["base_trade_flow_imbalance"])))
    if not bars:
        raise ValueError("empty dataset")
    for left, right in zip(bars, bars[1:]):
        if right.open_time_ms != left.open_time_ms + BAR_MS:
            raise ValueError("dataset is not a gap-free 5m series")
    return bars


def quantile(values: list[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ValueError("invalid quantile input")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def percentile(values: list[float], probability: float) -> float:
    return quantile(values, probability)


def daily_block_bootstrap(outcomes: list[float | None], seed: int, replicates: int = 2000) -> tuple[float | None, float | None]:
    blocks: list[tuple[float, int]] = []
    for start in range(0, len(outcomes), 288):
        selected = [value for value in outcomes[start:start + 288] if value is not None]
        blocks.append((sum(selected), len(selected)))
    active = [block for block in blocks if block[1]]
    if not active:
        return None, None
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replicates):
        total = count = 0
        for _ in range(len(blocks)):
            block_sum, block_count = blocks[rng.randrange(len(blocks))]
            total += block_sum
            count += block_count
        if count:
            estimates.append(total / count)
    if not estimates:
        return None, None
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def summarize(outcomes: list[float | None], expected_sign: int, seed: int) -> dict:
    selected = [value for value in outcomes if value is not None]
    if not selected:
        return {"events": 0, "mean_forward_log_return": None, "median_forward_log_return": None,
                "direction_hit_rate": None, "continuation_mean": None, "continuation_ci95": [None, None]}
    continuation = [expected_sign * value if value is not None else None for value in outcomes]
    cont_selected = [value for value in continuation if value is not None]
    low, high = daily_block_bootstrap(continuation, seed)
    return {
        "events": len(selected),
        "mean_forward_log_return": statistics.fmean(selected),
        "median_forward_log_return": statistics.median(selected),
        "direction_hit_rate": sum(expected_sign * value > 0 for value in selected) / len(selected),
        "continuation_mean": statistics.fmean(cont_selected),
        "continuation_ci95": [low, high],
    }


def analyze(bars: list[Bar], lower: float, upper: float) -> dict:
    split_ms = 1_735_689_600_000  # 2025-01-01T00:00:00Z
    report: dict = {"thresholds_from_2024": {"lower_q05": lower, "upper_q95": upper}, "splits": {}}
    for split_name, start_ms, end_ms in (
        ("train_2024", 1_704_067_200_000, split_ms),
        ("test_2025", split_ms, 1_767_225_600_000),
    ):
        split_report: dict = {}
        for horizon in HORIZONS:
            positive: list[float | None] = []
            negative: list[float | None] = []
            for index, bar in enumerate(bars):
                if not start_ms <= bar.open_time_ms < end_ms or index + horizon >= len(bars):
                    continue
                future = math.log(bars[index + horizon].close / bar.close)
                positive.append(future if bar.imbalance >= upper else None)
                negative.append(future if bar.imbalance <= lower else None)
            split_report[f"{horizon * 5}m"] = {
                "positive_imbalance": summarize(positive, 1, 10_000 + horizon),
                "negative_imbalance": summarize(negative, -1, 20_000 + horizon),
            }
        report["splits"][split_name] = split_report
    return report


def enforce_holdout_access(manifest: dict, data_sha: str, hypothesis_path: Path | None) -> None:
    if not str(manifest.get("partition", "")).startswith("holdout"):
        return
    if hypothesis_path is None:
        raise ValueError("sealed holdout requires a frozen hypothesis file")
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    if hypothesis.get("status") != "frozen" or hypothesis.get("holdout_dataset_sha256") != data_sha:
        raise ValueError("hypothesis is not frozen for this holdout dataset")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--hypothesis", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    data_sha = hashlib.sha256(args.data.read_bytes()).hexdigest()
    if not manifest.get("accepted") or data_sha != manifest.get("dataset_sha256"):
        parser.error("dataset is not accepted by the supplied manifest")
    try:
        enforce_holdout_access(manifest, data_sha, args.hypothesis)
    except (ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    bars = load(args.data)
    training = [bar.imbalance for bar in bars if bar.open_time_ms < 1_735_689_600_000]
    lower, upper = quantile(training, 0.05), quantile(training, 0.95)
    report = analyze(bars, lower, upper)
    report.update({
        "study": "btc-taker-trade-flow-extreme-event-v1",
        "dataset_sha256": data_sha,
        "threshold_policy": "2024 q05/q95 frozen before 2025 evaluation",
        "forward_return_policy": "log(close[t+h]/close[t]); event bar ends at t",
        "bootstrap": {"method": "UTC-day block bootstrap", "block_bars": 288, "replicates": 2000},
        "multiple_testing_status": "exploratory; no model promotion decision permitted",
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
