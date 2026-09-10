"""Causal OB1 sampling helpers for accepted, offline BTC order-book replays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


NS_PER_MS = 1_000_000
NS_PER_SECOND = 1_000_000_000

BOOK_REQUIRED = {
    "capture_sequence",
    "connection_id",
    "segment_id",
    "receipt_time_ns",
    "best_bid",
    "best_ask",
    "bid_qty_l1",
    "ask_qty_l1",
    "spread",
    "mid_price",
    "microprice_minus_mid_spreads",
    "queue_imbalance_l1",
    "queue_imbalance_l5",
    "queue_imbalance_l10",
    "ofi_l1",
    "bid_add_qty",
    "bid_remove_qty",
    "ask_add_qty",
    "ask_remove_qty",
}
TRADE_REQUIRED = {
    "capture_sequence",
    "connection_id",
    "receipt_time_ns",
    "quote_quantity",
    "signed_quote_quantity",
}


@dataclass(frozen=True)
class Ob1DatasetResult:
    frame: pd.DataFrame
    quality: Mapping[str, int]


def _numeric_frame(frame: pd.DataFrame, required: set[str], label: str) -> pd.DataFrame:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} frame missing columns: {missing}")
    out = frame[list(required)].copy()
    out = out.apply(pd.to_numeric, errors="coerce")
    if out.isna().any().any() or not np.isfinite(out.to_numpy(dtype=float)).all():
        raise ValueError(f"{label} frame contains non-finite values")
    out = out.sort_values(["receipt_time_ns", "capture_sequence"]).reset_index(drop=True)
    if out["capture_sequence"].duplicated().any():
        raise ValueError(f"{label} frame contains duplicate capture sequences")
    if out["receipt_time_ns"].diff().dropna().lt(0).any():
        raise ValueError(f"{label} receipt timestamps move backwards")
    return out


def validate_replay_frames(
    book: pd.DataFrame, trades: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    checked_book = _numeric_frame(book, BOOK_REQUIRED, "book")
    checked_trades = _numeric_frame(trades, TRADE_REQUIRED, "trade")
    if checked_book.empty:
        raise ValueError("book frame is empty")
    invalid_book = (
        checked_book["best_bid"].le(0)
        | checked_book["best_ask"].le(checked_book["best_bid"])
        | checked_book["bid_qty_l1"].le(0)
        | checked_book["ask_qty_l1"].le(0)
        | checked_book["spread"].le(0)
        | checked_book["segment_id"].le(0)
    )
    if invalid_book.any():
        raise ValueError(f"book frame contains {int(invalid_book.sum())} invalid rows")
    expected_mid = (checked_book["best_bid"] + checked_book["best_ask"]) / 2
    expected_spread = checked_book["best_ask"] - checked_book["best_bid"]
    if not np.allclose(checked_book["mid_price"], expected_mid, rtol=0, atol=1e-9):
        raise ValueError("book mid price disagrees with best quotes")
    if not np.allclose(checked_book["spread"], expected_spread, rtol=0, atol=1e-9):
        raise ValueError("book spread disagrees with best quotes")
    if checked_trades["quote_quantity"].lt(0).any():
        raise ValueError("trade quote quantity cannot be negative")
    return checked_book, checked_trades


def _ceil_second(values: pd.Series) -> pd.Series:
    raw = values.astype("int64")
    return ((raw + NS_PER_SECOND - 1) // NS_PER_SECOND) * NS_PER_SECOND


def _latest_book_at(
    targets: pd.DataFrame, book: pd.DataFrame, suffix: str
) -> pd.DataFrame:
    source = book[
        ["receipt_time_ns", "segment_id", "connection_id", "mid_price"]
    ].rename(
        columns={
            "receipt_time_ns": f"book_receipt_ns_{suffix}",
            "segment_id": f"segment_id_{suffix}",
            "connection_id": f"connection_id_{suffix}",
            "mid_price": f"mid_price_{suffix}",
        }
    )
    return pd.merge_asof(
        targets.sort_values("target_time_ns"),
        source.sort_values(f"book_receipt_ns_{suffix}"),
        left_on="target_time_ns",
        right_on=f"book_receipt_ns_{suffix}",
        direction="backward",
        allow_exact_matches=True,
    ).sort_values("decision_time_ns")


def build_ob1_dataset(
    book: pd.DataFrame,
    trades: pd.DataFrame,
    spec: Mapping[str, Any],
    start: pd.Timestamp,
    end_exclusive: pd.Timestamp,
) -> Ob1DatasetResult:
    """Build one causal row per UTC second and delayed mid-return labels.

    Event windows are `(decision - window, decision]`. A target mid is the latest accepted
    book whose local receipt time is no later than the target, never the first future event.
    """

    checked_book, checked_trades = validate_replay_frames(book, trades)
    start = pd.Timestamp(start)
    end_exclusive = pd.Timestamp(end_exclusive)
    if start.tzinfo is None or end_exclusive.tzinfo is None or start >= end_exclusive:
        raise ValueError("OB1 boundaries must be ordered and timezone aware")
    sampling = spec["sampling"]
    labels = spec["labels"]
    if int(sampling["decision_frequency_ms"]) != 1000:
        raise ValueError("this OB1 builder requires the frozen one-second grid")
    maximum_age_ns = int(sampling["maximum_book_age_ms"]) * NS_PER_MS
    label_age_ns = int(labels["maximum_target_book_age_ms"]) * NS_PER_MS
    decisions = pd.DataFrame(
        {
            "decision_time": pd.date_range(
                start.ceil("1s"), end_exclusive.floor("1s"), freq="1s", inclusive="left"
            )
        }
    )
    decisions["decision_time_ns"] = decisions["decision_time"].astype("int64")
    current_columns = [
        "receipt_time_ns",
        "connection_id",
        "segment_id",
        "mid_price",
        "spread",
        "bid_qty_l1",
        "ask_qty_l1",
        "microprice_minus_mid_spreads",
        "queue_imbalance_l1",
        "queue_imbalance_l5",
        "queue_imbalance_l10",
        "bid_add_qty",
        "bid_remove_qty",
        "ask_add_qty",
        "ask_remove_qty",
    ]
    sampled = pd.merge_asof(
        decisions.sort_values("decision_time_ns"),
        checked_book[current_columns].sort_values("receipt_time_ns"),
        left_on="decision_time_ns",
        right_on="receipt_time_ns",
        direction="backward",
        allow_exact_matches=True,
    )
    sampled["book_age_ms"] = (
        sampled["decision_time_ns"] - sampled["receipt_time_ns"]
    ) / NS_PER_MS
    sampled["l1_total_depth"] = sampled["bid_qty_l1"] + sampled["ask_qty_l1"]

    book_events = checked_book.copy()
    book_events["decision_time_ns"] = _ceil_second(book_events["receipt_time_ns"])
    book_window = book_events.groupby(
        ["decision_time_ns", "connection_id", "segment_id"], sort=True
    ).agg(
        ofi_l1_sum_1s=("ofi_l1", "sum"),
        depth_event_count_1s=("ofi_l1", "size"),
    ).reset_index()
    sampled = sampled.merge(
        book_window,
        on=["decision_time_ns", "connection_id", "segment_id"],
        how="left",
    )
    sampled[["ofi_l1_sum_1s", "depth_event_count_1s"]] = sampled[
        ["ofi_l1_sum_1s", "depth_event_count_1s"]
    ].fillna(0)

    trade_events = checked_trades.copy()
    trade_events["decision_time_ns"] = _ceil_second(trade_events["receipt_time_ns"])
    trade_events["absolute_quote_quantity"] = trade_events["quote_quantity"].abs()
    trade_window = trade_events.groupby(
        ["decision_time_ns", "connection_id"], sort=True
    ).agg(
        signed_trade_quote_qty_1s=("signed_quote_quantity", "sum"),
        trade_count_1s=("signed_quote_quantity", "size"),
        absolute_trade_quote_qty_1s=("absolute_quote_quantity", "sum"),
    ).reset_index()
    sampled = sampled.merge(
        trade_window, on=["decision_time_ns", "connection_id"], how="left"
    )
    trade_columns = [
        "signed_trade_quote_qty_1s",
        "trade_count_1s",
        "absolute_trade_quote_qty_1s",
    ]
    sampled[trade_columns] = sampled[trade_columns].fillna(0)

    prior_targets = decisions[["decision_time_ns"]].copy()
    prior_targets["target_time_ns"] = prior_targets["decision_time_ns"] - NS_PER_SECOND
    prior = _latest_book_at(prior_targets, checked_book, "prior")
    sampled = sampled.merge(
        prior.drop(columns="target_time_ns"), on="decision_time_ns", how="left"
    )
    prior_age = sampled["decision_time_ns"] - NS_PER_SECOND - sampled["book_receipt_ns_prior"]
    same_prior_segment = (
        sampled["segment_id"].eq(sampled["segment_id_prior"])
        & sampled["connection_id"].eq(sampled["connection_id_prior"])
    )
    sampled["return_1s"] = np.where(
        same_prior_segment & prior_age.between(0, maximum_age_ns),
        np.log(sampled["mid_price"] / sampled["mid_price_prior"]),
        np.nan,
    )
    sampled["realized_volatility_10s"] = (
        sampled.groupby(["connection_id", "segment_id"], sort=False)["return_1s"]
        .rolling(10, min_periods=10)
        .std(ddof=1)
        .reset_index(level=[0, 1], drop=True)
    )

    horizons = sorted(
        {int(labels["primary_horizon_seconds"]), *map(int, labels["sensitivity_horizons_seconds"])}
    )
    latencies = sorted(
        {int(labels["primary_latency_ms"]), *map(int, labels["sensitivity_latencies_ms"])}
    )
    label_valid = pd.Series(True, index=sampled.index)
    for latency_ms in latencies:
        entry_targets = decisions[["decision_time_ns"]].copy()
        entry_targets["target_time_ns"] = (
            entry_targets["decision_time_ns"] + latency_ms * NS_PER_MS
        )
        entry = _latest_book_at(entry_targets, checked_book, f"entry_{latency_ms}")
        sampled = sampled.merge(
            entry.drop(columns="target_time_ns"), on="decision_time_ns", how="left"
        )
        entry_receipt = sampled[f"book_receipt_ns_entry_{latency_ms}"]
        entry_age = sampled["decision_time_ns"] + latency_ms * NS_PER_MS - entry_receipt
        entry_valid = (
            entry_age.between(0, label_age_ns)
            & sampled["segment_id"].eq(sampled[f"segment_id_entry_{latency_ms}"])
            & sampled["connection_id"].eq(sampled[f"connection_id_entry_{latency_ms}"])
        )
        for horizon_seconds in horizons:
            key = f"exit_{latency_ms}_{horizon_seconds}"
            exit_targets = decisions[["decision_time_ns"]].copy()
            exit_targets["target_time_ns"] = (
                exit_targets["decision_time_ns"]
                + latency_ms * NS_PER_MS
                + horizon_seconds * NS_PER_SECOND
            )
            exit_frame = _latest_book_at(exit_targets, checked_book, key)
            sampled = sampled.merge(
                exit_frame.drop(columns="target_time_ns"), on="decision_time_ns", how="left"
            )
            exit_receipt = sampled[f"book_receipt_ns_{key}"]
            target_ns = (
                sampled["decision_time_ns"]
                + latency_ms * NS_PER_MS
                + horizon_seconds * NS_PER_SECOND
            )
            valid = (
                entry_valid
                & (target_ns - exit_receipt).between(0, label_age_ns)
                & sampled[f"segment_id_entry_{latency_ms}"].eq(sampled[f"segment_id_{key}"])
                & sampled[f"connection_id_entry_{latency_ms}"].eq(
                    sampled[f"connection_id_{key}"]
                )
            )
            column = f"target_log_return_l{latency_ms}ms_h{horizon_seconds}s"
            sampled[column] = np.where(
                valid,
                np.log(
                    sampled[f"mid_price_{key}"]
                    / sampled[f"mid_price_entry_{latency_ms}"]
                ),
                np.nan,
            )
            if latency_ms == int(labels["primary_latency_ms"]) and horizon_seconds == int(
                labels["primary_horizon_seconds"]
            ):
                label_valid = valid

    feature_columns = [
        *spec["features"]["primary_l2"],
        *spec["features"]["signed_trade_control"],
        *spec["features"]["state_controls"],
    ]
    feature_valid = sampled[feature_columns].notna().all(axis=1)
    current_valid = sampled["book_age_ms"].between(
        0, int(sampling["maximum_book_age_ms"])
    )
    valid = current_valid & feature_valid & label_valid
    quality = {
        "decision_rows": int(len(sampled)),
        "valid_rows": int(valid.sum()),
        "rejected_stale_or_missing_current": int((~current_valid).sum()),
        "rejected_missing_feature_history": int((current_valid & ~feature_valid).sum()),
        "rejected_primary_label": int((current_valid & feature_valid & ~label_valid).sum()),
    }
    keep = [
        "decision_time",
        "decision_time_ns",
        "connection_id",
        "segment_id",
        *dict.fromkeys(
            [
                *feature_columns,
                *spec["features"]["secondary_diagnostics"],
                *[
                    f"target_log_return_l{latency}ms_h{horizon}s"
                    for latency in latencies
                    for horizon in horizons
                ],
            ]
        ),
    ]
    return Ob1DatasetResult(sampled.loc[valid, keep].reset_index(drop=True), quality)


def development_folds(
    accepted_days: Sequence[pd.Timestamp], spec: Mapping[str, Any]
) -> list[dict[str, Any]]:
    days = sorted({pd.Timestamp(day).normalize() for day in accepted_days})
    required = int(spec["data_gate"]["minimum_accepted_development_days"])
    if len(days) < required:
        raise ValueError(f"OB1 requires {required} accepted development days; found {len(days)}")
    days = days[:required]
    folds = []
    initial = int(spec["walk_forward"]["initial_training_days"])
    for number, (first, last) in enumerate(
        spec["walk_forward"]["validation_day_ranges_inclusive"], start=1
    ):
        validation = days[int(first) - 1 : int(last)]
        training = days[: int(first) - 1]
        if len(training) < initial or len(validation) != int(last) - int(first) + 1:
            raise ValueError("frozen OB1 fold ranges do not fit the accepted days")
        folds.append(
            {
                "fold": number,
                "training_days": training,
                "validation_days": validation,
                "purge_seconds_each_side": int(
                    spec["walk_forward"]["purge_seconds_each_side"]
                ),
            }
        )
    return folds


def validate_ob1_collection_contract(
    contract: Mapping[str, Any], spec: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate metadata boundaries without opening development or sealed replay rows."""

    if contract.get("experiment_id") != spec.get("experiment_id"):
        raise ValueError("OB1 collection contract has the wrong experiment ID")
    if contract.get("status") != "locked":
        raise ValueError("OB1 collection contract must be locked before analysis")
    development = contract.get("development_days")
    sealed = contract.get("sealed_test_days")
    if not isinstance(development, list) or not isinstance(sealed, list):
        raise ValueError("OB1 collection contract requires development and sealed day lists")

    def validate_rows(rows: Sequence[Mapping[str, Any]], label: str) -> list[pd.Timestamp]:
        dates: list[pd.Timestamp] = []
        for row in rows:
            if row.get("acceptance_status") != "accepted":
                raise ValueError(f"{label} contains a day that is not accepted")
            digest = row.get("replay_manifest_sha256")
            if not isinstance(digest, str) or len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError(f"{label} contains an invalid replay-manifest checksum")
            day = pd.Timestamp(row.get("date"))
            if day.tzinfo is None or day != day.normalize():
                raise ValueError(f"{label} dates must be midnight UTC timestamps")
            dates.append(day)
        if len(set(dates)) != len(dates) or dates != sorted(dates):
            raise ValueError(f"{label} dates must be unique and chronological")
        return dates

    development_dates = validate_rows(development, "development")
    sealed_dates = validate_rows(sealed, "sealed test")
    required_development = int(spec["data_gate"]["minimum_accepted_development_days"])
    required_test = int(spec["data_gate"]["sealed_test_days"])
    if len(development_dates) != required_development:
        raise ValueError(
            f"OB1 requires exactly {required_development} locked development days"
        )
    if len(sealed_dates) != required_test:
        raise ValueError(f"OB1 requires exactly {required_test} sealed test days")
    if development_dates[-1] >= sealed_dates[0]:
        raise ValueError("OB1 sealed test must begin after all development days")
    if any(
        later - earlier != pd.Timedelta(days=1)
        for earlier, later in zip(sealed_dates, sealed_dates[1:])
    ):
        raise ValueError("OB1 sealed test must be 30 contiguous UTC days")
    if contract.get("sealed_test_access") != "metadata_only_unread":
        raise ValueError("OB1 sealed test must remain metadata-only and unread")
    return {
        "status": "development_ready_test_sealed",
        "development_days": len(development_dates),
        "development_start": development_dates[0].isoformat(),
        "development_end": development_dates[-1].isoformat(),
        "sealed_test_days": len(sealed_dates),
        "sealed_test_start": sealed_dates[0].isoformat(),
        "sealed_test_end": sealed_dates[-1].isoformat(),
    }
