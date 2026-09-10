from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from .contracts import SignalPayload, SignedEnvelope, SignalStatus


class ValidationSettings(Protocol):
    hmac_secret: str
    environment: str
    bot_id: str
    exchange: str
    timeframe: str
    clock_skew_seconds: int


def validate_for_materialization(
    envelope: SignedEnvelope, settings: ValidationSettings, now: datetime
) -> str | None:
    payload = envelope.payload
    if not envelope.verify(settings.hmac_secret):
        return "signature_or_checksum_invalid"
    if payload.environment != settings.environment or payload.bot_id != settings.bot_id:
        return "routing_mismatch"
    if payload.exchange != settings.exchange:
        return "exchange_mismatch"
    if payload.timeframe != settings.timeframe:
        return "timeframe_mismatch"
    if payload.published_at > now + timedelta(seconds=settings.clock_skew_seconds):
        return "published_in_future"
    if isinstance(payload, SignalPayload):
        if payload.provenance.data_as_of > now + timedelta(seconds=settings.clock_skew_seconds):
            return "source_data_in_future"
        if payload.status != SignalStatus.VALID:
            return f"status_{payload.status.value}"
        if now >= payload.expires_at:
            return "expired"
    return None
