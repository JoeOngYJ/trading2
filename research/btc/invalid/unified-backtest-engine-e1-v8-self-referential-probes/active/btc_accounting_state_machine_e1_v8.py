"""Synthetic-only BTC spot/perpetual Decimal accounting state machine (E1-v8).

This module deliberately has no file, network, database, broker, or production imports.
All authorities and point-in-time observations are immutable values supplied at
construction.  The only actionable arm emitted by the engine is ``no_trade``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


EXPERIMENT_ID = "btc-unified-backtest-engine-e1-v8"
ACTIONABLE_ARM_ID = "no_trade"
ZERO = Decimal("0")
ONE = Decimal("1")
RESIDUAL_QUANTUM = Decimal("0.00000001")
DAILY_STOP = Decimal("-0.015")
DRAWDOWN_STOP = Decimal("-0.10")

EXECUTION_AUTHORITY = (
    "config/execution_scenarios.json",
    "a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36",
)
MANDATE_AUTHORITIES = MappingProxyType({
    "retail-btc-spot-v2": (
        "config/retail_mandate.json",
        "7e34cfb0928b4373bbf52b5c5505f63a2b19e674124059191c1b6c62ec129041",
    ),
    "retail-btc-directional-perpetual-research-v1": (
        "config/mandates/retail-btc-directional-perpetual-research-v1.json",
        "1b5d492f12f71ebe28e1bdfbd0b5916bcf0ad285b483cb10bf8770504371165d",
    ),
    "retail-btc-delta-neutral-research-v1": (
        "config/mandates/retail-btc-delta-neutral-research-v1.json",
        "d95a53ee493862549b932dc5f80600a02a0e38e4ba1b3da0d79d0b0c5bb9eeba",
    ),
})
REQUIRED_SCENARIOS = frozenset({
    "candle-primary-30bps-rt-v1",
    "candle-stress-40bps-rt-v1",
    "candle-severe-80bps-rt-v1",
})


class AccountingError(ValueError):
    """Fail-closed input, authority, accounting, or safety violation."""


def D(value: Any) -> Decimal:
    """Convert string/int/Decimal to a finite Decimal; floats are forbidden."""
    if isinstance(value, bool) or isinstance(value, float):
        raise AccountingError("economic values must not be bool or float")
    try:
        out = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AccountingError("invalid Decimal") from exc
    if not out.is_finite():
        raise AccountingError("nonfinite Decimal")
    return out


def decimal_string(value: Any) -> str:
    value = D(value)
    if value == ZERO:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        if not value.endswith("Z"):
            raise AccountingError("timestamp must end in Z")
        try:
            value = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise AccountingError("invalid timestamp") from exc
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise AccountingError("timestamp must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def timestamp_string(value: datetime | str) -> str:
    return utc(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AccountingError("duplicate JSON key")
        out[key] = value
    return out


def parse_json_strict(raw: str | bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise AccountingError("nonfinite JSON number: " + value)
    return json.loads(raw, object_pairs_hook=_pairs_no_duplicates,
                      parse_constant=reject_constant, parse_float=Decimal,
                      parse_int=Decimal)


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_string(value)
    if isinstance(value, datetime):
        return timestamp_string(value)
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        seen: set[str] = set()
        for key, item in value.items():
            skey = str(key)
            if skey in seen:
                raise AccountingError("post-string key collision")
            seen.add(skey)
            out[skey] = _canonical(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AccountingError("nonfinite value")
        raise AccountingError("float forbidden")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise AccountingError("unsupported canonical type")


def canonical_json(value: Any) -> bytes:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical_json(value)).hexdigest()


def row_with_digest(row: Mapping[str, Any]) -> dict[str, Any]:
    if "row_digest" in row:
        raise AccountingError("row_digest is engine-owned")
    result = dict(row)
    result["row_digest"] = digest(result)
    return _canonical(result)


def _positive(value: Any, name: str) -> Decimal:
    out = D(value)
    if out <= ZERO:
        raise AccountingError(name + " must be positive")
    return out


@dataclass(frozen=True)
class InstrumentRules:
    instrument: str
    quantity_step: Decimal
    price_tick: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal
    maximum_quantity: Decimal
    digest: str

    def __post_init__(self) -> None:
        if self.instrument not in {"BTC_USDT_spot", "BTCUSDT_USD_M_linear_perpetual"}:
            raise AccountingError("wrong instrument")
        for name in ("quantity_step", "price_tick", "minimum_quantity",
                     "minimum_notional", "maximum_quantity"):
            value = D(getattr(self, name))
            if value <= ZERO:
                raise AccountingError("invalid rule " + name)
            object.__setattr__(self, name, value)
        if not self.digest:
            raise AccountingError("rules digest required")

    def quantity(self, value: Any) -> Decimal:
        value = D(value)
        sign = ONE if value >= ZERO else -ONE
        return sign * ((abs(value) / self.quantity_step).to_integral_value(rounding=ROUND_DOWN)
                       * self.quantity_step)

    def price(self, value: Any) -> Decimal:
        value = _positive(value, "price")
        return (value / self.price_tick).to_integral_value(rounding=ROUND_DOWN) * self.price_tick

    def validate(self, quantity: Any, price: Any) -> tuple[Decimal, Decimal]:
        quantity, price = D(quantity), D(price)
        if self.quantity(quantity) != quantity or self.price(price) != price:
            raise AccountingError("off-rule quantity or price")
        if abs(quantity) < self.minimum_quantity or abs(quantity) > self.maximum_quantity:
            raise AccountingError("quantity limit")
        if abs(quantity) * price < self.minimum_notional:
            raise AccountingError("minimum notional")
        return quantity, price


@dataclass(frozen=True)
class SourceMark:
    instrument: str
    timestamp: datetime
    segment_id: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    observed_at: datetime
    available_at: datetime
    source_digest: str
    mark_source_digest: str
    rules_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", utc(self.timestamp))
        object.__setattr__(self, "observed_at", utc(self.observed_at))
        object.__setattr__(self, "available_at", utc(self.available_at))
        if self.available_at > self.timestamp or self.observed_at > self.timestamp:
            raise AccountingError("future source observation")
        prices = [_positive(getattr(self, key), key) for key in ("open", "high", "low", "close")]
        for key, value in zip(("open", "high", "low", "close"), prices):
            object.__setattr__(self, key, value)
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise AccountingError("invalid OHLC")
        if not all((self.segment_id, self.source_digest, self.mark_source_digest, self.rules_digest)):
            raise AccountingError("complete source lineage required")


@dataclass(frozen=True)
class Fee:
    asset: str
    rate: Decimal
    tax_rate: Decimal = ZERO
    third_asset_mark: Decimal | None = None
    authorized_tax: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", D(self.rate))
        object.__setattr__(self, "tax_rate", D(self.tax_rate))
        if self.rate < ZERO or self.tax_rate < ZERO:
            raise AccountingError("negative fee")
        if self.tax_rate and not self.authorized_tax:
            raise AccountingError("unauthorized tax")
        if self.asset not in {"quote", "base", "third"}:
            raise AccountingError("unsupported fee currency")
        if self.third_asset_mark is not None:
            object.__setattr__(self, "third_asset_mark", _positive(self.third_asset_mark, "third mark"))


@dataclass(frozen=True)
class RunBinding:
    run_id: str
    scenario_id: str
    selected_mandate_id: str
    selected_mandate_path: str
    selected_mandate_exact_file_sha256: str
    execution_config_path: str
    execution_config_exact_file_sha256: str
    contract_digest: str
    implementation_digest: str
    spot_rules_digest: str
    perpetual_rules_digest: str
    spot_fee_policy_digest: str
    perpetual_fee_policy_digest: str
    severe_price_and_cost_bound_digest: str
    margin_rule_digest: str
    source_digests: tuple[str, ...]
    adapter_id: str
    leverage: Decimal
    perpetual_exit_cost_rate: Decimal
    liquidation_fee_rate: Decimal
    maximum_notional_fraction: Decimal
    mismatch_limit: Decimal
    partition_start: datetime
    terminal_timestamp: datetime
    terminal_convention: str
    zero_exit_reserve_fixture: bool = False
    manifest_digest: str = ""

    def __post_init__(self) -> None:
        expected = MANDATE_AUTHORITIES.get(self.selected_mandate_id)
        if expected != (self.selected_mandate_path, self.selected_mandate_exact_file_sha256):
            raise AccountingError("mandate authority mismatch")
        if (self.execution_config_path, self.execution_config_exact_file_sha256) != EXECUTION_AUTHORITY:
            raise AccountingError("execution authority mismatch")
        if self.scenario_id not in REQUIRED_SCENARIOS and self.adapter_id == "candle_OHLC":
            raise AccountingError("required candle scenario")
        for key in ("contract_digest", "implementation_digest", "spot_rules_digest",
                    "perpetual_rules_digest", "spot_fee_policy_digest",
                    "perpetual_fee_policy_digest", "severe_price_and_cost_bound_digest",
                    "margin_rule_digest"):
            if not getattr(self, key):
                raise AccountingError("missing immutable binding " + key)
        if not self.source_digests or any(not item for item in self.source_digests):
            raise AccountingError("source binding required")
        object.__setattr__(self, "leverage", _positive(self.leverage, "leverage"))
        for key in ("perpetual_exit_cost_rate", "liquidation_fee_rate",
                    "maximum_notional_fraction", "mismatch_limit"):
            value = D(getattr(self, key))
            if value < ZERO:
                raise AccountingError("negative binding")
            object.__setattr__(self, key, value)
        if self.perpetual_exit_cost_rate == ZERO and not self.zero_exit_reserve_fixture:
            raise AccountingError("zero exit reserve not declared")
        object.__setattr__(self, "partition_start", utc(self.partition_start))
        object.__setattr__(self, "terminal_timestamp", utc(self.terminal_timestamp))
        if self.terminal_timestamp <= self.partition_start:
            raise AccountingError("invalid partition")
        if self.terminal_convention not in {"market_on_close", "eligible_next_open"}:
            raise AccountingError("invalid terminal convention")

    @property
    def lineage(self) -> dict[str, str]:
        return {
            "experiment_id": EXPERIMENT_ID, "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "implementation_digest": self.implementation_digest,
            "contract_digest": self.contract_digest,
            "execution_config_digest": self.execution_config_exact_file_sha256,
            "mandate_digest": self.selected_mandate_exact_file_sha256,
        }


@dataclass
class PortfolioState:
    quote_cash: Decimal
    spot_quantity_BTC: Decimal = ZERO
    isolated_collateral: Decimal = ZERO
    signed_perpetual_quantity_BTC: Decimal = ZERO
    average_perpetual_entry: Decimal | None = None
    realized_PnL: Decimal = ZERO
    unrealized_PnL: Decimal = ZERO
    accrued_funding: Decimal = ZERO
    allocated_initial_margin_memo: Decimal = ZERO
    explicit_costs: Decimal = ZERO
    exit_cost_reserve_memo: Decimal = ZERO
    fee_asset_balances: dict[str, Decimal] = field(default_factory=dict)
    implicit_costs: Decimal = ZERO
    liabilities: Decimal = ZERO

    def __post_init__(self) -> None:
        for name in ("quote_cash", "spot_quantity_BTC", "isolated_collateral",
                     "signed_perpetual_quantity_BTC", "realized_PnL", "unrealized_PnL",
                     "accrued_funding", "allocated_initial_margin_memo", "explicit_costs",
                     "exit_cost_reserve_memo", "implicit_costs", "liabilities"):
            setattr(self, name, D(getattr(self, name)))
        self.fee_asset_balances = {str(k): D(v) for k, v in self.fee_asset_balances.items()}
        if self.spot_quantity_BTC < ZERO or self.liabilities < ZERO:
            raise AccountingError("negative inventory or liability")
        if self.average_perpetual_entry is not None:
            self.average_perpetual_entry = _positive(self.average_perpetual_entry, "entry")


STATE_FIELDS = frozenset(PortfolioState.__dataclass_fields__)

DECISION_FIELDS = frozenset({"decision_id", "decision_at", "available_information_cutoff",
    "requested_target", "permission_or_abstention", "reason", "source_digest", "rules_digest",
    "lineage_digest", "event_sequence", "before_state_digest", "after_state_digest",
    "event_accounting_residual", "invalidation_reason_or_null", "row_digest"})
ORDER_FIELDS = frozenset({"order_id", "decision_id", "created_at", "arrival_at", "instrument",
    "requested_quantity", "rounded_quantity", "filled_quantity", "unfilled_quantity", "status",
    "reason", "price_bound", "scenario_id", "source_digest", "rules_digest", "event_sequence",
    "before_state_digest", "after_state_digest", "event_accounting_residual",
    "invalidation_reason_or_null", "row_digest"})
FILL_FIELDS = frozenset({"fill_id", "order_id", "fill_at", "instrument", "signed_quantity",
    "accounting_fill_price", "explicit_fee_native", "explicit_fee_asset",
    "explicit_fee_quote_equivalent", "implicit_cost_quote", "post_fill_position", "rules_digest",
    "source_digest", "event_sequence", "before_state_digest", "after_state_digest",
    "event_accounting_residual", "invalidation_reason_or_null", "row_digest"})
FUNDING_FIELDS = frozenset({"funding_at", "t_minus_signed_quantity", "funding_rate", "funding_mark",
    "cashflow_quote", "economic_at", "available_at", "mark_source_digest", "index_source_digest",
    "rules_digest", "source_digest", "event_sequence", "before_state_digest", "after_state_digest",
    "event_accounting_residual", "invalidation_reason_or_null", "row_digest"})
ACCOUNT_FIELDS = frozenset({"timestamp", "segment_id", "quote_cash", "spot_quantity",
    "perpetual_quantity", "isolated_collateral", "allocated_initial_margin_memo",
    "exit_cost_reserve_memo", "fee_asset_balances", "liabilities", "realized_PnL",
    "unrealized_PnL", "funding", "explicit_costs", "implicit_costs", "NAV", "gross_exposure",
    "net_exposure", "margin_equity", "maintenance_requirement", "state", "source_digest",
    "rules_digest", "mark_source_digest", "index_source_digest", "event_sequence",
    "before_state_digest", "after_state_digest", "event_accounting_residual",
    "invalidation_reason_or_null", "row_digest"})
EPISODE_FIELDS = frozenset({"episode_id", "opened_at", "closed_at", "direction", "entry_costs",
    "exit_costs", "price_PnL", "funding_PnL", "net_dollar_PnL", "maximum_adverse_excursion",
    "maximum_favourable_excursion", "close_reason", "entry_fill_digests", "exit_fill_digests",
    "source_digests", "rules_digests", "invalidation_reason", "row_digest"})


@dataclass
class Episode:
    episode_id: str
    instrument: str
    opened_at: datetime
    direction: str
    entry_price: Decimal
    quantity: Decimal
    entry_costs: Decimal = ZERO
    exit_costs: Decimal = ZERO
    price_PnL: Decimal = ZERO
    funding_PnL: Decimal = ZERO
    maximum_adverse_excursion: Decimal = ZERO
    maximum_favourable_excursion: Decimal = ZERO
    entry_fill_digests: list[str] = field(default_factory=list)
    exit_fill_digests: list[str] = field(default_factory=list)
    source_digests: set[str] = field(default_factory=set)
    rules_digests: set[str] = field(default_factory=set)


class AccountingEngine:
    """One immutable-bound, sequential synthetic run."""

    def __init__(self, binding: RunBinding, initial_nav: Any,
                 spot_rules: InstrumentRules, perpetual_rules: InstrumentRules,
                 third_fee_balances: Mapping[str, Any] | None = None) -> None:
        if spot_rules.digest != binding.spot_rules_digest or perpetual_rules.digest != binding.perpetual_rules_digest:
            raise AccountingError("rule digest binding mismatch")
        self.binding = binding
        self.spot_rules = spot_rules
        self.perpetual_rules = perpetual_rules
        self.state = PortfolioState(D(initial_nav), fee_asset_balances=dict(third_fee_balances or {}))
        self.starting_nav = D(initial_nav)
        self.high_water_nav = self.starting_nav
        self.day_start_nav = self.starting_nav
        self.last_reconciled_nav = self.starting_nav
        self.day = binding.partition_start.date()
        self.last_timestamp: datetime | None = None
        self.segment_id: str | None = None
        self.spot_mark: Decimal | None = None
        self.perpetual_mark: Decimal | None = None
        self.terminal = False
        self.liquidated = False
        self.invalid = False
        self.invalidation_reason: str | None = None
        self.unknown = False
        self.pending_safety: str | None = None
        self.sequence = 0
        self.current_phase = 0
        self.seen_keys: set[str] = set()
        self.ledgers: dict[str, list[dict[str, Any]]] = {
            "decision": [], "order": [], "fill": [], "funding": [], "account": [], "episode": []}
        self.open_episodes: dict[str, Episode] = {}
        self.spot_price_pnl = ZERO
        self.perpetual_price_pnl = ZERO

    def snapshot(self) -> dict[str, Any]:
        return _canonical({name: getattr(self.state, name) for name in STATE_FIELDS})

    def state_digest(self) -> str:
        return digest(self.snapshot())

    def nav(self, spot_mark: Any | None = None, perpetual_mark: Any | None = None,
            third_marks: Mapping[str, Any] | None = None) -> Decimal:
        sm = self.spot_mark if spot_mark is None else _positive(spot_mark, "spot mark")
        pm = self.perpetual_mark if perpetual_mark is None else _positive(perpetual_mark, "perp mark")
        if self.state.spot_quantity_BTC and sm is None:
            raise AccountingError("spot mark required")
        if self.state.signed_perpetual_quantity_BTC and pm is None:
            raise AccountingError("perpetual mark required")
        third = ZERO
        marks = third_marks or {}
        for asset, balance in self.state.fee_asset_balances.items():
            if balance and asset not in marks:
                raise AccountingError("third fee mark required")
            third += balance * D(marks.get(asset, ZERO))
        unrealized = ZERO
        if self.state.signed_perpetual_quantity_BTC:
            unrealized = self.state.signed_perpetual_quantity_BTC * (D(pm) - D(self.state.average_perpetual_entry))
        self.state.unrealized_PnL = unrealized
        return (self.state.quote_cash + self.state.spot_quantity_BTC * D(sm or ZERO) + third
                + self.state.isolated_collateral + unrealized - self.state.liabilities)

    def _invalidate(self, reason: str, unknown: bool = False) -> None:
        self.invalid = True
        self.invalidation_reason = self.invalidation_reason or reason
        self.unknown = self.unknown or unknown

    def _guard_time(self, at: datetime | str, *, ordinary: bool = True) -> datetime:
        at = utc(at)
        if at < self.binding.partition_start or at > self.binding.terminal_timestamp:
            raise AccountingError("outside partition")
        if self.last_timestamp is not None and at < self.last_timestamp:
            raise AccountingError("timestamp regression")
        if self.terminal and (ordinary or at > (self.last_timestamp or at)):
            raise AccountingError("post-terminal event")
        return at

    def _unique(self, key: str) -> None:
        if key in self.seen_keys:
            raise AccountingError("duplicate logical event")
        self.seen_keys.add(key)

    def _common(self, before: str, after: str, residual: Decimal = ZERO) -> dict[str, Any]:
        self.sequence += 1
        return {"event_sequence": self.sequence, "before_state_digest": before,
                "after_state_digest": after, "event_accounting_residual": decimal_string(residual),
                "invalidation_reason_or_null": self.invalidation_reason}

    def _emit(self, ledger: str, payload: dict[str, Any], fields: frozenset[str]) -> dict[str, Any]:
        full = dict(self.binding.lineage)
        full.update(payload)
        row = row_with_digest(full)
        required = fields | frozenset(self.binding.lineage)
        if frozenset(row) != required:
            raise AccountingError("ledger schema mismatch")
        self.ledgers[ledger].append(row)
        return row

    def _fee_amounts(self, quantity: Decimal, price: Decimal, fee: Fee) -> tuple[Decimal, Decimal]:
        notional = abs(quantity) * price
        if fee.asset == "base":
            native = abs(quantity) * (fee.rate + fee.tax_rate)
            quote = native * price
        elif fee.asset == "quote":
            native = notional * (fee.rate + fee.tax_rate)
            quote = native
        else:
            if fee.third_asset_mark is None:
                raise AccountingError("third fee conversion unavailable")
            quote = notional * (fee.rate + fee.tax_rate)
            native = quote / fee.third_asset_mark
        return native, quote

    def _preflight_fee(self, instrument: str, quantity: Decimal, price: Decimal, fee: Fee) -> tuple[Decimal, Decimal]:
        native, quote = self._fee_amounts(quantity, price, fee)
        if fee.asset == "base" and instrument != "BTC_USDT_spot":
            raise AccountingError("base perpetual fee unauthorized")
        if fee.asset == "third":
            balance = self.state.fee_asset_balances.get("third")
            if balance is None or balance < native:
                raise AccountingError("insufficient third fee asset")
        return native, quote

    def _refresh_reserve(self, mark: Decimal) -> None:
        self.state.exit_cost_reserve_memo = (abs(self.state.signed_perpetual_quantity_BTC)
                                             * mark * self.binding.perpetual_exit_cost_rate)

    def entry_allowed(self, mark_nav: Decimal | None = None) -> bool:
        nav = self.nav() if mark_nav is None else D(mark_nav)
        daily = nav / self.day_start_nav - ONE
        dd = nav / self.high_water_nav - ONE
        return not (self.invalid or self.unknown or self.terminal or daily <= DAILY_STOP or dd <= DRAWDOWN_STOP)

    def decision(self, decision_id: str, at: datetime | str, requested_target: str,
                 source_digest: str, rules_digest: str, available_at: datetime | str,
                 increasing: bool) -> dict[str, Any]:
        at = self._guard_time(at)
        available_at = utc(available_at)
        if available_at > at:
            raise AccountingError("future information")
        if source_digest not in self.binding.source_digests or rules_digest not in {
                self.binding.spot_rules_digest, self.binding.perpetual_rules_digest}:
            raise AccountingError("decision source/rule binding mismatch")
        self._unique("decision:" + decision_id)
        before = self.state_digest()
        allowed = (not increasing) or self.entry_allowed()
        reason = "permitted" if allowed else "entry_disabled"
        payload = {"decision_id": decision_id, "decision_at": timestamp_string(at),
            "available_information_cutoff": timestamp_string(available_at),
            "requested_target": requested_target,
            "permission_or_abstention": "permission" if allowed else "abstention", "reason": reason,
            "source_digest": source_digest, "rules_digest": rules_digest,
            "lineage_digest": digest(self.binding.lineage), **self._common(before, before)}
        return self._emit("decision", payload, DECISION_FIELDS)

    def _authorize(self, instrument: str, delta: Decimal, protective: bool) -> None:
        mandate = self.binding.selected_mandate_id
        if instrument == "BTC_USDT_spot":
            if mandate not in {"retail-btc-spot-v2", "retail-btc-delta-neutral-research-v1"}:
                raise AccountingError("spot prohibited by mandate")
            if self.state.spot_quantity_BTC + delta < ZERO:
                raise AccountingError("spot borrowing prohibited")
        else:
            if mandate not in {"retail-btc-directional-perpetual-research-v1",
                               "retail-btc-delta-neutral-research-v1"}:
                raise AccountingError("perpetual prohibited by mandate")
            old, new = self.state.signed_perpetual_quantity_BTC, self.state.signed_perpetual_quantity_BTC + delta
            if mandate == "retail-btc-delta-neutral-research-v1" and new > ZERO:
                raise AccountingError("pair mandate prohibits long perpetual")
            if mandate == "retail-btc-directional-perpetual-research-v1" and old and new and old * new > ZERO and abs(new) > abs(old):
                raise AccountingError("pyramiding prohibited")
        old_abs = abs(self.state.spot_quantity_BTC if instrument == "BTC_USDT_spot" else self.state.signed_perpetual_quantity_BTC)
        new_abs = abs((self.state.spot_quantity_BTC if instrument == "BTC_USDT_spot" else self.state.signed_perpetual_quantity_BTC) + delta)
        if (self.current_phase == 2 or self.terminal or self.last_timestamp == self.binding.terminal_timestamp) and new_abs > old_abs:
            raise AccountingError("phase/terminal increase prohibited")
        if protective and new_abs > old_abs:
            raise AccountingError("protective action must reduce")

    def fill(self, order_id: str, at: datetime | str, instrument: str, signed_quantity: Any,
             price: Any, fee: Fee, source: SourceMark, *, implicit_rate: Any = ZERO,
             protective: bool = False, decision_id: str = "synthetic", allow_partial: bool = False,
             requested_quantity: Any | None = None, price_bound: Any | None = None,
             reason: str = "ordinary") -> dict[str, Any]:
        at = self._guard_time(at, ordinary=not protective)
        if source.timestamp != at or source.instrument != instrument or source.segment_id != self.segment_id:
            raise AccountingError("engine-owned timestamp/instrument/segment mismatch")
        rules = self.spot_rules if instrument == "BTC_USDT_spot" else self.perpetual_rules
        if source.rules_digest != rules.digest:
            raise AccountingError("source/rule lineage mismatch")
        quantity, price = rules.validate(signed_quantity, price)
        if price != source.open:
            raise AccountingError("caller-substituted execution price")
        requested = quantity if requested_quantity is None else D(requested_quantity)
        if self.binding.adapter_id == "candle_OHLC" and quantity != rules.quantity(requested):
            raise AccountingError("candle partial fill prohibited")
        if not allow_partial and quantity != rules.quantity(requested):
            raise AccountingError("partial fill capability absent")
        if price_bound is not None:
            bound = D(price_bound)
            if quantity > ZERO and price > bound or quantity < ZERO and price < bound:
                raise AccountingError("price bound exceeded")
        self._authorize(instrument, quantity, protective)
        native_fee, quote_fee = self._preflight_fee(instrument, quantity, price, fee)
        implicit = abs(quantity) * price * D(implicit_rate)
        old_perp = self.state.signed_perpetual_quantity_BTC
        if instrument == "BTC_USDT_spot":
            if quantity > ZERO and self.state.quote_cash < quantity * price + (quote_fee if fee.asset == "quote" else ZERO) + implicit:
                raise AccountingError("insufficient quote cash")
            if quantity < ZERO and fee.asset == "base" and self.state.spot_quantity_BTC < abs(quantity) + native_fee:
                raise AccountingError("insufficient base inventory")
        else:
            old_abs, new = abs(old_perp), old_perp + quantity
            increasing = old_perp == ZERO or old_perp * quantity > ZERO
            if old_perp * new < ZERO:
                raise AccountingError("reversal must be two fills")
            if fee.asset != "quote":
                raise AccountingError("perpetual fee must be quote")
            if increasing:
                margin = abs(quantity) * price / self.binding.leverage
                if self.state.quote_cash < margin:
                    raise AccountingError("insufficient collateral")
                prospective_collateral = self.state.isolated_collateral + margin
            else:
                realized_preflight = abs(quantity) * (ONE if old_perp > ZERO else -ONE) * (
                    price - D(self.state.average_perpetual_entry))
                prospective_collateral = self.state.isolated_collateral + realized_preflight
            if prospective_collateral < native_fee + implicit:
                raise AccountingError("perpetual fee not funded")
        # Complete preflight above; mutations begin here.
        before = self.state_digest()
        old_spot = self.state.spot_quantity_BTC
        if instrument == "BTC_USDT_spot":
            self.state.quote_cash -= quantity * price
            self.state.spot_quantity_BTC += quantity
            if fee.asset == "base":
                self.state.spot_quantity_BTC -= native_fee
            elif fee.asset == "quote":
                self.state.quote_cash -= native_fee
            else:
                self.state.fee_asset_balances["third"] -= native_fee
            self.state.quote_cash -= implicit
            post_position = self.state.spot_quantity_BTC
        else:
            old_abs, new = abs(old_perp), old_perp + quantity
            increasing = old_perp == ZERO or old_perp * quantity > ZERO
            if increasing:
                margin = abs(quantity) * price / self.binding.leverage
                self.state.quote_cash -= margin
                self.state.isolated_collateral += margin
                self.state.allocated_initial_margin_memo += margin
                if old_perp == ZERO:
                    self.state.average_perpetual_entry = price
                else:
                    self.state.average_perpetual_entry = ((old_abs * D(self.state.average_perpetual_entry)
                        + abs(quantity) * price) / abs(new))
            else:
                close_qty = abs(quantity)
                realized = close_qty * (ONE if old_perp > ZERO else -ONE) * (price - D(self.state.average_perpetual_entry))
                self.state.realized_PnL += realized
                self.state.isolated_collateral += realized
                released_memo = self.state.allocated_initial_margin_memo * close_qty / old_abs
                self.state.allocated_initial_margin_memo -= released_memo
            self.state.isolated_collateral -= native_fee + implicit
            self.state.signed_perpetual_quantity_BTC = new
            if not increasing:
                cash_release = min(released_memo, max(self.state.isolated_collateral, ZERO))
                self.state.isolated_collateral -= cash_release
                self.state.quote_cash += cash_release
            if new == ZERO:
                if self.state.isolated_collateral < ZERO:
                    self.state.liabilities += -self.state.isolated_collateral
                else:
                    self.state.quote_cash += self.state.isolated_collateral
                self.state.isolated_collateral = ZERO
                self.state.allocated_initial_margin_memo = ZERO
                self.state.average_perpetual_entry = None
            post_position = new
            self._refresh_reserve(price)
        self.state.explicit_costs += quote_fee
        self.state.implicit_costs += implicit
        after = self.state_digest()
        order_payload = {"order_id": order_id, "decision_id": decision_id,
            "created_at": timestamp_string(at), "arrival_at": timestamp_string(at), "instrument": instrument,
            "requested_quantity": decimal_string(requested), "rounded_quantity": decimal_string(rules.quantity(requested)),
            "filled_quantity": decimal_string(quantity), "unfilled_quantity": decimal_string(rules.quantity(requested)-quantity),
            "status": "filled" if quantity == rules.quantity(requested) else "partial", "reason": reason,
            "price_bound": decimal_string(price_bound if price_bound is not None else price),
            "scenario_id": self.binding.scenario_id, "source_digest": source.source_digest,
            "rules_digest": rules.digest, **self._common(before, after)}
        self._emit("order", order_payload, ORDER_FIELDS)
        fill_payload = {"fill_id": order_id + ":fill", "order_id": order_id,
            "fill_at": timestamp_string(at), "instrument": instrument,
            "signed_quantity": decimal_string(quantity), "accounting_fill_price": decimal_string(price),
            "explicit_fee_native": decimal_string(native_fee), "explicit_fee_asset": fee.asset,
            "explicit_fee_quote_equivalent": decimal_string(quote_fee),
            "implicit_cost_quote": decimal_string(implicit), "post_fill_position": decimal_string(post_position),
            "rules_digest": rules.digest, "source_digest": source.source_digest,
            **self._common(before, after)}
        fill_row = self._emit("fill", fill_payload, FILL_FIELDS)
        self._episode_fill(instrument, old_spot if instrument == "BTC_USDT_spot" else old_perp,
                           quantity, price, quote_fee + implicit, fill_row, source)
        return fill_row

    def _episode_fill(self, instrument: str, old: Decimal, quantity: Decimal, price: Decimal,
                      costs: Decimal, fill_row: Mapping[str, Any], source: SourceMark) -> None:
        new = self.state.spot_quantity_BTC if instrument == "BTC_USDT_spot" else self.state.signed_perpetual_quantity_BTC
        key = instrument
        if old == ZERO and new != ZERO:
            ep = Episode("episode-" + str(len(self.open_episodes) + len(self.ledgers["episode"]) + 1),
                         instrument, source.timestamp, "long" if new > ZERO else "short", price, abs(new),
                         entry_costs=costs)
            ep.entry_fill_digests.append(fill_row["row_digest"])
            ep.source_digests.add(source.source_digest); ep.rules_digests.add(source.rules_digest)
            self.open_episodes[key] = ep
        elif key in self.open_episodes:
            ep = self.open_episodes[key]
            ep.source_digests.add(source.source_digest); ep.rules_digests.add(source.rules_digest)
            if abs(new) > abs(old):
                ep.entry_costs += costs; ep.entry_fill_digests.append(fill_row["row_digest"])
            else:
                ep.exit_costs += costs; ep.exit_fill_digests.append(fill_row["row_digest"])
                closed = min(abs(quantity), abs(old))
                ep.price_PnL += closed * (ONE if ep.direction == "long" else -ONE) * (price - ep.entry_price)
                ep.quantity = abs(new)
            if new == ZERO:
                self._close_episode(key, source.timestamp, "ordinary", source)

    def _close_episode(self, key: str, at: datetime, reason: str, source: SourceMark) -> dict[str, Any]:
        ep = self.open_episodes.pop(key)
        payload = {"episode_id": ep.episode_id, "opened_at": timestamp_string(ep.opened_at),
            "closed_at": timestamp_string(at), "direction": ep.direction,
            "entry_costs": decimal_string(ep.entry_costs), "exit_costs": decimal_string(ep.exit_costs),
            "price_PnL": decimal_string(ep.price_PnL), "funding_PnL": decimal_string(ep.funding_PnL),
            "net_dollar_PnL": decimal_string(ep.price_PnL + ep.funding_PnL - ep.entry_costs - ep.exit_costs),
            "maximum_adverse_excursion": decimal_string(ep.maximum_adverse_excursion),
            "maximum_favourable_excursion": decimal_string(ep.maximum_favourable_excursion),
            "close_reason": reason, "entry_fill_digests": ep.entry_fill_digests,
            "exit_fill_digests": ep.exit_fill_digests,
            "rules_digests": sorted(ep.rules_digests | {self.binding.margin_rule_digest}),
            "source_digests": sorted(ep.source_digests | {source.mark_source_digest}),
            "invalidation_reason": self.invalidation_reason}
        return self._emit("episode", payload, EPISODE_FIELDS)

    def funding(self, funding_at: datetime | str, rate: Any, mark: Any, available_at: datetime | str,
                source_digest: str, mark_source_digest: str, index_source_digest: str,
                rules_digest: str, t_minus_quantity: Any | None = None) -> dict[str, Any]:
        at = utc(funding_at)
        if self.liquidated and self.last_timestamp is not None and at >= self.last_timestamp:
            raise AccountingError("funding at/after observed liquidation")
        at = self._guard_time(at)
        available_at = utc(available_at)
        if available_at > at or rules_digest != self.binding.perpetual_rules_digest:
            raise AccountingError("funding availability/rule mismatch")
        qty = self.state.signed_perpetual_quantity_BTC if t_minus_quantity is None else D(t_minus_quantity)
        if qty != self.state.signed_perpetual_quantity_BTC:
            raise AccountingError("caller-substituted t-minus membership")
        mark, rate = _positive(mark, "funding mark"), D(rate)
        if source_digest not in self.binding.source_digests or not mark_source_digest or not index_source_digest:
            raise AccountingError("funding source lineage mismatch")
        self._unique("funding:" + timestamp_string(at))
        cashflow = -qty * mark * rate
        before = self.state_digest()
        if qty:
            self.state.isolated_collateral += cashflow
            if self.state.isolated_collateral < ZERO:
                self.state.liabilities += -self.state.isolated_collateral
                self.state.isolated_collateral = ZERO
            self.state.accrued_funding += cashflow
            if "BTCUSDT_USD_M_linear_perpetual" in self.open_episodes:
                self.open_episodes["BTCUSDT_USD_M_linear_perpetual"].funding_PnL += cashflow
        self._refresh_reserve(mark)
        after = self.state_digest()
        payload = {"funding_at": timestamp_string(at), "t_minus_signed_quantity": decimal_string(qty),
            "funding_rate": decimal_string(rate), "funding_mark": decimal_string(mark),
            "cashflow_quote": decimal_string(cashflow), "economic_at": timestamp_string(at),
            "available_at": timestamp_string(available_at), "mark_source_digest": mark_source_digest,
            "index_source_digest": index_source_digest, "rules_digest": rules_digest,
            "source_digest": source_digest, **self._common(before, after)}
        return self._emit("funding", payload, FUNDING_FIELDS)

    def maintenance(self, mark: Any, rate: Any, add_on: Any = ZERO) -> Decimal:
        return abs(self.state.signed_perpetual_quantity_BTC) * D(mark) * D(rate) + D(add_on)

    def margin_equity(self, mark: Any) -> Decimal:
        mark = D(mark)
        unrealized = ZERO if not self.state.signed_perpetual_quantity_BTC else (
            self.state.signed_perpetual_quantity_BTC * (mark - D(self.state.average_perpetual_entry)))
        return self.state.isolated_collateral + unrealized - self.state.exit_cost_reserve_memo

    def liquidate(self, source: SourceMark, maintenance_rate: Any, add_on: Any = ZERO,
                  observed_price: Any | None = None) -> bool:
        if source.rules_digest != self.binding.perpetual_rules_digest or source.mark_source_digest == "placeholder":
            raise AccountingError("liquidation lineage mismatch")
        qty = self.state.signed_perpetual_quantity_BTC
        if not qty:
            return False
        observed = (source.low if qty > ZERO else source.high) if observed_price is None else D(observed_price)
        if observed not in {source.open, source.high, source.low, source.close}:
            raise AccountingError("observed liquidation price not in source path")
        self._refresh_reserve(observed)
        requirement = self.maintenance(observed, maintenance_rate, add_on)
        if self.margin_equity(observed) > requirement:
            return False
        before = self.state_digest()
        fee = abs(qty) * observed * self.binding.liquidation_fee_rate
        realized = abs(qty) * (ONE if qty > ZERO else -ONE) * (observed - D(self.state.average_perpetual_entry))
        self.state.realized_PnL += realized
        settlement = self.state.isolated_collateral + realized - fee
        self.state.explicit_costs += fee
        if settlement >= ZERO:
            self.state.quote_cash += settlement
        else:
            self.state.liabilities += -settlement
        self.state.isolated_collateral = ZERO
        self.state.signed_perpetual_quantity_BTC = ZERO
        self.state.average_perpetual_entry = None
        self.state.allocated_initial_margin_memo = ZERO
        self.state.exit_cost_reserve_memo = ZERO
        self.state.unrealized_PnL = ZERO
        self._invalidate("observed_liquidation")
        self.terminal = True; self.liquidated = True; self.last_timestamp = source.timestamp
        after = self.state_digest()
        order_payload = {"order_id": "liquidation:" + str(self.sequence + 1), "decision_id": "forced_liquidation",
            "created_at": timestamp_string(source.timestamp), "arrival_at": timestamp_string(source.timestamp),
            "instrument": source.instrument, "requested_quantity": decimal_string(-qty),
            "rounded_quantity": decimal_string(-qty), "filled_quantity": decimal_string(-qty),
            "unfilled_quantity": "0", "status": "filled", "reason": "observed_liquidation",
            "price_bound": decimal_string(observed), "scenario_id": self.binding.scenario_id,
            "source_digest": source.source_digest, "rules_digest": source.rules_digest,
            **self._common(before, after)}
        order = self._emit("order", order_payload, ORDER_FIELDS)
        fill_payload = {"fill_id": order["order_id"] + ":fill", "order_id": order["order_id"],
            "fill_at": timestamp_string(source.timestamp), "instrument": source.instrument,
            "signed_quantity": decimal_string(-qty), "accounting_fill_price": decimal_string(observed),
            "explicit_fee_native": decimal_string(fee), "explicit_fee_asset": "quote",
            "explicit_fee_quote_equivalent": decimal_string(fee), "implicit_cost_quote": "0",
            "post_fill_position": "0", "rules_digest": source.rules_digest,
            "source_digest": source.source_digest, **self._common(before, after)}
        fill = self._emit("fill", fill_payload, FILL_FIELDS)
        key = "BTCUSDT_USD_M_linear_perpetual"
        if key in self.open_episodes:
            ep = self.open_episodes[key]
            ep.exit_costs += fee; ep.price_PnL += realized
            ep.exit_fill_digests.append(fill["row_digest"]); ep.source_digests.add(source.source_digest)
            ep.rules_digests.add(source.rules_digest)
            self._close_episode(key, source.timestamp, "observed_liquidation", source)
        return True

    def account_row(self, source: SourceMark, maintenance_rate: Any, add_on: Any = ZERO,
                    index_source_digest: str = "not_applicable") -> dict[str, Any]:
        before = self.state_digest()
        if source.instrument == "BTC_USDT_spot": self.spot_mark = source.close
        else: self.perpetual_mark = source.close
        nav = self.nav()
        requirement = self.maintenance(self.perpetual_mark or source.close, maintenance_rate, add_on)
        gross = self.state.spot_quantity_BTC * D(self.spot_mark or ZERO) + abs(self.state.signed_perpetual_quantity_BTC) * D(self.perpetual_mark or ZERO)
        net = self.state.spot_quantity_BTC * D(self.spot_mark or ZERO) + self.state.signed_perpetual_quantity_BTC * D(self.perpetual_mark or ZERO)
        after = self.state_digest()
        payload = {"timestamp": timestamp_string(source.timestamp), "segment_id": source.segment_id,
            "quote_cash": decimal_string(self.state.quote_cash), "spot_quantity": decimal_string(self.state.spot_quantity_BTC),
            "perpetual_quantity": decimal_string(self.state.signed_perpetual_quantity_BTC),
            "isolated_collateral": decimal_string(self.state.isolated_collateral),
            "allocated_initial_margin_memo": decimal_string(self.state.allocated_initial_margin_memo),
            "exit_cost_reserve_memo": decimal_string(self.state.exit_cost_reserve_memo),
            "fee_asset_balances": _canonical(self.state.fee_asset_balances), "liabilities": decimal_string(self.state.liabilities),
            "realized_PnL": decimal_string(self.state.realized_PnL), "unrealized_PnL": decimal_string(self.state.unrealized_PnL),
            "funding": decimal_string(self.state.accrued_funding), "explicit_costs": decimal_string(self.state.explicit_costs),
            "implicit_costs": decimal_string(self.state.implicit_costs), "NAV": decimal_string(nav),
            "gross_exposure": decimal_string(gross), "net_exposure": decimal_string(net),
            "margin_equity": decimal_string(self.margin_equity(self.perpetual_mark or source.close) if self.state.signed_perpetual_quantity_BTC else ZERO),
            "maintenance_requirement": decimal_string(requirement),
            "state": "liquidated" if self.liquidated else "invalid_unknown" if self.unknown else "invalid" if self.invalid else "valid",
            "source_digest": source.source_digest, "rules_digest": source.rules_digest,
            "mark_source_digest": source.mark_source_digest, "index_source_digest": index_source_digest,
            **self._common(before, after)}
        row = self._emit("account", payload, ACCOUNT_FIELDS)
        self.high_water_nav = max(self.high_water_nav, nav)
        if source.timestamp.date() != self.day:
            self.day = source.timestamp.date(); self.day_start_nav = self.last_reconciled_nav
        self.last_reconciled_nav = nav
        self.last_timestamp = source.timestamp
        return row

    def _observe_excursions(self, spot: SourceMark, perp: SourceMark) -> None:
        for instrument, source in (("BTC_USDT_spot", spot),
                                   ("BTCUSDT_USD_M_linear_perpetual", perp)):
            ep = self.open_episodes.get(instrument)
            if ep is None:
                continue
            sign = ONE if ep.direction == "long" else -ONE
            low_move = sign * (source.low - ep.entry_price) * ep.quantity
            high_move = sign * (source.high - ep.entry_price) * ep.quantity
            ep.maximum_adverse_excursion = min(ep.maximum_adverse_excursion, low_move, high_move)
            ep.maximum_favourable_excursion = max(ep.maximum_favourable_excursion, low_move, high_move)

    def process_interval(self, spot: SourceMark, perp: SourceMark, *, funding_events: Sequence[Mapping[str, Any]] = (),
                         maintenance_rate: Any = ZERO, add_on: Any = ZERO,
                         phase6: Any = None) -> None:
        if spot.timestamp != perp.timestamp or spot.segment_id != perp.segment_id:
            raise AccountingError("common clock/segment required")
        at = self._guard_time(spot.timestamp)
        if self.last_timestamp is not None and at <= self.last_timestamp:
            raise AccountingError("duplicate/permuted interval")
        incoming_qty = self.state.signed_perpetual_quantity_BTC
        incoming_spot = self.state.spot_quantity_BTC
        self.current_phase = 1
        old_segment = self.segment_id
        self.segment_id = spot.segment_id
        if old_segment is not None and old_segment != self.segment_id:
            if self.state.spot_quantity_BTC or incoming_qty:
                self._invalidate("gap_cross_segment", unknown=True); self.pending_safety = "forced_neutralization"
            else:
                self.seen_keys.clear()
        self.current_phase = 2
        if self.spot_mark is not None:
            self.spot_price_pnl += incoming_spot * (spot.open - self.spot_mark)
        if self.perpetual_mark is not None:
            self.perpetual_price_pnl += incoming_qty * (perp.open - self.perpetual_mark)
        self.spot_mark, self.perpetual_mark = spot.open, perp.open
        if self.liquidate(perp, maintenance_rate, add_on, perp.open):
            self.current_phase = 9; self.account_row(perp, maintenance_rate, add_on); return
        self.current_phase = 3
        # Caller can only request an already-bound protective handler; ordinary increases are guarded.
        self.current_phase = 4
        for event in funding_events:
            if D(event.get("t_minus_quantity", incoming_qty)) != incoming_qty:
                raise AccountingError("funding membership mismatch")
            self.funding(**event, t_minus_quantity=incoming_qty)
            if self.liquidate(perp, maintenance_rate, add_on, perp.open):
                self.current_phase = 9; self.account_row(perp, maintenance_rate, add_on); return
        self.current_phase = 5
        self.entry_allowed(self.nav(spot.open, perp.open))
        self.current_phase = 6
        if phase6 is not None:
            phase6(self)
        self.current_phase = 7
        if self.liquidate(perp, maintenance_rate, add_on, perp.open):
            self.current_phase = 9; self.account_row(perp, maintenance_rate, add_on); return
        self.current_phase = 8
        self._observe_excursions(spot, perp)
        adverse = perp.low if self.state.signed_perpetual_quantity_BTC > ZERO else perp.high
        if self.state.signed_perpetual_quantity_BTC:
            self._refresh_reserve(adverse)
            if self.margin_equity(adverse) <= self.maintenance(adverse, maintenance_rate, add_on):
                self.perpetual_price_pnl += self.state.signed_perpetual_quantity_BTC * (adverse - perp.open)
                self.liquidate(perp, maintenance_rate, add_on, adverse)
                self.current_phase = 9; self.account_row(perp, maintenance_rate, add_on); return
        self.spot_price_pnl += self.state.spot_quantity_BTC * (spot.close - spot.open)
        self.perpetual_price_pnl += self.state.signed_perpetual_quantity_BTC * (perp.close - perp.open)
        self.spot_mark, self.perpetual_mark = spot.close, perp.close
        self._refresh_reserve(perp.close)
        self.current_phase = 9
        self.account_row(perp, maintenance_rate, add_on)
        self.current_phase = 0

    def gap(self, first_valid_spot: SourceMark, first_valid_perp: SourceMark) -> None:
        if first_valid_spot.timestamp != first_valid_perp.timestamp:
            raise AccountingError("first valid common open required")
        if first_valid_spot.timestamp >= self.binding.terminal_timestamp:
            raise AccountingError("gap recovery outside boundary")
        if self.state.spot_quantity_BTC or self.state.signed_perpetual_quantity_BTC:
            self._invalidate("gap_unknown_path", unknown=True)
            self.pending_safety = "forced_neutralization"
        self.segment_id = first_valid_spot.segment_id
        self.spot_mark, self.perpetual_mark = first_valid_spot.open, first_valid_perp.open
        self.seen_keys.clear()

    def qualify_partial_outcomes(self, source_digest: str, outcomes: Sequence[Mapping[str, Any]],
                                 permitted_R: Sequence[Any], permitted_q: Mapping[str, Sequence[Any]],
                                 spot_fee: Fee, perp_fee: Fee) -> tuple[tuple[Decimal, Decimal], ...]:
        if self.binding.adapter_id != "qualified_quote_L2" or source_digest not in self.binding.source_digests:
            raise AccountingError("unqualified partial source")
        indexed: dict[tuple[str, str], Mapping[str, Any]] = {}
        for item in outcomes:
            key = (decimal_string(item["R"]), decimal_string(item["q"]))
            if key in indexed: raise AccountingError("duplicate partial outcome")
            indexed[key] = item
        proven: list[tuple[Decimal, Decimal]] = []
        for raw_R in permitted_R:
            R = D(raw_R)
            key_R = decimal_string(R)
            if key_R not in permitted_q: raise AccountingError("missing intermediate R")
            for raw_q in permitted_q[key_R]:
                q = D(raw_q); key = (key_R, decimal_string(q))
                item = indexed.get(key)
                if item is None: raise AccountingError("incomplete Cartesian outcomes")
                for required in ("spot_vwap", "perp_vwap", "severe_vwap", "spot_rules_digest",
                                 "perp_rules_digest", "source_digest", "spot_explicit_cost",
                                 "spot_implicit_cost", "perp_explicit_cost", "perp_implicit_cost"):
                    if required not in item: raise AccountingError("unqualified outcome")
                if item["source_digest"] != source_digest or item["spot_rules_digest"] != self.spot_rules.digest or item["perp_rules_digest"] != self.perpetual_rules.digest:
                    raise AccountingError("outcome lineage mismatch")
                self.spot_rules.validate(-R, item["spot_vwap"])
                if q: self.perpetual_rules.validate(q, item["perp_vwap"])
                residual = R - q
                if residual < ZERO: raise AccountingError("negative residual")
                if residual: self.perpetual_rules.validate(residual, item["severe_vwap"])
                expected_spot = self._fee_amounts(-R, D(item["spot_vwap"]), spot_fee)[1]
                expected_perp = self._fee_amounts(q, D(item["perp_vwap"]), perp_fee)[1] if q else ZERO
                if D(item["spot_explicit_cost"]) != expected_spot or D(item["perp_explicit_cost"]) != expected_perp:
                    raise AccountingError("outcome fee mutation mismatch")
                proven.append((R, q))
        if set(indexed) != {(decimal_string(R), decimal_string(q)) for R, q in proven}:
            raise AccountingError("undeclared endpoint/outcome")
        return tuple(proven)

    def severe_path_preflight(self, actual_price: Any, worst_permitted_price: Any, side: str,
                              source: SourceMark, rule_digest: str) -> None:
        actual, worst = D(actual_price), D(worst_permitted_price)
        if source.source_digest not in self.binding.source_digests or source.rules_digest != rule_digest:
            raise AccountingError("severe source/rule mismatch")
        if actual != source.open:
            raise AccountingError("severe price not observed open")
        if (side == "buy" and actual > worst) or (side == "sell" and actual < worst):
            raise AccountingError("actual severe price worse than frozen bound")

    def pair_close_preflight(self, paths: Sequence[Mapping[str, Any]], expected_pairs: Iterable[tuple[Any, Any]],
                             source_digest: str) -> None:
        if self.binding.selected_mandate_id != "retail-btc-delta-neutral-research-v1":
            raise AccountingError("pair mandate required")
        expected = {(decimal_string(R), decimal_string(q)) for R, q in expected_pairs}
        actual: set[tuple[str, str]] = set()
        for path in paths:
            for key in ("R", "q", "ordinary_funded", "residual_valid", "severe_funded",
                        "spot_rules_digest", "perp_rules_digest", "source_digest"):
                if key not in path: raise AccountingError("incomplete recovery path")
            pair = (decimal_string(path["R"]), decimal_string(path["q"]))
            if pair in actual: raise AccountingError("duplicate recovery path")
            actual.add(pair)
            if not (path["ordinary_funded"] and path["residual_valid"] and path["severe_funded"]):
                raise AccountingError("invalid recovery path")
            if path["spot_rules_digest"] != self.spot_rules.digest or path["perp_rules_digest"] != self.perpetual_rules.digest or path["source_digest"] != source_digest:
                raise AccountingError("recovery lineage mismatch")
        if actual != expected:
            raise AccountingError("recovery Cartesian set mismatch")

    def pair_failure(self, reason: str, *, neutralized: bool, attempts: int, commits: int) -> None:
        if attempts != 1 or commits < 1:
            raise AccountingError("one finite committed recovery attempt required")
        self._invalidate(reason, unknown=True)
        self.pending_safety = None if neutralized else "whole_pair_close"

    def atomic_pair_close(self, intention_id: str, spot_source: SourceMark,
                          perpetual_source: SourceMark, spot_gross_sale: Any,
                          intended_perpetual_fill: Any, spot_fee: Fee, perpetual_fee: Fee,
                          severe_source: SourceMark, severe_fee: Fee,
                          worst_severe_buy_price: Any, recovery_paths: Sequence[Mapping[str, Any]],
                          expected_pairs: Iterable[tuple[Any, Any]]) -> dict[str, Any]:
        """Commit a spot-first pair reduction and neutralize its created naked short.

        All Cartesian recovery paths are proven before leg one.  Once leg one commits,
        failures are retained and the intention becomes sticky invalid/unknown.
        """
        if spot_source.timestamp != perpetual_source.timestamp:
            raise AccountingError("pair legs require one arrival timestamp")
        if spot_source.segment_id != perpetual_source.segment_id or severe_source.segment_id != spot_source.segment_id:
            raise AccountingError("pair common segment required")
        self.pair_close_preflight(recovery_paths, expected_pairs, spot_source.source_digest)
        gross = D(spot_gross_sale)
        if gross <= ZERO:
            raise AccountingError("spot sale must be positive")
        intended = D(intended_perpetual_fill)
        if intended < ZERO:
            raise AccountingError("perpetual close must buy")
        # Validate every concrete leg, including the severe bound, before leg one.
        self.spot_rules.validate(-gross, spot_source.open)
        if intended:
            self.perpetual_rules.validate(intended, perpetual_source.open)
        self.severe_path_preflight(severe_source.open, worst_severe_buy_price, "buy",
                                   severe_source, self.perpetual_rules.digest)
        pre_spot = self.state.spot_quantity_BTC
        commits = 0
        try:
            spot_row = self.fill(intention_id + ":spot", spot_source.timestamp, spot_source.instrument,
                -gross, spot_source.open, spot_fee, spot_source, protective=True,
                reason="atomic_pair_close_spot_first")
            commits += 1
            reduction = pre_spot - self.state.spot_quantity_BTC
            target = self.perpetual_rules.quantity(reduction)
            if target != reduction or target > abs(self.state.signed_perpetual_quantity_BTC):
                raise AccountingError("actual spot reduction cannot form rule-valid close")
            perp_row = None
            if intended:
                if intended > target:
                    raise AccountingError("intended perpetual fill exceeds actual reduction")
                perp_row = self.fill(intention_id + ":perpetual", perpetual_source.timestamp,
                    perpetual_source.instrument, intended, perpetual_source.open, perpetual_fee,
                    perpetual_source, protective=True, allow_partial=self.binding.adapter_id == "qualified_quote_L2",
                    requested_quantity=target, reason="atomic_pair_close_intended_perpetual")
                commits += 1
            residual = reduction - intended
            severe_row = None
            if residual:
                self.perpetual_rules.validate(residual, severe_source.open)
                severe_row = self.fill(intention_id + ":severe_residual", severe_source.timestamp,
                    severe_source.instrument, residual, severe_source.open, severe_fee, severe_source,
                    protective=True, reason="forced_severe_residual_close")
                commits += 1
            spot_notional = self.state.spot_quantity_BTC * spot_source.open
            perp_notional = abs(self.state.signed_perpetual_quantity_BTC) * perpetual_source.open
            denominator = max(abs(spot_notional), abs(perp_notional))
            mismatch = ZERO if denominator == ZERO else abs(abs(spot_notional) - abs(perp_notional)) / denominator
            if mismatch > self.binding.mismatch_limit:
                self.pair_failure("post_close_pair_mismatch", neutralized=False, attempts=1, commits=commits)
            return _canonical({"spot_fill_digest": spot_row["row_digest"],
                "perpetual_fill_digest": None if perp_row is None else perp_row["row_digest"],
                "severe_fill_digest": None if severe_row is None else severe_row["row_digest"],
                "actual_spot_reduction": reduction, "created_residual": residual,
                "remaining_notional_mismatch": mismatch, "commits": commits,
                "invalidation_reason_or_null": self.invalidation_reason})
        except AccountingError:
            if commits:
                self.pair_failure("pair_close_committed_failure", neutralized=False, attempts=1,
                                  commits=commits)
            raise

    def controls(self, partition_open: SourceMark, partition_close: SourceMark,
                 same_exposure_events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if partition_open.timestamp != self.binding.partition_start:
            raise AccountingError("buy-hold must start at partition boundary")
        if partition_close.timestamp > self.binding.terminal_timestamp:
            raise AccountingError("control crosses boundary")
        if partition_open.instrument != "BTC_USDT_spot" or partition_close.instrument != "BTC_USDT_spot":
            raise AccountingError("buy-hold requires spot observations")
        flat = AccountingEngine(self.binding, self.starting_nav, self.spot_rules, self.perpetual_rules)
        flat.segment_id = partition_open.segment_id
        flat.account_row(partition_open, ZERO)
        flat.segment_id = partition_close.segment_id
        flat.account_row(partition_close, ZERO)
        hold = AccountingEngine(self.binding, self.starting_nav, self.spot_rules, self.perpetual_rules)
        hold.segment_id = partition_open.segment_id; hold.spot_mark = partition_open.open
        quantity = self.spot_rules.quantity(
            self.starting_nav * self.binding.maximum_notional_fraction / partition_open.open)
        hold.fill("buy_hold_entry", partition_open.timestamp, partition_open.instrument, quantity,
                  partition_open.open, Fee("quote", ZERO), partition_open, protective=False)
        hold.account_row(partition_open, ZERO)
        terminal_source = SourceMark("BTC_USDT_spot", partition_close.timestamp,
            partition_close.segment_id, partition_close.close, partition_close.close,
            partition_close.close, partition_close.close, partition_close.observed_at,
            partition_close.available_at, partition_close.source_digest,
            partition_close.mark_source_digest, partition_close.rules_digest)
        hold.segment_id = terminal_source.segment_id
        hold.fill("buy_hold_exit", terminal_source.timestamp, terminal_source.instrument,
                  -hold.state.spot_quantity_BTC, terminal_source.open, Fee("quote", ZERO),
                  terminal_source, protective=True, reason="terminal_flatten")
        hold.account_row(terminal_source, ZERO)
        matched = AccountingEngine(self.binding, self.starting_nav, self.spot_rules, self.perpetual_rules)
        matched.segment_id = partition_open.segment_id; matched.spot_mark = partition_open.open
        for number, event in enumerate(same_exposure_events, 1):
            event_at = utc(event["at"])
            matched.decision("control-" + str(number), event_at, str(event["exposure"]),
                partition_open.source_digest, partition_open.rules_digest, event_at, D(event["exposure"]) != ZERO)
        return {"flat": {"starting_NAV": decimal_string(self.starting_nav),
                          "ending_NAV": decimal_string(flat.nav()), "ledger": flat.ledgers},
                "true_buy_and_hold": {"entry_at": timestamp_string(partition_open.timestamp),
                    "exit_at": timestamp_string(partition_close.timestamp), "ledger": hold.ledgers},
                "same_timestamp_same_exposure": {"events": [_canonical(x) for x in same_exposure_events],
                    "ledger": matched.ledgers}, "terminal_convention": self.binding.terminal_convention}

    def summary(self) -> dict[str, Any]:
        ending = self.nav()
        return _canonical({"starting_NAV": self.starting_nav, "ending_NAV": ending,
            "spot_price_PnL": self.spot_price_pnl, "perpetual_price_PnL": self.perpetual_price_pnl,
            "funding_PnL": self.state.accrued_funding, "explicit_costs": self.state.explicit_costs,
            "implicit_costs": self.state.implicit_costs, "neutralization_costs": ZERO,
            "diagnostic_opportunity_cost": ZERO,
            "diagnostic_missed_unfilled_and_unused_rounded_notional": ZERO,
            "accounting_residual": ending - self.starting_nav - self.spot_price_pnl
                - self.perpetual_price_pnl - self.state.accrued_funding
                + self.state.explicit_costs + self.state.implicit_costs,
            "rejected_expired_partial_and_unfilled_counts": {"rejected": 0, "expired": 0, "partial": 0, "unfilled": 0},
            "unknown_or_invalid_intervals": int(self.invalid), "artifact_digests": {},
            "run_invalidation_reason": self.invalidation_reason, "actionable_arm_id": ACTIONABLE_ARM_ID})


def verify_manifest_bound_implementation(manifest: Mapping[str, Any], active_path: str,
                                         snapshot_path: str, active_bytes: bytes,
                                         snapshot_bytes: bytes) -> str:
    """Derive implementation identity only from exact manifest-bound bytes."""
    if active_bytes != snapshot_bytes:
        raise AccountingError("active/snapshot bytes differ")
    entries = manifest.get("entries")
    if not isinstance(entries, list): raise AccountingError("manifest entries required")
    by_path = {entry.get("path"): entry for entry in entries}
    if set(by_path) != {entry.get("path") for entry in entries} or len(by_path) != len(entries):
        raise AccountingError("duplicate manifest path")
    actual = sha256(active_bytes).hexdigest()
    for path in (active_path, snapshot_path):
        entry = by_path.get(path)
        if entry is None or set(entry) != {"path", "sha256", "size_bytes", "semantic_role"}:
            raise AccountingError("manifest entry schema")
        if entry["sha256"] != actual or entry["size_bytes"] != len(active_bytes):
            raise AccountingError("manifest byte mismatch")
    return actual


__all__ = ["AccountingEngine", "AccountingError", "ACCOUNT_FIELDS", "ACTIONABLE_ARM_ID",
           "DECISION_FIELDS", "D", "EPISODE_FIELDS", "EXPERIMENT_ID", "FILL_FIELDS", "FUNDING_FIELDS",
           "Fee", "InstrumentRules", "MANDATE_AUTHORITIES", "ORDER_FIELDS", "PortfolioState",
           "REQUIRED_SCENARIOS", "RunBinding", "SourceMark", "canonical_json", "decimal_string",
           "digest", "parse_json_strict", "timestamp_string", "verify_manifest_bound_implementation"]
