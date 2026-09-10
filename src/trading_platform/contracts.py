from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "2.0.0"


class SignalStatus(str, Enum):
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


RATING_SCORE: dict[PortfolioRating, float] = {
    PortfolioRating.BUY: 1.0,
    PortfolioRating.OVERWEIGHT: 0.5,
    PortfolioRating.HOLD: 0.0,
    PortfolioRating.UNDERWEIGHT: -0.5,
    PortfolioRating.SELL: -1.0,
}


class PortfolioDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: PortfolioRating
    executive_summary: str = Field(min_length=1)
    investment_thesis: str = Field(min_length=1)
    price_target: float | None = None
    time_horizon: str | None = None


class SentimentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_band: Literal[
        "Bullish",
        "Mildly Bullish",
        "Neutral",
        "Mixed",
        "Mildly Bearish",
        "Bearish",
    ]
    overall_score: float = Field(ge=0.0, le=10.0)
    confidence: Literal["low", "medium", "high"]
    narrative: str = Field(min_length=1)


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producer: str = "TauricResearch/TradingAgents"
    producer_version: str
    code_revision: str
    llm_provider: str
    deep_model: str
    quick_model: str
    configuration_hash: str
    data_as_of: datetime
    source_timestamps: dict[str, datetime] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)

    @field_validator("data_as_of", mode="after")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("data_as_of must be timezone-aware")
        return value.astimezone(timezone.utc)


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    media_type: str
    byte_length: int = Field(ge=0)
    storage_path: str


class InstrumentIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str = Field(pattern=r"^crypto:[a-z0-9_-]+:(spot|margin|future):[A-Z0-9._-]+$")
    research_symbol: str
    execution_exchange: str
    execution_pair: str
    market_type: Literal["spot", "margin", "future"]
    base: str
    quote: str
    research_quote: str
    timezone: Literal["UTC"] = "UTC"
    enabled: bool = True


class ExecutionMarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID = Field(default_factory=uuid4)
    instrument_id: str
    exchange: str
    pair: str
    market_type: Literal["spot", "margin", "future"]
    timeframe: str
    candle_type: str = "spot"
    candle_open_at: datetime
    candle_close_at: datetime
    open: str
    high: str
    low: str
    close: str
    volume: str
    retrieved_at: datetime
    exchange_time_at: datetime
    clock_offset_ms: int
    is_closed: bool
    has_gap: bool
    collector_version: str
    raw_artifact: ArtifactRef

    @model_validator(mode="after")
    def validate_snapshot(self) -> "ExecutionMarketSnapshot":
        for name in ("candle_open_at", "candle_close_at", "retrieved_at", "exchange_time_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            setattr(self, name, value.astimezone(timezone.utc))
        if self.candle_close_at <= self.candle_open_at:
            raise ValueError("candle must close after it opens")
        if not self.is_closed or self.candle_close_at > self.exchange_time_at:
            raise ValueError("execution snapshot must contain a completed candle")
        return self


class SourceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: UUID = Field(default_factory=uuid4)
    category: Literal["execution_market", "research_market", "news", "social", "macro", "prediction", "fundamental"]
    vendor: str
    symbol_or_query: str
    external_id: str | None = None
    canonical_url: str | None = None
    event_at: datetime | None = None
    published_at: datetime | None = None
    first_seen_at: datetime
    retrieved_at: datetime
    artifact: ArtifactRef
    request_parameters: dict[str, Any] = Field(default_factory=dict)
    status: Literal["available", "unavailable", "error"]
    error_code: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    replay_safe: bool
    replay_unsafe_reason: str | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> "SourceObservation":
        for name in ("event_at", "published_at", "first_seen_at", "retrieved_at"):
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f"{name} must be timezone-aware")
                setattr(self, name, value.astimezone(timezone.utc))
        if self.retrieved_at < self.first_seen_at:
            raise ValueError("retrieved_at precedes first_seen_at")
        if not self.replay_safe and not self.replay_unsafe_reason:
            raise ValueError("replay-unsafe observations require a reason")
        return self


class EvidenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    instrument_id: str
    execution_snapshot_id: UUID
    mode: Literal["live", "captured_replay"]
    collection_started_at: datetime
    collection_completed_at: datetime
    observation_ids: list[UUID]
    configured_vendors: dict[str, str | list[str]]
    vendor_fallbacks: list[str] = Field(default_factory=list)
    required_sources: dict[str, Literal["available", "degraded", "missing"]]
    replay_safe: bool
    quality_flags: list[str] = Field(default_factory=list)
    policy_evaluation_id: UUID | None = None
    policy_result_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class CaptureSessionStatus(str, Enum):
    COLLECTING = "collecting"
    EVALUATING = "evaluating"
    SEALED = "sealed"
    REJECTED = "rejected"
    ABANDONED = "abandoned"


class SourceCallOutcome(str, Enum):
    AVAILABLE = "available"
    NO_DATA = "no_data"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    VENDOR_ERROR = "vendor_error"
    POLICY_REJECTED = "policy_rejected"
    INVALID_RESPONSE = "invalid_response"


class SourceTemporalMetadata(BaseModel):
    """Typed, source-derived chronology attached to one semantic result."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["source-temporal/1.0.0"] = "source-temporal/1.0.0"
    result_kind: SourceCallOutcome
    requested_symbol: str | None = None
    resolved_symbol: str | None = None
    requested_start_at: datetime | None = None
    requested_end_at: datetime | None = None
    earliest_item_at: datetime | None = None
    latest_item_at: datetime | None = None
    latest_bar_at: datetime | None = None
    latest_bar_close_at: datetime | None = None
    market_bar_closed: bool | None = None
    item_count: int = Field(default=0, ge=0)
    timestamps_complete: bool
    source_time_basis: Literal[
        "published_at", "created_at", "daily_bar_close", "retrieved_at", "none"
    ]
    information_cutoff_at: datetime | None = None
    quality_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_temporal_metadata(self) -> "SourceTemporalMetadata":
        fields = (
            "requested_start_at", "requested_end_at", "earliest_item_at",
            "latest_item_at", "latest_bar_at", "latest_bar_close_at",
            "information_cutoff_at",
        )
        for name in fields:
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f"{name} must be timezone-aware")
                setattr(self, name, value.astimezone(timezone.utc))
        if (
            self.requested_start_at is not None and self.requested_end_at is not None
            and self.requested_start_at > self.requested_end_at
        ):
            raise ValueError("requested temporal window is reversed")
        if (
            self.earliest_item_at is not None and self.latest_item_at is not None
            and self.earliest_item_at > self.latest_item_at
        ):
            raise ValueError("source item timestamps are reversed")
        if self.latest_bar_close_at is not None and self.latest_bar_at is None:
            raise ValueError("bar close requires a bar timestamp")
        if self.market_bar_closed is not None and self.latest_bar_close_at is None:
            raise ValueError("bar closure state requires a close timestamp")
        if self.timestamps_complete and self.item_count > 0:
            has_time = self.latest_item_at is not None or self.latest_bar_close_at is not None
            if not has_time and self.source_time_basis != "retrieved_at":
                raise ValueError("complete nonempty metadata requires source timestamps")
        return self


class CaptureSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    manifest_id: UUID
    instrument_id: str
    execution_snapshot_id: UUID
    job_id: UUID
    job_attempt: int = Field(gt=0)
    fencing_token: int = Field(gt=0)
    mode: Literal["live_capture", "captured_replay"]
    status: CaptureSessionStatus = CaptureSessionStatus.COLLECTING
    upstream_version: str
    upstream_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    adapter_version: str
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime
    deadline_at: datetime
    collection_closed_at: datetime | None = None
    completed_at: datetime | None = None
    rejection_code: str | None = None

    @model_validator(mode="after")
    def validate_session(self) -> "CaptureSession":
        for name in ("started_at", "deadline_at", "collection_closed_at", "completed_at"):
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f"{name} must be timezone-aware")
                setattr(self, name, value.astimezone(timezone.utc))
        if self.deadline_at <= self.started_at:
            raise ValueError("capture deadline must follow start time")
        if self.status == CaptureSessionStatus.COLLECTING:
            if self.collection_closed_at is not None:
                raise ValueError("collecting sessions cannot have a collection cutoff")
        elif self.collection_closed_at is None:
            raise ValueError("closed collection requires a collection cutoff")
        elif not (self.started_at <= self.collection_closed_at <= self.deadline_at):
            raise ValueError("collection cutoff is outside the capture window")
        terminal = self.status in (
            CaptureSessionStatus.SEALED,
            CaptureSessionStatus.REJECTED,
            CaptureSessionStatus.ABANDONED,
        )
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal capture sessions require completed_at")
        if self.status in (CaptureSessionStatus.REJECTED, CaptureSessionStatus.ABANDONED):
            if not self.rejection_code:
                raise ValueError("rejected or abandoned sessions require a rejection code")
        elif self.rejection_code is not None:
            raise ValueError("non-rejected sessions cannot have a rejection code")
        return self


class CaptureFence(BaseModel):
    """Identity presented by a worker for a capture-session state transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: UUID
    worker_id: str = Field(min_length=1, max_length=255)
    attempt: int = Field(gt=0)
    fencing_token: int = Field(gt=0)


SourceCategory = Literal[
    "research_market", "news", "social", "macro", "prediction", "fundamental"
]


class SemanticInvocationRecord(BaseModel):
    """The exact final value delivered across one graph data boundary."""

    model_config = ConfigDict(extra="forbid")

    invocation_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    ordinal: int = Field(ge=0)
    method: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    category: SourceCategory
    policy_subject: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    consumer: str = Field(min_length=1, max_length=127)
    sanitized_arguments: dict[str, Any]
    arguments_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    started_at: datetime
    completed_at: datetime
    first_seen_at: datetime
    information_cutoff_at: datetime | None = None
    outcome: SourceCallOutcome
    error_code: str | None = None
    normalized_artifact_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    observation_id: UUID | None = None
    typed_metadata: SourceTemporalMetadata
    replay_safe: bool
    replay_unsafe_reason: str | None = None

    @model_validator(mode="after")
    def validate_invocation(self) -> "SemanticInvocationRecord":
        for name in (
            "started_at", "completed_at", "first_seen_at", "information_cutoff_at"
        ):
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f"{name} must be timezone-aware")
                setattr(self, name, value.astimezone(timezone.utc))
        if not (self.started_at <= self.first_seen_at <= self.completed_at):
            raise ValueError("semantic-invocation timestamps are out of order")
        delivered = self.outcome in (
            SourceCallOutcome.AVAILABLE,
            SourceCallOutcome.NO_DATA,
            SourceCallOutcome.UNAVAILABLE,
        )
        if delivered and (not self.normalized_artifact_digest or not self.observation_id):
            raise ValueError("delivered invocation outcomes require exact normalized evidence")
        if self.outcome == SourceCallOutcome.AVAILABLE and self.error_code is not None:
            raise ValueError("available invocations cannot carry an error code")
        if self.outcome != SourceCallOutcome.AVAILABLE and not self.error_code:
            raise ValueError("non-available invocations require a typed error code")
        if self.typed_metadata.result_kind != self.outcome:
            raise ValueError("typed metadata result kind does not match invocation outcome")
        if self.information_cutoff_at != self.typed_metadata.information_cutoff_at:
            raise ValueError("information cutoff does not match typed metadata")
        if not self.replay_safe and not self.replay_unsafe_reason:
            raise ValueError("replay-unsafe invocations require a reason")
        return self


class VendorAttemptRecord(BaseModel):
    """One ordered vendor attempt belonging to a semantic invocation."""

    model_config = ConfigDict(extra="forbid")

    attempt_id: UUID = Field(default_factory=uuid4)
    invocation_id: UUID
    session_id: UUID
    fallback_ordinal: int = Field(ge=0)
    vendor: str = Field(min_length=1, max_length=127)
    started_at: datetime
    completed_at: datetime
    first_seen_at: datetime
    outcome: SourceCallOutcome
    error_code: str | None = None
    raw_artifact_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    normalized_artifact_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    observation_id: UUID | None = None

    @model_validator(mode="after")
    def validate_attempt(self) -> "VendorAttemptRecord":
        for name in ("started_at", "completed_at", "first_seen_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            setattr(self, name, value.astimezone(timezone.utc))
        if not (self.started_at <= self.first_seen_at <= self.completed_at):
            raise ValueError("vendor-attempt timestamps are out of order")
        if self.outcome == SourceCallOutcome.AVAILABLE:
            if not self.normalized_artifact_digest or not self.observation_id:
                raise ValueError("available vendor attempts require normalized evidence")
            if self.error_code is not None:
                raise ValueError("available vendor attempts cannot carry an error code")
        elif not self.error_code:
            raise ValueError("non-available vendor attempts require a typed error code")
        return self


class SourceCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    ordinal: int = Field(ge=0)
    method: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    category: SourceCategory
    vendor: str
    fallback_ordinal: int = Field(default=0, ge=0)
    consumer: str | None = None
    sanitized_arguments: dict[str, Any]
    arguments_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    started_at: datetime
    completed_at: datetime
    first_seen_at: datetime
    outcome: SourceCallOutcome
    error_code: str | None = None
    raw_artifact_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    normalized_artifact_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    observation_id: UUID | None = None

    @model_validator(mode="after")
    def validate_call(self) -> "SourceCallRecord":
        for name in ("started_at", "completed_at", "first_seen_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            setattr(self, name, value.astimezone(timezone.utc))
        if not (self.started_at <= self.first_seen_at <= self.completed_at):
            raise ValueError("source-call timestamps are out of order")
        if self.outcome == SourceCallOutcome.AVAILABLE:
            if not self.normalized_artifact_digest or not self.observation_id:
                raise ValueError("available calls require normalized evidence")
            if self.error_code is not None:
                raise ValueError("available calls cannot carry an error code")
        elif not self.error_code:
            raise ValueError("non-available calls require a typed error code")
        return self


class SignalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    event_type: Literal["signal.created"] = "signal.created"
    event_id: UUID = Field(default_factory=uuid4)
    signal_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    correlation_id: UUID
    instrument_id: str
    execution_snapshot_id: UUID
    evidence_manifest_id: UUID
    source_policy_result_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    environment: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    bot_id: str = Field(min_length=1, max_length=100)
    exchange: str = Field(min_length=1, max_length=50)
    pair: str = Field(pattern=r"^[A-Z0-9._-]+/[A-Z0-9._-]+(?::[A-Z0-9._-]+)?$")
    asset_type: Literal["crypto"] = "crypto"
    timeframe: str = Field(pattern=r"^[1-9][0-9]*[mhdwM]$")
    sequence: int = Field(ge=1)
    candle_close_at: datetime
    analysis_started_at: datetime
    analysis_completed_at: datetime
    published_at: datetime
    signal_available_at: datetime
    expires_at: datetime
    status: SignalStatus = SignalStatus.VALID
    decision: PortfolioDecision
    sentiment: SentimentReport | None = None
    normalized_rating_score: float = Field(ge=-1.0, le=1.0)
    provenance: Provenance
    supersedes_signal_id: UUID | None = None

    @field_validator(
        "candle_close_at",
        "analysis_started_at",
        "analysis_completed_at",
        "published_at",
        "signal_available_at",
        "expires_at",
        mode="after",
    )
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("all timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_invariants(self) -> "SignalPayload":
        major = self.schema_version.split(".", 1)[0]
        if major != SCHEMA_VERSION.split(".", 1)[0]:
            raise ValueError(f"unsupported schema major version: {major}")
        if self.normalized_rating_score != RATING_SCORE[self.decision.rating]:
            raise ValueError("normalized_rating_score does not match rating")
        if self.analysis_started_at < self.candle_close_at:
            raise ValueError("analysis cannot start before its source candle closes")
        if self.analysis_completed_at < self.analysis_started_at:
            raise ValueError("analysis_completed_at precedes analysis_started_at")
        if self.published_at < self.analysis_completed_at:
            raise ValueError("published_at precedes analysis completion")
        if self.signal_available_at < self.published_at:
            raise ValueError("signal_available_at precedes publication")
        if self.expires_at <= self.published_at:
            raise ValueError("expires_at must be after published_at")
        if self.provenance.data_as_of > self.analysis_completed_at:
            raise ValueError("data_as_of cannot be after analysis completion")
        if self.status != SignalStatus.VALID:
            raise ValueError("signal.created must have valid status")
        return self

    def is_usable(self, now: datetime, expected_environment: str, expected_bot: str) -> bool:
        now = now.astimezone(timezone.utc)
        return (
            self.status == SignalStatus.VALID
            and self.environment == expected_environment
            and self.bot_id == expected_bot
            and self.published_at <= now < self.expires_at
            and self.provenance.data_as_of <= now
        )


class SignalRevocationPayload(BaseModel):
    """Signed tombstone that invalidates one previously actionable signal."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    event_type: Literal["signal.revoked"] = "signal.revoked"
    event_id: UUID = Field(default_factory=uuid4)
    revocation_id: UUID = Field(default_factory=uuid4)
    signal_id: UUID
    target_sequence: int = Field(ge=1)
    target_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: UUID
    correlation_id: UUID
    instrument_id: str
    execution_snapshot_id: UUID
    evidence_manifest_id: UUID | None = None
    source_policy_result_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    environment: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    bot_id: str = Field(min_length=1, max_length=100)
    exchange: str = Field(min_length=1, max_length=50)
    pair: str = Field(pattern=r"^[A-Z0-9._-]+/[A-Z0-9._-]+(?::[A-Z0-9._-]+)?$")
    timeframe: str = Field(pattern=r"^[1-9][0-9]*[mhdwM]$")
    sequence: int = Field(ge=2)
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    denied_rating: PortfolioRating | None = None
    published_at: datetime
    revoked_at: datetime
    producer_version: str = Field(min_length=1)
    code_revision: str = Field(min_length=1)

    @field_validator("published_at", "revoked_at", mode="after")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("revocation timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_invariants(self) -> "SignalRevocationPayload":
        if self.schema_version.split(".", 1)[0] != SCHEMA_VERSION.split(".", 1)[0]:
            raise ValueError("unsupported revocation schema major version")
        if self.sequence <= self.target_sequence:
            raise ValueError("revocation sequence must be newer than its target")
        if self.revoked_at < self.published_at:
            raise ValueError("revoked_at precedes publication")
        return self


EnvelopePayload = Annotated[
    SignalPayload | SignalRevocationPayload,
    Field(discriminator="event_type"),
]


class SignedEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"
    key_id: str = "platform-v1"
    payload: EnvelopePayload
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")

    @staticmethod
    def canonical_payload(payload: SignalPayload | SignalRevocationPayload) -> bytes:
        data: Any = payload.model_dump(mode="json")
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def sign(
        cls,
        payload: SignalPayload | SignalRevocationPayload,
        secret: str,
        key_id: str = "platform-v1",
    ) -> "SignedEnvelope":
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("HMAC secret must contain at least 32 bytes")
        canonical = cls.canonical_payload(payload)
        checksum = hashlib.sha256(canonical).hexdigest()
        signature = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        return cls(payload=payload, checksum=checksum, signature=signature, key_id=key_id)

    def verify(self, secret: str) -> bool:
        canonical = self.canonical_payload(self.payload)
        checksum = hashlib.sha256(canonical).hexdigest()
        signature = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        return hmac.compare_digest(checksum, self.checksum) and hmac.compare_digest(
            signature, self.signature
        )


class ExecutionEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: Literal[
        "intent", "submitted", "open", "partial", "filled", "cancelled", "rejected", "closed", "status"
    ]
    occurred_at: datetime
    bot_id: str
    exchange: str
    pair: str | None = None
    trade_id: str | None = None
    order_id: str | None = None
    signal_id: UUID | None = None
    run_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
