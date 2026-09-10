#!/usr/bin/env python3
"""Validate offline universe and partition evidence contracts and publish a manifest."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from trading_platform.research_evidence import (
    EvidenceContractError,
    canonical_json,
    iso_utc,
    load_point_in_time_universe,
    load_research_partition_registry,
    require_child_path,
    require_output_path,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = REPO_ROOT / "config/research"
OUTPUT_ROOT = REPO_ROOT / "artifacts/agent-level-experiment"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--partitions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    universe_path = require_child_path(args.universe, CONFIG_ROOT, "universe contract")
    partition_path = require_child_path(args.partitions, CONFIG_ROOT, "partition contract")
    output_dir = require_output_path(args.output_dir, OUTPUT_ROOT)
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"refusing to overwrite non-empty output directory: {output_dir}")

    universe = load_point_in_time_universe(universe_path, verify_local_evidence=True)
    registry = load_research_partition_registry(partition_path)
    if registry.strategy_family != "multi-asset-top2":
        raise EvidenceContractError("this validator run expects the multi-asset-top2 family")

    development = registry.partition("development-2021-2025-inspected")
    audit = universe.audit(development.start, development.end_exclusive)
    eligibility_error: str | None = None
    eligible_at_start: list[str] | None = None
    eligible_at_end: list[str] | None = None
    try:
        eligible_at_start = list(universe.eligible_pairs(development.start))
        eligible_at_end = list(
            universe.eligible_pairs(development.end_exclusive - timedelta(microseconds=1))
        )
    except EvidenceContractError as exc:
        eligibility_error = str(exc)

    clean_unseen = list(registry.clean_unseen_partition_ids())
    gates = {
        "point_in_time_universe_complete": audit.complete,
        "clean_unseen_partition_declared": bool(clean_unseen),
        "inspected_2026_not_relabelled_unseen": not registry.audit_unseen(
            "historical-2026-known-contaminated"
        ).genuinely_unseen,
        "minimum_embargo_at_least_label_horizon": (
            registry.minimum_embargo_hours >= registry.label_horizon_hours
        ),
    }
    ready = all(gates.values())
    report: dict[str, Any] = {
        "schema_version": "research-evidence-contract-validation-v1",
        "decision": "evidence_ready" if ready else "evidence_not_ready_fail_closed",
        "research_only": True,
        "live_trading_authorized": False,
        "external_services_used": False,
        "universe": {
            "universe_id": universe.universe_id,
            "venue": universe.venue,
            "quote_asset": universe.quote_asset,
            "inclusion_rule_id": universe.inclusion_rule_id,
            "inclusion_rule_definition": universe.inclusion_rule_definition,
            "inclusion_rule_point_in_time_defensible": (
                universe.inclusion_rule_point_in_time_defensible
            ),
            "frozen_at": iso_utc(universe.frozen_at),
            "coverage_start": iso_utc(universe.coverage_start),
            "coverage_end_exclusive": iso_utc(universe.coverage_end_exclusive),
            "candidate_pairs": list(universe.candidate_pairs),
            "evidence_source_count": len(universe.evidence),
            "development_audit": audit.as_dict(),
            "eligible_at_development_start": eligible_at_start,
            "eligible_at_development_end": eligible_at_end,
            "eligibility_error": eligibility_error,
        },
        "partitions": registry.summary(),
        "gates": gates,
        "failed_gates": sorted(name for name, passed in gates.items() if not passed),
        "next_requirement": (
            "Add evidence-backed, gap-free eligible/ineligible intervals under a new universe "
            "version and freeze a new locked prospective partition after the 48-hour embargo. "
            "Previously inspected 2026 data remains ineligible."
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    manifest = {
        "schema_version": "research-evidence-contract-manifest-v1",
        "universe_contract_sha256": sha256_file(universe_path),
        "partition_contract_sha256": sha256_file(partition_path),
        "validator_sha256": sha256_file(Path(__file__)),
        "research_evidence_module_sha256": sha256_file(
            REPO_ROOT / "src/trading_platform/research_evidence.py"
        ),
        "report_sha256": sha256_file(report_path),
    }
    (output_dir / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    print(
        canonical_json(
            {
                "output_dir": str(output_dir),
                "decision": report["decision"],
                "failed_gates": report["failed_gates"],
                "unknown_pairs": list(audit.unknown_pairs),
                "clean_unseen_partition_ids": clean_unseen,
            }
        )
    )


if __name__ == "__main__":
    main()
