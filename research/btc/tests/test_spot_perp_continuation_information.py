from __future__ import annotations

import ast
import copy
import gzip
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from trading_platform.research_spot_perp_continuation import (
    CANDIDATE_FEATURES,
    CONTROL_FEATURES,
    DAY_MS,
    FIVE_MINUTES_MS,
    HORIZON_MS,
    DailyPair,
    FiveMinuteOpen,
    SpotPerpContinuationError,
    build_feature_rows,
    build_label_rows,
    joint_three_month_bootstrap,
    load_feature_rows,
    ols,
    parse_utc_z_ms,
    record_digest,
    resolve_effective_contract,
    robust_z,
    sha256_file,
    walk_forward,
    write_jsonl_gzip,
)


ROOT = Path(__file__).resolve().parents[3]
UTC = timezone.utc


def ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def feature_contract(experiment_id: str = "synthetic-d1") -> dict:
    return {
        "candidate_experiment_id": "synthetic-candidate",
        "experiment_id": experiment_id,
        "feature_contract": {"robust_window_days": 90, "clip_absolute_z": 5},
    }


def make_feature(decision: datetime, index: int, experiment_id: str = "synthetic-d1") -> dict:
    values = {
        "lagged_72h_spot_return_z": math.sin(index * 0.11),
        "log_spot_rv7_z": math.cos(index * 0.071),
        "spot_turnover_z": ((index % 17) - 8) / 8,
        "basis_impulse_z": math.sin(index * 0.031 + 0.4),
        "spot_minus_perpetual_turnover_z": math.cos(index * 0.043 + 0.2),
    }
    row = {
        "available_at": iso(decision),
        "candidate_experiment_id": "synthetic-candidate",
        "decision_at": iso(decision),
        "experiment_id": experiment_id,
        "feature_values": values,
        "instrument": "BTC/USDT",
        "interval": "1d",
        "observed_at": iso(decision - timedelta(minutes=5)),
        "segment": "synthetic-0",
        "source_day_open_at": iso(decision - timedelta(days=1, minutes=5)),
        "source_manifest_sha256": "a" * 64,
        "source_window_start_at": iso(decision - timedelta(days=98, minutes=5)),
    }
    row["feature_digest"] = record_digest(row, "feature_digest")
    return row


def make_walk_forward_data() -> tuple[list[dict], list[dict], dict]:
    start = datetime(2019, 1, 1, 0, 5, tzinfo=UTC)
    end = datetime(2021, 7, 1, 0, 5, tzinfo=UTC)
    features = []
    labels = []
    current = start
    index = 0
    while current < end:
        feature = make_feature(current, index)
        values = feature["feature_values"]
        target = (
            0.001
            + 0.002 * values["lagged_72h_spot_return_z"]
            - 0.001 * values["log_spot_rv7_z"]
            + 0.0007 * values["spot_turnover_z"]
            + 0.0015 * values["basis_impulse_z"]
            + 0.0012 * values["spot_minus_perpetual_turnover_z"]
            + 0.0001 * math.sin(index * 0.17)
        )
        label = {
            "decision_at": feature["decision_at"],
            "experiment_id": "synthetic-d1",
            "feature_digest": feature["feature_digest"],
            "five_minute_segment": "synthetic-5m-0",
            "target_available_at": iso(current + timedelta(hours=72)),
            "target_return": target,
        }
        label["label_digest"] = record_digest(label, "label_digest")
        features.append(feature)
        labels.append(label)
        index += 1
        current += timedelta(days=1)
    contract = {
        "chronology": {
            "minimum_training_rows": 300,
            "evaluation_start_inclusive": "2021-01-01T00:05:00Z",
        },
        "experiment_id": "synthetic-d1",
    }
    return features, labels, contract


class SpotPerpContinuationInformationTests(unittest.TestCase):
    def test_effective_contract_preserves_frozen_v2_override(self) -> None:
        path = ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v2.json"
        contract = resolve_effective_contract(ROOT, path)
        self.assertEqual(contract["experiment_id"], "btc-spot-perp-continuation-information-d1-v2")
        self.assertNotIn("invalid_or_cross_segment_labels_maximum", contract["label_gates"])
        self.assertEqual(contract["label_gates"]["serialized_invalid_labels_maximum"], 0)
        self.assertFalse(contract["action_boundary"]["strategy_backtest_allowed"])

    def test_robust_z_uses_prior_window_and_fails_closed(self) -> None:
        values = [float(index) for index in range(102)]
        first = robust_z(values, 100, 90, 5)
        values[101] = -1_000_000
        self.assertEqual(first, robust_z(values, 100, 90, 5))
        values[100] = 1_000_000
        self.assertEqual(robust_z(values, 100, 90, 5), 5)
        self.assertIsNone(robust_z([1.0] * 100, 99, 90, 5))

    def test_features_are_point_in_time_and_contain_no_target(self) -> None:
        start = datetime(2020, 1, 1, tzinfo=UTC)
        pairs = []
        for index in range(180):
            spot = 10_000 * math.exp(index * 0.001 + 0.01 * math.sin(index * 0.13))
            basis = 0.001 * math.sin(index * 0.19)
            pairs.append(
                DailyPair(
                    ms(start + timedelta(days=index)),
                    spot,
                    1_000_000 * (1.1 + 0.1 * math.sin(index * 0.17)),
                    spot * math.exp(basis),
                    2_000_000 * (1.1 + 0.1 * math.cos(index * 0.23)),
                )
            )
        rows, diagnostics = build_feature_rows(pairs, feature_contract(), "b" * 64)
        self.assertGreater(len(rows), 70)
        self.assertEqual(diagnostics["unknown_after_minimum_history"], 0)
        first = rows[0]
        self.assertEqual(parse_utc_z_ms(first["decision_at"], "decision") % DAY_MS, FIVE_MINUTES_MS)
        self.assertLess(
            parse_utc_z_ms(first["source_day_open_at"], "source"),
            parse_utc_z_ms(first["observed_at"], "observed"),
        )
        self.assertNotIn("target", " ".join(first.keys()).lower())
        self.assertEqual(set(first["feature_values"]), set(CONTROL_FEATURES + CANDIDATE_FEATURES))
        self.assertEqual(first["feature_digest"], record_digest(first, "feature_digest"))

    def test_labels_require_exact_same_segment_opens(self) -> None:
        base = datetime(2020, 6, 1, 0, 5, tzinfo=UTC)
        features = [make_feature(base + timedelta(days=index), index) for index in range(3)]
        opens = {
            ms(base): FiveMinuteOpen("a", 100.0),
            ms(base) + HORIZON_MS: FiveMinuteOpen("a", 110.0),
            ms(base + timedelta(days=1)): FiveMinuteOpen("b", 100.0),
            ms(base + timedelta(days=1)) + HORIZON_MS: FiveMinuteOpen("c", 110.0),
        }
        labels, diagnostics = build_label_rows(features, opens, {"experiment_id": "synthetic-d1"})
        self.assertEqual(len(labels), 1)
        self.assertAlmostEqual(labels[0]["target_return"], math.log(1.1), places=12)
        self.assertEqual(diagnostics["excluded_cross_segment_candidates"], 1)
        self.assertEqual(diagnostics["excluded_missing_exact_open_candidates"], 1)
        self.assertEqual(diagnostics["serialized_invalid_labels"], 0)

    def test_ols_recovers_known_coefficients(self) -> None:
        x = np.asarray([[index, index * index] for index in range(-5, 6)], dtype=np.float64)
        y = 1.5 + 2.0 * x[:, 0] - 0.25 * x[:, 1]
        np.testing.assert_allclose(ols(y, x), [1.5, 2.0, -0.25], rtol=0, atol=1e-12)

    def test_monthly_walk_forward_does_not_use_same_month_targets(self) -> None:
        features, labels, contract = make_walk_forward_data()
        baseline, snapshots = walk_forward(features, labels, contract)
        changed = copy.deepcopy(labels)
        for label in changed:
            if label["decision_at"].startswith("2021-01"):
                label["target_return"] += 100.0
        challenged, _ = walk_forward(features, changed, contract)
        january_baseline = [row for row in baseline if row["decision_at"].startswith("2021-01")]
        january_challenged = [row for row in challenged if row["decision_at"].startswith("2021-01")]
        self.assertEqual(len(january_baseline), 31)
        for left, right in zip(january_baseline, january_challenged, strict=True):
            self.assertEqual(left["M0_prediction"], right["M0_prediction"])
            self.assertEqual(left["M1_prediction"], right["M1_prediction"])
        cutoff = parse_utc_z_ms(snapshots[0]["fit_cutoff"], "cutoff")
        expected = sum(
            parse_utc_z_ms(label["target_available_at"], "target") < cutoff for label in labels
        )
        self.assertEqual(snapshots[0]["training_rows"], expected)

    def test_bootstrap_is_seeded_and_deterministic(self) -> None:
        features, labels, contract = make_walk_forward_data()
        forecasts, _ = walk_forward(features, labels, contract)
        first = joint_three_month_bootstrap(forecasts, 50, 20260901)
        second = joint_three_month_bootstrap(forecasts, 50, 20260901)
        self.assertEqual(first, second)
        self.assertEqual(first["replications"], 50)

    def test_deterministic_gzip_and_bad_chronology_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = [make_feature(datetime(2020, 1, 2, 0, 5, tzinfo=UTC), 2)]
            first = directory / "first.jsonl.gz"
            second = directory / "second.jsonl.gz"
            write_jsonl_gzip(first, rows)
            write_jsonl_gzip(second, rows)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            reversed_rows = [
                make_feature(datetime(2020, 1, 3, 0, 5, tzinfo=UTC), 3),
                make_feature(datetime(2020, 1, 2, 0, 5, tzinfo=UTC), 2),
            ]
            reversed_path = directory / "reversed.jsonl.gz"
            write_jsonl_gzip(reversed_path, reversed_rows)
            with self.assertRaises(SpotPerpContinuationError):
                load_feature_rows(reversed_path, sha256_file(reversed_path), "synthetic-d1")

            future = make_feature(datetime(2026, 1, 1, 0, 5, tzinfo=UTC), 4)
            future_path = directory / "future.jsonl.gz"
            write_jsonl_gzip(future_path, [future])
            with self.assertRaises(SpotPerpContinuationError):
                load_feature_rows(future_path, sha256_file(future_path), "synthetic-d1")

    def test_research_code_has_no_network_or_production_client_imports(self) -> None:
        paths = [
            ROOT / "src/trading_platform/research_spot_perp_continuation.py",
            ROOT / "scripts/run_btc_spot_perp_continuation_information.py",
            ROOT / "scripts/audit_btc_spot_perp_continuation_information.py",
        ]
        prohibited = {"aiohttp", "ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests"}
        imported = set()
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
        self.assertFalse(imported.intersection(prohibited))


if __name__ == "__main__":
    unittest.main()
