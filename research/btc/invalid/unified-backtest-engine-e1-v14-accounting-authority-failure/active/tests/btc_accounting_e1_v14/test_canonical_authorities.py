from __future__ import annotations

import ast
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from trading_platform.btc_accounting_e1_v14 import authorities as authority_module
from trading_platform.btc_accounting_e1_v14.authorities import (
    AuthorityBinding,
    AuthorityBundle,
    AuthorityError,
    RunSpec,
    authority,
    comparison_scenarios,
    ensure_operation_allowed,
    get_run_spec,
    load_authorities,
    scenario_for,
)
from trading_platform.btc_accounting_e1_v14.canonical import (
    CanonicalError,
    FrozenDict,
    as_decimal,
    canonical_decimal,
    canonical_json,
    canonical_json_bytes,
    canonical_sha256,
    freeze,
    parse_json_bytes,
    parse_utc,
    quantize_step,
    solve_base_fee_sale,
    validate_instrument_order,
)


ROOT = Path(__file__).resolve().parents[4]
RUN_IDS = (
    "spot_candle_primary",
    "directional_candle_primary",
    "pair_candle_primary",
    "pair_l2_primary",
)


def _assert_deep_immutable(value):
    if isinstance(value, FrozenDict):
        with pytest.raises(TypeError):
            value["__mutation__"] = True
        for item in value.values():
            _assert_deep_immutable(item)
    elif isinstance(value, tuple):
        with pytest.raises(TypeError):
            value[0] = None
        for item in value:
            _assert_deep_immutable(item)


def test_A01_factory_only_hidden_capability():
    for value_type in (AuthorityBinding, RunSpec, AuthorityBundle):
        with pytest.raises(TypeError):
            value_type()
    names = set(vars(authority_module))
    assert not {name for name in names if "token" in name.casefold() or "capability" in name.casefold()}
    assert not {"_make_binding", "_make_run_spec", "_make_bundle", "_load"} & names
    assert get_run_spec("spot_candle_primary") is load_authorities().run_spec("spot_candle_primary")
    with pytest.raises(AuthorityError):
        get_run_spec("caller_selected_path_or_value")


def test_A02_exact_manifest_fields_complete_sets():
    bundle = load_authorities()
    assert tuple(bundle.run_specs) == RUN_IDS
    assert len(bundle.bindings) == 10
    assert {binding.role for binding in bundle.bindings} == {
        "execution_scenarios", "spot_mandate", "directional_mandate", "pair_mandate",
        "instrument_rules", "margin_rules", "semantic_settings", "candle_source",
        "qualified_l2_source", "run_specs",
    }
    manifest = authority("run_specs")
    assert set(manifest) == {"schema_version", "run_specs"}
    expected = {
        "adapter", "execution_authority", "execution_convention", "initial_NAV",
        "leverage", "margin", "partition", "rules", "run_spec_id",
        "schema_version", "selected_mandate", "settings", "source",
    }
    assert all(set(spec.payload) == expected for spec in bundle.run_specs.values())


def test_A03_active_snapshot_identity_when_snapshot_is_frozen():
    candidate_root = ROOT / "research/btc/candidates/unified-backtest-engine-e1-v14"
    owned = (
        "src/trading_platform/btc_accounting_e1_v14/canonical.py",
        "src/trading_platform/btc_accounting_e1_v14/authorities.py",
        "research/btc/tests/btc_accounting_e1_v14/test_canonical_authorities.py",
    )
    if not candidate_root.exists():
        # Implementers must not create the candidate snapshot; before the
        # independent freeze there must be no partial candidate directory.
        assert not candidate_root.exists()
        return
    for relative in owned:
        active = ROOT / relative
        mirror = candidate_root / relative
        assert mirror.is_file()
        assert mirror.read_bytes() == active.read_bytes()


def test_A04_recursive_immutable_bindings_runspec_phase_clock_state_rows():
    bundle = load_authorities()
    _assert_deep_immutable(bundle.run_specs)
    for spec in bundle.run_specs.values():
        _assert_deep_immutable(spec.payload)
        with pytest.raises(TypeError):
            spec._payload = FrozenDict()
        with pytest.raises(TypeError):
            spec.bindings[0]._sha256 = "0" * 64
    representative_view = freeze({
        "phase": 4,
        "clock": {"at": "2025-01-01T02:00:00.000000Z"},
        "state": {"cash": Decimal("1000")},
        "rows": [{"row_id": "A1"}],
    })
    _assert_deep_immutable(representative_view)


@pytest.mark.parametrize("binding", load_authorities().bindings, ids=lambda item: item.role)
def test_H01_every_changed_bound_authority_byte_fails_closed(binding):
    target = ROOT / binding.path
    program = r'''
from pathlib import Path
import sys
target = Path(sys.argv[1]).resolve()
original = Path.read_bytes
def changed(self):
    raw = original(self)
    if self.resolve() == target:
        return raw[:-1] + bytes([raw[-1] ^ 1])
    return raw
Path.read_bytes = changed
try:
    import trading_platform.btc_accounting_e1_v14.authorities
except Exception as exc:
    if "exact-byte verification failed" in str(exc):
        raise SystemExit(0)
    print(type(exc).__name__, str(exc), file=sys.stderr)
    raise SystemExit(2)
raise SystemExit(3)
'''
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-c", program, str(target)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_H02_transitive_real_lineage_source_rule_margin_scenario_mandate():
    all_bindings = {binding.role: binding for binding in load_authorities().bindings}
    for spec in load_authorities().run_specs.values():
        roles = {binding.role for binding in spec.bindings}
        assert {"run_specs", "execution_scenarios", "instrument_rules", "margin_rules", "semantic_settings"} <= roles
        assert ("candle_source" if spec.adapter == "candle" else "qualified_l2_source") in roles
        assert all(binding.sha256 == all_bindings[binding.role].sha256 for binding in spec.bindings)
        assert scenario_for(spec)["scenario_id"] == spec.primary_scenario_id
        assert scenario_for(spec, severe=True)["scenario_id"] == "candle-severe-80bps-rt-v1"
        assert spec.source["sha256"] == all_bindings[next(role for role in roles if role.endswith("_source"))].sha256


@pytest.mark.parametrize(
    ("value", "invalid_json_value"),
    [
        (float("nan"), True), (float("inf"), True), (float("-inf"), True),
        (Decimal("NaN"), True), (Decimal("Infinity"), True),
        (True, False), ("1e2", False), ("+1", False),
    ],
)
def test_J01_finite_decimal_only(value, invalid_json_value):
    with pytest.raises(CanonicalError):
        as_decimal(value)
    if invalid_json_value:
        with pytest.raises(CanonicalError):
            canonical_json({"economic": value})
    assert canonical_decimal(Decimal("-0.000")) == "0"
    assert canonical_decimal(Decimal("120.3400")) == "120.34"


def test_J02_tick_step_notional_bounds_and_base_fee_solver_dust():
    rule = authority("instrument_rules")["instruments"]["BTC/USDT"]
    assert quantize_step(Decimal("-1.29"), rule["step"]) == Decimal("-1.2")
    assert validate_instrument_order(quantity=Decimal("0.19"), price=Decimal("100.00"), rule=rule) == Decimal("0.1")
    for quantity, price in ((Decimal("0.04"), Decimal("100")), (Decimal("10.1"), Decimal("100")), (Decimal("1"), Decimal("100.001"))):
        with pytest.raises(CanonicalError):
            validate_instrument_order(quantity=quantity, price=price, rule=rule)
    gross, fee, dust = solve_base_fee_sale(inventory="1.001", fee_rate="0.001", step="0.1")
    assert (gross, fee, dust) == (Decimal("1.0"), Decimal("0.0010"), Decimal("0.0000"))
    gross, fee, dust = solve_base_fee_sale(inventory="1", fee_rate="0.001", step="0.1")
    assert gross + fee <= Decimal("1") and dust == Decimal("0.0991")
    assert gross + Decimal("0.1") + (gross + Decimal("0.1")) * Decimal("0.001") > Decimal("1")


def test_J03_canonical_JSON_SHA_duplicate_and_key_collision_rejection():
    value = {"z": [Decimal("1.00"), None], "a": "é"}
    expected = '{"a":"é","z":["1",null]}'
    assert canonical_json(value) == expected
    assert canonical_json_bytes(value) == expected.encode("utf-8")
    assert canonical_sha256(value) == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    with pytest.raises(CanonicalError):
        parse_json_bytes(b'{"same":1,"same":2}')
    with pytest.raises(CanonicalError):
        canonical_json({1: "integer", "1": "string"})
    with pytest.raises(CanonicalError):
        parse_json_bytes(b'{"x":NaN}')


def test_R01_no_token_or_capability_forge():
    spec = get_run_spec("pair_candle_primary")
    assert not hasattr(spec, "token") and not hasattr(spec, "capability")
    assert not hasattr(spec, "path_override") and not hasattr(spec, "rate_override")
    with pytest.raises(TypeError):
        RunSpec(spec.payload, spec.bindings)


def test_R11_authorities_loaded_once_and_never_reopened(monkeypatch):
    original = Path.read_bytes
    calls = 0

    def counted(path):
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", counted)
    first = load_authorities()
    for run_id in RUN_IDS:
        assert get_run_spec(run_id) is first.run_specs[run_id]
        scenario_for(first.run_specs[run_id])
    assert load_authorities() is first
    assert calls == 0


def test_R19_string_key_collision_rejects_in_freeze_parse_and_digest():
    with pytest.raises(CanonicalError):
        freeze({1: "x"})
    with pytest.raises(CanonicalError):
        canonical_sha256({"1": "x", 1: "y"})
    with pytest.raises(CanonicalError):
        parse_json_bytes(b'{"\\u0061":1,"a":2}')


def test_R21_four_exact_RunSpecs_and_wrong_method_rejection():
    specs = load_authorities().run_specs
    assert tuple(specs) == RUN_IDS
    allowed = {
        "spot_candle_primary": "submit_spot_target",
        "directional_candle_primary": "submit_directional_target",
        "pair_candle_primary": "atomic_pair_entry",
        "pair_l2_primary": "atomic_pair_close",
    }
    all_specialized = {"submit_spot_target", "submit_directional_target", "atomic_pair_entry", "atomic_pair_close"}
    for run_id, operation in allowed.items():
        ensure_operation_allowed(specs[run_id], operation)
        for wrong in all_specialized - {operation}:
            # Pair specs permit both pair entry and close.
            if run_id.startswith("pair_") and wrong in {"atomic_pair_entry", "atomic_pair_close"}:
                continue
            with pytest.raises(AuthorityError):
                ensure_operation_allowed(specs[run_id], wrong)
    l2 = specs["pair_l2_primary"]
    assert l2.adapter == "qualified_l2"
    assert scenario_for(l2)["mode"] == "book_taker"
    assert scenario_for(l2)["latency_ms"] == 250
    assert tuple(comparison_scenarios(l2)) == (
        "l2-comparison-30bps-rt", "l2-comparison-40bps-rt", "l2-comparison-80bps-rt",
    )


def test_R22_no_candidate_or_oracle_helper_dependency():
    canonical_path = ROOT / "src/trading_platform/btc_accounting_e1_v14/canonical.py"
    authorities_path = ROOT / "src/trading_platform/btc_accounting_e1_v14/authorities.py"
    canonical_tree = ast.parse(canonical_path.read_text(encoding="utf-8"))
    authority_tree = ast.parse(authorities_path.read_text(encoding="utf-8"))

    def imports(tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                yield from (alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                yield node.module or ""

    canonical_imports = set(imports(canonical_tree))
    authority_imports = set(imports(authority_tree))
    assert all(not name.startswith("trading_platform") for name in canonical_imports)
    assert not any(term in name.casefold() for name in authority_imports for term in ("oracle", "candidate", "history", "service"))
    assert authority_imports <= {
        "__future__", "collections.abc", "pathlib", "hashlib", "typing", "canonical"
    }
