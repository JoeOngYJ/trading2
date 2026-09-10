"""Offline Decimal accounting primitives for synthetic BTC research fixtures.

This E1 kernel implements the frozen E0 accounting semantics.  It deliberately contains no
strategy, metrics, historical-data loader, network client, production signal, or order-routing
integration.  The separate E2 oracle must not import this module.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable, Mapping


ZERO = Decimal("0")
ONE = Decimal("1")
QUOTE_QUANTUM = Decimal("0.00000001")
UTC = timezone.utc


class UnifiedAccountingError(ValueError):
    """Raised before or during an invalid synthetic accounting transition."""


def require_decimal(value: Decimal, name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal):
        raise UnifiedAccountingError(f"{name} must be Decimal")
    if not value.is_finite():
        raise UnifiedAccountingError(f"{name} must be finite")
    if positive and value <= ZERO:
        raise UnifiedAccountingError(f"{name} must be positive")
    return value


def decimal_string(value: Decimal) -> str:
    """Return the E0 canonical plain Decimal representation."""
    require_decimal(value, "value")
    if value == ZERO:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def utc_string(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != ZERO:
        raise UnifiedAccountingError("timestamp must be timezone-aware UTC")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_string(value)
    if isinstance(value, datetime):
        return utc_string(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        raise UnifiedAccountingError("float is forbidden in canonical economic content")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical(value), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def content_digest(value: Mapping[str, Any], own_digest_field: str | None = None) -> str:
    material = dict(value)
    if own_digest_field is not None:
        material.pop(own_digest_field, None)
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class KernelLineage:
    experiment_id: str
    run_id: str
    scenario_id: str
    implementation_digest: str
    contract_digest: str
    execution_config_digest: str
    mandate_digest: str

    def __post_init__(self) -> None:
        if not self.experiment_id or not self.run_id or not self.scenario_id:
            raise UnifiedAccountingError("lineage identifiers are required")
        for name in (
            "implementation_digest",
            "contract_digest",
            "execution_config_digest",
            "mandate_digest",
        ):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise UnifiedAccountingError(f"{name} must be lowercase SHA-256")

    def as_dict(self) -> dict[str, str]:
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
class InstrumentRules:
    step_size: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal

    def __post_init__(self) -> None:
        for name in ("step_size", "minimum_quantity", "minimum_notional"):
            require_decimal(getattr(self, name), name, positive=True)

    def rounded_quantity(self, requested: Decimal, price: Decimal) -> Decimal:
        require_decimal(requested, "requested")
        require_decimal(price, "price", positive=True)
        sign = ONE if requested >= ZERO else -ONE
        rounded = (abs(requested) / self.step_size).to_integral_value(rounding=ROUND_DOWN)
        rounded *= self.step_size * sign
        if abs(rounded) < self.minimum_quantity or abs(rounded) * price < self.minimum_notional:
            raise UnifiedAccountingError("rounded order violates quantity or notional rules")
        return rounded


@dataclass(slots=True)
class AccountState:
    quote_cash: Decimal
    spot_quantity: Decimal = ZERO
    isolated_collateral: Decimal = ZERO
    perpetual_quantity: Decimal = ZERO
    average_perpetual_entry: Decimal | None = None
    fee_asset_balances: dict[str, Decimal] = field(default_factory=dict)
    liabilities: Decimal = ZERO
    realized_pnl_memo: Decimal = ZERO
    funding_memo: Decimal = ZERO
    explicit_costs_memo: Decimal = ZERO
    implicit_costs_memo: Decimal = ZERO
    allocated_initial_margin_memo: Decimal = ZERO
    exit_cost_reserve_memo: Decimal = ZERO
    invalidation_reason: str | None = None
    terminal: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "allocated_initial_margin_memo": self.allocated_initial_margin_memo,
            "average_perpetual_entry": self.average_perpetual_entry,
            "exit_cost_reserve_memo": self.exit_cost_reserve_memo,
            "explicit_costs_memo": self.explicit_costs_memo,
            "fee_asset_balances": dict(sorted(self.fee_asset_balances.items())),
            "funding_memo": self.funding_memo,
            "implicit_costs_memo": self.implicit_costs_memo,
            "invalidation_reason": self.invalidation_reason,
            "isolated_collateral": self.isolated_collateral,
            "liabilities": self.liabilities,
            "perpetual_quantity": self.perpetual_quantity,
            "quote_cash": self.quote_cash,
            "realized_pnl_memo": self.realized_pnl_memo,
            "spot_quantity": self.spot_quantity,
            "terminal": self.terminal,
        }


@dataclass(frozen=True, slots=True)
class MarginSnapshot:
    equity: Decimal
    maintenance: Decimal
    ratio: Decimal | None
    observed_liquidation: bool


class UnifiedBtcAccounting:
    """Deterministic transition kernel over one synthetic BTC spot/perpetual account."""

    _PHASES = {
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
        starting_quote_cash: Decimal,
        spot_mark: Decimal,
        perpetual_mark: Decimal,
        lineage: KernelLineage,
        fee_asset_balances: Mapping[str, Decimal] | None = None,
        fee_asset_marks: Mapping[str, Decimal] | None = None,
    ) -> None:
        require_decimal(starting_quote_cash, "starting_quote_cash", positive=True)
        require_decimal(spot_mark, "spot_mark", positive=True)
        require_decimal(perpetual_mark, "perpetual_mark", positive=True)
        balances = dict(fee_asset_balances or {})
        marks = dict(fee_asset_marks or {})
        for asset, amount in balances.items():
            require_decimal(amount, f"fee balance {asset}")
            if amount < ZERO or asset in {"BTC", "USDT"}:
                raise UnifiedAccountingError("third fee balances must be nonnegative and non-BTC/USDT")
            require_decimal(marks.get(asset), f"fee mark {asset}", positive=True)
        if set(marks) != set(balances):
            raise UnifiedAccountingError("fee balances and marks must have identical assets")
        self.state = AccountState(starting_quote_cash, fee_asset_balances=balances)
        self.spot_mark = spot_mark
        self.perpetual_mark = perpetual_mark
        self.fee_asset_marks = marks
        self.lineage = lineage
        self.events: list[dict[str, Any]] = []
        self._seen_ids: set[str] = set()
        self._last_key: tuple[datetime, int] | None = None

    @property
    def actionable_arm_id(self) -> str:
        return "no_trade"

    def state_digest(self) -> str:
        return content_digest(
            {
                "fee_asset_marks": self.fee_asset_marks,
                "perpetual_mark": self.perpetual_mark,
                "spot_mark": self.spot_mark,
                "state": self.state.as_dict(),
            }
        )

    def nav(self) -> Decimal:
        fee_value = sum(
            (amount * self.fee_asset_marks[asset] for asset, amount in self.state.fee_asset_balances.items()),
            ZERO,
        )
        unrealized = ZERO
        if self.state.perpetual_quantity != ZERO:
            assert self.state.average_perpetual_entry is not None
            unrealized = self.state.perpetual_quantity * (
                self.perpetual_mark - self.state.average_perpetual_entry
            )
        return (
            self.state.quote_cash
            + self.state.spot_quantity * self.spot_mark
            + fee_value
            + self.state.isolated_collateral
            + unrealized
            - self.state.liabilities
        )

    def _check_event(self, event_id: str, at: datetime, phase: str) -> None:
        if self.state.terminal:
            raise UnifiedAccountingError("terminal account rejects further events")
        if not event_id or event_id in self._seen_ids:
            raise UnifiedAccountingError("event ID is missing or duplicated")
        utc_string(at)
        if phase not in self._PHASES:
            raise UnifiedAccountingError("unknown event phase")
        key = (at, self._PHASES[phase])
        if self._last_key is not None and key < self._last_key:
            raise UnifiedAccountingError("events are reversed or phases are permuted")
        self._seen_ids.add(event_id)
        self._last_key = key

    def _transition(
        self,
        *,
        event_id: str,
        at: datetime,
        phase: str,
        kind: str,
        mutate: Callable[[], None],
        spot_price_pnl: Decimal = ZERO,
        perpetual_price_pnl: Decimal = ZERO,
        fee_asset_price_pnl: Decimal = ZERO,
        funding: Decimal = ZERO,
        explicit_cost: Decimal = ZERO,
        implicit_cost: Decimal = ZERO,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        for name, value in (
            ("spot_price_pnl", spot_price_pnl),
            ("perpetual_price_pnl", perpetual_price_pnl),
            ("fee_asset_price_pnl", fee_asset_price_pnl),
            ("funding", funding),
            ("explicit_cost", explicit_cost),
            ("implicit_cost", implicit_cost),
        ):
            require_decimal(value, name)
        self._check_event(event_id, at, phase)
        before_nav = self.nav()
        before_digest = self.state_digest()
        mutate()
        after_nav = self.nav()
        after_digest = self.state_digest()
        expected = (
            spot_price_pnl
            + perpetual_price_pnl
            + fee_asset_price_pnl
            + funding
            - explicit_cost
            - implicit_cost
        )
        residual = after_nav - before_nav - expected
        if abs(residual) > QUOTE_QUANTUM:
            raise UnifiedAccountingError(f"event accounting residual exceeds quantum: {residual}")
        row: dict[str, Any] = {
            **self.lineage.as_dict(),
            "actionable_arm_id": "no_trade",
            "after_NAV": after_nav,
            "after_state_digest": after_digest,
            "at": at,
            "before_NAV": before_nav,
            "before_state_digest": before_digest,
            "details": dict(details or {}),
            "event_accounting_residual": residual,
            "event_id": event_id,
            "event_sequence": len(self.events) + 1,
            "event_type": kind,
            "explicit_cost": explicit_cost,
            "fee_asset_price_pnl": fee_asset_price_pnl,
            "funding": funding,
            "implicit_cost": implicit_cost,
            "invalidation_reason": self.state.invalidation_reason,
            "perpetual_price_pnl": perpetual_price_pnl,
            "phase": phase,
            "spot_price_pnl": spot_price_pnl,
        }
        row["row_digest"] = content_digest(row, "row_digest")
        self.events.append(row)
        return row

    def _fee_quote_value(
        self, fee_amount: Decimal, fee_asset: str | None, fee_mark: Decimal | None
    ) -> Decimal:
        require_decimal(fee_amount, "fee_amount")
        if fee_amount < ZERO:
            raise UnifiedAccountingError("fee amount must be nonnegative")
        if fee_amount == ZERO:
            if fee_asset not in {None, "USDT", "BTC"} and fee_asset not in self.state.fee_asset_balances:
                raise UnifiedAccountingError("unsupported fee currency")
            return ZERO
        if fee_asset == "USDT":
            return fee_amount
        if fee_asset == "BTC":
            mark = self.spot_mark if fee_mark is None else require_decimal(fee_mark, "fee_mark", positive=True)
            return fee_amount * mark
        if fee_asset is None or fee_asset not in self.state.fee_asset_balances:
            raise UnifiedAccountingError("unsupported fee currency")
        mark = self.fee_asset_marks.get(fee_asset) if fee_mark is None else fee_mark
        require_decimal(mark, "fee_mark", positive=True)
        return fee_amount * mark

    def _apply_fee(self, fee_amount: Decimal, fee_asset: str | None, *, perpetual: bool) -> None:
        if fee_amount == ZERO:
            return
        if fee_asset == "USDT":
            if perpetual:
                self.state.isolated_collateral -= fee_amount
            else:
                self.state.quote_cash -= fee_amount
        elif fee_asset == "BTC":
            if perpetual:
                raise UnifiedAccountingError("BTC perpetual fee is unsupported in E1")
            if self.state.spot_quantity < fee_amount:
                raise UnifiedAccountingError("insufficient BTC fee balance")
            self.state.spot_quantity -= fee_amount
        elif fee_asset in self.state.fee_asset_balances:
            if self.state.fee_asset_balances[fee_asset] < fee_amount:
                raise UnifiedAccountingError("insufficient third-asset fee balance")
            self.state.fee_asset_balances[fee_asset] -= fee_amount
        else:
            raise UnifiedAccountingError("unsupported fee currency")

    def apply_spot_fill(
        self,
        *,
        event_id: str,
        at: datetime,
        signed_quantity: Decimal,
        price: Decimal,
        fee_amount: Decimal = ZERO,
        fee_asset: str | None = None,
        fee_mark: Decimal | None = None,
        implicit_cost: Decimal = ZERO,
        phase: str = "rebalance",
    ) -> dict[str, Any]:
        require_decimal(signed_quantity, "signed_quantity")
        require_decimal(price, "price", positive=True)
        require_decimal(implicit_cost, "implicit_cost")
        if signed_quantity == ZERO or implicit_cost < ZERO:
            raise UnifiedAccountingError("spot quantity must be nonzero and cost nonnegative")
        explicit = self._fee_quote_value(fee_amount, fee_asset, fee_mark)
        new_spot = self.state.spot_quantity + signed_quantity
        if signed_quantity < ZERO and self.state.spot_quantity < abs(signed_quantity) + (
            fee_amount if fee_asset == "BTC" else ZERO
        ):
            raise UnifiedAccountingError("spot sell exceeds available BTC including base fee")
        if signed_quantity > ZERO and fee_asset == "BTC" and fee_amount > signed_quantity:
            raise UnifiedAccountingError("base fee exceeds acquired BTC")
        quote_delta = -signed_quantity * price
        quote_fee = fee_amount if fee_asset == "USDT" else ZERO
        if self.state.quote_cash + quote_delta - quote_fee - implicit_cost < ZERO:
            raise UnifiedAccountingError("insufficient quote cash")
        if new_spot < ZERO:
            raise UnifiedAccountingError("spot inventory cannot be negative")

        def mutate() -> None:
            self.state.quote_cash += quote_delta
            self.state.spot_quantity = new_spot
            self._apply_fee(fee_amount, fee_asset, perpetual=False)
            self.state.quote_cash -= implicit_cost
            self.state.explicit_costs_memo += explicit
            self.state.implicit_costs_memo += implicit_cost

        return self._transition(
            event_id=event_id,
            at=at,
            phase=phase,
            kind="spot_fill",
            mutate=mutate,
            spot_price_pnl=signed_quantity * (self.spot_mark - price),
            explicit_cost=explicit,
            implicit_cost=implicit_cost,
            details={
                "fee_amount": fee_amount,
                "fee_asset": fee_asset,
                "price": price,
                "signed_quantity": signed_quantity,
            },
        )

    def apply_perpetual_fill(
        self,
        *,
        event_id: str,
        at: datetime,
        signed_quantity_delta: Decimal,
        price: Decimal,
        leverage: Decimal,
        fee_amount: Decimal = ZERO,
        fee_asset: str | None = None,
        fee_mark: Decimal | None = None,
        implicit_cost: Decimal = ZERO,
        exit_cost_rate: Decimal = ZERO,
        phase: str = "rebalance",
    ) -> dict[str, Any]:
        for name, value in (
            ("signed_quantity_delta", signed_quantity_delta),
            ("price", price),
            ("leverage", leverage),
            ("implicit_cost", implicit_cost),
            ("exit_cost_rate", exit_cost_rate),
        ):
            require_decimal(value, name)
        if signed_quantity_delta == ZERO or price <= ZERO or leverage <= ZERO:
            raise UnifiedAccountingError("perpetual quantity, price and leverage must be valid")
        if implicit_cost < ZERO or exit_cost_rate < ZERO:
            raise UnifiedAccountingError("costs must be nonnegative")
        if fee_asset == "BTC" and fee_amount != ZERO:
            raise UnifiedAccountingError("BTC perpetual fee is unsupported in E1")
        explicit = self._fee_quote_value(fee_amount, fee_asset, fee_mark)
        old = self.state.perpetual_quantity
        new = old + signed_quantity_delta
        if old != ZERO and new != ZERO and old * new < ZERO:
            raise UnifiedAccountingError("reversal must be an explicit close then new open")
        increasing = old == ZERO or old * signed_quantity_delta > ZERO
        if not increasing and abs(signed_quantity_delta) > abs(old):
            raise UnifiedAccountingError("reduction exceeds open perpetual quantity")
        margin_transfer = abs(signed_quantity_delta) * price / leverage if increasing else ZERO
        if self.state.quote_cash < margin_transfer:
            raise UnifiedAccountingError("insufficient quote cash for isolated collateral")
        old_entry = self.state.average_perpetual_entry
        old_allocated = self.state.allocated_initial_margin_memo
        old_abs = abs(old)

        def mutate() -> None:
            if increasing:
                self.state.quote_cash -= margin_transfer
                self.state.isolated_collateral += margin_transfer
                if old == ZERO:
                    self.state.average_perpetual_entry = price
                else:
                    assert old_entry is not None
                    self.state.average_perpetual_entry = (
                        old_abs * old_entry + abs(signed_quantity_delta) * price
                    ) / abs(new)
                self.state.perpetual_quantity = new
                self.state.allocated_initial_margin_memo += margin_transfer
            else:
                assert old_entry is not None
                closed = abs(signed_quantity_delta)
                realized = closed * (ONE if old > ZERO else -ONE) * (price - old_entry)
                self.state.isolated_collateral += realized
                self.state.realized_pnl_memo += realized
                self.state.perpetual_quantity = new
            self._apply_fee(fee_amount, fee_asset, perpetual=True)
            self.state.isolated_collateral -= implicit_cost
            self.state.explicit_costs_memo += explicit
            self.state.implicit_costs_memo += implicit_cost
            if not increasing:
                closed = abs(signed_quantity_delta)
                released_memo = old_allocated * closed / old_abs
                self.state.allocated_initial_margin_memo -= released_memo
                release = min(released_memo, max(self.state.isolated_collateral, ZERO))
                self.state.isolated_collateral -= release
                self.state.quote_cash += release
                if new == ZERO:
                    if self.state.isolated_collateral >= ZERO:
                        self.state.quote_cash += self.state.isolated_collateral
                    else:
                        self.state.liabilities += -self.state.isolated_collateral
                    self.state.isolated_collateral = ZERO
                    self.state.allocated_initial_margin_memo = ZERO
                    self.state.average_perpetual_entry = None
            self.state.exit_cost_reserve_memo = abs(new) * self.perpetual_mark * exit_cost_rate

        return self._transition(
            event_id=event_id,
            at=at,
            phase=phase,
            kind="perpetual_fill",
            mutate=mutate,
            perpetual_price_pnl=signed_quantity_delta * (self.perpetual_mark - price),
            explicit_cost=explicit,
            implicit_cost=implicit_cost,
            details={
                "fee_amount": fee_amount,
                "fee_asset": fee_asset,
                "leverage": leverage,
                "price": price,
                "signed_quantity_delta": signed_quantity_delta,
            },
        )

    def apply_funding(
        self,
        *,
        event_id: str,
        at: datetime,
        t_minus_quantity: Decimal,
        rate: Decimal,
        funding_mark: Decimal,
    ) -> dict[str, Any]:
        for name, value in (
            ("t_minus_quantity", t_minus_quantity),
            ("rate", rate),
            ("funding_mark", funding_mark),
        ):
            require_decimal(value, name)
        if funding_mark <= ZERO:
            raise UnifiedAccountingError("funding mark must be positive")
        cashflow = -t_minus_quantity * funding_mark * rate

        def mutate() -> None:
            if self.state.perpetual_quantity != ZERO:
                self.state.isolated_collateral += cashflow
            else:
                self.state.quote_cash += cashflow
                if self.state.quote_cash < ZERO:
                    self.state.liabilities += -self.state.quote_cash
                    self.state.quote_cash = ZERO
            self.state.funding_memo += cashflow

        return self._transition(
            event_id=event_id,
            at=at,
            phase="funding",
            kind="funding",
            mutate=mutate,
            funding=cashflow,
            details={
                "funding_mark": funding_mark,
                "rate": rate,
                "t_minus_quantity": t_minus_quantity,
            },
        )

    def mark_to_market(
        self,
        *,
        event_id: str,
        at: datetime,
        spot_mark: Decimal,
        perpetual_mark: Decimal,
        fee_asset_marks: Mapping[str, Decimal] | None = None,
        phase: str = "intrabar_mark_or_liquidation",
    ) -> dict[str, Any]:
        require_decimal(spot_mark, "spot_mark", positive=True)
        require_decimal(perpetual_mark, "perpetual_mark", positive=True)
        replacement = dict(self.fee_asset_marks if fee_asset_marks is None else fee_asset_marks)
        if set(replacement) != set(self.state.fee_asset_balances):
            raise UnifiedAccountingError("every third fee balance needs exactly one mark")
        for asset, mark in replacement.items():
            require_decimal(mark, f"fee mark {asset}", positive=True)
        spot_pnl = self.state.spot_quantity * (spot_mark - self.spot_mark)
        perp_pnl = self.state.perpetual_quantity * (perpetual_mark - self.perpetual_mark)
        fee_pnl = sum(
            (
                self.state.fee_asset_balances[asset]
                * (replacement[asset] - self.fee_asset_marks[asset])
                for asset in replacement
            ),
            ZERO,
        )

        def mutate() -> None:
            self.spot_mark = spot_mark
            self.perpetual_mark = perpetual_mark
            self.fee_asset_marks = replacement

        return self._transition(
            event_id=event_id,
            at=at,
            phase=phase,
            kind="mark_to_market",
            mutate=mutate,
            spot_price_pnl=spot_pnl,
            perpetual_price_pnl=perp_pnl,
            fee_asset_price_pnl=fee_pnl,
        )

    def margin_snapshot(self, *, mark: Decimal, maintenance_rate: Decimal) -> MarginSnapshot:
        require_decimal(mark, "mark", positive=True)
        require_decimal(maintenance_rate, "maintenance_rate")
        if maintenance_rate < ZERO:
            raise UnifiedAccountingError("maintenance rate must be nonnegative")
        unrealized = ZERO
        if self.state.perpetual_quantity != ZERO:
            assert self.state.average_perpetual_entry is not None
            unrealized = self.state.perpetual_quantity * (mark - self.state.average_perpetual_entry)
        equity = self.state.isolated_collateral + unrealized - self.state.exit_cost_reserve_memo
        maintenance = abs(self.state.perpetual_quantity) * mark * maintenance_rate
        ratio = equity / maintenance if maintenance > ZERO else None
        return MarginSnapshot(equity, maintenance, ratio, maintenance > ZERO and equity <= maintenance)

    def liquidate(
        self,
        *,
        event_id: str,
        at: datetime,
        observed_mark: Decimal,
        maintenance_rate: Decimal,
        liquidation_fee_rate: Decimal,
        phase: str,
        reason: str = "observed_liquidation",
    ) -> dict[str, Any]:
        require_decimal(observed_mark, "observed_mark", positive=True)
        require_decimal(liquidation_fee_rate, "liquidation_fee_rate")
        if phase not in {"open_mark_or_liquidation", "funding", "intrabar_mark_or_liquidation"}:
            raise UnifiedAccountingError("liquidation phase is invalid")
        snapshot = self.margin_snapshot(mark=observed_mark, maintenance_rate=maintenance_rate)
        if not snapshot.observed_liquidation or self.state.perpetual_quantity == ZERO:
            raise UnifiedAccountingError("liquidation requires an observed maintenance breach")
        quantity = self.state.perpetual_quantity
        entry = self.state.average_perpetual_entry
        assert entry is not None
        price_pnl = quantity * (observed_mark - self.perpetual_mark)
        realized = abs(quantity) * (ONE if quantity > ZERO else -ONE) * (observed_mark - entry)
        fee = abs(quantity) * observed_mark * liquidation_fee_rate

        def mutate() -> None:
            self.perpetual_mark = observed_mark
            self.state.isolated_collateral += realized - fee
            self.state.realized_pnl_memo += realized
            self.state.explicit_costs_memo += fee
            self.state.perpetual_quantity = ZERO
            self.state.average_perpetual_entry = None
            self.state.allocated_initial_margin_memo = ZERO
            self.state.exit_cost_reserve_memo = ZERO
            if self.state.isolated_collateral >= ZERO:
                self.state.quote_cash += self.state.isolated_collateral
            else:
                self.state.liabilities += -self.state.isolated_collateral
            self.state.isolated_collateral = ZERO
            self.state.invalidation_reason = reason
            self.state.terminal = True

        return self._transition(
            event_id=event_id,
            at=at,
            phase=phase,
            kind="liquidation",
            mutate=mutate,
            perpetual_price_pnl=price_pnl,
            explicit_cost=fee,
            details={"liquidation_fee_rate": liquidation_fee_rate, "observed_mark": observed_mark},
        )

    def invalidate(self, reason: str) -> None:
        if not reason:
            raise UnifiedAccountingError("invalidation reason is required")
        self.state.invalidation_reason = reason


def validate_candle_all_or_none(
    *,
    decision_at: datetime,
    fill_at: datetime,
    exact_next_open: datetime,
    requested_quantity: Decimal,
    reported_filled_quantity: Decimal,
) -> None:
    """Reject fabricated candle partial fills or forward-search execution."""
    utc_string(decision_at)
    utc_string(fill_at)
    utc_string(exact_next_open)
    require_decimal(requested_quantity, "requested_quantity")
    require_decimal(reported_filled_quantity, "reported_filled_quantity")
    if not decision_at < exact_next_open or fill_at != exact_next_open:
        raise UnifiedAccountingError("candle fill must use the exact next open")
    if reported_filled_quantity not in {ZERO, requested_quantity}:
        raise UnifiedAccountingError("candle adapter cannot report a partial fill")


def notional_mismatch_fraction(spot_quantity: Decimal, spot_price: Decimal, perp_quantity: Decimal, perp_price: Decimal) -> Decimal:
    for name, value in (
        ("spot_quantity", spot_quantity),
        ("spot_price", spot_price),
        ("perp_quantity", perp_quantity),
        ("perp_price", perp_price),
    ):
        require_decimal(value, name)
    spot_notional = abs(spot_quantity * spot_price)
    perp_notional = abs(perp_quantity * perp_price)
    larger = max(spot_notional, perp_notional)
    return abs(spot_notional - perp_notional) / larger if larger > ZERO else ZERO

