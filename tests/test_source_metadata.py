from datetime import datetime, timezone

from trading_platform.contracts import SourceCallOutcome
from trading_platform.source_metadata import build_source_temporal_metadata


SEEN = datetime(2026, 8, 23, 18, tzinfo=timezone.utc)


def test_stock_metadata_detects_current_daily_bar_as_open():
    result = """# Stock data for BTC-USD from 2026-08-22 to 2026-08-23
# Total records: 2

Date,Open,High,Low,Close,Volume
2026-08-22,1,2,1,2,10
2026-08-23,2,3,2,3,11
"""
    metadata = build_source_temporal_metadata(
        method="get_stock_data",
        arguments={"args": ["BTC-USDT", "2026-08-22", "2026-08-23"], "kwargs": {}},
        result=result,
        outcome=SourceCallOutcome.AVAILABLE,
        first_seen_at=SEEN,
    )
    assert metadata.resolved_symbol == "BTC-USD"
    assert metadata.item_count == 2
    assert metadata.latest_bar_close_at == datetime(2026, 8, 24, tzinfo=timezone.utc)
    assert metadata.market_bar_closed is False
    assert metadata.information_cutoff_at == metadata.latest_bar_close_at


def test_verified_snapshot_default_window_and_closed_bar():
    result = """## Verified market data snapshot for ETH-USD
- Requested analysis date: 2026-08-22
- Latest trading row used: 2026-08-22
"""
    metadata = build_source_temporal_metadata(
        method="get_verified_market_snapshot",
        arguments={"args": ["ETH-USD", "2026-08-22"], "kwargs": {}},
        result=result,
        outcome=SourceCallOutcome.AVAILABLE,
        first_seen_at=SEEN,
    )
    assert metadata.requested_start_at == datetime(2026, 7, 23, tzinfo=timezone.utc)
    assert metadata.market_bar_closed is True


def test_news_metadata_uses_only_kept_pre_render_article_times():
    first = datetime(2026, 8, 22, 9, tzinfo=timezone.utc)
    second = datetime(2026, 8, 23, 11, tzinfo=timezone.utc)
    metadata = build_source_temporal_metadata(
        method="get_news",
        arguments={"args": ["BTC-USD", "2026-08-20", "2026-08-23"], "kwargs": {}},
        result="rendered articles without timestamps",
        outcome=SourceCallOutcome.AVAILABLE,
        first_seen_at=SEEN,
        hook_data={
            "news_hook_observed": True,
            "kept_news_count": 2,
            "kept_news_times": [second, first],
        },
    )
    assert metadata.item_count == 2
    assert metadata.timestamps_complete is True
    assert metadata.earliest_item_at == first
    assert metadata.information_cutoff_at == second


def test_missing_news_timestamp_is_explicitly_incomplete():
    metadata = build_source_temporal_metadata(
        method="get_news",
        arguments={"args": ["BTC-USD", "2026-08-20", "2026-08-23"], "kwargs": {}},
        result="one dated and one undated article",
        outcome=SourceCallOutcome.AVAILABLE,
        first_seen_at=SEEN,
        hook_data={
            "news_hook_observed": True,
            "kept_news_count": 2,
            "kept_news_times": [datetime(2026, 8, 22, tzinfo=timezone.utc)],
        },
    )
    assert metadata.timestamps_complete is False
    assert metadata.quality_flags == ["news_timestamp_missing"]


def test_alpha_vantage_news_uses_structured_publication_times():
    metadata = build_source_temporal_metadata(
        method="get_news",
        arguments={"args": ["BTC", "2026-08-20", "2026-08-23"], "kwargs": {}},
        result={
            "feed": [
                {"title": "one", "time_published": "20260822T090000"},
                {"title": "two", "time_published": "20260823T103000"},
            ]
        },
        outcome=SourceCallOutcome.AVAILABLE,
        first_seen_at=SEEN,
    )
    assert metadata.item_count == 2
    assert metadata.timestamps_complete is True
    assert metadata.latest_item_at == datetime(2026, 8, 23, 10, 30, tzinfo=timezone.utc)


def test_stocktwits_metadata_parses_pinned_iso_timestamps():
    result = """Bullish: 1 (50%) · Bearish: 1 (50%) · Unlabeled: 0 · Total: 2 most-recent messages

[2026-08-23T10:00:00Z · @one · Bullish] first
[2026-08-23T12:30:00+00:00 · @two · Bearish] second
"""
    metadata = build_source_temporal_metadata(
        method="fetch_stocktwits_messages",
        arguments={"args": ["BTC-USD"], "kwargs": {"limit": 30}},
        result=result,
        outcome=SourceCallOutcome.AVAILABLE,
        first_seen_at=SEEN,
    )
    assert metadata.item_count == 2
    assert metadata.timestamps_complete is True
    assert metadata.latest_item_at == datetime(2026, 8, 23, 12, 30, tzinfo=timezone.utc)


def test_reddit_metadata_preserves_structured_pre_render_times():
    created = datetime(2026, 8, 23, 8, tzinfo=timezone.utc)
    metadata = build_source_temporal_metadata(
        method="fetch_reddit_posts",
        arguments={"args": ["BTC-USD"], "kwargs": {}},
        result="rendered reddit posts contain only dates",
        outcome=SourceCallOutcome.AVAILABLE,
        first_seen_at=SEEN,
        hook_data={
            "reddit_hook_observed": True,
            "reddit_item_count": 2,
            "reddit_created_times": [created, None],
        },
    )
    assert metadata.item_count == 2
    assert metadata.timestamps_complete is False
    assert metadata.latest_item_at == created
    assert metadata.resolved_symbol == "BTC"


def test_no_data_has_no_information_cutoff():
    metadata = build_source_temporal_metadata(
        method="get_news",
        arguments={"args": ["BTC-USD", "2026-08-20", "2026-08-23"], "kwargs": {}},
        result="No news found for BTC-USD",
        outcome=SourceCallOutcome.NO_DATA,
        first_seen_at=SEEN,
    )
    assert metadata.item_count == 0
    assert metadata.source_time_basis == "none"
    assert metadata.information_cutoff_at is None
