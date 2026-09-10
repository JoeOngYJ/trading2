"""Atomic spot/perpetual pair orchestration for the frozen E1-v14 fixtures."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal, ROUND_DOWN
from types import MappingProxyType
from typing import Any

from . import authorities
from .canonical import as_decimal, canonical_sha256, freeze
from .ledger import _LedgerEngine, _d, _digest, _ds


ZERO = Decimal("0")
ONE = Decimal("1")
TEN_THOUSAND = Decimal("10000")
SPOT = "BTC/USDT"
PERP = "BTCUSDT_USD_M_perpetual"


class PairError(ValueError):
    pass


def _rounded(quantity: Decimal, rule: Mapping[str, Any]) -> Decimal:
    step = as_decimal(rule["step"], "step")
    units = (abs(quantity) / step).to_integral_value(rounding=ROUND_DOWN)
    return (units * step).copy_sign(quantity)


def _valid_rule_quantity(quantity: Decimal, price: Decimal, rule: Mapping[str, Any]) -> bool:
    return (
        quantity != ZERO
        and abs(quantity) <= as_decimal(rule["maximum_quantity"])
        and abs(quantity) * price >= as_decimal(rule["minimum_notional"])
    )


def _levels(snapshot: Mapping[str, Any], side: str) -> tuple[tuple[Decimal, Decimal], ...]:
    if snapshot.get("adapter_status") != "qualified":
        return ()
    raw = snapshot["asks" if side == "buy" else "bids"]
    seen: set[Decimal] = set()
    levels: list[tuple[Decimal, Decimal]] = []
    for price_raw, quantity_raw in raw:
        price = as_decimal(price_raw, "depth price")
        quantity = as_decimal(quantity_raw, "depth quantity")
        if price <= ZERO or quantity <= ZERO or price in seen:
            raise PairError("duplicate or invalid depth level")
        seen.add(price)
        levels.append((price, quantity))
    levels.sort(key=lambda item: item[0], reverse=side == "sell")
    return tuple(levels)


def _depth_fill(
    snapshot: Mapping[str, Any], requested: Decimal, rule: Mapping[str, Any],
    protection_bps: Decimal,
) -> tuple[Decimal, Decimal | None, str]:
    """Derive quantity/VWAP solely from one qualified authority snapshot."""

    if requested == ZERO:
        return ZERO, None, "zero_requested"
    if snapshot.get("adapter_status") != "qualified":
        return ZERO, None, snapshot.get("rejection_reason", "adapter_rejected")
    side = "buy" if requested > ZERO else "sell"
    reference = as_decimal(snapshot["reference_open"], "reference_open")
    bound = reference * (ONE + protection_bps / TEN_THOUSAND) if side == "buy" else reference * (ONE - protection_bps / TEN_THOUSAND)
    remaining = abs(_rounded(requested, rule))
    filled = ZERO
    notional = ZERO
    for price, available in _levels(snapshot, side):
        if (side == "buy" and price > bound) or (side == "sell" and price < bound):
            break
        take = min(remaining, available)
        take = abs(_rounded(take, rule))
        if take == ZERO:
            continue
        filled += take
        notional += take * price
        remaining -= take
        if remaining <= ZERO:
            break
    if filled == ZERO:
        return ZERO, None, "zero_by_price_bound"
    signed = filled.copy_sign(requested)
    return signed, notional / filled, "filled" if filled == abs(_rounded(requested, rule)) else "partial_by_price_bound"


def _permitted_depth_quantities(
    snapshot: Mapping[str, Any], requested: Decimal, rule: Mapping[str, Any],
    protection_bps: Decimal,
) -> tuple[Decimal, ...]:
    """Enumerate every step-quantized fill permitted by bound visible depth."""

    if snapshot.get("adapter_status") != "qualified":
        return (ZERO,)
    actual, _vwap, _status = _depth_fill(snapshot, requested, rule, protection_bps)
    maximum = abs(actual)
    step = as_decimal(rule["step"])
    count = int((maximum / step).to_integral_value(rounding=ROUND_DOWN))
    sign = Decimal(-1) if requested < ZERO else Decimal(1)
    return tuple(sign * step * index for index in range(count + 1))


class _PairEngine:
    __slots__ = ("__ledger", "__pair_rows", "__recovery_attempts")

    def __init__(self, ledger: _LedgerEngine) -> None:
        if not isinstance(ledger, _LedgerEngine):
            raise TypeError("pair engine requires the package ledger")
        self.__ledger = ledger
        self.__pair_rows: list[dict[str, Any]] = []
        self.__recovery_attempts = 0

    @property
    def state(self):
        return self.__ledger.state

    @property
    def phase(self) -> int:
        return self.__ledger.phase

    @property
    def rows(self):
        combined = dict(self.__ledger.rows)
        combined["pair"] = tuple(freeze(row) for row in self.__pair_rows)
        return MappingProxyType(combined)

    @property
    def episodes(self):
        return self.__ledger.episodes

    @property
    def bindings(self):
        return self.__ledger.bindings

    def open_next_interval(self):
        return self.__ledger.open_next_interval()

    def close_interval(self):
        if self.__ledger._spec.adapter != "qualified_l2":
            return self.__ledger.close_interval()
        if self.__ledger.phase not in (5, 7):
            raise RuntimeError("interval is not ready to close")
        if self.__ledger.phase == 5:
            self.__ledger._record_phase(6)
            self.__ledger._record_phase(7)
        self.__ledger._record_phase(8)
        spot = self.__ledger._open_price(SPOT, optional=True)
        perp = self.__ledger._open_price(PERP, optional=True)
        self.__ledger._mark(spot, perp)
        self.__ledger._update_excursion()
        self.__ledger._phase_reconcile()
        result = freeze({"timestamp": self.__ledger._timestamp(), "phase": 9, "terminal": False})
        self.__ledger._phase = 0
        self.__ledger._current = None
        return result

    def terminate(self):
        return self.__ledger.terminate()

    def _snapshots(self) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        current = self.__ledger._current
        if not current or SPOT not in current or PERP not in current:
            raise PairError("pair requires common point-in-time source observations")
        spot, perp = current[SPOT], current[PERP]
        if spot["observed_at"] != perp["observed_at"] or spot["segment_id"] != perp["segment_id"]:
            raise PairError("pair source timestamp/segment mismatch")
        return spot, perp

    def _fill_plan(self, instrument: str, requested: Decimal, *, severe: bool = False):
        rule = self.__ledger._rule(instrument)
        if self.__ledger._spec.adapter == "candle":
            price = self.__ledger._source_price(instrument)
            rounded = _rounded(requested, rule)
            if not _valid_rule_quantity(rounded, price, rule):
                return ZERO, None, "rule_rejected"
            return rounded, price, "filled"
        spot, perp = self._snapshots()
        snapshot = spot if instrument == SPOT else perp
        scenario = authorities.scenario_for(self.__ledger._spec, severe=severe)
        return _depth_fill(snapshot, requested, rule, as_decimal(scenario["price_protection_bps"]))

    def _commit(
        self, instrument: str, quantity: Decimal, price: Decimal, *, severe: bool,
        reason: str, requested: Decimal | None = None,
    ):
        ledger = self.__ledger
        before_fill = ledger.state
        starts = {name: len(ledger._rows[name]) for name in ("decision", "order", "fill")}
        if ledger.phase == 5:
            ledger._record_phase(6)
        ledger._engine_fill(instrument, quantity, price, severe=severe, reason=reason)
        scenario = authorities.scenario_for(ledger._spec, severe=severe)
        for name, start in starts.items():
            for emitted in ledger._rows[name][start:]:
                emitted["scenario_id"] = scenario["scenario_id"]
                emitted["row_digest"] = _digest({key: value for key, value in emitted.items() if key != "row_digest"})
        residual_rate = as_decimal(scenario["residual_impact_bps"]) / TEN_THOUSAND
        residual_cost = abs(quantity) * price * residual_rate
        if residual_cost:
            current = ledger.state
            if instrument == SPOT:
                if current.quote_cash < residual_cost:
                    raise PairError("insufficient quote cash for bound residual impact")
                ledger._state = replace(
                    current, quote_cash=current.quote_cash - residual_cost,
                    implicit_costs=current.implicit_costs + residual_cost,
                )
            else:
                if current.isolated_collateral < residual_cost:
                    raise PairError("insufficient isolated collateral for bound residual impact")
                ledger._state = replace(
                    current, isolated_collateral=current.isolated_collateral - residual_cost,
                    implicit_costs=current.implicit_costs + residual_cost,
                )
            ledger._refresh()
            fill = ledger._rows["fill"][-1]
            existing_implicit = as_decimal(fill["implicit_cost_quote"])
            total_implicit = existing_implicit + residual_cost
            fill["implicit_cost_quote"] = _ds(total_implicit)
            fill["after_state_digest"] = ledger._state_digest()
            explicit = as_decimal(fill["explicit_fee_quote_equivalent"])
            fill["event_accounting_residual"] = _ds(
                (ledger.state.NAV - before_fill.NAV) + explicit + total_implicit
            )
            fill["row_digest"] = _digest({key: value for key, value in fill.items() if key != "row_digest"})
            ledger._last_digest = fill["after_state_digest"]
            if ledger._episode is not None:
                if any(term in reason for term in ("close", "recovery", "residual", "terminal")):
                    ledger._episode.exit_costs += residual_cost
                else:
                    ledger._episode.entry_costs += residual_cost
        order = ledger._rows["order"][-1]
        if requested is not None and requested != quantity:
            order["requested_quantity"] = _ds(requested)
            order["filled_quantity"] = _ds(quantity)
            order["unfilled_quantity"] = _ds(requested - quantity)
            order["status"] = "partial" if ledger._spec.adapter == "qualified_l2" else "filled_rounded"
            order["reason"] = reason
        if ledger._spec.adapter == "qualified_l2":
            snapshot = ledger._current[instrument]
            reference = as_decimal(snapshot["reference_open"])
            bps = as_decimal(authorities.scenario_for(ledger._spec, severe=severe)["price_protection_bps"])
            bound = reference * (ONE + bps / TEN_THOUSAND) if quantity > ZERO else reference * (ONE - bps / TEN_THOUSAND)
            order["price_bound"] = _ds(bound)
        order["row_digest"] = _digest({key: value for key, value in order.items() if key != "row_digest"})
        ledger._margin_checkpoint("post_pair_fill")
        if not ledger.state.terminal:
            ledger._phase = 7
        return freeze(order)

    def _record_preflight(
        self, kind: str, requested: Decimal, outcomes: tuple[Mapping[str, Any], ...],
        selected: tuple[Decimal, Decimal],
    ) -> None:
        selected_key = (_ds(selected[0]), _ds(selected[1]))
        selected_rows = tuple(
            row for row in outcomes
            if (row["spot_filled_quantity"], row["perpetual_filled_quantity"]) == selected_key
        )
        if len(selected_rows) != 1:
            raise PairError("actual selected outcome is not uniquely bound in Cartesian set")
        payload = {
            "kind": kind,
            "requested_quantity": _ds(requested),
            "timestamp": self.__ledger._timestamp(),
            "adapter": self.__ledger._spec.adapter,
            "outcomes": outcomes,
            "outcome_count": len(outcomes),
            "selected_outcome_digest": canonical_sha256(selected_rows[0]),
            "source_digest": self.__ledger._current_source_digest(None),
            "rules_digest": self.__ledger._rules_digest(),
            "scenario_id": authorities.scenario_for(self.__ledger._spec)["scenario_id"],
            "before_event_sequence": self.__ledger._seq,
        }
        payload["outcome_digest"] = canonical_sha256(payload)
        self.__pair_rows.append(payload)

    def _entry_outcomes(self, target: Decimal) -> tuple[Mapping[str, Any], ...]:
        spot_price = self.__ledger._source_price(SPOT)
        perp_price = self.__ledger._source_price(PERP)
        spot_rule, perp_rule = self.__ledger._rule(SPOT), self.__ledger._rule(PERP)
        if self.__ledger._spec.adapter == "candle":
            spot_values = (ZERO, _rounded(target, spot_rule))
        else:
            spot, perp = self._snapshots()
            bps = as_decimal(authorities.scenario_for(self.__ledger._spec)["price_protection_bps"])
            spot_values = _permitted_depth_quantities(spot, target, spot_rule, bps)
        outcomes: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        fee_rate = as_decimal(authorities.scenario_for(self.__ledger._spec)["taker_fee_bps"]) / TEN_THOUSAND
        for spot_q in spot_values:
            if self.__ledger._spec.adapter == "candle":
                perp_values = (ZERO, -_rounded(spot_q, perp_rule)) if spot_q else (ZERO,)
            else:
                _spot, perp = self._snapshots()
                bps = as_decimal(authorities.scenario_for(self.__ledger._spec)["price_protection_bps"])
                perp_values = _permitted_depth_quantities(perp, -spot_q, perp_rule, bps) if spot_q else (ZERO,)
            for perp_q in perp_values:
                spot_outcome_price = spot_price
                perp_outcome_price = perp_price
                if self.__ledger._spec.adapter == "qualified_l2":
                    spot_snapshot, perp_snapshot = self._snapshots()
                    bps = as_decimal(authorities.scenario_for(self.__ledger._spec)["price_protection_bps"])
                    if spot_q:
                        _sq, spot_outcome_price, _ = _depth_fill(spot_snapshot, spot_q, spot_rule, bps)
                    if perp_q:
                        _pq, perp_outcome_price, _ = _depth_fill(perp_snapshot, perp_q, perp_rule, bps)
                row = freeze({
                    "spot_filled_quantity": _ds(spot_q),
                    "perpetual_filled_quantity": _ds(perp_q),
                    "spot_price": _ds(spot_outcome_price if spot_q else ZERO),
                    "perpetual_price": _ds(perp_outcome_price if perp_q else ZERO),
                    "created_residual": _ds(spot_q - abs(perp_q)),
                    "spot_fee_quote": _ds(abs(spot_q) * (spot_outcome_price or ZERO) * fee_rate),
                    "perpetual_fee_quote": _ds(abs(perp_q) * (perp_outcome_price or ZERO) * fee_rate),
                    "severe_recovery_bound": "candle-severe-80bps-rt-v1",
                })
                digest = canonical_sha256(row)
                if digest in seen:
                    raise PairError("duplicate Cartesian outcome digest")
                seen.add(digest)
                outcomes.append(row)
        outcomes.sort(key=canonical_sha256)
        return tuple(outcomes)

    def _close_outcomes(self, reduction: Decimal) -> tuple[Mapping[str, Any], ...]:
        spot_rule, perp_rule = self.__ledger._rule(SPOT), self.__ledger._rule(PERP)
        scenario = authorities.scenario_for(self.__ledger._spec)
        fee_rate = as_decimal(scenario["taker_fee_bps"]) / TEN_THOUSAND
        if self.__ledger._spec.adapter == "candle":
            reductions = (ZERO, abs(_rounded(reduction, spot_rule)))
            spot_snapshot = perp_snapshot = None
            bps = ZERO
        else:
            spot_snapshot, perp_snapshot = self._snapshots()
            bps = as_decimal(scenario["price_protection_bps"])
            reductions = tuple(abs(value) for value in _permitted_depth_quantities(spot_snapshot, -reduction, spot_rule, bps))
        rows: list[Mapping[str, Any]] = []
        for reduced in reductions:
            if self.__ledger._spec.adapter == "candle":
                perp_values = (ZERO, abs(_rounded(reduced, perp_rule))) if reduced else (ZERO,)
                spot_price = self.__ledger._source_price(SPOT) if reduced else ZERO
            else:
                perp_values = tuple(abs(value) for value in _permitted_depth_quantities(perp_snapshot, reduced, perp_rule, bps)) if reduced else (ZERO,)
                _sq, spot_price, _ = _depth_fill(spot_snapshot, -reduced, spot_rule, bps) if reduced else (ZERO, ZERO, "zero")
            for perp_closed in perp_values:
                if self.__ledger._spec.adapter == "candle":
                    perp_price = self.__ledger._source_price(PERP) if perp_closed else ZERO
                else:
                    _pq, perp_price, _ = _depth_fill(perp_snapshot, perp_closed, perp_rule, bps) if perp_closed else (ZERO, ZERO, "zero")
                row = freeze({
                    "spot_filled_quantity": _ds(reduced),
                    "perpetual_filled_quantity": _ds(perp_closed),
                    "spot_price": _ds(spot_price), "perpetual_price": _ds(perp_price),
                    "created_residual": _ds(reduced - perp_closed),
                    "spot_fee_quote": _ds(reduced * spot_price * fee_rate),
                    "perpetual_fee_quote": _ds(perp_closed * perp_price * fee_rate),
                    "severe_recovery_bound": "candle-severe-80bps-rt-v1",
                })
                rows.append(row)
        if len({canonical_sha256(row) for row in rows}) != len(rows):
            raise PairError("duplicate close Cartesian outcome digest")
        return tuple(sorted(rows, key=canonical_sha256))

    def atomic_pair_entry(self, target_quantity: Decimal):
        self.__ledger._pair_ready()
        self.__recovery_attempts = 0
        target = as_decimal(target_quantity, "target_quantity")
        if target <= ZERO or self.state.spot_quantity != ZERO or self.state.perpetual_quantity != ZERO:
            raise PairError("pair entry requires a positive target and a flat account")
        intended_spot = _rounded(target, self.__ledger._rule(SPOT))
        intended_perp = -abs(_rounded(target, self.__ledger._rule(PERP)))
        self.__ledger._check_pair_delta(
            intended_spot, intended_perp,
            self.__ledger._source_price(SPOT), self.__ledger._source_price(PERP),
        )
        spot_q, spot_price, spot_status = self._fill_plan(SPOT, target)
        outcomes = self._entry_outcomes(target)
        if spot_q == ZERO or spot_price is None:
            self._record_preflight("entry", target, outcomes, (ZERO, ZERO))
            return self.__ledger._reject_order(SPOT, target, spot_status)
        perp_requested = -abs(spot_q)
        perp_q, perp_price, perp_status = self._fill_plan(PERP, perp_requested)
        # Delta/cap authorization concerns the intended rounded pair.  Partial
        # adapter outcomes are enumerated and recovered, not rejected as a
        # caller-selected mismatched target.
        self.__ledger._check_pair_delta(
            spot_q, perp_requested, spot_price, self.__ledger._source_price(PERP)
        )
        self._record_preflight("entry", target, outcomes, (spot_q, perp_q))
        # Every nonzero Cartesian residual must be rule-valid under the severe bound.
        perp_rule = self.__ledger._rule(PERP)
        for outcome in outcomes:
            residual = as_decimal(outcome["created_residual"])
            if residual and not _valid_rule_quantity(residual, self.__ledger._source_price(PERP), perp_rule):
                raise PairError("Cartesian severe recovery is not rule-valid")
        spot_order = self._commit(SPOT, spot_q, spot_price, severe=False, reason="pair_entry_spot_first", requested=target)
        if perp_q == ZERO or perp_price is None:
            failed = self.__ledger._reject_order(PERP, perp_requested, perp_status)
            self._recover_entry(spot_q, ZERO, "pair_entry_leg2_zero")
            return freeze({"spot_order": spot_order, "perpetual_order": failed, "recovered": True})
        perp_order = self._commit(PERP, perp_q, perp_price, severe=False, reason="pair_entry_perpetual_second", requested=perp_requested)
        if abs(perp_q) != abs(perp_requested):
            self._recover_entry(spot_q, perp_q, "pair_entry_leg2_partial")
            return freeze({"spot_order": spot_order, "perpetual_order": perp_order, "recovered": True})
        self.__ledger._check_pair_delta(self.state.spot_quantity, self.state.perpetual_quantity, spot_price, perp_price)
        return freeze({"spot_order": spot_order, "perpetual_order": perp_order, "recovered": False})

    def _recover_entry(self, spot_q: Decimal, perp_q: Decimal, reason: str) -> None:
        self.__recovery_attempts += 1
        if self.__recovery_attempts > 1:
            raise PairError("pair recovery is finite and non-recursive")
        if perp_q != ZERO:
            quantity, price, status = self._fill_plan(PERP, -perp_q, severe=True)
            if quantity == ZERO or price is None:
                self.__ledger._reject_order(PERP, -perp_q, status, severe=True)
                self.__ledger._invalidate(reason, pending="forced_perpetual_buy_to_close")
                return
            self._commit(PERP, quantity, price, severe=True, reason="severe_pair_recovery_perpetual_first")
        quantity, price, status = self._fill_plan(SPOT, -spot_q, severe=True)
        if quantity == ZERO or price is None:
            self.__ledger._reject_order(SPOT, -spot_q, status, severe=True)
            self.__ledger._invalidate(reason, pending="forced_spot_sell")
            return
        self._commit(SPOT, quantity, price, severe=True, reason="severe_pair_recovery_spot_second")
        self.__ledger._invalidate(reason)

    def atomic_pair_close(self, target_quantity: Decimal = ZERO):
        self.__ledger._pair_ready()
        self.__recovery_attempts = 0
        target = as_decimal(target_quantity, "target_quantity")
        if target < ZERO or target >= self.state.spot_quantity or self.state.perpetual_quantity >= ZERO:
            raise PairError("pair close target must reduce an existing matched pair")
        reduction = self.state.spot_quantity - target
        spot_q, spot_price, spot_status = self._fill_plan(SPOT, -reduction)
        if spot_q == ZERO or spot_price is None:
            return self.__ledger._reject_order(SPOT, -reduction, spot_status)
        perp_q, perp_price, perp_status = self._fill_plan(PERP, abs(spot_q))
        outcomes = self._close_outcomes(reduction)
        self._record_preflight("close", reduction, outcomes, (abs(spot_q), abs(perp_q)))
        before_inventory = self.state.spot_quantity
        spot_order = self._commit(SPOT, spot_q, spot_price, severe=False, reason="pair_close_spot_first", requested=-reduction)
        actual_reduction = before_inventory - self.state.spot_quantity
        perp_requested = actual_reduction
        if perp_requested != abs(spot_q):
            perp_q, perp_price, perp_status = self._fill_plan(PERP, perp_requested)
        if perp_q == ZERO or perp_price is None:
            failed = self.__ledger._reject_order(PERP, perp_requested, perp_status)
            self._recover_close(actual_reduction, "pair_close_leg2_zero")
            return freeze({"spot_order": spot_order, "perpetual_order": failed, "recovered": True})
        perp_order = self._commit(PERP, perp_q, perp_price, severe=False, reason="pair_close_perpetual_second", requested=perp_requested)
        residual = actual_reduction - perp_q
        if residual > ZERO:
            self._recover_close(residual, "pair_close_leg2_partial")
        if self.state.spot_quantity or self.state.perpetual_quantity:
            try:
                self.__ledger._check_pair_delta(
                    self.state.spot_quantity, self.state.perpetual_quantity,
                    spot_price, perp_price,
                )
            except ValueError:
                self._whole_pair_severe_once("remaining_pair_mismatch")
        return freeze({"spot_order": spot_order, "perpetual_order": perp_order, "recovered": residual > ZERO})

    def _recover_close(self, residual: Decimal, reason: str) -> None:
        self.__recovery_attempts += 1
        if self.__recovery_attempts > 1:
            self.__ledger._invalidate(reason, pending="forced_perpetual_buy_to_close")
            return
        quantity, price, status = self._fill_plan(PERP, residual, severe=True)
        if quantity == ZERO or price is None:
            self.__ledger._reject_order(PERP, residual, status, severe=True)
            self.__ledger._invalidate(reason, pending="forced_perpetual_buy_to_close")
            return
        self._commit(PERP, quantity, price, severe=True, reason="severe_residual_buy_to_close")
        self.__ledger._invalidate(reason)

    def _whole_pair_severe_once(self, reason: str) -> None:
        if self.__recovery_attempts:
            self.__ledger._invalidate(reason, pending="forced_pair_close")
            return
        self.__recovery_attempts = 1
        # E0-v3 close order remains spot first.
        if self.state.spot_quantity:
            q, price, status = self._fill_plan(SPOT, -self.state.spot_quantity, severe=True)
            if q == ZERO or price is None:
                self.__ledger._reject_order(SPOT, -self.state.spot_quantity, status, severe=True)
                self.__ledger._invalidate(reason, pending="forced_pair_close")
                return
            self._commit(SPOT, q, price, severe=True, reason="severe_whole_pair_spot_first")
        if self.state.perpetual_quantity:
            q, price, status = self._fill_plan(PERP, -self.state.perpetual_quantity, severe=True)
            if q == ZERO or price is None:
                self.__ledger._reject_order(PERP, -self.state.perpetual_quantity, status, severe=True)
                self.__ledger._invalidate(reason, pending="forced_perpetual_buy_to_close")
                return
            self._commit(PERP, q, price, severe=True, reason="severe_whole_pair_perpetual_second")
        self.__ledger._invalidate(reason)


def _attach_pair(ledger: _LedgerEngine) -> _PairEngine:
    """Package-private facade hook; no price/depth/outcome/cost input exists."""

    return _PairEngine(ledger)


__all__ = ["PairError"]
