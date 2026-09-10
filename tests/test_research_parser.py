import pytest

from trading_platform.contracts import PortfolioRating
from trading_platform.research import parse_rendered_portfolio_decision


def test_upstream_structured_render_is_revalidated():
    rendered = """**Rating**: Overweight

**Executive Summary**: Enter cautiously after confirmation.

**Investment Thesis**: Evidence is constructive but risk remains.

**Price Target**: 125.5

**Time Horizon**: 3-6 months"""
    parsed = parse_rendered_portfolio_decision(rendered)
    assert parsed.rating is PortfolioRating.OVERWEIGHT
    assert parsed.price_target == 125.5


def test_free_form_llm_output_is_rejected():
    with pytest.raises(ValueError, match="missing structured"):
        parse_rendered_portfolio_decision("I think this might be a buy.")
