from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from trading_platform.capture import canonical_digest
from trading_platform.contracts import (
    ArtifactRef,
    CaptureSession,
    ExecutionMarketSnapshot,
    InstrumentIdentity,
    SemanticInvocationRecord,
    SourceCallOutcome,
    SourceTemporalMetadata,
    VendorAttemptRecord,
)
from trading_platform.source_allowlist import ALLOWED_INGRESS
from trading_platform.source_policy import (
    OPTIONAL_METHODS,
    PolicyVerdict,
    SourcePolicyInput,
    SourcePolicyResult,
    evaluate_source_policy,
)


NOW = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)


def digest(number: int) -> str:
    return "sha256:" + f"{number:064x}"


def artifact(number: int) -> ArtifactRef:
    value = digest(number)
    return ArtifactRef(
        digest=value,
        media_type="application/json",
        byte_length=10,
        storage_path=f"sha256/{number:02x}/{number:02x}/{value[7:]}",
    )


def temporal_metadata(method: str, outcome: SourceCallOutcome) -> SourceTemporalMetadata:
    symbol_methods = {
        "resolve_instrument_identity", "get_stock_data", "get_indicators",
        "get_verified_market_snapshot", "get_news", "fetch_stocktwits_messages",
        "fetch_reddit_posts",
    }
    resolved = "BTC-USD"
    if method == "fetch_stocktwits_messages":
        resolved = "BTC.X"
    elif method == "fetch_reddit_posts":
        resolved = "BTC"
    base = {
        "result_kind": outcome,
        "requested_symbol": "BTC-USD" if method in symbol_methods else None,
        "resolved_symbol": resolved if method in symbol_methods else None,
        "timestamps_complete": True,
        "source_time_basis": "none",
    }
    if method in ("get_stock_data", "get_indicators", "get_verified_market_snapshot"):
        bar_at = datetime(2026, 8, 21, tzinfo=timezone.utc)
        return SourceTemporalMetadata(
            **{**base, "source_time_basis": "daily_bar_close"},
            latest_bar_at=bar_at,
            latest_bar_close_at=bar_at + timedelta(days=1),
            market_bar_closed=True,
            item_count=1,
            information_cutoff_at=bar_at + timedelta(days=1),
        )
    if method in (
        "get_news", "get_global_news", "fetch_stocktwits_messages", "fetch_reddit_posts"
    ):
        source_time = NOW - timedelta(hours=1)
        return SourceTemporalMetadata(
            **{
                **base,
                "source_time_basis": (
                    "created_at" if method.startswith("fetch_") else "published_at"
                ),
            },
            latest_item_at=source_time,
            earliest_item_at=source_time,
            item_count=1,
            information_cutoff_at=source_time,
        )
    return SourceTemporalMetadata(**base)


def make_policy_input(
    *,
    omitted_methods: set[str] | None = None,
    outcome_overrides: dict[str, SourceCallOutcome] | None = None,
    verified: bool = True,
) -> SourcePolicyInput:
    omitted_methods = omitted_methods or set()
    outcome_overrides = outcome_overrides or {}
    session_id = uuid4()
    run_id = uuid4()
    manifest_id = uuid4()
    snapshot_id = uuid4()
    session = CaptureSession(
        session_id=session_id,
        run_id=run_id,
        manifest_id=manifest_id,
        instrument_id="crypto:binance:spot:BTC-USDT",
        execution_snapshot_id=snapshot_id,
        job_id=uuid4(),
        job_attempt=1,
        fencing_token=1,
        mode="live_capture",
        status="evaluating",
        upstream_version="0.3.1",
        upstream_commit="0" * 40,
        adapter_version="1.0.0",
        configuration_hash="0" * 64,
        started_at=NOW,
        deadline_at=NOW + timedelta(minutes=10),
        collection_closed_at=NOW + timedelta(minutes=1),
    )
    instrument = InstrumentIdentity(
        instrument_id="crypto:binance:spot:BTC-USDT",
        research_symbol="BTC-USD",
        execution_exchange="binance",
        execution_pair="BTC/USDT",
        market_type="spot",
        base="BTC",
        quote="USDT",
        research_quote="USD",
    )
    snapshot = ExecutionMarketSnapshot(
        snapshot_id=snapshot_id,
        instrument_id=instrument.instrument_id,
        exchange="binance",
        pair="BTC/USDT",
        market_type="spot",
        timeframe="5m",
        candle_open_at=NOW - timedelta(minutes=6),
        candle_close_at=NOW - timedelta(minutes=1),
        open="60000", high="60100", low="59900", close="60050", volume="10",
        retrieved_at=NOW - timedelta(seconds=50),
        exchange_time_at=NOW - timedelta(seconds=50),
        clock_offset_ms=25,
        is_closed=True,
        has_gap=False,
        collector_version="test",
        raw_artifact=artifact(1),
    )
    invocations = []
    attempts = []
    verified_digests = [snapshot.raw_artifact.digest]
    methods = [method for method in ALLOWED_INGRESS if method not in omitted_methods]
    for ordinal, method in enumerate(methods):
        invocation_id = UUID(int=ordinal + 1)
        observation_id = UUID(int=100 + ordinal)
        outcome = outcome_overrides.get(method, SourceCallOutcome.AVAILABLE)
        value_digest = digest(10 + ordinal)
        metadata = temporal_metadata(method, outcome)
        error_code = None if outcome == SourceCallOutcome.AVAILABLE else "vendor_no_data"
        invocation = SemanticInvocationRecord(
            invocation_id=invocation_id,
            session_id=session_id,
            ordinal=ordinal,
            method=method,
            category=ALLOWED_INGRESS[method].category,
            policy_subject=method,
            consumer=ALLOWED_INGRESS[method].consumer,
            sanitized_arguments={"args": ["BTC-USD"], "kwargs": {}},
            arguments_hash=canonical_digest({"args": ["BTC-USD"], "kwargs": {}}),
            started_at=NOW + timedelta(seconds=ordinal),
            first_seen_at=NOW + timedelta(seconds=ordinal + 1),
            completed_at=NOW + timedelta(seconds=ordinal + 2),
            information_cutoff_at=metadata.information_cutoff_at,
            outcome=outcome,
            error_code=error_code,
            normalized_artifact_digest=value_digest,
            observation_id=observation_id,
            typed_metadata=metadata,
            replay_safe=method not in {
                "fetch_stocktwits_messages", "fetch_reddit_posts",
                "get_macro_indicators", "get_prediction_markets",
            },
            replay_unsafe_reason=(
                "live source" if method in {
                    "fetch_stocktwits_messages", "fetch_reddit_posts",
                    "get_macro_indicators", "get_prediction_markets",
                } else None
            ),
        )
        invocations.append(invocation)
        attempts.append(VendorAttemptRecord(
            invocation_id=invocation_id,
            session_id=session_id,
            fallback_ordinal=0,
            vendor=ALLOWED_INGRESS[method].vendors[0],
            started_at=invocation.started_at,
            first_seen_at=invocation.first_seen_at,
            completed_at=invocation.completed_at,
            outcome=outcome,
            error_code=error_code,
            normalized_artifact_digest=(
                value_digest if outcome == SourceCallOutcome.AVAILABLE else None
            ),
            observation_id=(
                observation_id if outcome == SourceCallOutcome.AVAILABLE else None
            ),
        ))
        verified_digests.append(value_digest)
    if not verified:
        verified_digests.pop()
    return SourcePolicyInput(
        session=session,
        instrument=instrument,
        execution_snapshot=snapshot,
        vendor_plan={method: rule.vendors for method, rule in ALLOWED_INGRESS.items()},
        invocations=tuple(invocations),
        vendor_attempts=tuple(attempts),
        verified_artifact_digests=tuple(verified_digests),
        analysis_started_at=NOW,
        collection_cutoff_at=NOW + timedelta(minutes=1),
    )


def test_complete_ledger_passes_and_digest_is_repeatable():
    policy_input = make_policy_input()
    first = evaluate_source_policy(policy_input)
    second = evaluate_source_policy(policy_input)
    assert first.verdict == PolicyVerdict.PASS
    assert first.permitted_ratings == (
        "Buy", "Overweight", "Hold", "Underweight", "Sell"
    )
    assert first.result_digest == second.result_digest
    assert first.input_digest == second.input_digest
    assert first.data_as_of == NOW - timedelta(minutes=1)


def test_degraded_news_allows_only_original_hold():
    result = evaluate_source_policy(make_policy_input(
        outcome_overrides={"get_news": SourceCallOutcome.NO_DATA}
    ))
    assert result.verdict == PolicyVerdict.HOLD_ONLY
    assert result.permitted_ratings == ("Hold",)
    assert "get_news.degraded" in result.quality_flags


def test_absent_optional_sources_warn_but_do_not_block_ratings():
    result = evaluate_source_policy(make_policy_input(omitted_methods=set(OPTIONAL_METHODS)))
    assert result.verdict == PolicyVerdict.PASS
    assert "get_macro_indicators.optional_unavailable" in result.quality_flags
    assert "get_prediction_markets.optional_unavailable" in result.quality_flags


def test_missing_verified_artifact_rejects():
    result = evaluate_source_policy(make_policy_input(verified=False))
    assert result.verdict == PolicyVerdict.REJECT
    assert result.permitted_ratings == ()
    integrity = next(rule for rule in result.rules if rule.rule_id == "artifact.integrity")
    assert integrity.code == "artifacts.unverified_or_missing"


def test_wrong_resolved_symbol_rejects():
    policy_input = make_policy_input()
    invocations = list(policy_input.invocations)
    target = next(index for index, item in enumerate(invocations) if item.method == "get_news")
    invocation = invocations[target]
    invocations[target] = invocation.model_copy(update={
        "typed_metadata": invocation.typed_metadata.model_copy(
            update={"resolved_symbol": "ETH-USD"}
        )
    })
    result = evaluate_source_policy(policy_input.model_copy(
        update={"invocations": tuple(invocations)}
    ))
    assert result.verdict == PolicyVerdict.REJECT
    symbols = next(rule for rule in result.rules if rule.rule_id == "contract.research_symbols")
    assert symbols.code == "symbols.requested_or_resolved_mismatch"


def test_future_source_timestamp_rejects():
    policy_input = make_policy_input()
    invocations = list(policy_input.invocations)
    target = next(index for index, item in enumerate(invocations) if item.method == "get_news")
    invocation = invocations[target]
    future = invocation.first_seen_at + timedelta(minutes=5)
    metadata = invocation.typed_metadata.model_copy(update={
        "latest_item_at": future,
        "information_cutoff_at": future,
    })
    invocations[target] = invocation.model_copy(update={
        "typed_metadata": metadata,
        "information_cutoff_at": future,
    })
    result = evaluate_source_policy(policy_input.model_copy(
        update={"invocations": tuple(invocations)}
    ))
    assert result.verdict == PolicyVerdict.REJECT
    temporal = next(rule for rule in result.rules if rule.rule_id == "temporal.invocations")
    assert temporal.code == "temporal.future_or_late_input"


def test_missing_required_market_source_rejects():
    result = evaluate_source_policy(make_policy_input(
        omitted_methods={"get_stock_data"}
    ))
    assert result.verdict == PolicyVerdict.REJECT
    required = next(
        rule for rule in result.rules
        if rule.rule_id == "source.required.get_stock_data"
    )
    assert required.code == "get_stock_data.required_invalid"


def test_reordered_vendor_fallback_rejects():
    policy_input = make_policy_input()
    attempts = list(policy_input.vendor_attempts)
    target = next(index for index, item in enumerate(policy_input.invocations)
                  if item.method == "get_news")
    attempts[target] = attempts[target].model_copy(update={"vendor": "alpha_vantage"})
    result = evaluate_source_policy(policy_input.model_copy(
        update={"vendor_attempts": tuple(attempts)}
    ))
    assert result.verdict == PolicyVerdict.REJECT
    fallback = next(
        rule for rule in result.rules if rule.rule_id == "contract.vendor_fallbacks"
    )
    assert fallback.code == "fallbacks.invalid"


def test_exact_eth_identity_also_passes():
    policy_input = make_policy_input()
    session = policy_input.session.model_copy(update={
        "instrument_id": "crypto:binance:spot:ETH-USDT"
    })
    instrument = policy_input.instrument.model_copy(update={
        "instrument_id": "crypto:binance:spot:ETH-USDT",
        "research_symbol": "ETH-USD",
        "execution_pair": "ETH/USDT",
        "base": "ETH",
    })
    snapshot = policy_input.execution_snapshot.model_copy(update={
        "instrument_id": instrument.instrument_id,
        "pair": "ETH/USDT",
    })
    invocations = []
    for invocation in policy_input.invocations:
        rule = ALLOWED_INGRESS[invocation.method]
        arguments = invocation.sanitized_arguments
        metadata = invocation.typed_metadata
        if rule.symbol_argument:
            arguments = {"args": ["ETH-USD"], "kwargs": {}}
            resolved = "ETH-USD"
            if invocation.method == "fetch_stocktwits_messages":
                resolved = "ETH.X"
            elif invocation.method == "fetch_reddit_posts":
                resolved = "ETH"
            metadata = metadata.model_copy(update={
                "requested_symbol": "ETH-USD", "resolved_symbol": resolved
            })
        invocations.append(invocation.model_copy(update={
            "sanitized_arguments": arguments,
            "arguments_hash": canonical_digest(arguments),
            "typed_metadata": metadata,
        }))
    result = evaluate_source_policy(policy_input.model_copy(update={
        "session": session,
        "instrument": instrument,
        "execution_snapshot": snapshot,
        "invocations": tuple(invocations),
    }))
    assert result.verdict == PolicyVerdict.PASS


def test_policy_result_digest_cannot_be_substituted():
    result = evaluate_source_policy(make_policy_input())
    tampered = result.model_dump(mode="json")
    tampered["result_digest"] = digest(999)
    with pytest.raises(ValidationError, match="digest mismatch"):
        SourcePolicyResult(**tampered)
