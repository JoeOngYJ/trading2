from __future__ import annotations

import csv
import re
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO
from typing import Any

from .contracts import SourceCallOutcome, SourceTemporalMetadata


_DATE_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s|:|,|$)")
_SNAPSHOT_LATEST = re.compile(r"^- Latest trading row used:\s*(\d{4}-\d{2}-\d{2})\s*$")
_STOCKTWITS_TIME = re.compile(r"^\[([^·\]]+)\s*·")


def _utc_day(value: str) -> datetime:
    parsed = date.fromisoformat(value)
    return datetime.combine(parsed, time.min, tzinfo=timezone.utc)


def _requested_symbol(method: str, arguments: dict[str, Any]) -> str | None:
    args = arguments.get("args") or []
    if not args or method in ("get_global_news", "get_macro_indicators", "get_prediction_markets"):
        return None
    return str(args[0]).strip().upper() or None


def _crypto_base(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    compact = symbol.replace("-", "")
    for quote in ("USDT", "USDC", "USD"):
        if compact.endswith(quote) and compact[:-len(quote)] in {"BTC", "ETH"}:
            return compact[:-len(quote)]
    return None


def _resolved_symbol(method: str, symbol: str | None) -> str | None:
    base = _crypto_base(symbol)
    if method == "fetch_stocktwits_messages" and base:
        return f"{base}.X"
    if method == "fetch_reddit_posts" and base:
        return base
    if base:
        return f"{base}-USD"
    return symbol


def _window(method: str, arguments: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    args = arguments.get("args") or []
    try:
        if method in ("get_stock_data", "get_news") and len(args) >= 3:
            return _utc_day(str(args[1])), _utc_day(str(args[2])) + timedelta(days=1)
        if method == "get_indicators" and len(args) >= 4:
            end = _utc_day(str(args[2]))
            lookback = int(args[3])
            return end - timedelta(days=lookback), end + timedelta(days=1)
        if method == "get_verified_market_snapshot" and len(args) >= 2:
            end = _utc_day(str(args[1]))
            lookback = int(args[2]) if len(args) >= 3 else 30
            return end - timedelta(days=lookback), end + timedelta(days=1)
        if method == "get_global_news" and args:
            end = _utc_day(str(args[0]))
            lookback = int(args[1]) if len(args) > 1 and args[1] is not None else None
            return (end - timedelta(days=lookback), end + timedelta(days=1)) if lookback else (None, end + timedelta(days=1))
    except (TypeError, ValueError):
        return None, None
    return None, None


def _daily_dates(method: str, result: Any) -> list[datetime]:
    if not isinstance(result, str):
        return []
    dates: list[datetime] = []
    if method == "get_stock_data":
        lines = [line for line in result.splitlines() if line and not line.startswith("#")]
        if lines:
            rows = list(csv.reader(StringIO("\n".join(lines))))
            for row in rows[1:]:
                if row:
                    match = _DATE_LINE.match(row[0])
                    if match:
                        dates.append(_utc_day(match.group(1)))
    elif method == "get_indicators":
        for line in result.splitlines():
            match = _DATE_LINE.match(line)
            if match and "N/A:" not in line:
                dates.append(_utc_day(match.group(1)))
    elif method == "get_verified_market_snapshot":
        for line in result.splitlines():
            match = _SNAPSHOT_LATEST.match(line)
            if match:
                dates.append(_utc_day(match.group(1)))
                break
    return sorted(set(dates))


def _stocktwits_dates(result: Any) -> tuple[list[datetime], bool]:
    if not isinstance(result, str):
        return [], False
    timestamps: list[datetime] = []
    message_lines = 0
    for line in result.splitlines():
        match = _STOCKTWITS_TIME.match(line)
        if not match:
            continue
        message_lines += 1
        try:
            parsed = datetime.fromisoformat(match.group(1).strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            timestamps.append(parsed.astimezone(timezone.utc))
    return timestamps, message_lines > 0 and message_lines == len(timestamps)


def _alpha_vantage_news_dates(result: Any) -> tuple[list[datetime], int] | None:
    if not isinstance(result, dict) or not isinstance(result.get("feed"), list):
        return None
    values: list[datetime] = []
    feed = result["feed"]
    for article in feed:
        raw = article.get("time_published") if isinstance(article, dict) else None
        try:
            values.append(datetime.strptime(str(raw), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc))
        except (TypeError, ValueError):
            continue
    return values, len(feed)


def build_source_temporal_metadata(
    *,
    method: str,
    arguments: dict[str, Any],
    result: Any,
    outcome: SourceCallOutcome,
    first_seen_at: datetime,
    hook_data: dict[str, Any] | None = None,
) -> SourceTemporalMetadata:
    """Build metadata from pinned source shapes and pre-render source hooks."""
    hook_data = hook_data or {}
    requested_symbol = _requested_symbol(method, arguments)
    requested_start_at, requested_end_at = _window(method, arguments)
    common: dict[str, Any] = {
        "result_kind": outcome,
        "requested_symbol": requested_symbol,
        "resolved_symbol": _resolved_symbol(method, requested_symbol),
        "requested_start_at": requested_start_at,
        "requested_end_at": requested_end_at,
    }
    if outcome != SourceCallOutcome.AVAILABLE:
        return SourceTemporalMetadata(
            **common, item_count=0, timestamps_complete=True,
            source_time_basis="none", information_cutoff_at=None,
        )

    daily_dates = _daily_dates(method, result)
    if daily_dates:
        latest_bar = daily_dates[-1]
        latest_close = latest_bar + timedelta(days=1)
        return SourceTemporalMetadata(
            **common,
            earliest_item_at=daily_dates[0], latest_item_at=latest_bar,
            latest_bar_at=latest_bar, latest_bar_close_at=latest_close,
            market_bar_closed=latest_close <= first_seen_at,
            item_count=len(daily_dates), timestamps_complete=True,
            source_time_basis="daily_bar_close", information_cutoff_at=latest_close,
        )

    if method in ("get_news", "get_global_news"):
        alpha_news = _alpha_vantage_news_dates(result)
        if alpha_news is not None:
            values, count = alpha_news
            values.sort()
            complete = count > 0 and count == len(values)
            return SourceTemporalMetadata(
                **common, earliest_item_at=values[0] if values else None,
                latest_item_at=values[-1] if values else None, item_count=count,
                timestamps_complete=complete, source_time_basis="published_at",
                information_cutoff_at=values[-1] if values else None,
                quality_flags=[] if complete else ["news_timestamp_missing"],
            )
        values = sorted(hook_data.get("kept_news_times", []))
        kept_count = int(hook_data.get("kept_news_count", 0))
        hook_observed = bool(hook_data.get("news_hook_observed", False))
        complete = hook_observed and kept_count > 0 and kept_count == len(values)
        return SourceTemporalMetadata(
            **common, earliest_item_at=values[0] if values else None,
            latest_item_at=values[-1] if values else None, item_count=kept_count,
            timestamps_complete=complete, source_time_basis="published_at",
            information_cutoff_at=values[-1] if values else None,
            quality_flags=[] if complete else [
                "news_timestamp_missing" if hook_observed else "temporal_metadata_hook_missing"
            ],
        )

    if method == "fetch_stocktwits_messages":
        values, complete = _stocktwits_dates(result)
        return SourceTemporalMetadata(
            **common, earliest_item_at=min(values) if values else None,
            latest_item_at=max(values) if values else None, item_count=len(values),
            timestamps_complete=complete, source_time_basis="created_at",
            information_cutoff_at=max(values) if values else None,
            quality_flags=[] if complete else ["social_timestamp_missing"],
        )

    if method == "fetch_reddit_posts":
        raw_times = hook_data.get("reddit_created_times", [])
        values = sorted(value for value in raw_times if value is not None)
        count = int(hook_data.get("reddit_item_count", 0))
        hook_observed = bool(hook_data.get("reddit_hook_observed", False))
        complete = hook_observed and count > 0 and count == len(values)
        return SourceTemporalMetadata(
            **common, earliest_item_at=values[0] if values else None,
            latest_item_at=values[-1] if values else None, item_count=count,
            timestamps_complete=complete, source_time_basis="created_at",
            information_cutoff_at=values[-1] if values else None,
            quality_flags=[] if complete else [
                "social_timestamp_missing" if hook_observed else "temporal_metadata_hook_missing"
            ],
        )

    if method == "resolve_instrument_identity":
        return SourceTemporalMetadata(
            **common, item_count=1, timestamps_complete=True,
            source_time_basis="retrieved_at", information_cutoff_at=first_seen_at,
        )

    return SourceTemporalMetadata(
        **common, item_count=1, timestamps_complete=False,
        source_time_basis="retrieved_at", information_cutoff_at=first_seen_at,
        quality_flags=["temporal_metadata_incomplete"],
    )
