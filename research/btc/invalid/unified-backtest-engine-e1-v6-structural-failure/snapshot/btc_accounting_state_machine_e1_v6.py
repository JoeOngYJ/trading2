"""Offline synthetic BTC accounting state machine (E1-v6).

This module is deliberately self contained.  It has no I/O adapter, strategy hook,
network client, database integration, or production order type.  Its only actionable
arm is ``no_trade``.  All economic arithmetic is :class:`decimal.Decimal`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EXPERIMENT_ID = "btc-unified-backtest-engine-e1-v6"
ACTIONABLE_ARM_ID = "no_trade"
QUOTE_QUANTUM = Decimal("0.00000001")
DAILY_LOSS_LIMIT = Decimal("-0.015")
DRAWDOWN_LIMIT = Decimal("-0.10")
PAIR_MISMATCH_LIMIT = Decimal("0.01")

CONTRACT_DIGESTS = {
    "E0_v1": "af23751e6ef08a4c0dc11eb33559b4d939ec38260ae2d3ae22fcb73237856c0e",
    "E0_v2": "201bbaad8f1fb6e00efdc2b3c25d632d0d3da94d8b8521c2f92b37da29cde887",
    "E0_v3": "b0cea8cb6b35df31d51c7745a6b2ec1b3a4a3c6ac99f67c4d5db12a021057df1",
    "E0_v4": "d8b2852e6ef1e1c5b32bbf585f64683751d95480f9c87f890408708b58b5407c",
    "E1_v6": "5a2f05ab500d21dfbbb9bed4d257ea57b9f107264518f451df68ef70138cf714",
}
EXECUTION_CONFIG_DIGEST = "a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36"

MANDATES = {
    "retail-btc-spot-v2": (
        "config/retail_mandate.json",
        "7e34cfb0928b4373bbf52b5c5505f63a2b19e674124059191c1b6c62ec129041",
        "spot",
    ),
    "retail-btc-directional-perpetual-research-v1": (
        "config/mandates/retail-btc-directional-perpetual-research-v1.json",
        "1b5d492f12f71ebe28e1bdfbd0b5916bcf0ad285b483cb10bf8770504371165d",
        "directional",
    ),
    "retail-btc-delta-neutral-research-v1": (
        "config/mandates/retail-btc-delta-neutral-research-v1.json",
        "d95a53ee493862549b932dc5f80600a02a0e38e4ba1b3da0d79d0b0c5bb9eeba",
        "pair",
    ),
}

SCENARIOS = {
    "candle-primary-30bps-rt-v1": (Decimal("0.001"), Decimal("0.0005"), Decimal("0.001")),
    "candle-stress-40bps-rt-v1": (Decimal("0.001"), Decimal("0.001"), Decimal("0.002")),
    "candle-severe-80bps-rt-v1": (Decimal("0.002"), Decimal("0.002"), Decimal("0.005")),
}

SPOT = "BTCUSDT_spot"
PERPETUAL = "BTCUSDT_USD_M_perpetual"


class AccountingError(ValueError):
    """Fail-closed contract violation."""


class PhaseError(AccountingError):
    """Operation attempted outside its canonical phase."""


class State(Enum):
    ACTIVE = "active"
    UNKNOWN = "invalid_unknown"
    TERMINAL = "terminal"
    LIQUIDATED = "liquidated"


def D(value: Any) -> Decimal:
    """Strict finite Decimal conversion; floats are intentionally rejected."""
    if isinstance(value, bool) or isinstance(value, float):
        raise AccountingError("economic values cannot be bool or float")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (str, int)):
        try:
            result = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise AccountingError("invalid Decimal") from exc
    else:
        raise AccountingError("economic value must be Decimal, string, or integer")
    if not result.is_finite():
        raise AccountingError("nonfinite Decimal")
    return result


def decimal_string(value: Decimal) -> str:
    value = D(value)
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def utc_timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        if not value.endswith("Z"):
            raise AccountingError("timestamp must be UTC RFC3339 Z")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise AccountingError("invalid timestamp") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise AccountingError("timestamp must be datetime or string")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise AccountingError("timestamp must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Decimal):
        return decimal_string(value)
    if isinstance(value, datetime):
        return utc_timestamp(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        seen: dict[str, Any] = {}
        for key, item in value.items():
            canonical_key = str(key)
            if canonical_key in seen and seen[canonical_key] != key:
                raise AccountingError("mapping keys collide after string conversion")
            seen[canonical_key] = key
            out[canonical_key] = _canonical(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        raise AccountingError("float forbidden in canonical economic JSON")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise AccountingError(f"unsupported canonical type: {type(value).__name__}")


def canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    encoded = json.dumps(
        _canonical(value), ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return encoded + (b"\n" if newline else b"")


def canonical_digest(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def strict_json_loads(data: str | bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise AccountingError("duplicate JSON object key")
            out[key] = value
        return out

    def reject_constant(value: str) -> None:
        raise AccountingError(f"nonfinite JSON number: {value}")

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_float=Decimal,
                          parse_int=Decimal, parse_constant=reject_constant)
    except (json.JSONDecodeError, InvalidOperation) as exc:
        raise AccountingError("invalid strict JSON") from exc


def implementation_digest(path: str | Path | None = None) -> str:
    """Digest exact implementation bytes; never accepts a digest from a caller."""
    target = Path(path) if path is not None else Path(__file__)
    return sha256(target.read_bytes()).hexdigest()


def canonical_candle_arrival(decision_at: str, arrival_at: str) -> str:
    decision = datetime.fromisoformat(utc_timestamp(decision_at)[:-1] + "+00:00")
    arrival = datetime.fromisoformat(utc_timestamp(arrival_at)[:-1] + "+00:00")
    expected = decision + timedelta(hours=1)
    if arrival != expected or arrival.minute != 0 or arrival.second != 0 or arrival.microsecond != 0:
        raise AccountingError("candle fill must use exact next hourly open")
    return utc_timestamp(arrival)


@dataclass(frozen=True)
class SourceLineage:
    source_path: str
    source_sha256: str
    segment_id: str
    observed_at: str
    available_at: str
    rule_snapshot_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", utc_timestamp(self.observed_at))
        object.__setattr__(self, "available_at", utc_timestamp(self.available_at))
        for digest in (self.source_sha256, self.rule_snapshot_digest):
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise AccountingError("lineage digests must be lowercase SHA-256")
        if self.available_at > self.observed_at:
            # Availability may lag observation, but it cannot be consumed before available_at.
            pass

    def require_available(self, event_at: str) -> None:
        if self.available_at > utc_timestamp(event_at):
            raise AccountingError("future/unavailable source input")


@dataclass(frozen=True)
class InstrumentRules:
    instrument: str
    quantity_step: Decimal
    price_tick: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal
    digest: str

    def __post_init__(self) -> None:
        for name in ("quantity_step", "price_tick", "minimum_quantity", "minimum_notional"):
            value = D(getattr(self, name))
            if value <= 0:
                raise AccountingError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if self.instrument not in (SPOT, PERPETUAL):
            raise AccountingError("wrong instrument")

    def quantity(self, requested: Decimal) -> Decimal:
        requested = D(requested)
        sign = Decimal("-1") if requested < 0 else Decimal("1")
        rounded = (abs(requested) / self.quantity_step).to_integral_value(rounding=ROUND_DOWN)
        return sign * rounded * self.quantity_step

    def validate_price(self, price: Decimal) -> Decimal:
        price = D(price)
        if price <= 0 or price % self.price_tick != 0:
            raise AccountingError("price is nonpositive or off tick")
        return price

    def validate_order(self, quantity: Decimal, price: Decimal) -> None:
        quantity, price = abs(D(quantity)), self.validate_price(price)
        if quantity == 0 or quantity < self.minimum_quantity:
            raise AccountingError("quantity below minimum")
        if quantity % self.quantity_step != 0:
            raise AccountingError("quantity off step")
        if quantity * price < self.minimum_notional:
            raise AccountingError("notional below minimum")


@dataclass(frozen=True)
class Fee:
    asset: str = "quote"
    rate: Decimal = Decimal("0")
    tax_quote: Decimal = Decimal("0")
    third_asset_mark: Decimal | None = None
    lineage: SourceLineage | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", D(self.rate))
        object.__setattr__(self, "tax_quote", D(self.tax_quote))
        if self.rate < 0 or self.tax_quote < 0 or self.asset not in ("quote", "base", "third"):
            raise AccountingError("invalid fee")
        if self.third_asset_mark is not None:
            mark = D(self.third_asset_mark)
            if mark <= 0:
                raise AccountingError("third-asset mark must be positive")
            object.__setattr__(self, "third_asset_mark", mark)


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
    liabilities: Decimal = Decimal("0")
    fee_asset_balances: dict[str, Decimal] = field(default_factory=dict)
    status: State = State.ACTIVE
    invalidation_reason: str | None = None
    new_exposure_enabled: bool = True
    pending_safety_actions: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in (
            "quote_cash", "spot_quantity", "isolated_collateral", "perpetual_quantity",
            "realized_pnl", "unrealized_pnl", "accrued_funding",
            "allocated_initial_margin_memo", "explicit_costs", "implicit_costs",
            "exit_cost_reserve_memo", "liabilities",
        ):
            setattr(self, name, D(getattr(self, name)))
        if self.average_perpetual_entry is not None:
            self.average_perpetual_entry = D(self.average_perpetual_entry)
        self.fee_asset_balances = {str(k): D(v) for k, v in self.fee_asset_balances.items()}
        if self.spot_quantity < 0 or self.liabilities < 0:
            raise AccountingError("negative spot inventory or liability")
        if self.perpetual_quantity == 0 and self.average_perpetual_entry is not None:
            raise AccountingError("flat perpetual average entry must be null")
        if self.perpetual_quantity != 0 and self.average_perpetual_entry is None:
            raise AccountingError("open perpetual requires average entry")


@dataclass(frozen=True)
class RunBinding:
    run_id: str
    scenario_id: str
    selected_mandate_id: str
    selected_mandate_path: str
    selected_mandate_sha256: str
    adapter_id: str
    spot_rules_digest: str
    perpetual_rules_digest: str
    source_digests: tuple[str, ...]
    leverage: Decimal
    exit_cost_rate: Decimal
    zero_exit_reserve_fixture: bool = False

    def __post_init__(self) -> None:
        if self.scenario_id not in SCENARIOS:
            raise AccountingError("only immutable 30/40/80 scenarios are accepted")
        if self.selected_mandate_id not in MANDATES:
            raise AccountingError("unknown mandate")
        path, digest, kind = MANDATES[self.selected_mandate_id]
        if (self.selected_mandate_path, self.selected_mandate_sha256) != (path, digest):
            raise AccountingError("mandate path/id/exact-file digest mismatch")
        leverage = D(self.leverage)
        exit_rate = D(self.exit_cost_rate)
        if leverage <= 0 or exit_rate < 0:
            raise AccountingError("invalid leverage or exit reserve rate")
        if kind == "pair" and leverage != 1:
            raise AccountingError("delta-neutral leverage is exactly 1x")
        if exit_rate == 0 and not self.zero_exit_reserve_fixture:
            raise AccountingError("zero exit reserve requires explicit fixture flag")
        object.__setattr__(self, "leverage", leverage)
        object.__setattr__(self, "exit_cost_rate", exit_rate)

    @property
    def mandate_kind(self) -> str:
        return MANDATES[self.selected_mandate_id][2]

    @property
    def scenario_fee_rate(self) -> Decimal:
        return SCENARIOS[self.scenario_id][0]

    @property
    def scenario_implicit_rate(self) -> Decimal:
        return SCENARIOS[self.scenario_id][1]

    @property
    def semantic_settings(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "scenario_id": self.scenario_id,
            "selected_mandate_path": self.selected_mandate_path,
            "selected_mandate_id": self.selected_mandate_id,
            "selected_mandate_exact_file_sha256": self.selected_mandate_sha256,
            "execution_config_exact_file_sha256": EXECUTION_CONFIG_DIGEST,
            "spot_rules_digest": self.spot_rules_digest,
            "perpetual_rules_digest": self.perpetual_rules_digest,
            "source_digests": self.source_digests,
            "leverage": self.leverage,
            "exit_cost_rate": self.exit_cost_rate,
        }

    @property
    def semantic_settings_digest(self) -> str:
        return canonical_digest(self.semantic_settings)


@dataclass(frozen=True)
class FillSpec:
    fill_id: str
    order_id: str
    instrument: str
    signed_quantity: Decimal
    price: Decimal
    fee: Fee
    implicit_cost_quote: Decimal
    timestamp: str
    rules: InstrumentRules
    source: SourceLineage
    authorization: str = "ordinary"
    reference_price: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "signed_quantity", D(self.signed_quantity))
        object.__setattr__(self, "price", D(self.price))
        object.__setattr__(self, "implicit_cost_quote", D(self.implicit_cost_quote))
        object.__setattr__(self, "timestamp", utc_timestamp(self.timestamp))
        if self.reference_price is not None:
            reference = D(self.reference_price)
            if reference <= 0:
                raise AccountingError("reference price must be positive")
            object.__setattr__(self, "reference_price", reference)
        if self.instrument != self.rules.instrument or self.implicit_cost_quote < 0:
            raise AccountingError("fill instrument/rules mismatch or negative implicit cost")


@dataclass(frozen=True)
class FundingSpec:
    funding_at: str
    economic_at: str
    available_at: str
    rate: Decimal
    mark: Decimal
    mark_source: SourceLineage
    index_source: SourceLineage
    rules_digest: str

    def __post_init__(self) -> None:
        for name in ("funding_at", "economic_at", "available_at"):
            object.__setattr__(self, name, utc_timestamp(getattr(self, name)))
        object.__setattr__(self, "rate", D(self.rate))
        object.__setattr__(self, "mark", D(self.mark))
        if self.mark <= 0 or self.economic_at != self.funding_at:
            raise AccountingError("funding economic timestamp/mark invalid")
        if self.available_at > self.funding_at:
            raise AccountingError("funding unavailable at payment")


@dataclass(frozen=True)
class MarginRules:
    maintenance_rate: Decimal
    add_on: Decimal
    liquidation_fee_rate: Decimal
    minimum_buffer: Decimal
    digest: str

    def __post_init__(self) -> None:
        for name in ("maintenance_rate", "add_on", "liquidation_fee_rate", "minimum_buffer"):
            value = D(getattr(self, name))
            if value < 0:
                raise AccountingError("negative margin rule")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class PairOutcome:
    spot_reduction: Decimal
    perpetual_fill: Decimal
    perpetual_vwap: Decimal
    ordinary_fee_quote: Decimal
    ordinary_implicit_quote: Decimal
    severe_price: Decimal
    severe_fee_quote: Decimal
    severe_implicit_quote: Decimal

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = D(getattr(self, name))
            object.__setattr__(self, name, value)
        if min(self.spot_reduction, self.perpetual_fill, self.ordinary_fee_quote,
               self.ordinary_implicit_quote, self.severe_fee_quote,
               self.severe_implicit_quote) < 0:
            raise AccountingError("negative pair outcome field")
        if self.perpetual_fill > self.spot_reduction:
            raise AccountingError("pair close would cross the required reduction")


class AccountingStateMachine:
    """Deterministic nine-phase synthetic accounting kernel."""

    PHASES = (
        "validate_and_snapshot", "opening_marks_and_liquidation", "protective_exit",
        "funding_and_liquidation", "risk_permissions", "orders_and_fills",
        "post_fill_margin", "intrabar_and_close", "reconcile_emit_advance",
    )

    def __init__(self, binding: RunBinding, state: LedgerState, *, starting_nav: Decimal,
                 spot_mark: Decimal, perpetual_mark: Decimal,
                 margin_rules: MarginRules, mark_lineage: SourceLineage,
                 third_asset_marks: Mapping[str, Decimal] | None = None) -> None:
        self.binding = binding
        self.state = state
        self.starting_nav = D(starting_nav)
        self.spot_mark = D(spot_mark)
        self.perpetual_mark = D(perpetual_mark)
        self.previous_spot_mark = self.spot_mark
        self.previous_perpetual_mark = self.perpetual_mark
        self.third_asset_marks = {str(k): D(v) for k, v in (third_asset_marks or {}).items()}
        self.margin_rules = margin_rules
        self.mark_lineage = mark_lineage
        self.segment_id = mark_lineage.segment_id
        self.rows: dict[str, list[dict[str, Any]]] = {
            name: [] for name in ("decision", "order", "fill", "funding", "account", "closed_episode")
        }
        self.phase = 0
        self.event_sequence = 0
        self.current_timestamp: str | None = None
        self.incoming_perpetual_quantity = state.perpetual_quantity
        self.high_water_nav = self.starting_nav
        self.day_start_nav = self.starting_nav
        self.current_day: str | None = None
        self._partition_day_pending = True
        self.last_reconciled_nav = self.starting_nav
        self._funding_keys: set[str] = set()
        self._fill_ids: set[str] = set()
        self._order_ids: set[str] = set()
        self.price_pnl_spot = Decimal("0")
        self.price_pnl_perpetual = Decimal("0")
        self._episode: dict[str, Any] | None = None
        self._impl_digest = implementation_digest()
        self._pair_outcome_digest: str | None = None
        self._refresh_unrealized(self.perpetual_mark)
        if abs(self.nav() - self.starting_nav) > QUOTE_QUANTUM:
            raise AccountingError("declared starting NAV does not reconcile")

    def _assert_mutable(self, *, reduction: bool = False, protective: bool = False) -> None:
        if self.state.status in (State.LIQUIDATED, State.TERMINAL):
            raise AccountingError("terminal state is persistent")
        if self.state.status is State.UNKNOWN and not protective:
            raise AccountingError("unknown state permits safety action only")
        if not self.state.new_exposure_enabled and not (reduction or protective):
            raise AccountingError("new exposure disabled")

    def _require_phase(self, *allowed: int) -> None:
        if self.phase not in allowed:
            raise PhaseError(f"operation forbidden in phase {self.phase}")

    def state_object(self) -> dict[str, Any]:
        return _canonical(self.state)

    def state_digest(self) -> str:
        return canonical_digest(self.state_object())

    def nav(self, *, spot_mark: Decimal | None = None, perpetual_mark: Decimal | None = None) -> Decimal:
        sm = self.spot_mark if spot_mark is None else D(spot_mark)
        pm = self.perpetual_mark if perpetual_mark is None else D(perpetual_mark)
        third = Decimal("0")
        for asset, balance in self.state.fee_asset_balances.items():
            if asset not in self.third_asset_marks:
                raise AccountingError("missing point-in-time third-asset mark")
            third += balance * self.third_asset_marks[asset]
        unrealized = self._unrealized_at(pm)
        return (self.state.quote_cash + self.state.spot_quantity * sm + third
                + self.state.isolated_collateral + unrealized - self.state.liabilities)

    def _unrealized_at(self, mark: Decimal) -> Decimal:
        if self.state.perpetual_quantity == 0:
            return Decimal("0")
        assert self.state.average_perpetual_entry is not None
        return self.state.perpetual_quantity * (mark - self.state.average_perpetual_entry)

    def _refresh_unrealized(self, mark: Decimal) -> None:
        self.perpetual_mark = D(mark)
        self.state.unrealized_pnl = self._unrealized_at(self.perpetual_mark)
        self.state.exit_cost_reserve_memo = (
            abs(self.state.perpetual_quantity) * self.perpetual_mark * self.binding.exit_cost_rate
            if self.state.perpetual_quantity else Decimal("0")
        )
        if self._episode is not None:
            pnl = self.state.unrealized_pnl
            self._episode["maximum_adverse_excursion"] = min(
                D(self._episode["maximum_adverse_excursion"]), pnl
            )
            self._episode["maximum_favourable_excursion"] = max(
                D(self._episode["maximum_favourable_excursion"]), pnl
            )

    def _lineage(self) -> dict[str, Any]:
        lineage = {
            "experiment_id": EXPERIMENT_ID, "run_id": self.binding.run_id,
            "scenario_id": self.binding.scenario_id, "implementation_digest": self._impl_digest,
            "contract_digests": CONTRACT_DIGESTS,
            "contract_digest": CONTRACT_DIGESTS["E1_v6"],
            "execution_config_digest": EXECUTION_CONFIG_DIGEST,
            "mandate_digest": self.binding.selected_mandate_sha256,
            "semantic_settings_digest": self.binding.semantic_settings_digest,
            "actionable_arm_id": ACTIONABLE_ARM_ID,
        }
        if self._pair_outcome_digest is not None:
            lineage["pair_outcome_set_digest"] = self._pair_outcome_digest
        return lineage

    def _emit(self, ledger: str, payload: Mapping[str, Any], before: str,
              *, residual: Decimal = Decimal("0")) -> dict[str, Any]:
        row = dict(payload)
        row.update(self._lineage())
        row.setdefault("event_sequence", self.event_sequence)
        row.setdefault("before_state_digest", before)
        row.setdefault("after_state_digest", self.state_digest())
        row.setdefault("event_accounting_residual", residual)
        row.setdefault("source_digest_or_explicit_not_applicable", "not_applicable")
        row.setdefault("rules_digest_or_explicit_not_applicable", "not_applicable")
        row.setdefault("invalidation_reason_or_null", self.state.invalidation_reason)
        row["row_digest"] = canonical_digest(row)
        self.rows[ledger].append(_canonical(row))
        return row

    def begin_timestamp(self, timestamp: str) -> None:
        if self.phase != 0:
            raise PhaseError("prior timestamp not completed")
        timestamp = utc_timestamp(timestamp)
        if self.current_timestamp is not None and timestamp <= self.current_timestamp:
            raise AccountingError("duplicate or non-increasing timestamp")
        self.event_sequence += 1
        self.current_timestamp = timestamp
        self.incoming_perpetual_quantity = self.state.perpetual_quantity
        self.phase = 1

    def phase_open(self, *, spot_open: Decimal, perpetual_open: Decimal,
                   margin_rules: MarginRules | None = None) -> None:
        self._require_phase(1)
        spot_open, perpetual_open = D(spot_open), D(perpetual_open)
        if spot_open <= 0 or perpetual_open <= 0:
            raise AccountingError("invalid opening mark")
        assert self.current_timestamp is not None
        self.mark_lineage.require_available(self.current_timestamp)
        self.price_pnl_spot += self.state.spot_quantity * (spot_open - self.previous_spot_mark)
        self.price_pnl_perpetual += self.state.perpetual_quantity * (perpetual_open - self.previous_perpetual_mark)
        self.spot_mark = spot_open
        self._refresh_unrealized(perpetual_open)
        self.phase = 2
        self.check_margin(margin_rules or self.margin_rules, perpetual_open, checkpoint="adverse_open")

    def phase_protective_complete(self) -> None:
        self._require_phase(2)
        self.phase = 3

    def apply_funding(self, funding: FundingSpec, margin_rules: MarginRules | None = None) -> Decimal:
        self._require_phase(3)
        if funding.funding_at != self.current_timestamp:
            raise AccountingError("funding timestamp mismatch")
        funding_key = canonical_digest(funding)
        if funding_key in self._funding_keys:
            raise AccountingError("duplicate funding event")
        self._funding_keys.add(funding_key)
        funding.mark_source.require_available(funding.funding_at)
        funding.index_source.require_available(funding.funding_at)
        if (funding.mark_source.segment_id != self.segment_id
                or funding.index_source.segment_id != self.segment_id):
            raise AccountingError("cross-segment funding input")
        before = self.state_digest()
        member = self.incoming_perpetual_quantity  # engine-owned t-minus snapshot
        cashflow = -member * funding.mark * funding.rate
        if member != 0 and self.state.status is not State.LIQUIDATED:
            if self.state.perpetual_quantity != 0:
                self.state.isolated_collateral += cashflow
                if self.state.isolated_collateral < 0:
                    self.state.liabilities += -self.state.isolated_collateral
                    self.state.isolated_collateral = Decimal("0")
            else:
                self.state.quote_cash += cashflow
            self.state.accrued_funding += cashflow
            if self._episode is not None:
                self._episode["funding_PnL"] += cashflow
        self._refresh_unrealized(funding.mark)
        self._emit("funding", {
            "funding_at": funding.funding_at, "economic_at": funding.economic_at,
            "available_at": funding.available_at, "t_minus_signed_quantity": member,
            "funding_rate": funding.rate, "funding_mark": funding.mark,
            "cashflow_quote": cashflow, "mark_source_digest": funding.mark_source.source_sha256,
            "index_source_digest": funding.index_source.source_sha256,
            "source_digest": canonical_digest([funding.mark_source, funding.index_source]),
            "rules_digest": funding.rules_digest,
        }, before)
        self.check_margin(margin_rules or self.margin_rules, funding.mark, checkpoint="after_funding")
        return cashflow

    def phase_funding_complete(self, margin_rules: MarginRules | None = None) -> None:
        self._require_phase(3)
        self.check_margin(margin_rules or self.margin_rules, self.perpetual_mark, checkpoint="after_funding")
        self.phase = 4

    def phase_risk(self) -> None:
        self._require_phase(4)
        assert self.current_timestamp is not None
        day = self.current_timestamp[:10]
        current = self.nav()
        if self._partition_day_pending:
            self.current_day = day
            self._partition_day_pending = False
        elif self.current_day != day:
            self.current_day = day
            self.day_start_nav = self.last_reconciled_nav
        daily = current / self.day_start_nav - 1
        drawdown = current / self.high_water_nav - 1
        if daily <= DAILY_LOSS_LIMIT or drawdown <= DRAWDOWN_LIMIT:
            self.state.new_exposure_enabled = False
        self.phase = 5

    def phase_orders_complete(self, margin_rules: MarginRules | None = None) -> None:
        self._require_phase(5)
        self.check_margin(margin_rules or self.margin_rules, self.perpetual_mark, checkpoint="post_fill")
        self.phase = 6

    def phase_post_fill_complete(self, margin_rules: MarginRules | None = None) -> None:
        self._require_phase(6)
        self.check_margin(margin_rules or self.margin_rules, self.perpetual_mark, checkpoint="post_fill")
        self.phase = 7

    def phase_intrabar_close(self, *, high: Decimal, low: Decimal, close_spot: Decimal,
                              close_perpetual: Decimal, margin_rules: MarginRules | None = None) -> None:
        self._require_phase(7)
        high, low = D(high), D(low)
        effective_margin = margin_rules or self.margin_rules
        if self.state.perpetual_quantity > 0:
            self._refresh_unrealized(low)
            self.check_margin(effective_margin, low, checkpoint="adverse_intrabar")
        elif self.state.perpetual_quantity < 0:
            self._refresh_unrealized(high)
            self.check_margin(effective_margin, high, checkpoint="adverse_intrabar")
        if self.state.status is not State.LIQUIDATED:
            close_spot, close_perpetual = D(close_spot), D(close_perpetual)
            self.price_pnl_spot += self.state.spot_quantity * (close_spot - self.spot_mark)
            self.price_pnl_perpetual += self.state.perpetual_quantity * (close_perpetual - self.perpetual_mark)
            self.spot_mark = close_spot
            self._refresh_unrealized(close_perpetual)
            self.check_margin(effective_margin, close_perpetual, checkpoint="close")
        self.phase = 8

    def phase_reconcile(self) -> None:
        self._require_phase(8)
        before = self.state_digest()
        current = self.nav()
        self.high_water_nav = max(self.high_water_nav, current)
        self.last_reconciled_nav = current
        self.previous_spot_mark = self.spot_mark
        self.previous_perpetual_mark = self.perpetual_mark
        self._emit("account", {
            "timestamp": self.current_timestamp, "segment_id": "synthetic",
            **self.state_object(), "NAV": current,
            "gross_exposure": self.state.spot_quantity * self.spot_mark
                + abs(self.state.perpetual_quantity * self.perpetual_mark),
            "net_exposure": self.state.spot_quantity * self.spot_mark
                + self.state.perpetual_quantity * self.perpetual_mark,
            "margin_equity": self.margin_equity(), "maintenance_requirement": "not_applicable",
            "source_digest": self.mark_lineage.source_sha256,
            "rules_digest": canonical_digest([self.binding.spot_rules_digest,
                                               self.binding.perpetual_rules_digest]),
            "mark_source_digest": self.mark_lineage.source_sha256,
            "index_source_digest": "not_applicable",
        }, before)
        self.phase = 0

    def margin_equity(self) -> Decimal:
        return self.state.isolated_collateral + self.state.unrealized_pnl - self.state.exit_cost_reserve_memo

    def check_margin(self, rules: MarginRules, mark: Decimal, *, checkpoint: str) -> str:
        mark = D(mark)
        self._refresh_unrealized(mark)
        if self.state.perpetual_quantity == 0 or self.state.status is State.LIQUIDATED:
            return "flat"
        requirement = abs(self.state.perpetual_quantity) * mark * rules.maintenance_rate + rules.add_on
        equity = self.margin_equity()
        if equity <= requirement:
            self.liquidate(mark, rules, checkpoint=checkpoint)
            return "liquidated"
        if equity < rules.minimum_buffer:
            self.state.new_exposure_enabled = False
            if not any(a.get("kind") == "planning_buffer_exit" for a in self.state.pending_safety_actions):
                self.state.pending_safety_actions.append({"kind": "planning_buffer_exit", "quantity": abs(self.state.perpetual_quantity)})
            return "planning_buffer"
        return "ok"

    def _fee_amounts(self, quantity: Decimal, price: Decimal, fee: Fee) -> tuple[Decimal, Decimal]:
        native = abs(quantity) * price * fee.rate if fee.asset == "quote" else abs(quantity) * fee.rate
        if fee.asset == "third":
            if fee.third_asset_mark is None or fee.lineage is None:
                raise AccountingError("third-asset fee requires point-in-time mark and lineage")
            assert self.current_timestamp is not None
            fee.lineage.require_available(self.current_timestamp)
            quote = native * fee.third_asset_mark + fee.tax_quote
        elif fee.asset == "base":
            quote = native * price + fee.tax_quote
        else:
            native += fee.tax_quote
            quote = native
        return native, quote

    def _validate_fee_matches_scenario(self, fill: FillSpec) -> None:
        rates = SCENARIOS["candle-severe-80bps-rt-v1"] if fill.authorization == "forced" else SCENARIOS[self.binding.scenario_id]
        if fill.fee.rate != rates[0]:
            raise AccountingError("arbitrary caller fee rejected")
        expected_implicit = abs(fill.signed_quantity) * fill.price * rates[1]
        if fill.implicit_cost_quote != expected_implicit:
            raise AccountingError("arbitrary caller implicit cost rejected")

    def apply_fill(self, fill: FillSpec, *, margin_rules: MarginRules | None = None,
                   scenario_enforced: bool = True, _atomic_pair: bool = False,
                   _allow_delayed_safety: bool = False) -> dict[str, Any]:
        self._require_phase(2, 5)
        if fill.timestamp != self.current_timestamp and not (
            _allow_delayed_safety and fill.authorization == "forced"
            and self.current_timestamp is not None and fill.timestamp > self.current_timestamp
        ):
            raise AccountingError("fill timestamp must equal active event timestamp")
        if fill.fill_id in self._fill_ids or fill.order_id in self._order_ids:
            raise AccountingError("duplicate fill or order identity")
        fill.source.require_available(fill.timestamp)
        if fill.source.segment_id != self.segment_id:
            if not (_allow_delayed_safety and fill.authorization == "forced"):
                raise AccountingError("cross-segment fill input")
            self.segment_id = fill.source.segment_id
            self.current_day = None
        if _allow_delayed_safety and fill.timestamp != self.current_timestamp:
            self.current_timestamp = fill.timestamp
            self.event_sequence += 1
        fill.rules.validate_order(fill.signed_quantity, fill.price)
        reduction = ((fill.instrument == SPOT and fill.signed_quantity < 0)
                     or (fill.instrument == PERPETUAL and self.state.perpetual_quantity != 0
                         and self.state.perpetual_quantity * fill.signed_quantity < 0))
        protective = fill.authorization in ("protective", "forced", "terminal")
        self._assert_mutable(reduction=reduction, protective=protective)
        if self.binding.mandate_kind == "pair" and not (_atomic_pair or protective):
            raise AccountingError("pair mandate operations require an atomic pair intention")
        if protective:
            if fill.instrument == SPOT and fill.signed_quantity > 0:
                raise AccountingError("protective spot fill must reduce")
            if fill.instrument == PERPETUAL and abs(self.state.perpetual_quantity + fill.signed_quantity) > abs(self.state.perpetual_quantity):
                raise AccountingError("protective perpetual fill must reduce")
        if scenario_enforced:
            self._validate_fee_matches_scenario(fill)
        if not reduction and not protective and self.binding.mandate_kind != "pair":
            projected_spot = ((self.state.spot_quantity + fill.signed_quantity) * fill.price
                              if fill.instrument == SPOT else self.state.spot_quantity * self.spot_mark)
            projected_perp = (abs((self.state.perpetual_quantity + fill.signed_quantity) * fill.price)
                              if fill.instrument == PERPETUAL else abs(self.state.perpetual_quantity * self.perpetual_mark))
            self._cap_check(projected_spot, projected_perp)
        increasing_exposure = not reduction and not protective
        if increasing_exposure:
            if fill.reference_price is None:
                raise AccountingError("entry requires a bound reference price")
            if not self.price_within_entry_cap(reference_price=fill.reference_price,
                                               executable_price=fill.price,
                                               signed_quantity=fill.signed_quantity):
                raise AccountingError("entry executable price exceeds scenario cap")
        native_fee, quote_fee = self._fee_amounts(fill.signed_quantity, fill.price, fill.fee)
        self._preflight_fee(fill, native_fee)
        self._preflight_transition(fill, native_fee, quote_fee)
        before = self.state_digest()
        incoming_mark = self.spot_mark if fill.instrument == SPOT else self.perpetual_mark
        incoming_quantity = self.state.spot_quantity if fill.instrument == SPOT else self.state.perpetual_quantity
        fill_price_pnl = incoming_quantity * (fill.price - incoming_mark)
        if fill.instrument == SPOT:
            self.price_pnl_spot += fill_price_pnl
            self.spot_mark = fill.price
        else:
            self.price_pnl_perpetual += fill_price_pnl
            self._refresh_unrealized(fill.price)
        # A fill always has a corresponding complete order record.  Rejected,
        # expired and unfilled orders use record_order directly and never call here.
        self._emit("order", {
            "order_id": fill.order_id, "decision_id": "synthetic-fixture",
            "created_at": fill.timestamp, "arrival_at": fill.timestamp,
            "instrument": fill.instrument, "requested_quantity": fill.signed_quantity,
            "rounded_quantity": fill.signed_quantity, "filled_quantity": fill.signed_quantity,
            "unfilled_quantity": Decimal("0"), "status": "filled", "reason": "filled",
            "price_bound": fill.price, "source_digest": fill.source.source_sha256,
            "rules_digest": fill.rules.digest,
        }, before)
        self._order_ids.add(fill.order_id)
        pre_spot = self.state.spot_quantity
        pre_perpetual = self.state.perpetual_quantity
        pre_realized = self.state.realized_pnl
        start_nav = self.nav(spot_mark=fill.price if fill.instrument == SPOT else None,
                             perpetual_mark=fill.price if fill.instrument == PERPETUAL else None)
        if fill.instrument == SPOT:
            self._spot_transition(fill, native_fee)
        elif fill.instrument == PERPETUAL:
            quote_balance_cost = (native_fee if fill.fee.asset == "quote" else fill.fee.tax_quote)
            self._perpetual_transition(fill, quote_balance_cost, fill.implicit_cost_quote)
        else:
            raise AccountingError("wrong instrument")
        self._apply_nonquote_fee(fill, native_fee)
        self.state.explicit_costs += quote_fee
        self.state.implicit_costs += fill.implicit_cost_quote
        if fill.instrument == SPOT:
            self.state.quote_cash -= fill.implicit_cost_quote + (
                fill.fee.tax_quote if fill.fee.asset != "quote" else Decimal("0")
            )
            self.spot_mark = fill.price
        else:
            self._refresh_unrealized(fill.price)
        end_nav = self.nav(spot_mark=fill.price if fill.instrument == SPOT else None,
                           perpetual_mark=fill.price if fill.instrument == PERPETUAL else None)
        residual = end_nav - start_nav + quote_fee + fill.implicit_cost_quote
        if abs(residual) > QUOTE_QUANTUM:
            raise AccountingError("fill accounting identity failed")
        row = self._emit("fill", {
            "fill_id": fill.fill_id, "order_id": fill.order_id, "fill_at": fill.timestamp,
            "instrument": fill.instrument, "signed_quantity": fill.signed_quantity,
            "accounting_fill_price": fill.price, "explicit_fee_native": native_fee,
            "explicit_fee_asset": fill.fee.asset, "explicit_fee_quote_equivalent": quote_fee,
            "implicit_cost_quote": fill.implicit_cost_quote,
            "post_fill_position": self.state.spot_quantity if fill.instrument == SPOT else self.state.perpetual_quantity,
            "rules_digest": fill.rules.digest, "source_digest": fill.source.source_sha256,
            "authorization": fill.authorization,
        }, before, residual=residual)
        self._fill_ids.add(fill.fill_id)
        self._track_episode(fill, row, pre_spot=pre_spot, pre_perpetual=pre_perpetual,
                            realized_delta=(self.state.realized_pnl - pre_realized
                                            if fill.instrument == PERPETUAL else fill_price_pnl),
                            total_cost=quote_fee + fill.implicit_cost_quote,
                            reduction=reduction)
        self.check_margin(margin_rules or self.margin_rules, self.perpetual_mark,
                          checkpoint="after_each_fill")
        return row

    def _preflight_fee(self, fill: FillSpec, native_fee: Decimal) -> None:
        if fill.fee.asset == "third":
            balance = self.state.fee_asset_balances.get("third")
            if balance is None or balance < native_fee:
                raise AccountingError("insufficient third fee asset")
        if fill.fee.asset == "base":
            available = self.state.spot_quantity + (
                fill.signed_quantity if fill.instrument == SPOT and fill.signed_quantity > 0 else Decimal("0")
            )
            required = native_fee + (
                abs(fill.signed_quantity) if fill.instrument == SPOT and fill.signed_quantity < 0 else Decimal("0")
            )
            if available < required:
                raise AccountingError("insufficient base fee asset")
        if fill.fee.asset != "quote" and fill.fee.tax_quote:
            balance = self.state.quote_cash if fill.instrument == SPOT else self.state.isolated_collateral
            if balance < fill.fee.tax_quote:
                raise AccountingError("insufficient quote balance for tax")

    def _preflight_transition(self, fill: FillSpec, native_fee: Decimal,
                              quote_equivalent: Decimal) -> None:
        q, p = fill.signed_quantity, fill.price
        quote_balance_cost = native_fee if fill.fee.asset == "quote" else fill.fee.tax_quote
        if fill.instrument == SPOT:
            if self.binding.mandate_kind not in ("spot", "pair"):
                raise AccountingError("spot operation forbidden by selected mandate")
            if q > 0:
                needed = q * p + quote_balance_cost + fill.implicit_cost_quote
                if self.state.quote_cash < needed:
                    raise AccountingError("insufficient quote cash")
            else:
                needed_base = abs(q) + (native_fee if fill.fee.asset == "base" else 0)
                if self.state.spot_quantity < needed_base:
                    raise AccountingError("spot borrowing/oversell forbidden")
        else:
            if self.binding.mandate_kind not in ("directional", "pair"):
                raise AccountingError("perpetual operation forbidden by selected mandate")
            old, new = self.state.perpetual_quantity, self.state.perpetual_quantity + q
            if old != 0 and old * new < 0:
                raise AccountingError("reversal must be represented as close then new fill")
            if old == 0 or old * q > 0:
                margin = abs(q) * p / self.binding.leverage
                if self.state.quote_cash < margin:
                    raise AccountingError("insufficient collateral transfer")
                available = self.state.isolated_collateral + margin
            else:
                assert self.state.average_perpetual_entry is not None
                closed = min(abs(q), abs(old))
                available = self.state.isolated_collateral + closed * (
                    Decimal("1") if old > 0 else Decimal("-1")
                ) * (p - self.state.average_perpetual_entry)
            if available < quote_balance_cost + fill.implicit_cost_quote:
                raise AccountingError("perpetual costs not funded by isolated collateral")

    def _spot_transition(self, fill: FillSpec, native_fee: Decimal) -> None:
        q, p = fill.signed_quantity, fill.price
        if self.binding.mandate_kind not in ("spot", "pair"):
            raise AccountingError("spot operation forbidden by selected mandate")
        if q > 0:
            required = q * p + (native_fee if fill.fee.asset == "quote" else 0)
            if self.state.quote_cash < required + fill.implicit_cost_quote:
                raise AccountingError("insufficient quote cash")
            self.state.quote_cash -= q * p
            self.state.spot_quantity += q
        else:
            gross = abs(q)
            required_base = gross + (native_fee if fill.fee.asset == "base" else 0)
            if self.state.spot_quantity < required_base:
                raise AccountingError("spot borrowing/oversell forbidden")
            self.state.spot_quantity -= gross
            self.state.quote_cash += gross * p
        if fill.fee.asset == "quote":
            if self.state.quote_cash < native_fee:
                raise AccountingError("insufficient quote fee balance")
            self.state.quote_cash -= native_fee

    def _apply_nonquote_fee(self, fill: FillSpec, native_fee: Decimal) -> None:
        if fill.fee.asset == "base":
            if self.state.spot_quantity < native_fee:
                raise AccountingError("insufficient/unsupported base fee balance")
            self.state.spot_quantity -= native_fee
        elif fill.fee.asset == "third":
            balance = self.state.fee_asset_balances.get("third")
            if balance is None or balance < native_fee:
                raise AccountingError("insufficient third fee asset")
            self.state.fee_asset_balances["third"] = balance - native_fee

    def _perpetual_transition(self, fill: FillSpec, quote_fee: Decimal,
                              implicit_cost: Decimal) -> None:
        if self.binding.mandate_kind not in ("directional", "pair"):
            raise AccountingError("perpetual operation forbidden by selected mandate")
        old, delta, price = self.state.perpetual_quantity, fill.signed_quantity, fill.price
        new = old + delta
        increasing = old == 0 or old * delta > 0
        reversing = old != 0 and old * new < 0
        if reversing:
            raise AccountingError("reversal must be represented as close then new fill")
        if increasing:
            margin = abs(delta) * price / self.binding.leverage
            if self.state.quote_cash < margin:
                raise AccountingError("insufficient collateral transfer")
            self.state.quote_cash -= margin
            self.state.isolated_collateral += margin
            self.state.allocated_initial_margin_memo += margin
            if old == 0:
                self.state.average_perpetual_entry = price
            else:
                assert self.state.average_perpetual_entry is not None
                self.state.average_perpetual_entry = (
                    abs(old) * self.state.average_perpetual_entry + abs(delta) * price
                ) / abs(new)
        else:
            closed = min(abs(delta), abs(old))
            assert self.state.average_perpetual_entry is not None
            realized = closed * (Decimal("1") if old > 0 else Decimal("-1")) * (
                price - self.state.average_perpetual_entry)
            self.state.isolated_collateral += realized
            self.state.realized_pnl += realized
            old_memo = self.state.allocated_initial_margin_memo
            memo_release = old_memo * closed / abs(old)
            self.state.allocated_initial_margin_memo -= memo_release
            # Costs settle before collateral release.
            if self.state.isolated_collateral < quote_fee + implicit_cost:
                raise AccountingError("perpetual costs not funded by isolated collateral")
            cash_release = min(memo_release, max(self.state.isolated_collateral - quote_fee - implicit_cost, Decimal("0")))
            self.state.quote_cash += cash_release
            self.state.isolated_collateral -= cash_release
        if self.state.isolated_collateral < quote_fee + implicit_cost:
            raise AccountingError("perpetual quote fee not funded")
        self.state.isolated_collateral -= quote_fee + implicit_cost
        self.state.perpetual_quantity = new
        if new == 0:
            self.state.average_perpetual_entry = None
            self.state.allocated_initial_margin_memo = Decimal("0")
            self._settle_flat_collateral()

    def _track_episode(self, fill: FillSpec, row: Mapping[str, Any], *, pre_spot: Decimal,
                       pre_perpetual: Decimal, realized_delta: Decimal,
                       total_cost: Decimal, reduction: bool) -> None:
        before_exposure = pre_spot != 0 or pre_perpetual != 0
        after_exposure = self.state.spot_quantity != 0 or self.state.perpetual_quantity != 0
        if not before_exposure and after_exposure:
            direction = ("spot_long" if self.state.spot_quantity > 0 and self.state.perpetual_quantity == 0
                         else "long" if self.state.perpetual_quantity > 0
                         else "short" if self.state.spot_quantity == 0 else "delta_neutral_pair")
            self._episode = {
                "episode_id": f"episode-{fill.fill_id}", "opened_at": fill.timestamp,
                "direction": direction, "entry_costs": total_cost,
                "exit_costs": Decimal("0"), "price_PnL": Decimal("0"),
                "funding_PnL": Decimal("0"), "maximum_adverse_excursion": Decimal("0"),
                "maximum_favourable_excursion": Decimal("0"),
                "entry_fill_digests": [row["row_digest"]], "exit_fill_digests": [],
                "source_digests": [fill.source.source_sha256], "rules_digests": [fill.rules.digest],
            }
        elif self._episode is not None:
            self._episode["price_PnL"] += realized_delta
            if after_exposure:
                if reduction:
                    self._episode["exit_costs"] += total_cost
                    self._episode["exit_fill_digests"].append(row["row_digest"])
                else:
                    self._episode["entry_costs"] += total_cost
                    self._episode["entry_fill_digests"].append(row["row_digest"])
            else:
                self._episode["exit_costs"] += total_cost
                self._episode["exit_fill_digests"].append(row["row_digest"])
                self._episode["funding_PnL"] = self.state.accrued_funding
                self._episode["closed_at"] = fill.timestamp
                self._episode["net_dollar_PnL"] = (
                    self._episode["price_PnL"] + self._episode["funding_PnL"]
                    - self._episode["entry_costs"] - self._episode["exit_costs"]
                )
                self._episode["close_reason"] = fill.authorization
                self._episode["invalidation_reason"] = self.state.invalidation_reason
                before = self.state_digest()
                self._emit("closed_episode", self._episode, before)
                self._episode = None

    def _settle_flat_collateral(self) -> None:
        if self.state.isolated_collateral >= 0:
            self.state.quote_cash += self.state.isolated_collateral
        else:
            self.state.liabilities += -self.state.isolated_collateral
        self.state.isolated_collateral = Decimal("0")
        self.state.exit_cost_reserve_memo = Decimal("0")

    def _settle_negative_collateral_if_flat(self) -> None:
        if self.state.perpetual_quantity == 0 and self.state.isolated_collateral != 0:
            self._settle_flat_collateral()

    def reverse_perpetual(self, close_fill: FillSpec, open_fill: FillSpec,
                          margin_rules: MarginRules | None = None) -> None:
        if abs(close_fill.signed_quantity) != abs(self.state.perpetual_quantity):
            raise AccountingError("reversal close must flatten exactly")
        self.apply_fill(close_fill, margin_rules=margin_rules)
        if self.state.status is State.LIQUIDATED:
            return
        self.apply_fill(open_fill, margin_rules=margin_rules)

    def liquidate(self, mark: Decimal, rules: MarginRules, *, checkpoint: str) -> None:
        if self.state.status is State.LIQUIDATED or self.state.perpetual_quantity == 0:
            return
        before = self.state_digest()
        q = self.state.perpetual_quantity
        entry = self.state.average_perpetual_entry
        assert entry is not None and self.current_timestamp is not None
        realized = abs(q) * (Decimal("1") if q > 0 else Decimal("-1")) * (D(mark) - entry)
        fee = abs(q) * D(mark) * rules.liquidation_fee_rate
        self.state.isolated_collateral += realized - fee
        self.state.realized_pnl += realized
        self.state.explicit_costs += fee
        self.state.perpetual_quantity = Decimal("0")
        self.state.average_perpetual_entry = None
        self.state.unrealized_pnl = Decimal("0")
        self.state.allocated_initial_margin_memo = Decimal("0")
        self.state.exit_cost_reserve_memo = Decimal("0")
        self._settle_flat_collateral()
        self.state.status = State.LIQUIDATED
        self.state.new_exposure_enabled = False
        self.state.invalidation_reason = f"observed_liquidation:{checkpoint}"
        order_id = f"liq-order-{self.event_sequence}"
        common = {
            "source_digest": "synthetic_observed_mark", "rules_digest": rules.digest,
            "invalidation_reason": self.state.invalidation_reason,
        }
        self._emit("order", {
            "order_id": order_id, "decision_id": "protective-liquidation",
            "created_at": self.current_timestamp, "arrival_at": self.current_timestamp,
            "instrument": PERPETUAL, "requested_quantity": -q, "rounded_quantity": -q,
            "filled_quantity": -q, "unfilled_quantity": Decimal("0"), "status": "filled",
            "reason": "observed_liquidation", "price_bound": "not_applicable",
            **common,
        }, before)
        fill_row = {
            "fill_id": f"liq-fill-{self.event_sequence}", "order_id": order_id,
            "fill_at": self.current_timestamp, "instrument": PERPETUAL,
            "signed_quantity": -q, "accounting_fill_price": mark,
            "explicit_fee_native": fee, "explicit_fee_asset": "quote",
            "explicit_fee_quote_equivalent": fee, "implicit_cost_quote": Decimal("0"),
            "post_fill_position": Decimal("0"), **common,
        }
        self._emit("fill", fill_row, before)
        episode = self._episode or {
            "episode_id": f"episode-{self.event_sequence}", "opened_at": "synthetic_preloaded",
            "direction": "long" if q > 0 else "short", "entry_costs": Decimal("0"),
            "entry_fill_digests": [], "price_PnL": Decimal("0"), "funding_PnL": Decimal("0"),
            "maximum_adverse_excursion": realized, "maximum_favourable_excursion": Decimal("0"),
            "source_digests": [], "rules_digests": [],
        }
        episode.update({
            "closed_at": self.current_timestamp, "exit_costs": fee,
            "price_PnL": D(episode.get("price_PnL", 0)) + realized,
            "funding_PnL": D(episode.get("funding_PnL", 0)),
            "net_dollar_PnL": D(episode.get("price_PnL", 0)) + realized
                + D(episode.get("funding_PnL", 0)) - D(episode.get("entry_costs", 0)) - fee,
            "close_reason": "liquidation", "exit_fill_digests": [canonical_digest(fill_row)],
            "invalidation_reason": self.state.invalidation_reason,
        })
        self._emit("closed_episode", episode, before)
        self._episode = None

    def mark_unknown(self, reason: str, pending: Mapping[str, Any] | None = None) -> None:
        if self.state.status not in (State.LIQUIDATED, State.TERMINAL):
            self.state.status = State.UNKNOWN
            self.state.new_exposure_enabled = False
            self.state.invalidation_reason = reason
            if pending is not None:
                self.state.pending_safety_actions.append(dict(pending))

    def exposed_gap(self, *, next_spot_open: Decimal | None = None,
                    next_perpetual_open: Decimal | None = None,
                    protective_fills: Sequence[FillSpec] = ()) -> None:
        exposed = self.state.spot_quantity != 0 or self.state.perpetual_quantity != 0
        if not exposed:
            self.current_day = None
            return
        self.mark_unknown("missing_bar_while_exposed")
        if not protective_fills:
            self.state.pending_safety_actions.append({"kind": "gap_neutralization"})
            return
        for fill in protective_fills:
            if fill.authorization != "forced":
                raise AccountingError("gap completion must be forced")
            self.apply_fill(fill, _allow_delayed_safety=(
                fill.timestamp != self.current_timestamp or fill.source.segment_id != self.segment_id
            ))
        if self.state.spot_quantity == 0 and self.state.perpetual_quantity == 0:
            self.state.pending_safety_actions.clear()

    def terminal_flatten(self, fills: Sequence[FillSpec]) -> None:
        for fill in fills:
            if fill.authorization != "terminal":
                raise AccountingError("terminal event only accepts declared terminal reductions")
            self.apply_fill(fill)
        if self.state.spot_quantity != 0 or self.state.perpetual_quantity != 0:
            raise AccountingError("terminal flatten incomplete")
        self.state.status = State.TERMINAL
        self.state.new_exposure_enabled = False

    def _cap_check(self, spot_notional: Decimal, perp_notional: Decimal) -> None:
        equity = self.nav()
        kind = self.binding.mandate_kind
        if kind == "spot" and (perp_notional != 0 or spot_notional > equity * Decimal("0.25")):
            raise AccountingError("spot mandate exposure cap/instrument breach")
        if kind == "directional" and (spot_notional != 0 or perp_notional > equity * Decimal("0.25")):
            raise AccountingError("directional mandate exposure cap/instrument breach")
        if kind == "pair" and (spot_notional > equity * Decimal("0.5") or perp_notional > equity * Decimal("0.5")):
            raise AccountingError("pair leg cap breach")

    def price_within_entry_cap(self, *, reference_price: Decimal, executable_price: Decimal,
                               signed_quantity: Decimal, protective: bool = False) -> bool:
        reference_price, executable_price, signed_quantity = map(
            D, (reference_price, executable_price, signed_quantity)
        )
        if reference_price <= 0 or executable_price <= 0 or signed_quantity == 0:
            raise AccountingError("invalid price-cap input")
        if protective:
            return True
        cap = SCENARIOS[self.binding.scenario_id][2]
        if signed_quantity > 0:
            return executable_price <= reference_price * (Decimal("1") + cap)
        return executable_price >= reference_price * (Decimal("1") - cap)

    def atomic_pair_entry(self, spot_fill: FillSpec, perpetual_fill: FillSpec | None,
                          *, severe_perpetual_close: FillSpec | None = None,
                          severe_spot_close: FillSpec | None = None,
                          margin_rules: MarginRules | None = None) -> None:
        self._require_phase(5)
        if self.binding.mandate_kind != "pair" or spot_fill.instrument != SPOT or spot_fill.signed_quantity <= 0:
            raise AccountingError("pair entry requires delta-neutral mandate and spot buy first")
        if perpetual_fill is not None and (perpetual_fill.instrument != PERPETUAL or perpetual_fill.signed_quantity >= 0):
            raise AccountingError("pair second leg must short perpetual")
        self._cap_check(spot_fill.signed_quantity * spot_fill.price,
                        abs(perpetual_fill.signed_quantity * perpetual_fill.price) if perpetual_fill else Decimal("0"))
        # Preflight severe recovery before committing first leg.  Candle second legs
        # are all-or-none, but their zero endpoint must still be recoverable.
        if severe_spot_close is None:
            raise AccountingError("unproven pair-entry neutralization path")
        if severe_spot_close.authorization != "forced" or severe_spot_close.instrument != SPOT:
            raise AccountingError("pair-entry severe recovery must be a forced spot close")
        spot_fill.rules.validate_order(spot_fill.signed_quantity, spot_fill.price)
        severe_spot_close.rules.validate_order(severe_spot_close.signed_quantity, severe_spot_close.price)
        self._validate_fee_matches_scenario(spot_fill)
        self._validate_fee_matches_scenario(severe_spot_close)
        projected_native, _ = self._fee_amounts(spot_fill.signed_quantity, spot_fill.price, spot_fill.fee)
        projected_net = spot_fill.signed_quantity - (projected_native if spot_fill.fee.asset == "base" else 0)
        if severe_spot_close.signed_quantity >= 0:
            raise AccountingError("entry recovery spot order must sell")
        severe_native, _ = self._fee_amounts(severe_spot_close.signed_quantity,
                                             severe_spot_close.price, severe_spot_close.fee)
        recovered = abs(severe_spot_close.signed_quantity) + (
            severe_native if severe_spot_close.fee.asset == "base" else 0
        )
        if recovered != projected_net:
            raise AccountingError("entry recovery must deterministically flatten projected net spot")
        self.apply_fill(spot_fill, margin_rules=margin_rules, _atomic_pair=True)
        actual_net = self.state.spot_quantity
        if perpetual_fill is not None:
            try:
                self.apply_fill(perpetual_fill, margin_rules=margin_rules, _atomic_pair=True)
            except AccountingError:
                # First fill remains irrevocably committed.
                self.apply_fill(severe_spot_close, margin_rules=margin_rules, _atomic_pair=True)
                return
        else:
            self.record_order(
                order_id=f"pair-entry-missing-perp-{self.event_sequence}", decision_id="atomic-pair-entry",
                instrument=PERPETUAL, requested_quantity=-actual_net, rounded_quantity=-actual_net,
                filled_quantity=Decimal("0"), status="rejected", reason="second_leg_failure",
                price_bound="not_available", source_digest="not_applicable",
                rules_digest=self.binding.perpetual_rules_digest,
            )
        mismatch = self._fraction_mismatch(actual_net, abs(self.state.perpetual_quantity))
        if mismatch > PAIR_MISMATCH_LIMIT:
            if self.state.perpetual_quantity != 0:
                if severe_perpetual_close is None:
                    self.mark_unknown("pair_entry_second_leg_failure", {"kind": "forced_perpetual_close"})
                    return
                if (severe_perpetual_close.authorization != "forced"
                        or severe_perpetual_close.signed_quantity != -self.state.perpetual_quantity):
                    raise AccountingError("entry recovery closes committed perpetual first")
                self.apply_fill(severe_perpetual_close, margin_rules=margin_rules, _atomic_pair=True)
            if severe_spot_close is None:
                self.mark_unknown("pair_entry_second_leg_failure", {"kind": "forced_spot_close"})
                return
            self.apply_fill(severe_spot_close, margin_rules=margin_rules, _atomic_pair=True)
            if self.state.spot_quantity != 0 or self.state.perpetual_quantity != 0:
                self.mark_unknown("pair_entry_neutralization_incomplete")

    @staticmethod
    def _fraction_mismatch(left: Decimal, right: Decimal) -> Decimal:
        left, right = abs(D(left)), abs(D(right))
        if left == 0 and right == 0:
            return Decimal("0")
        if left == 0 or right == 0:
            return Decimal("1")
        return abs(left - right) / max(left, right)

    @staticmethod
    def solve_full_spot_sale(inventory: Decimal, fee_rate: Decimal,
                             rules: InstrumentRules) -> Decimal:
        inventory, fee_rate = D(inventory), D(fee_rate)
        if inventory <= 0 or fee_rate < 0:
            raise AccountingError("invalid full-sale solver input")
        gross = rules.quantity(inventory / (Decimal("1") + fee_rate))
        if gross <= 0 or gross + gross * fee_rate != inventory:
            raise AccountingError("rule quantization leaves voluntary close dust")
        return gross

    def validate_pair_outcomes(self, outcomes: Sequence[PairOutcome], *, full_reduction: Decimal,
                               incoming_short: Decimal, collateral: Decimal,
                               initial_margin_memo: Decimal, entry_price: Decimal) -> str:
        if not outcomes:
            raise AccountingError("empty Cartesian outcome set")
        full_reduction, incoming_short = D(full_reduction), D(incoming_short)
        keys = [canonical_digest(item) for item in outcomes]
        if len(keys) != len(set(keys)):
            raise AccountingError("duplicate pair outcomes")
        reductions = {item.spot_reduction for item in outcomes}
        if Decimal("0") not in reductions or full_reduction not in reductions:
            raise AccountingError("outcome set lacks zero/full spot endpoints")
        by_reduction: dict[Decimal, set[Decimal]] = {}
        for item in outcomes:
            by_reduction.setdefault(item.spot_reduction, set()).add(item.perpetual_fill)
        for reduction, fills in by_reduction.items():
            if Decimal("0") not in fills or reduction not in fills:
                raise AccountingError("Cartesian outcome set lacks zero/full perpetual endpoints")
        if self.binding.adapter_id == "candle_OHLC":
            if reductions != {Decimal("0"), full_reduction}:
                raise AccountingError("candle adapter spot outcomes must be zero/full only")
            for reduction, fills in by_reduction.items():
                if fills != ({Decimal("0")} if reduction == 0 else {Decimal("0"), reduction}):
                    raise AccountingError("candle adapter perpetual outcomes must be zero/full only")
        for item in outcomes:
            r, q = item.spot_reduction, item.perpetual_fill
            if r > incoming_short or q > incoming_short:
                raise AccountingError("outcome crosses short position")
            cpre = D(collateral) + q * (D(entry_price) - item.perpetual_vwap)
            if cpre < item.ordinary_fee_quote + item.ordinary_implicit_quote:
                raise AccountingError("ordinary close path fee-unfunded")
            release = min(D(initial_margin_memo) * q / incoming_short if incoming_short else 0,
                          max(cpre - item.ordinary_fee_quote - item.ordinary_implicit_quote, Decimal("0")))
            c1 = cpre - item.ordinary_fee_quote - item.ordinary_implicit_quote - release
            residual = r - q
            ordinary_rates = SCENARIOS[self.binding.scenario_id]
            if item.ordinary_fee_quote != q * item.perpetual_vwap * ordinary_rates[0]:
                raise AccountingError("outcome ordinary fee does not match bound scenario")
            if item.ordinary_implicit_quote != q * item.perpetual_vwap * ordinary_rates[1]:
                raise AccountingError("outcome ordinary implicit cost does not match bound scenario")
            if residual:
                severe_rates = SCENARIOS["candle-severe-80bps-rt-v1"]
                if item.severe_fee_quote != residual * item.severe_price * severe_rates[0]:
                    raise AccountingError("outcome severe fee does not match frozen severe schedule")
                if item.severe_implicit_quote != residual * item.severe_price * severe_rates[1]:
                    raise AccountingError("outcome severe implicit cost does not match frozen severe schedule")
                cpre2 = c1 + residual * (D(entry_price) - item.severe_price)
                if cpre2 < item.severe_fee_quote + item.severe_implicit_quote:
                    raise AccountingError("severe residual path fee-unfunded")
        return canonical_digest(sorted((_canonical(item) for item in outcomes), key=canonical_json_bytes))

    def atomic_pair_close(self, *, spot_fill: FillSpec, perpetual_fill: FillSpec | None,
                          severe_residual_fill: FillSpec | None, outcomes: Sequence[PairOutcome],
                          full_reduction: Decimal, spot_mark: Decimal, perpetual_mark: Decimal,
                          initial_margin_memo: Decimal, margin_rules: MarginRules | None = None,
                          delayed: bool = False, new_segment: bool = False,
                          mismatch_spot_fill: FillSpec | None = None,
                          mismatch_perpetual_fill: FillSpec | None = None) -> dict[str, Any]:
        self._require_phase(5)
        if self.binding.mandate_kind != "pair" or self.state.perpetual_quantity >= 0:
            raise AccountingError("pair close requires existing short pair")
        incoming_short = abs(self.state.perpetual_quantity)
        spot_native, _ = self._fee_amounts(spot_fill.signed_quantity, spot_fill.price, spot_fill.fee)
        prospective_reduction = abs(spot_fill.signed_quantity) + (
            spot_native if spot_fill.fee.asset == "base" else Decimal("0")
        )
        if prospective_reduction != D(full_reduction) or prospective_reduction > incoming_short:
            raise AccountingError("pair-close declared reduction does not equal actual fee-adjusted spot reduction")
        if (D(full_reduction) == self.state.spot_quantity
                and prospective_reduction != self.state.spot_quantity):
            raise AccountingError("voluntary base-fee full close would leave dust")
        if spot_fill.fee.asset == "base" and D(full_reduction) == self.state.spot_quantity:
            solved = self.solve_full_spot_sale(self.state.spot_quantity, spot_fill.fee.rate,
                                               spot_fill.rules)
            if abs(spot_fill.signed_quantity) != solved:
                raise AccountingError("spot fill differs from deterministic full-sale solver")
        digest = self.validate_pair_outcomes(
            outcomes, full_reduction=D(full_reduction), incoming_short=incoming_short,
            collateral=self.state.isolated_collateral, initial_margin_memo=initial_margin_memo,
            entry_price=self.state.average_perpetual_entry or Decimal("0"),
        )
        self._pair_outcome_digest = digest
        if (self.binding.adapter_id == "candle_OHLC" and severe_residual_fill is not None
                and severe_residual_fill.price != D(perpetual_mark)):
            raise AccountingError("candle severe fill must use exact same-instrument open")
        pre_spot = self.state.spot_quantity
        self.apply_fill(spot_fill, margin_rules=margin_rules, _atomic_pair=True)
        if margin_rules:
            self.check_margin(margin_rules, self.perpetual_mark, checkpoint="after_pair_spot_leg")
        if self.state.status is State.LIQUIDATED:
            return _canonical({"outcome_set_digest": digest, "terminated_by_liquidation": True})
        actual_reduction = pre_spot - self.state.spot_quantity
        if perpetual_fill is not None:
            if abs(perpetual_fill.signed_quantity) > actual_reduction:
                raise AccountingError("intended perpetual close exceeds actual spot reduction")
            self.apply_fill(perpetual_fill, margin_rules=margin_rules, _atomic_pair=True)
            intended = abs(perpetual_fill.signed_quantity)
        else:
            intended = Decimal("0")
            self.record_order(
                order_id=f"pair-close-missing-perp-{self.event_sequence}", decision_id="atomic-pair-close",
                instrument=PERPETUAL, requested_quantity=actual_reduction,
                rounded_quantity=actual_reduction, filled_quantity=Decimal("0"),
                status="rejected", reason="second_leg_failure", price_bound="not_available",
                source_digest="not_applicable", rules_digest=self.binding.perpetual_rules_digest,
            )
        residual = actual_reduction - intended
        if residual > 0:
            if severe_residual_fill is None:
                self.mark_unknown("pair_close_residual_pending", {"kind": "forced_buy_to_close", "quantity": residual})
            else:
                if severe_residual_fill.authorization != "forced" or severe_residual_fill.instrument != PERPETUAL:
                    raise AccountingError("residual close must be forced perpetual buy")
                if severe_residual_fill.signed_quantity != residual:
                    raise AccountingError("severe residual quantity mismatch")
                self.apply_fill(severe_residual_fill, margin_rules=margin_rules, _atomic_pair=True,
                                _allow_delayed_safety=delayed)
        q_mismatch = self._fraction_mismatch(self.state.spot_quantity, abs(self.state.perpetual_quantity))
        n_mismatch = self._fraction_mismatch(self.state.spot_quantity * D(spot_mark),
                                              abs(self.state.perpetual_quantity) * D(perpetual_mark))
        if (q_mismatch > PAIR_MISMATCH_LIMIT or n_mismatch > PAIR_MISMATCH_LIMIT) and self.state.status is State.ACTIVE:
            # Exactly one finite, non-recursive severe whole-pair attempt, spot first.
            if mismatch_spot_fill is not None:
                self.apply_fill(mismatch_spot_fill, margin_rules=margin_rules, _atomic_pair=True)
            if self.state.status is not State.LIQUIDATED and mismatch_perpetual_fill is not None:
                self.apply_fill(mismatch_perpetual_fill, margin_rules=margin_rules, _atomic_pair=True)
            if self.state.spot_quantity != 0 or self.state.perpetual_quantity != 0:
                self.mark_unknown("remaining_pair_mismatch_after_single_whole_pair_attempt",
                                  {"kind": "protective_cleanup", "attempts_remaining": 0})
        if delayed:
            self.state.invalidation_reason = self.state.invalidation_reason or "delayed_residual_neutralization"
            if new_segment:
                self.current_day = None
        result = {
            "actual_spot_inventory_reduction": actual_reduction,
            "intended_perpetual_filled_quantity": intended,
            "created_residual_naked_short_quantity": residual,
            "remaining_quantity_mismatch": q_mismatch,
            "remaining_notional_mismatch": n_mismatch,
            "common_spot_mark": D(spot_mark), "common_perpetual_mark": D(perpetual_mark),
            "delayed": delayed, "segment_reset": bool(delayed and new_segment),
            "semantic_settings_digest": self.binding.semantic_settings_digest,
            "outcome_set_digest": digest,
        }
        return _canonical(result)

    def buy_and_hold_entry_allowed(self, *, partition_start: str, observation_at: str) -> bool:
        return utc_timestamp(partition_start) == utc_timestamp(observation_at)

    def record_order(self, *, order_id: str, decision_id: str, instrument: str,
                     requested_quantity: Decimal, rounded_quantity: Decimal,
                     filled_quantity: Decimal, status: str, reason: str,
                     price_bound: Decimal | str, source_digest: str,
                     rules_digest: str) -> dict[str, Any]:
        if status not in ("submitted", "filled", "rejected", "expired", "partial", "unfilled"):
            raise AccountingError("unknown order status")
        if self.binding.adapter_id == "candle_OHLC" and status == "partial":
            raise AccountingError("candle adapter cannot emit partial fill")
        requested_quantity, rounded_quantity, filled_quantity = map(
            D, (requested_quantity, rounded_quantity, filled_quantity))
        if order_id in self._order_ids:
            raise AccountingError("duplicate order identity")
        before = self.state_digest()
        row = self._emit("order", {
            "order_id": order_id, "decision_id": decision_id,
            "created_at": self.current_timestamp, "arrival_at": self.current_timestamp,
            "instrument": instrument, "requested_quantity": requested_quantity,
            "rounded_quantity": rounded_quantity, "filled_quantity": filled_quantity,
            "unfilled_quantity": abs(rounded_quantity) - abs(filled_quantity),
            "status": status, "reason": reason, "price_bound": price_bound,
            "source_digest": source_digest, "rules_digest": rules_digest,
        }, before)
        self._order_ids.add(order_id)
        return row

    def record_decision(self, *, decision_id: str, reason: str,
                        source_digest: str, rules_digest: str) -> dict[str, Any]:
        before = self.state_digest()
        return self._emit("decision", {
            "decision_id": decision_id, "decision_at": self.current_timestamp,
            "available_information_cutoff": self.current_timestamp,
            "requested_target": "flat", "permission_or_abstention": "abstention",
            "reason": reason, "source_digest": source_digest,
            "rules_digest": rules_digest,
            "lineage_digest": canonical_digest(self._lineage()),
            "invalidation_reason": self.state.invalidation_reason,
        }, before)

    def missing_funding(self) -> None:
        if self.incoming_perpetual_quantity != 0:
            self.mark_unknown("missing_funding_while_exposed")

    def run_summary(self) -> dict[str, Any]:
        ending = self.nav()
        ledger_artifacts = {
            f"{name}_ledger.jsonl": sha256(canonical_jsonl(self.rows[name])).hexdigest()
            for name in ("decision", "order", "fill", "funding", "account", "closed_episode")
        }
        summary = {
            "starting_NAV": self.starting_nav, "ending_NAV": ending,
            "spot_price_PnL": self.price_pnl_spot,
            "perpetual_price_PnL": self.price_pnl_perpetual,
            "funding_PnL": self.state.accrued_funding,
            "explicit_costs": self.state.explicit_costs,
            "implicit_costs": self.state.implicit_costs,
            "neutralization_costs": sum((D(row["explicit_fee_quote_equivalent"]) + D(row["implicit_cost_quote"])
                                          for row in self.rows["fill"] if row.get("authorization") == "forced"), Decimal("0")),
            "diagnostic_opportunity_cost": Decimal("0"),
            "diagnostic_missed_unfilled_and_unused_rounded_notional": Decimal("0"),
            "accounting_residual": ending - self.starting_nav - self.price_pnl_spot
                - self.price_pnl_perpetual - self.state.accrued_funding
                + self.state.explicit_costs + self.state.implicit_costs,
            "rejected_expired_partial_and_unfilled_counts": {
                status: sum(row["status"] == status for row in self.rows["order"])
                for status in ("rejected", "expired", "partial", "unfilled")
            },
            "unknown_or_invalid_intervals": int(self.state.status is State.UNKNOWN),
            "artifact_digests": ledger_artifacts,
            "run_invalidation_reason": self.state.invalidation_reason,
            "actionable_arm_id": ACTIONABLE_ARM_ID,
            **self._lineage(),
        }
        summary["result_digest"] = canonical_digest(summary)
        return _canonical(summary)

    def artifacts(self) -> dict[str, bytes]:
        names = {
            "decision_ledger.jsonl": "decision", "order_ledger.jsonl": "order",
            "fill_ledger.jsonl": "fill", "funding_ledger.jsonl": "funding",
            "account_ledger.jsonl": "account", "closed_episode_ledger.jsonl": "closed_episode",
        }
        result = {path: canonical_jsonl(self.rows[ledger]) for path, ledger in names.items()}
        result["report.json"] = canonical_json_bytes(self.run_summary(), newline=True)
        manifest_entries = []
        for path, payload in sorted(result.items()):
            manifest_entries.append({"path": path, "sha256": sha256(payload).hexdigest(),
                                     "size_bytes": len(payload), "semantic_role": path.rsplit(".", 1)[0]})
        evidence = {
            "experiment_id": EXPERIMENT_ID, "run_id": self.binding.run_id,
            "actionable_arm_id": ACTIONABLE_ARM_ID, "artifacts": manifest_entries,
            **self._lineage(),
        }
        result["evidence_manifest.json"] = canonical_json_bytes(evidence, newline=True)
        return result


def canonical_jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row, newline=True) for row in rows)


__all__ = [
    "ACTIONABLE_ARM_ID", "AccountingError", "AccountingStateMachine", "CONTRACT_DIGESTS",
    "D", "DAILY_LOSS_LIMIT", "DRAWDOWN_LIMIT", "EXPERIMENT_ID", "Fee", "FillSpec",
    "FundingSpec", "InstrumentRules", "LedgerState", "MANDATES", "MarginRules",
    "PAIR_MISMATCH_LIMIT", "PERPETUAL", "PairOutcome", "PhaseError", "QUOTE_QUANTUM",
    "RunBinding", "SCENARIOS", "SPOT", "SourceLineage", "State", "canonical_digest",
    "canonical_candle_arrival", "canonical_json_bytes", "canonical_jsonl", "decimal_string", "implementation_digest",
    "strict_json_loads", "utc_timestamp",
]
