from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from trading_platform.contracts import (
    PortfolioRating,
    SignalPayload,
    SignalRevocationPayload,
    SignalStatus,
    SignedEnvelope,
)
from conftest import TEST_SECRET


def test_signed_envelope_round_trip(signal_factory):
    envelope = signal_factory(rating=PortfolioRating.BUY)
    restored = SignedEnvelope.model_validate_json(envelope.model_dump_json())
    assert restored.verify(TEST_SECRET)
    assert restored.payload.normalized_rating_score == 1.0


def test_tampered_payload_fails_signature(signal_factory):
    envelope = signal_factory()
    envelope.payload.decision.executive_summary = "tampered"
    assert not envelope.verify(TEST_SECRET)


def test_rating_score_cannot_disagree(signal_factory):
    envelope = signal_factory()
    data = envelope.payload.model_dump()
    data["normalized_rating_score"] = 1.0
    with pytest.raises(ValidationError, match="does not match rating"):
        SignalPayload.model_validate(data)


def test_naive_timestamps_are_rejected(signal_factory):
    envelope = signal_factory()
    data = envelope.payload.model_dump()
    data["published_at"] = datetime.now()
    with pytest.raises(ValidationError, match="timezone-aware"):
        SignalPayload.model_validate(data)


def test_signal_usability_is_fail_closed(signal_factory):
    now = datetime.now(timezone.utc)
    envelope = signal_factory(now=now)
    assert envelope.payload.is_usable(now, "production", "freqtrade-primary")
    assert not envelope.payload.is_usable(now, "staging", "freqtrade-primary")
    assert not envelope.payload.is_usable(now + timedelta(hours=1), "production", "freqtrade-primary")


def test_short_hmac_key_is_rejected(signal_factory):
    with pytest.raises(ValueError, match="at least 32"):
        SignedEnvelope.sign(signal_factory().payload, "too-short")


def test_signed_revocation_round_trips_as_distinct_event(revocation_factory):
    envelope = revocation_factory()
    restored = SignedEnvelope.model_validate_json(envelope.model_dump_json())
    assert isinstance(restored.payload, SignalRevocationPayload)
    assert restored.payload.sequence > restored.payload.target_sequence
    assert restored.verify(TEST_SECRET)


def test_created_signal_cannot_masquerade_as_revoked(signal_factory):
    data = signal_factory().payload.model_dump()
    data["status"] = SignalStatus.REVOKED
    with pytest.raises(ValidationError, match="must have valid status"):
        SignalPayload.model_validate(data)


def test_revocation_must_advance_target_sequence(signal_factory, revocation_factory):
    original = signal_factory(rating=PortfolioRating.BUY)
    target = SignedEnvelope.sign(
        original.payload.model_copy(update={"sequence": 2}), TEST_SECRET
    )
    data = revocation_factory(target=target).payload.model_dump()
    data["sequence"] = data["target_sequence"]
    with pytest.raises(ValidationError, match="newer than its target"):
        SignalRevocationPayload.model_validate(data)
