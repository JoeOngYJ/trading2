"""Clean-room synthetic Decimal ledger for BTC spot and linear perpetual research.

This is an offline E1 accounting kernel.  It intentionally contains no strategy,
historical-data adapter, performance metric, network client, or executable order type.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_DOWN, getcontext
from enum import IntEnum
from datetime import datetime, timezone
from typing import Any, Callable, Mapping


getcontext().prec = 50
ZERO = Decimal("0")
RESIDUAL_LIMIT = Decimal("0.00000001")


class LedgerError(ValueError):
    """Raised when synthetic accounting would become ambiguous or invalid."""


class PhaseError(LedgerError):
    """Raised when an event is attempted outside the frozen nine-phase order."""


class Phase(IntEnum):
    VALIDATE = 1
    OPEN_MARK = 2
    PROTECTIVE = 3
    FUNDING = 4
    PERMISSIONS = 5
    ORDERS = 6
    POST_FILL_MARGIN = 7
    INTRABAR = 8
    RECONCILE = 9


def decimal_string(value: Decimal) -> str:
    if not value.is_finite():
        raise LedgerError("economic Decimal must be finite")
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_string(value)
    if isinstance(value, IntEnum):
        return int(value)
    if hasattr(value, "__dataclass_fields__"):
        return _canonical(asdict(value))
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if key in result:
                raise LedgerError(f"mapping-key collision after canonicalization: {key}")
            result[key] = _canonical(raw_value)
        return {key: result[key] for key in sorted(result)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        raise LedgerError("float is forbidden in accounting serialization")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_json_no_collisions(text: str) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise LedgerError(f"duplicate JSON object key: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=pairs, parse_float=Decimal, parse_int=Decimal)


@dataclass(frozen=True, slots=True)
class Lineage:
    source_digest: str
    rules_digest: str
    mark_source_digest: str
    index_source_digest: str
    source_path: str = "synthetic://fixture"
    segment_id: str = "synthetic-segment"
    observed_at: str = "1970-01-01T00:00:00.000000Z"
    source_available_at: str = "1970-01-01T00:00:00.000000Z"
    rules_available_at: str = "1970-01-01T00:00:00.000000Z"
    mark_available_at: str = "1970-01-01T00:00:00.000000Z"
    index_available_at: str = "1970-01-01T00:00:00.000000Z"

    def __post_init__(self) -> None:
        values = asdict(self)
        for name in (
            "source_digest", "rules_digest", "mark_source_digest", "index_source_digest",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", values[name]):
                raise LedgerError(f"{name} must be a lowercase SHA-256")
        for name in (
            "observed_at", "source_available_at", "rules_available_at", "mark_available_at",
            "index_available_at",
        ):
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", values[name]
            ):
                raise LedgerError(f"{name} must be canonical UTC")
        if not self.source_path or not self.segment_id:
            raise LedgerError("source_path and segment_id are required")


@dataclass(frozen=True, slots=True)
class InstrumentRules:
    instrument: str
    quantity_step: Decimal
    price_tick: Decimal
    minimum_notional: Decimal
    fee_asset: str = "quote"
    fee_asset_name: str | None = None

    def __post_init__(self) -> None:
        if not self.instrument or min(self.quantity_step, self.price_tick) <= 0:
            raise LedgerError("instrument and positive tick/step are required")
        if self.minimum_notional < 0 or self.fee_asset not in {"quote", "base", "third"}:
            raise LedgerError("invalid instrument rules")
        if self.fee_asset == "third" and not self.fee_asset_name:
            raise LedgerError("third fee asset identity is required")

    def quantity(self, requested: Decimal) -> Decimal:
        if not requested.is_finite():
            raise LedgerError("requested quantity must be finite")
        absolute = (abs(requested) / self.quantity_step).to_integral_value(rounding=ROUND_DOWN)
        return absolute * self.quantity_step * (Decimal("-1") if requested < 0 else Decimal("1"))

    def validate(self, quantity: Decimal, price: Decimal) -> None:
        if not price.is_finite() or price <= 0 or quantity == 0:
            raise LedgerError("positive price and nonzero rounded quantity required")
        if quantity != self.quantity(quantity):
            raise LedgerError("filled quantity is not step-quantized")
        if price / self.price_tick != (price / self.price_tick).to_integral_value():
            raise LedgerError("accounting fill price is not tick-quantized")
        if abs(quantity) * price < self.minimum_notional:
            raise LedgerError("minimum_notional")


@dataclass(slots=True)
class LedgerState:
    quote_cash: Decimal
    spot_quantity: Decimal = ZERO
    isolated_collateral: Decimal = ZERO
    perpetual_quantity: Decimal = ZERO
    average_perpetual_entry: Decimal | None = None
    allocated_initial_margin: Decimal = ZERO
    liabilities: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    funding_pnl: Decimal = ZERO
    explicit_costs: Decimal = ZERO
    implicit_costs: Decimal = ZERO
    liquidation_costs: Decimal = ZERO
    neutralization_costs: Decimal = ZERO
    spot_price_pnl: Decimal = ZERO
    perpetual_price_pnl: Decimal = ZERO
    spot_mark: Decimal = ZERO
    perpetual_mark: Decimal = ZERO
    fee_asset_balances: dict[str, Decimal] = field(default_factory=dict)
    fee_asset_marks: dict[str, Decimal] = field(default_factory=dict)
    invalidation_reason: str | None = None
    margin_state: str = "flat"
    high_water_nav: Decimal = ZERO
    utc_day_start_nav: Decimal = ZERO
    utc_day: str | None = None
    entries_disabled: bool = False
    daily_entries_disabled: bool = False
    drawdown_entries_disabled: bool = False
    pending_forced_perpetual_buy_to_close: Decimal = ZERO
    pending_pair_origin_segment: str | None = None


@dataclass(frozen=True, slots=True)
class RunLineage:
    experiment_id: str
    run_id: str
    scenario_id: str
    implementation_digest: str
    contract_digest: str
    predecessor_contract_digest: str
    foundational_contract_digest: str
    execution_config_digest: str
    base_run_settings_digest: str
    mandate_digest: str

    def __post_init__(self) -> None:
        if any(not value for value in asdict(self).values()):
            raise LedgerError("complete run lineage is required")
        for name in (
            "implementation_digest", "contract_digest", "predecessor_contract_digest",
            "foundational_contract_digest", "execution_config_digest",
            "base_run_settings_digest", "mandate_digest",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", getattr(self, name)):
                raise LedgerError(f"{name} must be a lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class CostSchedule:
    ordinary_explicit_rate: Decimal
    ordinary_implicit_rate: Decimal
    severe_explicit_rate: Decimal
    severe_implicit_rate: Decimal

    def __post_init__(self) -> None:
        if any(
            not value.is_finite() or value < 0 for value in asdict(self).values()
        ):
            raise LedgerError("cost schedule rates must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class PairCloseCartesianOutcome:
    spot_gross_fill: Decimal
    spot_execution_price: Decimal
    perpetual_fill: Decimal
    perpetual_execution_price: Decimal
    severe_residual_price: Decimal

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(not value.is_finite() for value in values.values()):
            raise LedgerError("Cartesian outcome values must be finite Decimal")
        if min(
            self.spot_gross_fill, self.perpetual_fill,
            self.spot_execution_price, self.perpetual_execution_price,
            self.severe_residual_price,
        ) < 0 or min(
            self.spot_execution_price, self.perpetual_execution_price,
            self.severe_residual_price,
        ) == 0:
            raise LedgerError("Cartesian prices must be positive and fills nonnegative")


def expected_run_digests(
    *, cost_schedule: CostSchedule, initial_nav: Decimal = Decimal("1000"),
    leverage: Decimal = Decimal("4"), maintenance_fraction: Decimal = Decimal("0.10"),
    liquidation_fee_rate: Decimal = Decimal("0.01"),
    exit_cost_rate: Decimal = Decimal("0.004"), zero_exit_reserve_fixture: bool = False,
    maximum_allocation_fraction: Decimal = Decimal("0.25"),
    terminal_timestamp: str | None = None,
    mandate_mode: str = "spot",
) -> dict[str, str]:
    """Compute exact local-authority and immutable execution-configuration digests."""
    root = Path(__file__).resolve().parents[2]

    def file_sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    contract_root = root / "research/btc/contracts"
    execution = {
        "initial_nav": initial_nav, "leverage": leverage,
        "maintenance_fraction": maintenance_fraction,
        "liquidation_fee_rate": liquidation_fee_rate,
        "exit_cost_rate": exit_cost_rate,
        "maximum_allocation_fraction": maximum_allocation_fraction,
        "zero_exit_reserve_fixture": zero_exit_reserve_fixture,
        "terminal_timestamp": terminal_timestamp,
        "mandate_mode": mandate_mode,
        "cost_schedule": asdict(cost_schedule),
    }
    mandate_files = {
        "spot": "config/retail_mandate.json",
        "directional_perpetual": "config/mandates/retail-btc-directional-perpetual-research-v1.json",
        "delta_neutral": "config/mandates/retail-btc-delta-neutral-research-v1.json",
    }
    if mandate_mode not in mandate_files:
        raise LedgerError("unknown research mandate mode")
    return {
        "implementation_digest": file_sha(Path(__file__).resolve()),
        "contract_digest": file_sha(
            contract_root / "btc-unified-backtest-engine-e0-v3-pair-close.json"
        ),
        "predecessor_contract_digest": file_sha(
            contract_root / "btc-unified-backtest-engine-e0-v2.json"
        ),
        "foundational_contract_digest": file_sha(
            contract_root / "btc-unified-backtest-engine-e0-v1.json"
        ),
        "execution_config_digest": file_sha(root / "config/execution_scenarios.json"),
        "base_run_settings_digest": digest(execution),
        "mandate_digest": file_sha(root / mandate_files[mandate_mode]),
    }


@dataclass(slots=True)
class Episode:
    episode_id: str
    direction: int
    opened_at: str
    entry_costs: Decimal = ZERO
    exit_costs: Decimal = ZERO
    price_pnl: Decimal = ZERO
    funding_pnl: Decimal = ZERO
    maximum_adverse_excursion: Decimal = ZERO
    maximum_favourable_excursion: Decimal = ZERO
    entry_fill_digests: list[str] = field(default_factory=list)
    exit_fill_digests: list[str] = field(default_factory=list)
    source_digests: list[str] = field(default_factory=list)
    rules_digests: list[str] = field(default_factory=list)


class SyntheticDecimalLedger:
    """Synthetic-only state machine implementing combined E0-v1/v2 semantics."""

    def __init__(
        self,
        *,
        initial_nav: Decimal = Decimal("1000"),
        leverage: Decimal = Decimal("4"),
        maintenance_fraction: Decimal = Decimal("0.10"),
        liquidation_fee_rate: Decimal = Decimal("0.01"),
        exit_cost_rate: Decimal = Decimal("0.004"),
        maximum_allocation_fraction: Decimal = Decimal("0.25"),
        mandate_mode: str = "spot",
        zero_exit_reserve_fixture: bool = False,
        run_lineage: RunLineage | None = None,
        cost_schedule: CostSchedule | None = None,
        rule_registry: Mapping[str, InstrumentRules] | None = None,
        terminal_timestamp: str | None = None,
    ) -> None:
        values = (
            initial_nav, leverage, maintenance_fraction, liquidation_fee_rate,
            exit_cost_rate, maximum_allocation_fraction,
        )
        if any(not value.is_finite() for value in values) or initial_nav <= 0 or leverage <= 0:
            raise LedgerError("finite positive initial NAV and leverage are required")
        if min(maintenance_fraction, liquidation_fee_rate, exit_cost_rate) < 0:
            raise LedgerError("risk rates must be nonnegative")
        if maximum_allocation_fraction <= 0 or maximum_allocation_fraction > 1:
            raise LedgerError("maximum allocation fraction must be in (0, 1]")
        self.initial_nav = initial_nav
        self.leverage = leverage
        self.maintenance_fraction = maintenance_fraction
        self.liquidation_fee_rate = liquidation_fee_rate
        self.exit_cost_rate = exit_cost_rate
        self.maximum_allocation_fraction = maximum_allocation_fraction
        if mandate_mode not in {"spot", "directional_perpetual", "delta_neutral"}:
            raise LedgerError("unknown research mandate mode")
        expected_cap = Decimal("0.50") if mandate_mode == "delta_neutral" else Decimal("0.25")
        if maximum_allocation_fraction != expected_cap:
            raise LedgerError("allocation cap does not match selected mandate")
        if mandate_mode == "delta_neutral" and leverage != Decimal("1"):
            raise LedgerError("delta-neutral mandate requires 1x perpetual leverage")
        self.mandate_mode = mandate_mode
        self.zero_exit_reserve_fixture = zero_exit_reserve_fixture
        if run_lineage is None or cost_schedule is None or not rule_registry:
            raise LedgerError(
                "explicit run lineage, immutable costs, and a rule registry are required"
            )
        self.run_lineage = run_lineage
        self.cost_schedule = cost_schedule
        self.rule_registry = dict(rule_registry)
        self.terminal_timestamp = terminal_timestamp
        if terminal_timestamp is not None and not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", terminal_timestamp
        ):
            raise LedgerError("terminal timestamp must be canonical UTC")
        expected_digests = expected_run_digests(
            cost_schedule=cost_schedule, initial_nav=initial_nav, leverage=leverage,
            maintenance_fraction=maintenance_fraction,
            liquidation_fee_rate=liquidation_fee_rate, exit_cost_rate=exit_cost_rate,
            maximum_allocation_fraction=maximum_allocation_fraction,
            zero_exit_reserve_fixture=zero_exit_reserve_fixture,
            terminal_timestamp=terminal_timestamp,
            mandate_mode=mandate_mode,
        )
        for name, expected in expected_digests.items():
            if getattr(run_lineage, name) != expected:
                raise LedgerError(f"run lineage {name} does not match exact local authority")
        self.state = LedgerState(initial_nav, high_water_nav=initial_nav, utc_day_start_nav=initial_nav)
        self.phase: Phase | None = None
        self.timestamp: str | None = None
        self.event_sequence = 0
        self.t_minus_perpetual_quantity = ZERO
        self.current_lineage: Lineage | None = None
        self.ledgers: dict[str, list[dict[str, Any]]] = {
            name: [] for name in (
                "decision", "order", "fill", "funding", "account", "episode", "diagnostic"
            )
        }
        self._seen_ids: dict[str, set[str]] = {
            "decision": set(), "order": set(), "fill": set(),
            "episode": set(), "diagnostic": set(),
        }
        self._pair_ids: set[str] = set()
        self._episode: Episode | None = None
        self._pending_funding_episode: tuple[Episode, str, str] | None = None
        self._spot_episode: Episode | None = None
        self._episode_counter = 0
        self._event_finalized = True
        self._phase_completed = True
        self._last_timestamp: datetime | None = None
        self._terminal = False
        self._phase_work_done = True
        self._funding_membership_removed = False
        self._defer_episode_until_funding = False
        self._pair_operation = False
        self._protective_operation = False
        self._pending_pair_context: dict[str, Any] | None = None

    def initialize_fee_asset(self, *, asset: str, quantity: Decimal, quote_mark: Decimal) -> None:
        """Exchange initial quote cash for a declared fee asset without changing NAV."""
        if self.phase is not None or not asset or min(quantity, quote_mark) <= 0:
            raise LedgerError("fee asset initialization must precede the first event")
        quote_value = quantity * quote_mark
        if self.state.quote_cash < quote_value:
            raise LedgerError("insufficient quote cash for fee asset initialization")
        self.state.quote_cash -= quote_value
        self.state.fee_asset_balances[asset] = quantity
        self.state.fee_asset_marks[asset] = quote_mark

    def _state_data(self) -> dict[str, Any]:
        return asdict(self.state)

    def state_digest(self) -> str:
        return digest(self._state_data())

    def nav(self) -> Decimal:
        third = sum(
            (balance * self.state.fee_asset_marks.get(asset, ZERO)
             for asset, balance in self.state.fee_asset_balances.items()), ZERO
        )
        unrealized = (
            ZERO if self.state.perpetual_quantity == 0 else
            self.state.perpetual_quantity
            * (self.state.perpetual_mark - (self.state.average_perpetual_entry or ZERO))
        )
        return (
            self.state.quote_cash
            + self.state.spot_quantity * self.state.spot_mark
            + third
            + self.state.isolated_collateral
            + unrealized
            - self.state.liabilities
        )

    def margin_equity(self, *, planning: bool = False) -> Decimal:
        if self.state.perpetual_quantity == 0:
            return ZERO
        unrealized = self.state.perpetual_quantity * (
            self.state.perpetual_mark - (self.state.average_perpetual_entry or ZERO)
        )
        # Combined E0-v1/v2 explicitly includes the refreshed reserve in both tests.
        reserve = self.exit_cost_reserve()
        return self.state.isolated_collateral + unrealized - reserve

    def maintenance(self) -> Decimal:
        return abs(self.state.perpetual_quantity) * self.state.perpetual_mark * self.maintenance_fraction

    def exit_cost_reserve(self) -> Decimal:
        if self.state.perpetual_quantity == 0 or self.zero_exit_reserve_fixture:
            return ZERO
        return abs(self.state.perpetual_quantity) * self.state.perpetual_mark * self.exit_cost_rate

    def begin_event(self, timestamp: str, lineage: Lineage) -> None:
        if self._terminal:
            raise LedgerError("terminal liquidation forbids subsequent events")
        if not self._event_finalized or self.phase not in {None, Phase.RECONCILE}:
            raise PhaseError("previous event has not reconciled")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", timestamp):
            raise LedgerError("timestamp must be canonical UTC with six fractional digits")
        parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
        if parsed.tzinfo != timezone.utc or (self._last_timestamp is not None and parsed <= self._last_timestamp):
            raise LedgerError("event timestamps must be strictly increasing UTC")
        if self.terminal_timestamp is not None and timestamp > self.terminal_timestamp:
            raise LedgerError("event timestamp exceeds terminal boundary")
        for available_at in (
            lineage.source_available_at, lineage.rules_available_at,
            lineage.mark_available_at, lineage.index_available_at,
        ):
            available = datetime.fromisoformat(available_at[:-1] + "+00:00")
            if available > parsed:
                raise LedgerError("lineage is not available at the consuming event")
        observed = datetime.fromisoformat(lineage.observed_at[:-1] + "+00:00")
        source_available = datetime.fromisoformat(
            lineage.source_available_at[:-1] + "+00:00"
        )
        if observed > source_available:
            raise LedgerError("source observation occurs after its availability")
        expected_source = digest({
            "source_path": lineage.source_path, "segment_id": lineage.segment_id,
            "observed_at": lineage.observed_at,
            "source_available_at": lineage.source_available_at,
        })
        if lineage.source_digest != expected_source:
            raise LedgerError("source digest does not bind the declared synthetic source")
        if lineage.rules_digest != digest(self.rule_registry):
            raise LedgerError("rules digest does not bind the run rule registry")
        if lineage.mark_source_digest != digest({
            "source_digest": lineage.source_digest, "kind": "official_mark"
        }):
            raise LedgerError("mark source digest is not bound")
        if lineage.index_source_digest != digest({
            "source_digest": lineage.source_digest, "kind": "official_index"
        }):
            raise LedgerError("index source digest is not bound")
        self.timestamp = timestamp
        self.current_lineage = lineage
        self.phase = Phase.VALIDATE
        self.t_minus_perpetual_quantity = self.state.perpetual_quantity
        self.event_sequence += 1
        self._event_finalized = False
        self._phase_completed = True
        self._phase_work_done = True
        self._funding_membership_removed = False
        self._last_timestamp = parsed
        event_day = timestamp[:10]
        if self.state.utc_day != event_day:
            self.state.utc_day = event_day
            self.state.utc_day_start_nav = self.nav()
            self.state.daily_entries_disabled = False
            self.state.entries_disabled = self.state.drawdown_entries_disabled

    def advance(self, phase: Phase) -> None:
        if not self._phase_completed:
            raise PhaseError(f"phase {self.phase} must be explicitly completed")
        if self.phase is None or int(phase) != int(self.phase) + 1:
            raise PhaseError(f"phase must advance exactly once from {self.phase} to {phase}")
        self.phase = phase
        self._phase_completed = False
        self._phase_work_done = False

    def complete_phase(self) -> None:
        if self.phase is None:
            raise PhaseError("no active phase")
        if self.phase in {Phase.OPEN_MARK, Phase.PERMISSIONS, Phase.POST_FILL_MARGIN, Phase.INTRABAR} \
                and not self._phase_work_done:
            raise PhaseError(f"mandatory phase {self.phase} has no validated work")
        if self.phase == Phase.FUNDING and self._pending_funding_episode is not None:
            episode, closed_at, reason = self._pending_funding_episode
            self._emit_episode(episode, closed_at, reason)
            self._pending_funding_episode = None
        self._phase_completed = True

    def _require(self, phase: Phase) -> None:
        if self.phase != phase:
            raise PhaseError(f"operation requires phase {int(phase)}, current={self.phase}")
        if self._phase_completed:
            raise PhaseError(f"phase {int(phase)} is already completed")

    def _lineage_fields(self) -> dict[str, str]:
        if self.current_lineage is None:
            raise LedgerError("event lineage is unavailable")
        return asdict(self.current_lineage)

    def _record(
        self, ledger: str, payload: dict[str, Any], before: str, after: str,
        *, before_nav: Decimal | None = None, after_nav: Decimal | None = None,
        expected_nav_change: Decimal = ZERO,
    ) -> str:
        before_value = self.nav() if before_nav is None else before_nav
        after_value = self.nav() if after_nav is None else after_nav
        residual = after_value - before_value - expected_nav_change
        if abs(residual) > RESIDUAL_LIMIT:
            raise LedgerError(
                f"event accounting residual {decimal_string(residual)} exceeds tolerance"
            )
        identity_fields = {
            "decision": "decision_id", "order": "order_id", "fill": "fill_id",
            "episode": "episode_id", "diagnostic": "diagnostic_id",
        }
        if ledger in identity_fields:
            identity = str(payload[identity_fields[ledger]])
            if identity in self._seen_ids[ledger]:
                raise LedgerError(f"duplicate {identity_fields[ledger]}: {identity}")
            self._seen_ids[ledger].add(identity)
        row = {
            **payload,
            **self._lineage_fields(),
            **asdict(self.run_lineage),
            "event_sequence": self.event_sequence,
            "before_state_digest": before,
            "after_state_digest": after,
            "before_NAV": before_value,
            "after_NAV": after_value,
            "event_NAV_change": after_value - before_value,
            "expected_event_NAV_change": expected_nav_change,
            "event_accounting_residual": residual,
            "invalidation_reason": self.state.invalidation_reason,
            "actionable_arm_id": "no_trade",
        }
        row["row_digest"] = digest(row)
        self.ledgers[ledger].append(_canonical(row))
        return row["row_digest"]

    def _transaction(self, mutation: Callable[[], Any]) -> Any:
        state_before = copy.deepcopy(self.state)
        ledger_lengths = {key: len(value) for key, value in self.ledgers.items()}
        episode_before = copy.deepcopy(self._episode)
        spot_episode_before = copy.deepcopy(self._spot_episode)
        pending_episode_before = copy.deepcopy(self._pending_funding_episode)
        counter_before = self._episode_counter
        terminal_before = self._terminal
        completed_before = self._phase_completed
        work_before = self._phase_work_done
        membership_before = self._funding_membership_removed
        defer_before = self._defer_episode_until_funding
        pair_operation_before = self._pair_operation
        protective_operation_before = self._protective_operation
        pending_pair_context_before = copy.deepcopy(self._pending_pair_context)
        seen_before = copy.deepcopy(self._seen_ids)
        pair_ids_before = set(self._pair_ids)
        try:
            return mutation()
        except Exception:
            self.state = state_before
            self._episode = episode_before
            self._spot_episode = spot_episode_before
            self._pending_funding_episode = pending_episode_before
            self._episode_counter = counter_before
            self._terminal = terminal_before
            self._phase_completed = completed_before
            self._phase_work_done = work_before
            self._funding_membership_removed = membership_before
            self._defer_episode_until_funding = defer_before
            self._pair_operation = pair_operation_before
            self._protective_operation = protective_operation_before
            self._pending_pair_context = pending_pair_context_before
            self._seen_ids = seen_before
            self._pair_ids = pair_ids_before
            for key, length in ledger_lengths.items():
                del self.ledgers[key][length:]
            raise

    def mark_open(self, *, spot: Decimal | None = None, perpetual: Decimal | None = None) -> None:
        self._require(Phase.OPEN_MARK)
        self._mark(spot=spot, perpetual=perpetual)
        self._liquidate_if_observed("open")
        self._phase_work_done = True
        self.complete_phase()

    def _mark(self, *, spot: Decimal | None = None, perpetual: Decimal | None = None) -> None:
        before = self.state_digest()
        before_nav = self.nav()
        expected_change = ZERO
        if spot is not None:
            if spot <= 0 or not spot.is_finite():
                raise LedgerError("spot mark must be finite and positive")
            if self.state.spot_mark:
                delta = self.state.spot_quantity * (spot - self.state.spot_mark)
                self.state.spot_price_pnl += delta
                expected_change += delta
                if self._spot_episode is not None:
                    self._spot_episode.price_pnl += delta
                    self._spot_episode.maximum_adverse_excursion = min(
                        self._spot_episode.maximum_adverse_excursion, self._spot_episode.price_pnl
                    )
                    self._spot_episode.maximum_favourable_excursion = max(
                        self._spot_episode.maximum_favourable_excursion, self._spot_episode.price_pnl
                    )
            self.state.spot_mark = spot
        if perpetual is not None:
            if perpetual <= 0 or not perpetual.is_finite():
                raise LedgerError("perpetual mark must be finite and positive")
            if self.state.perpetual_mark:
                delta = self.state.perpetual_quantity * (perpetual - self.state.perpetual_mark)
                self.state.perpetual_price_pnl += delta
                expected_change += delta
                if self._episode is not None:
                    self._episode.price_pnl += delta
                    self._episode.maximum_adverse_excursion = min(
                        self._episode.maximum_adverse_excursion, self._episode.price_pnl
                    )
                    self._episode.maximum_favourable_excursion = max(
                        self._episode.maximum_favourable_excursion, self._episode.price_pnl
                    )
            self.state.perpetual_mark = perpetual
        after = self.state_digest()
        if before != after and self.current_lineage is not None:
            self._record("account", {
                "timestamp": self.timestamp, "state": "mark_transition", "NAV": self.nav(),
                "spot_mark": self.state.spot_mark, "perpetual_mark": self.state.perpetual_mark,
            }, before, after, before_nav=before_nav, after_nav=self.nav(),
                expected_nav_change=expected_change)

    def permissions(self, *, decision_id: str, requested_target: str) -> bool:
        self._require(Phase.PERMISSIONS)
        before = self.state_digest()
        allowed = not self.state.entries_disabled and self.state.invalidation_reason is None
        self._record("decision", {
            "decision_id": decision_id, "decision_at": self.timestamp,
            "available_information_cutoff": self.timestamp, "requested_target": requested_target,
            "permission_or_abstention": "allowed" if allowed else "abstain",
            "reason": None if allowed else "risk_or_invalid_state",
            "lineage_digest": digest(self._lineage_fields()),
        }, before, self.state_digest())
        self._phase_work_done = True
        self.complete_phase()
        return allowed

    def _invalidate(self, reason: str) -> None:
        if self.state.invalidation_reason is None:
            self.state.invalidation_reason = reason

    def _increases_at_terminal(self, incoming: Decimal, target: Decimal) -> bool:
        return self.timestamp == self.terminal_timestamp and (
            abs(target) > abs(incoming) or (incoming and target and incoming * target < 0)
        )

    def _validate_cost_rates(
        self, *, explicit_rate: Decimal, implicit_rate: Decimal, reason: str,
    ) -> None:
        severe = "neutralization" in reason
        expected = (
            (self.cost_schedule.severe_explicit_rate, self.cost_schedule.severe_implicit_rate)
            if severe else
            (self.cost_schedule.ordinary_explicit_rate, self.cost_schedule.ordinary_implicit_rate)
        )
        if (explicit_rate, implicit_rate) != expected:
            raise LedgerError("fill cost rates differ from immutable run cost schedule")

    def _validate_rules(self, rules: InstrumentRules) -> None:
        if self.rule_registry.get(rules.instrument) != rules:
            raise LedgerError("instrument rules differ from immutable run rule registry")

    def record_unfilled_order(
        self, *, order_id: str, instrument: str, requested_quantity: Decimal,
        rounded_quantity: Decimal, status: str, reason: str, price_bound: Decimal,
    ) -> None:
        self._require(Phase.ORDERS)
        if status not in {"rejected", "expired"}:
            raise LedgerError("unfilled status must be rejected or expired")
        before = self.state_digest()
        self._record("order", {
            "order_id": order_id, "decision_id": order_id, "created_at": self.timestamp,
            "arrival_at": self.timestamp, "instrument": instrument,
            "requested_quantity": requested_quantity, "rounded_quantity": rounded_quantity,
            "filled_quantity": ZERO, "unfilled_quantity": rounded_quantity,
            "status": status, "reason": reason, "price_bound": price_bound,
            "scenario_id": self.run_lineage.scenario_id,
        }, before, before)
        self._record("diagnostic", {
            "diagnostic_id": f"{order_id}:{status}", "timestamp": self.timestamp,
            "kind": status, "quantity": rounded_quantity,
            "cash_effect": ZERO, "reason": reason,
        }, before, before)

    def _fee(self, *, quantity: Decimal, price: Decimal, rate: Decimal, rules: InstrumentRules,
             fee_mark_asset: str | None, fee_mark: Decimal | None) -> tuple[Decimal, str]:
        quote_value = abs(quantity) * price * rate
        if rules.fee_asset == "quote":
            return quote_value, "quote"
        if rules.fee_asset == "base":
            return abs(quantity) * rate, "base"
        if fee_mark_asset != rules.fee_asset_name or fee_mark is None or fee_mark <= 0:
            raise LedgerError("third-asset fee mark identity or value is invalid")
        native = quote_value / fee_mark
        assert rules.fee_asset_name is not None
        available = self.state.fee_asset_balances.get(rules.fee_asset_name, ZERO)
        if available < native or self.state.fee_asset_marks.get(rules.fee_asset_name) != fee_mark:
            raise LedgerError("third-asset fee balance/point-in-time mark unavailable")
        return native, "third"

    def spot_fill(
        self, *, order_id: str, requested_delta: Decimal, filled_quantity: Decimal, price: Decimal,
        rules: InstrumentRules, explicit_rate: Decimal, implicit_rate: Decimal,
        adapter: str = "synthetic_quote_l2", fee_mark_asset: str | None = None,
        fee_mark: Decimal | None = None, reason: str = "ordinary",
    ) -> Decimal:
        self._require(Phase.ORDERS)
        if self.mandate_mode != "spot" and not self._pair_operation and not self._protective_operation:
            raise LedgerError("selected mandate prohibits standalone spot execution")
        if order_id in self._seen_ids["order"] or order_id in self._pair_ids:
            raise LedgerError(f"duplicate order_id: {order_id}")

        def mutate() -> Decimal:
            before = self.state_digest()
            before_nav = self.nav()
            if any(not rate.is_finite() or rate < 0 for rate in (explicit_rate, implicit_rate)):
                raise LedgerError("fill rates must be finite and nonnegative")
            self._validate_cost_rates(
                explicit_rate=explicit_rate, implicit_rate=implicit_rate, reason=reason
            )
            self._validate_rules(rules)
            rounded = rules.quantity(requested_delta)
            if self._increases_at_terminal(self.state.spot_quantity, self.state.spot_quantity + rounded):
                raise LedgerError("terminal timestamp forbids increasing spot exposure")
            rules.validate(rounded, price)
            post_spot = self.state.spot_quantity + rounded
            if rounded > 0 and post_spot * price > self.nav() * self.maximum_allocation_fraction:
                raise LedgerError("spot allocation exceeds immutable mandate cap")
            if abs(filled_quantity) > abs(rounded) or filled_quantity * rounded < 0:
                raise LedgerError("invalid filled quantity")
            if adapter == "candle" and filled_quantity != rounded:
                raise LedgerError("candle adapter cannot emit partial fill")
            if filled_quantity == 0:
                raise LedgerError("zero fill")
            rules.validate(filled_quantity, price)
            native_fee, fee_kind = self._fee(
                quantity=filled_quantity, price=price, rate=explicit_rate, rules=rules,
                fee_mark_asset=fee_mark_asset, fee_mark=fee_mark,
            )
            implicit = abs(filled_quantity) * price * implicit_rate
            basis = filled_quantity * (price - self.state.spot_mark)
            if fee_kind == "quote":
                explicit_quote = native_fee
            elif fee_kind == "base":
                explicit_quote = native_fee * self.state.spot_mark
            else:
                assert fee_mark is not None
                explicit_quote = native_fee * fee_mark
            fill_cost = explicit_quote
            incoming_spot = self.state.spot_quantity
            if filled_quantity > 0:
                required_cash = filled_quantity * price + implicit + (native_fee if fee_kind == "quote" else ZERO)
                if self.state.quote_cash < required_cash:
                    raise LedgerError("insufficient quote cash")
                self.state.quote_cash -= filled_quantity * price + implicit
                self.state.spot_quantity += filled_quantity
            else:
                gross = abs(filled_quantity)
                base_required = gross + (native_fee if fee_kind == "base" else ZERO)
                if self.state.spot_quantity < base_required:
                    raise LedgerError("insufficient spot inventory")
                self.state.spot_quantity -= gross
                self.state.quote_cash += gross * price - implicit
            if fee_kind == "quote":
                self.state.quote_cash -= native_fee
            elif fee_kind == "base":
                if filled_quantity > 0 and self.state.spot_quantity < native_fee:
                    raise LedgerError("base fee exceeds acquired inventory")
                self.state.spot_quantity -= native_fee
            else:
                assert fee_mark is not None
                assert rules.fee_asset_name is not None
                self.state.fee_asset_balances[rules.fee_asset_name] -= native_fee
            self.state.explicit_costs += explicit_quote
            self.state.implicit_costs += implicit + basis
            if "neutralization" in reason:
                self.state.neutralization_costs += explicit_quote + implicit + basis
            if filled_quantity > 0:
                if incoming_spot == 0:
                    self._episode_counter += 1
                    self._spot_episode = Episode(
                        f"episode-{self._episode_counter}", 1, self.timestamp or "",
                        entry_costs=fill_cost + implicit + basis,
                    )
                elif self._spot_episode is not None:
                    self._spot_episode.entry_costs += fill_cost + implicit + basis
            elif self._spot_episode is not None:
                self._spot_episode.exit_costs += fill_cost + implicit + basis
            close_spot_episode = filled_quantity < 0 and self.state.spot_quantity == 0
            after = self.state_digest()
            status = "filled" if filled_quantity == rounded else "partially_filled"
            self._record("order", {
                "order_id": order_id, "decision_id": order_id, "created_at": self.timestamp,
                "arrival_at": self.timestamp, "instrument": rules.instrument,
                "requested_quantity": requested_delta, "rounded_quantity": rounded,
                "filled_quantity": filled_quantity, "unfilled_quantity": rounded - filled_quantity,
                "status": status, "reason": reason, "price_bound": price, "scenario_id": adapter,
            }, before, after, before_nav=before_nav, after_nav=self.nav(),
                expected_nav_change=-(explicit_quote + implicit + basis))
            fill_digest = self._record("fill", {
                "fill_id": f"{order_id}:1", "order_id": order_id, "fill_at": self.timestamp,
                "instrument": rules.instrument, "signed_quantity": filled_quantity,
                "accounting_fill_price": price, "explicit_fee_native": native_fee,
                "explicit_fee_asset": rules.fee_asset,
                "explicit_fee_quote_equivalent": explicit_quote,
                "implicit_cost_quote": implicit + basis,
                "post_fill_position": self.state.spot_quantity,
            }, before, after, before_nav=before_nav, after_nav=self.nav(),
                expected_nav_change=-(explicit_quote + implicit + basis))
            if self._spot_episode is not None:
                digests = (
                    self._spot_episode.entry_fill_digests if filled_quantity > 0
                    else self._spot_episode.exit_fill_digests
                )
                digests.append(fill_digest)
                self._spot_episode.source_digests.append(self.current_lineage.source_digest)
                self._spot_episode.rules_digests.append(self.current_lineage.rules_digest)
                if close_spot_episode:
                    self._close_spot_episode(reason)
            return filled_quantity

        try:
            return self._transaction(mutate)
        except LedgerError as exc:
            rounded = rules.quantity(requested_delta)
            self.record_unfilled_order(
                order_id=order_id, instrument=rules.instrument,
                requested_quantity=requested_delta, rounded_quantity=rounded,
                status="rejected", reason=str(exc), price_bound=price,
            )
            raise

    def _open_episode(self, direction: int, entry_cost: Decimal, order_id: str = "entry") -> None:
        self._episode_counter += 1
        self._episode = Episode(
            episode_id=f"episode-{self._episode_counter}", direction=direction,
            opened_at=self.timestamp or "", entry_costs=entry_cost,
        )

    def _emit_episode(self, episode: Episode, closed_at: str, reason: str) -> None:
        row = {
            **asdict(episode), "closed_at": closed_at,
            "net_dollar_pnl": episode.price_pnl + episode.funding_pnl
            - episode.entry_costs - episode.exit_costs,
            "price_PnL": episode.price_pnl,
            "funding_PnL": episode.funding_pnl,
            "net_dollar_PnL": episode.price_pnl + episode.funding_pnl
            - episode.entry_costs - episode.exit_costs,
            "close_reason": reason,
            "invalidation_reason": self.state.invalidation_reason,
        }
        before = self.state_digest()
        self._record("episode", row, before, before)

    def _close_episode(self, exit_cost: Decimal, reason: str) -> None:
        if self._episode is None:
            return
        self._episode.exit_costs += exit_cost
        if self._defer_episode_until_funding and self.t_minus_perpetual_quantity:
            self._pending_funding_episode = (
                self._episode, self.timestamp or "", reason,
            )
        else:
            self._emit_episode(self._episode, self.timestamp or "", reason)
        self._episode = None

    def _close_spot_episode(self, reason: str) -> None:
        if self._spot_episode is None:
            return
        row = {
            **asdict(self._spot_episode), "closed_at": self.timestamp,
            "net_dollar_pnl": self._spot_episode.price_pnl
            - self._spot_episode.entry_costs - self._spot_episode.exit_costs,
            "price_PnL": self._spot_episode.price_pnl,
            "funding_PnL": self._spot_episode.funding_pnl,
            "net_dollar_PnL": self._spot_episode.price_pnl
            - self._spot_episode.entry_costs - self._spot_episode.exit_costs,
            "close_reason": reason,
            "invalidation_reason": self.state.invalidation_reason,
        }
        before = self.state_digest()
        self._record("episode", row, before, before)
        self._spot_episode = None

    def _perp_one_fill(
        self, *, order_id: str, delta: Decimal, price: Decimal, rules: InstrumentRules,
        explicit_rate: Decimal, implicit_rate: Decimal, reason: str,
    ) -> tuple[Decimal, Decimal, Decimal, bool]:
        before_nav = self.nav()
        self._validate_rules(rules)
        self._validate_cost_rates(
            explicit_rate=explicit_rate, implicit_rate=implicit_rate, reason=reason
        )
        rules.validate(delta, price)
        if any(not rate.is_finite() or rate < 0 for rate in (explicit_rate, implicit_rate)):
            raise LedgerError("fill rates must be finite and nonnegative")
        before_qty = self.state.perpetual_quantity
        before_abs = abs(before_qty)
        increasing = before_qty == 0 or before_qty * delta > 0
        cost_explicit = abs(delta) * price * explicit_rate
        cost_implicit = abs(delta) * price * implicit_rate
        total_cost = cost_explicit + cost_implicit
        basis = delta * (price - self.state.perpetual_mark)
        attributed_cost = total_cost + basis
        self.state.explicit_costs += cost_explicit
        self.state.implicit_costs += cost_implicit + basis
        if "neutralization" in reason:
            self.state.neutralization_costs += attributed_cost
        if increasing:
            margin = abs(delta) * price / self.leverage
            if self.state.quote_cash < margin:
                raise LedgerError("insufficient quote cash for initial margin")
            self.state.quote_cash -= margin
            self.state.isolated_collateral += margin
            self.state.allocated_initial_margin += margin
            new_abs = before_abs + abs(delta)
            previous_entry = self.state.average_perpetual_entry or ZERO
            self.state.average_perpetual_entry = (
                previous_entry * before_abs + price * abs(delta)
            ) / new_abs
            self.state.perpetual_quantity += delta
            if self.state.isolated_collateral < total_cost:
                raise LedgerError("isolated collateral cannot fund fill costs")
            self.state.isolated_collateral -= total_cost
            if before_qty == 0:
                self._open_episode(1 if delta > 0 else -1, attributed_cost, order_id)
            elif self._episode is not None:
                self._episode.entry_costs += attributed_cost
        else:
            closed = abs(delta)
            if closed > before_abs:
                raise LedgerError("single reducing fill crosses zero")
            sign = Decimal("1") if before_qty > 0 else Decimal("-1")
            realized = closed * sign * (price - (self.state.average_perpetual_entry or ZERO))
            self.state.realized_pnl += realized
            self.state.isolated_collateral += realized
            if self.state.isolated_collateral < total_cost:
                deficit = total_cost - max(self.state.isolated_collateral, ZERO)
                self.state.isolated_collateral = ZERO
                self.state.liabilities += deficit
            else:
                self.state.isolated_collateral -= total_cost
            release_memo = self.state.allocated_initial_margin * closed / before_abs
            self.state.allocated_initial_margin -= release_memo
            release = min(release_memo, max(self.state.isolated_collateral, ZERO))
            self.state.isolated_collateral -= release
            self.state.quote_cash += release
            self.state.perpetual_quantity += delta
            if self._episode is not None:
                self._episode.exit_costs += attributed_cost
            if self.state.perpetual_quantity == 0:
                if self.state.isolated_collateral < 0:
                    self.state.liabilities += -self.state.isolated_collateral
                    self.state.isolated_collateral = ZERO
                self.state.quote_cash += self.state.isolated_collateral
                self.state.isolated_collateral = ZERO
                self.state.allocated_initial_margin = ZERO
                self.state.average_perpetual_entry = None
                close_episode = True
            elif self._episode is not None:
                close_episode = False
            else:
                close_episode = False
        if increasing:
            close_episode = False
        return before_nav, self.nav(), cost_explicit + cost_implicit + basis, close_episode

    def rebalance_perpetual(
        self, *, order_id: str, target_quantity: Decimal, price: Decimal,
        rules: InstrumentRules, explicit_rate: Decimal, implicit_rate: Decimal,
        reason: str = "ordinary",
        reported_requested_quantity: Decimal | None = None,
        reported_rounded_quantity: Decimal | None = None,
    ) -> None:
        self._require(Phase.ORDERS)
        if (
            self.mandate_mode != "directional_perpetual"
            and not self._pair_operation and not self._protective_operation
        ):
            raise LedgerError("selected mandate prohibits standalone perpetual execution")
        if order_id in self._seen_ids["order"] or order_id in self._pair_ids:
            raise LedgerError(f"duplicate order_id: {order_id}")

        if rules.fee_asset != "quote":
            self.record_unfilled_order(
                order_id=order_id, instrument=rules.instrument,
                requested_quantity=target_quantity,
                rounded_quantity=rules.quantity(target_quantity), status="rejected",
                reason="linear perpetual fees must be quote-denominated",
                price_bound=price,
            )
            raise LedgerError("linear perpetual fees must be quote-denominated")

        def mutate() -> None:
            before = self.state_digest()
            order_before_nav = self.nav()
            total_economic_cost = ZERO
            target = rules.quantity(target_quantity)
            if self._terminal:
                raise LedgerError("terminal liquidation forbids orders")
            if self._increases_at_terminal(self.state.perpetual_quantity, target):
                raise LedgerError("terminal timestamp forbids increasing perpetual exposure")
            if target:
                rules.validate(target, price)
            incoming = self.state.perpetual_quantity
            if (abs(target) > abs(incoming) or (target and incoming and target * incoming < 0)) and (
                abs(target) * price > self.nav() * self.maximum_allocation_fraction
            ):
                raise LedgerError("perpetual allocation exceeds immutable mandate cap")
            deltas: list[Decimal] = []
            if incoming and target and incoming * target < 0:
                deltas = [-incoming, target]
            elif target != incoming:
                deltas = [target - incoming]
            for index, delta in enumerate(deltas, 1):
                pre_fill_quantity = self.state.perpetual_quantity
                fill_before_nav, fill_after_nav, economic_cost, close_episode = self._perp_one_fill(
                    order_id=order_id, delta=delta, price=price, rules=rules,
                    explicit_rate=explicit_rate, implicit_rate=implicit_rate, reason=reason,
                )
                total_economic_cost += economic_cost
                middle = self.state_digest()
                fill_digest = self._record("fill", {
                    "fill_id": f"{order_id}:{index}", "order_id": order_id,
                    "fill_at": self.timestamp, "instrument": rules.instrument,
                    "signed_quantity": delta, "accounting_fill_price": price,
                    "explicit_fee_native": abs(delta) * price * explicit_rate,
                    "explicit_fee_asset": "quote",
                    "explicit_fee_quote_equivalent": abs(delta) * price * explicit_rate,
                    "implicit_cost_quote": abs(delta) * price * implicit_rate,
                    "post_fill_position": self.state.perpetual_quantity,
                }, before if index == 1 else self.ledgers["fill"][-1]["after_state_digest"], middle,
                    before_nav=fill_before_nav, after_nav=fill_after_nav,
                    expected_nav_change=-economic_cost)
                if self._episode is not None:
                    digests = (
                        self._episode.entry_fill_digests
                        if pre_fill_quantity == 0 or pre_fill_quantity * delta > 0
                        else self._episode.exit_fill_digests
                    )
                    digests.append(fill_digest)
                    self._episode.source_digests.append(self.current_lineage.source_digest)
                    self._episode.rules_digests.append(self.current_lineage.rules_digest)
                    if close_episode:
                        self._close_episode(ZERO, reason)
                liquidation_cost_before = self.state.liquidation_costs
                if self._liquidate_if_observed("post_fill"):
                    total_economic_cost += self.state.liquidation_costs - liquidation_cost_before
                    break
            after = self.state_digest()
            self._record("order", {
                "order_id": order_id, "decision_id": order_id, "created_at": self.timestamp,
                "arrival_at": self.timestamp, "instrument": rules.instrument,
                "requested_quantity": (
                    target_quantity if reported_requested_quantity is None
                    else reported_requested_quantity
                ),
                "rounded_quantity": (
                    target if reported_rounded_quantity is None
                    else reported_rounded_quantity
                ),
                "filled_quantity": target - incoming,
                "unfilled_quantity": (
                    ZERO if reported_rounded_quantity is None
                    else reported_rounded_quantity - (target - incoming)
                ),
                "status": "filled" if deltas else "no_change", "reason": reason,
                "price_bound": price, "scenario_id": "synthetic",
            }, before, after, before_nav=order_before_nav, after_nav=self.nav(),
                expected_nav_change=-total_economic_cost)

        try:
            self._transaction(mutate)
        except LedgerError as exc:
            self.record_unfilled_order(
                order_id=order_id, instrument=rules.instrument,
                requested_quantity=target_quantity,
                rounded_quantity=rules.quantity(target_quantity), status="rejected",
                reason=str(exc), price_bound=price,
            )
            raise

    def apply_funding(
        self, *, rate: Decimal | None, mark: Decimal, economic_at: str,
        available_at: str, missing: bool = False,
    ) -> Decimal:
        self._require(Phase.FUNDING)

        def mutate() -> Decimal:
            before = self.state_digest()
            before_nav = self.nav()
            if economic_at != self.timestamp:
                raise LedgerError("funding economic timestamp must equal current event")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", available_at):
                raise LedgerError("funding available_at must be canonical UTC")
            if available_at > (self.timestamp or ""):
                raise LedgerError("funding value is unavailable at this synthetic event")
            if missing:
                if self.t_minus_perpetual_quantity:
                    self._invalidate("missing_funding_while_exposed")
                cashflow = ZERO
            else:
                if rate is None or not rate.is_finite() or mark <= 0:
                    raise LedgerError("valid funding rate and mark required")
                membership = ZERO if self._funding_membership_removed else self.t_minus_perpetual_quantity
                cashflow = -membership * mark * rate
                if self.state.perpetual_quantity:
                    self.state.isolated_collateral += cashflow
                else:
                    self.state.quote_cash += cashflow
                if self.state.isolated_collateral < 0:
                    self.state.liabilities += -self.state.isolated_collateral
                    self.state.isolated_collateral = ZERO
                self.state.funding_pnl += cashflow
                if self._episode is not None:
                    self._episode.funding_pnl += cashflow
                    self._episode.source_digests.append(self.current_lineage.source_digest)
                    self._episode.rules_digests.append(self.current_lineage.rules_digest)
                elif self._pending_funding_episode is not None:
                    self._pending_funding_episode[0].funding_pnl += cashflow
                    self._pending_funding_episode[0].source_digests.append(
                        self.current_lineage.source_digest
                    )
                    self._pending_funding_episode[0].rules_digests.append(
                        self.current_lineage.rules_digest
                    )
            after = self.state_digest()
            self._record("funding", {
                "funding_at": self.timestamp,
                "t_minus_signed_quantity": (
                    ZERO if self._funding_membership_removed else self.t_minus_perpetual_quantity
                ),
                "funding_rate": rate, "funding_mark": mark, "cashflow_quote": cashflow,
                "economic_at": economic_at, "available_at": available_at,
            }, before, after, before_nav=before_nav, after_nav=self.nav(),
                expected_nav_change=cashflow)
            if self.state.perpetual_quantity:
                self._liquidate_if_observed("funding")
            self.complete_phase()
            return cashflow

        try:
            return self._transaction(mutate)
        except LedgerError as exc:
            before = self.state_digest()
            self._record("diagnostic", {
                "diagnostic_id": f"funding:{self.event_sequence}:rejected",
                "timestamp": self.timestamp, "kind": "rejected_funding",
                "quantity": self.t_minus_perpetual_quantity,
                "cash_effect": ZERO, "reason": str(exc),
                "economic_at": economic_at, "available_at": available_at,
            }, before, before)
            raise

    def protective_flatten_perpetual(
        self, *, order_id: str, price: Decimal, rules: InstrumentRules,
        explicit_rate: Decimal, implicit_rate: Decimal, reason: str,
    ) -> None:
        self._require(Phase.PROTECTIVE)
        # Use the same transition while preserving the phase contract.
        self.phase = Phase.ORDERS
        self._defer_episode_until_funding = True
        self._protective_operation = True
        try:
            self.rebalance_perpetual(
                order_id=order_id, target_quantity=ZERO, price=price, rules=rules,
                explicit_rate=explicit_rate, implicit_rate=implicit_rate, reason=reason,
            )
        finally:
            self._defer_episode_until_funding = False
            self._protective_operation = False
            self.phase = Phase.PROTECTIVE
        self.complete_phase()

    def _liquidate_if_observed(self, checkpoint: str) -> bool:
        if self.state.perpetual_quantity == 0 or self.margin_equity() > self.maintenance():
            return False
        before = self.state_digest()
        before_nav = self.nav()
        quantity = self.state.perpetual_quantity
        price = self.state.perpetual_mark
        realized = abs(quantity) * (Decimal("1") if quantity > 0 else Decimal("-1")) * (
            price - (self.state.average_perpetual_entry or ZERO)
        )
        self.state.realized_pnl += realized
        self.state.isolated_collateral += realized
        fee = abs(quantity) * price * self.liquidation_fee_rate
        self.state.liquidation_costs += fee
        self.state.explicit_costs += fee
        self.state.isolated_collateral -= fee
        if self.state.isolated_collateral < 0:
            self.state.liabilities += -self.state.isolated_collateral
            self.state.isolated_collateral = ZERO
        self.state.quote_cash += self.state.isolated_collateral
        self.state.isolated_collateral = ZERO
        self.state.perpetual_quantity = ZERO
        self.state.average_perpetual_entry = None
        self.state.allocated_initial_margin = ZERO
        self.state.margin_state = "liquidated"
        self._invalidate(f"observed_liquidation_{checkpoint}")
        self._terminal = True
        if checkpoint in {"open", "gap_open"}:
            self._funding_membership_removed = True
        after = self.state_digest()
        liquidation_fill_digest = self._record("fill", {
            "fill_id": f"liquidation:{self.event_sequence}", "order_id": "liquidation",
            "fill_at": self.timestamp, "instrument": "BTCUSDT_USD_M_perpetual",
            "signed_quantity": -quantity, "accounting_fill_price": price,
            "explicit_fee_native": fee, "explicit_fee_asset": "quote",
            "explicit_fee_quote_equivalent": fee, "implicit_cost_quote": ZERO,
            "post_fill_position": ZERO,
        }, before, after, before_nav=before_nav, after_nav=self.nav(),
            expected_nav_change=-fee)
        if self._episode is not None:
            self._episode.exit_fill_digests.append(liquidation_fill_digest)
            self._episode.source_digests.append(self.current_lineage.source_digest)
            self._episode.rules_digests.append(self.current_lineage.rules_digest)
            self._close_episode(fee, "observed_liquidation")
        return True

    def post_fill_margin(self) -> str:
        self._require(Phase.POST_FILL_MARGIN)
        self._phase_work_done = True
        if self._liquidate_if_observed("post_fill"):
            self.complete_phase()
            return "liquidated"
        if self.state.perpetual_quantity and self.margin_equity(planning=True) < self.maintenance() * 2:
            self.state.margin_state = "planning_buffer_breach"
            self.complete_phase()
            return self.state.margin_state
        self.state.margin_state = "open" if self.state.perpetual_quantity else "flat"
        self.complete_phase()
        return self.state.margin_state

    def intrabar(
        self, *, low: Decimal, high: Decimal, close: Decimal,
        spot_close: Decimal | None = None,
    ) -> None:
        self._require(Phase.INTRABAR)
        self._phase_work_done = True
        if min(low, high, close) <= 0 or low > high:
            raise LedgerError("invalid intrabar marks")
        if self.state.perpetual_quantity > 0:
            self._mark(perpetual=low)
        elif self.state.perpetual_quantity < 0:
            self._mark(perpetual=high)
        if self._liquidate_if_observed("intrabar"):
            if spot_close is not None:
                self._mark(spot=spot_close)
            self.complete_phase()
            return
        self._mark(perpetual=close)
        self._liquidate_if_observed("close")
        if spot_close is not None:
            self._mark(spot=spot_close)
        self.complete_phase()

    def handle_gap(
        self, *, next_spot: Decimal | None, next_perpetual: Decimal | None,
        spot_rules: InstrumentRules | None, perp_rules: InstrumentRules | None,
        severe_explicit: Decimal, severe_implicit: Decimal, missing_funding: bool = False,
    ) -> None:
        self._require(Phase.PROTECTIVE)
        if self.state.spot_quantity == 0 and self.state.perpetual_quantity == 0:
            before = self.state_digest()
            nav = self.nav()
            self.state.high_water_nav = nav
            self.state.utc_day_start_nav = nav
            self.state.daily_entries_disabled = False
            self.state.drawdown_entries_disabled = False
            self.state.entries_disabled = False
            self.state.margin_state = "flat"
            self._record("diagnostic", {
                "diagnostic_id": f"gap-flat-reset:{self.event_sequence}",
                "timestamp": self.timestamp, "kind": "flat_segment_reset",
                "quantity": ZERO, "cash_effect": ZERO,
                "reason": "missing_bar_while_flat",
            }, before, self.state_digest())
            self.complete_phase()
            return
        self._invalidate(
            "missing_funding_while_exposed" if missing_funding else "missing_bar_while_exposed"
        )
        if ((self.state.spot_quantity and next_spot is None)
                or (self.state.perpetual_quantity and next_perpetual is None)):
            self.state.margin_state = "unknown"
            self.complete_phase()
            return
        if next_spot is not None:
            self._mark(spot=next_spot)
        if next_perpetual is not None:
            self._mark(perpetual=next_perpetual)
            if self._liquidate_if_observed("gap_open"):
                self.complete_phase()
                return
        if self.state.perpetual_quantity:
            assert perp_rules is not None and next_perpetual is not None
            self.protective_flatten_perpetual(
                order_id="gap:perp", price=next_perpetual, rules=perp_rules,
                explicit_rate=severe_explicit, implicit_rate=severe_implicit,
                reason="gap_neutralization",
            )
        if self.state.spot_quantity:
            assert spot_rules is not None and next_spot is not None
            self.phase = Phase.ORDERS
            self._protective_operation = True
            try:
                self.spot_fill(
                    order_id="gap:spot", requested_delta=-self.state.spot_quantity,
                    filled_quantity=-self.state.spot_quantity, price=next_spot,
                    rules=spot_rules, explicit_rate=severe_explicit,
                    implicit_rate=severe_implicit, reason="gap_neutralization",
                )
            finally:
                self._protective_operation = False
                self.phase = Phase.PROTECTIVE
        self.complete_phase()

    def atomic_pair_entry(
        self, *, order_id: str, requested_spot: Decimal, spot_filled: Decimal,
        perpetual_filled_abs: Decimal, spot_price: Decimal, perpetual_price: Decimal,
        spot_rules: InstrumentRules, perp_rules: InstrumentRules,
        explicit_rate: Decimal, implicit_rate: Decimal,
        severe_explicit: Decimal, severe_implicit: Decimal,
    ) -> bool:
        self._require(Phase.ORDERS)
        if self.mandate_mode != "delta_neutral":
            raise LedgerError("atomic pair entry requires delta-neutral mandate")
        if order_id in self._seen_ids["order"] or order_id in self._pair_ids:
            raise LedgerError(f"duplicate order_id: {order_id}")

        def mutate() -> bool:
            self._pair_operation = True
            # Preflight exact zero-inventory neutralization under quote fees.
            if spot_rules.fee_asset == "third" or perp_rules.fee_asset != "quote":
                raise LedgerError("atomic pair preflight requires quote/base spot and quote perp fees")
            rounded_spot = spot_rules.quantity(requested_spot)
            spot_rules.validate(rounded_spot, spot_price)
            spot_rules.validate(spot_filled, spot_price)
            if spot_filled <= 0 or spot_filled > rounded_spot:
                raise LedgerError("invalid atomic-pair first-leg fill")
            entry_quote_fee = explicit_rate if spot_rules.fee_asset == "quote" else ZERO
            entry_cash = spot_filled * spot_price * (Decimal("1") + entry_quote_fee + implicit_rate)
            entry_net = (
                spot_filled * (Decimal("1") - explicit_rate)
                if spot_rules.fee_asset == "base" else spot_filled
            )
            if spot_rules.fee_asset == "base":
                neutral_gross = spot_rules.quantity(entry_net / (Decimal("1") + severe_explicit))
                if neutral_gross + neutral_gross * severe_explicit != entry_net:
                    raise LedgerError("atomic-pair base-fee neutralization cannot leave exact zero BTC")
            else:
                neutral_gross = entry_net
            spot_rules.validate(neutral_gross, spot_price)
            severe_proceeds = neutral_gross * spot_price * (
                Decimal("1") - (severe_explicit if spot_rules.fee_asset == "quote" else ZERO)
                - severe_implicit
            )
            if self.state.quote_cash < entry_cash or severe_proceeds < 0:
                raise LedgerError("atomic-pair neutralization preflight failed")
            if perpetual_filled_abs:
                perp_rules.validate(-perpetual_filled_abs, perpetual_price)
                perp_margin = perpetual_filled_abs * perpetual_price / self.leverage
                perp_cost = perpetual_filled_abs * perpetual_price * (
                    explicit_rate + implicit_rate
                )
                if self.state.quote_cash - entry_cash < perp_margin or perp_margin < perp_cost:
                    raise LedgerError("atomic-pair second-leg funding preflight failed")
            self.spot_fill(
                order_id=f"{order_id}:spot", requested_delta=requested_spot,
                filled_quantity=spot_filled, price=spot_price, rules=spot_rules,
                explicit_rate=explicit_rate, implicit_rate=implicit_rate,
            )
            net_spot = self.state.spot_quantity
            if perpetual_filled_abs:
                self.rebalance_perpetual(
                    order_id=f"{order_id}:perp", target_quantity=-perpetual_filled_abs,
                    price=perpetual_price, rules=perp_rules,
                    explicit_rate=explicit_rate, implicit_rate=implicit_rate,
                )
            spot_notional = net_spot * spot_price
            perp_notional = abs(self.state.perpetual_quantity) * perpetual_price
            mismatch = abs(spot_notional - perp_notional) / max(spot_notional, perp_notional)
            if self.state.perpetual_quantity and mismatch <= Decimal("0.01"):
                self._pair_operation = False
                return True
            self._invalidate("atomic_pair_leg_failure")
            if self.state.perpetual_quantity:
                self.rebalance_perpetual(
                    order_id=f"{order_id}:neutralize-perp", target_quantity=ZERO,
                    price=perpetual_price, rules=perp_rules,
                    explicit_rate=severe_explicit, implicit_rate=severe_implicit,
                    reason="atomic_pair_neutralization",
                )
            if self.state.spot_quantity:
                if spot_rules.fee_asset == "base":
                    neutral_quantity = spot_rules.quantity(
                        self.state.spot_quantity / (Decimal("1") + severe_explicit)
                    )
                    if neutral_quantity + neutral_quantity * severe_explicit != self.state.spot_quantity:
                        raise LedgerError("base-fee neutralization would leave BTC dust")
                else:
                    neutral_quantity = self.state.spot_quantity
                self.spot_fill(
                    order_id=f"{order_id}:neutralize-spot",
                    requested_delta=-neutral_quantity,
                    filled_quantity=-neutral_quantity, price=spot_price,
                    rules=spot_rules, explicit_rate=severe_explicit,
                    implicit_rate=severe_implicit, reason="atomic_pair_neutralization",
                )
            self._pair_operation = False
            return False

        try:
            result = self._transaction(mutate)
            self._pair_ids.add(order_id)
            return result
        except LedgerError as exc:
            self.record_unfilled_order(
                order_id=order_id, instrument="BTC_spot_perpetual_pair",
                requested_quantity=requested_spot,
                rounded_quantity=spot_rules.quantity(requested_spot), status="rejected",
                reason=str(exc), price_bound=max(spot_price, perpetual_price),
            )
            raise

    def atomic_pair_close(
        self, *, order_id: str, requested_spot_gross: Decimal,
        spot_filled_gross: Decimal, perpetual_filled_abs: Decimal,
        spot_price: Decimal, perpetual_price: Decimal,
        severe_spot_price: Decimal, severe_perpetual_price: Decimal | None,
        worst_permitted_severe_perpetual_price: Decimal,
        post_spot_mark: Decimal, post_perpetual_mark: Decimal,
        valuation_timestamp: str, spot_rules: InstrumentRules,
        perp_rules: InstrumentRules, adapter: str = "candle_OHLC",
        full_close: bool = False,
        cartesian_outcomes: tuple[PairCloseCartesianOutcome, ...] | None = None,
        spot_source_digest: str | None = None,
        perpetual_source_digest: str | None = None,
    ) -> bool:
        """Execute the E0-v3 spot-first Cartesian close without fill rollback."""
        self._require(Phase.ORDERS)
        if self.mandate_mode != "delta_neutral":
            raise LedgerError("atomic pair close requires delta-neutral mandate")
        if order_id in self._seen_ids["order"] or order_id in self._pair_ids:
            raise LedgerError(f"duplicate order_id: {order_id}")
        if self.state.spot_quantity <= 0 or self.state.perpetual_quantity >= 0:
            raise LedgerError("pair close requires existing long-spot short-perpetual pair")
        self._validate_rules(spot_rules)
        self._validate_rules(perp_rules)
        if perp_rules.fee_asset != "quote" or spot_rules.fee_asset == "third":
            raise LedgerError("pair close supports quote/base spot and quote perpetual fees")
        if valuation_timestamp != self.timestamp:
            raise LedgerError("pair-close valuation timestamp must equal shared arrival")
        for named_digest in (spot_source_digest, perpetual_source_digest):
            if named_digest is None or not re.fullmatch(r"[0-9a-f]{64}", named_digest):
                raise LedgerError("independent leg source digests are required")
        if min(spot_price, perpetual_price, severe_spot_price,
               worst_permitted_severe_perpetual_price,
               post_spot_mark, post_perpetual_mark) <= 0:
            raise LedgerError("pair-close prices and marks must be positive")
        if adapter == "candle_OHLC" and (
            severe_spot_price != spot_price
            or (
                severe_perpetual_price is not None
                and severe_perpetual_price != perpetual_price
            )
        ):
            raise LedgerError("candle severe execution must use the exact same instrument open")
        self._validate_cost_rates(
            explicit_rate=self.cost_schedule.ordinary_explicit_rate,
            implicit_rate=self.cost_schedule.ordinary_implicit_rate, reason="ordinary",
        )

        incoming_spot = self.state.spot_quantity
        incoming_short = abs(self.state.perpetual_quantity)
        requested_input = spot_rules.quantity(requested_spot_gross)
        fee_multiplier = (
            Decimal("1") + self.cost_schedule.ordinary_explicit_rate
            if spot_rules.fee_asset == "base" else Decimal("1")
        )
        maximum_full_gross = spot_rules.quantity(incoming_spot / fee_multiplier)
        if full_close:
            if requested_spot_gross != incoming_spot:
                raise LedgerError("declared full close must request actual spot inventory")
            requested = maximum_full_gross
        else:
            requested = requested_input
        if requested <= 0:
            self.record_unfilled_order(
                order_id=f"{order_id}:spot", instrument=spot_rules.instrument,
                requested_quantity=requested_spot_gross, rounded_quantity=requested,
                status="rejected", reason="spot close quantized to zero", price_bound=spot_price,
            )
            return False
        spot_rules.validate(requested, spot_price)

        def reduction(gross: Decimal) -> Decimal:
            return gross * fee_multiplier

        if reduction(requested) > incoming_spot:
            raise LedgerError("spot close plus base fee exceeds inventory")
        if full_close and incoming_spot - reduction(requested) != 0:
            raise LedgerError("full pair close would leave spot dust")
        if adapter == "candle_OHLC":
            if spot_filled_gross not in {ZERO, requested}:
                raise LedgerError("candle pair close cannot partially fill spot")
            spot_outcomes = (ZERO, requested)
        elif adapter == "qualified_quote_or_L2":
            if not cartesian_outcomes:
                raise LedgerError("qualified adapter requires priced Cartesian outcomes")
            outcome_keys = [canonical_json(row) for row in cartesian_outcomes]
            if len(set(outcome_keys)) != len(outcome_keys):
                raise LedgerError("duplicate Cartesian outcome")
            cartesian_outcomes = tuple(
                row for _, row in sorted(zip(outcome_keys, cartesian_outcomes), key=lambda item: item[0])
            )
            spot_outcomes = tuple(sorted({row.spot_gross_fill for row in cartesian_outcomes}))
            if spot_filled_gross not in spot_outcomes:
                raise LedgerError("realized spot fill is absent from Cartesian outcomes")
            if ZERO not in spot_outcomes or requested not in spot_outcomes:
                raise LedgerError("Cartesian spot outcomes omit zero or full endpoint")
        else:
            raise LedgerError("unsupported pair-close adapter")

        ordinary_explicit = self.cost_schedule.ordinary_explicit_rate
        ordinary_implicit = self.cost_schedule.ordinary_implicit_rate
        severe_explicit = self.cost_schedule.severe_explicit_rate
        severe_implicit = self.cost_schedule.severe_implicit_rate
        bound_cartesian_outcomes: list[PairCloseCartesianOutcome] = []
        def semantic_settings() -> dict[str, Any]:
            mandate_path = "config/mandates/retail-btc-delta-neutral-research-v1.json"
            return {
                "adapter_id": adapter, "scenario_id": self.run_lineage.scenario_id,
                "selected_mandate_path": mandate_path,
                "selected_mandate_id": "retail-btc-delta-neutral-research-v1",
                "selected_mandate_exact_file_sha256": self.run_lineage.mandate_digest,
                "execution_config_exact_file_sha256": self.run_lineage.execution_config_digest,
                "spot_rules_digest": digest(spot_rules),
                "perpetual_rules_digest": digest(perp_rules),
                "spot_fee_policy_digest": digest({
                    "asset": spot_rules.fee_asset,
                    "ordinary": ordinary_explicit, "severe": severe_explicit,
                }),
                "perpetual_fee_policy_digest": digest({
                    "asset": perp_rules.fee_asset,
                    "ordinary": ordinary_explicit, "severe": severe_explicit,
                }),
                "severe_price_and_cost_bound_digest": digest({
                    "spot_price": severe_spot_price,
                    "perpetual_price": worst_permitted_severe_perpetual_price,
                    "explicit": severe_explicit, "implicit": severe_implicit,
                }),
                "mismatch_limit": Decimal("0.01"), "arrival_timestamp": self.timestamp,
                "source_digests": [spot_source_digest, perpetual_source_digest],
                "cartesian_outcome_set": bound_cartesian_outcomes,
                "cartesian_outcome_set_digest": digest(bound_cartesian_outcomes),
            }
        average_entry = self.state.average_perpetual_entry or ZERO
        q0 = incoming_short
        c0 = self.state.isolated_collateral
        im0 = self.state.allocated_initial_margin

        for gross in spot_outcomes:
            if gross < 0 or gross > requested or gross != spot_rules.quantity(gross):
                raise LedgerError("invalid Cartesian spot outcome")
            r_value = reduction(gross)
            if r_value > incoming_spot or r_value > q0:
                raise LedgerError("Cartesian spot reduction exceeds matched incoming pair")
            target_q = perp_rules.quantity(r_value)
            if adapter == "candle_OHLC":
                priced_outcomes = (
                    PairCloseCartesianOutcome(
                        gross, spot_price, ZERO, perpetual_price,
                        worst_permitted_severe_perpetual_price,
                    ),
                    PairCloseCartesianOutcome(
                        gross, spot_price, target_q, perpetual_price,
                        worst_permitted_severe_perpetual_price,
                    ),
                )
            else:
                priced_outcomes = tuple(
                    row for row in cartesian_outcomes or () if row.spot_gross_fill == gross
                )
                if not priced_outcomes:
                    raise LedgerError("missing Cartesian perpetual outcomes for spot reduction")
                quantities = {row.perpetual_fill for row in priced_outcomes}
                if ZERO not in quantities or target_q not in quantities:
                    raise LedgerError("Cartesian outcomes omit zero or full endpoint")
            for outcome in priced_outcomes:
                bound_cartesian_outcomes.append(outcome)
                q_value = outcome.perpetual_fill
                if gross:
                    spot_rules.validate(gross, outcome.spot_execution_price)
                if q_value < 0 or q_value > target_q or q_value != perp_rules.quantity(q_value):
                    raise LedgerError("invalid Cartesian perpetual outcome")
                if q_value:
                    perp_rules.validate(q_value, outcome.perpetual_execution_price)
                residual = r_value - q_value
                cpre = c0 + q_value * (average_entry - outcome.perpetual_execution_price)
                ordinary_cost = q_value * outcome.perpetual_execution_price * (
                    ordinary_explicit + ordinary_implicit
                )
                if cpre < ordinary_cost:
                    raise LedgerError("ordinary perpetual close fee is not collateral-funded")
                cpre -= ordinary_cost
                release = min(im0 * q_value / q0, max(cpre, ZERO)) if q0 else ZERO
                c1 = cpre - release
                if residual:
                    if outcome.severe_residual_price > worst_permitted_severe_perpetual_price:
                        raise LedgerError("Cartesian severe price exceeds frozen worst bound")
                    perp_rules.validate(residual, outcome.severe_residual_price)
                    severe_cost = residual * outcome.severe_residual_price * (
                        severe_explicit + severe_implicit
                    )
                    if c1 + residual * (
                        average_entry - outcome.severe_residual_price
                    ) < severe_cost:
                        raise LedgerError("severe residual fee is not collateral-funded")

        chosen_reduction = reduction(spot_filled_gross)
        if adapter == "qualified_quote_or_L2":
            chosen_rows = tuple(
                row for row in cartesian_outcomes or ()
                if row.spot_gross_fill == spot_filled_gross
                and row.perpetual_fill == perpetual_filled_abs
            )
            if not chosen_rows:
                raise LedgerError("realized perpetual fill is absent from Cartesian outcomes")
            if not any(
                row.spot_execution_price == spot_price
                and row.perpetual_execution_price == perpetual_price
                and (
                    perpetual_filled_abs == chosen_reduction
                    or severe_perpetual_price is None
                    or row.severe_residual_price == severe_perpetual_price
                )
                for row in chosen_rows
            ):
                raise LedgerError("realized prices are absent from Cartesian outcome")
        if severe_perpetual_price is not None and (
            severe_perpetual_price > worst_permitted_severe_perpetual_price
        ):
            raise LedgerError("actual severe price exceeds frozen worst bound")
        chosen_target = perp_rules.quantity(chosen_reduction)
        if perpetual_filled_abs < 0 or perpetual_filled_abs > chosen_target:
            raise LedgerError("perpetual close exceeds actual spot reduction")
        if adapter == "candle_OHLC" and perpetual_filled_abs not in {ZERO, chosen_target}:
            raise LedgerError("candle pair close cannot partially fill perpetual")

        if spot_filled_gross == ZERO:
            self.record_unfilled_order(
                order_id=f"{order_id}:spot", instrument=spot_rules.instrument,
                requested_quantity=requested_spot_gross, rounded_quantity=requested,
                status="rejected", reason="spot first leg did not fill", price_bound=spot_price,
            )
            self._pair_ids.add(order_id)
            return False

        self._pair_operation = True
        try:
            spot_before = self.state.spot_quantity
            self.spot_fill(
                order_id=f"{order_id}:spot", requested_delta=-requested,
                filled_quantity=-spot_filled_gross, price=spot_price, rules=spot_rules,
                explicit_rate=ordinary_explicit, implicit_rate=ordinary_implicit,
                adapter=adapter, reason="pair_close_intended_spot",
            )
            actual_reduction = spot_before - self.state.spot_quantity
            if self._liquidate_if_observed("post_pair_spot_fill"):
                self._invalidate("pair_close_liquidated_after_spot_fill")
                self._pair_ids.add(order_id)
                return False
            target_close = perp_rules.quantity(actual_reduction)
            if perpetual_filled_abs:
                self.rebalance_perpetual(
                    order_id=f"{order_id}:perp", target_quantity=(
                        self.state.perpetual_quantity + perpetual_filled_abs
                    ), price=perpetual_price, rules=perp_rules,
                    explicit_rate=ordinary_explicit, implicit_rate=ordinary_implicit,
                    reason="pair_close_intended_perpetual",
                    reported_requested_quantity=actual_reduction,
                    reported_rounded_quantity=target_close,
                )
                if self._terminal:
                    self._pair_ids.add(order_id)
                    return False
            else:
                self.record_unfilled_order(
                    order_id=f"{order_id}:perp", instrument=perp_rules.instrument,
                    requested_quantity=target_close, rounded_quantity=target_close,
                    status="rejected", reason="perpetual intended leg did not fill",
                    price_bound=perpetual_price,
                )
            residual = actual_reduction - perpetual_filled_abs
            if residual:
                if severe_perpetual_price is None:
                    self._invalidate("pair_close_pending_forced_buy_to_close")
                    self.state.margin_state = "invalid_unknown_pending_forced_buy_to_close"
                    self.state.pending_forced_perpetual_buy_to_close = residual
                    self.state.pending_pair_origin_segment = self.current_lineage.segment_id
                    self._pending_pair_context = {
                        "origin_segment_id": self.current_lineage.segment_id,
                        "spot_source_digest": spot_source_digest,
                        "perpetual_source_digest": perpetual_source_digest,
                        "semantic_run_settings": semantic_settings(),
                    }
                    pending_state = self.state_digest()
                    settings = semantic_settings()
                    self._record("diagnostic", {
                        "diagnostic_id": f"{order_id}:pending", "timestamp": self.timestamp,
                        "kind": "pair_close_pending", "quantity": actual_reduction,
                        "cash_effect": ZERO, "reason": "same_timestamp_severe_price_missing",
                        "actual_spot_inventory_reduction": actual_reduction,
                        "intended_perpetual_filled_quantity": perpetual_filled_abs,
                        "created_residual_naked_short_quantity": residual,
                        "spot_leg_source_digest": spot_source_digest,
                        "perpetual_leg_source_digest": perpetual_source_digest,
                        "semantic_run_settings_digest": digest(settings),
                        "semantic_run_settings": settings,
                    }, pending_state, pending_state)
                    self._pair_ids.add(order_id)
                    return False
                self.rebalance_perpetual(
                    order_id=f"{order_id}:severe-residual",
                    target_quantity=self.state.perpetual_quantity + residual,
                    price=severe_perpetual_price, rules=perp_rules,
                    explicit_rate=severe_explicit, implicit_rate=severe_implicit,
                    reason="pair_close_residual_neutralization",
                )
                if self._terminal:
                    self._pair_ids.add(order_id)
                    return False
            self._mark(spot=post_spot_mark, perpetual=post_perpetual_mark)
            remaining_spot = self.state.spot_quantity
            remaining_short = abs(self.state.perpetual_quantity)
            quantity_denominator = max(remaining_spot, remaining_short)
            quantity_mismatch = (
                ZERO if quantity_denominator == 0 else
                abs(remaining_spot - remaining_short) / quantity_denominator
            )
            spot_notional = remaining_spot * post_spot_mark
            perp_notional = remaining_short * post_perpetual_mark
            notional_denominator = max(spot_notional, perp_notional)
            notional_mismatch = (
                ZERO if notional_denominator == 0 else
                abs(spot_notional - perp_notional) / notional_denominator
            )
            valid = quantity_mismatch <= Decimal("0.01") and notional_mismatch <= Decimal("0.01")
            if not valid:
                # One non-recursive whole-pair severe attempt, preserving spot-first commits.
                try:
                    terminal_during_whole = False
                    if remaining_spot:
                        if spot_rules.fee_asset == "base":
                            severe_spot_gross = spot_rules.quantity(
                                remaining_spot / (Decimal("1") + severe_explicit)
                            )
                            if severe_spot_gross + severe_spot_gross * severe_explicit != remaining_spot:
                                raise LedgerError("severe whole-pair spot close leaves dust")
                        else:
                            severe_spot_gross = remaining_spot
                        self.spot_fill(
                            order_id=f"{order_id}:severe-whole-spot",
                            requested_delta=-severe_spot_gross,
                            filled_quantity=-severe_spot_gross, price=severe_spot_price,
                            rules=spot_rules, explicit_rate=severe_explicit,
                            implicit_rate=severe_implicit,
                            reason="pair_close_whole_neutralization",
                        )
                        terminal_during_whole = self._liquidate_if_observed(
                            "post_severe_pair_spot_fill"
                        )
                        if terminal_during_whole:
                            raise LedgerError("terminal liquidation during severe whole-pair close")
                    if remaining_short and not self._terminal:
                        if severe_perpetual_price is None:
                            raise LedgerError("no same-timestamp severe perpetual price")
                        self.rebalance_perpetual(
                            order_id=f"{order_id}:severe-whole-perp", target_quantity=ZERO,
                            price=severe_perpetual_price, rules=perp_rules,
                            explicit_rate=severe_explicit, implicit_rate=severe_implicit,
                            reason="pair_close_whole_neutralization",
                        )
                    valid = (
                        self.state.spot_quantity == 0
                        and self.state.perpetual_quantity == 0
                    )
                except LedgerError:
                    valid = False
                if not valid:
                    self._invalidate("pair_close_remaining_pair_mismatch")
                    if not self._terminal:
                        self.state.margin_state = "invalid_unknown_pending_forced_buy_to_close"
                        self.state.pending_forced_perpetual_buy_to_close = abs(
                            self.state.perpetual_quantity
                        )
            pair_settings = semantic_settings()
            before = self.state_digest()
            self._record("diagnostic", {
                "diagnostic_id": f"{order_id}:completion", "timestamp": self.timestamp,
                "kind": "pair_close_completion", "quantity": actual_reduction,
                "cash_effect": ZERO, "reason": "valid" if valid else "mismatch",
                "actual_spot_inventory_reduction": actual_reduction,
                "intended_perpetual_filled_quantity": perpetual_filled_abs,
                "created_residual_naked_short_quantity": residual,
                "remaining_pair_quantity_mismatch": quantity_mismatch,
                "remaining_pair_notional_mismatch": notional_mismatch,
                "spot_leg_source_digest": spot_source_digest,
                "perpetual_leg_source_digest": perpetual_source_digest,
                "valuation_timestamp": valuation_timestamp,
                "semantic_run_settings_digest": digest(pair_settings),
                "semantic_run_settings": pair_settings,
            }, before, before)
            self._pair_ids.add(order_id)
            return valid
        finally:
            self._pair_operation = False

    def resolve_pending_pair_close(
        self, *, order_id: str, price: Decimal, rules: InstrumentRules,
        spot_mark: Decimal, perpetual_mark: Decimal, valuation_timestamp: str,
        spot_source_digest: str, perpetual_source_digest: str,
    ) -> bool:
        """Make the single delayed severe buy-to-close permitted by E0-v3."""
        self._require(Phase.PROTECTIVE)
        pending = self.state.pending_forced_perpetual_buy_to_close
        if pending <= 0:
            raise LedgerError("no pending forced pair-close safety intention")
        if self.terminal_timestamp is not None and (self.timestamp or "") > self.terminal_timestamp:
            raise LedgerError("pending close is outside frozen terminal boundary")
        if valuation_timestamp != self.timestamp:
            raise LedgerError("delayed valuation timestamp must equal current event")
        for value in (spot_source_digest, perpetual_source_digest):
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise LedgerError("delayed close source digest must be SHA-256")
        self.phase = Phase.ORDERS
        self._protective_operation = True
        crossed_segment = (
            self.state.pending_pair_origin_segment is not None
            and self.current_lineage.segment_id != self.state.pending_pair_origin_segment
        )
        try:
            self.rebalance_perpetual(
                order_id=order_id,
                target_quantity=self.state.perpetual_quantity + pending,
                price=price, rules=rules,
                explicit_rate=self.cost_schedule.severe_explicit_rate,
                implicit_rate=self.cost_schedule.severe_implicit_rate,
                reason="pair_close_delayed_neutralization",
            )
            self.state.pending_forced_perpetual_buy_to_close = ZERO
            self.state.pending_pair_origin_segment = None
        finally:
            self._protective_operation = False
            self.phase = Phase.PROTECTIVE
        if crossed_segment:
            nav = self.nav()
            self.state.high_water_nav = nav
            self.state.utc_day_start_nav = nav
            self.state.daily_entries_disabled = False
            self.state.drawdown_entries_disabled = False
            self.state.entries_disabled = False
        self._mark(spot=spot_mark, perpetual=perpetual_mark)
        context = self._pending_pair_context or {}
        remaining_spot = self.state.spot_quantity
        remaining_short = abs(self.state.perpetual_quantity)
        quantity_denominator = max(remaining_spot, remaining_short)
        quantity_mismatch = (
            ZERO if quantity_denominator == 0 else
            abs(remaining_spot - remaining_short) / quantity_denominator
        )
        spot_notional = remaining_spot * spot_mark
        perp_notional = remaining_short * perpetual_mark
        notional_denominator = max(spot_notional, perp_notional)
        notional_mismatch = (
            ZERO if notional_denominator == 0 else
            abs(spot_notional - perp_notional) / notional_denominator
        )
        valid = quantity_mismatch <= Decimal("0.01") and notional_mismatch <= Decimal("0.01")
        if not valid:
            self._invalidate("delayed_pair_close_remaining_mismatch")
            self.state.margin_state = "invalid_unknown_pending_forced_buy_to_close"
        before = self.state_digest()
        settings = context.get("semantic_run_settings", {})
        self._record("diagnostic", {
            "diagnostic_id": f"{order_id}:completion", "timestamp": self.timestamp,
            "kind": "pair_close_delayed_completion", "quantity": pending,
            "cash_effect": ZERO, "reason": "resolved" if valid else "remaining_mismatch",
            "created_residual_naked_short_quantity": pending,
            "remaining_pair_quantity_mismatch": quantity_mismatch,
            "remaining_pair_notional_mismatch": notional_mismatch,
            "origin_segment_id": context.get("origin_segment_id"),
            "completion_segment_id": self.current_lineage.segment_id,
            "origin_spot_leg_source_digest": context.get("spot_source_digest"),
            "origin_perpetual_leg_source_digest": context.get("perpetual_source_digest"),
            "spot_leg_source_digest": spot_source_digest,
            "perpetual_leg_source_digest": perpetual_source_digest,
            "valuation_timestamp": valuation_timestamp,
            "semantic_run_settings_digest": digest(settings),
            "semantic_run_settings": settings,
        }, before, before)
        self._pending_pair_context = None
        self.complete_phase()
        return valid

    def finalize_event(self, *, utc_day: str) -> dict[str, Any]:
        self._require(Phase.RECONCILE)
        before = self.state_digest()
        current_nav = self.nav()
        if self.state.utc_day != utc_day:
            raise LedgerError("UTC day does not match event timestamp")
        daily_return = current_nav / self.state.utc_day_start_nav - Decimal("1")
        drawdown = current_nav / self.state.high_water_nav - Decimal("1")
        if daily_return <= Decimal("-0.015") or drawdown <= Decimal("-0.10"):
            if daily_return <= Decimal("-0.015"):
                self.state.daily_entries_disabled = True
            if drawdown <= Decimal("-0.10"):
                self.state.drawdown_entries_disabled = True
            self.state.entries_disabled = (
                self.state.daily_entries_disabled or self.state.drawdown_entries_disabled
            )
        self.state.high_water_nav = max(self.state.high_water_nav, current_nav)
        payload = {
            **self._state_data(), "timestamp": self.timestamp, "NAV": current_nav,
            "spot_BTC": self.state.spot_quantity,
            "perpetual_BTC": self.state.perpetual_quantity,
            "allocated_initial_margin_memo": self.state.allocated_initial_margin,
            "exit_cost_reserve_memo": self.exit_cost_reserve(),
            "realized_PnL": self.state.realized_pnl,
            "unrealized_PnL": (
                ZERO if self.state.perpetual_quantity == 0 else
                self.state.perpetual_quantity * (
                    self.state.perpetual_mark - (self.state.average_perpetual_entry or ZERO)
                )
            ),
            "funding": self.state.funding_pnl,
            "gross_exposure": self.state.spot_quantity * self.state.spot_mark
            + abs(self.state.perpetual_quantity) * self.state.perpetual_mark,
            "net_exposure": self.state.spot_quantity * self.state.spot_mark
            + self.state.perpetual_quantity * self.state.perpetual_mark,
            "margin_equity": self.margin_equity(), "maintenance_requirement": self.maintenance(),
            "state": self.state.margin_state,
        }
        self._record("account", payload, before, self.state_digest())
        self._event_finalized = True
        self._phase_completed = True
        return _canonical(payload)

    def reconcile(self) -> Decimal:
        expected = (
            self.initial_nav + self.state.spot_price_pnl + self.state.perpetual_price_pnl
            + self.state.funding_pnl - self.state.explicit_costs - self.state.implicit_costs
        )
        return self.nav() - expected

    def canonical_ledgers(self) -> dict[str, str]:
        return {
            name: "".join(canonical_json(row) + "\n" for row in rows)
            for name, rows in sorted(self.ledgers.items())
        }

    def run_summary(self) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        for row in self.ledgers["order"]:
            status = str(row["status"])
            statuses[status] = statuses.get(status, 0) + 1
        artifact_names = {
            "decision": "decision_ledger.jsonl", "order": "order_ledger.jsonl",
            "fill": "fill_ledger.jsonl", "funding": "funding_ledger.jsonl",
            "account": "account_ledger.jsonl", "episode": "closed_episode_ledger.jsonl",
        }
        ledgers = self.canonical_ledgers()
        artifact_digests = {
            artifact: hashlib.sha256(ledgers[ledger].encode("utf-8")).hexdigest()
            for ledger, artifact in artifact_names.items()
        }
        summary = {
            **asdict(self.run_lineage),
            "starting_NAV": self.initial_nav,
            "ending_NAV": self.nav(),
            "spot_price_PnL": self.state.spot_price_pnl,
            "perpetual_price_PnL": self.state.perpetual_price_pnl,
            "funding_PnL": self.state.funding_pnl,
            "explicit_costs": self.state.explicit_costs,
            "implicit_costs": self.state.implicit_costs,
            "neutralization_costs": self.state.neutralization_costs,
            "diagnostic_opportunity_cost": ZERO,
            "diagnostic_missed_unfilled_and_unused_rounded_notional": ZERO,
            "accounting_residual": self.reconcile(),
            "rejected_expired_partial_and_unfilled_counts": statuses,
            "unknown_or_invalid_intervals": 1 if self.state.invalidation_reason else 0,
            "artifact_digests": artifact_digests,
            "run_invalidation_reason": self.state.invalidation_reason,
            "actionable_arm_id": "no_trade",
            "historical_rows_accessed": False,
            "metrics_computed": False,
            "strategy_logic_executed": False,
        }
        return _canonical(summary)

    def evidence_bundle(self) -> dict[str, str]:
        """Emit all required E0 artifacts in-memory as exact UTF-8 file payloads."""
        ledgers = self.canonical_ledgers()
        names = {
            "decision": "decision_ledger.jsonl",
            "order": "order_ledger.jsonl",
            "fill": "fill_ledger.jsonl",
            "funding": "funding_ledger.jsonl",
            "account": "account_ledger.jsonl",
            "episode": "closed_episode_ledger.jsonl",
        }
        bundle = {artifact: ledgers[ledger] for ledger, artifact in names.items()}
        bundle["report.json"] = canonical_json(self.run_summary()) + "\n"
        entries = []
        roles = {
            **{artifact: ledger for ledger, artifact in names.items()},
            "report.json": "run_summary",
        }
        for path, content in sorted(bundle.items()):
            encoded = content.encode("utf-8")
            entries.append({
                "path": path, "sha256": hashlib.sha256(encoded).hexdigest(),
                "size_bytes": len(encoded), "semantic_role": roles[path],
            })
        bundle["evidence_manifest.json"] = canonical_json({"artifacts": entries}) + "\n"
        return bundle


__all__ = [
    "CostSchedule", "InstrumentRules", "LedgerError", "LedgerState", "Lineage",
    "PairCloseCartesianOutcome", "Phase", "PhaseError",
    "RunLineage",
    "expected_run_digests",
    "SyntheticDecimalLedger", "canonical_json", "decimal_string", "digest",
    "load_json_no_collisions",
]
