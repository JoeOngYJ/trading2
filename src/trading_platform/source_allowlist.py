from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class IngressPolicyError(RuntimeError):
    """A stable fail-closed violation at the TradingAgents data boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AllowedIngress:
    category: str
    consumer: str
    vendors: tuple[str, ...]
    symbol_argument: bool = True


ALLOWED_INGRESS: dict[str, AllowedIngress] = {
    "resolve_instrument_identity": AllowedIngress(
        "research_market", "graph_preflight", ("yfinance_identity",)
    ),
    "get_stock_data": AllowedIngress(
        "research_market", "market_analyst", ("yfinance", "alpha_vantage")
    ),
    "get_indicators": AllowedIngress(
        "research_market", "market_analyst", ("yfinance", "alpha_vantage")
    ),
    "get_verified_market_snapshot": AllowedIngress(
        "research_market", "market_analyst", ("yfinance",)
    ),
    "get_news": AllowedIngress(
        "news", "news_analyst", ("yfinance", "alpha_vantage")
    ),
    "get_global_news": AllowedIngress(
        "news", "news_analyst", ("yfinance", "alpha_vantage"), symbol_argument=False
    ),
    "fetch_stocktwits_messages": AllowedIngress(
        "social", "social_analyst", ("stocktwits",)
    ),
    "fetch_reddit_posts": AllowedIngress(
        "social", "social_analyst", ("reddit",)
    ),
    "get_macro_indicators": AllowedIngress(
        "macro", "news_analyst", ("fred",), symbol_argument=False
    ),
    "get_prediction_markets": AllowedIngress(
        "prediction", "news_analyst", ("polymarket",), symbol_argument=False
    ),
}

FORBIDDEN_CRYPTO_METHODS = frozenset({
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_insider_transactions",
})

KNOWN_ROUTED_METHODS = frozenset(
    method for method in (*ALLOWED_INGRESS, *FORBIDDEN_CRYPTO_METHODS)
    if method not in {
        "resolve_instrument_identity", "get_verified_market_snapshot",
        "fetch_stocktwits_messages", "fetch_reddit_posts",
    }
)

CRYPTO_INSTRUMENTS = {
    "crypto:binance:spot:BTC-USDT": {
        "research_symbol": "BTC-USD",
        "execution_pair": "BTC/USDT",
        "base_asset": "BTC",
    },
    "crypto:binance:spot:ETH-USDT": {
        "research_symbol": "ETH-USD",
        "execution_pair": "ETH/USDT",
        "base_asset": "ETH",
    },
}


@dataclass(frozen=True)
class CryptoCaptureScope:
    instrument_id: str
    research_symbol: str
    execution_exchange: str
    execution_pair: str
    market_type: str
    enabled: bool
    vendor_plan: dict[str, tuple[str, ...]]


def normalize_vendor_plan(configured: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Validate the frozen per-method vendor plan stored in the manifest."""
    if set(configured) != set(ALLOWED_INGRESS):
        raise IngressPolicyError("ingress.vendor_plan_keys_invalid")
    normalized: dict[str, tuple[str, ...]] = {}
    for method, rule in ALLOWED_INGRESS.items():
        raw = configured[method]
        if isinstance(raw, str):
            chain = tuple(item.strip() for item in raw.split(",") if item.strip())
        elif isinstance(raw, (list, tuple)):
            chain = tuple(str(item).strip() for item in raw if str(item).strip())
        else:
            raise IngressPolicyError("ingress.vendor_chain_invalid")
        if not chain or len(set(chain)) != len(chain):
            raise IngressPolicyError("ingress.vendor_chain_invalid")
        if any(vendor not in rule.vendors for vendor in chain):
            raise IngressPolicyError("ingress.vendor_not_allowed")
        if len(rule.vendors) == 1 and chain != rule.vendors:
            raise IngressPolicyError("ingress.direct_vendor_mismatch")
        if len(rule.vendors) > 1 and chain != rule.vendors[:len(chain)]:
            raise IngressPolicyError("ingress.vendor_chain_order_invalid")
        normalized[method] = chain
    return normalized


def validate_crypto_scope(scope: CryptoCaptureScope) -> None:
    expected = CRYPTO_INSTRUMENTS.get(scope.instrument_id)
    if expected is None:
        raise IngressPolicyError("ingress.instrument_not_allowed")
    if not scope.enabled:
        raise IngressPolicyError("ingress.instrument_disabled")
    if (
        scope.research_symbol != expected["research_symbol"]
        or scope.execution_exchange != "binance"
        or scope.execution_pair != expected["execution_pair"]
        or scope.market_type != "spot"
    ):
        raise IngressPolicyError("ingress.instrument_identity_mismatch")
    normalize_vendor_plan(scope.vendor_plan)


def validate_semantic_ingress(
    scope: CryptoCaptureScope,
    *,
    method: str,
    category: str,
    consumer: str,
    arguments: dict[str, Any],
) -> tuple[str, ...]:
    if method in FORBIDDEN_CRYPTO_METHODS:
        raise IngressPolicyError("ingress.method_forbidden")
    rule = ALLOWED_INGRESS.get(method)
    if rule is None:
        raise IngressPolicyError("ingress.method_unknown")
    if category != rule.category:
        raise IngressPolicyError("ingress.category_mismatch")
    if consumer != rule.consumer:
        raise IngressPolicyError("ingress.consumer_mismatch")
    if rule.symbol_argument:
        args = arguments.get("args") or []
        if not args or str(args[0]).strip().upper() != scope.research_symbol:
            raise IngressPolicyError("ingress.research_symbol_mismatch")
    return normalize_vendor_plan(scope.vendor_plan)[method]


def validate_vendor_attempt(
    expected_chain: tuple[str, ...], vendor: str, fallback_ordinal: int
) -> None:
    if fallback_ordinal >= len(expected_chain):
        raise IngressPolicyError("ingress.fallback_chain_exhausted")
    if expected_chain[fallback_ordinal] != vendor:
        raise IngressPolicyError("ingress.fallback_order_mismatch")


def validate_completed_fallbacks(
    expected_chain: tuple[str, ...], attempts: list[tuple[str, str]], final_outcome: str
) -> None:
    if not attempts:
        raise IngressPolicyError("ingress.semantic_result_without_vendor_attempt")
    vendors = tuple(vendor for vendor, _ in attempts)
    if vendors != expected_chain[:len(vendors)]:
        raise IngressPolicyError("ingress.fallback_order_mismatch")
    available_positions = [
        position for position, (_, outcome) in enumerate(attempts) if outcome == "available"
    ]
    if available_positions and available_positions != [len(attempts) - 1]:
        raise IngressPolicyError("ingress.fallback_continued_after_success")
    if final_outcome == "available" and (
        not attempts or attempts[-1][1] != "available"
    ):
        raise IngressPolicyError("ingress.semantic_result_without_vendor_success")
    if final_outcome != "available" and available_positions:
        raise IngressPolicyError("ingress.semantic_result_conflicts_with_vendor_success")
    if final_outcome == "no_data" and not any(
        outcome == "no_data" for _, outcome in attempts
    ):
        raise IngressPolicyError("ingress.semantic_no_data_without_vendor_no_data")
