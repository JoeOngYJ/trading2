"""Decimal account ledger for the synthetic E1-v14 engine.

This module deliberately has no public constructor and no general purpose event/fill
method.  The facade/authority layer supplies already verified, immutable authorities;
the small set of engine-owned methods below advance that frozen event stream.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from . import authorities as _authorities
from . import canonical as _canonical


ZERO = Decimal("0")
ONE = Decimal("1")
TEN_THOUSAND = Decimal("10000")
RESIDUAL_LIMIT = Decimal("0.00000001")
EXPERIMENT_ID = "btc-unified-backtest-engine-e1-v14"
_IMPLEMENTATION_DIGEST = sha256(Path(__file__).read_bytes()).hexdigest()

PHASES = (
    "validate_timestamp_inputs_and_snapshot_incoming_state",
    "open_mark_and_immediate_liquidation",
    "precaused_protective_or_gap_reduction",
    "tminus_funding_and_immediate_liquidation",
    "risk_and_mandate_permissions",
    "ordinary_exit_rebalance_or_next_open_entry",
    "post_fill_margin_checkpoint",
    "intrabar_adverse_then_close_mark",
    "reconcile_account_and_advance_resets",
)

DECISION_FIELDS = (
    "decision_id", "decision_at", "available_information_cutoff", "requested_target",
    "permission_or_abstention", "reason", "source_digest", "rules_digest",
    "lineage_digest", "event_sequence", "before_state_digest", "after_state_digest",
    "event_accounting_residual", "invalidation_reason", "row_digest",
)
ORDER_FIELDS = (
    "order_id", "decision_id", "created_at", "arrival_at", "instrument",
    "requested_quantity", "rounded_quantity", "filled_quantity", "unfilled_quantity",
    "status", "reason", "price_bound", "scenario_id", "source_digest", "rules_digest",
    "event_sequence", "before_state_digest", "after_state_digest",
    "event_accounting_residual", "invalidation_reason", "row_digest",
)
FILL_FIELDS = (
    "fill_id", "order_id", "fill_at", "instrument", "signed_quantity",
    "accounting_fill_price", "explicit_fee_native", "explicit_fee_asset",
    "explicit_fee_quote_equivalent", "implicit_cost_quote", "post_fill_position",
    "rules_digest", "source_digest", "event_sequence", "before_state_digest",
    "after_state_digest", "event_accounting_residual", "invalidation_reason", "row_digest",
)
FUNDING_FIELDS = (
    "funding_at", "t_minus_signed_quantity", "funding_rate", "funding_mark",
    "cashflow_quote", "economic_at", "available_at", "mark_source_digest",
    "index_source_digest", "rules_digest", "source_digest", "event_sequence",
    "before_state_digest", "after_state_digest", "event_accounting_residual",
    "invalidation_reason", "row_digest",
)
ACCOUNT_FIELDS = (
    "timestamp", "segment_id", "quote_cash", "spot_quantity", "perpetual_quantity",
    "isolated_collateral", "allocated_initial_margin_memo", "exit_cost_reserve_memo",
    "fee_asset_balances", "liabilities", "realized_PnL", "unrealized_PnL", "funding",
    "explicit_costs", "implicit_costs", "NAV", "gross_exposure", "net_exposure",
    "margin_equity", "maintenance_requirement", "state", "source_digest", "rules_digest",
    "mark_source_digest", "index_source_digest", "event_sequence", "before_state_digest",
    "after_state_digest", "event_accounting_residual", "invalidation_reason", "row_digest",
)
EPISODE_FIELDS = (
    "episode_id", "opened_at", "closed_at", "direction", "entry_costs", "exit_costs",
    "price_PnL", "funding_PnL", "net_dollar_PnL", "maximum_adverse_excursion",
    "maximum_favourable_excursion", "close_reason", "entry_fill_digests",
    "exit_fill_digests", "source_digests", "rules_digests", "invalidation_reason",
    "row_digest",
)
LINEAGE_FIELDS = (
    "experiment_id", "run_id", "scenario_id", "implementation_digest", "contract_digest",
    "execution_config_digest", "mandate_digest",
)


def _d(value: Any, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("economic values must be finite Decimal-compatible strings")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid Decimal") from exc
    if not result.is_finite() or (positive and result <= ZERO):
        raise ValueError("non-finite or non-positive economic value")
    return result


def _ds(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == ZERO:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _ds(value)
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


def _digest(value: Any) -> str:
    # Canonical owns the domain in production.  Keeping the call loosely coupled lets the
    # ledger consume the intentionally tiny canonical module API.
    for name in ("digest", "canonical_digest", "sha256_digest"):
        helper = getattr(_canonical, name, None)
        if helper is not None:
            try:
                return str(helper(_plain(value)))
            except TypeError:
                pass
    raw = json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be UTC RFC3339 Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != timezone.utc:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    value = getattr(obj, key, None)
    if value is not None:
        return value
    payload = getattr(obj, "payload", None)
    if isinstance(payload, Mapping):
        return payload.get(key, default)
    return default


@dataclass(frozen=True, slots=True)
class AccountState:
    quote_cash: Decimal
    spot_quantity: Decimal = ZERO
    perpetual_quantity: Decimal = ZERO
    average_perpetual_entry: Decimal | None = None
    isolated_collateral: Decimal = ZERO
    allocated_initial_margin_memo: Decimal = ZERO
    exit_cost_reserve_memo: Decimal = ZERO
    fee_asset_balances: tuple[tuple[str, Decimal], ...] = ()
    fee_asset_marks: tuple[tuple[str, Decimal], ...] = ()
    liabilities: Decimal = ZERO
    realized_PnL: Decimal = ZERO
    unrealized_PnL: Decimal = ZERO
    funding: Decimal = ZERO
    explicit_costs: Decimal = ZERO
    implicit_costs: Decimal = ZERO
    spot_mark: Decimal = ZERO
    perpetual_mark: Decimal = ZERO
    NAV: Decimal = ZERO
    high_water_NAV: Decimal = ZERO
    UTC_day_start_equity: Decimal = ZERO
    UTC_day: str | None = None
    segment_id: str | None = None
    state: str = "active"
    invalidation_reason: str | None = None
    terminal: bool = False
    new_exposure_enabled: bool = True
    pending_protection: str | None = None


def _apply_native_fee(state: AccountState, *, instrument: str, asset: str,
                      native_amount: Any, quote_equivalent: Any) -> AccountState:
    """Apply one already-authorized fee/tax mutation exactly once.

    This is a package-private accounting primitive, not an event API.  Fee selection and
    conversion remain authority-owned; callers cannot reach it through the facade.
    """
    native = _d(native_amount)
    quote = _d(quote_equivalent)
    if native < ZERO or quote < ZERO:
        raise ValueError("fee amounts cannot be negative")
    if asset == "USDT":
        if instrument == "BTCUSDT_USD_M_perpetual":
            if state.isolated_collateral < native:
                raise ValueError("insufficient isolated collateral for fee")
            return replace(state, isolated_collateral=state.isolated_collateral - native,
                           explicit_costs=state.explicit_costs + quote)
        if state.quote_cash < native:
            raise ValueError("insufficient quote fee balance")
        return replace(state, quote_cash=state.quote_cash - native,
                       explicit_costs=state.explicit_costs + quote)
    if asset == "BTC":
        if instrument != "BTC/USDT":
            raise ValueError("base fee is unsupported for perpetual")
        if state.spot_quantity < native:
            raise ValueError("insufficient base fee balance")
        return replace(state, spot_quantity=state.spot_quantity - native,
                       explicit_costs=state.explicit_costs + quote)
    balances = dict(state.fee_asset_balances)
    if asset not in balances or balances[asset] < native:
        raise ValueError("insufficient or unsupported third fee asset")
    if asset not in dict(state.fee_asset_marks):
        raise ValueError("missing point-in-time third-asset mark")
    balances[asset] -= native
    return replace(state, fee_asset_balances=tuple(sorted(balances.items())),
                   explicit_costs=state.explicit_costs + quote)


@dataclass(slots=True)
class _Episode:
    episode_id: str
    opened_at: str
    direction: str
    entry_costs: Decimal = ZERO
    exit_costs: Decimal = ZERO
    price_pnl: Decimal = ZERO
    funding_pnl: Decimal = ZERO
    mae: Decimal = ZERO
    mfe: Decimal = ZERO
    entry_fills: list[str] = None  # type: ignore[assignment]
    exit_fills: list[str] = None  # type: ignore[assignment]
    sources: set[str] = None  # type: ignore[assignment]
    rules: set[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.entry_fills = []
        self.exit_fills = []
        self.sources = set()
        self.rules = set()


class _LedgerEngine:
    """Capability-created engine.  Callers never construct this class directly."""

    __slots__ = (
        "_binding", "_spec", "_rules", "_margin", "_settings", "_source", "_scenarios",
        "_state", "_rows", "_episodes", "_episode", "_phase", "_cursor", "_current",
        "_tminus", "_seq", "_last_digest", "_seen", "_entry_days", "_entry_times",
        "_last_timestamp",
    )

    def __init__(self, binding: Any) -> None:
        self._binding = binding
        if isinstance(binding, _authorities.RunSpec):
            self._spec = binding
            self._rules = _authorities.authority("instrument_rules")
            self._margin = _authorities.margin_rule(binding)
            self._settings = _authorities.authority("semantic_settings")
            records = _authorities.source_records(binding)
            key = "observations" if binding.adapter == "candle" else "snapshots"
            self._source = {key: records}
            self._scenarios = _authorities.authority("execution_scenarios")
        else:
            self._spec = _get(binding, "run_spec", _get(binding, "spec", {}))
            self._rules = _get(binding, "rules", {})
            self._margin = _get(binding, "margin", {})
            self._settings = _get(binding, "settings", {})
            self._source = _get(binding, "source", {})
            self._scenarios = _get(binding, "scenarios", _get(binding, "execution", {}))
        nav = _d(_get(self._spec, "initial_NAV", _get(self._spec, "initial_nav", "1000")), positive=True)
        self._state = AccountState(quote_cash=nav, NAV=nav, high_water_NAV=nav,
                                   UTC_day_start_equity=nav)
        self._rows: dict[str, list[dict[str, Any]]] = {
            "decision": [], "order": [], "fill": [], "funding": [], "account": [], "phase": []
        }
        self._episodes: list[dict[str, Any]] = []
        self._episode: _Episode | None = None
        self._phase = 0
        self._cursor = 0
        self._current: dict[str, Mapping[str, Any]] | None = None
        self._tminus = ZERO
        self._seq = 0
        self._last_digest = self._state_digest()
        self._seen: set[tuple[str, str]] = set()
        self._entry_days: set[str] = set()
        self._entry_times: list[datetime] = []
        self._last_timestamp: datetime | None = None

    @property
    def state(self) -> AccountState:
        return self._state

    @property
    def rows(self) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        return MappingProxyType({k: tuple(_freeze(row) for row in v) for k, v in self._rows.items()})

    @property
    def episodes(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(_freeze(row) for row in self._episodes)

    @property
    def bindings(self) -> Any:
        return _freeze(_plain(self._binding))

    @property
    def phase(self) -> int:
        return self._phase

    def open_next_interval(self) -> Mapping[str, Any]:
        if self._state.terminal:
            raise RuntimeError("terminal ledger cannot advance")
        if self._phase != 0:
            raise RuntimeError("previous interval is not closed")
        grouped = self._observations()
        if self._cursor >= len(grouped):
            raise StopIteration
        candidate = grouped[self._cursor]
        self._validate_group(candidate)
        self._cursor += 1
        self._current = candidate
        day = self._timestamp()[:10]
        if self._state.UTC_day is not None and day != self._state.UTC_day:
            self._state = replace(self._state, UTC_day=day,
                                  UTC_day_start_equity=self._state.NAV)
        self._tminus = self._state.perpetual_quantity
        self._record_phase(1)
        self._phase_open_mark()
        if not self._state.terminal:
            self._phase_protection()
        if not self._state.terminal:
            self._phase_funding()
        if not self._state.terminal:
            self._phase_permissions()
        return _freeze({"timestamp": self._timestamp(), "phase": self._phase,
                        "t_minus_perpetual_quantity": _ds(self._tminus)})

    def submit_spot_target(self, target_quantity: Any) -> Mapping[str, Any]:
        self._require_ordinary("spot_candle_primary")
        target = _d(target_quantity)
        if target < ZERO:
            raise ValueError("spot target cannot be negative")
        return self._ordinary_target("BTC/USDT", target)

    def submit_directional_target(self, target_quantity: Any) -> Mapping[str, Any]:
        self._require_ordinary("directional_candle_primary")
        return self._ordinary_target("BTCUSDT_USD_M_perpetual", _d(target_quantity))

    def close_interval(self) -> Mapping[str, Any]:
        if self._state.terminal:
            raise RuntimeError("terminal ledger cannot close again")
        if self._phase not in (5, 7):
            raise RuntimeError("interval is not ready to close")
        if self._phase == 5:
            self._record_phase(6)
            self._record_phase(7)
        self._phase_intrabar_close()
        if not self._state.terminal:
            self._phase_reconcile()
        result = {"timestamp": self._timestamp(), "phase": self._phase,
                  "terminal": self._state.terminal}
        if not self._state.terminal:
            self._phase = 0
            self._current = None
        return _freeze(result)

    def terminate(self) -> Mapping[str, Any]:
        if self._state.terminal:
            return _freeze({"terminal": True, "reason": self._state.invalidation_reason})
        if self._phase == 0:
            raise RuntimeError("termination requires an open interval")
        if self._phase == 5:
            self._record_phase(6)
        # A declared terminal flatten is a reduction and remains available despite risk gates.
        if self._state.perpetual_quantity != ZERO:
            self._engine_fill("BTCUSDT_USD_M_perpetual", -self._state.perpetual_quantity,
                              self._open_price("BTCUSDT_USD_M_perpetual"), severe=True,
                              reason="terminal_flatten")
        if self._state.spot_quantity != ZERO:
            self._engine_fill("BTC/USDT", -self._state.spot_quantity,
                              self._open_price("BTC/USDT"), severe=True,
                              reason="terminal_flatten")
        if self._phase == 6:
            self._record_phase(7)
        if self._phase == 7:
            self._record_phase(8)
        self._state = replace(self._state, terminal=True, state="terminated",
                              new_exposure_enabled=False)
        self._emit_account("terminal")
        self._record_phase(9)
        return _freeze({"terminal": True, "reason": None})

    # ---- private collaboration surface for pair.py; not exported by the facade ----
    def _pair_ready(self) -> None:
        self._require_ordinary(("pair_candle_primary", "pair_l2_primary"))

    def _source_price(self, instrument: str) -> Decimal:
        return self._open_price(instrument)

    def _rule(self, instrument: str) -> Mapping[str, Any]:
        if isinstance(self._spec, _authorities.RunSpec):
            return _authorities.instrument_rule(self._spec, instrument)
        return _get(_get(self._rules, "instruments", {}), instrument, {})

    def _apply_pair_fill(self, instrument: str, signed_quantity: Any, *, severe: bool = False,
                         reason: str = "pair") -> Mapping[str, Any]:
        if self._phase == 5:
            self._record_phase(6)
        result = self._engine_fill(instrument, _d(signed_quantity), self._open_price(instrument),
                                   severe=severe, reason=reason)
        self._margin_checkpoint("post_pair_fill")
        if not self._state.terminal:
            self._phase = 7
        return result

    def _check_pair_delta(self, spot_quantity: Any, perpetual_quantity: Any,
                          spot_price: Any, perpetual_price: Any) -> None:
        """Enforce the pair mandate using point-in-time price notionals."""
        spot_q, perp_q = _d(spot_quantity), _d(perpetual_quantity)
        spot_p, perp_p = _d(spot_price, positive=True), _d(perpetual_price, positive=True)
        if spot_q < ZERO or perp_q > ZERO or ((spot_q == ZERO) != (perp_q == ZERO)):
            raise ValueError("pair cannot contain a naked or wrong-direction leg")
        spot_n, perp_n = spot_q * spot_p, abs(perp_q) * perp_p
        cap = self._state.NAV * Decimal("0.5")
        if spot_n > cap or perp_n > cap:
            raise ValueError("pair leg exceeds 50 percent equity cap")
        denominator = max(spot_n, perp_n)
        mismatch = ZERO if denominator == ZERO else abs(spot_n - perp_n) / denominator
        if mismatch > Decimal("0.01"):
            raise ValueError("pair point-in-time notional mismatch exceeds one percent")

    def _reject_order(self, instrument: str, requested: Any, reason: str, *, severe: bool = False) -> Mapping[str, Any]:
        return self._emit_rejection(instrument, _d(requested), reason, severe=severe)

    def _invalidate(self, reason: str, *, pending: str | None = None) -> None:
        self._state = replace(self._state, state="invalid_unknown", invalidation_reason=reason,
                              new_exposure_enabled=False, pending_protection=pending)

    # ---- phases ----
    def _record_phase(self, number: int) -> None:
        if number != self._phase + 1:
            raise RuntimeError("phase order violation")
        self._phase = number
        self._rows["phase"].append({"phase": number, "name": PHASES[number - 1],
                                    "timestamp": self._timestamp() if self._current else None,
                                    "state_digest": self._state_digest()})

    def _phase_open_mark(self) -> None:
        self._record_phase(2)
        spot = self._open_price("BTC/USDT", optional=True)
        perp = self._open_price("BTCUSDT_USD_M_perpetual", optional=True)
        self._mark(spot, perp)
        if self._state.perpetual_quantity != ZERO:
            self._margin_checkpoint("opening_mark")

    def _phase_protection(self) -> None:
        self._record_phase(3)
        pending = self._state.pending_protection
        if not pending:
            return
        if self._state.perpetual_quantity != ZERO:
            self._engine_fill("BTCUSDT_USD_M_perpetual", -self._state.perpetual_quantity,
                              self._open_price("BTCUSDT_USD_M_perpetual"), severe=True,
                              reason=pending)
        if self._state.spot_quantity != ZERO:
            self._engine_fill("BTC/USDT", -self._state.spot_quantity,
                              self._open_price("BTC/USDT"), severe=True, reason=pending)
        self._state = replace(self._state, pending_protection=None)

    def _phase_funding(self) -> None:
        self._record_phase(4)
        perp = self._current.get("BTCUSDT_USD_M_perpetual") if self._current else None
        funding = _get(perp, "funding") if perp else None
        if funding is None or self._tminus == ZERO:
            return
        rate = _d(_get(funding, "rate"))
        mark = _d(_get(perp, "mark_open", _get(perp, "mark")), positive=True)
        cashflow = -self._tminus * mark * rate
        before = self._state
        if self._state.perpetual_quantity == ZERO:
            state = replace(self._state, quote_cash=self._state.quote_cash + cashflow)
        else:
            state = replace(self._state, isolated_collateral=self._state.isolated_collateral + cashflow)
        self._state = replace(state, funding=state.funding + cashflow)
        self._refresh()
        row = {
            "funding_at": self._timestamp(), "t_minus_signed_quantity": _ds(self._tminus),
            "funding_rate": _ds(rate), "funding_mark": _ds(mark), "cashflow_quote": _ds(cashflow),
            "economic_at": _get(funding, "economic_at"), "available_at": _get(funding, "available_at"),
            "mark_source_digest": self._source_digest(perp), "index_source_digest": self._source_digest(perp),
            "rules_digest": self._rules_digest(), "source_digest": self._source_digest(perp),
        }
        self._append_row("funding", row, before, self._state, funding=cashflow)
        if self._episode is not None:
            self._episode.funding_pnl += cashflow
        if self._state.perpetual_quantity != ZERO:
            self._margin_checkpoint("funding")

    def _phase_permissions(self) -> None:
        self._record_phase(5)
        nav = self._state.NAV
        daily = nav / self._state.UTC_day_start_equity - ONE
        drawdown = nav / self._state.high_water_NAV - ONE
        enabled = (daily > Decimal("-0.015") and drawdown > Decimal("-0.10")
                   and self._state.invalidation_reason is None)
        self._state = replace(self._state, new_exposure_enabled=enabled)

    def _phase_intrabar_close(self) -> None:
        self._record_phase(8)
        perp = self._current.get("BTCUSDT_USD_M_perpetual") if self._current else None
        if self._state.perpetual_quantity > ZERO and perp:
            adverse = _d(_get(perp, "low"), positive=True)
            self._mark(None, adverse)
            self._update_excursion()
            self._margin_checkpoint("intrabar_adverse")
        elif self._state.perpetual_quantity < ZERO and perp:
            adverse = _d(_get(perp, "high"), positive=True)
            self._mark(None, adverse)
            self._update_excursion()
            self._margin_checkpoint("intrabar_adverse")
        if self._state.terminal:
            return
        spot = self._close_price("BTC/USDT", optional=True)
        perp_close = self._close_price("BTCUSDT_USD_M_perpetual", optional=True)
        self._mark(spot, perp_close)
        self._update_excursion()

    def _phase_reconcile(self) -> None:
        self._record_phase(9)
        before = self._state
        day = self._timestamp()[:10]
        day_start = self._state.UTC_day_start_equity
        if self._state.UTC_day is not None and self._state.UTC_day != day:
            day_start = self._state.NAV
        high = max(self._state.high_water_NAV, self._state.NAV)
        self._state = replace(self._state, UTC_day=day, UTC_day_start_equity=day_start,
                              high_water_NAV=high)
        self._emit_account("reconciled", before=before)

    # ---- orders and accounting ----
    def _ordinary_target(self, instrument: str, target: Decimal) -> Mapping[str, Any]:
        current = self._state.spot_quantity if instrument == "BTC/USDT" else self._state.perpetual_quantity
        delta = target - current
        self._record_phase(6)
        price = self._open_price(instrument)
        increasing = abs(target) > abs(current)
        if increasing and not self._state.new_exposure_enabled:
            result = self._emit_rejection(instrument, delta, "risk_entry_disabled")
        elif increasing and target * current > ZERO:
            result = self._emit_rejection(instrument, delta, "pyramiding_forbidden")
        elif increasing and not self._cadence_allows():
            result = self._emit_rejection(instrument, delta, "cadence_limit")
        else:
            cap = Decimal("0.25") * self._state.NAV
            if abs(target) * price > cap:
                result = self._emit_rejection(instrument, delta, "exposure_cap")
            elif current != ZERO and target != ZERO and current * target < ZERO:
                self._engine_fill(instrument, -current, price, reason="reversal_close")
                result = self._engine_fill(instrument, target, price, reason="reversal_open")
                now = _utc(self._timestamp())
                self._entry_days.add(self._timestamp()[:10])
                self._entry_times.append(now)
            else:
                result = self._engine_fill(instrument, delta, price, reason="ordinary_target")
                if increasing and _d(result["filled_quantity"]) != ZERO:
                    now = _utc(self._timestamp())
                    self._entry_days.add(self._timestamp()[:10])
                    self._entry_times.append(now)
        if not self._state.terminal:
            self._margin_checkpoint("post_fill")
            self._record_phase(7)
        return result

    def _engine_fill(self, instrument: str, signed_quantity: Decimal, price: Decimal, *,
                     severe: bool = False, reason: str) -> Mapping[str, Any]:
        rule = self._rule(instrument)
        step = _d(_get(rule, "step", "0.00000001"), positive=True)
        rounded = (abs(signed_quantity) / step).to_integral_value(rounding=ROUND_DOWN) * step
        rounded = rounded.copy_sign(signed_quantity)
        scenario = self._scenario(severe)
        requested = signed_quantity
        if rounded == ZERO:
            return self._emit_rejection(instrument, requested, "rounded_to_zero", severe=severe)
        if abs(rounded) > _d(_get(rule, "maximum_quantity", "999999")):
            return self._emit_rejection(instrument, requested, "maximum_quantity", severe=severe)
        if abs(rounded) * price < _d(_get(rule, "minimum_notional", "0")):
            return self._emit_rejection(instrument, requested, "minimum_notional", severe=severe)
        before = self._state
        explicit_rate = _d(_get(scenario, "taker_fee_bps", "0")) / TEN_THOUSAND
        implicit_rate = _d(_get(scenario, "implicit_cost_bps_per_side", "0")) / TEN_THOUSAND
        explicit = abs(rounded) * price * explicit_rate
        implicit = abs(rounded) * price * implicit_rate
        if instrument == "BTC/USDT":
            self._spot_transition(rounded, price, explicit, implicit)
            post = self._state.spot_quantity
        else:
            self._perpetual_transition(rounded, price, explicit, implicit)
            post = self._state.perpetual_quantity
        self._refresh()
        decision_id = f"D{self._seq + 1:06d}"
        order_id = f"O{self._seq + 1:06d}"
        fill_id = f"F{self._seq + 1:06d}"
        common = {"source_digest": self._current_source_digest(instrument),
                  "rules_digest": self._rules_digest()}
        self._append_row("decision", {
            "decision_id": decision_id, "decision_at": self._timestamp(),
            "available_information_cutoff": self._timestamp(), "requested_target": _ds(post),
            "permission_or_abstention": "permitted", "reason": reason,
            "lineage_digest": _digest(self._lineage()), **common,
        }, before, before)
        self._append_row("order", {
            "order_id": order_id, "decision_id": decision_id, "created_at": self._timestamp(),
            "arrival_at": self._arrival(), "instrument": instrument,
            "requested_quantity": _ds(requested), "rounded_quantity": _ds(rounded),
            "filled_quantity": _ds(rounded), "unfilled_quantity": _ds(requested - rounded),
            "status": "filled" if requested == rounded else "partial_rounded",
            "reason": reason, "price_bound": self._price_bound(price, scenario),
            "scenario_id": _get(scenario, "scenario_id"), **common,
        }, before, before)
        fill_row = self._append_row("fill", {
            "fill_id": fill_id, "order_id": order_id, "fill_at": self._arrival(),
            "instrument": instrument, "signed_quantity": _ds(rounded),
            "accounting_fill_price": _ds(price), "explicit_fee_native": _ds(explicit),
            "explicit_fee_asset": "USDT", "explicit_fee_quote_equivalent": _ds(explicit),
            "implicit_cost_quote": _ds(implicit), "post_fill_position": _ds(post), **common,
        }, before, self._state, explicit=explicit, implicit=implicit)
        self._episode_fill(instrument, rounded, before, fill_row, explicit + implicit, reason)
        return _freeze(self._rows["order"][-1])

    def _spot_transition(self, quantity: Decimal, price: Decimal, explicit: Decimal,
                         implicit: Decimal) -> None:
        if quantity < ZERO and -quantity > self._state.spot_quantity:
            raise ValueError("spot inventory cannot become negative")
        quote = self._state.quote_cash - quantity * price - explicit - implicit
        if quantity > ZERO and quote < ZERO:
            raise ValueError("insufficient quote cash")
        self._state = replace(self._state, quote_cash=quote,
                              spot_quantity=self._state.spot_quantity + quantity,
                              explicit_costs=self._state.explicit_costs + explicit,
                              implicit_costs=self._state.implicit_costs + implicit)

    def _perpetual_transition(self, quantity: Decimal, price: Decimal, explicit: Decimal,
                              implicit: Decimal) -> None:
        oldq = self._state.perpetual_quantity
        newq = oldq + quantity
        if oldq != ZERO and newq != ZERO and oldq * newq < ZERO:
            raise ValueError("reversal must be split close then open")
        quote = self._state.quote_cash
        collateral = self._state.isolated_collateral
        allocated = self._state.allocated_initial_margin_memo
        realized = self._state.realized_PnL
        average = self._state.average_perpetual_entry
        increasing = oldq == ZERO or oldq * quantity > ZERO
        if increasing:
            margin = abs(quantity) * price / _d(_get(self._spec, "leverage", "1"), positive=True)
            if quote < margin:
                raise ValueError("insufficient quote cash for isolated collateral")
            quote -= margin
            collateral += margin
            allocated += margin
            average = price if oldq == ZERO else ((abs(oldq) * average + abs(quantity) * price) / abs(newq))
        else:
            closed = abs(quantity)
            if closed > abs(oldq):
                raise ValueError("reduction cannot cross zero")
            pnl = closed * (ONE if oldq > ZERO else -ONE) * (price - average)
            realized += pnl
            collateral += pnl
            released_memo = allocated * closed / abs(oldq)
            allocated -= released_memo
            release = min(released_memo, max(collateral - explicit - implicit, ZERO))
            collateral -= release
            quote += release
            if newq == ZERO:
                average = None
        collateral -= explicit + implicit
        liabilities = self._state.liabilities
        if newq == ZERO:
            if collateral >= ZERO:
                quote += collateral
            else:
                liabilities += -collateral
            collateral = ZERO
            allocated = ZERO
        self._state = replace(self._state, quote_cash=quote, isolated_collateral=collateral,
                              allocated_initial_margin_memo=allocated, perpetual_quantity=newq,
                              average_perpetual_entry=average, realized_PnL=realized,
                              explicit_costs=self._state.explicit_costs + explicit,
                              implicit_costs=self._state.implicit_costs + implicit,
                              liabilities=liabilities)

    def _emit_rejection(self, instrument: str, requested: Decimal, reason: str, *,
                        severe: bool = False) -> Mapping[str, Any]:
        before = self._state
        rule = self._rule(instrument)
        step = _d(_get(rule, "step", "0.00000001"), positive=True)
        rounded = (abs(requested) / step).to_integral_value(rounding=ROUND_DOWN) * step
        rounded = rounded.copy_sign(requested)
        scenario = self._scenario(severe)
        decision_id = f"D{self._seq + 1:06d}"
        common = {"source_digest": self._current_source_digest(instrument),
                  "rules_digest": self._rules_digest()}
        self._append_row("decision", {
            "decision_id": decision_id, "decision_at": self._timestamp(),
            "available_information_cutoff": self._timestamp(), "requested_target": _ds(requested),
            "permission_or_abstention": "abstention", "reason": reason,
            "lineage_digest": _digest(self._lineage()), **common,
        }, before, before)
        self._append_row("order", {
            "order_id": f"O{self._seq + 1:06d}", "decision_id": decision_id,
            "created_at": self._timestamp(), "arrival_at": self._arrival(), "instrument": instrument,
            "requested_quantity": _ds(requested), "rounded_quantity": _ds(rounded),
            "filled_quantity": "0", "unfilled_quantity": _ds(requested), "status": "rejected",
            "reason": reason, "price_bound": None, "scenario_id": _get(scenario, "scenario_id"),
            **common,
        }, before, before)
        return _freeze(self._rows["order"][-1])

    # ---- margin, mark and episode handling ----
    def _mark(self, spot: Decimal | None, perp: Decimal | None) -> None:
        old_spot = self._state.spot_mark
        old_perp = self._state.perpetual_mark
        spot = old_spot if spot is None else spot
        perp = old_perp if perp is None else perp
        spot_pnl = self._state.spot_quantity * (spot - old_spot) if old_spot else ZERO
        perp_pnl = self._state.perpetual_quantity * (perp - old_perp) if old_perp else ZERO
        if self._episode is not None:
            self._episode.price_pnl += spot_pnl + perp_pnl
        self._state = replace(self._state, spot_mark=spot, perpetual_mark=perp)
        self._refresh()

    def _refresh(self) -> None:
        unrealized = ZERO
        if self._state.perpetual_quantity != ZERO:
            unrealized = self._state.perpetual_quantity * (
                self._state.perpetual_mark - self._state.average_perpetual_entry)
        third = sum((balance * dict(self._state.fee_asset_marks).get(asset, ZERO)
                     for asset, balance in self._state.fee_asset_balances), ZERO)
        nav = (self._state.quote_cash + self._state.spot_quantity * self._state.spot_mark + third
               + self._state.isolated_collateral + unrealized - self._state.liabilities)
        reserve_rate = _d(_get(self._margin, "exit_cost_reserve_rate", "0"))
        reserve = abs(self._state.perpetual_quantity) * self._state.perpetual_mark * reserve_rate
        self._state = replace(self._state, unrealized_PnL=unrealized,
                              exit_cost_reserve_memo=reserve, NAV=nav)

    def _margin_checkpoint(self, cause: str) -> None:
        if self._state.perpetual_quantity == ZERO or self._state.terminal:
            return
        equity = self._margin_equity()
        maintenance = abs(self._state.perpetual_quantity) * self._state.perpetual_mark * _d(
            _get(self._margin, "maintenance_fraction", "0"))
        if equity <= maintenance:
            self._liquidate(cause)

    def _liquidate(self, cause: str) -> None:
        before = self._state
        quantity = self._state.perpetual_quantity
        mark = self._state.perpetual_mark
        pnl = abs(quantity) * (ONE if quantity > ZERO else -ONE) * (
            mark - self._state.average_perpetual_entry)
        fee = abs(quantity) * mark * _d(_get(self._margin, "liquidation_fee_rate", "0"))
        settlement = self._state.isolated_collateral + pnl - fee
        quote = self._state.quote_cash + max(settlement, ZERO)
        liability = self._state.liabilities + max(-settlement, ZERO)
        self._state = replace(self._state, quote_cash=quote, perpetual_quantity=ZERO,
                              average_perpetual_entry=None, isolated_collateral=ZERO,
                              allocated_initial_margin_memo=ZERO, exit_cost_reserve_memo=ZERO,
                              liabilities=liability, realized_PnL=self._state.realized_PnL + pnl,
                              explicit_costs=self._state.explicit_costs + fee,
                              state="liquidated_invalid", invalidation_reason=f"liquidation:{cause}",
                              terminal=True, new_exposure_enabled=False, unrealized_PnL=ZERO)
        self._refresh()
        decision_id = f"D{self._seq + 1:06d}"
        common = {"source_digest": self._current_source_digest("BTCUSDT_USD_M_perpetual"),
                  "rules_digest": self._rules_digest()}
        self._append_row("decision", {
            "decision_id": decision_id, "decision_at": self._timestamp(),
            "available_information_cutoff": self._timestamp(), "requested_target": "0",
            "permission_or_abstention": "protective", "reason": f"liquidation:{cause}",
            "lineage_digest": _digest(self._lineage()), **common,
        }, before, before)
        order_id = f"O{self._seq + 1:06d}"
        self._append_row("order", {
            "order_id": order_id, "decision_id": decision_id, "created_at": self._timestamp(),
            "arrival_at": self._timestamp(), "instrument": "BTCUSDT_USD_M_perpetual",
            "requested_quantity": _ds(-quantity), "rounded_quantity": _ds(-quantity),
            "filled_quantity": _ds(-quantity), "unfilled_quantity": "0", "status": "filled",
            "reason": f"liquidation:{cause}", "price_bound": None,
            "scenario_id": "liquidation", **common,
        }, before, before)
        fill = self._append_row("fill", {
            "fill_id": f"F{self._seq + 1:06d}", "order_id": order_id,
            "fill_at": self._timestamp(), "instrument": "BTCUSDT_USD_M_perpetual",
            "signed_quantity": _ds(-quantity), "accounting_fill_price": _ds(mark),
            "explicit_fee_native": _ds(fee), "explicit_fee_asset": "USDT",
            "explicit_fee_quote_equivalent": _ds(fee), "implicit_cost_quote": "0",
            "post_fill_position": "0", **common,
        }, before, self._state, explicit=fee)
        if self._episode is not None:
            self._episode.exit_fills.append(fill["row_digest"])
            self._episode.exit_costs += fee
            self._close_episode(f"liquidation:{cause}", self._state.invalidation_reason)
        self._emit_account("liquidation", before=before)

    def _episode_fill(self, instrument: str, quantity: Decimal, before: AccountState,
                      row: Mapping[str, Any], cost: Decimal, reason: str) -> None:
        pre = before.spot_quantity if instrument == "BTC/USDT" else before.perpetual_quantity
        post = self._state.spot_quantity if instrument == "BTC/USDT" else self._state.perpetual_quantity
        digest = row["row_digest"]
        source = row["source_digest"]
        rules = row["rules_digest"]
        if self._episode is None and post != ZERO:
            direction = "spot_long" if instrument == "BTC/USDT" else (
                "perpetual_long" if post > ZERO else "perpetual_short")
            self._episode = _Episode(f"E{len(self._episodes) + 1:06d}", self._timestamp(), direction)
            self._episode.entry_costs += cost
            self._episode.entry_fills.append(digest)
        elif self._episode is not None:
            reducing = pre != ZERO and abs(post) < abs(pre)
            if reducing:
                self._episode.exit_costs += cost
                self._episode.exit_fills.append(digest)
            else:
                self._episode.entry_costs += cost
                self._episode.entry_fills.append(digest)
        if self._episode is not None:
            self._episode.sources.add(source)
            self._episode.rules.add(rules)
            if self._state.spot_quantity == ZERO and self._state.perpetual_quantity == ZERO:
                self._close_episode(reason, self._state.invalidation_reason)

    def _update_excursion(self) -> None:
        if self._episode is None:
            return
        value = self._episode.price_pnl + self._episode.funding_pnl
        self._episode.mae = min(self._episode.mae, value)
        self._episode.mfe = max(self._episode.mfe, value)

    def _close_episode(self, reason: str, invalidation: str | None) -> None:
        episode = self._episode
        if episode is None:
            return
        net = episode.price_pnl + episode.funding_pnl - episode.entry_costs - episode.exit_costs
        row = {
            "episode_id": episode.episode_id, "opened_at": episode.opened_at,
            "closed_at": self._timestamp(), "direction": episode.direction,
            "entry_costs": _ds(episode.entry_costs), "exit_costs": _ds(episode.exit_costs),
            "price_PnL": _ds(episode.price_pnl), "funding_PnL": _ds(episode.funding_pnl),
            "net_dollar_PnL": _ds(net), "maximum_adverse_excursion": _ds(episode.mae),
            "maximum_favourable_excursion": _ds(episode.mfe), "close_reason": reason,
            "entry_fill_digests": tuple(episode.entry_fills),
            "exit_fill_digests": tuple(episode.exit_fills),
            "source_digests": tuple(sorted(episode.sources)),
            "rules_digests": tuple(sorted(episode.rules)), "invalidation_reason": invalidation,
        }
        row["row_digest"] = _digest({key: value for key, value in row.items()
                                     if key != "row_digest"})
        self._episodes.append(row)
        self._episode = None

    # ---- deterministic rows/helpers ----
    def _append_row(self, ledger: str, values: Mapping[str, Any], before: AccountState,
                    after: AccountState, *, funding: Decimal = ZERO, explicit: Decimal = ZERO,
                    implicit: Decimal = ZERO) -> dict[str, Any]:
        self._seq += 1
        residual = (after.NAV - before.NAV) - funding + explicit + implicit
        fields = {"decision": DECISION_FIELDS, "order": ORDER_FIELDS, "fill": FILL_FIELDS,
                  "funding": FUNDING_FIELDS}[ledger]
        row = {key: None for key in fields}
        row.update(self._lineage())
        row.update(values)
        row.update({"event_sequence": self._seq, "before_state_digest": self._state_digest(before),
                    "after_state_digest": self._state_digest(after),
                    "event_accounting_residual": _ds(residual),
                    "invalidation_reason": after.invalidation_reason})
        row["row_digest"] = _digest({key: value for key, value in row.items()
                                     if key != "row_digest"})
        self._rows[ledger].append(row)
        self._last_digest = row["after_state_digest"]
        return row

    def _emit_account(self, label: str, *, before: AccountState | None = None) -> None:
        before = before or self._state
        self._seq += 1
        row = {key: None for key in ACCOUNT_FIELDS}
        row.update(self._lineage())
        row.update({
            "timestamp": self._timestamp(), "segment_id": self._state.segment_id,
            "quote_cash": _ds(self._state.quote_cash), "spot_quantity": _ds(self._state.spot_quantity),
            "perpetual_quantity": _ds(self._state.perpetual_quantity),
            "isolated_collateral": _ds(self._state.isolated_collateral),
            "allocated_initial_margin_memo": _ds(self._state.allocated_initial_margin_memo),
            "exit_cost_reserve_memo": _ds(self._state.exit_cost_reserve_memo),
            "fee_asset_balances": {k: _ds(v) for k, v in self._state.fee_asset_balances},
            "liabilities": _ds(self._state.liabilities), "realized_PnL": _ds(self._state.realized_PnL),
            "unrealized_PnL": _ds(self._state.unrealized_PnL), "funding": _ds(self._state.funding),
            "explicit_costs": _ds(self._state.explicit_costs),
            "implicit_costs": _ds(self._state.implicit_costs), "NAV": _ds(self._state.NAV),
            "gross_exposure": _ds(self._gross_exposure()), "net_exposure": _ds(self._net_exposure()),
            "margin_equity": _ds(self._margin_equity()),
            "maintenance_requirement": _ds(abs(self._state.perpetual_quantity)
                * self._state.perpetual_mark * _d(_get(self._margin, "maintenance_fraction", "0"))),
            "state": label if self._state.state == "active" else self._state.state,
            "source_digest": self._current_source_digest(None), "rules_digest": self._rules_digest(),
            "mark_source_digest": self._current_source_digest("BTCUSDT_USD_M_perpetual"),
            "index_source_digest": self._current_source_digest("BTCUSDT_USD_M_perpetual"),
            "event_sequence": self._seq, "before_state_digest": self._state_digest(before),
            "after_state_digest": self._state_digest(), "event_accounting_residual": "0",
            "invalidation_reason": self._state.invalidation_reason,
        })
        row["row_digest"] = _digest({key: value for key, value in row.items()
                                     if key != "row_digest"})
        self._rows["account"].append(row)

    def _lineage(self) -> dict[str, Any]:
        scenario = self._scenario(False)
        return {
            "experiment_id": EXPERIMENT_ID,
            "run_id": _get(self._spec, "run_spec_id", "unknown"),
            "scenario_id": _get(scenario, "scenario_id", _get(_get(self._spec, "execution_authority", {}), "primary_scenario_id")),
            "implementation_digest": _get(self._binding, "implementation_digest", _IMPLEMENTATION_DIGEST),
            "contract_digest": _get(self._binding, "contract_digest", "d9deacb388f46daa77fda6470b82feba13093b2bb2c4895be9c32b0caa0d1259"),
            "execution_config_digest": _get(_get(self._spec, "execution_authority", {}), "sha256"),
            "mandate_digest": _get(_get(self._spec, "selected_mandate", {}), "sha256"),
        }

    def _state_digest(self, state: AccountState | None = None) -> str:
        state = self._state if state is None else state
        return _digest({name: _plain(getattr(state, name)) for name in AccountState.__slots__})

    def _observations(self) -> list[dict[str, Mapping[str, Any]]]:
        rows = _get(self._source, "observations", None)
        if rows is None:
            rows = _get(self._source, "snapshots", ())
        grouped: dict[str, dict[str, Mapping[str, Any]]] = {}
        for row in rows:
            stamp = _get(row, "observed_at")
            grouped.setdefault(stamp, {})[_get(row, "instrument")] = row
        return [grouped[k] for k in sorted(grouped, key=_utc)]

    def _validate_group(self, group: Mapping[str, Mapping[str, Any]]) -> None:
        if not group:
            raise ValueError("empty source group")
        stamps = {_get(v, "observed_at") for v in group.values()}
        segments = {_get(v, "segment_id") for v in group.values()}
        if len(stamps) != 1 or len(segments) != 1:
            raise ValueError("source timestamp/segment mismatch")
        stamp = next(iter(stamps))
        terminal = _utc(_get(_get(self._spec, "partition", {}), "terminal_exclusive"))
        if _utc(stamp) >= terminal:
            raise ValueError("source at or beyond terminal")
        for instrument, row in group.items():
            key = (instrument, stamp)
            if key in self._seen or _utc(_get(row, "available_at")) < _utc(stamp):
                raise ValueError("duplicate or pre-arrival source")
            for field in ("open", "reference_open", "mark_open", "mark"):
                value = _get(row, field)
                if value is not None:
                    _d(value, positive=True)
            if _get(row, "adapter_status", "qualified") != "qualified":
                raise ValueError("unqualified source")
        segment = next(iter(segments))
        stamp_dt = _utc(stamp)
        crossed = self._state.segment_id is not None and segment != self._state.segment_id
        gap = self._last_timestamp is not None and (
            stamp_dt - self._last_timestamp).total_seconds() != 3600
        exposed = self._state.spot_quantity != ZERO or self._state.perpetual_quantity != ZERO
        if (crossed or gap) and exposed:
            self._state = replace(self._state, segment_id=segment, state="invalid_unknown",
                                  invalidation_reason="exposed_gap", new_exposure_enabled=False,
                                  pending_protection="gap_exit")
        elif crossed or gap:
            self._state = replace(self._state, segment_id=segment,
                                  high_water_NAV=self._state.NAV,
                                  UTC_day_start_equity=self._state.NAV, UTC_day=stamp[:10])
            self._entry_days.clear()
            self._entry_times.clear()
        else:
            self._state = replace(self._state, segment_id=segment)
        self._seen.update((instrument, stamp) for instrument in group)
        self._last_timestamp = stamp_dt

    def _open_price(self, instrument: str, optional: bool = False) -> Decimal | None:
        row = self._current.get(instrument) if self._current else None
        if row is None:
            if optional:
                return None
            raise ValueError(f"missing {instrument} observation")
        value = _get(row, "open", _get(row, "reference_open", _get(row, "mark")))
        return _d(value, positive=True)

    def _close_price(self, instrument: str, optional: bool = False) -> Decimal | None:
        row = self._current.get(instrument) if self._current else None
        if row is None:
            if optional:
                return None
            raise ValueError(f"missing {instrument} observation")
        value = _get(row, "close", _get(row, "mark", _get(row, "reference_open")))
        return _d(value, positive=True)

    def _scenario(self, severe: bool) -> Mapping[str, Any]:
        helper = getattr(_authorities, "scenario_for", None)
        if helper is not None and isinstance(self._spec, _authorities.RunSpec):
            return helper(self._spec, severe=severe)
        authority = _get(self._spec, "execution_authority", {})
        wanted = (_get(authority, "severe_scenario_id") or "candle-severe-80bps-rt-v1") if severe else _get(authority, "primary_scenario_id")
        rows = _get(self._scenarios, "scenarios", self._scenarios if isinstance(self._scenarios, (list, tuple)) else ())
        for row in rows:
            if _get(row, "scenario_id") == wanted:
                return row
        # Exact authority defaults, used only for lightweight synthetic unit bindings.
        return {"scenario_id": wanted, "taker_fee_bps": "20" if severe else "10",
                "implicit_cost_bps_per_side": "20" if severe else "5",
                "price_protection_bps": "50" if severe else "10"}

    def _require_ordinary(self, allowed: str | tuple[str, ...]) -> None:
        allowed = (allowed,) if isinstance(allowed, str) else allowed
        if _get(self._spec, "run_spec_id") not in allowed:
            raise PermissionError("operation is not authorized by selected RunSpec")
        if self._phase != 5 or self._state.terminal:
            raise RuntimeError("ordinary target is only accepted in phase 5")

    def _cadence_allows(self) -> bool:
        now = _utc(self._timestamp())
        cutoff = now.timestamp() - 7 * 24 * 60 * 60
        recent = [t for t in self._entry_times if t.timestamp() > cutoff]
        return self._timestamp()[:10] not in self._entry_days and len(recent) < 4

    def _timestamp(self) -> str:
        if not self._current:
            return _get(_get(self._spec, "partition", {}), "start_inclusive")
        return _get(next(iter(self._current.values())), "observed_at")

    def _arrival(self) -> str:
        if not self._current:
            return self._timestamp()
        return _get(next(iter(self._current.values())), "available_at", self._timestamp())

    def _rules_digest(self) -> str:
        return _get(_get(self._spec, "rules", {}), "sha256", _digest(self._rules))

    def _source_digest(self, row: Mapping[str, Any] | None) -> str:
        return _digest(row) if row else "not_applicable"

    def _current_source_digest(self, instrument: str | None) -> str:
        if not self._current:
            return "not_applicable"
        if instrument is not None:
            return self._source_digest(self._current.get(instrument))
        return _digest(self._current)

    def _price_bound(self, price: Decimal, scenario: Mapping[str, Any]) -> str:
        bps = _d(_get(scenario, "price_protection_bps", "0")) / TEN_THOUSAND
        return _ds(price * (ONE + bps))

    def _gross_exposure(self) -> Decimal:
        return self._state.spot_quantity * self._state.spot_mark + abs(self._state.perpetual_quantity) * self._state.perpetual_mark

    def _net_exposure(self) -> Decimal:
        return self._state.spot_quantity * self._state.spot_mark + self._state.perpetual_quantity * self._state.perpetual_mark

    def _margin_equity(self) -> Decimal:
        return self._state.isolated_collateral + self._state.unrealized_PnL - self._state.exit_cost_reserve_memo


def _create_ledger(binding: Any) -> _LedgerEngine:
    """Package-private constructor used by the verified facade factory."""
    return _LedgerEngine(binding)


__all__ = ["AccountState", "PHASES"]
