from __future__ import annotations

from decimal import Decimal

import pytest

from trading_platform.btc_accounting_e1_v14.authorities import get_run_spec
from trading_platform.btc_accounting_e1_v14.canonical import FrozenDict, canonical_sha256
from trading_platform.btc_accounting_e1_v14.controls import CONTROL_IDS, ControlError, _run_control


def run(name, run_id="pair_candle_primary"):
    return _run_control(get_run_spec(run_id), name, Decimal("0.1"))


def test_D01_engine_gap_full_execution_rows():
    artifact = run("spot_buy_and_hold")
    assert artifact.summary["gap_count"] == 2
    assert artifact.summary["fill_count"] == 2
    assert any(row["reason"] == "gap_exit" for row in artifact.rows["order"])
    assert artifact.rows["decision"] and artifact.rows["order"] and artifact.rows["account"]


def test_D02_gap_sticky_reset_after_fill():
    artifact = run("spot_buy_and_hold")
    gap = artifact.artifacts["gaps"]
    assert gap["row_count"] == 2
    assert artifact.rows["order"][-1]["reason"] == "gap_exit"
    assert artifact.rows["account"][-1]["state"] == "invalid_unknown"


def test_D03_missing_gap_pending_no_search():
    artifact = run("flat", "pair_l2_primary")
    assert artifact.summary["gap_count"] == 1
    assert artifact.artifacts["gaps"]["row_count"] == 1
    # The rejected authority row terminates the control; later snapshots are not opened.
    assert len(artifact.rows["account"]) == 2


def test_D04_real_flat_control():
    artifact = run("flat")
    assert artifact.summary["fill_count"] == 0
    assert Decimal(artifact.summary["final_NAV"]) == Decimal("1000")
    assert Decimal(artifact.summary["net_return"]) == 0
    assert artifact.rows["account"]


def test_D05_true_boundary_spot_buyhold():
    artifact = run("spot_buy_and_hold")
    first = artifact.rows["fill"][0]
    assert first["fill_at"] == "2025-01-01T01:00:00.000000Z"
    assert first["instrument"] == "BTC/USDT" and Decimal(first["signed_quantity"]) > 0
    assert Decimal(artifact.summary["explicit_cost_quote"]) > 0


def test_D06_independent_same_exposure_control():
    artifact = run("same_timestamp_same_absolute_exposure")
    assert artifact.summary["economic_run_spec_id"] == "directional_candle_primary"
    first = artifact.rows["fill"][0]
    assert first["instrument"] == "BTCUSDT_USD_M_perpetual"
    assert abs(Decimal(first["signed_quantity"])) == Decimal("0.1")
    assert first["fill_at"] == "2025-01-01T01:00:00.000000Z"


def test_K05_real_artifact_derivation():
    artifact = run("same_timestamp_same_absolute_exposure")
    assert isinstance(artifact.artifacts, FrozenDict)
    assert artifact.artifacts["ledgers"]["fill"]["row_count"] == len(artifact.rows["fill"])
    assert artifact.artifacts["ledgers"]["fill"]["sha256"] == canonical_sha256(artifact.rows["fill"])
    assert artifact.summary["rows_digest"] == canonical_sha256(artifact.rows)
    with pytest.raises(TypeError):
        artifact.summary["fill_count"] = 999


def test_R14_engine_owned_gap_sequence():
    artifact = run("spot_buy_and_hold")
    orders = artifact.rows["order"]
    assert orders[0]["reason"] == "ordinary_target"
    assert orders[1]["reason"] == "gap_exit"
    assert orders[1]["scenario_id"] == "candle-severe-80bps-rt-v1"
    assert orders[1]["event_sequence"] > orders[0]["event_sequence"]


def test_R15_controls_economic_not_tags():
    controls = {name: run(name) for name in CONTROL_IDS}
    assert controls["flat"].summary["fill_count"] == 0
    for name in ("spot_buy_and_hold", "same_timestamp_same_absolute_exposure"):
        item = controls[name]
        assert item.summary["fill_count"] >= 2
        assert Decimal(item.summary["turnover_quote"]) > 0
        assert Decimal(item.summary["explicit_cost_quote"]) > 0
        assert item.summary["rows_digest"] == canonical_sha256(item.rows)
    with pytest.raises(ControlError):
        run("mere_label")
