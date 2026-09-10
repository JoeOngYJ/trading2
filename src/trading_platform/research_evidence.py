"""Fail-closed point-in-time universe and research-partition evidence contracts.

The contracts in this module are deliberately offline.  They validate local evidence,
make unknown membership distinct from known ineligibility, and prevent an inspected period
from being relabelled as unseen for the same strategy family.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


UTC = timezone.utc
MEMBERSHIP_STATES = frozenset({"eligible", "ineligible", "unknown"})
PARTITION_ROLES = frozenset({"development", "evaluation", "prospective_validation", "excluded"})
ACCESS_STATES = frozenset(
    {"open", "locked", "consumed", "contaminated", "sealed_ineligible"}
)
ACCESS_PURPOSES = frozenset(
    {"analysis", "collection", "development", "reproduction", "risk_benchmark_development"}
)


class EvidenceContractError(ValueError):
    """Raised when evidence is incomplete, contradictory, contaminated, or out of scope."""


def parse_utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceContractError(f"{label} must be a non-empty UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceContractError(f"invalid {label}: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise EvidenceContractError(f"{label} must include an explicit UTC offset")
    return parsed.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise EvidenceContractError("cannot serialize a naive timestamp")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_child_path(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    boundary = parent.resolve(strict=True)
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise EvidenceContractError(f"{label} escapes frozen boundary {boundary}: {resolved}") from exc
    return resolved


def require_output_path(path: Path, parent: Path) -> Path:
    boundary = parent.resolve(strict=True)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise EvidenceContractError(
            f"output directory escapes frozen boundary {boundary}: {resolved}"
        ) from exc
    return resolved


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise EvidenceContractError(f"{label} must be a 64-character SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise EvidenceContractError(f"{label} is not hexadecimal") from exc
    return value.lower()


@dataclass(frozen=True)
class EvidenceSource:
    evidence_id: str
    source_type: str
    observed_at: datetime
    sha256: str
    local_path: Path | None
    description: str


@dataclass(frozen=True)
class MembershipInterval:
    pair: str
    start: datetime
    end_exclusive: datetime
    state: str
    evidence_ids: tuple[str, ...]
    reason: str

    def contains(self, timestamp: datetime) -> bool:
        return self.start <= timestamp < self.end_exclusive

    def overlaps(self, start: datetime, end_exclusive: datetime) -> bool:
        return self.start < end_exclusive and start < self.end_exclusive


@dataclass(frozen=True)
class UniverseAudit:
    start: datetime
    end_exclusive: datetime
    complete: bool
    inclusion_rule_point_in_time_defensible: bool
    unknown_pairs: tuple[str, ...]
    unknown_intervals: tuple[dict[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": iso_utc(self.start),
            "end_exclusive": iso_utc(self.end_exclusive),
            "complete": self.complete,
            "inclusion_rule_point_in_time_defensible": self.inclusion_rule_point_in_time_defensible,
            "unknown_pairs": list(self.unknown_pairs),
            "unknown_intervals": list(self.unknown_intervals),
        }


@dataclass(frozen=True)
class PointInTimeUniverse:
    universe_id: str
    venue: str
    quote_asset: str
    inclusion_rule_id: str
    inclusion_rule_definition: str
    inclusion_rule_point_in_time_defensible: bool
    frozen_at: datetime
    coverage_start: datetime
    coverage_end_exclusive: datetime
    candidate_pairs: tuple[str, ...]
    evidence: Mapping[str, EvidenceSource]
    intervals: Mapping[str, tuple[MembershipInterval, ...]]
    source_path: Path
    source_sha256: str

    def _checked_timestamp(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None:
            raise EvidenceContractError("membership timestamp must be timezone aware")
        checked = timestamp.astimezone(UTC)
        if not self.coverage_start <= checked < self.coverage_end_exclusive:
            raise EvidenceContractError(
                f"membership timestamp {iso_utc(checked)} is outside "
                f"[{iso_utc(self.coverage_start)}, {iso_utc(self.coverage_end_exclusive)})"
            )
        return checked

    def status_at(self, timestamp: datetime) -> dict[str, str]:
        checked = self._checked_timestamp(timestamp)
        result: dict[str, str] = {}
        for pair in self.candidate_pairs:
            matches = [interval for interval in self.intervals[pair] if interval.contains(checked)]
            if len(matches) != 1:
                raise EvidenceContractError(f"membership timeline is not singular for {pair}")
            result[pair] = matches[0].state
        return result

    def eligible_pairs(self, timestamp: datetime, require_complete: bool = True) -> tuple[str, ...]:
        statuses = self.status_at(timestamp)
        unknown = sorted(pair for pair, state in statuses.items() if state == "unknown")
        if require_complete:
            failures: list[str] = []
            if not self.inclusion_rule_point_in_time_defensible:
                failures.append(
                    f"inclusion rule {self.inclusion_rule_id} is not point-in-time defensible"
                )
            if unknown:
                failures.append("membership is unknown for: " + ", ".join(unknown))
            if failures:
                raise EvidenceContractError("; ".join(failures))
        return tuple(pair for pair in self.candidate_pairs if statuses[pair] == "eligible")

    def require_exact_eligible_set(self, timestamp: datetime, expected_pairs: Sequence[str]) -> None:
        actual = self.eligible_pairs(timestamp, require_complete=True)
        expected = tuple(expected_pairs)
        if set(actual) != set(expected):
            raise EvidenceContractError(
                f"point-in-time eligible set mismatch; expected={expected}, actual={actual}"
            )

    def audit(self, start: datetime, end_exclusive: datetime) -> UniverseAudit:
        if start.tzinfo is None or end_exclusive.tzinfo is None:
            raise EvidenceContractError("universe audit timestamps must be timezone aware")
        checked_start = start.astimezone(UTC)
        checked_end = end_exclusive.astimezone(UTC)
        if not self.coverage_start <= checked_start < checked_end <= self.coverage_end_exclusive:
            raise EvidenceContractError("universe audit range is outside declared coverage")
        unknown: list[dict[str, str]] = []
        for pair in self.candidate_pairs:
            for interval in self.intervals[pair]:
                if interval.state == "unknown" and interval.overlaps(checked_start, checked_end):
                    unknown.append(
                        {
                            "pair": pair,
                            "start": iso_utc(max(interval.start, checked_start)),
                            "end_exclusive": iso_utc(min(interval.end_exclusive, checked_end)),
                            "reason": interval.reason,
                        }
                    )
        pairs = tuple(sorted({row["pair"] for row in unknown}))
        return UniverseAudit(
            start=checked_start,
            end_exclusive=checked_end,
            complete=not unknown and self.inclusion_rule_point_in_time_defensible,
            inclusion_rule_point_in_time_defensible=self.inclusion_rule_point_in_time_defensible,
            unknown_pairs=pairs,
            unknown_intervals=tuple(unknown),
        )


def _load_evidence_sources(
    raw_sources: Sequence[Mapping[str, Any]],
    config_path: Path,
    verify_local_evidence: bool,
) -> dict[str, EvidenceSource]:
    sources: dict[str, EvidenceSource] = {}
    for raw in raw_sources:
        evidence_id = str(raw.get("evidence_id", ""))
        if not evidence_id or evidence_id in sources:
            raise EvidenceContractError("evidence IDs must be non-empty and unique")
        local_raw = raw.get("local_path")
        local_path: Path | None = None
        if local_raw is not None:
            local_path = (config_path.parent / str(local_raw)).resolve(strict=verify_local_evidence)
        source = EvidenceSource(
            evidence_id=evidence_id,
            source_type=str(raw.get("source_type", "")),
            observed_at=parse_utc(raw.get("observed_at"), f"evidence {evidence_id} observed_at"),
            sha256=_sha256(raw.get("sha256"), f"evidence {evidence_id} sha256"),
            local_path=local_path,
            description=str(raw.get("description", "")),
        )
        if not source.source_type or not source.description:
            raise EvidenceContractError(f"evidence {evidence_id} lacks source_type or description")
        if source.local_path is not None and verify_local_evidence:
            actual = sha256_file(source.local_path)
            if actual != source.sha256:
                raise EvidenceContractError(
                    f"evidence checksum mismatch for {evidence_id}: expected {source.sha256}, got {actual}"
                )
        sources[evidence_id] = source
    return sources


def load_point_in_time_universe(
    path: Path,
    verify_local_evidence: bool = True,
) -> PointInTimeUniverse:
    config_path = path.resolve(strict=True)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "research-universe-timeline-v1":
        raise EvidenceContractError("unsupported universe timeline schema")
    frozen_at = parse_utc(payload.get("frozen_at"), "universe frozen_at")
    coverage = payload.get("coverage", {})
    coverage_start = parse_utc(coverage.get("start"), "universe coverage start")
    coverage_end = parse_utc(coverage.get("end_exclusive"), "universe coverage end_exclusive")
    if coverage_start >= coverage_end:
        raise EvidenceContractError("universe coverage is empty or reversed")
    pairs = tuple(str(pair) for pair in payload.get("candidate_pairs", []))
    if not pairs or len(set(pairs)) != len(pairs):
        raise EvidenceContractError("candidate pairs must be non-empty and unique")
    evidence = _load_evidence_sources(
        payload.get("evidence", []), config_path, verify_local_evidence
    )
    universe_id = str(payload.get("universe_id", ""))
    venue = str(payload.get("venue", ""))
    quote_asset = str(payload.get("quote_asset", ""))
    inclusion_rule = payload.get("inclusion_rule", {})
    inclusion_rule_id = str(inclusion_rule.get("rule_id", ""))
    inclusion_rule_definition = str(inclusion_rule.get("definition", ""))
    rule_defensible = inclusion_rule.get("point_in_time_defensible")
    if not universe_id or not venue or not quote_asset:
        raise EvidenceContractError("universe_id, venue, and quote_asset are required")
    if not inclusion_rule_id or not inclusion_rule_definition or not isinstance(rule_defensible, bool):
        raise EvidenceContractError(
            "inclusion_rule requires rule_id, definition, and point_in_time_defensible"
        )
    future_evidence = sorted(
        source.evidence_id for source in evidence.values() if source.observed_at > frozen_at
    )
    if future_evidence:
        raise EvidenceContractError(
            f"universe evidence was observed after the frozen_at boundary: {future_evidence}"
        )

    grouped: dict[str, list[MembershipInterval]] = {pair: [] for pair in pairs}
    for raw in payload.get("intervals", []):
        pair = str(raw.get("pair", ""))
        if pair not in grouped:
            raise EvidenceContractError(f"membership interval has undeclared pair: {pair}")
        state = str(raw.get("state", ""))
        if state not in MEMBERSHIP_STATES:
            raise EvidenceContractError(f"invalid membership state for {pair}: {state}")
        start = parse_utc(raw.get("start"), f"{pair} interval start")
        end = parse_utc(raw.get("end_exclusive"), f"{pair} interval end_exclusive")
        if start >= end:
            raise EvidenceContractError(f"empty or reversed membership interval for {pair}")
        evidence_ids = tuple(str(value) for value in raw.get("evidence_ids", []))
        missing_evidence = sorted(set(evidence_ids) - set(evidence))
        if missing_evidence:
            raise EvidenceContractError(
                f"membership interval for {pair} references missing evidence: {missing_evidence}"
            )
        reason = str(raw.get("reason", ""))
        if state in {"eligible", "ineligible"} and not evidence_ids:
            raise EvidenceContractError(f"known membership state for {pair} lacks evidence")
        if state == "unknown" and not reason:
            raise EvidenceContractError(f"unknown membership state for {pair} lacks a reason")
        grouped[pair].append(
            MembershipInterval(pair, start, end, state, evidence_ids, reason)
        )

    validated: dict[str, tuple[MembershipInterval, ...]] = {}
    for pair in pairs:
        intervals = sorted(grouped[pair], key=lambda item: item.start)
        if not intervals:
            raise EvidenceContractError(f"membership timeline is missing for {pair}")
        if intervals[0].start != coverage_start:
            raise EvidenceContractError(f"membership coverage for {pair} does not start at boundary")
        previous_end = coverage_start
        for interval in intervals:
            if interval.start != previous_end:
                relationship = "overlap" if interval.start < previous_end else "gap"
                raise EvidenceContractError(f"membership {relationship} for {pair} at {iso_utc(previous_end)}")
            if interval.start < coverage_start or interval.end_exclusive > coverage_end:
                raise EvidenceContractError(f"membership interval for {pair} escapes coverage")
            previous_end = interval.end_exclusive
        if previous_end != coverage_end:
            raise EvidenceContractError(f"membership coverage for {pair} does not end at boundary")
        validated[pair] = tuple(intervals)

    return PointInTimeUniverse(
        universe_id=universe_id,
        venue=venue,
        quote_asset=quote_asset,
        inclusion_rule_id=inclusion_rule_id,
        inclusion_rule_definition=inclusion_rule_definition,
        inclusion_rule_point_in_time_defensible=rule_defensible,
        frozen_at=frozen_at,
        coverage_start=coverage_start,
        coverage_end_exclusive=coverage_end,
        candidate_pairs=pairs,
        evidence=evidence,
        intervals=validated,
        source_path=config_path,
        source_sha256=sha256_file(config_path),
    )


@dataclass(frozen=True)
class PartitionUnlock:
    unlocked_at: datetime
    prior_locked_registry_sha256: str
    frozen_experiment_sha256: str
    observed_events: int
    one_time_analysis: bool


@dataclass(frozen=True)
class ResearchPartition:
    partition_id: str
    role: str
    start: datetime
    end_exclusive: datetime
    access_state: str
    allowed_purposes: tuple[str, ...]
    minimum_events: int | None
    locked_at: datetime | None
    unlock: PartitionUnlock | None
    notes: str

    def overlaps(self, start: datetime, end_exclusive: datetime) -> bool:
        return self.start < end_exclusive and start < self.end_exclusive


@dataclass(frozen=True)
class InspectionRecord:
    inspection_id: str
    strategy_family: str
    start: datetime
    end_exclusive: datetime
    recorded_at: datetime
    information_scope: str
    notes: str

    def overlaps(self, partition: ResearchPartition) -> bool:
        return self.start < partition.end_exclusive and partition.start < self.end_exclusive


@dataclass(frozen=True)
class PartitionAudit:
    partition_id: str
    genuinely_unseen: bool
    reasons: tuple[str, ...]
    overlapping_inspection_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "partition_id": self.partition_id,
            "genuinely_unseen": self.genuinely_unseen,
            "reasons": list(self.reasons),
            "overlapping_inspection_ids": list(self.overlapping_inspection_ids),
        }


@dataclass(frozen=True)
class ResearchPartitionRegistry:
    registry_id: str
    strategy_family: str
    frozen_at: datetime
    label_horizon_hours: int
    minimum_embargo_hours: int
    partitions: tuple[ResearchPartition, ...]
    inspections: tuple[InspectionRecord, ...]
    source_path: Path
    source_sha256: str

    def partition(self, partition_id: str) -> ResearchPartition:
        try:
            return next(item for item in self.partitions if item.partition_id == partition_id)
        except StopIteration as exc:
            raise EvidenceContractError(f"unknown research partition: {partition_id}") from exc

    def audit_unseen(self, partition_id: str) -> PartitionAudit:
        partition = self.partition(partition_id)
        reasons: list[str] = []
        if partition.role not in {"evaluation", "prospective_validation"}:
            reasons.append(f"role_{partition.role}_is_not_unseen_evaluation")
        if partition.access_state != "locked":
            reasons.append(f"access_state_{partition.access_state}_is_not_locked")
        overlaps = tuple(
            inspection.inspection_id
            for inspection in self.inspections
            if inspection.strategy_family in {self.strategy_family, "*"} and inspection.overlaps(partition)
        )
        if overlaps:
            reasons.append("overlaps_prior_strategy_family_inspection")
        return PartitionAudit(
            partition_id=partition_id,
            genuinely_unseen=not reasons,
            reasons=tuple(reasons),
            overlapping_inspection_ids=overlaps,
        )

    def clean_unseen_partition_ids(self) -> tuple[str, ...]:
        return tuple(
            partition.partition_id
            for partition in self.partitions
            if self.audit_unseen(partition.partition_id).genuinely_unseen
        )

    def require_access(
        self,
        partition_id: str,
        purpose: str,
        as_of: datetime,
        prior_locked_registry_path: Path | None = None,
        frozen_experiment_path: Path | None = None,
    ) -> None:
        partition = self.partition(partition_id)
        if purpose not in ACCESS_PURPOSES:
            raise EvidenceContractError(f"unknown research access purpose: {purpose}")
        if purpose not in partition.allowed_purposes:
            raise EvidenceContractError(
                f"purpose {purpose} is not allowed for partition {partition_id}"
            )
        if as_of.tzinfo is None:
            raise EvidenceContractError("research access time must be timezone aware")
        checked_as_of = as_of.astimezone(UTC)
        if purpose == "collection":
            if partition.role != "prospective_validation" or partition.access_state != "locked":
                raise EvidenceContractError("locked collection is allowed only for prospective validation")
            if not partition.start <= checked_as_of < partition.end_exclusive:
                raise EvidenceContractError("prospective collection is outside its frozen interval")
            return
        if purpose == "analysis":
            if partition.access_state != "open":
                raise EvidenceContractError(
                    f"analysis requires an explicitly open partition, got {partition.access_state}"
                )
            audit = self.audit_unseen(partition_id)
            if audit.overlapping_inspection_ids:
                raise EvidenceContractError("analysis partition is contaminated by prior inspection")
            self.require_unlock_lineage(
                partition_id,
                prior_locked_registry_path,
                frozen_experiment_path,
            )
        if partition.access_state in {"contaminated", "sealed_ineligible"}:
            raise EvidenceContractError(
                f"{partition.access_state} partition cannot be used as research evidence"
            )

    def require_unlock_lineage(
        self,
        partition_id: str,
        prior_locked_registry_path: Path | None,
        frozen_experiment_path: Path | None,
    ) -> None:
        partition = self.partition(partition_id)
        unlock = partition.unlock
        if unlock is None:
            raise EvidenceContractError(f"partition {partition_id} has no unlock lineage")
        if prior_locked_registry_path is None or frozen_experiment_path is None:
            raise EvidenceContractError(
                "analysis requires the prior locked registry and frozen experiment files"
            )
        prior_path = prior_locked_registry_path.resolve(strict=True)
        experiment_path = frozen_experiment_path.resolve(strict=True)
        if sha256_file(prior_path) != unlock.prior_locked_registry_sha256:
            raise EvidenceContractError("prior locked registry checksum does not match unlock lineage")
        if sha256_file(experiment_path) != unlock.frozen_experiment_sha256:
            raise EvidenceContractError("frozen experiment checksum does not match unlock lineage")
        prior = load_research_partition_registry(prior_path)
        if prior.strategy_family != self.strategy_family:
            raise EvidenceContractError("prior locked registry strategy family differs")
        prior_partition = prior.partition(partition_id)
        if prior_partition.access_state != "locked" or prior_partition.unlock is not None:
            raise EvidenceContractError("prior registry does not contain the locked partition")
        if not prior.audit_unseen(partition_id).genuinely_unseen:
            raise EvidenceContractError("prior registry partition was not genuinely unseen")
        immutable_fields = (
            "role",
            "start",
            "end_exclusive",
            "minimum_events",
            "locked_at",
        )
        changed = [
            field
            for field in immutable_fields
            if getattr(prior_partition, field) != getattr(partition, field)
        ]
        if changed:
            raise EvidenceContractError(
                f"opened partition changed frozen fields from locked registry: {changed}"
            )

    def summary(self) -> dict[str, Any]:
        audits = [self.audit_unseen(partition.partition_id).as_dict() for partition in self.partitions]
        return {
            "registry_id": self.registry_id,
            "strategy_family": self.strategy_family,
            "frozen_at": iso_utc(self.frozen_at),
            "label_horizon_hours": self.label_horizon_hours,
            "minimum_embargo_hours": self.minimum_embargo_hours,
            "clean_unseen_partition_ids": list(self.clean_unseen_partition_ids()),
            "partitions": [
                {
                    "partition_id": partition.partition_id,
                    "role": partition.role,
                    "start": iso_utc(partition.start),
                    "end_exclusive": iso_utc(partition.end_exclusive),
                    "access_state": partition.access_state,
                    "allowed_purposes": list(partition.allowed_purposes),
                    "minimum_events": partition.minimum_events,
                    "locked_at": iso_utc(partition.locked_at) if partition.locked_at else None,
                    "unlock": (
                        {
                            "unlocked_at": iso_utc(partition.unlock.unlocked_at),
                            "prior_locked_registry_sha256": (
                                partition.unlock.prior_locked_registry_sha256
                            ),
                            "frozen_experiment_sha256": partition.unlock.frozen_experiment_sha256,
                            "observed_events": partition.unlock.observed_events,
                            "one_time_analysis": partition.unlock.one_time_analysis,
                        }
                        if partition.unlock
                        else None
                    ),
                }
                for partition in self.partitions
            ],
            "unseen_audits": audits,
        }


def load_research_partition_registry(path: Path) -> ResearchPartitionRegistry:
    config_path = path.resolve(strict=True)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "research-evidence-boundaries-v1":
        raise EvidenceContractError("unsupported research partition schema")
    frozen_at = parse_utc(payload.get("frozen_at"), "partition registry frozen_at")
    registry_id = str(payload.get("registry_id", ""))
    strategy_family = str(payload.get("strategy_family", ""))
    if not registry_id or not strategy_family:
        raise EvidenceContractError("registry_id and strategy_family are required")
    horizon = int(payload.get("label_horizon_hours", 0))
    embargo = int(payload.get("minimum_embargo_hours", 0))
    if horizon <= 0 or embargo < horizon:
        raise EvidenceContractError("embargo must be at least the positive label horizon")

    partitions: list[ResearchPartition] = []
    seen_ids: set[str] = set()
    for raw in payload.get("partitions", []):
        partition_id = str(raw.get("partition_id", ""))
        if not partition_id or partition_id in seen_ids:
            raise EvidenceContractError("partition IDs must be non-empty and unique")
        seen_ids.add(partition_id)
        role = str(raw.get("role", ""))
        state = str(raw.get("access_state", ""))
        purposes = tuple(str(value) for value in raw.get("allowed_purposes", []))
        if role not in PARTITION_ROLES or state not in ACCESS_STATES:
            raise EvidenceContractError(f"invalid role or access state for {partition_id}")
        if len(set(purposes)) != len(purposes) or not set(purposes) <= ACCESS_PURPOSES:
            raise EvidenceContractError(f"invalid allowed purposes for {partition_id}")
        if not purposes and not (
            role == "excluded" and state in {"contaminated", "sealed_ineligible"}
        ):
            raise EvidenceContractError(f"non-excluded partition {partition_id} needs an allowed purpose")
        if role == "excluded" and state not in {"contaminated", "sealed_ineligible"}:
            raise EvidenceContractError(
                f"excluded partition {partition_id} must be contaminated or sealed_ineligible"
            )
        start = parse_utc(raw.get("start"), f"partition {partition_id} start")
        end = parse_utc(raw.get("end_exclusive"), f"partition {partition_id} end_exclusive")
        if start >= end:
            raise EvidenceContractError(f"partition {partition_id} is empty or reversed")
        minimum_events_raw = raw.get("minimum_events")
        minimum_events = int(minimum_events_raw) if minimum_events_raw is not None else None
        if minimum_events is not None and minimum_events <= 0:
            raise EvidenceContractError(f"partition {partition_id} minimum_events must be positive")
        if role in {"evaluation", "prospective_validation"} and minimum_events is None:
            raise EvidenceContractError(f"evaluation partition {partition_id} lacks minimum_events")
        locked_at_raw = raw.get("locked_at")
        locked_at = (
            parse_utc(locked_at_raw, f"partition {partition_id} locked_at")
            if locked_at_raw is not None
            else None
        )
        unlock_raw = raw.get("unlock")
        unlock: PartitionUnlock | None = None
        if unlock_raw is not None:
            unlock = PartitionUnlock(
                unlocked_at=parse_utc(
                    unlock_raw.get("unlocked_at"), f"partition {partition_id} unlocked_at"
                ),
                prior_locked_registry_sha256=_sha256(
                    unlock_raw.get("prior_locked_registry_sha256"),
                    f"partition {partition_id} prior_locked_registry_sha256",
                ),
                frozen_experiment_sha256=_sha256(
                    unlock_raw.get("frozen_experiment_sha256"),
                    f"partition {partition_id} frozen_experiment_sha256",
                ),
                observed_events=int(unlock_raw.get("observed_events", 0)),
                one_time_analysis=bool(unlock_raw.get("one_time_analysis", False)),
            )
        if role in {"evaluation", "prospective_validation"}:
            if locked_at is None or locked_at > frozen_at:
                raise EvidenceContractError(
                    f"evaluation partition {partition_id} needs locked_at no later than frozen_at"
                )
            if role == "prospective_validation" and locked_at > start:
                raise EvidenceContractError(
                    f"prospective partition {partition_id} was not locked before collection"
                )
            if state == "locked" and unlock is not None:
                raise EvidenceContractError(f"locked partition {partition_id} cannot contain unlock data")
            if state == "open":
                if unlock is None:
                    raise EvidenceContractError(
                        f"open evaluation partition {partition_id} lacks unlock lineage"
                    )
                if unlock.unlocked_at < end or unlock.unlocked_at > frozen_at:
                    raise EvidenceContractError(
                        f"partition {partition_id} unlock is before its end or after frozen_at"
                    )
                if unlock.observed_events < minimum_events:
                    raise EvidenceContractError(
                        f"partition {partition_id} unlock lacks its minimum event count"
                    )
                if not unlock.one_time_analysis:
                    raise EvidenceContractError(
                        f"partition {partition_id} unlock must be one-time analysis"
                    )
        elif locked_at is not None or unlock is not None:
            raise EvidenceContractError(
                f"non-evaluation partition {partition_id} cannot contain lock/unlock data"
            )
        partitions.append(
            ResearchPartition(
                partition_id=partition_id,
                role=role,
                start=start,
                end_exclusive=end,
                access_state=state,
                allowed_purposes=purposes,
                minimum_events=minimum_events,
                locked_at=locked_at,
                unlock=unlock,
                notes=str(raw.get("notes", "")),
            )
        )
    if not partitions:
        raise EvidenceContractError("partition registry is empty")
    partitions.sort(key=lambda item: item.start)
    for previous, current in zip(partitions, partitions[1:]):
        if current.start < previous.end_exclusive:
            raise EvidenceContractError(
                f"research partitions overlap: {previous.partition_id}, {current.partition_id}"
            )
        if current.role in {"evaluation", "prospective_validation"}:
            gap_hours = (current.start - previous.end_exclusive).total_seconds() / 3600
            if gap_hours < embargo:
                raise EvidenceContractError(
                    f"partition {current.partition_id} lacks the {embargo}h embargo"
                )

    inspections: list[InspectionRecord] = []
    seen_inspections: set[str] = set()
    for raw in payload.get("inspections", []):
        inspection_id = str(raw.get("inspection_id", ""))
        if not inspection_id or inspection_id in seen_inspections:
            raise EvidenceContractError("inspection IDs must be non-empty and unique")
        seen_inspections.add(inspection_id)
        start = parse_utc(raw.get("start"), f"inspection {inspection_id} start")
        end = parse_utc(raw.get("end_exclusive"), f"inspection {inspection_id} end_exclusive")
        if start >= end:
            raise EvidenceContractError(f"inspection {inspection_id} is empty or reversed")
        scope = str(raw.get("information_scope", ""))
        if not scope:
            raise EvidenceContractError(f"inspection {inspection_id} lacks information_scope")
        inspections.append(
            InspectionRecord(
                inspection_id=inspection_id,
                strategy_family=str(raw.get("strategy_family", "")),
                start=start,
                end_exclusive=end,
                recorded_at=parse_utc(
                    raw.get("recorded_at"), f"inspection {inspection_id} recorded_at"
                ),
                information_scope=scope,
                notes=str(raw.get("notes", "")),
            )
        )
        if not inspections[-1].strategy_family:
            raise EvidenceContractError(f"inspection {inspection_id} lacks strategy_family")
        if inspections[-1].recorded_at > frozen_at:
            raise EvidenceContractError(
                f"inspection {inspection_id} was recorded after the registry frozen_at boundary"
            )

    return ResearchPartitionRegistry(
        registry_id=registry_id,
        strategy_family=strategy_family,
        frozen_at=frozen_at,
        label_horizon_hours=horizon,
        minimum_embargo_hours=embargo,
        partitions=tuple(partitions),
        inspections=tuple(inspections),
        source_path=config_path,
        source_sha256=sha256_file(config_path),
    )
