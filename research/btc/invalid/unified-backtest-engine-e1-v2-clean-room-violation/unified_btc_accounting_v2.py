"""Synthetic-only BTC spot and linear perpetual Decimal accounting kernel.

This module implements E0 v1 plus the independently accepted E0-v2 clarifications. It is an
offline research primitive: no strategy, metrics, historical loader, exchange, database,
message-bus, production signal, or executable order integration is present.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable, Mapping


ZERO = Decimal("0")
ONE = Decimal("1")
RESIDUAL_LIMIT = Decimal("0.00000001")


class AccountingV2Error(ValueError):
    """A synthetic event is ambiguous, invalid, or violates the frozen contract."""


def _decimal(value: Decimal, label: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise AccountingV2Error(f"{label} must be a finite Decimal")
    if positive and value <= ZERO:
        raise AccountingV2Error(f"{label} must be positive")
    return value


def decimal_text(value: Decimal) -> str:
    _decimal(value, "decimal")
    if value == ZERO:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def timestamp_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise AccountingV2Error("timestamps must be timezone-aware UTC")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, datetime):
        return timestamp_text(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, float):
        raise AccountingV2Error("float economic content is prohibited")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _json_value(value), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def canonical_digest(value: Mapping[str, Any], own_field: str | None = None) -> str:
    material = dict(value)
    if own_field is not None:
        material.pop(own_field, None)
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LineageV2:
    experiment_id: str
    run_id: str
    scenario_id: str
    implementation_digest: str
    contract_digest: str
    execution_config_digest: str
    mandate_digest: str

    def __post_init__(self) -> None:
        if not self.experiment_id or not self.run_id or not self.scenario_id:
            raise AccountingV2Error("lineage IDs are required")
        for field_name in (
            "implementation_digest",
            "contract_digest",
            "execution_config_digest",
            "mandate_digest",
        ):
            digest = getattr(self, field_name)
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise AccountingV2Error(f"{field_name} must be lowercase SHA-256")

    def values(self) -> dict[str, str]:
        return {
            "contract_digest": self.contract_digest,
            "execution_config_digest": self.execution_config_digest,
            "experiment_id": self.experiment_id,
            "implementation_digest": self.implementation_digest,
            "mandate_digest": self.mandate_digest,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
        }


@dataclass(frozen=True, slots=True)
class RunPolicyV2:
    leverage: Decimal
    perpetual_exit_cost_rate: Decimal
    terminal_execution_at: datetime
    zero_exit_reserve_fixture: bool = False

    def __post_init__(self) -> None:
        _decimal(self.leverage, "leverage", positive=True)
        _decimal(self.perpetual_exit_cost_rate, "perpetual_exit_cost_rate")
        timestamp_text(self.terminal_execution_at)
        if self.perpetual_exit_cost_rate < ZERO:
            raise AccountingV2Error("exit cost rate cannot be negative")
        if self.perpetual_exit_cost_rate == ZERO and not self.zero_exit_reserve_fixture:
            raise AccountingV2Error("zero exit reserve requires explicit synthetic fixture metadata")


@dataclass(frozen=True, slots=True)
class RulesV2:
    price_tick: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal

    def __post_init__(self) -> None:
        for name in ("price_tick", "quantity_step", "minimum_quantity", "minimum_notional"):
            _decimal(getattr(self, name), name, positive=True)

    def price(self, value: Decimal) -> Decimal:
        _decimal(value, "price", positive=True)
        if value % self.price_tick != ZERO:
            raise AccountingV2Error("accounting price is not rule-quantized")
        return value

    def quantity(self, requested: Decimal, price: Decimal) -> Decimal:
        _decimal(requested, "requested quantity")
        self.price(price)
        if requested == ZERO:
            raise AccountingV2Error("requested quantity cannot be zero")
        sign = ONE if requested > ZERO else -ONE
        units = (abs(requested) / self.quantity_step).to_integral_value(rounding=ROUND_DOWN)
        filled = units * self.quantity_step * sign
        if abs(filled) < self.minimum_quantity or abs(filled) * price < self.minimum_notional:
            raise AccountingV2Error("quantized order violates quantity or notional minimum")
        return filled


@dataclass(slots=True)
class StateV2:
    quote_cash: Decimal
    spot_btc: Decimal = ZERO
    isolated_collateral: Decimal = ZERO
    perpetual_btc: Decimal = ZERO
    average_perpetual_entry: Decimal | None = None
    third_asset_balances: dict[str, Decimal] = field(default_factory=dict)
    liabilities: Decimal = ZERO
    allocated_initial_margin_memo: Decimal = ZERO
    exit_cost_reserve_memo: Decimal = ZERO
    realized_pnl_memo: Decimal = ZERO
    funding_memo: Decimal = ZERO
    explicit_cost_memo: Decimal = ZERO
    implicit_cost_memo: Decimal = ZERO
    invalidation_reason: str | None = None
    terminal: bool = False

    def values(self) -> dict[str, Any]:
        return {
            "allocated_initial_margin_memo": self.allocated_initial_margin_memo,
            "average_perpetual_entry": self.average_perpetual_entry,
            "exit_cost_reserve_memo": self.exit_cost_reserve_memo,
            "explicit_cost_memo": self.explicit_cost_memo,
            "funding_memo": self.funding_memo,
            "implicit_cost_memo": self.implicit_cost_memo,
            "invalidation_reason": self.invalidation_reason,
            "isolated_collateral": self.isolated_collateral,
            "liabilities": self.liabilities,
            "perpetual_btc": self.perpetual_btc,
            "quote_cash": self.quote_cash,
            "realized_pnl_memo": self.realized_pnl_memo,
            "spot_btc": self.spot_btc,
            "terminal": self.terminal,
            "third_asset_balances": dict(sorted(self.third_asset_balances.items())),
        }


@dataclass(frozen=True, slots=True)
class MarginV2:
    equity: Decimal
    maintenance: Decimal
    ratio: Decimal | None
    liquidated: bool


@dataclass(frozen=True, slots=True)
class PairPreflightV2:
    gross_spot_entry: Decimal
    entry_base_fee: Decimal
    net_spot_btc: Decimal
    perpetual_entry_btc: Decimal
    neutralization_gross_spot_sale: Decimal
    neutralization_base_fee: Decimal


class LedgerV2:
    """One deterministic synthetic account with row-level reconciliation."""

    _PHASE = {
        "validate": 1,
        "open_mark_or_liquidation": 2,
        "protective_exit": 3,
        "funding": 4,
        "risk": 5,
        "rebalance": 6,
        "post_fill_margin": 7,
        "intrabar_mark_or_liquidation": 8,
        "reconcile": 9,
    }

    def __init__(
        self,
        *,
        quote_cash: Decimal,
        spot_mark: Decimal,
        perpetual_mark: Decimal,
        policy: RunPolicyV2,
        lineage: LineageV2,
        third_asset_balances: Mapping[str, Decimal] | None = None,
        third_asset_marks: Mapping[str, Decimal] | None = None,
    ) -> None:
        _decimal(quote_cash, "quote_cash", positive=True)
        _decimal(spot_mark, "spot_mark", positive=True)
        _decimal(perpetual_mark, "perpetual_mark", positive=True)
        balances = dict(third_asset_balances or {})
        marks = dict(third_asset_marks or {})
        if set(balances) != set(marks) or {"BTC", "USDT"}.intersection(balances):
            raise AccountingV2Error("third-asset balances need matching non-BTC/USDT marks")
        for asset, amount in balances.items():
            _decimal(amount, f"{asset} balance")
            _decimal(marks[asset], f"{asset} mark", positive=True)
            if amount < ZERO:
                raise AccountingV2Error("third-asset balance cannot be negative")
        self.state = StateV2(quote_cash=quote_cash, third_asset_balances=balances)
        self.spot_mark = spot_mark
        self.perpetual_mark = perpetual_mark
        self.third_asset_marks = marks
        self.policy = policy
        self.lineage = lineage
        self.events: list[dict[str, Any]] = []
        self._event_ids: set[str] = set()
        self._last_order: tuple[datetime, int] | None = None

    @property
    def actionable_arm_id(self) -> str:
        return "no_trade"

    def nav(self) -> Decimal:
        third_value = sum(
            (amount * self.third_asset_marks[asset] for asset, amount in self.state.third_asset_balances.items()),
            ZERO,
        )
        unrealized = ZERO
        if self.state.perpetual_btc != ZERO:
            if self.state.average_perpetual_entry is None:
                raise AccountingV2Error("open perpetual position lacks average entry")
            unrealized = self.state.perpetual_btc * (
                self.perpetual_mark - self.state.average_perpetual_entry
            )
        return (
            self.state.quote_cash
            + self.state.spot_btc * self.spot_mark
            + third_value
            + self.state.isolated_collateral
            + unrealized
            - self.state.liabilities
        )

    def state_digest(self) -> str:
        return canonical_digest(
            {
                "perpetual_mark": self.perpetual_mark,
                "spot_mark": self.spot_mark,
                "state": self.state.values(),
                "third_asset_marks": self.third_asset_marks,
            }
        )

    def _event_guard(self, event_id: str, at: datetime, phase: str) -> None:
        if self.state.terminal:
            raise AccountingV2Error("terminal account rejects subsequent events")
        if not event_id or event_id in self._event_ids:
            raise AccountingV2Error("event ID is absent or duplicated")
        timestamp_text(at)
        if phase not in self._PHASE:
            raise AccountingV2Error("unknown event phase")
        order = (at, self._PHASE[phase])
        if self._last_order is not None and order < self._last_order:
            raise AccountingV2Error("event timestamp or same-time phase is permuted")
        self._event_ids.add(event_id)
        self._last_order = order

    def _record(
        self,
        *,
        event_id: str,
        at: datetime,
        phase: str,
        event_type: str,
        mutation: Callable[[], None],
        spot_price_pnl: Decimal = ZERO,
        perpetual_price_pnl: Decimal = ZERO,
        third_asset_price_pnl: Decimal = ZERO,
        funding: Decimal = ZERO,
        explicit_cost: Decimal = ZERO,
        implicit_cost: Decimal = ZERO,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        amounts = (
            spot_price_pnl,
            perpetual_price_pnl,
            third_asset_price_pnl,
            funding,
            explicit_cost,
            implicit_cost,
        )
        for amount in amounts:
            _decimal(amount, "event economic amount")
        self._event_guard(event_id, at, phase)
        before_nav = self.nav()
        before_digest = self.state_digest()
        mutation()
        after_nav = self.nav()
        after_digest = self.state_digest()
        expected = (
            spot_price_pnl
            + perpetual_price_pnl
            + third_asset_price_pnl
            + funding
            - explicit_cost
            - implicit_cost
        )
        residual = after_nav - before_nav - expected
        if abs(residual) > RESIDUAL_LIMIT:
            raise AccountingV2Error(f"event residual exceeds 1e-8 USDT: {residual}")
        row: dict[str, Any] = {
            **self.lineage.values(),
            "actionable_arm_id": "no_trade",
            "after_nav": after_nav,
            "after_state_digest": after_digest,
            "at": at,
            "before_nav": before_nav,
            "before_state_digest": before_digest,
            "details": dict(details or {}),
            "event_accounting_residual": residual,
            "event_id": event_id,
            "event_sequence": len(self.events) + 1,
            "event_type": event_type,
            "explicit_cost": explicit_cost,
            "funding": funding,
            "implicit_cost": implicit_cost,
            "invalidation_reason": self.state.invalidation_reason,
            "perpetual_price_pnl": perpetual_price_pnl,
            "phase": phase,
            "spot_price_pnl": spot_price_pnl,
            "third_asset_price_pnl": third_asset_price_pnl,
        }
        row["row_digest"] = canonical_digest(row, "row_digest")
        self.events.append(row)
        return row

    def _increasing_spot(self, signed_quantity: Decimal) -> bool:
        return signed_quantity > ZERO

    def _increasing_perpetual(self, delta: Decimal) -> bool:
        old = self.state.perpetual_btc
        return old == ZERO or old * delta > ZERO

    def _terminal_guard(self, at: datetime, increasing: bool) -> None:
        if at > self.policy.terminal_execution_at:
            raise AccountingV2Error("event is after terminal execution boundary")
        if at == self.policy.terminal_execution_at and increasing:
            raise AccountingV2Error("terminal execution cannot increase exposure")

    def _fee_value(self, amount: Decimal, asset: str | None, mark: Decimal | None) -> Decimal:
        _decimal(amount, "fee amount")
        if amount < ZERO:
            raise AccountingV2Error("fee cannot be negative")
        if amount == ZERO:
            return ZERO
        if asset == "USDT":
            return amount
        if asset == "BTC":
            conversion = self.spot_mark if mark is None else _decimal(mark, "fee mark", positive=True)
            return amount * conversion
        if asset is None or asset not in self.state.third_asset_balances:
            raise AccountingV2Error("unsupported fee currency")
        conversion = self.third_asset_marks[asset] if mark is None else _decimal(mark, "fee mark", positive=True)
        return amount * conversion

    def _debit_fee(self, amount: Decimal, asset: str | None, *, perpetual: bool) -> None:
        if amount == ZERO:
            return
        if asset == "USDT":
            if perpetual:
                self.state.isolated_collateral -= amount
            else:
                self.state.quote_cash -= amount
        elif asset == "BTC" and not perpetual:
            if self.state.spot_btc < amount:
                raise AccountingV2Error("insufficient BTC for base fee")
            self.state.spot_btc -= amount
        elif asset in self.state.third_asset_balances:
            if self.state.third_asset_balances[asset] < amount:
                raise AccountingV2Error("insufficient third fee asset")
            self.state.third_asset_balances[asset] -= amount
        else:
            raise AccountingV2Error("unsupported fee currency")

    def _refresh_exit_reserve(self) -> None:
        self.state.exit_cost_reserve_memo = (
            abs(self.state.perpetual_btc)
            * self.perpetual_mark
            * self.policy.perpetual_exit_cost_rate
        )

    def spot_fill(
        self,
        *,
        event_id: str,
        at: datetime,
        requested_quantity: Decimal,
        price: Decimal,
        rules: RulesV2,
        fee_amount: Decimal = ZERO,
        fee_asset: str | None = None,
        fee_mark: Decimal | None = None,
        implicit_cost: Decimal = ZERO,
        phase: str = "rebalance",
    ) -> dict[str, Any]:
        price = rules.price(price)
        quantity = rules.quantity(requested_quantity, price)
        _decimal(implicit_cost, "implicit cost")
        if implicit_cost < ZERO:
            raise AccountingV2Error("implicit cost cannot be negative")
        increasing = self._increasing_spot(quantity)
        self._terminal_guard(at, increasing)
        explicit = self._fee_value(fee_amount, fee_asset, fee_mark)
        if quantity < ZERO:
            required_btc = abs(quantity) + (fee_amount if fee_asset == "BTC" else ZERO)
            if self.state.spot_btc < required_btc:
                raise AccountingV2Error("spot sale and base fee exceed actual inventory")
        elif fee_asset == "BTC" and fee_amount > quantity:
            raise AccountingV2Error("entry base fee exceeds acquired BTC")
        quote_change = -quantity * price
        quote_fee = fee_amount if fee_asset == "USDT" else ZERO
        if self.state.quote_cash + quote_change - quote_fee - implicit_cost < ZERO:
            raise AccountingV2Error("insufficient quote cash")
        if fee_asset not in {None, "USDT", "BTC"}:
            if fee_asset not in self.state.third_asset_balances or self.state.third_asset_balances[fee_asset] < fee_amount:
                raise AccountingV2Error("third fee asset unavailable")

        def mutation() -> None:
            self.state.quote_cash += quote_change
            self.state.spot_btc += quantity
            self._debit_fee(fee_amount, fee_asset, perpetual=False)
            self.state.quote_cash -= implicit_cost
            self.state.explicit_cost_memo += explicit
            self.state.implicit_cost_memo += implicit_cost

        return self._record(
            event_id=event_id,
            at=at,
            phase=phase,
            event_type="spot_fill",
            mutation=mutation,
            spot_price_pnl=quantity * (self.spot_mark - price),
            explicit_cost=explicit,
            implicit_cost=implicit_cost,
            details={
                "fee_amount": fee_amount,
                "fee_asset": fee_asset,
                "filled_quantity": quantity,
                "price": price,
                "requested_quantity": requested_quantity,
            },
        )

    def perpetual_fill(
        self,
        *,
        event_id: str,
        at: datetime,
        requested_quantity_delta: Decimal,
        price: Decimal,
        rules: RulesV2,
        fee_amount: Decimal = ZERO,
        fee_asset: str | None = None,
        fee_mark: Decimal | None = None,
        implicit_cost: Decimal = ZERO,
        phase: str = "rebalance",
    ) -> dict[str, Any]:
        price = rules.price(price)
        delta = rules.quantity(requested_quantity_delta, price)
        _decimal(implicit_cost, "implicit cost")
        if implicit_cost < ZERO:
            raise AccountingV2Error("implicit cost cannot be negative")
        old = self.state.perpetual_btc
        new = old + delta
        increasing = self._increasing_perpetual(delta)
        self._terminal_guard(at, increasing)
        if old != ZERO and new != ZERO and old * new < ZERO:
            raise AccountingV2Error("reversal must be an explicit close then separate open")
        if not increasing and abs(delta) > abs(old):
            raise AccountingV2Error("reduction exceeds open perpetual quantity")
        if fee_asset == "BTC" and fee_amount != ZERO:
            raise AccountingV2Error("BTC-denominated perpetual fee is unsupported")
        explicit = self._fee_value(fee_amount, fee_asset, fee_mark)
        margin_increment = abs(delta) * price / self.policy.leverage if increasing else ZERO
        if self.state.quote_cash < margin_increment:
            raise AccountingV2Error("insufficient quote cash for additive initial margin")
        if fee_asset not in {None, "USDT", "BTC"}:
            if fee_asset not in self.state.third_asset_balances or self.state.third_asset_balances[fee_asset] < fee_amount:
                raise AccountingV2Error("third fee asset unavailable")
        old_entry = self.state.average_perpetual_entry
        old_abs = abs(old)
        old_allocated = self.state.allocated_initial_margin_memo

        def mutation() -> None:
            if increasing:
                self.state.quote_cash -= margin_increment
                self.state.isolated_collateral += margin_increment
                if old == ZERO:
                    self.state.average_perpetual_entry = price
                else:
                    assert old_entry is not None
                    self.state.average_perpetual_entry = (
                        old_abs * old_entry + abs(delta) * price
                    ) / abs(new)
                self.state.perpetual_btc = new
                self.state.allocated_initial_margin_memo += margin_increment
            else:
                assert old_entry is not None
                closed = abs(delta)
                realized = closed * (ONE if old > ZERO else -ONE) * (price - old_entry)
                self.state.isolated_collateral += realized
                self.state.realized_pnl_memo += realized
                self.state.perpetual_btc = new
            self._debit_fee(fee_amount, fee_asset, perpetual=True)
            self.state.isolated_collateral -= implicit_cost
            self.state.explicit_cost_memo += explicit
            self.state.implicit_cost_memo += implicit_cost
            if not increasing:
                released_memo = old_allocated * abs(delta) / old_abs
                self.state.allocated_initial_margin_memo -= released_memo
                cash_release = min(released_memo, max(self.state.isolated_collateral, ZERO))
                self.state.isolated_collateral -= cash_release
                self.state.quote_cash += cash_release
                if new == ZERO:
                    if self.state.isolated_collateral >= ZERO:
                        self.state.quote_cash += self.state.isolated_collateral
                    else:
                        self.state.liabilities += -self.state.isolated_collateral
                    self.state.isolated_collateral = ZERO
                    self.state.average_perpetual_entry = None
                    self.state.allocated_initial_margin_memo = ZERO
            self._refresh_exit_reserve()

        return self._record(
            event_id=event_id,
            at=at,
            phase=phase,
            event_type="perpetual_fill",
            mutation=mutation,
            perpetual_price_pnl=delta * (self.perpetual_mark - price),
            explicit_cost=explicit,
            implicit_cost=implicit_cost,
            details={
                "additive_initial_margin": margin_increment,
                "fee_amount": fee_amount,
                "fee_asset": fee_asset,
                "filled_quantity_delta": delta,
                "price": price,
                "requested_quantity_delta": requested_quantity_delta,
            },
        )

    def funding(
        self,
        *,
        event_id: str,
        at: datetime,
        t_minus_quantity: Decimal,
        rate: Decimal,
        mark: Decimal,
    ) -> dict[str, Any]:
        _decimal(t_minus_quantity, "t-minus quantity")
        _decimal(rate, "funding rate")
        _decimal(mark, "funding mark", positive=True)
        cashflow = -t_minus_quantity * mark * rate

        def mutation() -> None:
            if self.state.perpetual_btc != ZERO:
                self.state.isolated_collateral += cashflow
            else:
                self.state.quote_cash += cashflow
                if self.state.quote_cash < ZERO:
                    self.state.liabilities += -self.state.quote_cash
                    self.state.quote_cash = ZERO
            self.state.funding_memo += cashflow
            self._refresh_exit_reserve()

        return self._record(
            event_id=event_id,
            at=at,
            phase="funding",
            event_type="funding",
            mutation=mutation,
            funding=cashflow,
            details={"mark": mark, "rate": rate, "t_minus_quantity": t_minus_quantity},
        )

    def mark(
        self,
        *,
        event_id: str,
        at: datetime,
        spot_mark: Decimal,
        perpetual_mark: Decimal,
        third_asset_marks: Mapping[str, Decimal] | None = None,
        phase: str,
    ) -> dict[str, Any]:
        _decimal(spot_mark, "spot mark", positive=True)
        _decimal(perpetual_mark, "perpetual mark", positive=True)
        new_third = dict(self.third_asset_marks if third_asset_marks is None else third_asset_marks)
        if set(new_third) != set(self.state.third_asset_balances):
            raise AccountingV2Error("third-asset marks must match balances")
        for asset, value in new_third.items():
            _decimal(value, f"{asset} mark", positive=True)
        spot_pnl = self.state.spot_btc * (spot_mark - self.spot_mark)
        perp_pnl = self.state.perpetual_btc * (perpetual_mark - self.perpetual_mark)
        third_pnl = sum(
            (
                self.state.third_asset_balances[asset]
                * (new_third[asset] - self.third_asset_marks[asset])
                for asset in new_third
            ),
            ZERO,
        )

        def mutation() -> None:
            self.spot_mark = spot_mark
            self.perpetual_mark = perpetual_mark
            self.third_asset_marks = new_third
            self._refresh_exit_reserve()

        return self._record(
            event_id=event_id,
            at=at,
            phase=phase,
            event_type="mark",
            mutation=mutation,
            spot_price_pnl=spot_pnl,
            perpetual_price_pnl=perp_pnl,
            third_asset_price_pnl=third_pnl,
        )

    def adverse_perpetual_mark(self, *, interval_low: Decimal, interval_high: Decimal) -> Decimal | None:
        _decimal(interval_low, "interval low", positive=True)
        _decimal(interval_high, "interval high", positive=True)
        if interval_low > interval_high:
            raise AccountingV2Error("interval low exceeds high")
        if self.state.perpetual_btc > ZERO:
            return interval_low
        if self.state.perpetual_btc < ZERO:
            return interval_high
        return None

    def margin(self, *, mark: Decimal, maintenance_rate: Decimal) -> MarginV2:
        _decimal(mark, "margin mark", positive=True)
        _decimal(maintenance_rate, "maintenance rate")
        if maintenance_rate < ZERO:
            raise AccountingV2Error("maintenance rate cannot be negative")
        unrealized = ZERO
        if self.state.perpetual_btc != ZERO:
            assert self.state.average_perpetual_entry is not None
            unrealized = self.state.perpetual_btc * (mark - self.state.average_perpetual_entry)
        equity = self.state.isolated_collateral + unrealized - (
            abs(self.state.perpetual_btc) * mark * self.policy.perpetual_exit_cost_rate
        )
        maintenance = abs(self.state.perpetual_btc) * mark * maintenance_rate
        ratio = equity / maintenance if maintenance else None
        return MarginV2(equity, maintenance, ratio, bool(maintenance and equity <= maintenance))

    def liquidate(
        self,
        *,
        event_id: str,
        at: datetime,
        observed_adverse_mark: Decimal,
        maintenance_rate: Decimal,
        liquidation_fee_rate: Decimal,
        phase: str,
    ) -> dict[str, Any]:
        _decimal(observed_adverse_mark, "observed adverse mark", positive=True)
        _decimal(liquidation_fee_rate, "liquidation fee rate")
        if liquidation_fee_rate < ZERO:
            raise AccountingV2Error("liquidation fee rate cannot be negative")
        if phase not in {"open_mark_or_liquidation", "funding", "intrabar_mark_or_liquidation"}:
            raise AccountingV2Error("invalid liquidation phase")
        snapshot = self.margin(mark=observed_adverse_mark, maintenance_rate=maintenance_rate)
        quantity = self.state.perpetual_btc
        if quantity == ZERO or not snapshot.liquidated:
            raise AccountingV2Error("observed maintenance breach is required")
        assert self.state.average_perpetual_entry is not None
        realized = abs(quantity) * (ONE if quantity > ZERO else -ONE) * (
            observed_adverse_mark - self.state.average_perpetual_entry
        )
        price_pnl = quantity * (observed_adverse_mark - self.perpetual_mark)
        liquidation_fee = abs(quantity) * observed_adverse_mark * liquidation_fee_rate

        def mutation() -> None:
            self.perpetual_mark = observed_adverse_mark
            self.state.isolated_collateral += realized - liquidation_fee
            self.state.realized_pnl_memo += realized
            self.state.explicit_cost_memo += liquidation_fee
            self.state.perpetual_btc = ZERO
            self.state.average_perpetual_entry = None
            self.state.allocated_initial_margin_memo = ZERO
            self.state.exit_cost_reserve_memo = ZERO
            if self.state.isolated_collateral >= ZERO:
                self.state.quote_cash += self.state.isolated_collateral
            else:
                self.state.liabilities += -self.state.isolated_collateral
            self.state.isolated_collateral = ZERO
            self.state.invalidation_reason = "observed_liquidation"
            self.state.terminal = True

        return self._record(
            event_id=event_id,
            at=at,
            phase=phase,
            event_type="liquidation",
            mutation=mutation,
            perpetual_price_pnl=price_pnl,
            explicit_cost=liquidation_fee,
            details={
                "liquidation_fee_only": liquidation_fee,
                "ordinary_close_cost": ZERO,
                "observed_adverse_mark": observed_adverse_mark,
            },
        )


def validate_candle_fill_v2(
    *,
    decision_at: datetime,
    fill_at: datetime,
    exact_next_open: datetime,
    requested_quantity: Decimal,
    reported_filled_quantity: Decimal,
) -> None:
    timestamp_text(decision_at)
    timestamp_text(fill_at)
    timestamp_text(exact_next_open)
    _decimal(requested_quantity, "requested quantity")
    _decimal(reported_filled_quantity, "reported filled quantity")
    if exact_next_open <= decision_at or fill_at != exact_next_open:
        raise AccountingV2Error("candle execution must use the exact next open")
    if reported_filled_quantity not in {ZERO, requested_quantity}:
        raise AccountingV2Error("candle execution is all-or-none and cannot be partial")


def preflight_atomic_pair_v2(
    *,
    requested_gross_spot_btc: Decimal,
    spot_price: Decimal,
    perpetual_price: Decimal,
    spot_rules: RulesV2,
    perpetual_rules: RulesV2,
    spot_entry_base_fee_rate: Decimal,
    severe_spot_exit_base_fee_rate: Decimal,
) -> PairPreflightV2:
    for label, rate in (
        ("spot entry base fee rate", spot_entry_base_fee_rate),
        ("severe spot exit base fee rate", severe_spot_exit_base_fee_rate),
    ):
        _decimal(rate, label)
        if rate < ZERO:
            raise AccountingV2Error(f"{label} cannot be negative")
    spot_price = spot_rules.price(spot_price)
    perpetual_price = perpetual_rules.price(perpetual_price)
    gross_entry = spot_rules.quantity(requested_gross_spot_btc, spot_price)
    if gross_entry <= ZERO:
        raise AccountingV2Error("atomic pair spot leg must buy")
    entry_fee = gross_entry * spot_entry_base_fee_rate
    net_spot = gross_entry - entry_fee
    if net_spot <= ZERO:
        raise AccountingV2Error("entry base fee consumes spot inventory")
    requested_perp = -(net_spot * spot_price / perpetual_price)
    perp_entry = perpetual_rules.quantity(requested_perp, perpetual_price)
    gross_sale_unquantized = net_spot / (ONE + severe_spot_exit_base_fee_rate)
    gross_sale = spot_rules.quantity(-gross_sale_unquantized, spot_price)
    gross_sale = abs(gross_sale)
    neutralization_fee = gross_sale * severe_spot_exit_base_fee_rate
    if gross_sale + neutralization_fee != net_spot:
        raise AccountingV2Error("pair neutralization cannot leave exactly zero BTC after base fee")
    return PairPreflightV2(
        gross_spot_entry=gross_entry,
        entry_base_fee=entry_fee,
        net_spot_btc=net_spot,
        perpetual_entry_btc=perp_entry,
        neutralization_gross_spot_sale=gross_sale,
        neutralization_base_fee=neutralization_fee,
    )


def notional_mismatch_v2(
    *, spot_btc: Decimal, spot_price: Decimal, perpetual_btc: Decimal, perpetual_price: Decimal
) -> Decimal:
    for label, value in (
        ("spot BTC", spot_btc),
        ("spot price", spot_price),
        ("perpetual BTC", perpetual_btc),
        ("perpetual price", perpetual_price),
    ):
        _decimal(value, label)
    spot_notional = abs(spot_btc * spot_price)
    perpetual_notional = abs(perpetual_btc * perpetual_price)
    larger = max(spot_notional, perpetual_notional)
    return abs(spot_notional - perpetual_notional) / larger if larger else ZERO
