#!/usr/bin/env python3
"""Fail-closed validator for the frozen E0-v7 C0 authority-boundary design."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "btc-unified-backtest-engine-e0-v7-c0-authority-boundary"
CONTRACT = ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v7-c0-authority-boundary.json"
INTERFACE = ROOT / "research/btc/specs/btc-backtest-c0-authority-interface-e0-v7.json"
OBLIGATIONS = ROOT / "research/btc/specs/btc-backtest-c0-inherited-obligations-e0-v7.json"
BUNDLE = ROOT / "research/btc/candidates/unified-backtest-engine-e0-v7-c0-design/pre-review-bundle-manifest.json"
REVIEW = ROOT / "research/btc/reviews/btc-unified-backtest-engine-e0-v7-independent-review.json"
QUALIFICATION = ROOT / "artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v7-c0-design/qualification-report.json"

EXPECTED_CANONICAL_DIGESTS = {
    "contract": "046b1f4bf27ecc48a4d5ee11165bbf728b2293088e7c8b37d1dc23ba12d35951",
    "interface": "a142a4fc565030912899c23c96e2f89ec92dfd609de53c73fc769a74f70c5acf",
    "obligations": "7958b778d1a42a0795a26393c0061dd9ca865e313a314c031fcb28b1b3157491",
}
EXPECTED_FINDINGS = [
    {"finding_id": f"C0F{i:02d}", "owner": "C0", "probe_id": f"P{i:02d}"}
    for i in range(1, 15)
]
EXPECTED_GATES = [
    "canonical_JSON_rejects_duplicate_keys_and_nonfinite_numbers",
    "all_bound_authority_path_size_and_sha256_values_verify",
    "exact_interface_schema_and_all_nested_types_verify",
    "every_record_field_has_exact_type_nullability_producer_and_nonempty_consumers",
    "exact_C0_obligation_pointer_value_owner_and_probe_mapping_verifies",
    "failure_findings_have_unique_single_owner_and_unique_probe",
    "complete_design_bundle_path_role_size_and_digest_verifies",
    "mutation_tests_cover_schema_obligation_gate_role_and_future_boundary_drift",
    "hyphenated_and_underscored_premature_C1_C6_paths_fail",
    "two_independent_reviewers_pass_every_required_finding",
    "no_implementation_or_economic_evidence_was_created_or_opened",
    "only_no_trade_is_actionable",
]
EXPECTED_FUTURE_BOUNDARY = {
    "C0": "authority_manifest_and_RunContext_only",
    "C1": "deferred_unresolved_accounting_ledger",
    "C2": "deferred_unresolved_candle_execution",
    "C3": "deferred_unresolved_L2_execution",
    "C4": "deferred_unresolved_atomic_pair_execution",
    "C5": "deferred_unresolved_controls",
    "C6": "deferred_unresolved_integration_and_reporting",
}
EXPECTED_ROLES = [
    "c0_plan", "c0_failure_matrix", "c0_interface_spec", "c0_obligation_registry",
    "c0_contract", "c0_validator", "c0_tests",
]


class ValidationError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise ValidationError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )


def canonical_bytes(value: Any) -> bytes:
    def check(item: Any) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValidationError("non-finite value")
        if isinstance(item, dict):
            for nested in item.values():
                check(nested)
        elif isinstance(item, list):
            for nested in item:
                check(nested)
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def resolve_safe(relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValidationError("path must be a non-empty string")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or str(posix) != relative or "\\" in relative:
        raise ValidationError(f"unsafe or non-normalized path: {relative}")
    resolved = (ROOT / relative).resolve()
    if ROOT != resolved and ROOT not in resolved.parents:
        raise ValidationError(f"path leaves repository: {relative}")
    return resolved


def pointer_value(document: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ValidationError(f"invalid JSON pointer: {pointer}")
    value = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            value = value[int(token)]
        else:
            value = value[token]
    return value


def is_forbidden_future_relative_path(relative: str) -> bool:
    normalized = relative.lower().replace("_", "-")
    if "/invalid/" in f"/{normalized}/":
        return False
    component = re.search(r"(?:^|/)(?:btc-)?backtest-(?:accounting|ledger|candle|l2|pair|controls?|integration)-c[1-6](?:[./-]|$)", normalized)
    stage = re.search(r"unified-backtest-engine-(?:e1-v15|e2)(?:[./-]|$)", normalized)
    oracle = re.search(r"(?:^|/)(?:oracles?/.*(?:c[1-6]|e1-v15|e2)|.*(?:c[1-6]|e1-v15|e2).*oracles?)(?:[./-]|$)", normalized)
    return bool(component or stage or oracle)


def _validate_exact_document(name: str, document: Any) -> None:
    digest = sha256_bytes(canonical_bytes(document))
    if digest != EXPECTED_CANONICAL_DIGESTS[name]:
        raise ValidationError(f"{name} canonical digest drift: {digest}")


def _validate_interface(interface: dict[str, Any]) -> None:
    api = interface.get("supported_public_api")
    expected_arg = {"consumers": ["C0"], "name": "run_spec_id", "nullable": False, "producer": "caller", "type": "NonEmptyIdentifier"}
    if api != {
        "arguments": [expected_arg],
        "name": "build_run_context",
        "return_type": "RunContext",
        "security_claim": "deterministic_fail_closed_supported_public_API_not_hostile_Python_security",
    }:
        raise ValidationError("public API differs from run_spec_id-only boundary")
    types = interface.get("types")
    if not isinstance(types, dict) or not types:
        raise ValidationError("types missing")
    primitive_kinds = {"string", "integer", "enum", "literal"}
    for type_name, definition in types.items():
        kind = definition.get("kind")
        if kind == "record":
            fields = definition.get("fields")
            if not isinstance(fields, list) or not fields:
                raise ValidationError(f"{type_name} fields missing")
            names = [field.get("name") for field in fields]
            if len(names) != len(set(names)):
                raise ValidationError(f"{type_name} duplicate fields")
            for field in fields:
                if set(field) != {"name", "type", "nullable", "producer", "consumers"}:
                    raise ValidationError(f"{type_name}.{field.get('name')} incomplete ownership schema")
                if not isinstance(field["nullable"], bool) or not field["producer"] or not field["consumers"]:
                    raise ValidationError(f"{type_name}.{field['name']} invalid ownership schema")
                base = re.fullmatch(r"List\[([A-Za-z0-9_]+)\]", field["type"])
                referenced = base.group(1) if base else field["type"]
                if referenced not in types:
                    raise ValidationError(f"{type_name}.{field['name']} undefined type {referenced}")
        elif kind not in primitive_kinds:
            raise ValidationError(f"{type_name} has unknown kind {kind}")


def _validate_obligations(obligations: dict[str, Any]) -> None:
    rows = obligations.get("c0_owned_obligations")
    if not isinstance(rows, list) or len(rows) != 12:
        raise ValidationError("expected exactly twelve C0 obligations")
    if [row["obligation_id"] for row in rows] != [f"C0O{i:02d}" for i in range(1, 13)]:
        raise ValidationError("obligation IDs drift")
    for row in rows:
        if row["owner"] != "C0" or not re.fullmatch(r"P(?:0[1-9]|1[0-4])", row["probe_id"]):
            raise ValidationError(f"bad obligation owner/probe: {row['obligation_id']}")
        source = resolve_safe(row["source_path"])
        document = load_json(source)
        actual = sha256_bytes(canonical_bytes(pointer_value(document, row["source_pointer"])))
        if actual != row["value_sha256"]:
            raise ValidationError(f"obligation value mismatch: {row['obligation_id']}")
    deferred = obligations.get("deferred_inherited_domains")
    if [row.get("future_owner") for row in deferred] != [f"C{i}" for i in range(1, 7)]:
        raise ValidationError("C1-C6 deferred registry incomplete")
    if any(row.get("status") != "unresolved_not_closed" for row in deferred):
        raise ValidationError("a downstream domain was improperly closed")


def validate_documents(contract: dict[str, Any], interface: dict[str, Any], obligations: dict[str, Any]) -> None:
    _validate_exact_document("contract", contract)
    _validate_exact_document("interface", interface)
    _validate_exact_document("obligations", obligations)
    if contract.get("experiment_id") != EXPERIMENT_ID or interface.get("experiment_id") != EXPERIMENT_ID or obligations.get("experiment_id") != EXPERIMENT_ID:
        raise ValidationError("experiment identity mismatch")
    if contract.get("failure_findings") != EXPECTED_FINDINGS:
        raise ValidationError("failure owner/probe mapping drift")
    if contract.get("qualification_gates") != EXPECTED_GATES:
        raise ValidationError("qualification gates drift")
    if contract.get("future_component_boundary") != EXPECTED_FUTURE_BOUNDARY:
        raise ValidationError("future component boundary drift")
    if contract.get("required_bundle_roles") != EXPECTED_ROLES:
        raise ValidationError("required bundle roles drift")
    if contract.get("action_boundary") != {"actionable_arm_id": "no_trade", "may_create_order_intent_or_signal_payload": False, "may_route_or_trade": False}:
        raise ValidationError("action boundary drift")
    _validate_interface(interface)
    _validate_obligations(obligations)


def _validate_references(contract: dict[str, Any]) -> None:
    for key in ("bound_authorities", "design_bindings"):
        rows = contract[key]
        paths = [row["path"] for row in rows]
        roles = [row["role"] for row in rows]
        if len(paths) != len(set(paths)) or len(roles) != len(set(roles)):
            raise ValidationError(f"duplicate path or role in {key}")
        for row in rows:
            path = resolve_safe(row["path"])
            if not path.is_file() or sha256_file(path) != row["sha256"]:
                raise ValidationError(f"hash mismatch: {row['path']}")
            if "size_bytes" in row and path.stat().st_size != row["size_bytes"]:
                raise ValidationError(f"size mismatch: {row['path']}")


def _validate_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("experiment_id") != EXPERIMENT_ID or bundle.get("status") != "frozen_pre_review":
        raise ValidationError("bundle identity/status mismatch")
    files = bundle.get("files")
    if [row.get("role") for row in files] != EXPECTED_ROLES:
        raise ValidationError("bundle roles/order drift")
    paths = [row.get("path") for row in files]
    if len(paths) != len(set(paths)):
        raise ValidationError("bundle paths are not unique")
    for row in files:
        path = resolve_safe(row["path"])
        if not path.is_file() or path.stat().st_size != row.get("size_bytes") or sha256_file(path) != row.get("sha256"):
            raise ValidationError(f"bundle file mismatch: {row.get('path')}")


def _scan_future_paths() -> None:
    roots = [ROOT / "src", ROOT / "research/btc/tests", ROOT / "research/btc/contracts", ROOT / "research/btc/candidates", ROOT / "research/btc/oracles"]
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if is_forbidden_future_relative_path(path.relative_to(ROOT).as_posix()):
                raise ValidationError(f"premature future component path: {path.relative_to(ROOT)}")


def _validate_review(contract: dict[str, Any]) -> None:
    review = load_json(REVIEW)
    if review.get("experiment_id") != EXPERIMENT_ID or review.get("verdict") != "pass":
        raise ValidationError("independent review did not pass")
    reviewers = review.get("reviewers")
    if not isinstance(reviewers, list) or len(reviewers) != 2 or len(set(reviewers)) != 2:
        raise ValidationError("exactly two independent reviewers required")
    if review.get("bundle_manifest_sha256") != sha256_file(BUNDLE):
        raise ValidationError("review does not bind frozen bundle")
    findings = review.get("findings")
    required = contract["required_review_findings"]
    if [row.get("finding") for row in findings] != required or any(row.get("verdict") != "pass" for row in findings):
        raise ValidationError("review findings incomplete or non-pass")


def validate(qualification: bool = False) -> dict[str, Any]:
    contract, interface, obligations = load_json(CONTRACT), load_json(INTERFACE), load_json(OBLIGATIONS)
    validate_documents(contract, interface, obligations)
    _validate_references(contract)
    _validate_bundle(load_json(BUNDLE))
    _scan_future_paths()
    if qualification:
        _validate_review(contract)
    return {
        "experiment_id": EXPERIMENT_ID,
        "mode": "qualification" if qualification else "preflight",
        "checks_passed": 9 if qualification else 8,
        "status": "passed" if qualification else "frozen_pending_independent_review",
        "actionable_arm_id": "no_trade",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualification", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.qualification), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
