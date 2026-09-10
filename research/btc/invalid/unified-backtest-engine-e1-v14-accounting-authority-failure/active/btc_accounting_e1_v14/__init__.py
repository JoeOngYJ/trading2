"""Public facade for the frozen, offline E1-v14 accounting engine.

The only construction input is one exact RunSpec ID.  Market observations,
timestamps, phases, fills, prices, costs, authority paths and state transitions
remain engine-owned and cannot be supplied through this surface.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from . import authorities
from . import controls
from . import ledger
from . import pair


AuthorityError = authorities.AuthorityError
ControlError = controls.ControlError
PairError = pair.PairError
AccountState = ledger.AccountState
CONTROL_IDS = controls.CONTROL_IDS


def _make_factory():
    # The capability exists only in this closure.  It is not exported, stored on
    # an instance, or accepted by any public call.
    capability = object()

    class Engine:
        __slots__ = ("__spec", "__engine")

        def __init__(self, spec: authorities.RunSpec, engine: Any, key: object) -> None:
            if key is not capability:
                raise TypeError("engines are created only by create(run_spec_id)")
            object.__setattr__(self, "_Engine__spec", spec)
            object.__setattr__(self, "_Engine__engine", engine)

        def __setattr__(self, _name: str, _value: Any) -> None:
            raise TypeError("engine facade is immutable")

        def open_next_interval(self):
            authorities.ensure_operation_allowed(self.__spec, "open_next_interval")
            return self.__engine.open_next_interval()

        def submit_spot_target(self, target_quantity):
            authorities.ensure_operation_allowed(self.__spec, "submit_spot_target")
            return self.__engine.submit_spot_target(target_quantity)

        def submit_directional_target(self, target_quantity):
            authorities.ensure_operation_allowed(self.__spec, "submit_directional_target")
            return self.__engine.submit_directional_target(target_quantity)

        def atomic_pair_entry(self, target_quantity):
            authorities.ensure_operation_allowed(self.__spec, "atomic_pair_entry")
            return self.__engine.atomic_pair_entry(target_quantity)

        def atomic_pair_close(self, target_quantity=Decimal("0")):
            authorities.ensure_operation_allowed(self.__spec, "atomic_pair_close")
            return self.__engine.atomic_pair_close(target_quantity)

        def close_interval(self):
            authorities.ensure_operation_allowed(self.__spec, "close_interval")
            return self.__engine.close_interval()

        def terminate(self):
            authorities.ensure_operation_allowed(self.__spec, "terminate")
            return self.__engine.terminate()

        def run_control(self, control_id, target_quantity=Decimal("0.1")):
            authorities.ensure_operation_allowed(self.__spec, "run_control")
            return controls._run_control(self.__spec, control_id, target_quantity)

        @property
        def state(self):
            return self.__engine.state

        @property
        def rows(self):
            return self.__engine.rows

        @property
        def episodes(self):
            return self.__engine.episodes

        @property
        def bindings(self):
            return self.__spec.bindings

        @property
        def artifacts(self):
            rows = self.__engine.rows
            episodes = self.__engine.episodes
            bindings = tuple(
                {
                    "path": item.path,
                    "sha256": item.sha256,
                    "size_bytes": item.size_bytes,
                    "semantic_role": item.semantic_role,
                }
                for item in self.__spec.bindings
            )
            handoff = {
                "schema_version": "btc-unified-engine-e1-v14-oracle-handoff-v1",
                "run_spec_id": self.__spec.run_spec_id,
                "run_spec_digest": self.__spec.digest,
                "source_authority_sha256": self.__spec.source["sha256"],
                "rows": rows,
                "episodes": episodes,
            }
            result = {
                "run_spec_id": self.__spec.run_spec_id,
                "run_spec_digest": self.__spec.digest,
                "ledgers": {
                    name: {"row_count": len(values), "sha256": controls.canonical_sha256(values)}
                    for name, values in rows.items()
                },
                "episodes": {
                    "row_count": len(episodes),
                    "sha256": controls.canonical_sha256(episodes),
                },
                "bindings": bindings,
                "oracle_handoff": handoff,
                "oracle_handoff_digest": controls.canonical_sha256(handoff),
            }
            return controls.freeze(result)

    def create(run_spec_id: str):
        spec = authorities.get_run_spec(run_spec_id)
        base = ledger._create_ledger(spec)
        engine = pair._attach_pair(base) if spec.run_spec_id.startswith("pair_") else base
        return Engine(spec, engine, capability)

    return create


create = _make_factory()
del _make_factory


__all__ = [
    "AccountState",
    "AuthorityError",
    "CONTROL_IDS",
    "ControlError",
    "PairError",
    "create",
]
