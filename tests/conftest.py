from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from trading_platform.contracts import (
    PortfolioDecision,
    PortfolioRating,
    Provenance,
    RATING_SCORE,
    SentimentReport,
    SignalPayload,
    SignalRevocationPayload,
    SignedEnvelope,
)


TEST_SECRET = "a-reliable-test-secret-that-is-longer-than-32-bytes"


@pytest.fixture
def signal_factory():
    def factory(**updates):
        now = updates.pop("now", datetime.now(timezone.utc).replace(microsecond=0))
        rating = updates.pop("rating", PortfolioRating.HOLD)
        sequence = updates.pop("sequence", 1)
        payload = SignalPayload(
            run_id=uuid4(),
            correlation_id=uuid4(),
            instrument_id="crypto:binance:spot:BTCUSDT",
            execution_snapshot_id=uuid4(),
            evidence_manifest_id=uuid4(),
            environment="production",
            bot_id="freqtrade-primary",
            exchange="binance",
            pair="BTC/USDT",
            timeframe="5m",
            sequence=sequence,
            candle_close_at=now - timedelta(minutes=6),
            analysis_started_at=now - timedelta(minutes=5),
            analysis_completed_at=now - timedelta(minutes=1),
            published_at=now - timedelta(seconds=30),
            signal_available_at=now - timedelta(seconds=30),
            expires_at=now + timedelta(minutes=30),
            decision=PortfolioDecision(
                rating=rating,
                executive_summary="Validated test decision.",
                investment_thesis="Contract and delivery testing only.",
            ),
            sentiment=SentimentReport(
                overall_band="Neutral", overall_score=5, confidence="low", narrative="Test narrative."
            ),
            normalized_rating_score=RATING_SCORE[rating],
            provenance=Provenance(
                producer_version="0.3.1",
                code_revision="test",
                llm_provider="synthetic",
                deep_model="test",
                quick_model="test",
                configuration_hash="0" * 64,
                data_as_of=now - timedelta(minutes=6),
            ),
            **updates,
        )
        return SignedEnvelope.sign(payload, TEST_SECRET)

    return factory


@pytest.fixture
def revocation_factory(signal_factory):
    def factory(**updates):
        target = updates.pop("target", signal_factory(rating=PortfolioRating.BUY))
        now = updates.pop("now", datetime.now(timezone.utc).replace(microsecond=0))
        payload = SignalRevocationPayload(
            signal_id=target.payload.signal_id,
            target_sequence=target.payload.sequence,
            target_checksum=target.checksum,
            run_id=uuid4(),
            correlation_id=uuid4(),
            instrument_id=target.payload.instrument_id,
            execution_snapshot_id=uuid4(),
            evidence_manifest_id=uuid4(),
            environment=target.payload.environment,
            bot_id=target.payload.bot_id,
            exchange=target.payload.exchange,
            pair=target.payload.pair,
            timeframe=target.payload.timeframe,
            sequence=target.payload.sequence + 1,
            reason_code="execution_snapshot.invalid",
            denied_rating=PortfolioRating.BUY,
            published_at=now,
            revoked_at=now,
            producer_version="0.3.1",
            code_revision="test",
            **updates,
        )
        return SignedEnvelope.sign(payload, TEST_SECRET)

    return factory
