import json
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

import pytest

from trading_platform.research import run_tradingagents
from trading_platform.tradingagents_capture import (
    ISOLATED_ANALYSTS,
    TradingAgentsLifecycleIsolation,
    TradingAgentsCaptureAdapter,
    InvalidCapturedResponse,
    UpstreamDriftError,
    classify_captured_result,
    decode_normalized,
    encode_normalized,
    isolated_tradingagents_configuration,
)
from trading_platform import tradingagents_capture as capture_module
from trading_platform.capture import canonical_digest
from uuid import uuid4
from trading_platform.contracts import SourceCallOutcome


@pytest.mark.parametrize(
    "value",
    [
        "exact analyst input",
        b"raw bytes",
        {"prices": [1, 2.5], "available": True, "missing": None},
        ["one", {"two": 2}],
    ],
)
def test_normalized_codec_round_trip(value):
    encoded = encode_normalized(value)
    assert decode_normalized(encoded) == value
    assert json.loads(encoded)["type"] in {"str", "bytes", "json"}


def test_normalized_codec_rejects_lossy_types():
    with pytest.raises(TypeError, match="unsupported"):
        encode_normalized(object())


def test_normalized_codec_rejects_unknown_envelope():
    with pytest.raises(ValueError, match="unknown"):
        decode_normalized(b'{"type":"pickle","value":"unsafe"}')


@pytest.mark.parametrize(
    ("value", "outcome", "code"),
    [
        ("market data", SourceCallOutcome.AVAILABLE, None),
        ("NO_DATA_AVAILABLE: no rows", SourceCallOutcome.NO_DATA, "vendor_no_data"),
        (
            "DATA_UNAVAILABLE: optional macro_data could not be retrieved",
            SourceCallOutcome.UNAVAILABLE,
            "vendor_unavailable",
        ),
        (
            "Error fetching news: api_key=secret",
            SourceCallOutcome.INVALID_RESPONSE,
            "vendor_error_shaped_response",
        ),
    ],
)
def test_captured_result_classification_is_closed_and_typed(value, outcome, code):
    assert classify_captured_result(value) == (outcome, code)


@pytest.mark.parametrize(
    ("method", "value", "outcome"),
    [
        ("get_news", "No news found for BTC-USD", SourceCallOutcome.NO_DATA),
        (
            "fetch_stocktwits_messages",
            "<stocktwits unavailable: TimeoutError>",
            SourceCallOutcome.UNAVAILABLE,
        ),
        (
            "fetch_reddit_posts",
            "<no Reddit posts found mentioning BTC across r/stocks in the past 7 days>",
            SourceCallOutcome.NO_DATA,
        ),
        ("resolve_instrument_identity", {}, SourceCallOutcome.NO_DATA),
        ("get_news", {"feed": []}, SourceCallOutcome.NO_DATA),
        (
            "get_news",
            {"Information": "API rate limit details must not be stored"},
            SourceCallOutcome.INVALID_RESPONSE,
        ),
    ],
)
def test_method_specific_placeholders_are_not_available(method, value, outcome):
    assert classify_captured_result(value, method)[0] == outcome


def test_error_shaped_vendor_value_is_not_written_as_an_artifact(tmp_path):
    adapter = TradingAgentsCaptureAdapter("postgresql://unused", tmp_path, uuid4())
    adapter._allocate_ordinal = lambda: 0
    persisted = []
    adapter._persist_failure = lambda **values: (
        persisted.append(values) or SourceCallOutcome.INVALID_RESPONSE
    )
    now = datetime.now(timezone.utc)
    arguments = {"args": ["BTC-USD"], "kwargs": {}}
    context = capture_module._InvocationContext(
        invocation_id=uuid4(),
        ordinal=0,
        method="get_news",
        category="news",
        consumer="news_analyst",
        arguments=arguments,
        arguments_hash=canonical_digest(arguments),
        started_at=now,
        expected_vendor_chain=("yfinance",),
    )
    token = capture_module._INVOCATION_CONTEXT.set(context)
    try:
        with pytest.raises(InvalidCapturedResponse):
            adapter.capture_call(
                "get_news", "news", "yfinance",
                lambda *_args: "Error fetching news: api_key=do-not-store",
                ("BTC-USD",), {},
            )
    finally:
        capture_module._INVOCATION_CONTEXT.reset(token)
    assert len(persisted) == 1
    assert isinstance(persisted[0]["error"], InvalidCapturedResponse)
    assert not list(tmp_path.rglob("*"))


def test_news_hooks_keep_only_consumed_article_timestamps():
    now = datetime.now(timezone.utc)
    arguments = {"args": ["BTC-USD"], "kwargs": {}}
    context = capture_module._InvocationContext(
        invocation_id=uuid4(), ordinal=0, method="get_news", category="news",
        consumer="news_analyst", arguments=arguments,
        arguments_hash=canonical_digest(arguments), started_at=now,
    )
    extracted_at = datetime(2026, 8, 22, 10, tzinfo=timezone.utc)
    extract = TradingAgentsCaptureAdapter._news_extract_wrapper(
        lambda article: {"pub_date": article["published_at"]}
    )
    in_window = TradingAgentsCaptureAdapter._news_window_wrapper(
        lambda pub_date, start, end: start <= pub_date <= end
    )
    token = capture_module._INVOCATION_CONTEXT.set(context)
    try:
        data = extract({"published_at": extracted_at})
        assert in_window(
            data["pub_date"],
            datetime(2026, 8, 20, tzinfo=timezone.utc),
            datetime(2026, 8, 23, tzinfo=timezone.utc),
        )
    finally:
        capture_module._INVOCATION_CONTEXT.reset(token)
    assert context.hook_data["news_hook_observed"] is True
    assert context.hook_data["kept_news_times"] == [extracted_at]


class UnsafeMemory:
    def get_pending_entries(self):
        raise AssertionError("pending reflection memory was read")

    def get_past_context(self, ticker):
        raise AssertionError("past memory was read")

    def store_decision(self, **kwargs):
        raise AssertionError("decision memory was written")


class FakeGraph:
    def __init__(self, selected_analysts=(), debug=False, config=None):
        self.selected_analysts = tuple(selected_analysts)
        self.config = config
        self.memory_log = UnsafeMemory()

    def _resolve_pending_entries(self, ticker):
        raise AssertionError("reflection return fetch was invoked")

    def _log_state(self, trade_date, final_state):
        raise AssertionError("state log was written")


def test_isolated_configuration_is_fresh_and_does_not_mutate_input():
    original = {"checkpoint_enabled": True, "memory_log_path": "/mutable/memory.md"}
    isolated = isolated_tradingagents_configuration(original)
    assert original["checkpoint_enabled"] is True
    assert original["memory_log_path"] == "/mutable/memory.md"
    assert isolated["checkpoint_enabled"] is False
    assert isolated["memory_log_path"] is None
    assert isolated["platform_lifecycle_isolation"] == "1.0.0"


def test_lifecycle_isolation_blocks_reflection_memory_and_state_files(monkeypatch):
    monkeypatch.setattr(
        "trading_platform.tradingagents_capture.audit_pinned_upstream", lambda: None
    )
    graph = FakeGraph(
        selected_analysts=ISOLATED_ANALYSTS,
        config=isolated_tradingagents_configuration({}),
    )
    isolation = TradingAgentsLifecycleIsolation()
    isolation.install(graph)
    isolation.assert_installed(graph)
    graph._resolve_pending_entries("BTC-USD")
    graph._log_state("2026-08-23", {})
    assert graph.memory_log.get_pending_entries() == []
    assert graph.memory_log.get_past_context("BTC-USD") == ""
    assert graph.memory_log.store_decision("BTC-USD", "2026-08-23", "Hold") is None
    with pytest.raises(RuntimeError, match="disabled"):
        graph.memory_log.batch_update_with_outcomes([])


def test_lifecycle_isolation_rejects_fundamentals(monkeypatch):
    monkeypatch.setattr(
        "trading_platform.tradingagents_capture.audit_pinned_upstream", lambda: None
    )
    graph = FakeGraph(
        selected_analysts=("market", "social", "news", "fundamentals"),
        config=isolated_tradingagents_configuration({}),
    )
    with pytest.raises(UpstreamDriftError, match="analyst set"):
        TradingAgentsLifecycleIsolation().install(graph)


def test_run_tradingagents_installs_capture_and_lifecycle_before_propagate(monkeypatch):
    monkeypatch.setattr(
        "trading_platform.tradingagents_capture.audit_pinned_upstream", lambda: None
    )
    default_config = ModuleType("tradingagents.default_config")
    default_config.DEFAULT_CONFIG = {
        "checkpoint_enabled": True,
        "memory_log_path": "/mutable/memory.md",
    }
    graph_module = ModuleType("tradingagents.graph.trading_graph")

    class ExercisingGraph(FakeGraph):
        created = None

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            ExercisingGraph.created = self

        def propagate(self, symbol, trade_date, asset_type="stock"):
            self._resolve_pending_entries(symbol)
            assert self.memory_log.get_past_context(symbol) == ""
            self._log_state(trade_date, {"unsafe": "would have been written"})
            self.memory_log.store_decision(symbol, trade_date, "Hold")
            return {
                "final_trade_decision": (
                    "**Rating**: Hold\n"
                    "**Executive Summary**: Isolated lifecycle.\n"
                    "**Investment Thesis**: Infrastructure test."
                ),
                "sentiment_report": "",
            }, "HOLD"

    graph_module.TradingAgentsGraph = ExercisingGraph
    monkeypatch.setitem(sys.modules, "tradingagents", ModuleType("tradingagents"))
    monkeypatch.setitem(sys.modules, "tradingagents.default_config", default_config)
    monkeypatch.setitem(sys.modules, "tradingagents.graph", ModuleType("tradingagents.graph"))
    monkeypatch.setitem(sys.modules, "tradingagents.graph.trading_graph", graph_module)

    class CaptureProbe:
        installed = False
        checked = False
        uninstalled = False

        def install(self):
            self.installed = True

        def assert_complete_installation(self):
            self.checked = True

        def uninstall(self):
            self.uninstalled = True

    capture = CaptureProbe()
    result = run_tradingagents(
        "BTC-USD", "2026-08-23", SimpleNamespace(), capture_adapter=capture
    )
    assert capture.installed and capture.checked and capture.uninstalled
    assert ExercisingGraph.created.selected_analysts == ISOLATED_ANALYSTS
    assert ExercisingGraph.created.config["checkpoint_enabled"] is False
    assert ExercisingGraph.created.config["memory_log_path"] is None
    assert result.decision.rating.value == "Hold"
