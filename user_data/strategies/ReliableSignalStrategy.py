# flake8: noqa
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pandas import DataFrame
from freqtrade.strategy import IStrategy


def _snapshot_name(pair: str, timeframe: str) -> str:
    safe = lambda value: re.sub(r"[^A-Za-z0-9_.-]", "_", value)
    return f"{safe(pair)}__{safe(timeframe)}.json"


class ReliableSignalStrategy(IStrategy):
    """Fail-closed infrastructure strategy.

    This reference strategy deliberately creates no entries. A real strategy may
    use ``llm_signal_ready`` and ``llm_rating_score`` but must retain the final
    confirm_trade_entry gate below.
    """

    INTERFACE_VERSION = 3
    timeframe = os.getenv("PLATFORM_TIMEFRAME", "5m")
    can_short = False
    process_only_new_candles = True
    minimal_roi = {"0": 100.0}
    stoploss = -0.10
    use_exit_signal = True

    signal_dir = Path(os.getenv("PLATFORM_SNAPSHOT_DIR", "/signals"))
    environment = os.getenv("PLATFORM_ENVIRONMENT", "production")
    bot_id = os.getenv("PLATFORM_BOT_ID", "freqtrade-primary")
    exchange_name = os.getenv("PLATFORM_EXCHANGE", "binance")
    secret = os.getenv("PLATFORM_HMAC_SECRET", "")
    bridge_health_max_age = int(os.getenv("PLATFORM_BRIDGE_HEALTH_MAX_AGE", "30"))

    _signals: dict[str, dict] = {}
    _bridge_healthy = False

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)

    def _verify(self, envelope: dict, now: datetime) -> bool:
        if len(self.secret.encode()) < 32:
            return False
        payload = envelope.get("payload", {})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        checksum = hashlib.sha256(canonical).hexdigest()
        signature = hmac.new(self.secret.encode(), canonical, hashlib.sha256).hexdigest()
        try:
            return (
                hmac.compare_digest(checksum, envelope["checksum"])
                and hmac.compare_digest(signature, envelope["signature"])
                and payload["schema_version"].split(".", 1)[0] == "2"
                and payload["event_type"] == "signal.created"
                and payload["status"] == "valid"
                and payload["environment"] == self.environment
                and payload["bot_id"] == self.bot_id
                and payload["exchange"] == self.exchange_name
                and payload["timeframe"] == self.timeframe
                and self._parse_time(payload["published_at"]) <= now
                and self._parse_time(payload["signal_available_at"]) <= now
                and self._parse_time(payload["provenance"]["data_as_of"]) <= now
                and now < self._parse_time(payload["expires_at"])
            )
        except (KeyError, TypeError, ValueError):
            return False

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        now = current_time.astimezone(timezone.utc)
        self._bridge_healthy = False
        try:
            health = json.loads((self.signal_dir / "bridge-health.json").read_text())
            observed = self._parse_time(str(health["observed_at"]))
            self._bridge_healthy = health.get("status") == "healthy" and (
                now - observed <= timedelta(seconds=self.bridge_health_max_age)
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            pass

        loaded: dict[str, dict] = {}
        if self._bridge_healthy:
            for pair in self.dp.current_whitelist():
                try:
                    envelope = json.loads(
                        (self.signal_dir / _snapshot_name(pair, self.timeframe)).read_text(encoding="utf-8")
                    )
                    if self._verify(envelope, now) and envelope["payload"]["pair"] == pair:
                        loaded[pair] = envelope
                except (OSError, ValueError, KeyError, json.JSONDecodeError):
                    continue
        self._signals = loaded

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        envelope = self._signals.get(metadata["pair"])
        payload = envelope["payload"] if envelope else {}
        dataframe["llm_signal_ready"] = bool(envelope and self._bridge_healthy)
        dataframe["llm_rating_score"] = float(payload.get("normalized_rating_score", 0.0))
        dataframe["llm_signal_id"] = str(payload.get("signal_id", ""))
        dataframe["llm_run_id"] = str(payload.get("run_id", ""))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Infrastructure reference: strategy decisions are intentionally out of scope.
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    def confirm_trade_entry(
        self, pair: str, order_type: str, amount: float, rate: float, time_in_force: str,
        current_time: datetime, entry_tag: str | None, side: str, **kwargs
    ) -> bool:
        envelope = self._signals.get(pair)
        if not self._bridge_healthy or not envelope or not self._verify(envelope, current_time):
            return False
        payload = envelope["payload"]
        rating = payload.get("decision", {}).get("rating")
        rating_allows_side = (
            side == "long" and rating == "Buy"
        ) or (
            side == "short" and self.can_short and rating == "Sell"
        )
        expected_tag = f"llm:{payload['signal_id']}"
        return rating_allows_side and entry_tag == expected_tag
