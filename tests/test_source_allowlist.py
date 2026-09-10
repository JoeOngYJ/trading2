import pytest

from trading_platform.source_allowlist import (
    ALLOWED_INGRESS,
    CryptoCaptureScope,
    IngressPolicyError,
    normalize_vendor_plan,
    validate_completed_fallbacks,
    validate_crypto_scope,
    validate_semantic_ingress,
    validate_vendor_attempt,
)


def vendor_plan():
    return {method: list(rule.vendors) for method, rule in ALLOWED_INGRESS.items()}


def scope(**changes):
    values = {
        "instrument_id": "crypto:binance:spot:BTC-USDT",
        "research_symbol": "BTC-USD",
        "execution_exchange": "binance",
        "execution_pair": "BTC/USDT",
        "market_type": "spot",
        "enabled": True,
        "vendor_plan": vendor_plan(),
    }
    values.update(changes)
    return CryptoCaptureScope(**values)


def assert_policy_error(code, function, *args, **kwargs):
    with pytest.raises(IngressPolicyError) as caught:
        function(*args, **kwargs)
    assert caught.value.code == code


def test_vendor_plan_is_complete_ordered_and_normalized():
    plan = vendor_plan()
    plan["get_stock_data"] = "yfinance, alpha_vantage"
    normalized = normalize_vendor_plan(plan)
    assert normalized["get_stock_data"] == ("yfinance", "alpha_vantage")
    assert set(normalized) == set(ALLOWED_INGRESS)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda plan: plan.pop("get_news"), "ingress.vendor_plan_keys_invalid"),
        (lambda plan: plan.update({"unknown": ["vendor"]}), "ingress.vendor_plan_keys_invalid"),
        (lambda plan: plan.update({"get_news": []}), "ingress.vendor_chain_invalid"),
        (lambda plan: plan.update({"get_news": ["reddit"]}), "ingress.vendor_not_allowed"),
        (
            lambda plan: plan.update({"get_news": ["alpha_vantage", "yfinance"]}),
            "ingress.vendor_chain_order_invalid",
        ),
        (
            lambda plan: plan.update({"fetch_reddit_posts": ["stocktwits"]}),
            "ingress.vendor_not_allowed",
        ),
    ],
)
def test_vendor_plan_rejects_unfrozen_or_unapproved_routes(mutate, code):
    plan = vendor_plan()
    mutate(plan)
    assert_policy_error(code, normalize_vendor_plan, plan)


def test_scope_accepts_only_exact_enabled_btc_or_eth_binance_spot_identity():
    validate_crypto_scope(scope())
    validate_crypto_scope(
        scope(
            instrument_id="crypto:binance:spot:ETH-USDT",
            research_symbol="ETH-USD",
            execution_pair="ETH/USDT",
        )
    )
    assert_policy_error(
        "ingress.instrument_not_allowed",
        validate_crypto_scope,
        scope(instrument_id="crypto:binance:spot:SOL-USDT"),
    )
    assert_policy_error(
        "ingress.instrument_disabled", validate_crypto_scope, scope(enabled=False)
    )
    assert_policy_error(
        "ingress.instrument_identity_mismatch",
        validate_crypto_scope,
        scope(execution_pair="BTC/USD"),
    )


def test_semantic_ingress_binds_method_category_consumer_symbol_and_chain():
    chain = validate_semantic_ingress(
        scope(), method="get_stock_data", category="research_market",
        consumer="market_analyst", arguments={"args": ["BTC-USD"], "kwargs": {}},
    )
    assert chain == ("yfinance", "alpha_vantage")
    assert_policy_error(
        "ingress.research_symbol_mismatch", validate_semantic_ingress, scope(),
        method="get_stock_data", category="research_market", consumer="market_analyst",
        arguments={"args": ["BTC-USDT"], "kwargs": {}},
    )
    assert_policy_error(
        "ingress.category_mismatch", validate_semantic_ingress, scope(),
        method="get_news", category="social", consumer="news_analyst",
        arguments={"args": ["BTC-USD"], "kwargs": {}},
    )
    assert_policy_error(
        "ingress.consumer_mismatch", validate_semantic_ingress, scope(),
        method="get_news", category="news", consumer="market_analyst",
        arguments={"args": ["BTC-USD"], "kwargs": {}},
    )


def test_semantic_ingress_forbids_fundamentals_and_unknown_methods():
    for method, code in (
        ("get_fundamentals", "ingress.method_forbidden"),
        ("surprise_tool", "ingress.method_unknown"),
    ):
        assert_policy_error(
            code, validate_semantic_ingress, scope(), method=method,
            category="fundamental", consumer="fundamentals_analyst",
            arguments={"args": ["BTC-USD"], "kwargs": {}},
        )


def test_fallback_attempts_must_follow_frozen_order():
    chain = ("yfinance", "alpha_vantage")
    validate_vendor_attempt(chain, "yfinance", 0)
    validate_vendor_attempt(chain, "alpha_vantage", 1)
    assert_policy_error(
        "ingress.fallback_order_mismatch",
        validate_vendor_attempt, chain, "alpha_vantage", 0,
    )
    assert_policy_error(
        "ingress.fallback_chain_exhausted",
        validate_vendor_attempt, chain, "alpha_vantage", 2,
    )


def test_completed_fallbacks_match_the_semantic_result():
    chain = ("yfinance", "alpha_vantage")
    validate_completed_fallbacks(
        chain, [("yfinance", "rate_limited"), ("alpha_vantage", "available")],
        "available",
    )
    assert_policy_error(
        "ingress.semantic_result_without_vendor_attempt", validate_completed_fallbacks,
        chain, [], "no_data",
    )
    assert_policy_error(
        "ingress.fallback_continued_after_success", validate_completed_fallbacks,
        chain, [("yfinance", "available"), ("alpha_vantage", "available")], "available",
    )
    assert_policy_error(
        "ingress.semantic_result_without_vendor_success", validate_completed_fallbacks,
        chain, [("yfinance", "no_data")], "available",
    )
    assert_policy_error(
        "ingress.semantic_no_data_without_vendor_no_data", validate_completed_fallbacks,
        chain, [("yfinance", "rate_limited")], "no_data",
    )
    assert_policy_error(
        "ingress.semantic_result_conflicts_with_vendor_success",
        validate_completed_fallbacks, chain, [("yfinance", "available")], "no_data",
    )
