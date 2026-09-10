from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLATFORM_", env_file=".env", extra="ignore")

    environment: str = "production"
    database_url: str = "postgresql://platform:platform@localhost:5432/platform"
    nats_url: str = "nats://localhost:4222"
    nats_consumer_url: str | None = None
    hmac_secret: str = Field(min_length=32)
    signal_ttl_seconds: int = Field(default=3600, ge=60)
    pair_map_path: Path = Path("config/pair_map.json")
    snapshot_dir: Path = Path("runtime/signals")
    artifact_dir: Path = Path("runtime/artifacts")
    bot_id: str = "freqtrade-primary"
    exchange: str = "binance"
    timeframe: str = "5m"
    outbox_poll_seconds: float = Field(default=1.0, ge=0.1)
    outbox_batch_size: int = Field(default=100, ge=1, le=100)
    outbox_claim_seconds: int = Field(default=600, ge=30, le=3600)
    bridge_ack_wait_seconds: int = Field(default=30, ge=5)
    bridge_max_deliveries: int = Field(default=10, ge=1)
    freqtrade_url: str = "http://localhost:8080"
    freqtrade_username: str = "freqtrader"
    freqtrade_password: str = ""
    audit_token: str = Field(min_length=16)
    llm_max_concurrency: int = Field(default=2, ge=1, le=20)
    analysis_lease_seconds: int = Field(default=900, ge=30, le=7200)
    analysis_lease_renew_seconds: int = Field(default=60, ge=5, le=600)
    analysis_schedule_seconds: int = Field(default=900, ge=60)
    market_collection_seconds: int = Field(default=60, ge=5)
    market_data_mode: str = "synthetic"
    max_clock_offset_ms: int = Field(default=2000, ge=0, le=60000)
    capture_deadline_seconds: int = Field(default=900, ge=60, le=7200)
    tradingagents_commit: str = "01477f9afb7a47b849ed4c9259d3a9a4738d9fda"
    capture_adapter_version: str = "1.0.0"
    clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    research_mode: str = "synthetic"
    producer_version: str = "0.3.1"
    code_revision: str = "unknown"
    llm_provider: str = "openai"
    deep_model: str = "configured-by-tradingagents"
    quick_model: str = "configured-by-tradingagents"

    @model_validator(mode="after")
    def validate_lease_timing(self) -> "Settings":
        if self.analysis_lease_renew_seconds * 2 >= self.analysis_lease_seconds:
            raise ValueError("analysis lease renewal must be less than half the lease duration")
        if self.outbox_claim_seconds < self.outbox_batch_size * 6:
            raise ValueError("outbox claim must cover the batch publish timeout budget")
        return self

    @property
    def consumer_nats_url(self) -> str:
        return self.nats_consumer_url or self.nats_url
