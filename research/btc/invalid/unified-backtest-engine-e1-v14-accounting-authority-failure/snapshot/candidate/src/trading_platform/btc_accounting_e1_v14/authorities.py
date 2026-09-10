"""Exact, one-time authority loading for E1-v14.

Callers select only one of four frozen RunSpec IDs.  Authority paths, bytes,
digests, scenarios, rules, sources and mandates are not caller-overridable.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import hashlib
from typing import Any

from .canonical import (
    CanonicalError,
    FrozenDict,
    as_decimal,
    canonical_sha256,
    freeze,
    parse_json_bytes,
    parse_utc,
)


class AuthorityError(ValueError):
    """Frozen authority bytes or their transitive bindings do not verify."""


class AuthorityBinding:
    __slots__ = ("_role", "_path", "_sha256", "_size_bytes")

    def __new__(cls, *_: Any, **__: Any) -> "AuthorityBinding":
        raise TypeError("AuthorityBinding values are created only by the verified loader")

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise TypeError("AuthorityBinding is immutable")

    @property
    def role(self) -> str:
        return self._role

    @property
    def semantic_role(self) -> str:
        return self._role

    @property
    def path(self) -> str:
        return self._path

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def size_bytes(self) -> int:
        return self._size_bytes

    def __repr__(self) -> str:
        return (
            f"AuthorityBinding(role={self.role!r}, path={self.path!r}, "
            f"sha256={self.sha256!r}, size_bytes={self.size_bytes!r})"
        )


class RunSpec:
    __slots__ = ("_payload", "_bindings", "_digest")

    def __new__(cls, *_: Any, **__: Any) -> "RunSpec":
        raise TypeError("RunSpec values are created only by the verified factory")

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise TypeError("RunSpec is immutable")

    @property
    def payload(self) -> FrozenDict[str, Any]:
        return self._payload

    @property
    def run_spec_id(self) -> str:
        return self._payload["run_spec_id"]

    @property
    def id(self) -> str:
        return self.run_spec_id

    @property
    def adapter(self) -> str:
        return self._payload["adapter"]

    @property
    def bindings(self) -> tuple[AuthorityBinding, ...]:
        return self._bindings

    @property
    def digest(self) -> str:
        return self._digest

    @property
    def source(self) -> FrozenDict[str, Any]:
        return self._payload["source"]

    @property
    def rules(self) -> FrozenDict[str, Any]:
        return self._payload["rules"]

    @property
    def margin(self) -> FrozenDict[str, Any]:
        return self._payload["margin"]

    @property
    def settings(self) -> FrozenDict[str, Any]:
        return self._payload["settings"]

    @property
    def mandate(self) -> FrozenDict[str, Any]:
        return self._payload["selected_mandate"]

    @property
    def selected_mandate(self) -> FrozenDict[str, Any]:
        return self.mandate

    @property
    def execution_authority(self) -> FrozenDict[str, Any]:
        return self._payload["execution_authority"]

    @property
    def primary_scenario_id(self) -> str:
        return self.execution_authority["primary_scenario_id"]

    @property
    def severe_scenario_id(self) -> str:
        execution = self.execution_authority
        return execution.get("severe_scenario_id") or execution["severe_cost_budget_source_id"]

    @property
    def initial_nav(self):
        return as_decimal(self._payload["initial_NAV"], "initial_NAV")

    @property
    def leverage(self):
        return as_decimal(self._payload["leverage"], "leverage")

    def __getitem__(self, key: str) -> Any:
        return self._payload[key]

    def __repr__(self) -> str:
        return f"RunSpec({self.run_spec_id!r}, digest={self.digest!r})"


class AuthorityBundle:
    __slots__ = ("_bindings", "_data", "_run_specs")

    def __new__(cls, *_: Any, **__: Any) -> "AuthorityBundle":
        raise TypeError("AuthorityBundle is available only from load_authorities()")

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise TypeError("AuthorityBundle is immutable")

    @property
    def bindings(self) -> tuple[AuthorityBinding, ...]:
        return self._bindings

    @property
    def run_specs(self) -> FrozenDict[str, RunSpec]:
        return self._run_specs

    def run_spec(self, run_spec_id: str) -> RunSpec:
        if not isinstance(run_spec_id, str):
            raise AuthorityError("RunSpec ID must be a string")
        try:
            return self._run_specs[run_spec_id]
        except KeyError as exc:
            raise AuthorityError(f"unknown frozen RunSpec ID: {run_spec_id!r}") from exc

    def data(self, role: str) -> FrozenDict[str, Any]:
        if not isinstance(role, str):
            raise AuthorityError("authority role must be a string")
        try:
            return self._data[role]
        except KeyError as exc:
            raise AuthorityError(f"unknown authority role: {role!r}") from exc


def _builders():
    # The construction functions and their capability live only in this closure;
    # no token, sentinel, classmethod or readable object attribute is exported.
    def binding(role: str, path: str, digest: str, size: int) -> AuthorityBinding:
        value = object.__new__(AuthorityBinding)
        object.__setattr__(value, "_role", role)
        object.__setattr__(value, "_path", path)
        object.__setattr__(value, "_sha256", digest)
        object.__setattr__(value, "_size_bytes", size)
        return value

    def run_spec(
        payload: FrozenDict[str, Any], bindings: tuple[AuthorityBinding, ...]
    ) -> RunSpec:
        value = object.__new__(RunSpec)
        object.__setattr__(value, "_payload", payload)
        object.__setattr__(value, "_bindings", bindings)
        object.__setattr__(value, "_digest", canonical_sha256(payload))
        return value

    def bundle(
        bindings: tuple[AuthorityBinding, ...],
        data: FrozenDict[str, FrozenDict[str, Any]],
        specs: FrozenDict[str, RunSpec],
    ) -> AuthorityBundle:
        value = object.__new__(AuthorityBundle)
        object.__setattr__(value, "_bindings", bindings)
        object.__setattr__(value, "_data", data)
        object.__setattr__(value, "_run_specs", specs)
        return value

    return binding, run_spec, bundle


_make_binding, _make_run_spec, _make_bundle = _builders()
del _builders


_EXPECTED = (
    ("execution_scenarios", "config/execution_scenarios.json", "a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36", 2922),
    ("spot_mandate", "config/retail_mandate.json", "7e34cfb0928b4373bbf52b5c5505f63a2b19e674124059191c1b6c62ec129041", 2960),
    ("directional_mandate", "config/mandates/retail-btc-directional-perpetual-research-v1.json", "1b5d492f12f71ebe28e1bdfbd0b5916bcf0ad285b483cb10bf8770504371165d", 1619),
    ("pair_mandate", "config/mandates/retail-btc-delta-neutral-research-v1.json", "d95a53ee493862549b932dc5f80600a02a0e38e4ba1b3da0d79d0b0c5bb9eeba", 2268),
    ("instrument_rules", "research/btc/fixtures/unified-engine-e1-v14/instrument-rules.json", "858c96ce58abe4c02189f2102160a28bbc029d76b87515fa819d93ce1d770bb5", 767),
    ("margin_rules", "research/btc/fixtures/unified-engine-e1-v14/margin-rules.json", "b887b06d13ee414dc45ac6f76764586062c275b2581f46db979a8ebb00c79d60", 321),
    ("semantic_settings", "research/btc/fixtures/unified-engine-e1-v14/semantic-settings.json", "e47527842e8ae7d4a046576beac3146e69fac5e169e51e76e246143c2690647c", 2055),
    ("candle_source", "research/btc/fixtures/unified-engine-e1-v14/candle-source-observations.json", "96b80f8502a612b2475eb8a23f984380e747c00f5f3813802ef90d9fafd78ff5", 2873),
    ("qualified_l2_source", "research/btc/fixtures/unified-engine-e1-v14/l2-source-depth-observations.json", "9b7d9ba8e95ec814f1f02eb3e740284a5838bad4274c234d1a38e12ed7077e3c", 3862),
    ("run_specs", "research/btc/fixtures/unified-engine-e1-v14/run-specs.json", "7e341a480e3c6edba78ba02aa445c0feb9df65e9c8dadba3fb0f7b308a1abf4b", 7592),
)
_EXPECTED_IDS = (
    "spot_candle_primary",
    "directional_candle_primary",
    "pair_candle_primary",
    "pair_l2_primary",
)
_MANDATE_ROLE = {
    "spot_candle_primary": "spot_mandate",
    "directional_candle_primary": "directional_mandate",
    "pair_candle_primary": "pair_mandate",
    "pair_l2_primary": "pair_mandate",
}
_EXPECTED_RUN_KEYS = frozenset(
    {
        "adapter", "execution_authority", "execution_convention", "initial_NAV",
        "leverage", "margin", "partition", "rules", "run_spec_id",
        "schema_version", "selected_mandate", "settings", "source",
    }
)
_ROLE_BY_PATH = {path: role for role, path, _digest, _size in _EXPECTED}
_META_BY_ROLE = {
    role: (path, digest, size) for role, path, digest, size in _EXPECTED
}
_CACHE: AuthorityBundle | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _fail(message: str, cause: Exception | None = None) -> None:
    error = AuthorityError(message)
    if cause is None:
        raise error
    raise error from cause


def _validate_exact_ref(ref: Mapping[str, Any], role: str) -> None:
    path, digest, _size = _META_BY_ROLE[role]
    expected_keys = {"path", "sha256"}
    if "role" in ref:
        expected_keys.add("role")
    if set(ref) != expected_keys:
        _fail(f"{role} binding has an incomplete or extended field set")
    if ref["path"] != path or ref["sha256"] != digest:
        _fail(f"{role} binding does not match exact authority bytes")
    if "role" in ref and ref["role"] != role:
        _fail(f"{role} binding has the wrong semantic role")


def _validate_numeric_authorities(data: Mapping[str, FrozenDict[str, Any]]) -> None:
    rules = data["instrument_rules"]
    parse_utc(rules["effective_at"], "instrument rules effective_at")
    for name, rule in rules["instruments"].items():
        for field in ("maximum_quantity", "minimum_notional", "step", "tick"):
            value = as_decimal(rule[field], f"{name}.{field}")
            if value <= 0:
                _fail(f"{name}.{field} must be positive")
    margin = data["margin_rules"]
    parse_utc(margin["effective_at"], "margin effective_at")
    for field in ("exit_cost_reserve_rate", "liquidation_fee_rate", "maintenance_fraction"):
        value = as_decimal(margin[field], field)
        if value < 0:
            _fail(f"{field} must be nonnegative")

    for source_role, sequence_key, id_key in (
        ("candle_source", "observations", "observation_id"),
        ("qualified_l2_source", "snapshots", "snapshot_id"),
    ):
        seen: set[str] = set()
        for row in data[source_role][sequence_key]:
            row_id = row[id_key]
            if row_id in seen:
                _fail(f"duplicate {source_role} logical row: {row_id}")
            seen.add(row_id)
            observed = parse_utc(row["observed_at"], f"{row_id}.observed_at")
            available = parse_utc(row["available_at"], f"{row_id}.available_at")
            if available < observed:
                _fail(f"{row_id} is available before observation")


def _scenario_index(execution: Mapping[str, Any]) -> FrozenDict[str, FrozenDict[str, Any]]:
    index: dict[str, FrozenDict[str, Any]] = {}
    for scenario in execution["scenarios"]:
        scenario_id = scenario["scenario_id"]
        if scenario_id in index:
            _fail(f"duplicate execution scenario: {scenario_id}")
        index[scenario_id] = scenario
        for field in (
            "taker_fee_bps", "maker_fee_bps", "implicit_cost_bps_per_side",
            "residual_impact_bps", "price_protection_bps",
        ):
            if as_decimal(scenario[field], f"{scenario_id}.{field}") < 0:
                _fail(f"{scenario_id}.{field} must be nonnegative")
    return freeze(index)


def _validate_run_spec(
    spec: FrozenDict[str, Any],
    data: Mapping[str, FrozenDict[str, Any]],
    scenarios: Mapping[str, FrozenDict[str, Any]],
) -> tuple[AuthorityBinding, ...]:
    if set(spec) != _EXPECTED_RUN_KEYS:
        _fail("RunSpec has an incomplete or extended top-level field set")
    run_id = spec["run_spec_id"]
    if spec["schema_version"] != "btc-unified-engine-e1-v14-run-spec-v1":
        _fail(f"{run_id} has wrong schema_version")
    if as_decimal(spec["initial_NAV"], "initial_NAV") != 1000:
        _fail(f"{run_id} has wrong initial NAV")
    if as_decimal(spec["leverage"], "leverage") != 1:
        _fail(f"{run_id} has wrong leverage")

    for key, role in (
        ("rules", "instrument_rules"),
        ("margin", "margin_rules"),
        ("settings", "semantic_settings"),
    ):
        _validate_exact_ref(spec[key], role)
    source_role = "candle_source" if spec["adapter"] == "candle" else "qualified_l2_source"
    _validate_exact_ref(spec["source"], source_role)

    mandate_role = _MANDATE_ROLE[run_id]
    mandate_ref = spec["selected_mandate"]
    expected_path, expected_hash, _ = _META_BY_ROLE[mandate_role]
    if set(mandate_ref) != {"mandate_id", "path", "sha256"}:
        _fail(f"{run_id} mandate binding field set is not exact")
    mandate = data[mandate_role]
    if (
        mandate_ref["path"] != expected_path
        or mandate_ref["sha256"] != expected_hash
        or mandate_ref["mandate_id"] != mandate["mandate_id"]
    ):
        _fail(f"{run_id} mandate path/ID/hash mismatch")

    partition = spec["partition"]
    settings_partition = data["semantic_settings"]["partition"]
    if set(partition) != {"partition_id", "start_inclusive", "terminal_exclusive"}:
        _fail(f"{run_id} partition field set is not exact")
    if any(partition[key] != settings_partition[key] for key in partition):
        _fail(f"{run_id} partition is not bound to semantic settings")
    if parse_utc(partition["start_inclusive"]) >= parse_utc(partition["terminal_exclusive"]):
        _fail(f"{run_id} partition is empty")

    execution = spec["execution_authority"]
    if execution.get("path") != _META_BY_ROLE["execution_scenarios"][0] or execution.get("sha256") != _META_BY_ROLE["execution_scenarios"][1]:
        _fail(f"{run_id} execution authority mismatch")
    if execution.get("rate_override") != "forbidden":
        _fail(f"{run_id} permits caller rate override")
    primary = scenarios.get(execution.get("primary_scenario_id"))
    if primary is None:
        _fail(f"{run_id} primary scenario is absent")
    if spec["adapter"] == "candle":
        if primary["mode"] != "candle_taker" or execution.get("severe_scenario_id") != "candle-severe-80bps-rt-v1":
            _fail(f"{run_id} candle scenario binding is incompatible")
    elif spec["adapter"] == "qualified_l2":
        required = {
            "primary_scenario_id": "book-taker-primary-250ms-v1",
            "primary_mode": "book_taker",
            "latency_ms": 250,
            "severe_cost_budget_source_id": "candle-severe-80bps-rt-v1",
        }
        if any(execution.get(key) != value for key, value in required.items()):
            _fail("pair_l2_primary mode/latency/scenario binding is incompatible")
        if primary["mode"] != "book_taker" or primary["latency_ms"] != 250:
            _fail("pair_l2_primary does not bind the qualified 250ms book scenario")
    else:
        _fail(f"{run_id} has unknown adapter")

    roles = (
        "run_specs", "execution_scenarios", mandate_role, "instrument_rules",
        "margin_rules", "semantic_settings", source_role,
    )
    return tuple(
        _make_binding(role, *_META_BY_ROLE[role])
        for role in roles
    )


def _load() -> AuthorityBundle:
    root = _repo_root()
    loaded: dict[str, FrozenDict[str, Any]] = {}
    bindings: list[AuthorityBinding] = []
    for role, relative, expected_digest, expected_size in _EXPECTED:
        path = root / relative
        try:
            raw = path.read_bytes()
        except OSError as exc:
            _fail(f"required authority unavailable: {relative}", exc)
        actual = hashlib.sha256(raw).hexdigest()
        if len(raw) != expected_size or actual != expected_digest:
            _fail(f"exact-byte verification failed for {relative}")
        try:
            payload = parse_json_bytes(raw, label=relative)
        except CanonicalError as exc:
            _fail(f"canonical authority parsing failed for {relative}", exc)
        if not isinstance(payload, FrozenDict):
            _fail(f"authority root must be an object: {relative}")
        loaded[role] = payload
        bindings.append(_make_binding(role, relative, actual, len(raw)))

    frozen_data = freeze(loaded)
    _validate_numeric_authorities(frozen_data)
    scenarios = _scenario_index(frozen_data["execution_scenarios"])
    manifest = frozen_data["run_specs"]
    if set(manifest) != {"schema_version", "run_specs"} or manifest["schema_version"] != "btc-unified-engine-e1-v14-run-specs-v1":
        _fail("RunSpec manifest field set or schema is not exact")
    raw_specs = manifest["run_specs"]
    ids = tuple(spec.get("run_spec_id") for spec in raw_specs)
    if ids != _EXPECTED_IDS or len(set(ids)) != 4:
        _fail("RunSpec manifest must contain the four exact ordered unique IDs")
    specs: dict[str, RunSpec] = {}
    for spec in raw_specs:
        spec_bindings = _validate_run_spec(spec, frozen_data, scenarios)
        specs[spec["run_spec_id"]] = _make_run_spec(spec, spec_bindings)
    return _make_bundle(tuple(bindings), frozen_data, FrozenDict(specs))


def load_authorities() -> AuthorityBundle:
    """Verify and load all exact authorities once per process."""
    # _CACHE is populated exactly once at module initialization below.
    assert _CACHE is not None
    return _CACHE


def get_run_spec(run_spec_id: str) -> RunSpec:
    return load_authorities().run_spec(run_spec_id)


def authority(role: str) -> FrozenDict[str, Any]:
    return load_authorities().data(role)


def scenario_for(run_spec: RunSpec, *, severe: bool = False) -> FrozenDict[str, Any]:
    if not isinstance(run_spec, RunSpec) or run_spec not in load_authorities().run_specs.values():
        raise AuthorityError("scenario lookup requires a verified RunSpec")
    scenario_id = run_spec.severe_scenario_id if severe else run_spec.primary_scenario_id
    scenarios = authority("execution_scenarios")["scenarios"]
    return next(scenario for scenario in scenarios if scenario["scenario_id"] == scenario_id)


def comparison_scenarios(run_spec: RunSpec) -> FrozenDict[str, FrozenDict[str, Any]]:
    if run_spec.run_spec_id != "pair_l2_primary":
        return FrozenDict()
    scenarios = {item["scenario_id"]: item for item in authority("execution_scenarios")["scenarios"]}
    budgets = authority("semantic_settings")["execution"]["comparison_cost_budgets"]
    return freeze({budget["budget_id"]: scenarios[budget["authority_scenario_id"]] for budget in budgets})


def instrument_rule(run_spec: RunSpec, instrument: str) -> FrozenDict[str, Any]:
    if run_spec not in load_authorities().run_specs.values():
        raise AuthorityError("rule lookup requires a verified RunSpec")
    try:
        return authority("instrument_rules")["instruments"][instrument]
    except KeyError as exc:
        raise AuthorityError(f"instrument is not rule-authorized: {instrument!r}") from exc


def margin_rule(run_spec: RunSpec) -> FrozenDict[str, Any]:
    if run_spec not in load_authorities().run_specs.values():
        raise AuthorityError("margin lookup requires a verified RunSpec")
    return authority("margin_rules")


def source_records(run_spec: RunSpec) -> tuple[FrozenDict[str, Any], ...]:
    if run_spec.adapter == "candle":
        return authority("candle_source")["observations"]
    if run_spec.adapter == "qualified_l2":
        return authority("qualified_l2_source")["snapshots"]
    raise AuthorityError("RunSpec adapter is not authorized")


_OPERATIONS = {
    "spot_candle_primary": frozenset({"open_next_interval", "submit_spot_target", "close_interval", "terminate", "run_control"}),
    "directional_candle_primary": frozenset({"open_next_interval", "submit_directional_target", "close_interval", "terminate", "run_control"}),
    "pair_candle_primary": frozenset({"open_next_interval", "atomic_pair_entry", "atomic_pair_close", "close_interval", "terminate", "run_control"}),
    "pair_l2_primary": frozenset({"open_next_interval", "atomic_pair_entry", "atomic_pair_close", "close_interval", "terminate", "run_control"}),
}


def ensure_operation_allowed(run_spec: RunSpec, operation: str) -> None:
    if run_spec not in load_authorities().run_specs.values():
        raise AuthorityError("operation check requires a verified RunSpec")
    if operation not in _OPERATIONS[run_spec.run_spec_id]:
        raise AuthorityError(
            f"{operation!r} is not authorized for RunSpec {run_spec.run_spec_id!r}"
        )


# Verify once at module initialization, then discard every construction callable.
# Operations and repeated factory calls can only retrieve these already-frozen
# objects; even module introspection cannot recover a builder or capability.
_CACHE = _load()
del _load, _make_binding, _make_run_spec, _make_bundle


__all__ = [
    "AuthorityBinding",
    "AuthorityBundle",
    "AuthorityError",
    "RunSpec",
    "authority",
    "comparison_scenarios",
    "ensure_operation_allowed",
    "get_run_spec",
    "instrument_rule",
    "load_authorities",
    "margin_rule",
    "scenario_for",
    "source_records",
]
