from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .contracts import PortfolioDecision, PortfolioRating, SentimentReport


@dataclass(frozen=True)
class ResearchResult:
    decision: PortfolioDecision
    sentiment: SentimentReport | None
    raw_state: dict[str, Any]
    configuration: dict[str, Any]
    report_path: str | None = None


def _section(markdown: str, heading: str, next_headings: tuple[str, ...]) -> str:
    start = re.search(rf"\*\*{re.escape(heading)}\*\*:\s*", markdown, re.IGNORECASE)
    if not start:
        raise ValueError(f"missing structured TradingAgents heading: {heading}")
    end = len(markdown)
    for next_heading in next_headings:
        match = re.search(rf"\n\s*\*\*{re.escape(next_heading)}\*\*:\s*", markdown[start.end():], re.IGNORECASE)
        if match:
            end = min(end, start.end() + match.start())
    return markdown[start.end():end].strip()


def parse_rendered_portfolio_decision(markdown: str) -> PortfolioDecision:
    """Compatibility adapter for upstream's rendered Pydantic output.

    TradingAgents validates a PortfolioDecision internally but its public propagate()
    API currently returns the deterministic Markdown renderer. This parser accepts
    only that exact schema-shaped rendering and immediately revalidates it.
    """
    rating = _section(markdown, "Rating", ("Executive Summary",)).splitlines()[0].strip()
    summary = _section(markdown, "Executive Summary", ("Investment Thesis",))
    thesis = _section(markdown, "Investment Thesis", ("Price Target", "Time Horizon"))
    price_text = None
    horizon = None
    try:
        price_text = _section(markdown, "Price Target", ("Time Horizon",)).splitlines()[0]
    except ValueError:
        pass
    try:
        horizon = _section(markdown, "Time Horizon", ()).splitlines()[0]
    except ValueError:
        pass
    price_target = float(price_text.replace(",", "").replace("$", "")) if price_text else None
    return PortfolioDecision(
        rating=PortfolioRating(rating),
        executive_summary=summary,
        investment_thesis=thesis,
        price_target=price_target,
        time_horizon=horizon,
    )


def parse_rendered_sentiment(markdown: str) -> SentimentReport | None:
    patterns = {
        "overall_band": r"\*\*Overall Sentiment\*\*:\s*(.+)",
        "overall_score": r"\*\*Sentiment Score\*\*:\s*([0-9.]+)",
        "confidence": r"\*\*Confidence\*\*:\s*(low|medium|high)",
    }
    values: dict[str, Any] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, markdown, re.IGNORECASE)
        if not match:
            return None
        values[key] = match.group(1).strip()
    values["overall_score"] = float(values["overall_score"])
    values["confidence"] = values["confidence"].lower()
    values["narrative"] = markdown
    return SentimentReport.model_validate(values)


def configuration_hash(configuration: dict[str, Any]) -> str:
    canonical = json.dumps(configuration, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_tradingagents_configuration(
    settings: Any, vendor_plan: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    from tradingagents.default_config import DEFAULT_CONFIG
    from .tradingagents_capture import isolated_tradingagents_configuration

    configuration = DEFAULT_CONFIG.copy()
    llm_provider = getattr(settings, "llm_provider", None)
    if llm_provider is not None:
        configuration["llm_provider"] = llm_provider
    deep_model = getattr(settings, "deep_model", "configured-by-tradingagents")
    quick_model = getattr(settings, "quick_model", "configured-by-tradingagents")
    if deep_model != "configured-by-tradingagents":
        configuration["deep_think_llm"] = deep_model
    if quick_model != "configured-by-tradingagents":
        configuration["quick_think_llm"] = quick_model
    configuration["tool_vendors"] = {
        method: ",".join(chain)
        for method, chain in vendor_plan.items()
        if method in {
            "get_stock_data", "get_indicators", "get_news", "get_global_news",
            "get_macro_indicators", "get_prediction_markets",
        }
    }
    return isolated_tradingagents_configuration(configuration)


def run_tradingagents(
    symbol: str,
    trade_date: str,
    settings: Any,
    capture_adapter: Any,
    configuration: dict[str, Any] | None = None,
) -> ResearchResult:
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except ImportError as exc:
        raise RuntimeError(
            "TradingAgents is not installed; use synthetic mode or build the worker image with it"
        ) from exc

    from .tradingagents_capture import (
        ISOLATED_ANALYSTS,
        TradingAgentsLifecycleIsolation,
        isolated_tradingagents_configuration,
    )

    configuration = configuration or build_tradingagents_configuration(settings, {})
    configuration = isolated_tradingagents_configuration(configuration)
    capture_adapter.install()
    try:
        graph = TradingAgentsGraph(
            selected_analysts=ISOLATED_ANALYSTS,
            debug=False,
            config=configuration,
        )
        lifecycle = TradingAgentsLifecycleIsolation()
        lifecycle.install(graph)
        capture_adapter.assert_complete_installation()
        lifecycle.assert_installed(graph)
        final_state, _ = graph.propagate(symbol, trade_date, asset_type="crypto")
    finally:
        capture_adapter.uninstall()
    decision = parse_rendered_portfolio_decision(final_state["final_trade_decision"])
    sentiment = parse_rendered_sentiment(final_state.get("sentiment_report", ""))
    return ResearchResult(
        decision=decision,
        sentiment=sentiment,
        raw_state={
            key: value
            for key, value in final_state.items()
            if key in ("market_report", "sentiment_report", "news_report", "fundamentals_report")
        },
        configuration=configuration,
    )


def synthetic_result(symbol: str) -> ResearchResult:
    configuration = {"mode": "synthetic", "symbol": symbol}
    return ResearchResult(
        decision=PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="Synthetic infrastructure test signal; no entry should be opened.",
            investment_thesis="This deterministic HOLD validates transport and audit behavior only.",
            time_horizon="infrastructure test",
        ),
        sentiment=SentimentReport(
            overall_band="Neutral",
            overall_score=5.0,
            confidence="low",
            narrative="Synthetic data with no market interpretation.",
        ),
        raw_state={"synthetic": True},
        configuration=configuration,
    )
