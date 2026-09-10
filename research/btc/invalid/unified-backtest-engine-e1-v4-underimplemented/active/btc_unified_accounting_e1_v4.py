"""Offline synthetic Decimal ledger for the unified BTC E1-v4 candidate.

This module is deliberately an accounting boundary, not a trading adapter.  It accepts
only explicitly synthetic point-in-time inputs, has no I/O or service dependencies, and
never emits an actionable arm other than ``no_trade``.

Economic semantics are inherited from the frozen E0 v1, v2, and v3 contracts.  In
particular, state is never rounded to a reconciliation quantum, perpetual collateral is
isolated, and pair close recovery commits fills in spot-first order without rollback.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


EXPERIMENT_ID = "btc-unified-backtest-engine-e1-v4-clean-lineage"
ACTIONABLE_ARM_ID = "no_trade"
RECONCILIATION_QUANTUM = Decimal("0.00000001")
DELTA_NEUTRAL_MANDATE_ID = "retail-btc-delta-neutral-research-v1"
DELTA_NEUTRAL_MANDATE_PATH = (
    "config/mandates/retail-btc-delta-neutral-research-v1.json"
)
DELTA_NEUTRAL_MANDATE_SHA256 = (
    "d95a53ee493862549b932dc5f80600a02a0e38e4ba1b3da0d79d0b0c5bb9eeba"
)
EXECUTION_CONFIG_SHA256 = (
    "a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36"
)
CONTRACT_SHA256 = (
    "d8b2852e6ef1e1c5b32bbf585f64683751d95480f9c87f890408708b58b5407c"
)
REQUIRED_SCENARIOS = frozenset(
    {
        "candle-primary-30bps-rt-v1",
        "candle-stress-40bps-rt-v1",
        "candle-severe-80bps-rt-v1",
    }
)
SEMANTIC_RUN_SETTING_FIELDS = (
    "adapter_id", "scenario_id", "selected_mandate_path", "selected_mandate_id",
    "selected_mandate_exact_file_sha256", "execution_config_exact_file_sha256",
    "spot_rules_digest", "perpetual_rules_digest", "spot_fee_policy_digest",
    "perpetual_fee_policy_digest", "severe_price_and_cost_bound_digest",
    "mismatch_limit", "arrival_timestamp", "source_digests",
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ContractViolation(ValueError):
    """A fail-closed rejection before an economic mutation."""


class ReconciliationError(AssertionError):
    """An event failed the frozen accounting identity."""


def D(value: Decimal | str | int) -> Decimal:
    """Construct a finite Decimal without permitting binary floats."""

    if isinstance(value, bool) or isinstance(value, float):
        raise ContractViolation("economic values must not be bool or float")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ContractViolation("invalid Decimal value") from exc
    if not result.is_finite():
        raise ContractViolation("economic values must be finite")
    return result


def decimal_string(value: Decimal | str | int) -> str:
    """Return the v1 canonical finite base-10 representation."""

    number = D(value)
    if number.is_zero():
        return "0"
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def utc_string(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractViolation("timestamp must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ContractViolation("timestamp must be UTC")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


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
        raise ContractViolation("float forbidden in canonical economic JSON")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ContractViolation(f"unsupported canonical type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def canonical_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_json_strict(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ContractViolation(f"duplicate JSON object key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ContractViolation(f"non-finite JSON constant: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ContractViolation(f"{label} must be lowercase SHA-256")
    return value


def synthetic_digest(label: str) -> str:
    """Deterministic digest helper for named synthetic fixtures only."""

    if not label or not isinstance(label, str):
        raise ContractViolation("synthetic label required")
    return sha256(("synthetic:" + label).encode("utf-8")).hexdigest()


def semantic_run_settings_digest(settings: Mapping[str, Any]) -> str:
    """Digest exactly the v3 semantic run-setting domain."""

    missing = [name for name in SEMANTIC_RUN_SETTING_FIELDS if name not in settings]
    extras = set(settings) - set(SEMANTIC_RUN_SETTING_FIELDS) - {
        "semantic_run_settings_digest"
    }
    if missing or extras:
        raise ContractViolation(
            f"semantic settings fields invalid; missing={missing}, extras={sorted(extras)}"
        )
    canonical = {name: settings[name] for name in SEMANTIC_RUN_SETTING_FIELDS}
    return canonical_digest(canonical)


@dataclass(frozen=True)
class Evidence:
    """A synthetic point-in-time value with complete causal lineage."""

    value: Decimal
    observed_at: datetime
    available_at: datetime
    source_path: str
    source_sha256: str
    segment_id: str
    rules_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", D(self.value))
        utc_string(self.observed_at)
        utc_string(self.available_at)
        if self.available_at < self.observed_at:
            raise ContractViolation("available_at precedes observed_at")
        if not self.source_path.startswith("synthetic://"):
            raise ContractViolation("E1 accepts synthetic:// evidence only")
        _digest(self.source_sha256, "source_sha256")
        _digest(self.rules_digest, "rules_digest")
        if not self.segment_id:
            raise ContractViolation("segment_id required")

    @property
    def lineage_digest(self) -> str:
        return canonical_digest(
            {
                "available_at": self.available_at,
                "observed_at": self.observed_at,
                "rules_digest": self.rules_digest,
                "segment_id": self.segment_id,
                "source_path": self.source_path,
                "source_sha256": self.source_sha256,
            }
        )

    def consume(self, at: datetime) -> Decimal:
        utc_string(at)
        if self.available_at > at:
            raise ContractViolation("future/unavailable evidence")
        return self.value


def synthetic_evidence(
    value: Decimal | str | int,
    at: datetime,
    label: str,
    *,
    available_at: datetime | None = None,
    segment_id: str = "synthetic-segment-1",
    rules_digest: str | None = None,
) -> Evidence:
    available = available_at or at
    return Evidence(
        D(value), at, available, f"synthetic://{label}", synthetic_digest(label),
        segment_id, rules_digest or synthetic_digest(label + ":rules"),
    )


@dataclass(frozen=True)
class InstrumentRules:
    quantity_step: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal
    price_tick: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        for name in (
            "quantity_step", "minimum_quantity", "minimum_notional", "price_tick"
        ):
            value = D(getattr(self, name))
            object.__setattr__(self, name, value)
            if value <= 0:
                raise ContractViolation(f"{name} must be positive")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "minimum_notional": self.minimum_notional,
                "minimum_quantity": self.minimum_quantity,
                "price_tick": self.price_tick,
                "quantity_step": self.quantity_step,
                "rounding": "ROUND_DOWN_absolute_then_restore_sign",
            }
        )

    def quantity(self, requested: Decimal | str | int) -> Decimal:
        requested_d = D(requested)
        sign = Decimal("-1") if requested_d < 0 else Decimal("1")
        units = (abs(requested_d) / self.quantity_step).to_integral_value(
            rounding=ROUND_DOWN
        )
        rounded = units * self.quantity_step * sign
        return Decimal("0") if rounded.is_zero() else rounded

    def price(self, requested: Decimal | str | int) -> Decimal:
        price_d = D(requested)
        if price_d <= 0:
            raise ContractViolation("price must be positive")
        units = (price_d / self.price_tick).to_integral_value(rounding=ROUND_DOWN)
        rounded = units * self.price_tick
        if rounded <= 0:
            raise ContractViolation("price quantizes non-positive")
        return rounded

    def validate(self, quantity: Decimal, price: Decimal) -> None:
        quantity_d, price_d = abs(D(quantity)), D(price)
        if quantity_d.is_zero():
            raise ContractViolation("quantity quantizes to zero")
        if self.quantity(quantity_d) != quantity_d:
            raise ContractViolation("quantity is not rule-quantized")
        if quantity_d < self.minimum_quantity:
            raise ContractViolation("quantity below minimum")
        if quantity_d * price_d < self.minimum_notional:
            raise ContractViolation("notional below minimum")


@dataclass(frozen=True)
class FeePolicy:
    rate: Decimal
    asset: str = "quote"
    tax_rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", D(self.rate))
        object.__setattr__(self, "tax_rate", D(self.tax_rate))
        if self.rate < 0 or self.tax_rate < 0:
            raise ContractViolation("fee/tax rate must be nonnegative")
        if not self.asset:
            raise ContractViolation("fee asset required")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {"asset": self.asset, "rate": self.rate, "tax_rate": self.tax_rate}
        )

    def amounts(
        self,
        quantity: Decimal,
        price: Decimal,
        *,
        conversion_mark: Decimal | None = None,
    ) -> tuple[Decimal, Decimal]:
        quote = abs(D(quantity)) * D(price) * (self.rate + self.tax_rate)
        if self.asset == "quote":
            return quote, quote
        conversion = D(conversion_mark) if conversion_mark is not None else None
        if conversion is None or conversion <= 0:
            raise ContractViolation("fee-asset conversion mark unavailable")
        return quote / conversion, quote


@dataclass(frozen=True)
class RunBindings:
    run_id: str
    scenario_id: str
    adapter_id: str
    implementation_digest: str
    selected_mandate_path: str
    selected_mandate_id: str
    selected_mandate_exact_file_sha256: str
    execution_config_exact_file_sha256: str = EXECUTION_CONFIG_SHA256
    contract_digest: str = CONTRACT_SHA256
    actionable_arm_id: str = ACTIONABLE_ARM_ID

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ContractViolation("run_id required")
        if self.scenario_id not in REQUIRED_SCENARIOS:
            raise ContractViolation("one frozen execution scenario is required")
        if self.adapter_id not in {"candle_OHLC", "qualified_quote_or_L2"}:
            raise ContractViolation("unsupported adapter")
        if self.actionable_arm_id != ACTIONABLE_ARM_ID:
            raise ContractViolation("only no_trade is actionable")
        for name in (
            "implementation_digest", "selected_mandate_exact_file_sha256",
            "execution_config_exact_file_sha256", "contract_digest",
        ):
            _digest(getattr(self, name), name)
        if self.execution_config_exact_file_sha256 != EXECUTION_CONFIG_SHA256:
            raise ContractViolation("execution-config binding mismatch")
        allowed = {
            (
                "config/retail_mandate.json", "retail-btc-spot-v2",
                "7e34cfb0928b4373bbf52b5c5505f63a2b19e674124059191c1b6c62ec129041",
            ),
            (
                "config/mandates/retail-btc-directional-perpetual-research-v1.json",
                "retail-btc-directional-perpetual-research-v1",
                "1b5d492f12f71ebe28e1bdfbd0b5916bcf0ad285b483cb10bf8770504371165d",
            ),
            (
                DELTA_NEUTRAL_MANDATE_PATH, DELTA_NEUTRAL_MANDATE_ID,
                DELTA_NEUTRAL_MANDATE_SHA256,
            ),
        }
        selected = (
            self.selected_mandate_path, self.selected_mandate_id,
            self.selected_mandate_exact_file_sha256,
        )
        if selected not in allowed:
            raise ContractViolation("selected mandate triple is not frozen")

    def row_lineage(self) -> dict[str, str]:
        return {
            "actionable_arm_id": ACTIONABLE_ARM_ID,
            "contract_digest": self.contract_digest,
            "execution_config_digest": self.execution_config_exact_file_sha256,
            "experiment_id": EXPERIMENT_ID,
            "implementation_digest": self.implementation_digest,
            "mandate_digest": self.selected_mandate_exact_file_sha256,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
        }


@dataclass
class LedgerState:
    quote_cash: Decimal
    spot_quantity: Decimal = Decimal("0")
    isolated_collateral: Decimal = Decimal("0")
    perpetual_quantity: Decimal = Decimal("0")
    average_perpetual_entry: Decimal | None = None
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    accrued_funding: Decimal = Decimal("0")
    allocated_initial_margin_memo: Decimal = Decimal("0")
    explicit_costs: Decimal = Decimal("0")
    implicit_costs: Decimal = Decimal("0")
    exit_cost_reserve_memo: Decimal = Decimal("0")
    fee_asset_balances: dict[str, Decimal] = field(default_factory=dict)
    fee_asset_marks: dict[str, Decimal] = field(default_factory=dict)
    liabilities: Decimal = Decimal("0")
    spot_mark: Decimal | None = None
    perpetual_mark: Decimal | None = None
    state: str = "valid"
    invalidation_reason: str | None = None
    pending_safety_actions: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        scalar_names = (
            "quote_cash", "spot_quantity", "isolated_collateral",
            "perpetual_quantity", "realized_pnl", "unrealized_pnl",
            "accrued_funding", "allocated_initial_margin_memo", "explicit_costs",
            "implicit_costs", "exit_cost_reserve_memo", "liabilities",
        )
        for name in scalar_names:
            setattr(self, name, D(getattr(self, name)))
        if self.average_perpetual_entry is not None:
            self.average_perpetual_entry = D(self.average_perpetual_entry)
        if self.spot_mark is not None:
            self.spot_mark = D(self.spot_mark)
        if self.perpetual_mark is not None:
            self.perpetual_mark = D(self.perpetual_mark)
        self.fee_asset_balances = {
            key: D(value) for key, value in self.fee_asset_balances.items()
        }
        self.fee_asset_marks = {
            key: D(value) for key, value in self.fee_asset_marks.items()
        }
        self.validate()

    def validate(self) -> None:
        if self.spot_quantity < 0:
            raise ContractViolation("spot borrowing is forbidden")
        for name in (
            "isolated_collateral", "allocated_initial_margin_memo",
            "explicit_costs", "implicit_costs", "exit_cost_reserve_memo",
            "liabilities",
        ):
            if getattr(self, name) < 0:
                raise ContractViolation(f"{name} cannot be negative")
        if self.perpetual_quantity.is_zero():
            if self.average_perpetual_entry is not None:
                raise ContractViolation("flat perpetual average entry must be null")
            if self.allocated_initial_margin_memo != 0:
                raise ContractViolation("flat perpetual margin memo must be zero")
            if self.exit_cost_reserve_memo != 0:
                raise ContractViolation("flat perpetual reserve must be zero")
        elif self.average_perpetual_entry is None or self.average_perpetual_entry <= 0:
            raise ContractViolation("open perpetual requires positive average entry")
        if self.spot_quantity and (self.spot_mark is None or self.spot_mark <= 0):
            raise ContractViolation("spot inventory requires a positive mark")
        if self.perpetual_quantity and (
            self.perpetual_mark is None or self.perpetual_mark <= 0
        ):
            raise ContractViolation("perpetual exposure requires a positive mark")
        for asset, balance in self.fee_asset_balances.items():
            if balance < 0:
                raise ContractViolation("fee-asset balance cannot be negative")
            if balance and (asset not in self.fee_asset_marks or self.fee_asset_marks[asset] <= 0):
                raise ContractViolation("nonzero fee asset requires a mark")

    def economic_dict(self) -> dict[str, Any]:
        return {
            "accrued_funding": self.accrued_funding,
            "allocated_initial_margin_memo": self.allocated_initial_margin_memo,
            "average_perpetual_entry": self.average_perpetual_entry,
            "exit_cost_reserve_memo": self.exit_cost_reserve_memo,
            "explicit_costs": self.explicit_costs,
            "fee_asset_balances": dict(sorted(self.fee_asset_balances.items())),
            "fee_asset_marks": dict(sorted(self.fee_asset_marks.items())),
            "implicit_costs": self.implicit_costs,
            "invalidation_reason": self.invalidation_reason,
            "isolated_collateral": self.isolated_collateral,
            "liabilities": self.liabilities,
            "pending_safety_actions": self.pending_safety_actions,
            "perpetual_mark": self.perpetual_mark,
            "perpetual_quantity": self.perpetual_quantity,
            "quote_cash": self.quote_cash,
            "realized_pnl": self.realized_pnl,
            "spot_mark": self.spot_mark,
            "spot_quantity": self.spot_quantity,
            "state": self.state,
            "unrealized_pnl": self.unrealized_pnl,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.economic_dict())

    @property
    def nav(self) -> Decimal:
        spot_value = self.spot_quantity * (self.spot_mark or Decimal("0"))
        third_value = sum(
            (balance * self.fee_asset_marks[asset]
             for asset, balance in self.fee_asset_balances.items()),
            Decimal("0"),
        )
        return (
            self.quote_cash + spot_value + third_value + self.isolated_collateral
            + self.unrealized_pnl - self.liabilities
        )


@dataclass(frozen=True)
class PairOutcome:
    """One adapter-realizable (spot fill, perpetual fill) pair-close path."""

    spot_fill_quantity: Decimal
    perpetual_fill_quantity: Decimal
    spot_price: Decimal
    perpetual_price: Decimal
    severe_perpetual_price: Decimal | None

    def __post_init__(self) -> None:
        for name in ("spot_fill_quantity", "perpetual_fill_quantity", "spot_price",
                     "perpetual_price"):
            object.__setattr__(self, name, D(getattr(self, name)))
        if self.severe_perpetual_price is not None:
            object.__setattr__(self, "severe_perpetual_price", D(self.severe_perpetual_price))


@dataclass
class PairCloseResult:
    actual_spot_reduction: Decimal
    intended_perpetual_filled: Decimal
    created_residual_naked_short: Decimal
    severe_residual_filled: Decimal
    remaining_quantity_mismatch: Decimal | None
    remaining_notional_mismatch: Decimal | None
    status: str
    invalidation_reason: str | None


class SyntheticLedger:
    """Exact-Decimal BTC spot/linear-perpetual event ledger."""

    def __init__(
        self,
        state: LedgerState,
        bindings: RunBindings,
        *,
        leverage: Decimal | str | int,
        perpetual_exit_cost_rate: Decimal | str | int,
        maintenance_rate: Decimal | str | int = "0.005",
        liquidation_fee_rate: Decimal | str | int = "0.01",
        zero_exit_reserve_fixture: bool = False,
    ) -> None:
        self.state = deepcopy(state)
        self.bindings = bindings
        self.leverage = D(leverage)
        self.exit_cost_rate = D(perpetual_exit_cost_rate)
        self.maintenance_rate = D(maintenance_rate)
        self.liquidation_fee_rate = D(liquidation_fee_rate)
        if self.leverage <= 0:
            raise ContractViolation("leverage must be positive")
        if min(self.exit_cost_rate, self.maintenance_rate, self.liquidation_fee_rate) < 0:
            raise ContractViolation("margin/cost rates must be nonnegative")
        if self.exit_cost_rate == 0 and not zero_exit_reserve_fixture:
            raise ContractViolation("zero exit reserve requires explicit fixture metadata")
        self.events: list[dict[str, Any]] = []
        self.decision_ledger: list[dict[str, Any]] = []
        self.order_ledger: list[dict[str, Any]] = []
        self.fill_ledger: list[dict[str, Any]] = []
        self.funding_ledger: list[dict[str, Any]] = []
        self.account_ledger: list[dict[str, Any]] = []
        self.closed_episode_ledger: list[dict[str, Any]] = []
        self._sequence = 0
        self._last_timestamp: datetime | None = None
        self._seen_logical_events: set[str] = set()
        self._high_water_nav = self.state.nav
        self._day_start_nav = self.state.nav
        self._current_day = None
        self.starting_nav = self.state.nav
        self._refresh_unrealized()
        self._refresh_reserve()
        self.state.validate()
        self.starting_nav = self.state.nav

    def _evidence(self, at: datetime, evidence: Sequence[Evidence]) -> tuple[str, str]:
        if not evidence:
            return "explicit_not_applicable", "explicit_not_applicable"
        segments = set()
        for item in evidence:
            item.consume(at)
            segments.add(item.segment_id)
        if len(segments) != 1:
            raise ContractViolation("unannounced segment crossing")
        return (
            canonical_digest([item.lineage_digest for item in evidence]),
            canonical_digest([item.rules_digest for item in evidence]),
        )

    def _begin(self, event_id: str, at: datetime) -> tuple[LedgerState, Decimal]:
        utc_string(at)
        if event_id in self._seen_logical_events:
            raise ContractViolation("duplicate logical event")
        if self._last_timestamp is not None and at < self._last_timestamp:
            raise ContractViolation("event timestamps must be nondecreasing")
        self._seen_logical_events.add(event_id)
        self._last_timestamp = at
        return deepcopy(self.state), self.state.nav

    def _finish(
        self,
        event_id: str,
        event_type: str,
        at: datetime,
        before: LedgerState,
        before_nav: Decimal,
        *,
        spot_price_pnl: Decimal = Decimal("0"),
        perpetual_price_pnl: Decimal = Decimal("0"),
        funding_cashflow: Decimal = Decimal("0"),
        explicit_cost: Decimal = Decimal("0"),
        implicit_cost: Decimal = Decimal("0"),
        external_cashflow: Decimal = Decimal("0"),
        evidence: Sequence[Evidence] = (),
        details: Mapping[str, Any] | None = None,
        target: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.state.validate()
        source_digest, rules_digest = self._evidence(at, evidence)
        delta_nav = self.state.nav - before_nav
        expected = (
            D(spot_price_pnl) + D(perpetual_price_pnl) + D(funding_cashflow)
            - D(explicit_cost) - D(implicit_cost) + D(external_cashflow)
        )
        residual = delta_nav - expected
        if abs(residual) > RECONCILIATION_QUANTUM:
            raise ReconciliationError(
                f"{event_id} residual {decimal_string(residual)} exceeds quantum"
            )
        self._sequence += 1
        row: dict[str, Any] = {
            **self.bindings.row_lineage(),
            "after_state_digest": self.state.digest,
            "before_state_digest": before.digest,
            "event_accounting_residual": residual,
            "event_at": at,
            "event_id": event_id,
            "event_sequence": self._sequence,
            "event_type": event_type,
            "explicit_cost": D(explicit_cost),
            "external_cashflow": D(external_cashflow),
            "funding_cashflow": D(funding_cashflow),
            "implicit_cost": D(implicit_cost),
            "invalidation_reason": self.state.invalidation_reason,
            "perpetual_price_pnl": D(perpetual_price_pnl),
            "rules_digest": rules_digest,
            "source_digest": source_digest,
            "spot_price_pnl": D(spot_price_pnl),
        }
        if details:
            row.update(details)
        row["row_digest"] = canonical_digest(row)
        canonical = _canonical(row)
        self.events.append(canonical)
        if target is not None:
            target.append(canonical)
        if self.state.nav > self._high_water_nav:
            self._high_water_nav = self.state.nav
        return canonical

    def _refresh_unrealized(self) -> None:
        if self.state.perpetual_quantity == 0:
            self.state.unrealized_pnl = Decimal("0")
        else:
            if self.state.perpetual_mark is None or self.state.average_perpetual_entry is None:
                raise ContractViolation("cannot mark perpetual without price and entry")
            self.state.unrealized_pnl = self.state.perpetual_quantity * (
                self.state.perpetual_mark - self.state.average_perpetual_entry
            )

    def _refresh_reserve(self) -> None:
        if self.state.perpetual_quantity == 0:
            self.state.exit_cost_reserve_memo = Decimal("0")
        else:
            if self.state.perpetual_mark is None:
                raise ContractViolation("reserve requires official perpetual mark")
            self.state.exit_cost_reserve_memo = (
                abs(self.state.perpetual_quantity) * self.state.perpetual_mark
                * self.exit_cost_rate
            )

    def _invalidate(self, reason: str, pending: Mapping[str, Any] | None = None) -> None:
        self.state.state = "invalid_unknown"
        if self.state.invalidation_reason is None:
            self.state.invalidation_reason = reason
        if pending is not None:
            self.state.pending_safety_actions.append(_canonical(dict(pending)))

    def mark(
        self,
        event_id: str,
        at: datetime,
        *,
        spot: Evidence | None = None,
        perpetual: Evidence | None = None,
        adverse: bool = False,
        auto_liquidate: bool = False,
    ) -> dict[str, Any]:
        before, before_nav = self._begin(event_id, at)
        evidence = tuple(item for item in (spot, perpetual) if item is not None)
        spot_pnl = Decimal("0")
        perp_pnl = Decimal("0")
        if spot is not None:
            new_spot = spot.consume(at)
            if new_spot <= 0:
                raise ContractViolation("spot mark must be positive")
            if self.state.spot_mark is not None:
                spot_pnl = self.state.spot_quantity * (new_spot - self.state.spot_mark)
            self.state.spot_mark = new_spot
        if perpetual is not None:
            new_perp = perpetual.consume(at)
            if new_perp <= 0:
                raise ContractViolation("perpetual mark must be positive")
            if self.state.perpetual_mark is not None:
                perp_pnl = self.state.perpetual_quantity * (
                    new_perp - self.state.perpetual_mark
                )
            self.state.perpetual_mark = new_perp
            self._refresh_unrealized()
            self._refresh_reserve()
        row = self._finish(
            event_id, "mark", at, before, before_nav,
            spot_price_pnl=spot_pnl, perpetual_price_pnl=perp_pnl,
            evidence=evidence, details={"adverse_mark": adverse},
            target=self.account_ledger,
        )
        if auto_liquidate and self.is_liquidated():
            self.liquidate(event_id + ":liquidation", at, evidence=evidence)
        return row

    @property
    def margin_equity(self) -> Decimal:
        return (
            self.state.isolated_collateral + self.state.unrealized_pnl
            - self.state.exit_cost_reserve_memo
        )

    @property
    def maintenance_requirement(self) -> Decimal:
        if self.state.perpetual_quantity == 0:
            return Decimal("0")
        return (
            abs(self.state.perpetual_quantity) * D(self.state.perpetual_mark)
            * self.maintenance_rate
        )

    def is_liquidated(self) -> bool:
        return (
            self.state.perpetual_quantity != 0
            and self.margin_equity <= self.maintenance_requirement
        )

    def _fee(
        self, policy: FeePolicy, quantity: Decimal, price: Decimal,
        conversion_mark: Decimal | None,
    ) -> tuple[Decimal, Decimal]:
        return policy.amounts(quantity, price, conversion_mark=conversion_mark)

    def _debit_fee(
        self,
        instrument: str,
        side: str,
        policy: FeePolicy,
        native: Decimal,
        quote: Decimal,
    ) -> None:
        if policy.asset == "quote":
            if instrument == "perpetual":
                if self.state.isolated_collateral < native:
                    raise ContractViolation("perpetual quote fee not funded by collateral")
                self.state.isolated_collateral -= native
            else:
                if self.state.quote_cash < native:
                    raise ContractViolation("spot quote fee not funded")
                self.state.quote_cash -= native
        elif policy.asset == "base":
            if instrument != "spot":
                raise ContractViolation("base fee unsupported for perpetual")
            if side == "buy":
                if self.state.spot_quantity < native:
                    raise ContractViolation("base fee exceeds bought inventory")
                self.state.spot_quantity -= native
            else:
                if self.state.spot_quantity < native:
                    raise ContractViolation("base fee exceeds remaining inventory")
                self.state.spot_quantity -= native
        else:
            balance = self.state.fee_asset_balances.get(policy.asset)
            if balance is None or balance < native:
                raise ContractViolation("third fee asset insufficient")
            if policy.asset not in self.state.fee_asset_marks:
                raise ContractViolation("third fee asset mark missing")
            self.state.fee_asset_balances[policy.asset] = balance - native
        self.state.explicit_costs += quote

    def _preflight_fee_asset(
        self, policy: FeePolicy, native: Decimal, conversion_mark: Decimal | None
    ) -> None:
        if policy.asset in {"quote", "base"}:
            return
        balance = self.state.fee_asset_balances.get(policy.asset)
        if balance is None or balance < native:
            raise ContractViolation("third fee asset insufficient")
        bound_mark = self.state.fee_asset_marks.get(policy.asset)
        if bound_mark is None or conversion_mark is None or bound_mark != conversion_mark:
            raise ContractViolation("third fee asset point-in-time mark mismatch")

    def spot_fill(
        self,
        event_id: str,
        at: datetime,
        *,
        signed_quantity: Decimal | str | int,
        price: Evidence,
        rules: InstrumentRules,
        fee: FeePolicy = FeePolicy(Decimal("0")),
        fee_conversion: Evidence | None = None,
        implicit_cost_quote: Decimal | str | int = "0",
        order_id: str | None = None,
    ) -> dict[str, Any]:
        quantity = rules.quantity(D(signed_quantity))
        execution_price = price.consume(at)
        if price.rules_digest != rules.digest:
            raise ContractViolation("spot rule lineage mismatch")
        rules.validate(quantity, execution_price)
        if self.state.spot_mark != execution_price:
            raise ContractViolation("mark to accounting fill price before fill")
        implicit = D(implicit_cost_quote)
        if implicit < 0:
            raise ContractViolation("implicit cost must be nonnegative")
        conversion = None if fee_conversion is None else fee_conversion.consume(at)
        native_fee, quote_fee = self._fee(fee, quantity, execution_price, conversion)
        self._preflight_fee_asset(fee, native_fee, conversion)
        gross = abs(quantity)
        side = "buy" if quantity > 0 else "sell"
        if side == "buy":
            needed = gross * execution_price + implicit
            if fee.asset == "quote":
                needed += native_fee
            if self.state.quote_cash < needed:
                raise ContractViolation("insufficient quote cash")
            if fee.asset == "base" and native_fee > gross:
                raise ContractViolation("base fee exceeds bought inventory")
        else:
            inventory_needed = gross + (native_fee if fee.asset == "base" else Decimal("0"))
            if self.state.spot_quantity < inventory_needed:
                raise ContractViolation("spot sell would borrow BTC")
            cash_after_sale = self.state.quote_cash + gross * execution_price
            quote_debits = implicit + (native_fee if fee.asset == "quote" else Decimal("0"))
            if cash_after_sale < quote_debits:
                raise ContractViolation("spot sale costs not funded")
        before, before_nav = self._begin(event_id, at)
        if side == "buy":
            self.state.quote_cash -= gross * execution_price
            self.state.spot_quantity += gross
        else:
            self.state.spot_quantity -= gross
            self.state.quote_cash += gross * execution_price
        self._debit_fee("spot", side, fee, native_fee, quote_fee)
        if self.state.quote_cash < implicit:
            raise ContractViolation("implicit spot cost not funded")
        self.state.quote_cash -= implicit
        self.state.implicit_costs += implicit
        evidence = (price,) + (() if fee_conversion is None else (fee_conversion,))
        row = self._finish(
            event_id, "fill", at, before, before_nav,
            explicit_cost=quote_fee, implicit_cost=implicit, evidence=evidence,
            details={
                "accounting_fill_price": execution_price,
                "explicit_fee_asset": fee.asset,
                "explicit_fee_native": native_fee,
                "explicit_fee_quote_equivalent": quote_fee,
                "fill_at": at,
                "fill_id": event_id,
                "instrument": "BTC_USDT_spot",
                "order_id": order_id or event_id,
                "post_fill_position": self.state.spot_quantity,
                "signed_quantity": quantity,
                "implicit_cost_quote": implicit,
            },
            target=self.fill_ledger,
        )
        return row

    def _settle_flat_collateral(self) -> None:
        if self.state.isolated_collateral >= 0:
            self.state.quote_cash += self.state.isolated_collateral
        else:
            self.state.liabilities += -self.state.isolated_collateral
        self.state.isolated_collateral = Decimal("0")
        self.state.allocated_initial_margin_memo = Decimal("0")
        self.state.exit_cost_reserve_memo = Decimal("0")

    def perpetual_fill(
        self,
        event_id: str,
        at: datetime,
        *,
        signed_quantity: Decimal | str | int,
        price: Evidence,
        rules: InstrumentRules,
        fee: FeePolicy = FeePolicy(Decimal("0")),
        fee_conversion: Evidence | None = None,
        implicit_cost_quote: Decimal | str | int = "0",
        order_id: str | None = None,
    ) -> list[dict[str, Any]]:
        trade = rules.quantity(D(signed_quantity))
        execution_price = price.consume(at)
        if price.rules_digest != rules.digest:
            raise ContractViolation("perpetual rule lineage mismatch")
        rules.validate(trade, execution_price)
        if self.state.perpetual_mark != execution_price:
            raise ContractViolation("mark to accounting fill price before fill")
        incoming = self.state.perpetual_quantity
        if incoming and incoming * trade < 0 and abs(trade) > abs(incoming):
            closing_trade = -incoming
            opening_trade = trade + incoming
            rows = self.perpetual_fill(
                event_id + ":close", at, signed_quantity=closing_trade, price=price,
                rules=rules, fee=fee, fee_conversion=fee_conversion,
                implicit_cost_quote=D(implicit_cost_quote) * abs(closing_trade) / abs(trade),
                order_id=order_id or event_id,
            )
            rows.extend(self.perpetual_fill(
                event_id + ":open", at, signed_quantity=opening_trade, price=price,
                rules=rules, fee=fee, fee_conversion=fee_conversion,
                implicit_cost_quote=D(implicit_cost_quote) * abs(opening_trade) / abs(trade),
                order_id=order_id or event_id,
            ))
            return rows
        implicit = D(implicit_cost_quote)
        if implicit < 0:
            raise ContractViolation("implicit cost must be nonnegative")
        conversion = None if fee_conversion is None else fee_conversion.consume(at)
        native_fee, quote_fee = self._fee(fee, trade, execution_price, conversion)
        self._preflight_fee_asset(fee, native_fee, conversion)
        increasing = incoming == 0 or incoming * trade > 0
        margin = Decimal("0")
        released_memo = Decimal("0")
        realized = Decimal("0")
        if increasing:
            margin = abs(trade) * execution_price / self.leverage
            if self.state.quote_cash < margin:
                raise ContractViolation("incremental initial margin not funded")
            projected_collateral = self.state.isolated_collateral + margin
        else:
            close_quantity = abs(trade)
            if close_quantity > abs(incoming):
                raise ContractViolation("reduction would cross zero")
            pre_quantity = abs(incoming)
            released_memo = (
                self.state.allocated_initial_margin_memo * close_quantity / pre_quantity
            )
            realized = close_quantity * (Decimal("1") if incoming > 0 else Decimal("-1")) * (
                execution_price - D(self.state.average_perpetual_entry)
            )
            projected_collateral = self.state.isolated_collateral + realized
        collateral_debits = implicit + (native_fee if fee.asset == "quote" else Decimal("0"))
        if projected_collateral < collateral_debits:
            raise ContractViolation("perpetual costs not funded by isolated collateral")
        before, before_nav = self._begin(event_id, at)
        if increasing:
            self.state.quote_cash -= margin
            self.state.isolated_collateral += margin
            self.state.allocated_initial_margin_memo += margin
            if incoming == 0:
                self.state.average_perpetual_entry = execution_price
            else:
                old_abs = abs(incoming)
                self.state.average_perpetual_entry = (
                    old_abs * D(self.state.average_perpetual_entry)
                    + abs(trade) * execution_price
                ) / (old_abs + abs(trade))
            self.state.perpetual_quantity += trade
        else:
            self.state.isolated_collateral += realized
            self.state.realized_pnl += realized
            self.state.perpetual_quantity += trade
            self.state.allocated_initial_margin_memo -= released_memo
        self._debit_fee("perpetual", "buy" if trade > 0 else "sell", fee,
                        native_fee, quote_fee)
        self.state.isolated_collateral -= implicit
        self.state.implicit_costs += implicit
        if not increasing:
            if self.state.perpetual_quantity == 0:
                self.state.average_perpetual_entry = None
                self.state.unrealized_pnl = Decimal("0")
                self._settle_flat_collateral()
            else:
                cash_release = min(released_memo, max(self.state.isolated_collateral, Decimal("0")))
                self.state.isolated_collateral -= cash_release
                self.state.quote_cash += cash_release
                self._refresh_unrealized()
        else:
            self._refresh_unrealized()
        self._refresh_reserve()
        evidence = (price,) + (() if fee_conversion is None else (fee_conversion,))
        row = self._finish(
            event_id, "fill", at, before, before_nav,
            explicit_cost=quote_fee, implicit_cost=implicit, evidence=evidence,
            details={
                "accounting_fill_price": execution_price,
                "explicit_fee_asset": fee.asset,
                "explicit_fee_native": native_fee,
                "explicit_fee_quote_equivalent": quote_fee,
                "fill_at": at,
                "fill_id": event_id,
                "instrument": "BTCUSDT_USD_M_linear_perpetual",
                "order_id": order_id or event_id,
                "post_fill_position": self.state.perpetual_quantity,
                "signed_quantity": trade,
                "implicit_cost_quote": implicit,
            },
            target=self.fill_ledger,
        )
        return [row]

    def funding(
        self,
        event_id: str,
        at: datetime,
        *,
        t_minus_signed_quantity: Decimal | str | int,
        rate: Evidence,
        mark: Evidence,
        index: Evidence,
    ) -> dict[str, Any]:
        quantity = D(t_minus_signed_quantity)
        funding_rate = rate.consume(at)
        funding_mark = mark.consume(at)
        index.consume(at)
        if funding_mark <= 0:
            raise ContractViolation("funding mark must be positive")
        if quantity != self.state.perpetual_quantity and self.state.perpetual_quantity != 0:
            raise ContractViolation("t-minus membership does not match incoming position")
        before, before_nav = self._begin(event_id, at)
        cashflow = -quantity * funding_mark * funding_rate
        if self.state.perpetual_quantity == 0:
            self.state.quote_cash += cashflow
        else:
            self.state.isolated_collateral += cashflow
            if self.state.isolated_collateral < 0:
                self.state.liabilities += -self.state.isolated_collateral
                self.state.isolated_collateral = Decimal("0")
        self.state.accrued_funding += cashflow
        self._refresh_reserve()
        return self._finish(
            event_id, "funding", at, before, before_nav,
            funding_cashflow=cashflow, evidence=(rate, mark, index),
            details={
                "available_at": rate.available_at,
                "cashflow_quote": cashflow,
                "economic_at": at,
                "funding_at": at,
                "funding_mark": funding_mark,
                "funding_rate": funding_rate,
                "index_source_digest": index.lineage_digest,
                "mark_source_digest": mark.lineage_digest,
                "t_minus_signed_quantity": quantity,
            },
            target=self.funding_ledger,
        )

    def missing_funding(self, event_id: str, at: datetime) -> dict[str, Any]:
        before, before_nav = self._begin(event_id, at)
        if self.state.perpetual_quantity != 0:
            self._invalidate("missing_funding_while_exposed")
        return self._finish(
            event_id, "missing_funding", at, before, before_nav,
            details={"missing": True}, target=self.funding_ledger,
        )

    def liquidate(
        self,
        event_id: str,
        at: datetime,
        *,
        evidence: Sequence[Evidence] = (),
    ) -> dict[str, Any]:
        if self.state.perpetual_quantity == 0 or self.state.perpetual_mark is None:
            raise ContractViolation("no perpetual position to liquidate")
        if not self.is_liquidated():
            raise ContractViolation("observed maintenance breach not proven")
        before, before_nav = self._begin(event_id, at)
        incoming = self.state.perpetual_quantity
        mark = self.state.perpetual_mark
        fee = abs(incoming) * mark * self.liquidation_fee_rate
        realized = abs(incoming) * (Decimal("1") if incoming > 0 else Decimal("-1")) * (
            mark - D(self.state.average_perpetual_entry)
        )
        self.state.isolated_collateral += realized - fee
        self.state.realized_pnl += realized
        self.state.explicit_costs += fee
        self.state.perpetual_quantity = Decimal("0")
        self.state.average_perpetual_entry = None
        self.state.unrealized_pnl = Decimal("0")
        self._settle_flat_collateral()
        self._invalidate("observed_liquidation")
        return self._finish(
            event_id, "liquidation", at, before, before_nav,
            explicit_cost=fee, evidence=evidence,
            details={
                "liquidation_fee": fee, "liquidation_mark": mark,
                "ordinary_close_cost": Decimal("0"),
                "pre_liquidation_quantity": incoming,
            }, target=self.fill_ledger,
        )

    def missing_bar(self, event_id: str, at: datetime, *, next_segment_id: str) -> dict[str, Any]:
        before, before_nav = self._begin(event_id, at)
        exposed = self.state.spot_quantity != 0 or self.state.perpetual_quantity != 0
        if exposed:
            self._invalidate(
                "missing_bar_while_exposed",
                {"action": "forced_neutralization", "next_segment_id": next_segment_id},
            )
        return self._finish(
            event_id, "missing_bar", at, before, before_nav,
            details={"exposed": exposed, "next_segment_id": next_segment_id},
            target=self.account_ledger,
        )

    def risk_permission(self, *, reduction: bool, protective: bool = False) -> tuple[bool, str]:
        if reduction or protective:
            return True, "protective_or_reduction_priority"
        if self.state.state != "valid":
            return False, "unknown_or_invalid_state"
        daily = self.state.nav / self._day_start_nav - Decimal("1")
        drawdown = self.state.nav / self._high_water_nav - Decimal("1")
        if daily < Decimal("-0.05"):
            return False, "UTC_daily_loss"
        if drawdown < Decimal("-0.10"):
            return False, "drawdown"
        if self.state.perpetual_quantity and self.margin_equity <= self.maintenance_requirement:
            return False, "margin"
        return True, "permitted"

    @staticmethod
    def solve_full_spot_sale(
        inventory: Decimal | str | int,
        price: Decimal | str | int,
        rules: InstrumentRules,
        fee: FeePolicy,
    ) -> Decimal:
        inventory_d, price_d = D(inventory), D(price)
        if fee.asset != "base":
            result = rules.quantity(inventory_d)
            rules.validate(result, price_d)
            if result != inventory_d:
                raise ContractViolation("full close leaves spot dust")
            return result
        rate = fee.rate + fee.tax_rate
        result = rules.quantity(inventory_d / (Decimal("1") + rate))
        rules.validate(result, price_d)
        native, _ = fee.amounts(result, price_d, conversion_mark=price_d)
        if result + native != inventory_d:
            raise ContractViolation("base-fee full close cannot leave exactly zero dust")
        return result

    @staticmethod
    def mismatch(left: Decimal, right: Decimal) -> Decimal:
        left_abs, right_abs = abs(D(left)), abs(D(right))
        denominator = max(left_abs, right_abs)
        if denominator == 0:
            return Decimal("0")
        return abs(left_abs - right_abs) / denominator

    def _preflight_pair_outcome(
        self,
        outcome: PairOutcome,
        *,
        spot_rules: InstrumentRules,
        perpetual_rules: InstrumentRules,
        spot_fee: FeePolicy,
        ordinary_perpetual_fee: FeePolicy,
        severe_perpetual_fee: FeePolicy,
    ) -> tuple[Decimal, Decimal, Decimal]:
        gross_spot = D(outcome.spot_fill_quantity)
        q = D(outcome.perpetual_fill_quantity)
        if gross_spot < 0 or q < 0:
            raise ContractViolation("pair close fills must be nonnegative")
        if gross_spot:
            spot_rules.validate(gross_spot, outcome.spot_price)
        spot_native, _ = spot_fee.amounts(
            gross_spot, outcome.spot_price,
            conversion_mark=outcome.spot_price if spot_fee.asset == "base" else None,
        )
        reduction = gross_spot + (spot_native if spot_fee.asset == "base" else Decimal("0"))
        q_target = perpetual_rules.quantity(reduction)
        if q > q_target or q > abs(self.state.perpetual_quantity):
            raise ContractViolation("perpetual close exceeds actual spot reduction or short")
        if q:
            perpetual_rules.validate(q, outcome.perpetual_price)
        residual = reduction - q
        if residual < 0 or residual > abs(self.state.perpetual_quantity) - q:
            raise ContractViolation("invalid residual naked-short quantity")
        if reduction > self.state.spot_quantity:
            raise ContractViolation("spot reduction exceeds inventory")
        c0 = self.state.isolated_collateral
        q0 = abs(self.state.perpetual_quantity)
        im0 = self.state.allocated_initial_margin_memo
        entry = D(self.state.average_perpetual_entry)
        ordinary_fee_quote = ordinary_perpetual_fee.amounts(
            q, outcome.perpetual_price,
            conversion_mark=outcome.perpetual_price
            if ordinary_perpetual_fee.asset != "quote" else None,
        )[1]
        cpre = c0 + q * (entry - outcome.perpetual_price) - ordinary_fee_quote
        if c0 + q * (entry - outcome.perpetual_price) < ordinary_fee_quote:
            raise ContractViolation("ordinary perpetual close fee not collateral-funded")
        release = Decimal("0") if q0 == 0 else min(im0 * q / q0, max(cpre, Decimal("0")))
        c1 = cpre - release
        if residual:
            severe_price = outcome.severe_perpetual_price
            if severe_price is None or severe_price <= 0:
                raise ContractViolation("severe residual executable price unavailable")
            if perpetual_rules.quantity(residual) != residual:
                raise ContractViolation("residual is not rule-quantized")
            perpetual_rules.validate(residual, severe_price)
            severe_quote = severe_perpetual_fee.amounts(
                residual, severe_price,
                conversion_mark=severe_price
                if severe_perpetual_fee.asset != "quote" else None,
            )[1]
            if c1 + residual * (entry - severe_price) < severe_quote:
                raise ContractViolation("severe residual fee not collateral-funded")
        return reduction, q, residual

    def atomic_pair_close(
        self,
        event_id: str,
        at: datetime,
        *,
        selected_outcome: PairOutcome,
        outcome_set: Sequence[PairOutcome],
        outcome_set_complete: bool,
        spot_price: Evidence,
        perpetual_price: Evidence,
        severe_perpetual_price: Evidence | None,
        spot_rules: InstrumentRules,
        perpetual_rules: InstrumentRules,
        spot_fee: FeePolicy,
        ordinary_perpetual_fee: FeePolicy,
        severe_perpetual_fee: FeePolicy,
        post_spot_mark: Evidence,
        post_perpetual_mark: Evidence,
        mismatch_limit: Decimal | str | int = "0.01",
    ) -> PairCloseResult:
        if self.bindings.selected_mandate_id != DELTA_NEUTRAL_MANDATE_ID:
            raise ContractViolation("pair close requires delta-neutral mandate")
        if not outcome_set_complete or not outcome_set:
            raise ContractViolation("Cartesian adapter outcome set must be complete")
        if self.state.spot_quantity <= 0 or self.state.perpetual_quantity >= 0:
            raise ContractViolation("pair close requires long spot and short perpetual")
        if spot_price.consume(at) != selected_outcome.spot_price:
            raise ContractViolation("spot leg price lineage mismatch")
        if perpetual_price.consume(at) != selected_outcome.perpetual_price:
            raise ContractViolation("perpetual leg price lineage mismatch")
        if selected_outcome not in outcome_set:
            raise ContractViolation("selected outcome absent from preflight set")
        if self.bindings.adapter_id == "candle_OHLC":
            maximum_spot_fill = max(
                (outcome.spot_fill_quantity for outcome in outcome_set),
                default=Decimal("0"),
            )
            for outcome in outcome_set:
                if outcome.spot_fill_quantity not in {
                    Decimal("0"), maximum_spot_fill
                }:
                    raise ContractViolation("candle spot partial fill forbidden")
                target = perpetual_rules.quantity(
                    outcome.spot_fill_quantity
                    + (spot_fee.amounts(
                        outcome.spot_fill_quantity, outcome.spot_price,
                        conversion_mark=outcome.spot_price if spot_fee.asset == "base" else None,
                    )[0] if spot_fee.asset == "base" else Decimal("0"))
                )
                if outcome.perpetual_fill_quantity not in {Decimal("0"), target}:
                    raise ContractViolation("candle perpetual partial fill forbidden")
        preflight: list[tuple[Decimal, Decimal, Decimal]] = []
        for outcome in outcome_set:
            preflight.append(self._preflight_pair_outcome(
                outcome, spot_rules=spot_rules, perpetual_rules=perpetual_rules,
                spot_fee=spot_fee, ordinary_perpetual_fee=ordinary_perpetual_fee,
                severe_perpetual_fee=severe_perpetual_fee,
            ))
        index = list(outcome_set).index(selected_outcome)
        reduction, q, residual = preflight[index]
        if selected_outcome.spot_fill_quantity == 0:
            self.record_order(
                event_id + ":spot-order", at, instrument="BTC_USDT_spot",
                requested_quantity=Decimal("0"), rounded_quantity=Decimal("0"),
                filled_quantity=Decimal("0"), status="rejected", reason="spot_zero_or_rejected",
                evidence=(spot_price,),
            )
            return PairCloseResult(
                Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
                Decimal("0"), self.mismatch(
                    self.state.spot_quantity * post_spot_mark.consume(at),
                    abs(self.state.perpetual_quantity) * post_perpetual_mark.consume(at),
                ), "unchanged", self.state.invalidation_reason,
            )
        self.record_order(
            event_id + ":spot-order", at, instrument="BTC_USDT_spot",
            requested_quantity=-selected_outcome.spot_fill_quantity,
            rounded_quantity=-selected_outcome.spot_fill_quantity,
            filled_quantity=-selected_outcome.spot_fill_quantity,
            status="filled", reason="pair_close_first_leg", evidence=(spot_price,),
        )
        before_spot = self.state.spot_quantity
        self.spot_fill(
            event_id + ":spot-fill", at,
            signed_quantity=-selected_outcome.spot_fill_quantity,
            price=spot_price, rules=spot_rules, fee=spot_fee,
            fee_conversion=spot_price if spot_fee.asset == "base" else None,
            order_id=event_id + ":spot-order",
        )
        actual_reduction = before_spot - self.state.spot_quantity
        if actual_reduction != reduction:
            raise ReconciliationError("actual spot reduction differs from preflight")
        target = perpetual_rules.quantity(actual_reduction)
        perp_status = "filled" if q == target else ("partial" if q else "rejected")
        self.record_order(
            event_id + ":perpetual-order", at,
            instrument="BTCUSDT_USD_M_linear_perpetual",
            requested_quantity=target, rounded_quantity=target, filled_quantity=q,
            status=perp_status,
            reason="actual_spot_reduction_target", evidence=(perpetual_price,),
        )
        if q:
            self.perpetual_fill(
                event_id + ":perpetual-fill", at, signed_quantity=q,
                price=perpetual_price, rules=perpetual_rules,
                fee=ordinary_perpetual_fee, order_id=event_id + ":perpetual-order",
            )
        severe_filled = Decimal("0")
        if residual:
            if severe_perpetual_price is None:
                failure_before, failure_nav = self._begin(
                    event_id + ":severe-unavailable", at
                )
                self._invalidate(
                    "severe_residual_price_unavailable",
                    {"action": "buy_to_close", "quantity": residual},
                )
                self._finish(
                    event_id + ":severe-unavailable", "pair_close_failure", at,
                    failure_before, failure_nav,
                    details={
                        "created_residual_naked_short_quantity": residual,
                        "reason": "no_valid_same_timestamp_severe_price",
                        "status": "pending_forced_buy_to_close",
                    },
                )
                return PairCloseResult(
                    actual_reduction, q, residual, Decimal("0"), None, None,
                    "invalid_unknown_pending_forced_buy_to_close",
                    self.state.invalidation_reason,
                )
            severe_value = severe_perpetual_price.consume(at)
            if severe_value != selected_outcome.severe_perpetual_price:
                raise ContractViolation("severe residual price lineage mismatch")
            if self.state.perpetual_mark != severe_value:
                self.mark(
                    event_id + ":severe-mark", at, perpetual=severe_perpetual_price
                )
            self.record_order(
                event_id + ":severe-order", at,
                instrument="BTCUSDT_USD_M_linear_perpetual",
                requested_quantity=residual, rounded_quantity=residual,
                filled_quantity=residual, status="filled",
                reason="unintended_naked_short_residual", evidence=(severe_perpetual_price,),
            )
            self.perpetual_fill(
                event_id + ":severe-fill", at, signed_quantity=residual,
                price=severe_perpetual_price, rules=perpetual_rules,
                fee=severe_perpetual_fee, order_id=event_id + ":severe-order",
            )
            severe_filled = residual
        spot_mark_value = post_spot_mark.consume(at)
        perp_mark_value = post_perpetual_mark.consume(at)
        if post_spot_mark.observed_at != post_perpetual_mark.observed_at:
            raise ContractViolation("remaining-pair marks lack shared valuation timestamp")
        quantity_mismatch = self.mismatch(
            self.state.spot_quantity, abs(self.state.perpetual_quantity)
        )
        notional_mismatch = self.mismatch(
            self.state.spot_quantity * spot_mark_value,
            abs(self.state.perpetual_quantity) * perp_mark_value,
        )
        limit = D(mismatch_limit)
        if limit != Decimal("0.01"):
            raise ContractViolation("mismatch limit must equal frozen bound")
        if quantity_mismatch > limit or notional_mismatch > limit:
            mismatch_before, mismatch_nav = self._begin(
                event_id + ":mismatch-failure", at
            )
            self._invalidate(
                "remaining_pair_mismatch_requires_one_forced_close",
                {"action": "whole_pair_forced_close", "attempts_remaining": "1"},
            )
            self._finish(
                event_id + ":mismatch-failure", "pair_close_failure", at,
                mismatch_before, mismatch_nav,
                details={
                    "remaining_notional_mismatch": notional_mismatch,
                    "remaining_quantity_mismatch": quantity_mismatch,
                    "status": "pending_one_non_recursive_whole_pair_forced_close",
                },
            )
            status = "invalid_unknown_pending_whole_pair_forced_close"
        else:
            status = "closed_or_matched_remainder"
        return PairCloseResult(
            actual_reduction, q, residual, severe_filled, quantity_mismatch,
            notional_mismatch, status, self.state.invalidation_reason,
        )

    def resolve_pending_residual(
        self,
        event_id: str,
        at: datetime,
        *,
        price: Evidence,
        rules: InstrumentRules,
        severe_fee: FeePolicy,
        terminal_at: datetime,
        crossed_segment: bool = False,
    ) -> dict[str, Any]:
        utc_string(terminal_at)
        if at >= terminal_at:
            raise ContractViolation("safety execution may not reach/cross terminal boundary")
        pending = next(
            (item for item in self.state.pending_safety_actions
             if item.get("action") == "buy_to_close"), None,
        )
        if pending is None:
            raise ContractViolation("no pending residual buy-to-close")
        quantity = D(pending["quantity"])
        if crossed_segment:
            self._invalidate("delayed_residual_crossed_segment")
        if self.state.perpetual_mark != price.consume(at):
            self.mark(event_id + ":mark", at, perpetual=price)
        rows = self.perpetual_fill(
            event_id, at, signed_quantity=quantity, price=price, rules=rules,
            fee=severe_fee, order_id=event_id + ":forced-order",
        )
        clear_before, clear_nav = self._begin(event_id + ":clear-pending", at)
        self.state.pending_safety_actions.remove(pending)
        return self._finish(
            event_id + ":clear-pending", "safety_intention_resolved", at,
            clear_before, clear_nav,
            details={"resolved_fill_row_digest": rows[-1]["row_digest"]},
        )

    def record_order(
        self,
        event_id: str,
        at: datetime,
        *,
        instrument: str,
        requested_quantity: Decimal,
        rounded_quantity: Decimal,
        filled_quantity: Decimal,
        status: str,
        reason: str,
        evidence: Sequence[Evidence],
    ) -> dict[str, Any]:
        before, before_nav = self._begin(event_id, at)
        requested = D(requested_quantity)
        rounded = D(rounded_quantity)
        filled = D(filled_quantity)
        unfilled = abs(rounded) - abs(filled)
        if unfilled < 0:
            raise ContractViolation("filled quantity exceeds rounded quantity")
        return self._finish(
            event_id, "order", at, before, before_nav, evidence=evidence,
            details={
                "arrival_at": at, "created_at": at, "decision_id": event_id,
                "filled_quantity": filled, "instrument": instrument,
                "order_id": event_id, "price_bound": None, "reason": reason,
                "requested_quantity": requested, "rounded_quantity": rounded,
                "status": status, "unfilled_quantity": unfilled,
            }, target=self.order_ledger,
        )

    def record_decision(
        self,
        event_id: str,
        at: datetime,
        *,
        requested_target: str,
        permission: str,
        reason: str,
        evidence: Sequence[Evidence] = (),
    ) -> dict[str, Any]:
        if permission not in {"abstain", "reject", "accounting_fixture_only"}:
            raise ContractViolation("decision cannot be actionable")
        before, before_nav = self._begin(event_id, at)
        return self._finish(
            event_id, "decision", at, before, before_nav, evidence=evidence,
            details={
                "available_information_cutoff": at, "decision_at": at,
                "decision_id": event_id, "lineage_digest": canonical_digest(
                    [item.lineage_digest for item in evidence]
                ),
                "permission_or_abstention": permission, "reason": reason,
                "requested_target": requested_target,
            }, target=self.decision_ledger,
        )

    def account_snapshot(
        self,
        event_id: str,
        at: datetime,
        *,
        segment_id: str,
        evidence: Sequence[Evidence] = (),
    ) -> dict[str, Any]:
        before, before_nav = self._begin(event_id, at)
        gross = (
            self.state.spot_quantity * (self.state.spot_mark or Decimal("0"))
            + abs(self.state.perpetual_quantity) * (self.state.perpetual_mark or Decimal("0"))
        )
        net = (
            self.state.spot_quantity * (self.state.spot_mark or Decimal("0"))
            + self.state.perpetual_quantity * (self.state.perpetual_mark or Decimal("0"))
        )
        return self._finish(
            event_id, "account_snapshot", at, before, before_nav, evidence=evidence,
            details={
                "NAV": self.state.nav,
                "allocated_initial_margin_memo": self.state.allocated_initial_margin_memo,
                "explicit_costs": self.state.explicit_costs,
                "exit_cost_reserve_memo": self.state.exit_cost_reserve_memo,
                "fee_asset_balances": self.state.fee_asset_balances,
                "funding": self.state.accrued_funding,
                "gross_exposure": gross,
                "implicit_costs": self.state.implicit_costs,
                "isolated_collateral": self.state.isolated_collateral,
                "liabilities": self.state.liabilities,
                "maintenance_requirement": self.maintenance_requirement,
                "margin_equity": self.margin_equity,
                "net_exposure": net,
                "perpetual_quantity": self.state.perpetual_quantity,
                "quote_cash": self.state.quote_cash,
                "realized_PnL": self.state.realized_pnl,
                "segment_id": segment_id,
                "spot_quantity": self.state.spot_quantity,
                "state": self.state.state,
                "timestamp": at,
                "unrealized_PnL": self.state.unrealized_pnl,
            }, target=self.account_ledger,
        )

    def terminal_order_allowed(
        self,
        *,
        spot_delta: Decimal | str | int = "0",
        perpetual_delta: Decimal | str | int = "0",
        protective: bool = False,
        forced: bool = False,
        predeclared_flatten: bool = False,
    ) -> bool:
        if protective or forced or predeclared_flatten:
            return True
        spot_after = self.state.spot_quantity + D(spot_delta)
        perp_after = self.state.perpetual_quantity + D(perpetual_delta)
        if spot_after < 0:
            return False
        return (
            abs(spot_after) <= abs(self.state.spot_quantity)
            and abs(perp_after) <= abs(self.state.perpetual_quantity)
        )

    def run_summary(self) -> dict[str, Any]:
        total_spot = sum((D(row["spot_price_pnl"]) for row in self.events), Decimal("0"))
        total_perp = sum((D(row["perpetual_price_pnl"]) for row in self.events), Decimal("0"))
        total_funding = sum((D(row["funding_cashflow"]) for row in self.events), Decimal("0"))
        expected_end = (
            self.starting_nav + total_spot + total_perp + total_funding
            - self.state.explicit_costs - self.state.implicit_costs
        )
        residual = self.state.nav - expected_end
        if abs(residual) > RECONCILIATION_QUANTUM:
            raise ReconciliationError("run accounting identity failed")
        result = {
            **self.bindings.row_lineage(),
            "accounting_residual": residual,
            "actionable_arm_id": ACTIONABLE_ARM_ID,
            "diagnostic_missed_unfilled_and_unused_rounded_notional": Decimal("0"),
            "diagnostic_opportunity_cost": Decimal("0"),
            "ending_NAV": self.state.nav,
            "explicit_costs": self.state.explicit_costs,
            "funding_PnL": total_funding,
            "implicit_costs": self.state.implicit_costs,
            "neutralization_costs": sum(
                (D(row["explicit_cost"]) + D(row["implicit_cost"])
                 for row in self.events if "severe" in row["event_id"]), Decimal("0")
            ),
            "perpetual_price_PnL": total_perp,
            "rejected_expired_partial_and_unfilled_counts": {
                status: sum(1 for row in self.order_ledger if row["status"] == status)
                for status in ("rejected", "expired", "partial")
            },
            "run_invalidation_reason": self.state.invalidation_reason,
            "spot_price_PnL": total_spot,
            "starting_NAV": self.starting_nav,
            "unknown_or_invalid_intervals": int(self.state.state != "valid"),
        }
        result["result_digest"] = canonical_digest(result)
        return _canonical(result)

    def canonical_jsonl(self, rows: Iterable[Mapping[str, Any]]) -> bytes:
        materialized = list(rows)
        if not materialized:
            return b""
        return ("\n".join(canonical_json(row) for row in materialized) + "\n").encode("utf-8")

    def artifacts(self) -> dict[str, bytes]:
        ledgers = {
            "decision_ledger.jsonl": self.decision_ledger,
            "order_ledger.jsonl": self.order_ledger,
            "fill_ledger.jsonl": self.fill_ledger,
            "funding_ledger.jsonl": self.funding_ledger,
            "account_ledger.jsonl": self.account_ledger,
            "closed_episode_ledger.jsonl": self.closed_episode_ledger,
        }
        files = {name: self.canonical_jsonl(rows) for name, rows in ledgers.items()}
        files["report.json"] = (canonical_json(self.run_summary()) + "\n").encode("utf-8")
        manifest = {
            "actionable_arm_id": ACTIONABLE_ARM_ID,
            "artifacts": [
                {
                    "path": name, "semantic_role": name.removesuffix(".jsonl"),
                    "sha256": sha256(content).hexdigest(), "size_bytes": len(content),
                }
                for name, content in sorted(files.items())
            ],
            "experiment_id": EXPERIMENT_ID,
        }
        files["evidence_manifest.json"] = (canonical_json(manifest) + "\n").encode("utf-8")
        return files


__all__ = [
    "ACTIONABLE_ARM_ID", "CONTRACT_SHA256", "ContractViolation", "D",
    "DELTA_NEUTRAL_MANDATE_ID", "DELTA_NEUTRAL_MANDATE_PATH",
    "DELTA_NEUTRAL_MANDATE_SHA256", "EXECUTION_CONFIG_SHA256", "EXPERIMENT_ID",
    "Evidence", "FeePolicy", "InstrumentRules", "LedgerState", "PairCloseResult",
    "PairOutcome", "RECONCILIATION_QUANTUM", "ReconciliationError", "RunBindings",
    "SEMANTIC_RUN_SETTING_FIELDS", "SyntheticLedger", "canonical_digest",
    "canonical_json", "decimal_string", "parse_json_strict",
    "semantic_run_settings_digest", "synthetic_digest", "synthetic_evidence", "utc_string",
]
