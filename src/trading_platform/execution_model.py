"""Deterministic retail execution and transaction-cost simulation.

The model deliberately separates candle-resolution assumptions from quote/L2 replay.
It is a research component: it never sends an order or requires exchange credentials.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


BPS = Decimal("10000")
ZERO = Decimal("0")


def decimal(value: Decimal | str | int | float) -> Decimal:
    """Convert configuration/market values without binary-float arithmetic."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderKind(str, Enum):
    MARKETABLE_LIMIT = "marketable_limit"
    POST_ONLY = "post_only"
    PROTECTIVE = "protective"


class OrderStatus(str, Enum):
    CREATED = "created"
    REJECTED = "rejected"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    UNKNOWN = "unknown"
    RECONCILED = "reconciled"


@dataclass(frozen=True)
class SubmitDisposition:
    status: OrderStatus
    action: str
    reason: str


def classify_submit_response(
    http_status: int | None,
    exchange_error_code: int | None = None,
    transport_timeout: bool = False,
) -> SubmitDisposition:
    """Classify submit outcomes without converting ambiguity into duplicate orders."""
    if transport_timeout or http_status is None or 500 <= http_status <= 599:
        return SubmitDisposition(OrderStatus.UNKNOWN, "reconcile_by_client_order_id", "execution_status_unknown")
    if http_status in {418, 429}:
        return SubmitDisposition(OrderStatus.REJECTED, "disable_entries_and_backoff", "rate_limited")
    if exchange_error_code == -1021:
        return SubmitDisposition(OrderStatus.REJECTED, "resync_clock_before_new_entry", "timestamp_outside_recv_window")
    if 400 <= http_status <= 499 or exchange_error_code is not None:
        return SubmitDisposition(OrderStatus.REJECTED, "do_not_retry_without_correction", "exchange_rejected")
    if 200 <= http_status <= 299:
        return SubmitDisposition(OrderStatus.ACKNOWLEDGED, "track_until_terminal", "accepted")
    return SubmitDisposition(OrderStatus.UNKNOWN, "reconcile_by_client_order_id", "unclassified_response")


def resolve_long_exit_in_candle(
    candle_open: Decimal,
    candle_high: Decimal,
    candle_low: Decimal,
    stop_price: Decimal | None = None,
    target_price: Decimal | None = None,
) -> tuple[str, Decimal] | None:
    """Resolve OHLC ambiguity conservatively: gaps first, then stop before target."""
    candle_open, candle_high, candle_low = map(decimal, (candle_open, candle_high, candle_low))
    stop = decimal(stop_price) if stop_price is not None else None
    target = decimal(target_price) if target_price is not None else None
    if not (candle_low <= candle_open <= candle_high):
        raise ValueError("invalid candle bounds")
    if stop is not None and candle_open <= stop:
        return "stop_gap", candle_open
    if target is not None and candle_open >= target:
        return "target_gap", candle_open
    stop_hit = stop is not None and candle_low <= stop
    target_hit = target is not None and candle_high >= target
    if stop_hit:
        return "stop", stop
    if target_hit:
        return "target", target
    return None


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return _canonical(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"))


def canonical_data(value: Any) -> Any:
    """Return JSON-compatible canonical data for manifests and adapters."""
    return _canonical(value)


def sha256_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionScenario:
    scenario_id: str
    mode: str
    taker_fee_bps: Decimal
    maker_fee_bps: Decimal
    implicit_cost_bps_per_side: Decimal = ZERO
    residual_impact_bps: Decimal = ZERO
    latency_ms: int = 250
    price_protection_bps: Decimal = Decimal("10")
    maker_timeout_ms: int = 60_000
    cancel_latency_ms: int = 250
    maker_taker_fallback: bool = False
    commission_asset: str = "quote"
    schema_version: str = "retail-execution-scenario-v1"
    promotion_eligible: bool = True

    def __post_init__(self) -> None:
        if self.mode not in {"candle_taker", "book_taker", "maker_hybrid"}:
            raise ValueError(f"unsupported execution mode: {self.mode}")
        for name in (
            "taker_fee_bps", "maker_fee_bps", "implicit_cost_bps_per_side",
            "residual_impact_bps", "price_protection_bps",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.latency_ms < 0 or self.maker_timeout_ms <= 0 or self.cancel_latency_ms < 0:
            raise ValueError("latencies must be non-negative and maker timeout positive")
        if self.commission_asset not in {"quote", "base", "third"}:
            raise ValueError("commission_asset must be quote, base, or third")

    @property
    def checksum(self) -> str:
        return sha256_digest(self)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ExecutionScenario":
        values = dict(raw)
        for key in (
            "taker_fee_bps", "maker_fee_bps", "implicit_cost_bps_per_side",
            "residual_impact_bps", "price_protection_bps",
        ):
            values[key] = decimal(values.get(key, 0))
        return cls(**values)


@dataclass(frozen=True)
class BinanceCommissionRates:
    """Account/symbol commission response retained without assuming a headline rate."""

    standard_maker: Decimal
    standard_taker: Decimal
    standard_buyer: Decimal = ZERO
    standard_seller: Decimal = ZERO
    special_maker: Decimal = ZERO
    special_taker: Decimal = ZERO
    special_buyer: Decimal = ZERO
    special_seller: Decimal = ZERO
    tax_maker: Decimal = ZERO
    tax_taker: Decimal = ZERO
    tax_buyer: Decimal = ZERO
    tax_seller: Decimal = ZERO
    discount_enabled_for_account: bool = False
    discount_enabled_for_symbol: bool = False
    discount_asset: str | None = None
    discount_fraction: Decimal = ZERO

    @classmethod
    def from_binance_response(cls, payload: Mapping[str, Any]) -> "BinanceCommissionRates":
        def group(*names: str) -> Mapping[str, Any]:
            for name in names:
                candidate = payload.get(name)
                if isinstance(candidate, Mapping):
                    return candidate
            return {}

        standard = group("standardCommission", "standardCommissionForOrder")
        special = group("specialCommission", "specialCommissionForOrder")
        tax = group("taxCommission", "taxCommissionForOrder")
        discount = group("discount")
        if "maker" not in standard or "taker" not in standard:
            raise ValueError("commission response lacks standard maker/taker rates")

        def rate(source: Mapping[str, Any], name: str) -> Decimal:
            return decimal(source.get(name, 0))

        return cls(
            standard_maker=rate(standard, "maker"),
            standard_taker=rate(standard, "taker"),
            standard_buyer=rate(standard, "buyer"),
            standard_seller=rate(standard, "seller"),
            special_maker=rate(special, "maker"),
            special_taker=rate(special, "taker"),
            special_buyer=rate(special, "buyer"),
            special_seller=rate(special, "seller"),
            tax_maker=rate(tax, "maker"),
            tax_taker=rate(tax, "taker"),
            tax_buyer=rate(tax, "buyer"),
            tax_seller=rate(tax, "seller"),
            discount_enabled_for_account=bool(discount.get("enabledForAccount", False)),
            discount_enabled_for_symbol=bool(discount.get("enabledForSymbol", False)),
            discount_asset=discount.get("discountAsset"),
            discount_fraction=rate(discount, "discount"),
        )

    def effective_bps(self, liquidity: str, side: Side, use_discount: bool = False) -> Decimal:
        if liquidity not in {"maker", "taker"}:
            raise ValueError("liquidity must be maker or taker")
        side_name = "buyer" if side is Side.BUY else "seller"
        standard = getattr(self, f"standard_{liquidity}") + getattr(self, f"standard_{side_name}")
        if use_discount and self.discount_enabled_for_account and self.discount_enabled_for_symbol:
            standard *= Decimal("1") - self.discount_fraction
        special = getattr(self, f"special_{liquidity}") + getattr(self, f"special_{side_name}")
        tax = getattr(self, f"tax_{liquidity}") + getattr(self, f"tax_{side_name}")
        return (standard + special + tax) * BPS


def load_scenarios(path: Path) -> dict[str, ExecutionScenario]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "retail-execution-scenarios-v1":
        raise ValueError("unsupported execution scenario file")
    scenarios = {
        raw["scenario_id"]: ExecutionScenario.from_mapping(raw)
        for raw in payload.get("scenarios", [])
    }
    if len(scenarios) != len(payload.get("scenarios", [])) or not scenarios:
        raise ValueError("execution scenario IDs must be unique and non-empty")
    return scenarios


@dataclass(frozen=True)
class MarketRules:
    symbol: str
    effective_at: str
    tick_size: Decimal
    step_size: Decimal
    min_price: Decimal = ZERO
    max_price: Decimal = ZERO
    min_quantity: Decimal = ZERO
    max_quantity: Decimal = ZERO
    min_notional: Decimal = ZERO
    max_notional: Decimal = ZERO
    bid_multiplier_up: Decimal = ZERO
    bid_multiplier_down: Decimal = ZERO
    ask_multiplier_up: Decimal = ZERO
    ask_multiplier_down: Decimal = ZERO
    source: str = "frozen_fixture"
    schema_version: str = "market-rules-v1"

    def __post_init__(self) -> None:
        if not self.symbol or self.tick_size <= 0 or self.step_size <= 0:
            raise ValueError("symbol, positive tick_size, and positive step_size are required")

    @property
    def checksum(self) -> str:
        return sha256_digest(self)

    def round_price(self, value: Decimal, side: Side) -> Decimal:
        units = value / self.tick_size
        rounding = ROUND_FLOOR if side is Side.BUY else ROUND_CEILING
        return units.to_integral_value(rounding=rounding) * self.tick_size

    def round_quantity(self, value: Decimal) -> Decimal:
        return (value / self.step_size).to_integral_value(rounding=ROUND_FLOOR) * self.step_size

    def validate(
        self,
        quantity: Decimal,
        price: Decimal,
        reference_price: Decimal | None = None,
        side: Side = Side.BUY,
    ) -> str | None:
        if quantity <= 0:
            return "quantity_non_positive_after_rounding"
        if self.min_quantity and quantity < self.min_quantity:
            return "min_quantity"
        if self.max_quantity and quantity > self.max_quantity:
            return "max_quantity"
        if self.min_price and price < self.min_price:
            return "min_price"
        if self.max_price and price > self.max_price:
            return "max_price"
        notional = quantity * price
        if self.min_notional and notional < self.min_notional:
            return "min_notional"
        if self.max_notional and notional > self.max_notional:
            return "max_notional"
        if reference_price:
            multiplier_up = self.bid_multiplier_up if side is Side.BUY else self.ask_multiplier_up
            multiplier_down = self.bid_multiplier_down if side is Side.BUY else self.ask_multiplier_down
            if multiplier_up and price > reference_price * multiplier_up:
                return "percent_price_high"
            if multiplier_down and price < reference_price * multiplier_down:
                return "percent_price_low"
        return None

    @classmethod
    def from_binance_exchange_info(
        cls, payload: Mapping[str, Any], symbol: str, effective_at: str
    ) -> "MarketRules":
        symbols = payload.get("symbols", [])
        record = next((item for item in symbols if item.get("symbol") == symbol), None)
        if record is None:
            raise ValueError(f"symbol missing from exchangeInfo: {symbol}")
        filters = {item["filterType"]: item for item in record.get("filters", [])}
        price = filters.get("PRICE_FILTER", {})
        lot = filters.get("LOT_SIZE", {})
        notional = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
        percent = filters.get("PERCENT_PRICE_BY_SIDE", filters.get("PERCENT_PRICE", {}))
        if "tickSize" not in price or "stepSize" not in lot:
            raise ValueError("exchangeInfo lacks PRICE_FILTER or LOT_SIZE")

        common_up = percent.get("multiplierUp", "0")
        common_down = percent.get("multiplierDown", "0")
        return cls(
            symbol=symbol,
            effective_at=effective_at,
            tick_size=decimal(price["tickSize"]),
            step_size=decimal(lot["stepSize"]),
            min_price=decimal(price.get("minPrice", 0)),
            max_price=decimal(price.get("maxPrice", 0)),
            min_quantity=decimal(lot.get("minQty", 0)),
            max_quantity=decimal(lot.get("maxQty", 0)),
            min_notional=decimal(notional.get("minNotional", 0)),
            max_notional=decimal(notional.get("maxNotional", 0)),
            bid_multiplier_up=decimal(percent.get("bidMultiplierUp", common_up)),
            bid_multiplier_down=decimal(percent.get("bidMultiplierDown", common_down)),
            ask_multiplier_up=decimal(percent.get("askMultiplierUp", common_up)),
            ask_multiplier_down=decimal(percent.get("askMultiplierDown", common_down)),
            source="binance_exchangeInfo",
        )


@dataclass(frozen=True)
class OrderIntent:
    client_order_id: str
    side: Side
    quantity: Decimal
    decision_time_ns: int
    decision_price: Decimal
    kind: OrderKind = OrderKind.MARKETABLE_LIMIT
    limit_price: Decimal | None = None
    protective: bool = False

    def __post_init__(self) -> None:
        if not self.client_order_id or self.quantity <= 0 or self.decision_price <= 0:
            raise ValueError("order ID, quantity, and decision price must be positive")


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    quantity: Decimal

    def __post_init__(self) -> None:
        if self.price <= 0 or self.quantity < 0:
            raise ValueError("book price must be positive and quantity non-negative")


@dataclass(frozen=True)
class BookObservation:
    timestamp_ns: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    segment_id: int = 1
    stale: bool = False

    def __post_init__(self) -> None:
        if not self.bids or not self.asks:
            raise ValueError("both book sides are required")
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("crossed or locked book")
        if any(a.price < b.price for a, b in zip(self.bids, self.bids[1:])):
            raise ValueError("bids must be descending")
        if any(a.price > b.price for a, b in zip(self.asks, self.asks[1:])):
            raise ValueError("asks must be ascending")

    @property
    def midpoint(self) -> Decimal:
        return (self.bids[0].price + self.asks[0].price) / 2


@dataclass(frozen=True)
class TradeEvent:
    timestamp_ns: int
    price: Decimal
    quantity: Decimal
    aggressor_side: Side


@dataclass(frozen=True)
class Commission:
    amount: Decimal
    asset: str
    quote_value: Decimal


@dataclass(frozen=True)
class Fill:
    timestamp_ns: int
    side: Side
    price: Decimal
    quantity: Decimal
    liquidity: str
    commission: Commission

    @property
    def notional(self) -> Decimal:
        return self.price * self.quantity


@dataclass(frozen=True)
class CostBreakdown:
    explicit_fees_quote: Decimal = ZERO
    delay_quote: Decimal = ZERO
    spread_quote: Decimal = ZERO
    depth_impact_quote: Decimal = ZERO
    residual_impact_quote: Decimal = ZERO
    adverse_selection_quote: Decimal = ZERO
    opportunity_quote: Decimal = ZERO
    rounding_quote: Decimal = ZERO

    @property
    def total_quote(self) -> Decimal:
        return sum((
            self.explicit_fees_quote, self.delay_quote, self.spread_quote,
            self.depth_impact_quote, self.residual_impact_quote,
            self.adverse_selection_quote, self.opportunity_quote, self.rounding_quote,
        ), ZERO)

    def add(self, other: "CostBreakdown") -> "CostBreakdown":
        return CostBreakdown(**{
            name: getattr(self, name) + getattr(other, name)
            for name in self.__dataclass_fields__
        })


@dataclass(frozen=True)
class ExecutionResult:
    client_order_id: str
    status: OrderStatus
    requested_quantity: Decimal
    accepted_quantity: Decimal
    filled_quantity: Decimal
    unfilled_quantity: Decimal
    fills: tuple[Fill, ...]
    costs: CostBreakdown
    reason: str | None
    scenario_id: str
    scenario_checksum: str
    market_rules_checksum: str
    events: tuple[str, ...]

    @property
    def average_fill_price(self) -> Decimal | None:
        if not self.filled_quantity:
            return None
        return sum((fill.notional for fill in self.fills), ZERO) / self.filled_quantity

    def to_dict(self) -> dict[str, Any]:
        data = _canonical(self)
        data["average_fill_price"] = _canonical(self.average_fill_price)
        data["total_cost_quote"] = _canonical(self.costs.total_quote)
        return data


def _signed_price_cost(side: Side, quantity: Decimal, later: Decimal, earlier: Decimal) -> Decimal:
    return quantity * (later - earlier) if side is Side.BUY else quantity * (earlier - later)


def _commission(quantity: Decimal, price: Decimal, fee_bps: Decimal, asset: str) -> Commission:
    quote_value = quantity * price * fee_bps / BPS
    if asset == "base":
        return Commission(quantity * fee_bps / BPS, "base", quote_value)
    if asset == "third":
        raise ValueError("third-asset simulation requires an explicit converted fill")
    return Commission(quote_value, "quote", quote_value)


def _empty_result(
    intent: OrderIntent, scenario: ExecutionScenario, rules: MarketRules,
    status: OrderStatus, reason: str, accepted_quantity: Decimal = ZERO,
    costs: CostBreakdown | None = None, events: Sequence[str] = (),
) -> ExecutionResult:
    return ExecutionResult(
        client_order_id=intent.client_order_id,
        status=status,
        requested_quantity=intent.quantity,
        accepted_quantity=accepted_quantity,
        filled_quantity=ZERO,
        unfilled_quantity=accepted_quantity or intent.quantity,
        fills=(), costs=costs or CostBreakdown(), reason=reason,
        scenario_id=scenario.scenario_id, scenario_checksum=scenario.checksum,
        market_rules_checksum=rules.checksum, events=tuple(events),
    )


def _protected_limit(intent: OrderIntent, scenario: ExecutionScenario, rules: MarketRules) -> Decimal:
    if intent.protective or intent.kind is OrderKind.PROTECTIVE:
        return Decimal("Infinity") if intent.side is Side.BUY else ZERO
    multiplier = Decimal("1") + scenario.price_protection_bps / BPS
    if intent.side is Side.SELL:
        multiplier = Decimal("1") - scenario.price_protection_bps / BPS
    requested = intent.limit_price if intent.limit_price is not None else intent.decision_price * multiplier
    return rules.round_price(requested, intent.side)


def simulate_candle_taker(
    intent: OrderIntent,
    observed_price: Decimal,
    observation_time_ns: int,
    scenario: ExecutionScenario,
    rules: MarketRules,
    opportunity_price: Decimal | None = None,
) -> ExecutionResult:
    """Execute at an adverse-adjusted candle observation without fake sub-candle latency."""
    if scenario.mode != "candle_taker":
        raise ValueError("candle simulator requires candle_taker scenario")
    observed_price = decimal(observed_price)
    if observation_time_ns < intent.decision_time_ns:
        return _empty_result(intent, scenario, rules, OrderStatus.REJECTED, "observation_before_decision")
    quantity = rules.round_quantity(intent.quantity)
    adjusted = observed_price * (
        Decimal("1") + scenario.implicit_cost_bps_per_side / BPS
        if intent.side is Side.BUY
        else Decimal("1") - scenario.implicit_cost_bps_per_side / BPS
    )
    adjusted = rules.round_price(adjusted, Side.SELL if intent.side is Side.BUY else Side.BUY)
    reason = rules.validate(quantity, adjusted, observed_price, intent.side)
    rounding = (intent.quantity - quantity) * intent.decision_price
    if reason:
        return _empty_result(
            intent, scenario, rules, OrderStatus.REJECTED, reason,
            costs=CostBreakdown(rounding_quote=rounding), events=("created", "rejected"),
        )
    limit = _protected_limit(intent, scenario, rules)
    outside = adjusted > limit if intent.side is Side.BUY else adjusted < limit
    if outside and not intent.protective:
        opportunity = ZERO
        if opportunity_price is not None:
            opportunity = _signed_price_cost(intent.side, quantity, decimal(opportunity_price), intent.decision_price)
        return _empty_result(
            intent, scenario, rules, OrderStatus.EXPIRED, "price_protection",
            accepted_quantity=quantity,
            costs=CostBreakdown(opportunity_quote=opportunity, rounding_quote=rounding),
            events=("created", "acknowledged", "expired"),
        )
    commission = _commission(quantity, adjusted, scenario.taker_fee_bps, scenario.commission_asset)
    fill = Fill(observation_time_ns, intent.side, adjusted, quantity, "taker", commission)
    costs = CostBreakdown(
        explicit_fees_quote=commission.quote_value,
        delay_quote=_signed_price_cost(intent.side, quantity, observed_price, intent.decision_price),
        residual_impact_quote=abs(adjusted - observed_price) * quantity,
        rounding_quote=rounding,
    )
    return ExecutionResult(
        intent.client_order_id, OrderStatus.FILLED, intent.quantity, quantity, quantity, ZERO,
        (fill,), costs, None, scenario.scenario_id, scenario.checksum, rules.checksum,
        ("created", "acknowledged", "filled"),
    )


def simulate_book_taker(
    intent: OrderIntent,
    book: BookObservation,
    scenario: ExecutionScenario,
    rules: MarketRules,
    opportunity_price: Decimal | None = None,
    expected_segment_id: int | None = None,
) -> ExecutionResult:
    if scenario.mode not in {"book_taker", "maker_hybrid"}:
        raise ValueError("book simulator requires book_taker or maker_hybrid scenario")
    required_time = intent.decision_time_ns + scenario.latency_ms * 1_000_000
    if book.timestamp_ns < required_time:
        return _empty_result(intent, scenario, rules, OrderStatus.REJECTED, "book_before_arrival")
    if expected_segment_id is not None and book.segment_id != expected_segment_id:
        return _empty_result(intent, scenario, rules, OrderStatus.REJECTED, "segment_mismatch")
    if book.stale:
        return _empty_result(intent, scenario, rules, OrderStatus.REJECTED, "stale_book")
    quantity = rules.round_quantity(intent.quantity)
    limit = _protected_limit(intent, scenario, rules)
    reference = book.midpoint
    validation_price = book.asks[0].price if intent.side is Side.BUY else book.bids[0].price
    reason = rules.validate(quantity, validation_price, reference, intent.side)
    rounding = (intent.quantity - quantity) * intent.decision_price
    if reason:
        return _empty_result(
            intent, scenario, rules, OrderStatus.REJECTED, reason,
            costs=CostBreakdown(rounding_quote=rounding), events=("created", "rejected"),
        )

    levels = book.asks if intent.side is Side.BUY else book.bids
    remaining = quantity
    fills: list[Fill] = []
    raw_fill_prices: list[Decimal] = []
    residual_factor = scenario.residual_impact_bps / BPS
    for level in levels:
        if remaining <= 0:
            break
        price = level.price * (Decimal("1") + residual_factor if intent.side is Side.BUY else Decimal("1") - residual_factor)
        price = rules.round_price(price, Side.SELL if intent.side is Side.BUY else Side.BUY)
        outside = price > limit if intent.side is Side.BUY else price < limit
        if outside and not intent.protective:
            break
        amount = min(remaining, level.quantity)
        if amount <= 0:
            continue
        fee = _commission(amount, price, scenario.taker_fee_bps, scenario.commission_asset)
        fills.append(Fill(book.timestamp_ns, intent.side, price, amount, "taker", fee))
        raw_fill_prices.append(level.price)
        remaining -= amount

    filled = quantity - remaining
    if not filled:
        opportunity = ZERO
        if opportunity_price is not None:
            opportunity = _signed_price_cost(intent.side, quantity, decimal(opportunity_price), intent.decision_price)
        return _empty_result(
            intent, scenario, rules, OrderStatus.EXPIRED, "price_protection_or_no_depth",
            accepted_quantity=quantity,
            costs=CostBreakdown(opportunity_quote=opportunity, rounding_quote=rounding),
            events=("created", "acknowledged", "expired"),
        )

    average = sum((fill.notional for fill in fills), ZERO) / filled
    best = levels[0].price
    explicit = sum((fill.commission.quote_value for fill in fills), ZERO)
    residual = sum(
        (abs(fill.price - raw_price) * fill.quantity for fill, raw_price in zip(fills, raw_fill_prices)),
        ZERO,
    )
    opportunity = ZERO
    if remaining and opportunity_price is not None:
        opportunity = _signed_price_cost(intent.side, remaining, decimal(opportunity_price), intent.decision_price)
    costs = CostBreakdown(
        explicit_fees_quote=explicit,
        delay_quote=_signed_price_cost(intent.side, filled, reference, intent.decision_price),
        spread_quote=_signed_price_cost(intent.side, filled, best, reference),
        depth_impact_quote=_signed_price_cost(intent.side, filled, average, best) - residual,
        residual_impact_quote=residual,
        opportunity_quote=opportunity,
        rounding_quote=rounding,
    )
    status = OrderStatus.FILLED if remaining == 0 else OrderStatus.PARTIALLY_FILLED
    return ExecutionResult(
        intent.client_order_id, status, intent.quantity, quantity, filled, remaining,
        tuple(fills), costs, None if not remaining else "insufficient_protected_depth",
        scenario.scenario_id, scenario.checksum, rules.checksum,
        ("created", "acknowledged", status.value),
    )


def simulate_maker_hybrid(
    intent: OrderIntent,
    initial_book: BookObservation,
    trades: Iterable[TradeEvent],
    scenario: ExecutionScenario,
    rules: MarketRules,
    fallback_book: BookObservation | None = None,
    opportunity_price: Decimal | None = None,
    post_fill_midprice: Decimal | None = None,
) -> ExecutionResult:
    """Conservative market-by-price maker queue followed by optional taker fallback."""
    if scenario.mode != "maker_hybrid":
        raise ValueError("maker simulator requires maker_hybrid scenario")
    required_time = intent.decision_time_ns + scenario.latency_ms * 1_000_000
    if initial_book.stale or initial_book.timestamp_ns < required_time:
        return _empty_result(intent, scenario, rules, OrderStatus.REJECTED, "invalid_initial_book")
    quantity = rules.round_quantity(intent.quantity)
    limit = intent.limit_price
    if limit is None:
        limit = initial_book.bids[0].price if intent.side is Side.BUY else initial_book.asks[0].price
    limit = rules.round_price(limit, intent.side)
    if (intent.side is Side.BUY and limit >= initial_book.asks[0].price) or (
        intent.side is Side.SELL and limit <= initial_book.bids[0].price
    ):
        return _empty_result(intent, scenario, rules, OrderStatus.REJECTED, "post_only_would_take")
    reason = rules.validate(quantity, limit, initial_book.midpoint, intent.side)
    if reason:
        return _empty_result(intent, scenario, rules, OrderStatus.REJECTED, reason)

    side_levels = initial_book.bids if intent.side is Side.BUY else initial_book.asks
    queue_ahead = next((level.quantity for level in side_levels if level.price == limit), ZERO)
    remaining = quantity
    fills: list[Fill] = []
    cancel_request_ns = initial_book.timestamp_ns + scenario.maker_timeout_ms * 1_000_000
    cancel_effective_ns = cancel_request_ns + scenario.cancel_latency_ms * 1_000_000
    required_aggressor = Side.SELL if intent.side is Side.BUY else Side.BUY
    for trade in sorted(trades, key=lambda item: item.timestamp_ns):
        if trade.timestamp_ns < initial_book.timestamp_ns or trade.timestamp_ns > cancel_effective_ns:
            continue
        qualifies = trade.price <= limit if intent.side is Side.BUY else trade.price >= limit
        if trade.aggressor_side is not required_aggressor or not qualifies:
            continue
        available = trade.quantity
        if queue_ahead:
            consumed = min(queue_ahead, available)
            queue_ahead -= consumed
            available -= consumed
        amount = min(remaining, available)
        if amount > 0:
            fee = _commission(amount, limit, scenario.maker_fee_bps, scenario.commission_asset)
            fills.append(Fill(trade.timestamp_ns, intent.side, limit, amount, "maker", fee))
            remaining -= amount
        if not remaining:
            break

    filled = quantity - remaining
    costs = CostBreakdown(
        explicit_fees_quote=sum((fill.commission.quote_value for fill in fills), ZERO),
        delay_quote=_signed_price_cost(intent.side, filled, initial_book.midpoint, intent.decision_price),
        spread_quote=_signed_price_cost(intent.side, filled, limit, initial_book.midpoint),
        adverse_selection_quote=(
            _signed_price_cost(intent.side, filled, limit, decimal(post_fill_midprice))
            if post_fill_midprice is not None else ZERO
        ),
        rounding_quote=(intent.quantity - quantity) * intent.decision_price,
    )
    events = ["created", "acknowledged"]
    if fills:
        events.append("filled" if not remaining else "partially_filled")
    if not remaining:
        return ExecutionResult(
            intent.client_order_id, OrderStatus.FILLED, intent.quantity, quantity, quantity, ZERO,
            tuple(fills), costs, None, scenario.scenario_id, scenario.checksum,
            rules.checksum, tuple(events),
        )

    events.extend(("cancel_pending", "cancelled"))
    if scenario.maker_taker_fallback and fallback_book is not None:
        fallback_intent = replace(
            intent,
            client_order_id=f"{intent.client_order_id}:fallback",
            quantity=remaining,
            kind=OrderKind.MARKETABLE_LIMIT,
            limit_price=None,
        )
        fallback_scenario = replace(scenario, mode="book_taker", latency_ms=0)
        fallback = simulate_book_taker(fallback_intent, fallback_book, fallback_scenario, rules)
        fills.extend(fallback.fills)
        costs = costs.add(fallback.costs)
        remaining = fallback.unfilled_quantity
        filled = quantity - remaining
        if remaining and opportunity_price is not None:
            costs = costs.add(CostBreakdown(
                opportunity_quote=_signed_price_cost(
                    intent.side, remaining, decimal(opportunity_price), intent.decision_price
                )
            ))
        events.append("taker_fallback")
        status = OrderStatus.FILLED if not remaining else OrderStatus.PARTIALLY_FILLED
        return ExecutionResult(
            intent.client_order_id, status, intent.quantity, quantity, filled, remaining,
            tuple(fills), costs, fallback.reason, scenario.scenario_id, scenario.checksum,
            rules.checksum, tuple(events),
        )

    if remaining and opportunity_price is not None:
        costs = costs.add(CostBreakdown(
            opportunity_quote=_signed_price_cost(
                intent.side, remaining, decimal(opportunity_price), intent.decision_price
            )
        ))
    status = OrderStatus.PARTIALLY_FILLED if filled else OrderStatus.CANCELLED
    return ExecutionResult(
        intent.client_order_id, status, intent.quantity, quantity, filled, remaining,
        tuple(fills), costs, "maker_timeout", scenario.scenario_id, scenario.checksum,
        rules.checksum, tuple(events),
    )


@dataclass
class PortfolioLedger:
    quote_balance: Decimal
    base_balance: Decimal = ZERO
    other_balances: dict[str, Decimal] = field(default_factory=dict)

    def apply_fill(self, fill: Fill) -> None:
        commission = fill.commission
        projected_quote = self.quote_balance
        projected_base = self.base_balance
        if fill.side is Side.BUY:
            projected_quote -= fill.notional
            projected_base += fill.quantity
        else:
            projected_base -= fill.quantity
            projected_quote += fill.notional
        if commission.asset == "quote":
            projected_quote -= commission.amount
        elif commission.asset == "base":
            projected_base -= commission.amount
        elif self.other_balances.get(commission.asset, ZERO) < commission.amount:
            raise ValueError("insufficient third-asset balance for commission")
        if projected_quote < 0:
            raise ValueError("insufficient quote balance")
        if projected_base < 0:
            raise ValueError("insufficient base balance")
        self.quote_balance = projected_quote
        self.base_balance = projected_base
        if commission.asset not in {"quote", "base"}:
            available = self.other_balances.get(commission.asset, ZERO)
            self.other_balances[commission.asset] = available - commission.amount


def unknown_execution_result(
    intent: OrderIntent,
    scenario: ExecutionScenario,
    rules: MarketRules,
    reason: str = "transport_status_unknown",
) -> ExecutionResult:
    """Represent an ambiguous submit response that must be queried, never retried blindly."""
    quantity = rules.round_quantity(intent.quantity)
    return ExecutionResult(
        intent.client_order_id, OrderStatus.UNKNOWN, intent.quantity, quantity,
        ZERO, quantity, (), CostBreakdown(), reason, scenario.scenario_id,
        scenario.checksum, rules.checksum, ("created", "unknown", "reconcile_required"),
    )


def reconcile_unknown_result(
    result: ExecutionResult,
    final_status: OrderStatus,
    fills: Sequence[Fill] = (),
) -> ExecutionResult:
    if result.status is not OrderStatus.UNKNOWN:
        raise ValueError("only unknown execution results may be reconciled")
    if final_status not in {OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}:
        raise ValueError("invalid reconciled terminal status")
    filled = sum((fill.quantity for fill in fills), ZERO)
    if filled > result.accepted_quantity:
        raise ValueError("reconciled fills exceed accepted quantity")
    if final_status is OrderStatus.FILLED and filled != result.accepted_quantity:
        raise ValueError("filled reconciliation requires the full accepted quantity")
    explicit = sum((fill.commission.quote_value for fill in fills), ZERO)
    return replace(
        result,
        status=OrderStatus.RECONCILED,
        filled_quantity=filled,
        unfilled_quantity=result.accepted_quantity - filled,
        fills=tuple(fills),
        costs=replace(result.costs, explicit_fees_quote=explicit),
        reason=f"reconciled_{final_status.value}",
        events=result.events + (f"exchange_{final_status.value}", "reconciled"),
    )


def write_execution_manifest(
    path: Path,
    scenario: ExecutionScenario,
    rules: MarketRules,
    input_sha256: str,
    results: Sequence[ExecutionResult],
) -> dict[str, Any]:
    payload = {
        "schema_version": "execution-result-manifest-v1",
        "scenario": _canonical(scenario),
        "scenario_sha256": scenario.checksum,
        "market_rules": _canonical(rules),
        "market_rules_sha256": rules.checksum,
        "input_sha256": input_sha256,
        "results": [result.to_dict() for result in results],
    }
    payload["results_sha256"] = sha256_digest(payload["results"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
