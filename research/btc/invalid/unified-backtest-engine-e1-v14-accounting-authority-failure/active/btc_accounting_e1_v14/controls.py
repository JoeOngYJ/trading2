"""Independent economic controls, gap evidence and derived artifacts for E1-v14."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from .authorities import RunSpec, get_run_spec, source_records
from .canonical import as_decimal, canonical_sha256, freeze
from .ledger import _create_ledger
from .pair import _attach_pair


ZERO = Decimal("0")
CONTROL_IDS = ("flat", "spot_buy_and_hold", "same_timestamp_same_absolute_exposure")


class ControlError(ValueError):
    pass


class _ControlArtifact:
    __slots__ = ("_control_id", "_requested_run_spec_id", "_economic_run_spec_id", "_rows", "_episodes", "_gaps", "_summary", "_artifacts")

    def __init__(
        self, control_id: str, requested_spec: RunSpec, economic_spec: RunSpec,
        rows: Mapping[str, Any], episodes: tuple[Mapping[str, Any], ...],
        gap_rows: tuple[Mapping[str, Any], ...],
    ) -> None:
        self._control_id = control_id
        self._requested_run_spec_id = requested_spec.run_spec_id
        self._economic_run_spec_id = economic_spec.run_spec_id
        self._rows = freeze(rows)
        self._episodes = freeze(episodes)
        self._gaps = freeze(gap_rows)
        account = self._rows.get("account", ())
        fills = self._rows.get("fill", ())
        initial = requested_spec.initial_nav
        final = as_decimal(account[-1]["NAV"]) if account else initial
        turnover = sum(
            (abs(as_decimal(row["signed_quantity"])) * as_decimal(row["accounting_fill_price"]) for row in fills),
            ZERO,
        )
        explicit = sum((as_decimal(row["explicit_fee_quote_equivalent"]) for row in fills), ZERO)
        implicit = sum((as_decimal(row["implicit_cost_quote"]) for row in fills), ZERO)
        summary = {
            "control_id": control_id,
            "requested_run_spec_id": requested_spec.run_spec_id,
            "economic_run_spec_id": economic_spec.run_spec_id,
            "initial_NAV": str(initial), "final_NAV": str(final),
            "net_return": str(final / initial - Decimal("1")),
            "fill_count": len(fills), "episode_count": len(episodes),
            "turnover_quote": str(turnover), "explicit_cost_quote": str(explicit),
            "implicit_cost_quote": str(implicit), "gap_count": len(gap_rows),
            "source_authority_sha256": economic_spec.source["sha256"],
            "execution_authority_sha256": economic_spec.execution_authority["sha256"],
            "mandate_sha256": economic_spec.mandate["sha256"],
        }
        summary["rows_digest"] = canonical_sha256(self._rows)
        summary["episodes_digest"] = canonical_sha256(self._episodes)
        summary["gap_digest"] = canonical_sha256(gap_rows)
        summary["artifact_digest"] = canonical_sha256({key: value for key, value in summary.items() if key != "artifact_digest"})
        self._summary = freeze(summary)
        self._artifacts = freeze({
            "ledgers": {name: {"row_count": len(values), "sha256": canonical_sha256(values)} for name, values in self._rows.items()},
            "episodes": {"row_count": len(self._episodes), "sha256": summary["episodes_digest"]},
            "gaps": {"row_count": len(gap_rows), "sha256": summary["gap_digest"]},
            "summary": self._summary,
        })

    def __setattr__(self, name: str, value: Any) -> None:
        if hasattr(self, name):
            raise TypeError("control artifact is immutable")
        object.__setattr__(self, name, value)

    @property
    def control_id(self) -> str:
        return self._control_id

    @property
    def rows(self):
        return self._rows

    @property
    def episodes(self):
        return self._episodes

    @property
    def summary(self):
        return self._summary

    @property
    def artifacts(self):
        return self._artifacts

    @property
    def gaps(self):
        return self._gaps


def _timestamps(spec: RunSpec) -> tuple[str, ...]:
    return tuple(sorted({row["observed_at"] for row in source_records(spec)}))


def _run_economic(
    requested_spec: RunSpec, economic_spec: RunSpec, control_id: str,
    target_quantity: Decimal,
) -> _ControlArtifact:
    ledger = _create_ledger(economic_spec)
    engine = _attach_pair(ledger) if economic_spec.run_spec_id.startswith("pair_") else ledger
    stamps = _timestamps(economic_spec)
    gap_rows: list[Mapping[str, Any]] = []
    previous_stamp: str | None = None
    for index, expected_stamp in enumerate(stamps):
        before = engine.state
        try:
            opened = engine.open_next_interval()
        except ValueError as exc:
            # Invalid source is a real failed control run, never skipped or
            # searched past.  The artifact records the exact boundary.
            gap_rows.append(freeze({
                "kind": "source_failure", "expected_timestamp": expected_stamp,
                "reason": str(exc), "pending": bool(before.spot_quantity or before.perpetual_quantity),
                "searched_forward": False,
            }))
            break
        stamp = opened["timestamp"]
        if previous_stamp is not None:
            from datetime import datetime, timezone
            prior = datetime.fromisoformat(previous_stamp[:-1] + "+00:00").astimezone(timezone.utc)
            current = datetime.fromisoformat(stamp[:-1] + "+00:00").astimezone(timezone.utc)
            if (current - prior).total_seconds() != 3600:
                filled = before.spot_quantity != ZERO or before.perpetual_quantity != ZERO
                now_flat = engine.state.spot_quantity == ZERO and engine.state.perpetual_quantity == ZERO
                gap_rows.append(freeze({
                    "kind": "exposed_gap" if filled else "flat_gap",
                    "from_timestamp": previous_stamp, "to_timestamp": stamp,
                    "cleanup_filled": bool(filled and now_flat),
                    "reset_after_fill": bool(filled and now_flat),
                    "pending": engine.state.pending_protection,
                    "searched_forward": False,
                    "state": engine.state.state,
                }))
        if index == 0 and control_id != "flat":
            if economic_spec.run_spec_id == "spot_candle_primary":
                engine.submit_spot_target(target_quantity)
            elif economic_spec.run_spec_id == "directional_candle_primary":
                engine.submit_directional_target(target_quantity)
            else:
                engine.atomic_pair_entry(target_quantity)
        if index == len(stamps) - 1 and engine.state.invalidation_reason is None:
            engine.terminate()
        else:
            engine.close_interval()
        previous_stamp = stamp
    return _ControlArtifact(control_id, requested_spec, economic_spec, engine.rows, engine.episodes, tuple(gap_rows))


def _run_control(
    run_spec: RunSpec, control_id: str, target_quantity: Decimal = Decimal("0.1"),
) -> _ControlArtifact:
    """Package-private control runner; prices, sources and costs stay authority-owned."""

    if not isinstance(run_spec, RunSpec):
        raise TypeError("control runner requires a verified RunSpec")
    if control_id not in CONTROL_IDS:
        raise ControlError(f"unknown control: {control_id!r}")
    target = as_decimal(target_quantity, "target_quantity")
    if target <= ZERO:
        raise ControlError("control target quantity must be positive")
    if control_id == "flat":
        economic_spec = run_spec
    elif control_id == "spot_buy_and_hold":
        economic_spec = get_run_spec("spot_candle_primary")
    else:
        # This is an independently directed long perpetual path with the same
        # absolute requested BTC exposure, not a relabelled candidate run.
        economic_spec = get_run_spec("directional_candle_primary")
    return _run_economic(run_spec, economic_spec, control_id, target)


__all__ = ["CONTROL_IDS", "ControlError"]
