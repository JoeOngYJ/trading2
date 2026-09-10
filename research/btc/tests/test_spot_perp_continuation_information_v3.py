from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading_platform.research_spot_perp_continuation import (
    FiveMinuteOpen,
    HORIZON_MS,
    YEAR_2026_MS,
    SpotPerpContinuationError,
    record_digest,
    resolve_effective_contract,
)
from trading_platform.research_spot_perp_continuation_v3 import (
    build_endpoint_label_rows,
    load_official_endpoints,
    relevant_gap_diagnostics,
    requested_endpoint_timestamps,
    resolve_v3_contract,
)


ROOT = Path(__file__).resolve().parents[3]
UTC = timezone.utc


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def feature(decision: datetime, digest: str = "f" * 64) -> dict:
    return {"decision_at": iso(decision), "feature_digest": digest}


class SpotPerpContinuationInformationV3Tests(unittest.TestCase):
    def test_v3_changes_only_endpoint_eligibility_and_identity(self) -> None:
        v2_path = ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v2.json"
        v3_path = ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v3.json"
        v2 = resolve_effective_contract(ROOT, v2_path)
        v3 = resolve_v3_contract(ROOT, v3_path)
        self.assertEqual(v3["experiment_id"], "btc-spot-perp-continuation-information-d1-v3")
        self.assertFalse(v3["target_contract"]["same_five_minute_segment_required"])
        self.assertTrue(v2["target_contract"]["same_five_minute_segment_required"])
        for key in ("chronology", "environment", "feature_contract", "label_gates", "model_contract", "model_gates", "statistics"):
            self.assertEqual(v3[key], v2[key])

    def test_requested_endpoints_exclude_targets_at_or_after_2026(self) -> None:
        rows = [
            feature(datetime(2025, 12, 28, 0, 5, tzinfo=UTC), "a" * 64),
            feature(datetime(2025, 12, 29, 0, 5, tzinfo=UTC), "b" * 64),
        ]
        needed = requested_endpoint_timestamps(rows)
        self.assertIn(ms(datetime(2025, 12, 31, 0, 5, tzinfo=UTC)), needed)
        self.assertNotIn(ms(datetime(2026, 1, 1, 0, 5, tzinfo=UTC)), needed)
        self.assertTrue(all(value < YEAR_2026_MS for value in needed))

    def test_endpoint_label_allows_diagnostic_interior_gap(self) -> None:
        decision = datetime(2021, 2, 9, 0, 5, tzinfo=UTC)
        features = [feature(decision)]
        endpoint_rows = []
        for at, price, digest in (
            (decision, "100.00000000", "a" * 64),
            (decision + timedelta(hours=72), "110.00000000", "b" * 64),
        ):
            endpoint_rows.append(
                {
                    "base_volume": "10.0",
                    "endpoint_at": iso(at),
                    "endpoint_digest": digest,
                    "official_open": price,
                    "quote_volume": "1000.0",
                }
            )
        gap_map = {
            ms(decision): [
                {
                    "after_open_ms": ms(decision + timedelta(hours=51)),
                    "before_open_ms": ms(decision + timedelta(hours=52, minutes=25)),
                    "missing_bars": 16,
                }
            ]
        }
        labels, diagnostics = build_endpoint_label_rows(
            features, endpoint_rows, gap_map, {"experiment_id": "synthetic-v3"}
        )
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["interior_gap_count"], 1)
        self.assertEqual(labels[0]["interior_missing_minutes"], 80)
        self.assertAlmostEqual(labels[0]["target_return"], 0.095310179804, places=12)
        self.assertEqual(diagnostics["excluded_missing_exact_endpoint_candidates"], 0)

    def test_gap_diagnostics_are_label_blind(self) -> None:
        decision = datetime(2021, 2, 9, 0, 5, tzinfo=UTC)
        manifest = {
            "gaps": [
                {
                    "after_open_ms": ms(decision + timedelta(hours=51)),
                    "before_open_ms": ms(decision + timedelta(hours=52, minutes=25)),
                    "missing_bars": 16,
                }
            ]
        }
        mapping, diagnostics = relevant_gap_diagnostics([feature(decision)], manifest)
        self.assertIn(ms(decision), mapping)
        self.assertEqual(diagnostics["candidates_crossing_interior_gaps"], 1)
        self.assertEqual(diagnostics["summed_missing_minutes_by_candidate_year"], {"2021": 80})

    def test_official_archive_endpoint_is_authenticated_and_matches_s1(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            name = "BTCUSDT-5m-2020-01.zip"
            opened = ms(datetime(2020, 1, 1, 0, 5, tzinfo=UTC))
            fields = [
                str(opened),
                "7200.12000000",
                "7201.00000000",
                "7199.00000000",
                "7200.50000000",
                "12.50000000",
                str(opened + 299_999),
                "90005.00000000",
                "100",
                "6.00000000",
                "43200.00000000",
                "0",
            ]
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator="\n").writerow(fields)
            archive_path = raw / name
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(name.removesuffix(".zip") + ".csv", buffer.getvalue())
            archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            source = {
                "accepted": True,
                "dataset": "binance-spot-klines",
                "files": [
                    {
                        "bytes": archive_path.stat().st_size,
                        "checksum_url": f"https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/5m/{name}.CHECKSUM",
                        "file": name,
                        "first_ms": opened,
                        "last_ms": opened,
                        "official_sha256": archive_sha,
                        "origin": "reused_verified_archive",
                        "rows": 1,
                        "source_url": f"https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/5m/{name}",
                        "timestamp_unit": "milliseconds",
                    }
                ],
            }
            manifest_path = raw / "btc-history-source-manifest.json"
            manifest_path.write_text(json.dumps(source), encoding="utf-8")
            contract = {
                "experiment_id": "synthetic-v3",
                "v3_spec": {
                    "bound_inputs": [{"path": "raw/btc-history-source-manifest.json"}],
                    "endpoint_audit_contract": {
                        "archive_end_period_inclusive": "2020-01",
                        "archive_start_period_inclusive": "2020-01",
                        "expected_archive_count": 1,
                        "expected_unique_endpoint_timestamps": 1,
                    },
                },
            }
            records, diagnostics = load_official_endpoints(
                root,
                contract,
                {opened},
                {opened: FiveMinuteOpen("synthetic-segment", 7200.12)},
            )
            self.assertEqual(diagnostics["missing_endpoint_count"], 0)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["official_open"], "7200.12000000")
            self.assertEqual(records[0]["endpoint_digest"], record_digest(records[0], "endpoint_digest"))

            source["files"][0]["official_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(SpotPerpContinuationError):
                load_official_endpoints(
                    root,
                    contract,
                    {opened},
                    {opened: FiveMinuteOpen("synthetic-segment", 7200.12)},
                )

    def test_v3_code_has_no_network_or_production_client_imports(self) -> None:
        paths = [
            ROOT / "src/trading_platform/research_spot_perp_continuation_v3.py",
            ROOT / "scripts/run_btc_spot_perp_continuation_information_v3.py",
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
