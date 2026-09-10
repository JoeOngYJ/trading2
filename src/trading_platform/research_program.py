"""Validation for the repository-owned BTC regime-routing program context.

Only local, checksummed files are read.  The validator has no network, database, message
bus, exchange, container, or runtime signal dependency.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_platform.research_routing import EvidenceStatus, StrategyArmRegistry


STAGE_STATES = frozenset({"planned", "active", "passed", "rejected", "blocked", "skipped"})
TERMINAL_STAGE_STATES = frozenset({"passed", "rejected", "skipped"})
FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "ccxt",
        "fastapi",
        "httpx",
        "nats",
        "psycopg",
        "requests",
        "sqlalchemy",
        "trading_platform.bridge",
        "trading_platform.contracts",
        "trading_platform.db",
        "trading_platform.execution_model",
        "trading_platform.nats_support",
        "trading_platform.repository",
        "trading_platform.worker",
    }
)


class ProgramContextError(ValueError):
    """Raised when program context is missing, stale, unsafe, or internally inconsistent."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")
    ) + "\n"


def canonical_json_line(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_digest(record: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key != "record_digest"}
    return hashlib.sha256(canonical_json_line(payload).encode("utf-8")).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ProgramContextError(f"{label} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProgramContextError(f"invalid {label}: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ProgramContextError(f"{label} must use explicit UTC")
    return parsed


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ProgramContextError(f"{label} must be a 64-character SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProgramContextError(f"{label} must be hexadecimal") from exc
    if value != value.lower():
        raise ProgramContextError(f"{label} must use lowercase hexadecimal")
    return value


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgramContextError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ProgramContextError(f"{label} must contain a JSON object")
    if raw != canonical_json(payload):
        raise ProgramContextError(f"{label} is not deterministically serialized")
    return payload


def _repo_path(repo_root: Path, raw_path: Any, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
        raise ProgramContextError(f"{label} must be a non-empty repository-relative path")
    boundary = repo_root.resolve(strict=True)
    candidate = (boundary / raw_path).resolve(strict=True)
    try:
        candidate.relative_to(boundary)
    except ValueError as exc:
        raise ProgramContextError(f"{label} escapes repository boundary: {raw_path}") from exc
    if not candidate.is_file():
        raise ProgramContextError(f"{label} is not a regular file: {raw_path}")
    return candidate


@dataclass(frozen=True, slots=True)
class ProgramValidation:
    program_id: str
    current_stage: str
    current_state: str
    active_stage: str | None
    artifact_count: int
    sealed_partition_ids: tuple[str, ...]
    decision_records: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_stage": self.active_stage,
            "artifact_count": self.artifact_count,
            "current_stage": self.current_stage,
            "current_state": self.current_state,
            "decision_records": self.decision_records,
            "program_id": self.program_id,
            "sealed_partition_ids": list(self.sealed_partition_ids),
        }


def validate_program_contract(payload: Mapping[str, Any]) -> tuple[str, dict[str, tuple[str, ...]]]:
    if payload.get("schema_version") != "regime-routing-program-v1":
        raise ProgramContextError("unsupported regime-routing program schema")
    program_id = str(payload.get("program_id", ""))
    if not program_id:
        raise ProgramContextError("program_id is required")
    stages_raw = payload.get("stages")
    if not isinstance(stages_raw, list) or not stages_raw:
        raise ProgramContextError("program stages must be a non-empty list")
    graph: dict[str, tuple[str, ...]] = {}
    for stage in stages_raw:
        if not isinstance(stage, dict):
            raise ProgramContextError("each program stage must be an object")
        stage_id = str(stage.get("stage_id", ""))
        if not stage_id or stage_id in graph:
            raise ProgramContextError("stage IDs must be non-empty and unique")
        dependencies = tuple(str(item) for item in stage.get("dependencies", ()))
        if len(dependencies) != len(set(dependencies)):
            raise ProgramContextError(f"stage {stage_id} repeats a dependency")
        if not stage.get("objective") or not stage.get("pass_gate") or not stage.get("next_action"):
            raise ProgramContextError(f"stage {stage_id} lacks objective, pass_gate, or next_action")
        graph[stage_id] = dependencies
    expected = tuple(f"S{index}" for index in range(8))
    if tuple(graph) != expected:
        raise ProgramContextError(f"program stages must be ordered exactly as {expected}")
    for stage_id, dependencies in graph.items():
        for dependency in dependencies:
            if dependency not in graph:
                raise ProgramContextError(f"stage {stage_id} has unknown dependency {dependency}")
            if expected.index(dependency) >= expected.index(stage_id):
                raise ProgramContextError(f"stage {stage_id} dependency is not prior: {dependency}")
    safety = payload.get("safety_boundaries", {})
    required_false = (
        "database_access_allowed",
        "exchange_access_allowed",
        "live_trading_authorized",
        "message_bus_access_allowed",
        "network_access_allowed",
        "order_intent_creation_allowed",
        "position_creation_allowed",
        "production_signal_creation_allowed",
        "running_soak_access_allowed",
    )
    if any(safety.get(key) is not False for key in required_false):
        raise ProgramContextError("program safety boundaries must explicitly disable runtime access")
    if safety.get("actionable_arm_id") != "no_trade":
        raise ProgramContextError("program actionable_arm_id must be no_trade")
    if safety.get("allowed_inputs") != ["synthetic_fixtures", "repository_metadata"]:
        raise ProgramContextError("S0 allowed inputs must remain synthetic fixtures and metadata")
    return program_id, graph


def validate_status(
    payload: Mapping[str, Any], program_id: str, graph: Mapping[str, tuple[str, ...]]
) -> tuple[str, str, str | None]:
    if payload.get("schema_version") != "regime-routing-program-status-v1":
        raise ProgramContextError("unsupported program-status schema")
    if payload.get("program_id") != program_id:
        raise ProgramContextError("status registry does not match program_id")
    records = payload.get("stages")
    if not isinstance(records, list) or len(records) != len(graph):
        raise ProgramContextError("status registry must contain every program stage exactly once")
    states: dict[str, str] = {}
    for record in records:
        stage_id = str(record.get("stage_id", ""))
        state = str(record.get("state", ""))
        if stage_id not in graph or stage_id in states:
            raise ProgramContextError(f"invalid or duplicate status stage: {stage_id}")
        if state not in STAGE_STATES:
            raise ProgramContextError(f"invalid stage state for {stage_id}: {state}")
        states[stage_id] = state
    active = tuple(stage_id for stage_id, state in states.items() if state == "active")
    if len(active) > 1:
        raise ProgramContextError("only one program stage may be active")
    for stage_id, state in states.items():
        if state in TERMINAL_STAGE_STATES or state == "active":
            unsatisfied = []
            for dependency in graph[stage_id]:
                dependency_state = states[dependency]
                satisfied = dependency_state in {"passed", "skipped"}
                if stage_id == "S4" and state == "skipped" and dependency == "S3":
                    satisfied = dependency_state in TERMINAL_STAGE_STATES
                if stage_id == "S5" and dependency == "S3":
                    satisfied = dependency_state in TERMINAL_STAGE_STATES
                if not satisfied:
                    unsatisfied.append(dependency)
            if unsatisfied:
                raise ProgramContextError(
                    f"stage {stage_id} skips unsatisfied prerequisites: {sorted(unsatisfied)}"
                )
    current = str(payload.get("current_stage", ""))
    if current not in graph:
        raise ProgramContextError("current_stage is not a declared stage")
    if active and current != active[0]:
        raise ProgramContextError("current_stage must identify the active stage")
    active_stage = active[0] if active else None
    return current, states[current], active_stage


def validate_decision_log(path: Path, known_stages: Sequence[str]) -> int:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProgramContextError(f"cannot read decision log: {path}") from exc
    if not raw or not raw.endswith("\n"):
        raise ProgramContextError("decision log must be non-empty and newline terminated")
    previous: str | None = None
    count = 0
    for line_number, line in enumerate(raw.splitlines(), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProgramContextError(f"decision log line {line_number} is invalid JSON") from exc
        if not isinstance(record, dict) or line != canonical_json_line(record):
            raise ProgramContextError(f"decision log line {line_number} is not canonical JSON")
        if record.get("sequence") != line_number:
            raise ProgramContextError("decision log sequences must be contiguous and one-based")
        if record.get("stage_id") not in known_stages:
            raise ProgramContextError(f"decision log line {line_number} has an unknown stage")
        _utc(record.get("recorded_at"), f"decision log line {line_number} recorded_at")
        if not record.get("decision") or not record.get("reason"):
            raise ProgramContextError(f"decision log line {line_number} lacks decision or reason")
        if record.get("previous_record_digest") != previous:
            raise ProgramContextError(f"decision log chain is broken at line {line_number}")
        observed = _digest(record.get("record_digest"), f"decision log line {line_number} digest")
        expected = record_digest(record)
        if observed != expected:
            raise ProgramContextError(f"decision log digest mismatch at line {line_number}")
        previous = observed
        count += 1
    return count


def validate_module_isolation(path: Path) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ProgramContextError(f"cannot parse isolated research module: {path}") from exc
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    violations = sorted(
        imported
        for imported in imports
        if any(imported == forbidden or imported.startswith(forbidden + ".") for forbidden in FORBIDDEN_IMPORT_ROOTS)
    )
    if violations:
        raise ProgramContextError(f"offline research module has forbidden imports: {violations}")


def validate_artifact_lineage(
    repo_root: Path, lineage: Sequence[Mapping[str, Any]], label: str = "artifact_lineage"
) -> None:
    seen: set[str] = set()
    for index, item in enumerate(lineage):
        raw_path = item.get("path")
        if raw_path in seen:
            raise ProgramContextError(f"{label} repeats artifact path: {raw_path}")
        path = _repo_path(repo_root, raw_path, f"{label}[{index}]")
        expected = _digest(item.get("sha256"), f"{label}[{index}] sha256")
        observed = sha256_file(path)
        if observed != expected:
            raise ProgramContextError(
                f"artifact checksum mismatch for {raw_path}: expected {expected}, got {observed}"
            )
        seen.add(str(raw_path))


def validate_s0_contract(repo_root: Path, path: Path) -> dict[str, Any]:
    payload = _load_canonical_json(path, "S0 frozen contract")
    if payload.get("schema_version") != "regime-routing-s0-contract-v1":
        raise ProgramContextError("unsupported S0 contract schema")
    if payload.get("status") != "frozen" or payload.get("stage_id") != "S0":
        raise ProgramContextError("S0 contract must be frozen and identify S0")
    if payload.get("permitted_inputs") != ["synthetic_fixtures", "repository_metadata"]:
        raise ProgramContextError("S0 contract permits unexpected inputs")
    if payload.get("action_contract", {}).get("actionable_arm_id") != "no_trade":
        raise ProgramContextError("S0 action contract must lock actionable_arm_id to no_trade")
    if payload.get("action_contract", {}).get("executable_output_allowed") is not False:
        raise ProgramContextError("S0 action contract must prohibit executable output")
    holdout = payload.get("sealed_partition", {})
    if holdout.get("access_state") != "sealed" or holdout.get("accessed_by_s0") is not False:
        raise ProgramContextError("S0 contract does not preserve the sealed partition")
    lineage = payload.get("lineage", ())
    validate_artifact_lineage(repo_root, lineage, "S0 lineage")
    registry_refs = [
        item
        for item in lineage
        if item.get("path") == "config/research/btc-regime-routing-arm-registry-v1.json"
    ]
    if len(registry_refs) != 1:
        raise ProgramContextError("S0 lineage must contain the initial arm registry exactly once")
    registry_path = _repo_path(repo_root, registry_refs[0]["path"], "S0 arm registry")
    registry_payload = _load_canonical_json(registry_path, "S0 arm registry")
    registry = StrategyArmRegistry.from_dict(registry_payload)
    dispositions = {arm.arm_id: arm.evidence_status for arm in registry.arms}
    expected = {
        "btc_bocpd_gated_breakout": EvidenceStatus.REJECTED,
        "btc_breakout_20d_10d": EvidenceStatus.DEVELOPMENT,
        "no_trade": EvidenceStatus.ELIGIBLE,
    }
    if dispositions != expected:
        raise ProgramContextError(f"unexpected S0 arm registry dispositions: {dispositions}")
    return payload


def validate_s1_contract(repo_root: Path, path: Path) -> dict[str, Any]:
    payload = _load_canonical_json(path, "S1 frozen contract")
    if payload.get("schema_version") != "regime-routing-s1-contract-v1":
        raise ProgramContextError("unsupported S1 contract schema")
    if (
        payload.get("experiment_id") != "btc-regime-routing-s1-ledger-v1"
        or payload.get("status") != "frozen"
        or payload.get("stage_id") != "S1"
    ):
        raise ProgramContextError("S1 contract identity is not frozen")
    data = payload.get("data", {})
    allowed_path = str(data.get("allowed_dataset_path", ""))
    if "holdout" in allowed_path.lower() or "2026-01-07" in allowed_path.lower():
        raise ProgramContextError("S1 contract points at a sealed holdout path")
    development_path = _repo_path(repo_root, allowed_path, "S1 development dataset")
    expected_dataset = _digest(
        data.get("development_dataset_sha256"), "S1 development_dataset_sha256"
    )
    if sha256_file(development_path) != expected_dataset:
        raise ProgramContextError("S1 development dataset checksum mismatch")
    manifest_path = _repo_path(
        repo_root, data.get("development_manifest_path"), "S1 development manifest"
    )
    if sha256_file(manifest_path) != _digest(
        data.get("development_manifest_sha256"), "S1 development_manifest_sha256"
    ):
        raise ProgramContextError("S1 development manifest checksum mismatch")
    if data.get("sealed_2026_path_allowed") is not False:
        raise ProgramContextError("S1 must explicitly prohibit the sealed 2026 path")
    isolation = payload.get("isolation", {})
    required_false = (
        "active_order_book_partial_access_allowed",
        "active_soak_access_allowed",
        "database_access_allowed",
        "exchange_access_allowed",
        "freqtrade_access_allowed",
        "holdout_access_allowed",
        "message_bus_access_allowed",
        "model_fitting_allowed",
        "network_access_allowed",
        "order_intent_creation_allowed",
        "position_creation_allowed",
        "production_signal_creation_allowed",
    )
    if any(isolation.get(key) is not False for key in required_false):
        raise ProgramContextError("S1 isolation boundary enables prohibited access")
    parameters = payload.get("parameters", {})
    fixed = {
        "account_fraction_per_entry": 0.1,
        "entry_channel_bars": 120,
        "exit_channel_bars": 60,
        "maximum_holding_days": 14,
        "protective_stop_fraction": 0.04,
    }
    if any(parameters.get(key) != value for key, value in fixed.items()):
        raise ProgramContextError("S1 changes the frozen fixed-breakout parameters")
    legacy = payload.get("legacy_parity", {})
    for prefix in ("legacy_contract", "legacy_report", "legacy_runner"):
        referenced = _repo_path(repo_root, legacy.get(f"{prefix}_path"), f"S1 {prefix}")
        expected = _digest(legacy.get(f"{prefix}_sha256"), f"S1 {prefix}_sha256")
        if sha256_file(referenced) != expected:
            raise ProgramContextError(f"S1 {prefix} checksum mismatch")
    if legacy.get("promotion_evidence") is not False:
        raise ProgramContextError("S1 reproduction cannot be promotion evidence")
    return payload


def validate_s1_evidence_manifest(repo_root: Path, path: Path) -> None:
    payload = _load_canonical_json(path, "S1 evidence manifest")
    if (
        payload.get("schema_version") != "btc-regime-routing-s1-manifest-v1"
        or payload.get("experiment_id") != "btc-regime-routing-s1-ledger-v1"
        or payload.get("decision") != "s1_passed_reproduction_only"
        or payload.get("holdout_accessed") is not False
        or payload.get("model_fitted") is not False
        or payload.get("promotion_evidence") is not False
    ):
        raise ProgramContextError("S1 evidence manifest has an unsafe or incomplete decision")
    for raw_path, raw_digest in payload.get("inputs", {}).items():
        lowered = str(raw_path).lower()
        if "holdout" in lowered or "2026-01-07" in lowered:
            raise ProgramContextError("S1 evidence manifest records prohibited holdout input")
        referenced = _repo_path(repo_root, raw_path, "S1 evidence input")
        if sha256_file(referenced) != _digest(raw_digest, "S1 evidence input sha256"):
            raise ProgramContextError(f"S1 evidence input changed: {raw_path}")
    implementation_paths = {
        "research_breakout.py": "src/trading_platform/research_breakout.py",
        "research_ledger.py": "src/trading_platform/research_ledger.py",
        "runner": "scripts/build_btc_regime_research_ledger.py",
    }
    if set(payload.get("implementations", {})) != set(implementation_paths):
        raise ProgramContextError("S1 evidence manifest implementation set changed")
    for name, raw_path in implementation_paths.items():
        referenced = _repo_path(repo_root, raw_path, f"S1 implementation {name}")
        expected = _digest(payload["implementations"][name], f"S1 implementation {name}")
        if sha256_file(referenced) != expected:
            raise ProgramContextError(f"S1 implementation changed after reproduction: {name}")
    output_dir = path.parent.resolve(strict=True)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ProgramContextError("S1 evidence manifest has no artifacts")
    for name, metadata in artifacts.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise ProgramContextError(f"invalid S1 artifact name: {name}")
        artifact = (output_dir / name).resolve(strict=True)
        if artifact.parent != output_dir:
            raise ProgramContextError(f"S1 artifact escapes output directory: {name}")
        expected = _digest(metadata.get("sha256"), f"S1 artifact {name} sha256")
        if sha256_file(artifact) != expected or artifact.stat().st_size != metadata.get("bytes"):
            raise ProgramContextError(f"S1 artifact changed: {name}")


def validate_s1_determinism(path: Path) -> None:
    payload = _load_canonical_json(path, "S1 determinism report")
    if (
        payload.get("schema_version") != "btc-regime-routing-s1-determinism-v1"
        or payload.get("experiment_id") != "btc-regime-routing-s1-ledger-v1"
        or payload.get("result") != "identical"
        or payload.get("mismatches") != []
        or payload.get("holdout_accessed") is not False
    ):
        raise ProgramContextError("S1 determinism verification did not pass safely")
    official = path.parent
    files = payload.get("files", {})
    if payload.get("core_file_count") != len(files):
        raise ProgramContextError("S1 determinism report file count differs")
    for name, raw_digest in files.items():
        artifact = (official / name).resolve(strict=True)
        if artifact.parent != official.resolve(strict=True):
            raise ProgramContextError(f"S1 determinism artifact escapes boundary: {name}")
        if sha256_file(artifact) != _digest(raw_digest, f"S1 determinism {name}"):
            raise ProgramContextError(f"S1 deterministic artifact changed: {name}")


def validate_s2_contract(repo_root: Path, path: Path) -> dict[str, Any]:
    payload = _load_canonical_json(path, "S2 frozen contract")
    if (
        payload.get("schema_version") != "regime-routing-s2-ewma-contract-v1"
        or payload.get("experiment_id") != "btc-regime-routing-s2-ewma-v1"
        or payload.get("status") != "frozen"
        or payload.get("stage_id") != "S2"
    ):
        raise ProgramContextError("S2 contract identity is not frozen")
    isolation = payload.get("isolation", {})
    required_false = (
        "active_order_book_partial_access_allowed",
        "active_soak_access_allowed",
        "database_access_allowed",
        "exchange_access_allowed",
        "freqtrade_access_allowed",
        "holdout_access_allowed",
        "message_bus_access_allowed",
        "network_access_allowed",
        "order_intent_creation_allowed",
        "position_creation_allowed",
        "production_signal_creation_allowed",
    )
    if any(isolation.get(key) is not False for key in required_false):
        raise ProgramContextError("S2 isolation boundary enables prohibited access")
    action = payload.get("action_mapping", {})
    if (
        action.get("actionable_arm_id") != "no_trade"
        or action.get("direction_changes_allowed") is not False
        or action.get("intra_trade_rebalancing_allowed") is not False
        or action.get("locked_s1_opportunity_path") is not True
        or action.get("maximum_allocation_fraction") != 0.1
    ):
        raise ProgramContextError("S2 action mapping is not safely frozen")
    parameters = payload.get("parameters", {})
    frozen = {
        "annualization_days": 365,
        "base_allocation_fraction": 0.1,
        "daily_decay_lambda": 0.94,
        "forecast_maximum_age_hours_exclusive": 24,
        "maximum_planned_risk_fraction": 0.005,
        "protective_stop_fraction": 0.04,
        "target_annualized_volatility": 0.4,
    }
    if any(parameters.get(key) != value for key, value in frozen.items()):
        raise ProgramContextError("S2 changes a frozen primary parameter")
    if payload.get("initialization", {}).get("minimum_returns") != 30:
        raise ProgramContextError("S2 initialization is not frozen to 30 returns")
    gates = payload.get("validity_gates", {})
    if (
        gates.get("minimum_opportunity_coverage_overall") != 0.95
        or gates.get("minimum_opportunity_coverage_each_calendar_year") != 0.9
        or gates.get("s1_fixed_result_exact_parity_required") is not True
    ):
        raise ProgramContextError("S2 validity gates changed")
    data = payload.get("data", {})
    if data.get("sealed_2026_path_allowed") is not False:
        raise ProgramContextError("S2 must prohibit the sealed 2026 path")
    boundary = _repo_path(repo_root, data.get("evidence_boundary_path"), "S2 boundary")
    if sha256_file(boundary) != _digest(
        data.get("evidence_boundary_sha256"), "S2 evidence_boundary_sha256"
    ):
        raise ProgramContextError("S2 evidence-boundary checksum mismatch")
    boundary_payload = _load_canonical_json(boundary, "S2 evidence boundary")
    if (
        boundary_payload.get("registry_id")
        != "btc-directional-trend-evidence-boundaries-v2"
        or boundary_payload.get("status") != "frozen_no_clean_unseen_partition"
    ):
        raise ProgramContextError("S2 evidence boundary is unsafe")
    partitions = {item.get("partition_id"): item for item in boundary_payload.get("partitions", ())}
    sealed = partitions.get("btc-2026-jan-jul-sealed-ineligible", {})
    if sealed.get("access_state") != "sealed_ineligible" or sealed.get("allowed_purposes") != []:
        raise ProgramContextError("S2 boundary does not retain sealed-ineligible 2026")
    source_root = str(data.get("s1_source_root", ""))
    if not source_root or "s1-ledger-v1" not in source_root or "holdout" in source_root.lower():
        raise ProgramContextError("S2 source root is not immutable S1 evidence")
    for name, metadata in data.get("s1_source_artifacts", {}).items():
        if Path(name).name != name:
            raise ProgramContextError(f"invalid S2 source artifact name: {name}")
        source = _repo_path(repo_root, f"{source_root}/{name}", f"S2 source {name}")
        expected = _digest(metadata.get("sha256"), f"S2 source {name} sha256")
        if sha256_file(source) != expected:
            raise ProgramContextError(f"S2 source artifact changed: {name}")
    if payload.get("economic_scorecard", {}).get(
        "stage_can_pass_when_development_overlay_gate_is_false"
    ) is not True:
        raise ProgramContextError("S2 must freeze the EWMA control regardless of economics")
    return payload


def validate_s2_evidence_manifest(repo_root: Path, path: Path) -> None:
    payload = _load_canonical_json(path, "S2 evidence manifest")
    if (
        payload.get("schema_version") != "btc-regime-routing-s2-manifest-v1"
        or payload.get("experiment_id") != "btc-regime-routing-s2-ewma-v1"
        or payload.get("decision")
        not in {"s2_passed_benchmark_frozen", "s2_rejected_insufficient_risk_coverage"}
        or payload.get("holdout_accessed") is not False
        or payload.get("model_fitted") is not False
        or payload.get("promotion_evidence") is not False
        or payload.get("actionable_arm_id") != "no_trade"
    ):
        raise ProgramContextError("S2 evidence manifest has an unsafe or incomplete decision")
    for raw_path, raw_digest in payload.get("inputs", {}).items():
        lowered = str(raw_path).lower()
        if "holdout" in lowered or "2026-01-07" in lowered:
            raise ProgramContextError("S2 evidence manifest records prohibited holdout input")
        referenced = _repo_path(repo_root, raw_path, "S2 evidence input")
        if sha256_file(referenced) != _digest(raw_digest, "S2 evidence input sha256"):
            raise ProgramContextError(f"S2 evidence input changed: {raw_path}")
    implementation_paths = {
        "research_evidence.py": "src/trading_platform/research_evidence.py",
        "research_volatility.py": "src/trading_platform/research_volatility.py",
        "runner": "scripts/run_btc_regime_routing_s2_ewma.py",
    }
    if set(payload.get("implementations", {})) != set(implementation_paths):
        raise ProgramContextError("S2 evidence manifest implementation set changed")
    for name, raw_path in implementation_paths.items():
        referenced = _repo_path(repo_root, raw_path, f"S2 implementation {name}")
        expected = _digest(payload["implementations"][name], f"S2 implementation {name}")
        if sha256_file(referenced) != expected:
            raise ProgramContextError(f"S2 implementation changed after evaluation: {name}")
    output_dir = path.parent.resolve(strict=True)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ProgramContextError("S2 evidence manifest has no artifacts")
    for name, metadata in artifacts.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise ProgramContextError(f"invalid S2 artifact name: {name}")
        artifact = (output_dir / name).resolve(strict=True)
        if artifact.parent != output_dir:
            raise ProgramContextError(f"S2 artifact escapes output directory: {name}")
        expected = _digest(metadata.get("sha256"), f"S2 artifact {name} sha256")
        if sha256_file(artifact) != expected or artifact.stat().st_size != metadata.get("bytes"):
            raise ProgramContextError(f"S2 artifact changed: {name}")


def validate_s2_determinism(path: Path) -> None:
    payload = _load_canonical_json(path, "S2 determinism report")
    if (
        payload.get("schema_version") != "btc-regime-routing-s2-determinism-v1"
        or payload.get("experiment_id") != "btc-regime-routing-s2-ewma-v1"
        or payload.get("result") != "identical"
        or payload.get("mismatches") != []
        or payload.get("holdout_accessed") is not False
    ):
        raise ProgramContextError("S2 determinism verification did not pass safely")
    official = path.parent.resolve(strict=True)
    files = payload.get("files", {})
    if payload.get("core_file_count") != len(files):
        raise ProgramContextError("S2 determinism report file count differs")
    for name, raw_digest in files.items():
        artifact = (official / name).resolve(strict=True)
        if artifact.parent != official:
            raise ProgramContextError(f"S2 determinism artifact escapes boundary: {name}")
        if sha256_file(artifact) != _digest(raw_digest, f"S2 determinism {name}"):
            raise ProgramContextError(f"S2 deterministic artifact changed: {name}")


def validate_s2_v2_contract(repo_root: Path, path: Path) -> dict[str, Any]:
    """Validate the frozen close-only S2 successor without weakening the v1 record."""

    payload = _load_canonical_json(path, "S2-v2 frozen contract")
    if (
        payload.get("schema_version") != "regime-routing-s2-ewma-contract-v2"
        or payload.get("experiment_id") != "btc-regime-routing-s2-ewma-v2"
        or payload.get("status") != "frozen"
        or payload.get("stage_id") != "S2"
    ):
        raise ProgramContextError("S2-v2 contract identity is not frozen")
    isolation = payload.get("isolation", {})
    required_false = (
        "active_order_book_partial_access_allowed",
        "active_soak_access_allowed",
        "database_access_allowed",
        "exchange_access_allowed",
        "freqtrade_access_allowed",
        "holdout_access_allowed",
        "message_bus_access_allowed",
        "network_access_allowed",
        "order_intent_creation_allowed",
        "position_creation_allowed",
        "production_signal_creation_allowed",
    )
    if any(isolation.get(key) is not False for key in required_false):
        raise ProgramContextError("S2-v2 isolation boundary enables prohibited access")
    action = payload.get("action_mapping", {})
    if (
        action.get("actionable_arm_id") != "no_trade"
        or action.get("direction_changes_allowed") is not False
        or action.get("intra_trade_rebalancing_allowed") is not False
        or action.get("locked_s1_opportunity_path") is not True
        or action.get("maximum_allocation_fraction") != 0.1
    ):
        raise ProgramContextError("S2-v2 action mapping is not safely frozen")
    parameters = payload.get("parameters", {})
    frozen = {
        "annualization_days": 365,
        "base_allocation_fraction": 0.1,
        "daily_decay_lambda": 0.94,
        "forecast_maximum_age_hours_exclusive": 24,
        "maximum_planned_risk_fraction": 0.005,
        "protective_stop_fraction": 0.04,
        "target_annualized_volatility": 0.4,
    }
    if any(parameters.get(key) != value for key, value in frozen.items()):
        raise ProgramContextError("S2-v2 changes a frozen primary parameter")
    if payload.get("initialization", {}).get("minimum_returns") != 30:
        raise ProgramContextError("S2-v2 initialization is not frozen to 30 returns")
    gates = payload.get("validity_gates", {})
    if (
        gates.get("minimum_opportunity_coverage_overall") != 0.95
        or gates.get("minimum_opportunity_coverage_each_calendar_year") != 0.9
        or gates.get("s1_fixed_result_exact_parity_required") is not True
    ):
        raise ProgramContextError("S2-v2 validity gates changed")
    data = payload.get("data", {})
    if data.get("sealed_2026_path_allowed") is not False:
        raise ProgramContextError("S2-v2 must prohibit the sealed 2026 path")
    boundary = _repo_path(repo_root, data.get("evidence_boundary_path"), "S2-v2 boundary")
    if sha256_file(boundary) != _digest(
        data.get("evidence_boundary_sha256"), "S2-v2 evidence_boundary_sha256"
    ):
        raise ProgramContextError("S2-v2 evidence-boundary checksum mismatch")
    boundary_payload = _load_canonical_json(boundary, "S2-v2 evidence boundary")
    partitions = {item.get("partition_id"): item for item in boundary_payload.get("partitions", ())}
    sealed = partitions.get("btc-2026-jan-jul-sealed-ineligible", {})
    if (
        boundary_payload.get("registry_id")
        != "btc-directional-trend-evidence-boundaries-v2"
        or boundary_payload.get("status") != "frozen_no_clean_unseen_partition"
        or sealed.get("access_state") != "sealed_ineligible"
        or sealed.get("allowed_purposes") != []
    ):
        raise ProgramContextError("S2-v2 evidence boundary is unsafe")
    source_root = str(data.get("s1_source_root", ""))
    if not source_root or "s1-ledger-v1" not in source_root or "holdout" in source_root.lower():
        raise ProgramContextError("S2-v2 source root is not immutable S1 evidence")
    for name, metadata in data.get("s1_source_artifacts", {}).items():
        if Path(name).name != name:
            raise ProgramContextError(f"invalid S2-v2 source artifact name: {name}")
        source = _repo_path(repo_root, f"{source_root}/{name}", f"S2-v2 source {name}")
        expected = _digest(metadata.get("sha256"), f"S2-v2 source {name} sha256")
        if sha256_file(source) != expected:
            raise ProgramContextError(f"S2-v2 source artifact changed: {name}")
    daily = data.get("daily_risk_source", {})
    if (
        daily.get("feature_fields") != ["close"]
        or daily.get("independent_of_execution_segment") is not True
        or daily.get("expected_rows") != 3059
        or daily.get("source_segment_id")
        != "binance-direct-daily-continuous-2017-2025-v1"
    ):
        raise ProgramContextError("S2-v2 daily risk source is not the frozen close-only series")
    for stem in ("dataset", "audit_manifest", "audit_report"):
        source = _repo_path(repo_root, daily.get(f"{stem}_path"), f"S2-v2 {stem}")
        expected = _digest(daily.get(f"{stem}_sha256"), f"S2-v2 {stem} sha256")
        if sha256_file(source) != expected:
            raise ProgramContextError(f"S2-v2 {stem} checksum mismatch")
    disclosure = payload.get("source_discrepancy_disclosure", {})
    if (
        disclosure.get("all_overlapping_direct_daily_closes_match_s1") is not True
        or disclosure.get("official_1d_and_5m_open_or_volume_fields_can_differ") is not True
        or disclosure.get("ohlc_or_volume_fields_used_by_risk_model") is not False
        or disclosure.get("rejected_all_ohlc_audit_id")
        != "btc-regime-routing-s2-daily-data-audit-v1"
    ):
        raise ProgramContextError("S2-v2 does not preserve the source discrepancy disclosure")
    if payload.get("economic_scorecard", {}).get(
        "stage_can_pass_when_development_overlay_gate_is_false"
    ) is not True:
        raise ProgramContextError("S2-v2 must freeze the EWMA control regardless of economics")
    return payload


def validate_s2_v2_evidence_manifest(repo_root: Path, path: Path) -> None:
    payload = _load_canonical_json(path, "S2-v2 evidence manifest")
    if (
        payload.get("schema_version") != "btc-regime-routing-s2-manifest-v2"
        or payload.get("experiment_id") != "btc-regime-routing-s2-ewma-v2"
        or payload.get("decision") != "s2_passed_benchmark_frozen"
        or payload.get("holdout_accessed") is not False
        or payload.get("model_fitted") is not False
        or payload.get("promotion_evidence") is not False
        or payload.get("actionable_arm_id") != "no_trade"
    ):
        raise ProgramContextError("S2-v2 evidence manifest has an unsafe or incomplete decision")
    for raw_path, raw_digest in payload.get("inputs", {}).items():
        lowered = str(raw_path).lower()
        if "holdout" in lowered or "2026-01-07" in lowered:
            raise ProgramContextError("S2-v2 evidence manifest records prohibited holdout input")
        referenced = _repo_path(repo_root, raw_path, "S2-v2 evidence input")
        if sha256_file(referenced) != _digest(raw_digest, "S2-v2 evidence input sha256"):
            raise ProgramContextError(f"S2-v2 evidence input changed: {raw_path}")
    implementation_paths = {
        "research_volatility.py": "src/trading_platform/research_volatility.py",
        "runner": "scripts/run_btc_regime_routing_s2_ewma_v2.py",
    }
    if set(payload.get("implementations", {})) != set(implementation_paths):
        raise ProgramContextError("S2-v2 evidence manifest implementation set changed")
    for name, raw_path in implementation_paths.items():
        referenced = _repo_path(repo_root, raw_path, f"S2-v2 implementation {name}")
        expected = _digest(payload["implementations"][name], f"S2-v2 implementation {name}")
        if sha256_file(referenced) != expected:
            raise ProgramContextError(f"S2-v2 implementation changed after evaluation: {name}")
    output_dir = path.parent.resolve(strict=True)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ProgramContextError("S2-v2 evidence manifest has no artifacts")
    for name, metadata in artifacts.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise ProgramContextError(f"invalid S2-v2 artifact name: {name}")
        artifact = (output_dir / name).resolve(strict=True)
        if artifact.parent != output_dir:
            raise ProgramContextError(f"S2-v2 artifact escapes output directory: {name}")
        expected = _digest(metadata.get("sha256"), f"S2-v2 artifact {name} sha256")
        if sha256_file(artifact) != expected or artifact.stat().st_size != metadata.get("bytes"):
            raise ProgramContextError(f"S2-v2 artifact changed: {name}")


def validate_s2_v2_determinism(repo_root: Path, path: Path) -> None:
    payload = _load_canonical_json(path, "S2-v2 determinism report")
    if (
        payload.get("schema_version") != "btc-regime-routing-determinism-verification-v1"
        or payload.get("experiment_id") != "btc-regime-routing-s2-ewma-v2"
        or payload.get("byte_identical") is not True
    ):
        raise ProgramContextError("S2-v2 determinism verification did not pass safely")
    official = _repo_path(
        repo_root, f"{payload.get('official_output')}/manifest.json", "S2-v2 official output"
    ).parent
    replay = _repo_path(
        repo_root, f"{payload.get('replay_output')}/manifest.json", "S2-v2 replay output"
    ).parent
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ProgramContextError("S2-v2 determinism report has no artifacts")
    for name, raw_digest in artifacts.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise ProgramContextError(f"invalid S2-v2 deterministic artifact name: {name}")
        expected = _digest(raw_digest, f"S2-v2 determinism {name}")
        for label, output_dir in (("official", official), ("replay", replay)):
            artifact = (output_dir / name).resolve(strict=True)
            if artifact.parent != output_dir or sha256_file(artifact) != expected:
                raise ProgramContextError(f"S2-v2 {label} deterministic artifact changed: {name}")


def validate_s3_contracts(repo_root: Path, base_path: Path, amendment_path: Path) -> None:
    base = _load_canonical_json(base_path, "S3 base contract")
    if (
        base.get("schema_version") != "regime-routing-s3-student-t-hmm-contract-v1"
        or base.get("experiment_id") != "btc-regime-routing-s3-student-t-hmm-v1"
        or base.get("stage_id") != "S3"
        or base.get("status") != "frozen"
    ):
        raise ProgramContextError("S3 base contract identity is not frozen")
    if any(
        value is not False
        for key, value in base.get("isolation", {}).items()
        if key.endswith("_allowed")
    ):
        raise ProgramContextError("S3 isolation boundary enables prohibited access")
    action = base.get("action_mapping", {})
    if (
        action.get("actionable_arm_id") != "no_trade"
        or action.get("maximum_allocation_fraction") != 0.1
        or action.get("minimum_multiplier_when_known") != 0.5
        or action.get("direction_changes_allowed") is not False
        or action.get("state_probability_changes_entry_eligibility") is not False
    ):
        raise ProgramContextError("S3 action mapping is not safely frozen")
    fitting = base.get("fitting", {})
    if (
        fitting.get("degrees_of_freedom") != 5
        or fitting.get("minimum_training_observations") != 365
        or fitting.get("minimum_self_transition_probability") != 0.9
        or fitting.get("maximum_em_iterations") != 100
        or fitting.get("emission") != "multivariate_independent_student_t"
        or fitting.get("covariance") != "diagonal"
    ):
        raise ProgramContextError("S3 fitting parameters changed")
    if len(base.get("features", {}).get("definitions", ())) != 4:
        raise ProgramContextError("S3 must freeze exactly four risk features")
    data = base.get("data", {})
    if data.get("sealed_2026_path_allowed") is not False:
        raise ProgramContextError("S3 enables sealed data")
    daily = data.get("daily_risk_source", {})
    if daily.get("feature_fields") != ["close", "high", "low"] or "open" not in daily.get(
        "prohibited_fields", ()
    ):
        raise ProgramContextError("S3 daily source fields changed")
    for stem in (
        "evidence_boundary",
        "s1_candles",
        "s1_opportunities",
        "s1_report",
        "s2_allocations",
        "s2_contract",
        "s2_manifest",
        "s2_report",
    ):
        path = _repo_path(repo_root, data.get(f"{stem}_path"), f"S3 {stem}")
        if sha256_file(path) != _digest(data.get(f"{stem}_sha256"), f"S3 {stem} sha256"):
            raise ProgramContextError(f"S3 {stem} checksum mismatch")
    for stem in ("dataset", "audit_report"):
        path = _repo_path(repo_root, daily.get(f"{stem}_path"), f"S3 daily {stem}")
        if sha256_file(path) != _digest(
            daily.get(f"{stem}_sha256"), f"S3 daily {stem} sha256"
        ):
            raise ProgramContextError(f"S3 daily {stem} checksum mismatch")
    amendment = _load_canonical_json(amendment_path, "S3 successor contract")
    if (
        amendment.get("schema_version")
        != "regime-routing-s3-student-t-hmm-contract-amendment-v1"
        or amendment.get("experiment_id") != "btc-regime-routing-s3-student-t-hmm-v2"
        or amendment.get("stage_id") != "S3"
        or amendment.get("status") != "frozen"
        or amendment.get("base_contract_sha256") != sha256_file(base_path)
        or amendment.get("base_contract_path")
        != str(base_path.resolve(strict=True).relative_to(repo_root.resolve(strict=True)))
    ):
        raise ProgramContextError("S3 successor does not bind the frozen base")
    clarifications = amendment.get("clarifications", {})
    if set(clarifications) != {
        "dwell_and_transition_accounting",
        "fit_convergence",
        "forward_filtering",
        "forward_labels",
        "month_block_bootstrap",
        "strictly_positive_ci_gate",
    }:
        raise ProgramContextError("S3 successor clarification set changed")


def validate_s3_evidence_manifest(repo_root: Path, path: Path) -> None:
    payload = _load_canonical_json(path, "S3 evidence manifest")
    if (
        payload.get("schema_version") != "btc-regime-routing-s3-manifest-v1"
        or payload.get("experiment_id") != "btc-regime-routing-s3-student-t-hmm-v2"
        or payload.get("decision")
        not in {
            "s3_passed_all_gates_s4_skipped",
            "s3_rejected_overlay_gates_s4_skipped",
            "s3_rejected_s4_jump_model_eligible",
            "s3_rejected_s4_skipped",
            "s3_rejected_stop_latent_branch",
        }
        or payload.get("holdout_accessed") is not False
        or payload.get("model_fitted") is not True
        or payload.get("promotion_evidence") is not False
        or payload.get("actionable_arm_id") != "no_trade"
    ):
        raise ProgramContextError("S3 evidence manifest has an unsafe decision")
    for raw_path, raw_digest in payload.get("inputs", {}).items():
        lowered = str(raw_path).lower()
        if "holdout" in lowered or "2026-01-07" in lowered:
            raise ProgramContextError("S3 evidence records prohibited holdout input")
        referenced = _repo_path(repo_root, raw_path, "S3 evidence input")
        if sha256_file(referenced) != _digest(raw_digest, "S3 evidence input sha256"):
            raise ProgramContextError(f"S3 evidence input changed: {raw_path}")
    implementation_paths = {
        "research_hmm.py": "src/trading_platform/research_hmm.py",
        "runner": "scripts/run_btc_regime_routing_s3_hmm.py",
    }
    if set(payload.get("implementations", {})) != set(implementation_paths):
        raise ProgramContextError("S3 implementation set changed")
    for name, raw_path in implementation_paths.items():
        referenced = _repo_path(repo_root, raw_path, f"S3 implementation {name}")
        if sha256_file(referenced) != _digest(
            payload["implementations"][name], f"S3 implementation {name}"
        ):
            raise ProgramContextError(f"S3 implementation changed after evaluation: {name}")
    output_dir = path.parent.resolve(strict=True)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ProgramContextError("S3 evidence manifest has no artifacts")
    for name, metadata in artifacts.items():
        artifact = (output_dir / name).resolve(strict=True)
        if artifact.parent != output_dir:
            raise ProgramContextError(f"S3 artifact escapes output boundary: {name}")
        if sha256_file(artifact) != _digest(metadata.get("sha256"), f"S3 artifact {name}"):
            raise ProgramContextError(f"S3 artifact changed: {name}")


def validate_s3_determinism(repo_root: Path, path: Path) -> None:
    payload = _load_canonical_json(path, "S3 determinism report")
    if (
        payload.get("schema_version") != "btc-regime-routing-determinism-verification-v1"
        or payload.get("experiment_id") != "btc-regime-routing-s3-student-t-hmm-v2"
        or payload.get("byte_identical") is not True
    ):
        raise ProgramContextError("S3 determinism verification did not pass")
    official = _repo_path(
        repo_root, f"{payload.get('official_output')}/manifest.json", "S3 official output"
    ).parent
    replay = _repo_path(
        repo_root, f"{payload.get('replay_output')}/manifest.json", "S3 replay output"
    ).parent
    for name, raw_digest in payload.get("artifacts", {}).items():
        expected = _digest(raw_digest, f"S3 determinism {name}")
        for output_dir in (official, replay):
            artifact = (output_dir / name).resolve(strict=True)
            if artifact.parent != output_dir or sha256_file(artifact) != expected:
                raise ProgramContextError(f"S3 deterministic artifact changed: {name}")


def validate_program_context(
    repo_root: Path, program_path: Path, status_path: Path, s0_contract_path: Path
) -> ProgramValidation:
    root = repo_root.resolve(strict=True)
    program = _load_canonical_json(program_path, "program contract")
    program_id, graph = validate_program_contract(program)
    status = _load_canonical_json(status_path, "program status")
    current_stage, current_state, active_stage = validate_status(status, program_id, graph)
    validate_s0_contract(root, s0_contract_path)
    s1_contract_path = root / "config/experiments/btc-regime-routing-s1-ledger-v1.json"
    s1_stage = next(item for item in status["stages"] if item["stage_id"] == "S1")
    if s1_stage["state"] != "planned":
        validate_s1_contract(root, s1_contract_path)
    s2_contract_path = root / "config/experiments/btc-regime-routing-s2-ewma-v1.json"
    s2_v2_contract_path = root / "config/experiments/btc-regime-routing-s2-ewma-v2.json"
    s2_stage = next(item for item in status["stages"] if item["stage_id"] == "S2")
    if s2_stage["state"] != "planned":
        validate_s2_contract(root, s2_contract_path)
        if s2_v2_contract_path.exists():
            validate_s2_v2_contract(root, s2_v2_contract_path)
    s3_stage = next(item for item in status["stages"] if item["stage_id"] == "S3")
    if s3_stage["state"] != "planned":
        validate_s3_contracts(
            root,
            root / "config/experiments/btc-regime-routing-s3-student-t-hmm-v1.json",
            root / "config/experiments/btc-regime-routing-s3-student-t-hmm-v2.json",
        )
    artifacts = status.get("context_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ProgramContextError("status registry has no context_artifacts")
    validate_artifact_lineage(root, artifacts, "context_artifacts")
    artifact_paths = {str(item["path"]) for item in artifacts}
    artifact_paths.update(
        {
            str(program_path.resolve(strict=True).relative_to(root)),
            str(status_path.resolve(strict=True).relative_to(root)),
            str(s0_contract_path.resolve(strict=True).relative_to(root)),
        }
    )
    required_paths = set(program.get("required_session_start_paths", ()))
    missing_required = sorted(required_paths - artifact_paths)
    if missing_required:
        raise ProgramContextError(f"status omits required session-start artifacts: {missing_required}")
    decision_log_path = _repo_path(root, status.get("decision_log_path"), "decision_log_path")
    decision_count = validate_decision_log(decision_log_path, tuple(graph))
    sealed = status.get("sealed_partitions")
    if not isinstance(sealed, list) or not sealed:
        raise ProgramContextError("status must declare sealed partitions")
    sealed_ids: list[str] = []
    for item in sealed:
        partition_id = str(item.get("partition_id", ""))
        if not partition_id or partition_id in sealed_ids:
            raise ProgramContextError("sealed partition IDs must be non-empty and unique")
        if item.get("access_state") != "sealed" or item.get("accessed") is not False:
            raise ProgramContextError(f"sealed partition changed state: {partition_id}")
        source_contract = _repo_path(
            root, item.get("source_contract"), f"sealed partition {partition_id} source_contract"
        )
        expected_source_digest = _digest(
            item.get("source_contract_sha256"),
            f"sealed partition {partition_id} source_contract_sha256",
        )
        if sha256_file(source_contract) != expected_source_digest:
            raise ProgramContextError(f"sealed partition source contract changed: {partition_id}")
        sealed_ids.append(partition_id)
    artifact_paths_without_implicit = {str(item["path"]) for item in artifacts}
    for stage in status["stages"]:
        if stage["state"] in TERMINAL_STAGE_STATES or stage["state"] == "active":
            undeclared = sorted(set(stage.get("artifact_paths", ())) - artifact_paths_without_implicit)
            if undeclared:
                raise ProgramContextError(
                    f"terminal stage {stage['stage_id']} has unchecksummed artifacts: {undeclared}"
                )
    if s1_stage["state"] == "passed":
        evidence_path = _repo_path(
            root,
            "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/manifest.json",
            "S1 evidence manifest",
        )
        validate_s1_evidence_manifest(root, evidence_path)
        validate_s1_determinism(
            _repo_path(
                root,
                "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/determinism-verification.json",
                "S1 determinism report",
            )
        )
    if s2_stage["state"] in TERMINAL_STAGE_STATES:
        evidence_path = _repo_path(
            root,
            "artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v2/manifest.json",
            "S2-v2 evidence manifest",
        )
        validate_s2_v2_evidence_manifest(root, evidence_path)
        validate_s2_v2_determinism(
            root,
            _repo_path(
                root,
                "artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v2/determinism-verification.json",
                "S2-v2 determinism report",
            )
        )
    if s3_stage["state"] in TERMINAL_STAGE_STATES:
        evidence_path = _repo_path(
            root,
            "artifacts/agent-level-experiment/btc-regime-routing/s3-student-t-hmm-v1/manifest.json",
            "S3 evidence manifest",
        )
        validate_s3_evidence_manifest(root, evidence_path)
        validate_s3_determinism(
            root,
            _repo_path(
                root,
                "artifacts/agent-level-experiment/btc-regime-routing/s3-student-t-hmm-v1/determinism-verification.json",
                "S3 determinism report",
            ),
        )
    for module_path in status.get("isolated_module_paths", ()):
        validate_module_isolation(_repo_path(root, module_path, "isolated_module_path"))
    return ProgramValidation(
        program_id=program_id,
        current_stage=current_stage,
        current_state=current_state,
        active_stage=active_stage,
        artifact_count=len(artifacts),
        sealed_partition_ids=tuple(sorted(sealed_ids)),
        decision_records=decision_count,
    )
