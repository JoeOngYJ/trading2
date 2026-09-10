from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from trading_platform.capture import REDACTED, canonical_digest, classify_error, sanitize
from trading_platform.contracts import (
    CaptureSession,
    CaptureFence,
    CaptureSessionStatus,
    SemanticInvocationRecord,
    SourceCallOutcome,
    SourceCallRecord,
    VendorAttemptRecord,
)


def test_sanitize_redacts_nested_credentials_and_url_userinfo():
    value = {
        "ticker": "BTC-USD",
        "headers": {"Authorization": "Bearer secret", "X-API-Key": "key-value"},
        "url": "https://user:pass@example.com/data?symbol=BTC&apikey=secret&limit=3",
        "message": "token=secret-value allowed text",
    }
    cleaned = sanitize(value)
    assert cleaned["ticker"] == "BTC-USD"
    assert cleaned["headers"]["Authorization"] == REDACTED
    assert cleaned["headers"]["X-API-Key"] == REDACTED
    assert "user:pass" not in cleaned["url"]
    assert "secret" not in cleaned["url"]
    assert f"apikey={REDACTED}" in cleaned["url"]
    assert cleaned["message"] == f"token={REDACTED} allowed text"


def test_canonical_digest_is_order_independent_and_json_safe():
    now = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)
    left = {"b": Decimal("1.20"), "a": now, "values": {"ETH", "BTC"}}
    right = {"values": {"BTC", "ETH"}, "a": now, "b": Decimal("1.20")}
    assert canonical_digest(left) == canonical_digest(right)
    assert canonical_digest(left).startswith("sha256:")


@pytest.mark.parametrize(
    ("error", "outcome", "code"),
    [
        (TimeoutError("secret"), SourceCallOutcome.TIMEOUT, "vendor_timeout"),
        (type("RateLimit", (Exception,), {"status_code": 429})("secret"),
         SourceCallOutcome.RATE_LIMITED, "vendor_rate_limited"),
        (type("Auth", (Exception,), {"status_code": 401})("secret"),
         SourceCallOutcome.AUTH_ERROR, "vendor_auth_failed"),
        (RuntimeError("apikey=secret"), SourceCallOutcome.VENDOR_ERROR, "vendor_unavailable"),
    ],
)
def test_error_classification_never_uses_exception_text(error, outcome, code):
    assert classify_error(error) == (outcome, code)
    assert "secret" not in code


def test_capture_session_state_invariants():
    now = datetime.now(timezone.utc)
    base = {
        "run_id": uuid4(),
        "manifest_id": uuid4(),
        "instrument_id": "crypto:binance:spot:BTC-USDT",
        "execution_snapshot_id": uuid4(),
        "job_id": uuid4(),
        "job_attempt": 1,
        "fencing_token": 1,
        "mode": "live_capture",
        "upstream_version": "0.3.1",
        "upstream_commit": "0" * 40,
        "adapter_version": "1",
        "configuration_hash": "0" * 64,
        "started_at": now,
        "deadline_at": now + timedelta(minutes=15),
    }
    assert CaptureSession(**base).status == CaptureSessionStatus.COLLECTING
    assert CaptureSession(
        **base, status="evaluating", collection_closed_at=now + timedelta(minutes=1)
    ).completed_at is None
    with pytest.raises(ValidationError, match="completed_at"):
        CaptureSession(
            **base, status="sealed", collection_closed_at=now + timedelta(minutes=1)
        )
    with pytest.raises(ValidationError, match="rejection code"):
        CaptureSession(
            **base, status="rejected", collection_closed_at=now,
            completed_at=now,
        )


def test_capture_fence_requires_positive_attempt_and_token():
    fence = CaptureFence(job_id=uuid4(), worker_id="worker-a", attempt=2, fencing_token=7)
    assert fence.attempt == 2
    with pytest.raises(ValidationError):
        CaptureFence(job_id=uuid4(), worker_id="worker-a", attempt=0, fencing_token=7)


def test_available_source_call_requires_normalized_evidence():
    now = datetime.now(timezone.utc)
    base = {
        "session_id": uuid4(),
        "ordinal": 0,
        "method": "get_stock_data",
        "category": "research_market",
        "vendor": "yfinance",
        "sanitized_arguments": {"ticker": "BTC-USD"},
        "arguments_hash": canonical_digest({"ticker": "BTC-USD"}),
        "started_at": now,
        "first_seen_at": now + timedelta(milliseconds=1),
        "completed_at": now + timedelta(milliseconds=2),
        "outcome": "available",
    }
    with pytest.raises(ValidationError, match="normalized evidence"):
        SourceCallRecord(**base)
    record = SourceCallRecord(
        **base,
        normalized_artifact_digest="sha256:" + "a" * 64,
        observation_id=uuid4(),
    )
    assert record.outcome == SourceCallOutcome.AVAILABLE


def test_semantic_invocation_requires_exact_evidence_for_delivered_sentinel():
    now = datetime.now(timezone.utc)
    base = {
        "session_id": uuid4(),
        "ordinal": 0,
        "method": "get_stock_data",
        "category": "research_market",
        "policy_subject": "get_stock_data",
        "consumer": "market_analyst",
        "sanitized_arguments": {"args": ["BTC-USD"]},
        "arguments_hash": canonical_digest({"args": ["BTC-USD"]}),
        "started_at": now,
        "first_seen_at": now,
        "completed_at": now,
        "outcome": "no_data",
        "error_code": "vendor_no_data",
        "typed_metadata": {
            "schema_version": "source-temporal/1.0.0",
            "result_kind": "no_data",
            "timestamps_complete": True,
            "source_time_basis": "none",
        },
        "replay_safe": True,
    }
    with pytest.raises(ValidationError, match="exact normalized evidence"):
        SemanticInvocationRecord(**base)
    invocation = SemanticInvocationRecord(
        **base,
        normalized_artifact_digest="sha256:" + "b" * 64,
        observation_id=uuid4(),
    )
    assert invocation.outcome == SourceCallOutcome.NO_DATA


def test_vendor_attempt_requires_fallback_identity_and_typed_failure():
    now = datetime.now(timezone.utc)
    attempt = VendorAttemptRecord(
        invocation_id=uuid4(),
        session_id=uuid4(),
        fallback_ordinal=1,
        vendor="alpha_vantage",
        started_at=now,
        first_seen_at=now,
        completed_at=now,
        outcome="rate_limited",
        error_code="vendor_rate_limited",
    )
    assert attempt.fallback_ordinal == 1
    with pytest.raises(ValidationError, match="typed error code"):
        VendorAttemptRecord(**{**attempt.model_dump(), "error_code": None})
