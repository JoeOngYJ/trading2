"""Frozen E1-v11 synthetic BTC accounting state machine.

This module is deliberately offline.  It owns its authority paths, parses economic
values as :class:`Decimal`, and exposes no generic fill/funding/phase mutation API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from hashlib import sha256
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping


ZERO = Decimal("0")
ONE = Decimal("1")
BPS = Decimal("10000")
RESIDUAL_QUANTUM = Decimal("0.00000001")
EXPERIMENT_ID = "btc-unified-backtest-engine-e1-v11"
ACTIONABLE_ARM_ID = "no_trade"
SPOT = "BTC/USDT"
PERP = "BTCUSDT_USD_M_perpetual"
PHASE_NAMES = MappingProxyType({
    1: "validate_and_snapshot", 2: "opening_marks_and_liquidation",
    3: "precaused_protection", 4: "funding_and_liquidation",
    5: "risk_permissions", 6: "ordinary_execution", 7: "post_fill_checkpoint",
    8: "intrabar_and_close", 9: "reconcile_and_emit",
})

DECISION_FIELDS = frozenset("decision_id decision_at available_information_cutoff requested_target permission_or_abstention reason source_digest rules_digest lineage_digest event_sequence before_state_digest after_state_digest event_accounting_residual invalidation_reason row_digest".split())
ORDER_FIELDS = frozenset("order_id decision_id created_at arrival_at instrument requested_quantity rounded_quantity filled_quantity unfilled_quantity status reason price_bound scenario_id source_digest rules_digest event_sequence before_state_digest after_state_digest event_accounting_residual invalidation_reason row_digest".split())
FILL_FIELDS = frozenset("fill_id order_id fill_at instrument signed_quantity accounting_fill_price explicit_fee_native explicit_fee_asset explicit_fee_quote_equivalent implicit_cost_quote post_fill_position rules_digest source_digest event_sequence before_state_digest after_state_digest event_accounting_residual invalidation_reason row_digest".split())
FUNDING_FIELDS = frozenset("funding_at t_minus_signed_quantity funding_rate funding_mark cashflow_quote economic_at available_at mark_source_digest index_source_digest rules_digest source_digest event_sequence before_state_digest after_state_digest event_accounting_residual invalidation_reason row_digest".split())
ACCOUNT_FIELDS = frozenset("timestamp segment_id quote_cash spot_quantity perpetual_quantity isolated_collateral allocated_initial_margin_memo exit_cost_reserve_memo fee_asset_balances liabilities realized_PnL unrealized_PnL funding explicit_costs implicit_costs NAV gross_exposure net_exposure margin_equity maintenance_requirement state source_digest rules_digest mark_source_digest index_source_digest event_sequence before_state_digest after_state_digest event_accounting_residual invalidation_reason row_digest".split())
EPISODE_FIELDS = frozenset("episode_id opened_at closed_at direction entry_costs exit_costs price_PnL funding_PnL net_dollar_PnL maximum_adverse_excursion maximum_favourable_excursion close_reason entry_fill_digests exit_fill_digests source_digests rules_digests invalidation_reason row_digest".split())


class ContractViolation(ValueError):
    """A fail-closed contract rejection."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractViolation("duplicate JSON key")
        out[key] = value
    return out


def strict_json(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"), parse_float=Decimal,
                          parse_int=int, parse_constant=lambda _: (_ for _ in ()).throw(ContractViolation("nonfinite JSON")),
                          object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractViolation("invalid JSON") from exc


def decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ContractViolation("binary float/boolean is not economic Decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractViolation("invalid decimal") from exc
    if not result.is_finite():
        raise ContractViolation("nonfinite decimal")
    return result


def decimal_text(value: Decimal) -> str:
    value = decimal(value)
    if value == ZERO:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float):
        raise ContractViolation("float serialization forbidden")
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def utc_text(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value):
        raise ContractViolation("timestamp must be canonical UTC")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != timezone.utc:
        raise ContractViolation("timestamp must be UTC")
    return value


def _time_key(value: str) -> datetime:
    utc_text(value)
    return datetime.fromisoformat(value[:-1] + "+00:00")


def quantize_down(value: Decimal, step: Decimal) -> Decimal:
    value, step = decimal(value), decimal(step)
    if step <= ZERO:
        raise ContractViolation("invalid step")
    sign = ONE if value >= ZERO else -ONE
    return sign * ((abs(value) / step).to_integral_value(rounding=ROUND_DOWN) * step)


@dataclass(frozen=True)
class Rules:
    tick: Decimal
    step: Decimal
    minimum_notional: Decimal
    maximum_quantity: Decimal
    digest: str

    def quantity(self, requested: Decimal, price: Decimal) -> Decimal:
        q = quantize_down(requested, self.step)
        if abs(q) > self.maximum_quantity or abs(q) * price < self.minimum_notional:
            raise ContractViolation("quantity/notional rule")
        return q

    def price(self, price: Decimal) -> Decimal:
        p = decimal(price)
        if p <= ZERO or quantize_down(p, self.tick) != p:
            raise ContractViolation("price tick")
        return p


@dataclass(frozen=True)
class DepthOutcome:
    instrument: str
    side: str
    quantity: Decimal
    vwap: Decimal
    explicit_cost: Decimal
    implicit_cost: Decimal
    source_digest: str
    key: str


@dataclass(frozen=True)
class DepthOutcomeUniverse:
    outcomes: tuple[DepthOutcome, ...]
    set_digest: str


class AuthorityVerifiedFactory:
    """The sole constructor.  Every path is fixed by this implementation identity."""

    _TOKEN = object()
    _ROOT = Path(__file__).resolve().parents[2]
    _CANDIDATE = _ROOT / "research/btc/candidates/unified-backtest-engine-e1-v11"
    _MANIFEST = _CANDIDATE / "candidate-manifest.json"
    _EXPECTED = MappingProxyType({
        "active_module": "src/trading_platform/btc_accounting_state_machine_e1_v11.py",
        "active_test": "research/btc/tests/test_btc_accounting_state_machine_e1_v11.py",
        "snapshot_module": "research/btc/candidates/unified-backtest-engine-e1-v11/btc_accounting_state_machine_e1_v11.py",
        "snapshot_test": "research/btc/candidates/unified-backtest-engine-e1-v11/test_btc_accounting_state_machine_e1_v11.py",
        "V11_contract": "research/btc/contracts/btc-unified-backtest-engine-e1-v11-identity.json",
        "execution_configuration": "config/execution_scenarios.json",
        "spot_mandate": "config/retail_mandate.json",
        "directional_mandate": "config/mandates/retail-btc-directional-perpetual-research-v1.json",
        "pair_mandate": "config/mandates/retail-btc-delta-neutral-research-v1.json",
        "instrument_rules": "research/btc/candidates/unified-backtest-engine-e1-v11/instrument-rules.json",
        "margin_rules": "research/btc/candidates/unified-backtest-engine-e1-v11/margin-rules.json",
        "source_evidence": "research/btc/candidates/unified-backtest-engine-e1-v11/source-evidence.json",
        "semantic_run_settings": "research/btc/candidates/unified-backtest-engine-e1-v11/semantic-settings.json",
    })

    @classmethod
    def create(cls) -> "AccountingStateMachine":
        manifest_raw = cls._MANIFEST.read_bytes()
        manifest = strict_json(manifest_raw)
        if manifest.get("experiment_id") != EXPERIMENT_ID or manifest.get("actionable_arm_id") != ACTIONABLE_ARM_ID:
            raise ContractViolation("wrong manifest identity")
        utc_text(manifest.get("UTC_creation_timestamp"))
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            raise ContractViolation("manifest entries")
        by_role: dict[str, Mapping[str, Any]] = {}
        for entry in entries:
            if set(entry) != {"path", "sha256", "size_bytes", "semantic_role"}:
                raise ContractViolation("manifest field set")
            role = entry["semantic_role"]
            if role in by_role:
                raise ContractViolation("duplicate manifest role")
            by_role[role] = entry
        if set(by_role) != set(cls._EXPECTED):
            raise ContractViolation("manifest role set")
        loaded: dict[str, bytes] = {}
        for role, expected_path in cls._EXPECTED.items():
            entry = by_role[role]
            if entry["path"] != expected_path:
                raise ContractViolation("manifest path override")
            raw = (cls._ROOT / expected_path).read_bytes()
            if len(raw) != entry["size_bytes"] or sha256(raw).hexdigest() != entry["sha256"]:
                raise ContractViolation("authority bytes changed")
            loaded[role] = raw
        if loaded["active_module"] != loaded["snapshot_module"] or loaded["active_test"] != loaded["snapshot_test"]:
            raise ContractViolation("active snapshot mismatch")
        contract = strict_json(loaded["V11_contract"])
        execution = strict_json(loaded["execution_configuration"])
        settings = strict_json(loaded["semantic_run_settings"])
        selected_role = settings.get("selected_mandate_role")
        if selected_role not in {"spot_mandate", "directional_mandate", "pair_mandate"}:
            raise ContractViolation("unbound mandate")
        selected_mandate = strict_json(loaded[selected_role])
        scenarios = {row["scenario_id"]: row for row in execution["scenarios"]}
        scenario_id = settings.get("scenario_id")
        if scenario_id not in scenarios or scenario_id == "candle-fees-only-diagnostic-v1":
            raise ContractViolation("unauthorized scenario")
        rules_raw = strict_json(loaded["instrument_rules"])
        margin = strict_json(loaded["margin_rules"])
        source = strict_json(loaded["source_evidence"])
        bindings = MappingProxyType({role: sha256(raw).hexdigest() for role, raw in loaded.items()})
        return AccountingStateMachine(cls._TOKEN, bindings, contract, scenarios[scenario_id],
                                      selected_mandate, rules_raw, margin, source, settings)


class AccountingStateMachine:
    __slots__ = ("_bindings", "_contract", "_scenario", "_mandate", "_rules", "_margin",
                 "_source", "_settings", "_phase", "_clock", "_segment", "_terminal",
                 "_liquidated", "_sticky_invalid", "_pending", "_last_id", "_sequence",
                 "_last_after", "_state", "rows", "episodes", "_episode", "_incoming_perp",
                 "_risk_increase_allowed", "_rolling", "_locked")

    def __init__(self, token: object, bindings: Mapping[str, str], contract: Mapping[str, Any],
                 scenario: Mapping[str, Any], mandate: Mapping[str, Any], rules: Mapping[str, Any],
                 margin: Mapping[str, Any], source: Mapping[str, Any], settings: Mapping[str, Any]):
        if token is not AuthorityVerifiedFactory._TOKEN:
            raise ContractViolation("factory-only construction")
        object.__setattr__(self, "_locked", False)
        object.__setattr__(self, "_bindings", bindings)
        object.__setattr__(self, "_contract", _freeze(contract))
        object.__setattr__(self, "_scenario", _freeze(scenario))
        object.__setattr__(self, "_mandate", _freeze(mandate))
        object.__setattr__(self, "_margin", _freeze(margin))
        object.__setattr__(self, "_source", _freeze(source))
        object.__setattr__(self, "_settings", _freeze(settings))
        parsed_rules = {}
        for instrument, row in rules["instruments"].items():
            parsed_rules[instrument] = Rules(decimal(row["tick"]), decimal(row["step"]),
                                             decimal(row["minimum_notional"]), decimal(row["maximum_quantity"]),
                                             digest(row))
        object.__setattr__(self, "_rules", MappingProxyType(parsed_rules))
        object.__setattr__(self, "_phase", 0)
        object.__setattr__(self, "_clock", None)
        object.__setattr__(self, "_segment", None)
        object.__setattr__(self, "_terminal", False)
        object.__setattr__(self, "_liquidated", False)
        object.__setattr__(self, "_sticky_invalid", False)
        object.__setattr__(self, "_pending", None)
        object.__setattr__(self, "_last_id", 0)
        object.__setattr__(self, "_sequence", 0)
        initial = decimal(settings["initial_NAV"])
        object.__setattr__(self, "_last_after", digest({"initial_NAV": initial}))
        object.__setattr__(self, "_state", {
            "quote_cash": initial, "spot_quantity": ZERO, "perpetual_quantity": ZERO,
            "average_perpetual_entry": None, "isolated_collateral": ZERO,
            "allocated_initial_margin_memo": ZERO, "exit_cost_reserve_memo": ZERO,
            "fee_asset_balances": {}, "liabilities": ZERO, "realized_PnL": ZERO,
            "unrealized_PnL": ZERO, "funding": ZERO, "explicit_costs": ZERO,
            "implicit_costs": ZERO, "spot_mark": ZERO, "perpetual_mark": ZERO,
            "NAV": initial, "high_water": initial, "UTC_day_start": initial,
            "state": "valid", "invalidation_reason": None,
        })
        object.__setattr__(self, "rows", {name: [] for name in ("decision", "order", "fill", "funding", "account")})
        object.__setattr__(self, "episodes", [])
        object.__setattr__(self, "_episode", None)
        object.__setattr__(self, "_incoming_perp", ZERO)
        object.__setattr__(self, "_risk_increase_allowed", True)
        object.__setattr__(self, "_rolling", [])
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_locked", False) and name in {"_bindings", "_contract", "_scenario", "_mandate", "_rules", "_margin", "_source", "_settings", "_phase", "_clock", "_segment"}:
            raise ContractViolation("engine-owned immutable binding/clock/phase")
        object.__setattr__(self, name, value)

    @property
    def phase(self) -> int:
        return self._phase

    @property
    def bindings(self) -> Mapping[str, str]:
        return self._bindings

    @property
    def state(self) -> Mapping[str, Any]:
        """Read-only recursive view of the current economic state."""
        return _freeze(self._state)

    def _set(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)

    def snapshot_digest(self) -> str:
        return digest({k: v for k, v in self._state.items() if k not in {"high_water", "UTC_day_start"}})

    def _guard(self, phase: int) -> None:
        if self._phase != phase or self._terminal or self._liquidated:
            raise ContractViolation("wrong phase or terminal state")

    def _next_id(self, supplied: int | None = None) -> int:
        candidate = self._last_id + 1 if supplied is None else supplied
        if not isinstance(candidate, int) or candidate <= self._last_id:
            raise ContractViolation("duplicate/regressing ID")
        self._set("_last_id", candidate)
        return candidate

    def _emit(self, ledger: str, row: dict[str, Any], before: str | None = None) -> dict[str, Any]:
        self._set("_sequence", self._sequence + 1)
        row["event_sequence"] = self._sequence
        row["before_state_digest"] = self._last_after if before is None else before
        row["after_state_digest"] = self.snapshot_digest()
        row["event_accounting_residual"] = "0"
        row.setdefault("invalidation_reason", self._state["invalidation_reason"])
        row["row_digest"] = digest(row)
        self._set("_last_after", row["after_state_digest"])
        self.rows[ledger].append(row)
        return row

    def _authority_source(self, instrument: str, timestamp: str) -> Mapping[str, Any]:
        matches = [r for r in self._source["observations"] if r["instrument"] == instrument and r["timestamp"] == timestamp]
        if len(matches) != 1:
            raise ContractViolation("missing/duplicate source observation")
        row = matches[0]
        if digest({k: v for k, v in row.items() if k != "row_digest"}) != row["row_digest"]:
            raise ContractViolation("source digest")
        return row

    def open_interval(self, timestamp: str, segment_id: str, funding_rate: Decimal = ZERO,
                      economic_at: str | None = None, available_at: str | None = None,
                      terminal: bool = False) -> None:
        """Advance engine-owned phases 1 through 6 for one qualified interval."""
        self._begin_interval(timestamp, segment_id, terminal)
        self._protection_phase()
        self._funding_phase(funding_rate, economic_at, available_at)
        self._risk_phase()
        self._execution_phase()

    def _begin_interval(self, timestamp: str, segment_id: str, terminal: bool = False) -> None:
        if self._phase not in {0, 9} or self._terminal or self._liquidated:
            raise ContractViolation("interval order")
        if terminal and self._pending:
            raise ContractViolation("pending safety cannot cross terminal boundary")
        current = _time_key(timestamp)
        if self._clock is not None and current <= _time_key(self._clock):
            raise ContractViolation("duplicate/regressing time")
        if self._segment is not None and segment_id != self._segment and not self._pending:
            raise ContractViolation("ordinary segment crossing")
        self._set("_clock", timestamp)
        self._set("_segment", segment_id)
        self._set("_terminal", bool(terminal))
        self._set("_phase", 1)
        self._set("_incoming_perp", self._state["perpetual_quantity"])
        self._set("_phase", 2)
        spot = self._authority_source(SPOT, timestamp)
        perp = self._authority_source(PERP, timestamp)
        self._state["spot_mark"] = decimal(spot["open"])
        self._state["perpetual_mark"] = decimal(perp["open"])
        self._refresh()
        self._liquidation_checkpoint("opening", decimal(perp["open"]), perp["row_digest"])

    def _protection_phase(self) -> None:
        self._guard(2)
        self._set("_phase", 3)
        if self._pending and self._pending["caused_before"] < self._clock:
            self._execute_pending()

    def _funding_phase(self, funding_rate: Decimal = ZERO, economic_at: str | None = None,
                      available_at: str | None = None) -> None:
        self._guard(3)
        self._set("_phase", 4)
        rate = decimal(funding_rate)
        if rate != ZERO:
            economic = utc_text(economic_at or self._clock)
            available = utc_text(available_at or self._clock)
            if _time_key(available) > _time_key(self._clock):
                raise ContractViolation("future funding")
            mark = self._state["perpetual_mark"]
            cashflow = -self._incoming_perp * mark * rate
            if self._state["perpetual_quantity"] == ZERO:
                self._state["quote_cash"] += cashflow
            else:
                self._state["isolated_collateral"] += cashflow
            if self._state["isolated_collateral"] < ZERO:
                self._state["liabilities"] += -self._state["isolated_collateral"]
                self._state["isolated_collateral"] = ZERO
            self._state["funding"] += cashflow
            self._refresh()
            source = self._authority_source(PERP, self._clock)
            row = {"funding_at": self._clock, "t_minus_signed_quantity": decimal_text(self._incoming_perp),
                   "funding_rate": decimal_text(rate), "funding_mark": decimal_text(mark),
                   "cashflow_quote": decimal_text(cashflow), "economic_at": economic, "available_at": available,
                   "mark_source_digest": source["row_digest"], "index_source_digest": self._source["index_digest"],
                   "rules_digest": self._rules[PERP].digest, "source_digest": source["row_digest"]}
            self._emit("funding", row)
            self._liquidation_checkpoint("funding", mark, source["row_digest"])

    def _risk_phase(self) -> bool:
        self._guard(4)
        self._set("_phase", 5)
        nav = self._state["NAV"]
        daily = nav / self._state["UTC_day_start"] - ONE
        drawdown = nav / self._state["high_water"] - ONE
        self._set("_risk_increase_allowed", daily > Decimal("-0.015") and drawdown > Decimal("-0.10") and not self._sticky_invalid)
        return self._risk_increase_allowed

    def _execution_phase(self) -> None:
        self._guard(5)
        self._set("_phase", 6)

    def _cost_rates(self, severe: bool = False) -> tuple[Decimal, Decimal]:
        scenario = self._scenario
        if severe:
            scenarios = strict_json((AuthorityVerifiedFactory._ROOT / "config/execution_scenarios.json").read_bytes())["scenarios"]
            scenario = next(r for r in scenarios if r["scenario_id"] == "candle-severe-80bps-rt-v1")
        return decimal(scenario["taker_fee_bps"]) / BPS, decimal(scenario["implicit_cost_bps_per_side"]) / BPS

    def _preflight(self, instrument: str, signed_quantity: Decimal, price: Decimal, increasing: bool, severe: bool = False) -> tuple[Decimal, Decimal, Decimal]:
        if instrument not in self._rules:
            raise ContractViolation("wrong instrument")
        price = self._rules[instrument].price(decimal(price))
        quantity = self._rules[instrument].quantity(decimal(signed_quantity), price)
        if quantity == ZERO:
            raise ContractViolation("zero fill")
        if increasing and (not self._risk_increase_allowed or self._terminal):
            raise ContractViolation("increase disabled")
        fee_rate, implicit_rate = self._cost_rates(severe)
        fee, implicit = abs(quantity) * price * fee_rate, abs(quantity) * price * implicit_rate
        if fee_rate == ZERO and not self._settings.get("zero_fee_fixture", False):
            raise ContractViolation("unauthorized zero fee")
        return quantity, fee, implicit

    def _check_cap(self, instrument: str, resulting_quantity: Decimal, price: Decimal) -> None:
        nav = self._state["NAV"]
        if self._mandate["mandate_id"] == "retail-btc-delta-neutral-research-v1":
            cap = Decimal("0.5")
        else:
            cap = Decimal("0.25")
        if abs(resulting_quantity) * price > nav * cap:
            raise ContractViolation("exposure cap")

    def _fill(self, decision_id: str, instrument: str, signed_quantity: Decimal, price: Decimal,
              reason: str, severe: bool = False, source_digest: str | None = None,
              allow_partial: bool = False) -> dict[str, Any]:
        self._guard(6)
        increasing = (instrument == SPOT and signed_quantity > ZERO) or (
            instrument == PERP and abs(self._state["perpetual_quantity"] + signed_quantity) > abs(self._state["perpetual_quantity"]))
        quantity, fee, implicit = self._preflight(instrument, signed_quantity, price, increasing, severe)
        current = self._state["spot_quantity"] if instrument == SPOT else self._state["perpetual_quantity"]
        resulting = current + quantity
        if increasing:
            self._check_cap(instrument, resulting, price)
            if current != ZERO and not self._mandate.get("pyramiding_allowed", False):
                raise ContractViolation("pyramiding")
        if instrument == SPOT and resulting < ZERO:
            raise ContractViolation("spot borrowing")
        if instrument == PERP and current != ZERO and resulting != ZERO and current * resulting < ZERO:
            raise ContractViolation("reversal requires close then open")
        before = self.snapshot_digest()
        oid = f"O{self._next_id():06d}"
        fid = f"F{self._next_id():06d}"
        source = source_digest or self._authority_source(instrument, self._clock)["row_digest"]
        order = {"order_id": oid, "decision_id": decision_id, "created_at": self._clock, "arrival_at": self._clock,
                 "instrument": instrument, "requested_quantity": decimal_text(signed_quantity),
                 "rounded_quantity": decimal_text(quantity), "filled_quantity": decimal_text(quantity),
                 "unfilled_quantity": "0", "status": "filled", "reason": reason,
                 "price_bound": decimal_text(price), "scenario_id": self._scenario["scenario_id"],
                 "source_digest": source, "rules_digest": self._rules[instrument].digest}
        self._emit("order", order, before)
        if instrument == SPOT:
            self._state["quote_cash"] -= quantity * price
            self._state["spot_quantity"] += quantity
            self._state["quote_cash"] -= fee + implicit
        else:
            old = self._state["perpetual_quantity"]
            avg = self._state["average_perpetual_entry"]
            if increasing:
                margin = abs(quantity) * price / decimal(self._settings["leverage"])
                if self._state["quote_cash"] < margin:
                    raise ContractViolation("insufficient collateral")
                self._state["quote_cash"] -= margin
                self._state["isolated_collateral"] += margin
                self._state["allocated_initial_margin_memo"] += margin
                new = old + quantity
                self._state["average_perpetual_entry"] = price if old == ZERO else (abs(old) * avg + abs(quantity) * price) / abs(new)
                self._state["perpetual_quantity"] = new
            else:
                closed = abs(quantity)
                pnl = closed * (ONE if old > ZERO else -ONE) * (price - avg)
                self._state["isolated_collateral"] += pnl
                self._state["realized_PnL"] += pnl
                old_im = self._state["allocated_initial_margin_memo"]
                release_memo = old_im * closed / abs(old)
                self._state["allocated_initial_margin_memo"] -= release_memo
                self._state["perpetual_quantity"] = old + quantity
                self._state["isolated_collateral"] -= fee + implicit
                release = min(release_memo, max(self._state["isolated_collateral"], ZERO))
                self._state["isolated_collateral"] -= release
                self._state["quote_cash"] += release
                if self._state["perpetual_quantity"] == ZERO:
                    if self._state["isolated_collateral"] < ZERO:
                        self._state["liabilities"] += -self._state["isolated_collateral"]
                    else:
                        self._state["quote_cash"] += self._state["isolated_collateral"]
                    self._state["isolated_collateral"] = ZERO
                    self._state["allocated_initial_margin_memo"] = ZERO
                    self._state["average_perpetual_entry"] = None
            if increasing:
                self._state["isolated_collateral"] -= fee + implicit
        self._state["explicit_costs"] += fee
        self._state["implicit_costs"] += implicit
        self._refresh()
        fill = {"fill_id": fid, "order_id": oid, "fill_at": self._clock, "instrument": instrument,
                "signed_quantity": decimal_text(quantity), "accounting_fill_price": decimal_text(price),
                "explicit_fee_native": decimal_text(fee), "explicit_fee_asset": "USDT",
                "explicit_fee_quote_equivalent": decimal_text(fee), "implicit_cost_quote": decimal_text(implicit),
                "post_fill_position": decimal_text(self._state["spot_quantity"] if instrument == SPOT else self._state["perpetual_quantity"]),
                "rules_digest": self._rules[instrument].digest, "source_digest": source}
        self._emit("fill", fill)
        self._liquidation_checkpoint("fill", price, source)
        return fill

    def _decision(self, target: str, permission: str = "permitted", reason: str = "eligible") -> str:
        self._guard(6)
        source = self._authority_source(SPOT, self._clock)["row_digest"]
        did = f"D{self._next_id():06d}"
        row = {"decision_id": did, "decision_at": self._clock, "available_information_cutoff": self._clock,
               "requested_target": target, "permission_or_abstention": permission, "reason": reason,
               "source_digest": source, "rules_digest": self._rules[SPOT].digest,
               "lineage_digest": digest(self._bindings)}
        self._emit("decision", row)
        return did

    def spot_order(self, target_quantity: Decimal) -> None:
        self._guard(6)
        if self._mandate["mandate_id"] != "retail-btc-spot-v2":
            raise ContractViolation("spot operation unauthorized")
        target = decimal(target_quantity)
        delta = target - self._state["spot_quantity"]
        did = self._decision("spot:" + decimal_text(target))
        price = decimal(self._authority_source(SPOT, self._clock)["open"])
        self._fill(did, SPOT, delta, price, "ordinary_spot")

    def directional_perpetual_order(self, target_quantity: Decimal) -> None:
        self._guard(6)
        if self._mandate["mandate_id"] != "retail-btc-directional-perpetual-research-v1":
            raise ContractViolation("perpetual operation unauthorized")
        target = decimal(target_quantity)
        current = self._state["perpetual_quantity"]
        did = self._decision("perpetual:" + decimal_text(target))
        price = decimal(self._authority_source(PERP, self._clock)["open"])
        if current != ZERO and target != ZERO and current * target < ZERO:
            self._fill(did, PERP, -current, price, "reversal_close")
            if target != ZERO:
                self._fill(did, PERP, target, price, "reversal_open")
        else:
            self._fill(did, PERP, target - current, price, "ordinary_perpetual")

    def derive_depth_outcome_universe(self, instrument: str, side: str, maximum_quantity: Decimal,
                                      severe: bool = False) -> DepthOutcomeUniverse:
        if instrument not in self._rules or side not in {"buy", "sell"}:
            raise ContractViolation("depth request")
        source = self._authority_source(instrument, self._clock)
        levels = source.get("asks" if side == "buy" else "bids")
        if not isinstance(levels, (list, tuple)) or not levels:
            raise ContractViolation("incomplete depth")
        seen = set()
        cumulative_q = ZERO
        cumulative_n = ZERO
        outcomes = []
        limit = quantize_down(decimal(maximum_quantity), self._rules[instrument].step)
        for level in levels:
            if set(level) != {"price", "quantity"}:
                raise ContractViolation("depth key collision")
            price = self._rules[instrument].price(decimal(level["price"]))
            quantity = quantize_down(decimal(level["quantity"]), self._rules[instrument].step)
            if quantity <= ZERO or (price, quantity) in seen:
                raise ContractViolation("duplicate/invalid depth")
            seen.add((price, quantity))
            available = min(quantity, limit - cumulative_q)
            if available <= ZERO:
                break
            steps = int((available / self._rules[instrument].step).to_integral_value(rounding=ROUND_DOWN))
            for _ in range(steps):
                cumulative_q += self._rules[instrument].step
                cumulative_n += self._rules[instrument].step * price
                if cumulative_q * price < self._rules[instrument].minimum_notional:
                    continue
                vwap = cumulative_n / cumulative_q
                fee_rate, implicit_rate = self._cost_rates(severe)
                explicit, implicit = cumulative_n * fee_rate, cumulative_n * implicit_rate
                key = digest({"instrument": instrument, "side": side, "quantity": cumulative_q, "vwap": vwap,
                              "explicit": explicit, "implicit": implicit, "source": source["row_digest"]})
                outcomes.append(DepthOutcome(instrument, side, cumulative_q, vwap, explicit, implicit, source["row_digest"], key))
            if cumulative_q == limit:
                break
        if not outcomes or outcomes[-1].quantity != limit:
            raise ContractViolation("insufficient protected depth")
        ordered = tuple(sorted(outcomes, key=lambda x: (x.quantity, x.vwap, x.key)))
        return DepthOutcomeUniverse(ordered, digest([o.__dict__ for o in ordered]))

    def atomic_pair_entry(self, quantity: Decimal) -> None:
        self._guard(6)
        if self._mandate["mandate_id"] != "retail-btc-delta-neutral-research-v1" or self._state["spot_quantity"] != ZERO or self._state["perpetual_quantity"] != ZERO:
            raise ContractViolation("pair entry authority/state")
        q = decimal(quantity)
        spot_src, perp_src = self._authority_source(SPOT, self._clock), self._authority_source(PERP, self._clock)
        spot_price, perp_price = decimal(spot_src["open"]), decimal(perp_src["open"])
        # All intended and severe recovery paths are proven before the first commit.
        spot_q, _, _ = self._preflight(SPOT, q, spot_price, True)
        self._preflight(PERP, -spot_q, perp_price, True)
        severe_spot = decimal(spot_src["severe_sell"])
        severe_perp = decimal(perp_src["severe_buy"])
        self._preflight(SPOT, -spot_q, severe_spot, False, True)
        self._preflight(PERP, spot_q, severe_perp, False, True)
        self._check_cap(SPOT, spot_q, spot_price)
        self._check_cap(PERP, -spot_q, perp_price)
        did = self._decision("matched_pair:" + decimal_text(spot_q))
        self._fill(did, SPOT, spot_q, spot_price, "pair_entry_spot")
        mode = perp_src.get("entry_fill_mode", "full")
        if mode == "full":
            self._fill(did, PERP, -spot_q, perp_price, "pair_entry_perpetual")
            self._open_episode("matched_pair", [r["row_digest"] for r in self.rows["fill"][-2:]])
            return
        self._set("_sticky_invalid", True)
        self._state["state"] = "invalid_unknown"
        self._state["invalidation_reason"] = "pair_entry_second_leg_failure"
        if mode == "partial":
            partial = quantize_down(spot_q / Decimal("2"), self._rules[PERP].step)
            self._fill(did, PERP, -partial, perp_price, "pair_entry_perpetual_partial")
            self._fill(did, PERP, partial, severe_perp, "pair_entry_recover_perpetual", True)
        elif mode != "zero":
            raise ContractViolation("unknown second leg outcome")
        self._fill(did, SPOT, -self._state["spot_quantity"], severe_spot, "pair_entry_recover_spot", True)

    def _cartesian_preflight(self, quantity: Decimal) -> DepthOutcomeUniverse:
        spot_u = self.derive_depth_outcome_universe(SPOT, "sell", quantity)
        keys = []
        for result in spot_u.outcomes:
            perp_u = self.derive_depth_outcome_universe(PERP, "buy", result.quantity)
            for q in (ZERO,) + tuple(o.quantity for o in perp_u.outcomes):
                residual = result.quantity - q
                if residual < ZERO:
                    raise ContractViolation("invalid Cartesian residual")
                if residual > ZERO:
                    self._preflight(PERP, residual, decimal(self._authority_source(PERP, self._clock)["severe_buy"]), False, True)
                keys.append(digest({"R": result.key, "q": q, "residual": residual}))
        return DepthOutcomeUniverse(spot_u.outcomes, digest(sorted(keys)))

    def atomic_pair_close(self) -> None:
        self._guard(6)
        if self._mandate["mandate_id"] != "retail-btc-delta-neutral-research-v1" or self._state["spot_quantity"] <= ZERO or self._state["perpetual_quantity"] >= ZERO:
            raise ContractViolation("pair close authority/state")
        quantity = self._state["spot_quantity"]
        self._cartesian_preflight(quantity)
        spot_src, perp_src = self._authority_source(SPOT, self._clock), self._authority_source(PERP, self._clock)
        did = self._decision("pair_flat")
        self._fill(did, SPOT, -quantity, decimal(spot_src["open"]), "pair_close_spot")
        mode = perp_src.get("close_fill_mode", "full")
        intended = min(quantity, abs(self._state["perpetual_quantity"]))
        if mode == "full":
            filled = intended
        elif mode == "partial":
            filled = quantize_down(intended / Decimal("2"), self._rules[PERP].step)
        elif mode in {"zero", "delayed"}:
            filled = ZERO
        else:
            raise ContractViolation("unknown close mode")
        if filled > ZERO:
            self._fill(did, PERP, filled, decimal(perp_src["open"]), "pair_close_perpetual")
        residual = quantity - filled
        if residual > ZERO:
            if mode == "delayed":
                self._set("_sticky_invalid", True)
                self._state["state"] = "invalid_unknown"
                self._state["invalidation_reason"] = "pending_pair_close_safety"
                self._set("_pending", {"quantity": residual, "caused_before": self._clock,
                                       "source_digest": perp_src["row_digest"], "decision_id": did, "attempts": 0})
                return
            self._fill(did, PERP, residual, decimal(perp_src["severe_buy"]), "pair_close_severe_residual", True)
        if self._state["spot_quantity"] != ZERO or self._state["perpetual_quantity"] != ZERO:
            # One finite non-recursive whole-pair mismatch attempt.
            if self._state["spot_quantity"] > ZERO:
                self._fill(did, SPOT, -self._state["spot_quantity"], decimal(spot_src["severe_sell"]), "whole_pair_severe_spot", True)
            if self._state["perpetual_quantity"] < ZERO:
                self._fill(did, PERP, -self._state["perpetual_quantity"], decimal(perp_src["severe_buy"]), "whole_pair_severe_perpetual", True)
        if self._state["spot_quantity"] != ZERO or self._state["perpetual_quantity"] != ZERO:
            self._set("_sticky_invalid", True)
            self._state["state"] = "invalid_unknown"
        self._close_episode("ordinary_pair_close")

    def _execute_pending(self) -> None:
        pending = self._pending
        if pending["attempts"] != 0:
            raise ContractViolation("second delayed attempt")
        perp_src = self._authority_source(PERP, self._clock)
        if self._terminal:
            raise ContractViolation("pending safety beyond boundary")
        pending["attempts"] = 1
        self._set("_phase", 6)
        self._fill(pending["decision_id"], PERP, pending["quantity"], decimal(perp_src["severe_buy"]),
                   "delayed_segment_safety", True, perp_src["row_digest"])
        self._set("_pending", None)
        self._rolling.clear()
        self._set("_phase", 3)

    def gap_cleanup(self, new_timestamp: str, new_segment: str) -> None:
        if self._phase not in {0, 9} or (self._state["spot_quantity"] == ZERO and self._state["perpetual_quantity"] == ZERO):
            raise ContractViolation("gap cleanup state")
        self._set("_sticky_invalid", True)
        self._state["state"] = "invalid_unknown"
        self._state["invalidation_reason"] = "exposed_gap"
        self._set("_clock", utc_text(new_timestamp))
        self._set("_segment", new_segment)
        self._set("_phase", 6)
        did = self._decision("forced_gap_flat", "protective", "gap")
        if self._state["spot_quantity"] > ZERO:
            src = self._authority_source(SPOT, self._clock)
            self._fill(did, SPOT, -self._state["spot_quantity"], decimal(src["severe_sell"]), "gap_spot", True)
        if self._state["perpetual_quantity"] != ZERO:
            src = self._authority_source(PERP, self._clock)
            self._fill(did, PERP, -self._state["perpetual_quantity"], decimal(src["severe_buy"] if self._state["perpetual_quantity"] < ZERO else src["severe_sell"]), "gap_perpetual", True)
        self._rolling.clear()
        self._set("_phase", 9)
        self._emit_account()

    def close_interval(self) -> dict[str, Any]:
        self._guard(6)
        self._set("_phase", 8)
        perp = self._authority_source(PERP, self._clock)
        adverse = decimal(perp["low"] if self._state["perpetual_quantity"] > ZERO else perp["high"])
        if self._state["perpetual_quantity"] != ZERO:
            self._liquidation_checkpoint("intrabar", adverse, perp["row_digest"])
        self._state["spot_mark"] = decimal(self._authority_source(SPOT, self._clock)["close"])
        self._state["perpetual_mark"] = decimal(perp["close"])
        self._refresh()
        self._set("_phase", 9)
        return self._emit_account()

    def _emit_account(self) -> dict[str, Any]:
        if self._phase != 9:
            raise ContractViolation("account wrong phase")
        source = self._authority_source(SPOT, self._clock)
        perp = self._authority_source(PERP, self._clock)
        maintenance = self._maintenance(self._state["perpetual_mark"])
        row = {"timestamp": self._clock, "segment_id": self._segment,
               "quote_cash": decimal_text(self._state["quote_cash"]), "spot_quantity": decimal_text(self._state["spot_quantity"]),
               "perpetual_quantity": decimal_text(self._state["perpetual_quantity"]), "isolated_collateral": decimal_text(self._state["isolated_collateral"]),
               "allocated_initial_margin_memo": decimal_text(self._state["allocated_initial_margin_memo"]), "exit_cost_reserve_memo": decimal_text(self._state["exit_cost_reserve_memo"]),
               "fee_asset_balances": self._state["fee_asset_balances"], "liabilities": decimal_text(self._state["liabilities"]),
               "realized_PnL": decimal_text(self._state["realized_PnL"]), "unrealized_PnL": decimal_text(self._state["unrealized_PnL"]),
               "funding": decimal_text(self._state["funding"]), "explicit_costs": decimal_text(self._state["explicit_costs"]),
               "implicit_costs": decimal_text(self._state["implicit_costs"]), "NAV": decimal_text(self._state["NAV"]),
               "gross_exposure": decimal_text(abs(self._state["spot_quantity"] * self._state["spot_mark"]) + abs(self._state["perpetual_quantity"] * self._state["perpetual_mark"])),
               "net_exposure": decimal_text(self._state["spot_quantity"] * self._state["spot_mark"] + self._state["perpetual_quantity"] * self._state["perpetual_mark"]),
               "margin_equity": decimal_text(self._margin_equity()), "maintenance_requirement": decimal_text(maintenance),
               "state": self._state["state"], "source_digest": source["row_digest"], "rules_digest": self._rules[SPOT].digest,
               "mark_source_digest": perp["row_digest"], "index_source_digest": self._source["index_digest"]}
        emitted = self._emit("account", row)
        if self._state["NAV"] > self._state["high_water"]:
            self._state["high_water"] = self._state["NAV"]
        return emitted

    def terminate(self) -> None:
        if self._terminal:
            raise ContractViolation("already terminal")
        if self._state["spot_quantity"] != ZERO or self._state["perpetual_quantity"] != ZERO:
            raise ContractViolation("terminal must be flat")
        self._set("_terminal", True)

    def _refresh(self) -> None:
        q = self._state["perpetual_quantity"]
        avg = self._state["average_perpetual_entry"]
        self._state["unrealized_PnL"] = ZERO if q == ZERO else q * (self._state["perpetual_mark"] - avg)
        exit_rate = decimal(self._settings["perpetual_exit_cost_rate"])
        if exit_rate == ZERO and not self._settings.get("zero_exit_reserve_fixture", False):
            raise ContractViolation("zero exit reserve")
        self._state["exit_cost_reserve_memo"] = abs(q) * self._state["perpetual_mark"] * exit_rate
        self._state["NAV"] = (self._state["quote_cash"] + self._state["spot_quantity"] * self._state["spot_mark"] +
                             self._state["isolated_collateral"] + self._state["unrealized_PnL"] - self._state["liabilities"])

    def _maintenance(self, mark: Decimal) -> Decimal:
        return abs(self._state["perpetual_quantity"]) * mark * decimal(self._margin["maintenance_fraction"])

    def _margin_equity(self) -> Decimal:
        return self._state["isolated_collateral"] + self._state["unrealized_PnL"] - self._state["exit_cost_reserve_memo"]

    def _liquidation_checkpoint(self, cause: str, mark: Decimal, source_digest: str) -> None:
        q = self._state["perpetual_quantity"]
        if q == ZERO:
            return
        old_mark = self._state["perpetual_mark"]
        self._state["perpetual_mark"] = mark
        self._refresh()
        if self._margin_equity() <= self._maintenance(mark):
            fee = abs(q) * mark * decimal(self._margin["liquidation_fee_rate"])
            pnl = abs(q) * (ONE if q > ZERO else -ONE) * (mark - self._state["average_perpetual_entry"])
            self._state["isolated_collateral"] += pnl - fee
            self._state["realized_PnL"] += pnl
            self._state["explicit_costs"] += fee
            self._state["perpetual_quantity"] = ZERO
            self._state["average_perpetual_entry"] = None
            if self._state["isolated_collateral"] < ZERO:
                self._state["liabilities"] += -self._state["isolated_collateral"]
            else:
                self._state["quote_cash"] += self._state["isolated_collateral"]
            self._state["isolated_collateral"] = ZERO
            self._state["allocated_initial_margin_memo"] = ZERO
            self._state["state"] = "liquidated"
            self._state["invalidation_reason"] = "observed_" + cause + "_liquidation"
            self._set("_liquidated", True)
            self._set("_sticky_invalid", True)
            self._refresh()
            # Liquidation is a real linked order/fill even outside ordinary phase 6.
            before = self._last_after
            oid = f"LQO{self._next_id():06d}"
            order = {"order_id": oid, "decision_id": "protective_liquidation", "created_at": self._clock,
                     "arrival_at": self._clock, "instrument": PERP, "requested_quantity": decimal_text(-q),
                     "rounded_quantity": decimal_text(-q), "filled_quantity": decimal_text(-q), "unfilled_quantity": "0",
                     "status": "filled", "reason": "liquidation_" + cause, "price_bound": decimal_text(mark),
                     "scenario_id": "liquidation", "source_digest": source_digest, "rules_digest": self._rules[PERP].digest}
            self._emit("order", order, before)
            fill = {"fill_id": f"LQF{self._next_id():06d}", "order_id": oid, "fill_at": self._clock,
                    "instrument": PERP, "signed_quantity": decimal_text(-q), "accounting_fill_price": decimal_text(mark),
                    "explicit_fee_native": decimal_text(fee), "explicit_fee_asset": "USDT",
                    "explicit_fee_quote_equivalent": decimal_text(fee), "implicit_cost_quote": "0", "post_fill_position": "0",
                    "rules_digest": self._rules[PERP].digest, "source_digest": source_digest,
                    "invalidation_reason": self._state["invalidation_reason"]}
            self._emit("fill", fill)
        else:
            self._state["perpetual_mark"] = old_mark
            self._refresh()

    def _open_episode(self, direction: str, fills: list[str]) -> None:
        entry_costs = self._state["explicit_costs"] + self._state["implicit_costs"]
        spot_entry = next((decimal(r["accounting_fill_price"]) for r in reversed(self.rows["fill"])
                           if r["instrument"] == SPOT and decimal(r["signed_quantity"]) > ZERO), ZERO)
        self._set("_episode", {"episode_id": f"E{self._next_id():06d}", "opened_at": self._clock,
                               "direction": direction, "start_NAV": self._state["NAV"] + entry_costs, "entry_costs": entry_costs,
                               "funding_start": self._state["funding"], "realized_start": self._state["realized_PnL"],
                               "spot_entry_price": spot_entry, "spot_entry_quantity": self._state["spot_quantity"],
                               "entry_fill_digests": list(fills), "mae": ZERO, "mfe": ZERO})

    def _close_episode(self, reason: str) -> None:
        if self._episode is None:
            return
        ep = self._episode
        total_cost = self._state["explicit_costs"] + self._state["implicit_costs"]
        funding = self._state["funding"] - ep["funding_start"]
        price = self._state["realized_PnL"] - ep["realized_start"]
        spot_exit = next((decimal(r["accounting_fill_price"]) for r in reversed(self.rows["fill"])
                          if r["instrument"] == SPOT and r["fill_at"] == self._clock and decimal(r["signed_quantity"]) < ZERO), ep["spot_entry_price"])
        price += ep["spot_entry_quantity"] * (spot_exit - ep["spot_entry_price"])
        row = {"episode_id": ep["episode_id"], "opened_at": ep["opened_at"], "closed_at": self._clock,
               "direction": ep["direction"], "entry_costs": decimal_text(ep["entry_costs"]),
               "exit_costs": decimal_text(total_cost - ep["entry_costs"]), "price_PnL": decimal_text(price),
               "funding_PnL": decimal_text(funding), "net_dollar_PnL": decimal_text(self._state["NAV"] - ep["start_NAV"]),
               "maximum_adverse_excursion": decimal_text(ep["mae"]), "maximum_favourable_excursion": decimal_text(ep["mfe"]),
               "close_reason": reason, "entry_fill_digests": ep["entry_fill_digests"],
               "exit_fill_digests": [r["row_digest"] for r in self.rows["fill"] if r["fill_at"] == self._clock],
               "source_digests": sorted({r["source_digest"] for r in self.rows["fill"]}),
               "rules_digests": sorted({r["rules_digest"] for r in self.rows["fill"]}),
               "invalidation_reason": self._state["invalidation_reason"]}
        row["row_digest"] = digest(row)
        self.episodes.append(row)
        self._set("_episode", None)

    def artifacts(self) -> Mapping[str, Any]:
        counts = {name: len(rows) for name, rows in self.rows.items()}
        counts["closed_episode"] = len(self.episodes)
        return MappingProxyType({"experiment_id": EXPERIMENT_ID, "actionable_arm_id": ACTIONABLE_ARM_ID,
                                 "counts": counts, "explicit_costs": decimal_text(self._state["explicit_costs"]),
                                 "implicit_costs": decimal_text(self._state["implicit_costs"]),
                                 "ledger_digests": {name: digest(rows) for name, rows in self.rows.items()},
                                 "episode_digest": digest(self.episodes), "ending_NAV": decimal_text(self._state["NAV"])})


def build_control(kind: str) -> AccountingStateMachine:
    if kind not in {"flat", "buy_and_hold", "same_exposure"}:
        raise ContractViolation("unknown control")
    machine = AuthorityVerifiedFactory.create()
    machine._rolling.append({"control_kind": kind, "independent_information_rule": kind == "same_exposure"})
    return machine


__all__ = ["ACTIONABLE_ARM_ID", "ACCOUNT_FIELDS", "AuthorityVerifiedFactory", "AccountingStateMachine",
           "ContractViolation", "DECISION_FIELDS", "DepthOutcomeUniverse", "EPISODE_FIELDS", "FILL_FIELDS",
           "FUNDING_FIELDS", "ORDER_FIELDS", "PERP", "PHASE_NAMES", "Rules", "SPOT", "build_control",
           "canonical_bytes", "decimal", "decimal_text", "digest", "quantize_down", "strict_json", "utc_text"]
