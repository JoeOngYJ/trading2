from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .capture import canonical_digest
from .contracts import (
    CaptureSession,
    CaptureSessionStatus,
    ExecutionMarketSnapshot,
    InstrumentIdentity,
    PortfolioRating,
    SemanticInvocationRecord,
    SourceCallOutcome,
    VendorAttemptRecord,
)
from .source_allowlist import (
    ALLOWED_INGRESS,
    CRYPTO_INSTRUMENTS,
    CryptoCaptureScope,
    IngressPolicyError,
    normalize_vendor_plan,
    validate_completed_fallbacks,
    validate_crypto_scope,
)


POLICY_VERSION = "source-policy/1.0.0"
ALL_RATINGS = tuple(rating.value for rating in PortfolioRating)
REQUIRED_METHODS = (
    "resolve_instrument_identity",
    "get_stock_data",
    "get_verified_market_snapshot",
)
DEGRADED_METHODS = (
    "get_indicators",
    "get_news",
    "get_global_news",
    "fetch_stocktwits_messages",
    "fetch_reddit_posts",
)
OPTIONAL_METHODS = ("get_macro_indicators", "get_prediction_markets")
EXPECTED_POLICY_RULE_IDS = (
    "contract.identity",
    "contract.capture_state",
    "market.execution_snapshot",
    "contract.invocation_ledger",
    "contract.method_allowlist",
    "temporal.invocations",
    "contract.research_symbols",
    "artifact.integrity",
    "contract.vendor_fallbacks",
    "source.unsafe_outcomes",
    *(f"source.required.{method}" for method in REQUIRED_METHODS),
    *(f"source.degraded.{method}" for method in DEGRADED_METHODS),
    *(f"source.optional.{method}" for method in OPTIONAL_METHODS),
)


class PolicyVerdict(str, Enum):
    PASS = "pass"
    HOLD_ONLY = "hold_only"
    REJECT = "reject"


class RuleOutcome(str, Enum):
    PASS = "pass"
    WARN = "warn"
    DEGRADE = "degrade"
    FAIL = "fail"


class SourcePolicyConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["source-policy/1.0.0"] = POLICY_VERSION
    expected_timeframe: str = Field(default="5m", pattern=r"^[1-9][0-9]*[mhdw]$")
    expected_candle_type: Literal["spot"] = "spot"
    allowed_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    max_snapshot_age_seconds: int = Field(default=600, ge=60, le=86400)
    max_abs_clock_offset_ms: int = Field(default=2000, ge=0, le=60000)
    max_research_market_age_seconds: int = Field(default=259200, ge=3600, le=604800)
    max_enrichment_age_seconds: int = Field(default=604800, ge=3600, le=2592000)


class SourcePolicyInput(BaseModel):
    """Fully materialized, artifact-verified input to the pure evaluator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session: CaptureSession
    instrument: InstrumentIdentity
    execution_snapshot: ExecutionMarketSnapshot
    vendor_plan: dict[str, tuple[str, ...]]
    invocations: tuple[SemanticInvocationRecord, ...]
    vendor_attempts: tuple[VendorAttemptRecord, ...]
    verified_artifact_digests: tuple[str, ...]
    analysis_started_at: datetime
    collection_cutoff_at: datetime

    @field_validator("analysis_started_at", "collection_cutoff_at", mode="after")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("policy timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("verified_artifact_digests", mode="after")
    @classmethod
    def canonical_verified_digests(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for digest in values:
            if not digest.startswith("sha256:") or len(digest) != 71:
                raise ValueError("verified artifact digest is malformed")
        return tuple(sorted(set(values)))

    @model_validator(mode="after")
    def validate_time_order(self) -> "SourcePolicyInput":
        if self.collection_cutoff_at < self.analysis_started_at:
            raise ValueError("collection cutoff precedes analysis start")
        if self.session.collection_closed_at != self.collection_cutoff_at:
            raise ValueError("policy cutoff does not match the frozen capture cutoff")
        return self


class SourcePolicyRuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    outcome: RuleOutcome
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    evidence_refs: tuple[str, ...] = ()


class SourcePolicyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["source-policy/1.0.0"] = POLICY_VERSION
    policy_configuration_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    session_id: str
    input_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    verdict: PolicyVerdict
    permitted_ratings: tuple[str, ...]
    data_as_of: datetime
    quality_flags: tuple[str, ...]
    rules: tuple[SourcePolicyRuleResult, ...]
    result_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_result_contract(self) -> "SourcePolicyResult":
        if self.data_as_of.tzinfo is None or self.data_as_of.utcoffset() is None:
            raise ValueError("data_as_of must be timezone-aware")
        expected = {
            PolicyVerdict.PASS: ALL_RATINGS,
            PolicyVerdict.HOLD_ONLY: (PortfolioRating.HOLD.value,),
            PolicyVerdict.REJECT: (),
        }[self.verdict]
        if self.permitted_ratings != expected:
            raise ValueError("permitted ratings do not match policy verdict")
        digest_data = self.model_dump(mode="json", exclude={"result_digest"})
        if canonical_digest(digest_data) != self.result_digest:
            raise ValueError("source policy result digest mismatch")
        return self


def _rule(
    rule_id: str,
    outcome: RuleOutcome,
    code: str,
    refs: tuple[str, ...] = (),
) -> SourcePolicyRuleResult:
    return SourcePolicyRuleResult(
        rule_id=rule_id, outcome=outcome, code=code,
        evidence_refs=tuple(sorted(refs)),
    )


def _method_refs(invocations: list[SemanticInvocationRecord]) -> tuple[str, ...]:
    return tuple(str(invocation.invocation_id) for invocation in invocations)


def _expected_resolved_symbol(method: str, research_symbol: str, base: str) -> str | None:
    if method in ("get_global_news", "get_macro_indicators", "get_prediction_markets"):
        return None
    if method == "fetch_stocktwits_messages":
        return f"{base}.X"
    if method == "fetch_reddit_posts":
        return base
    return research_symbol


def evaluate_source_policy(
    policy_input: SourcePolicyInput,
    configuration: SourcePolicyConfiguration | None = None,
) -> SourcePolicyResult:
    """Evaluate all rules without I/O, wall-clock reads, or LLM-derived judgments."""
    config = configuration or SourcePolicyConfiguration()
    rules: list[SourcePolicyRuleResult] = []
    session = policy_input.session
    instrument = policy_input.instrument
    snapshot = policy_input.execution_snapshot
    invocations = sorted(policy_input.invocations, key=lambda item: item.ordinal)
    verified = set(policy_input.verified_artifact_digests)
    skew_seconds = config.allowed_clock_skew_seconds

    identity_refs = (instrument.instrument_id, str(snapshot.snapshot_id))
    try:
        normalized_plan = normalize_vendor_plan(policy_input.vendor_plan)
        validate_crypto_scope(CryptoCaptureScope(
            instrument_id=instrument.instrument_id,
            research_symbol=instrument.research_symbol,
            execution_exchange=instrument.execution_exchange,
            execution_pair=instrument.execution_pair,
            market_type=instrument.market_type,
            enabled=instrument.enabled,
            vendor_plan=normalized_plan,
        ))
        identity_ok = (
            session.instrument_id == instrument.instrument_id == snapshot.instrument_id
            and session.execution_snapshot_id == snapshot.snapshot_id
            and snapshot.exchange == instrument.execution_exchange
            and snapshot.pair == instrument.execution_pair
            and snapshot.market_type == instrument.market_type
            and instrument.base == CRYPTO_INSTRUMENTS[instrument.instrument_id]["base_asset"]
            and instrument.quote == "USDT"
            and instrument.research_quote == "USD"
        )
        if not identity_ok:
            raise IngressPolicyError("policy.identity_link_mismatch")
        rules.append(_rule("contract.identity", RuleOutcome.PASS, "identity.exact", identity_refs))
    except IngressPolicyError as error:
        normalized_plan = {}
        rules.append(_rule("contract.identity", RuleOutcome.FAIL, error.code, identity_refs))

    session_ok = (
        session.status == CaptureSessionStatus.EVALUATING
        and session.mode == "live_capture"
        and policy_input.analysis_started_at <= session.started_at
        and policy_input.collection_cutoff_at <= session.deadline_at
    )
    rules.append(_rule(
        "contract.capture_state",
        RuleOutcome.PASS if session_ok else RuleOutcome.FAIL,
        "capture.evaluating" if session_ok else "capture.state_or_window_invalid",
        (str(session.session_id), str(session.job_id)),
    ))

    snapshot_age = (
        policy_input.analysis_started_at - snapshot.candle_close_at
    ).total_seconds()
    snapshot_ok = (
        snapshot.is_closed
        and not snapshot.has_gap
        and snapshot.timeframe == config.expected_timeframe
        and snapshot.candle_type == config.expected_candle_type
        and snapshot.candle_close_at <= policy_input.analysis_started_at
        and snapshot.candle_close_at <= snapshot.retrieved_at
        and snapshot.retrieved_at <= policy_input.analysis_started_at
        and 0 <= snapshot_age <= config.max_snapshot_age_seconds
        and abs(snapshot.clock_offset_ms) <= config.max_abs_clock_offset_ms
    )
    rules.append(_rule(
        "market.execution_snapshot",
        RuleOutcome.PASS if snapshot_ok else RuleOutcome.FAIL,
        "execution_snapshot.valid" if snapshot_ok else "execution_snapshot.invalid",
        (str(snapshot.snapshot_id),),
    ))

    expected_ordinals = list(range(len(invocations)))
    ordinals_ok = [item.ordinal for item in invocations] == expected_ordinals
    session_links_ok = all(item.session_id == session.session_id for item in invocations)
    rules.append(_rule(
        "contract.invocation_ledger",
        RuleOutcome.PASS if ordinals_ok and session_links_ok else RuleOutcome.FAIL,
        "invocation_ledger.contiguous" if ordinals_ok and session_links_ok
        else "invocation_ledger.identity_or_order_invalid",
        _method_refs(invocations),
    ))

    unknown = [item for item in invocations if item.method not in ALLOWED_INGRESS]
    malformed_ingress = []
    for item in invocations:
        rule = ALLOWED_INGRESS.get(item.method)
        if rule is not None and (
            item.category != rule.category
            or item.consumer != rule.consumer
            or item.policy_subject != item.method
            or item.arguments_hash != canonical_digest(item.sanitized_arguments)
        ):
            malformed_ingress.append(item)
    invalid_ingress = unknown + malformed_ingress
    rules.append(_rule(
        "contract.method_allowlist",
        RuleOutcome.PASS if not invalid_ingress else RuleOutcome.FAIL,
        "ingress.methods_allowed" if not invalid_ingress
        else "ingress.method_identity_invalid",
        _method_refs(invalid_ingress),
    ))

    temporal_failures: list[SemanticInvocationRecord] = []
    symbol_failures: list[SemanticInvocationRecord] = []
    instrument_spec = CRYPTO_INSTRUMENTS.get(instrument.instrument_id, {})
    base = str(instrument_spec.get("base_asset", instrument.base))
    for invocation in invocations:
        metadata = invocation.typed_metadata
        source_times = tuple(filter(None, (
            metadata.latest_item_at,
            metadata.latest_bar_at,
            metadata.latest_bar_close_at,
            metadata.information_cutoff_at,
        )))
        temporal_ok = (
            invocation.started_at >= session.started_at
            and invocation.first_seen_at <= policy_input.collection_cutoff_at
            and invocation.completed_at <= policy_input.collection_cutoff_at
            and all(
                (source_time - invocation.first_seen_at).total_seconds() <= skew_seconds
                for source_time in source_times
            )
        )
        if not temporal_ok:
            temporal_failures.append(invocation)
        rule = ALLOWED_INGRESS.get(invocation.method)
        if rule and rule.symbol_argument:
            expected_resolved = _expected_resolved_symbol(
                invocation.method, instrument.research_symbol, base
            )
            if (
                metadata.requested_symbol != instrument.research_symbol
                or metadata.resolved_symbol != expected_resolved
            ):
                symbol_failures.append(invocation)

    rules.append(_rule(
        "temporal.invocations",
        RuleOutcome.PASS if not temporal_failures else RuleOutcome.FAIL,
        "temporal.within_capture_window" if not temporal_failures else "temporal.future_or_late_input",
        _method_refs(temporal_failures),
    ))
    rules.append(_rule(
        "contract.research_symbols",
        RuleOutcome.PASS if not symbol_failures else RuleOutcome.FAIL,
        "symbols.exact" if not symbol_failures else "symbols.requested_or_resolved_mismatch",
        _method_refs(symbol_failures),
    ))

    required_digests = {snapshot.raw_artifact.digest}
    required_digests.update(
        digest for invocation in invocations
        if (digest := invocation.normalized_artifact_digest) is not None
    )
    required_digests.update(
        digest for attempt in policy_input.vendor_attempts
        if (digest := attempt.normalized_artifact_digest) is not None
    )
    required_digests.update(
        digest for attempt in policy_input.vendor_attempts
        if (digest := attempt.raw_artifact_digest) is not None
    )
    missing_digests = tuple(sorted(required_digests - verified))
    rules.append(_rule(
        "artifact.integrity",
        RuleOutcome.PASS if not missing_digests else RuleOutcome.FAIL,
        "artifacts.verified" if not missing_digests else "artifacts.unverified_or_missing",
        missing_digests,
    ))

    attempts_by_invocation: dict[str, list[VendorAttemptRecord]] = {}
    orphan_attempts: list[VendorAttemptRecord] = []
    invocation_ids = {str(item.invocation_id) for item in invocations}
    for attempt in policy_input.vendor_attempts:
        key = str(attempt.invocation_id)
        if attempt.session_id != session.session_id or key not in invocation_ids:
            orphan_attempts.append(attempt)
        attempts_by_invocation.setdefault(key, []).append(attempt)
    fallback_failures: list[str] = [str(item.attempt_id) for item in orphan_attempts]
    for invocation in invocations:
        attempts = sorted(
            attempts_by_invocation.get(str(invocation.invocation_id), []),
            key=lambda item: item.fallback_ordinal,
        )
        try:
            if any(
                attempt.started_at < invocation.started_at
                or attempt.completed_at > invocation.completed_at
                for attempt in attempts
            ):
                raise IngressPolicyError("ingress.fallback_time_window_invalid")
            if [item.fallback_ordinal for item in attempts] != list(range(len(attempts))):
                raise IngressPolicyError("ingress.fallback_ordinals_invalid")
            expected_chain = normalized_plan.get(invocation.method, ())
            validate_completed_fallbacks(
                expected_chain,
                [(item.vendor, item.outcome.value) for item in attempts],
                invocation.outcome.value,
            )
        except IngressPolicyError:
            fallback_failures.append(str(invocation.invocation_id))
    rules.append(_rule(
        "contract.vendor_fallbacks",
        RuleOutcome.PASS if not fallback_failures else RuleOutcome.FAIL,
        "fallbacks.valid" if not fallback_failures else "fallbacks.invalid",
        tuple(fallback_failures),
    ))

    invocations_by_method = {
        method: [item for item in invocations if item.method == method]
        for method in ALLOWED_INGRESS
    }
    unsafe_outcomes = {
        SourceCallOutcome.INVALID_RESPONSE,
        SourceCallOutcome.POLICY_REJECTED,
    }
    unsafe = [item for item in invocations if item.outcome in unsafe_outcomes]
    rules.append(_rule(
        "source.unsafe_outcomes",
        RuleOutcome.PASS if not unsafe else RuleOutcome.FAIL,
        "source.no_unsafe_outcomes" if not unsafe else "source.unsafe_outcome",
        _method_refs(unsafe),
    ))

    for method in REQUIRED_METHODS:
        items = invocations_by_method.get(method, [])
        method_ok = bool(items) and all(
            item.outcome == SourceCallOutcome.AVAILABLE
            and item.typed_metadata.timestamps_complete
            for item in items
        )
        if method in ("get_stock_data", "get_verified_market_snapshot"):
            method_ok = method_ok and all(
                item.typed_metadata.market_bar_closed is True
                and item.typed_metadata.latest_bar_close_at is not None
                and 0 <= (
                    policy_input.analysis_started_at
                    - item.typed_metadata.latest_bar_close_at
                ).total_seconds() <= config.max_research_market_age_seconds
                for item in items
            )
        rules.append(_rule(
            f"source.required.{method}",
            RuleOutcome.PASS if method_ok else RuleOutcome.FAIL,
            f"{method}.available" if method_ok else f"{method}.required_invalid",
            _method_refs(items),
        ))

    for method in DEGRADED_METHODS:
        items = invocations_by_method.get(method, [])
        method_ok = bool(items) and all(
            item.outcome == SourceCallOutcome.AVAILABLE
            and item.typed_metadata.timestamps_complete
            for item in items
        )
        for item in items:
            cutoff = item.information_cutoff_at
            if cutoff is not None and not (
                0 <= (policy_input.analysis_started_at - cutoff).total_seconds()
                <= (
                    config.max_research_market_age_seconds
                    if method == "get_indicators"
                    else config.max_enrichment_age_seconds
                )
            ):
                method_ok = False
        rules.append(_rule(
            f"source.degraded.{method}",
            RuleOutcome.PASS if method_ok else RuleOutcome.DEGRADE,
            f"{method}.available" if method_ok else f"{method}.degraded",
            _method_refs(items),
        ))

    for method in OPTIONAL_METHODS:
        items = invocations_by_method.get(method, [])
        method_ok = bool(items) and all(
            item.outcome == SourceCallOutcome.AVAILABLE for item in items
        )
        rules.append(_rule(
            f"source.optional.{method}",
            RuleOutcome.PASS if method_ok else RuleOutcome.WARN,
            f"{method}.available" if method_ok else f"{method}.optional_unavailable",
            _method_refs(items),
        ))

    if any(rule.outcome == RuleOutcome.FAIL for rule in rules):
        verdict = PolicyVerdict.REJECT
        permitted_ratings: tuple[str, ...] = ()
    elif any(rule.outcome == RuleOutcome.DEGRADE for rule in rules):
        verdict = PolicyVerdict.HOLD_ONLY
        permitted_ratings = (PortfolioRating.HOLD.value,)
    else:
        verdict = PolicyVerdict.PASS
        permitted_ratings = ALL_RATINGS

    if tuple(rule.rule_id for rule in rules) != EXPECTED_POLICY_RULE_IDS:
        raise RuntimeError("source policy rule inventory drift")

    data_times = [snapshot.candle_close_at]
    data_times.extend(
        item.information_cutoff_at for item in invocations
        if item.outcome == SourceCallOutcome.AVAILABLE
        and item.information_cutoff_at is not None
    )
    data_as_of = max(data_times)
    quality_flags = tuple(sorted({
        rule.code for rule in rules
        if rule.outcome in (RuleOutcome.WARN, RuleOutcome.DEGRADE)
    } | {
        flag for invocation in invocations for flag in invocation.typed_metadata.quality_flags
    }))
    input_digest = canonical_digest(policy_input.model_dump(mode="json"))
    configuration_hash = canonical_digest(config.model_dump(mode="json"))
    result_data = {
        "policy_version": config.policy_version,
        "policy_configuration_hash": configuration_hash,
        "session_id": str(session.session_id),
        "input_digest": input_digest,
        "verdict": verdict,
        "permitted_ratings": permitted_ratings,
        "data_as_of": data_as_of,
        "quality_flags": quality_flags,
        "rules": tuple(rules),
    }
    draft = SourcePolicyResult.model_construct(
        **result_data, result_digest="sha256:" + "0" * 64
    )
    result_digest = canonical_digest(
        draft.model_dump(mode="json", exclude={"result_digest"})
    )
    return SourcePolicyResult(**result_data, result_digest=result_digest)
