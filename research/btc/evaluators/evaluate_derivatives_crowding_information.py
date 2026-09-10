#!/usr/bin/env python3
"""Offline evaluator for btc-derivatives-crowding-information-v1.

This module reads only frozen, checksummed artifacts.  It has no trading, broker,
exchange, database, NATS, Freqtrade, or network integration.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-derivatives-crowding-information-v1.json"
OUTPUT_DIR = ROOT / "artifacts/agent-level-experiment/btc-focused/derivatives-crowding-information-v1"
DATE_RE = re.compile(r'"open_at"\s*:\s*"([^"]+)"')
UTC = timezone.utc


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError(f"timestamp is not explicit UTC: {value}")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError(f"timestamp is not UTC: {value}")
    return parsed


def past_zscore(current: float, prior: Sequence[float], window: int, minimum: int) -> float | None:
    history = np.asarray(prior[-window:], dtype=float)
    if len(history) < minimum or not np.isfinite(current) or not np.all(np.isfinite(history)):
        return None
    standard_deviation = float(np.std(history, ddof=1))
    if standard_deviation <= 0.0:
        return None
    return (float(current) - float(np.mean(history))) / standard_deviation


def cftc_available_at(report_date: date) -> datetime:
    return datetime.combine(report_date + timedelta(days=4), time.min, tzinfo=UTC)


def future_labels(returns_by_date: dict[date, float], decision_date: date) -> dict[str, float] | None:
    future_dates = [decision_date + timedelta(days=offset) for offset in range(7)]
    if any(item not in returns_by_date for item in future_dates):
        return None
    future = np.asarray([returns_by_date[item] for item in future_dates], dtype=float)
    cumulative = np.cumsum(future)
    return {
        "next_1d_log_return": float(future[0]),
        "next_1d_squared_log_return": float(future[0] ** 2),
        "next_7d_downside_path_loss": float(max(0.0, -float(np.min(cumulative)))),
        "next_7d_log_return": float(np.sum(future)),
        "next_7d_realized_variance": float(np.sum(future**2)),
        "target_log_next_7d_realized_variance": float(math.log(max(float(np.sum(future**2)), 1e-18))),
    }


def load_contract() -> dict:
    with CONTRACT_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def verify_inputs(contract: dict) -> dict[str, str]:
    verified: dict[str, str] = {}
    for item in contract["bound_inputs"]:
        relative = item["path"]
        actual = sha256_path(ROOT / relative)
        if actual != item["sha256"]:
            raise ValueError(f"checksum mismatch for {relative}: {actual}")
        verified[relative] = actual
    return verified


def load_daily_prices(path: Path, development_end: date) -> tuple[dict[date, float], dict]:
    closes: dict[date, float] = {}
    locked_rows_screened = 0
    numeric_rows_deserialized_after_end = 0
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for raw in handle:
            match = DATE_RE.search(raw)
            if not match:
                raise ValueError("daily row lacks open_at timestamp")
            open_at_text = match.group(1)
            open_at = parse_utc(open_at_text)
            if open_at.time() != time.min:
                raise ValueError(f"daily open is not midnight UTC: {open_at_text}")
            if open_at.date() > development_end:
                locked_rows_screened += 1
                continue
            row = json.loads(raw)
            if open_at.date() > development_end:
                numeric_rows_deserialized_after_end += 1
                raise AssertionError("locked numeric row was deserialized")
            available_at = parse_utc(row["available_at"])
            if available_at != open_at + timedelta(days=1):
                raise ValueError(f"invalid close availability for {open_at_text}")
            close = float(row["close"])
            if not math.isfinite(close) or close <= 0 or open_at.date() in closes:
                raise ValueError(f"invalid or duplicate close for {open_at_text}")
            closes[open_at.date()] = close
    ordered = sorted(closes)
    if any(right - left != timedelta(days=1) for left, right in zip(ordered, ordered[1:])):
        raise ValueError("daily close input has a calendar gap")
    return closes, {
        "development_numeric_rows_deserialized": len(closes),
        "locked_rows_timestamp_screened_only": locked_rows_screened,
        "numeric_rows_deserialized_after_development_end": numeric_rows_deserialized_after_end,
    }


def load_funding(path: Path) -> tuple[dict[date, float], dict]:
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    grouped: dict[date, list[tuple[int, float]]] = defaultdict(list)
    seen: set[int] = set()
    for row in rows:
        timestamp = int(row["fundingTime"])
        observed_at = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
        if timestamp in seen or row["symbol"] != "BTCUSDT" or row["rateType"] != "Regular":
            raise ValueError("invalid or duplicate funding row")
        # Binance records the scheduled funding events with a small observed timestamp
        # jitter (0--47 ms in the frozen artifact).  Preserve the actual timestamp but
        # accept it only within one second after the scheduled 00/08/16 UTC boundary.
        if observed_at.minute or observed_at.second or observed_at.hour not in (0, 8, 16):
            raise ValueError(f"unexpected funding timestamp: {observed_at.isoformat()}")
        rate = float(row["fundingRate"])
        if not math.isfinite(rate):
            raise ValueError("non-finite funding rate")
        grouped[observed_at.date()].append((observed_at.hour, rate))
        seen.add(timestamp)
    daily: dict[date, float] = {}
    invalid_days: list[str] = []
    for day, values in grouped.items():
        if sorted(hour for hour, _ in values) != [0, 8, 16]:
            invalid_days.append(day.isoformat())
        else:
            daily[day] = float(sum(value for _, value in values))
    return daily, {"raw_rows": len(rows), "complete_days": len(daily), "invalid_days": invalid_days}


def load_basis(path: Path) -> tuple[dict[date, float], dict]:
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    daily: dict[date, float] = {}
    for row in rows:
        observed_at = datetime.fromtimestamp(int(row["timestamp"]) / 1000, tz=UTC)
        if observed_at.time() != time.min or row["pair"] != "BTCUSDT" or row["contractType"] != "PERPETUAL":
            raise ValueError("invalid basis identity or timestamp")
        value = float(row["basisRate"])
        if not math.isfinite(value) or observed_at.date() in daily:
            raise ValueError("invalid or duplicate basis row")
        daily[observed_at.date()] = value
    ordered = sorted(daily)
    if any(right - left != timedelta(days=1) for left, right in zip(ordered, ordered[1:])):
        raise ValueError("basis input has a calendar gap")
    return daily, {"raw_rows": len(rows), "complete_days": len(daily)}


def load_cftc(path: Path) -> tuple[list[dict], dict]:
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    normalized: list[dict] = []
    seen: set[date] = set()
    excluded_non_tuesday: list[str] = []
    for row in rows:
        report_date = date.fromisoformat(row["Report_Date_as_YYYY-MM-DD"])
        if report_date in seen:
            raise ValueError(f"invalid or duplicate CFTC report date: {report_date}")
        seen.add(report_date)
        # The frozen availability rule defines only Tuesday reports. Holiday-week
        # Monday rows therefore fail closed instead of receiving an inferred release
        # timestamp; the last valid Tuesday report remains in force.
        if report_date.weekday() != 1:
            excluded_non_tuesday.append(report_date.isoformat())
            continue
        if row["Market_and_Exchange_Names"].strip() != "BITCOIN - CHICAGO MERCANTILE EXCHANGE":
            raise ValueError("unexpected CFTC market")
        open_interest = float(row["Open_Interest_All"])
        long_positions = float(row["Lev_Money_Positions_Long_All"])
        short_positions = float(row["Lev_Money_Positions_Short_All"])
        if open_interest <= 0:
            raise ValueError("non-positive CFTC open interest")
        normalized.append({
            "report_date": report_date,
            "available_at": cftc_available_at(report_date),
            "leveraged_net_share": (long_positions - short_positions) / open_interest,
        })
    normalized.sort(key=lambda item: item["report_date"])
    if any((right["report_date"] - left["report_date"]).days not in (7, 14) for left, right in zip(normalized, normalized[1:])):
        raise ValueError("unexpected CFTC report cadence")
    return normalized, {
        "excluded_non_tuesday_report_dates": excluded_non_tuesday,
        "normalized_reports": len(normalized),
        "raw_rows": len(rows),
    }


def compute_returns_and_ewma(closes: dict[date, float], decay: float = 0.94) -> tuple[dict[date, float], dict[date, float]]:
    ordered = sorted(closes)
    returns: dict[date, float] = {}
    for previous, current in zip(ordered, ordered[1:]):
        if current - previous != timedelta(days=1):
            raise ValueError("close series is not consecutive")
        returns[current] = math.log(closes[current] / closes[previous])
    ewma: dict[date, float] = {}
    accumulated: list[float] = []
    variance: float | None = None
    for day in sorted(returns):
        value = returns[day]
        accumulated.append(value)
        if variance is None and len(accumulated) == 30:
            variance = float(np.var(np.asarray(accumulated), ddof=1))
        elif variance is not None:
            variance = decay * variance + (1.0 - decay) * value * value
        if variance is not None:
            ewma[day] = variance
    return returns, ewma


def build_observations(
    contract: dict,
    closes: dict[date, float],
    funding: dict[date, float],
    basis: dict[date, float],
    cftc: list[dict],
) -> tuple[list[dict], dict]:
    start = date.fromisoformat(contract["data_boundary"]["development_start_inclusive"])
    end = date.fromisoformat(contract["data_boundary"]["development_end_inclusive"])
    returns, ewma = compute_returns_and_ewma(closes, decay=float(contract["controls"]["ewma_variance"]["decay"]))
    funding_history: list[float] = []
    basis_history: list[float] = []
    cftc_history: list[float] = []
    last_cftc_report: date | None = None
    observations: list[dict] = []
    unknown_reasons: dict[str, int] = defaultdict(int)
    current = start
    while current <= end:
        previous_day = current - timedelta(days=1)
        decision_at = datetime.combine(current, time.min, tzinfo=UTC)
        current_funding = funding.get(previous_day)
        current_basis = basis.get(previous_day)
        available_cftc = [item for item in cftc if item["available_at"] <= decision_at]
        current_cftc = available_cftc[-1] if available_cftc else None

        funding_z = None if current_funding is None else past_zscore(current_funding, funding_history, 90, 60)
        basis_z = None if current_basis is None else past_zscore(current_basis, basis_history, 90, 60)
        cftc_z = None
        if current_cftc is not None:
            if current_cftc["report_date"] != last_cftc_report:
                cftc_z = past_zscore(current_cftc["leveraged_net_share"], cftc_history, 52, 26)
            else:
                # Reuse the z-score determined when this report first became available. Its
                # normalization history remains unchanged until a new report is published.
                cftc_z = observations[-1].get("cftc_signed_z") if observations else None

        control_ewma = ewma.get(previous_day)
        momentum_start = current - timedelta(days=8)
        abs_momentum = None
        if previous_day in closes and momentum_start in closes:
            abs_momentum = abs(math.log(closes[previous_day] / closes[momentum_start]))
        labels = future_labels(returns, current)

        missing = []
        for name, value in (
            ("funding", current_funding), ("basis", current_basis), ("cftc", current_cftc),
            ("funding_z", funding_z), ("basis_z", basis_z), ("cftc_z", cftc_z),
            ("ewma", control_ewma), ("momentum", abs_momentum), ("labels", labels),
        ):
            if value is None:
                missing.append(name)
                unknown_reasons[name] += 1
        complete = not missing
        observation = {
            "abs_momentum_7d": abs_momentum,
            "basis_rate": current_basis,
            "basis_signed_z": basis_z,
            "cftc_leveraged_net_share": None if current_cftc is None else current_cftc["leveraged_net_share"],
            "cftc_report_date": None if current_cftc is None else current_cftc["report_date"].isoformat(),
            "cftc_signed_z": cftc_z,
            "complete": complete,
            "crowding_intensity": None if not complete else float(np.mean(np.abs([funding_z, basis_z, cftc_z]))),
            "decision_at": decision_at.isoformat().replace("+00:00", "Z"),
            "ewma_variance": control_ewma,
            "funding_daily_sum": current_funding,
            "funding_signed_z": funding_z,
            "labels": labels,
            "missing": missing,
        }
        observations.append(observation)

        if current_funding is not None:
            funding_history.append(current_funding)
        if current_basis is not None:
            basis_history.append(current_basis)
        if current_cftc is not None and current_cftc["report_date"] != last_cftc_report:
            cftc_history.append(current_cftc["leveraged_net_share"])
            last_cftc_report = current_cftc["report_date"]
        current += timedelta(days=1)
    return observations, {"unknown_reason_counts": dict(sorted(unknown_reasons.items()))}


def fit_standardized_ols(rows: Sequence[dict], include_crowding: bool) -> dict:
    keys = ["ewma_variance", "abs_momentum_7d"] + (["crowding_intensity"] if include_crowding else [])
    matrix = np.asarray([[float(row[key]) for key in keys] for row in rows], dtype=float)
    target = np.asarray([float(row["labels"]["target_log_next_7d_realized_variance"]) for row in rows], dtype=float)
    means = np.mean(matrix, axis=0)
    scales = np.std(matrix, axis=0, ddof=1)
    if np.any(~np.isfinite(scales)) or np.any(scales <= 0):
        raise ValueError("invalid training predictor scale")
    standardized = (matrix - means) / scales
    design = np.column_stack([np.ones(len(standardized)), standardized])
    coefficients, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
    return {"keys": keys, "means": means, "scales": scales, "coefficients": coefficients}


def predict(model: dict, row: dict) -> float:
    values = np.asarray([float(row[key]) for key in model["keys"]], dtype=float)
    standardized = (values - model["means"]) / model["scales"]
    return float(model["coefficients"][0] + np.dot(model["coefficients"][1:], standardized))


def walk_forward(observations: Sequence[dict], training_minimum: int = 365, embargo_days: int = 7) -> list[dict]:
    complete = [row for row in observations if row["complete"]]
    predictions: list[dict] = []
    model_month: str | None = None
    control_model = None
    expanded_model = None
    for row in complete:
        decision = date.fromisoformat(row["decision_at"][:10])
        cutoff = decision - timedelta(days=embargo_days)
        training = [candidate for candidate in complete if date.fromisoformat(candidate["decision_at"][:10]) <= cutoff]
        if len(training) < training_minimum:
            continue
        month = decision.strftime("%Y-%m")
        if model_month != month:
            control_model = fit_standardized_ols(training, include_crowding=False)
            expanded_model = fit_standardized_ols(training, include_crowding=True)
            model_month = month
        assert control_model is not None and expanded_model is not None
        target = float(row["labels"]["target_log_next_7d_realized_variance"])
        control_forecast = predict(control_model, row)
        expanded_forecast = predict(expanded_model, row)
        prior_scores = [float(candidate["crowding_intensity"]) for candidate in complete if date.fromisoformat(candidate["decision_at"][:10]) < decision]
        group = "unclassified"
        q20 = q80 = None
        if len(prior_scores) >= 365:
            q20, q80 = (float(value) for value in np.percentile(np.asarray(prior_scores), [20, 80], method="linear"))
            if float(row["crowding_intensity"]) >= q80:
                group = "high"
            elif float(row["crowding_intensity"]) <= q20:
                group = "low"
            else:
                group = "middle"
        predictions.append({
            "control_forecast": control_forecast,
            "control_squared_error": (target - control_forecast) ** 2,
            "decision_at": row["decision_at"],
            "error_improvement": (target - control_forecast) ** 2 - (target - expanded_forecast) ** 2,
            "expanded_forecast": expanded_forecast,
            "expanded_squared_error": (target - expanded_forecast) ** 2,
            "group": group,
            "labels": row["labels"],
            "q20": q20,
            "q80": q80,
            "target": target,
        })
    return predictions


def month_block_interval(values_by_month: dict[str, list[float]], seed: int, samples: int) -> dict:
    monthly = np.asarray([float(np.mean(values_by_month[key])) for key in sorted(values_by_month)], dtype=float)
    if len(monthly) < 2:
        return {"lower": None, "point": None, "upper": None, "months": len(monthly)}
    rng = np.random.default_rng(seed)
    draws = rng.choice(monthly, size=(samples, len(monthly)), replace=True).mean(axis=1)
    lower, upper = np.percentile(draws, [2.5, 97.5], method="linear")
    return {"lower": float(lower), "point": float(np.mean(monthly)), "upper": float(upper), "months": len(monthly)}


def group_difference_interval(predictions: Sequence[dict], label: str, seed: int, samples: int) -> dict:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in predictions:
        if row["group"] in ("high", "low"):
            month = row["decision_at"][:7]
            grouped[month][row["group"]].append(float(row["labels"][label]))
    differences: dict[str, list[float]] = {}
    for month, groups in grouped.items():
        if groups["high"] and groups["low"]:
            differences[month] = [float(np.mean(groups["high"]) - np.mean(groups["low"]))]
    return month_block_interval(differences, seed, samples)


def rankdata(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(len(array), dtype=float)
    index = 0
    while index < len(array):
        end = index + 1
        while end < len(array) and array[order[end]] == array[order[index]]:
            end += 1
        ranks[order[index:end]] = (index + 1 + end) / 2.0
        index = end
    return ranks


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 3:
        return None
    left_rank = rankdata(left)
    right_rank = rankdata(right)
    if np.std(left_rank) == 0 or np.std(right_rank) == 0:
        return None
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def diagnostics(observations: Sequence[dict], predictions: Sequence[dict]) -> dict:
    complete = [row for row in observations if row["complete"]]
    labels = ["next_1d_log_return", "next_7d_log_return", "next_1d_squared_log_return", "next_7d_realized_variance", "next_7d_downside_path_loss"]
    features = ["crowding_intensity", "funding_signed_z", "basis_signed_z", "cftc_signed_z"]
    associations = {
        feature: {label: spearman([float(row[feature]) for row in complete], [float(row["labels"][label]) for row in complete]) for label in labels}
        for feature in features
    }
    yearly = {}
    for year in sorted({row["decision_at"][:4] for row in predictions}):
        rows = [row for row in predictions if row["decision_at"].startswith(year)]
        control_mse = float(np.mean([row["control_squared_error"] for row in rows]))
        expanded_mse = float(np.mean([row["expanded_squared_error"] for row in rows]))
        yearly[year] = {
            "control_mse": control_mse,
            "expanded_mse": expanded_mse,
            "relative_improvement": (control_mse - expanded_mse) / control_mse,
            "rows": len(rows),
        }
    monthly_improvement: dict[str, float] = {}
    for month in sorted({row["decision_at"][:7] for row in predictions}):
        monthly_improvement[month] = float(np.mean([row["error_improvement"] for row in predictions if row["decision_at"].startswith(month)]))
    positive = sorted((value for value in monthly_improvement.values() if value > 0), reverse=True)
    concentration = None if not positive else float(sum(positive[:3]) / sum(positive))
    return {
        "spearman_associations": associations,
        "walk_forward_by_year": yearly,
        "monthly_error_improvement": monthly_improvement,
        "best_three_positive_months_share": concentration,
    }


def write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_bytes(value))


def main() -> None:
    contract = load_contract()
    if contract["status"] != "frozen_before_forward_outcome_evaluation":
        raise ValueError("contract is not frozen")
    verified_inputs = verify_inputs(contract)
    paths = {Path(item["path"]).name: ROOT / item["path"] for item in contract["bound_inputs"]}
    development_end = date.fromisoformat(contract["data_boundary"]["development_end_inclusive"])
    closes, daily_audit = load_daily_prices(paths["btc-usdt-direct-1d-development-2017-2025.jsonl.gz"], development_end)
    funding, funding_audit = load_funding(paths["funding.json"])
    basis, basis_audit = load_basis(paths["basis.json"])
    cftc, cftc_audit = load_cftc(paths["cftc-bitcoin-tff.json"])
    observations, observation_audit = build_observations(contract, closes, funding, basis, cftc)
    predictions = walk_forward(
        observations,
        training_minimum=int(contract["controls"]["training_minimum_complete_observations"]),
        embargo_days=int(contract["controls"]["training_embargo_days"]),
    )

    complete = [row for row in observations if row["complete"]]
    control_mse = float(np.mean([row["control_squared_error"] for row in predictions])) if predictions else math.nan
    expanded_mse = float(np.mean([row["expanded_squared_error"] for row in predictions])) if predictions else math.nan
    relative_improvement = (control_mse - expanded_mse) / control_mse if predictions and control_mse else math.nan
    seed = int(contract["method"]["bootstrap_seed"])
    samples = int(contract["method"]["bootstrap_calendar_month_blocks"])
    error_by_month: dict[str, list[float]] = defaultdict(list)
    for row in predictions:
        error_by_month[row["decision_at"][:7]].append(float(row["error_improvement"]))
    error_interval = month_block_interval(error_by_month, seed, samples)
    variance_interval = group_difference_interval(predictions, "next_7d_realized_variance", seed + 1, samples)
    downside_interval = group_difference_interval(predictions, "next_7d_downside_path_loss", seed + 2, samples)
    classified = [row for row in predictions if row["group"] != "unclassified"]
    high_occupancy = sum(row["group"] == "high" for row in classified) / len(classified) if classified else math.nan
    months = len({row["decision_at"][:7] for row in predictions})
    gate_results = {
        "complete_feature_observations_minimum": len(complete) >= int(contract["gates"]["complete_feature_observations_minimum"]),
        "high_crowding_occupancy_range": bool(classified) and float(contract["gates"]["high_crowding_occupancy_minimum"]) <= high_occupancy <= float(contract["gates"]["high_crowding_occupancy_maximum"]),
        "high_minus_low_next_7d_downside_loss_ci_lower_positive": downside_interval["lower"] is not None and downside_interval["lower"] > 0,
        "high_minus_low_next_7d_realized_variance_ci_lower_positive": variance_interval["lower"] is not None and variance_interval["lower"] > 0,
        "next_7d_log_realized_variance_oos_mse_relative_improvement": relative_improvement >= float(contract["gates"]["next_7d_log_realized_variance_oos_mse_relative_improvement_minimum"]),
        "next_7d_log_realized_variance_paired_error_ci_lower_positive": error_interval["lower"] is not None and error_interval["lower"] > 0,
        "walk_forward_calendar_months_minimum": months >= int(contract["gates"]["walk_forward_calendar_months_minimum"]),
        "walk_forward_predictions_minimum": len(predictions) >= int(contract["gates"]["walk_forward_predictions_minimum"]),
    }
    passed = all(gate_results.values())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger_path = OUTPUT_DIR / "feature-label-ledger.jsonl"
    with ledger_path.open("wb") as handle:
        for row in observations:
            handle.write(canonical_bytes(row))
    predictions_path = OUTPUT_DIR / "walk-forward-predictions.jsonl"
    with predictions_path.open("wb") as handle:
        for row in predictions:
            handle.write(canonical_bytes(row))

    report = {
        "actionable_arm_id": "no_trade",
        "artifacts": {
            "feature_label_ledger": {"path": str(ledger_path.relative_to(ROOT)), "sha256": sha256_path(ledger_path)},
            "walk_forward_predictions": {"path": str(predictions_path.relative_to(ROOT)), "sha256": sha256_path(predictions_path)},
        },
        "audit": {
            "basis": basis_audit,
            "cftc": cftc_audit,
            "daily": daily_audit,
            "funding": funding_audit,
            "observations": observation_audit,
        },
        "contract": {"path": str(CONTRACT_PATH.relative_to(ROOT)), "sha256": sha256_path(CONTRACT_PATH)},
        "decision": "information_gate_passed" if passed else "information_gate_rejected",
        "diagnostics": diagnostics(observations, predictions),
        "experiment_id": contract["experiment_id"],
        "gate_results": gate_results,
        "information_evaluation": {
            "classified_predictions": len(classified),
            "complete_feature_observations": len(complete),
            "control_oos_mse": control_mse,
            "downside_high_minus_low_month_block_interval": downside_interval,
            "expanded_oos_mse": expanded_mse,
            "high_crowding_occupancy": high_occupancy,
            "low_crowding_occupancy": sum(row["group"] == "low" for row in classified) / len(classified) if classified else None,
            "oos_error_improvement_month_block_interval": error_interval,
            "oos_mse_relative_improvement": relative_improvement,
            "variance_high_minus_low_month_block_interval": variance_interval,
            "walk_forward_months": months,
            "walk_forward_predictions": len(predictions),
        },
        "implementation": {
            "evaluator_path": str(Path(__file__).resolve().relative_to(ROOT)),
            "evaluator_sha256": sha256_path(Path(__file__).resolve()),
            "test_path": "research/btc/tests/test_derivatives_crowding_information.py",
            "test_sha256": sha256_path(ROOT / "research/btc/tests/test_derivatives_crowding_information.py"),
        },
        "no_orders_positions_pnl_or_costs_computed": True,
        "strategy_evaluation_run": False,
        "verified_inputs": verified_inputs,
    }
    report_path = OUTPUT_DIR / "report.json"
    write_json(report_path, report)
    manifest = {
        "experiment_id": contract["experiment_id"],
        "files": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)}
            for path in (ledger_path, predictions_path, report_path)
        ],
    }
    write_json(OUTPUT_DIR / "manifest.json", manifest)
    print(json.dumps({
        "decision": report["decision"],
        "report": str(report_path.relative_to(ROOT)),
        "report_sha256": sha256_path(report_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
