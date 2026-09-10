"""W01-W06 wiring probes only; semantic behavior belongs to the unit owners."""

from __future__ import annotations

import ast
from decimal import Decimal
from hashlib import sha256
import inspect
from pathlib import Path

import pytest

import trading_platform.btc_accounting_e1_v14 as public
from trading_platform.btc_accounting_e1_v14.canonical import (
    FrozenDict,
    canonical_json_bytes,
)


ROOT = Path(__file__).resolve().parents[4]
PACKAGE = ROOT / "src/trading_platform/btc_accounting_e1_v14"
TESTS = ROOT / "research/btc/tests/btc_accounting_e1_v14"
CANDIDATE = ROOT / "research/btc/candidates/unified-backtest-engine-e1-v14"
MODULES = ("__init__.py", "canonical.py", "authorities.py", "ledger.py", "pair.py", "controls.py")
TEST_FILES = (
    "test_canonical_authorities.py", "test_ledger.py", "test_pair.py",
    "test_controls_outputs.py", "test_integration.py",
)
FIXTURES = (
    "instrument-rules.json", "margin-rules.json", "semantic-settings.json",
    "candle-source-observations.json", "l2-source-depth-observations.json", "run-specs.json",
)


def _internal_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            if node.module:
                result.add(node.module.split(".")[0])
            else:
                result.update(alias.name.split(".")[0] for alias in node.names)
    return result


def _fingerprint(path):
    raw = path.read_bytes()
    return sha256(raw).hexdigest(), len(raw)


def test_W01_acyclic_exact_import_graph():
    expected = {
        "__init__.py": {"authorities", "controls", "ledger", "pair"},
        "canonical.py": set(),
        "authorities.py": {"canonical"},
        "ledger.py": {"authorities", "canonical"},
        "pair.py": {"authorities", "canonical", "ledger"},
        "controls.py": {"authorities", "canonical", "ledger", "pair"},
    }
    assert {name: _internal_imports(PACKAGE / name) for name in MODULES} == expected
    order = {name: index for index, name in enumerate(
        ("canonical", "authorities", "ledger", "pair", "controls", "__init__"))}
    for filename, dependencies in expected.items():
        owner = filename.removesuffix(".py")
        assert all(order[dependency] < order[owner] for dependency in dependencies)


def test_W02_facade_only_surface_and_engine_owned_arguments():
    assert set(public.__all__) == {
        "AccountState", "AuthorityError", "CONTROL_IDS", "ControlError", "PairError", "create"
    }
    assert tuple(inspect.signature(public.create).parameters) == ("run_spec_id",)
    value = public.create("pair_candle_primary")
    allowed = {
        "open_next_interval", "submit_spot_target", "submit_directional_target",
        "atomic_pair_entry", "atomic_pair_close", "close_interval", "terminate",
        "run_control", "state", "rows", "episodes", "bindings", "artifacts",
    }
    visible = {name for name in dir(value) if not name.startswith("_")}
    assert visible == allowed
    forbidden_parameters = {
        "fill", "funding", "decision", "clock", "phase", "source", "price", "outcome",
        "cost", "rate", "state", "row", "binding", "token", "capability", "latency", "depth",
    }
    for name in allowed - {"state", "rows", "episodes", "bindings", "artifacts"}:
        assert not (set(inspect.signature(getattr(value, name)).parameters) & forbidden_parameters)
    assert not hasattr(value, "__dict__")
    with pytest.raises(TypeError):
        value.anything = object()


def test_W03_all_four_RunSpecs_wire_to_their_authorized_modules():
    spot = public.create("spot_candle_primary")
    spot.open_next_interval(); spot.submit_spot_target(Decimal("0.1")); spot.close_interval()
    directional = public.create("directional_candle_primary")
    directional.open_next_interval(); directional.submit_directional_target(Decimal("0.1")); directional.close_interval()
    for run_id in ("pair_candle_primary", "pair_l2_primary"):
        value = public.create(run_id)
        value.open_next_interval(); value.atomic_pair_entry(Decimal("0.5")); value.close_interval()
        assert "pair" in value.rows
    assert spot.state.spot_quantity == Decimal("0.1")
    assert directional.state.perpetual_quantity == Decimal("0.1")


def test_W04_active_snapshot_support_identity_when_frozen():
    active = [PACKAGE / name for name in MODULES] + [TESTS / name for name in TEST_FILES]
    fixtures = [ROOT / "research/btc/fixtures/unified-engine-e1-v14" / name for name in FIXTURES]
    assert all(path.is_file() for path in active + fixtures)
    if not CANDIDATE.exists():
        # Pre-snapshot implementation runs validate the complete frozen source set;
        # the same probe becomes strict identity verification after the freeze.
        return
    for path in active + fixtures:
        mirror = CANDIDATE / path.relative_to(ROOT)
        assert mirror.is_file() and _fingerprint(mirror) == _fingerprint(path)
    assert (CANDIDATE / "candidate-manifest.json").is_file()


@pytest.mark.parametrize("run_id", (
    "spot_candle_primary", "directional_candle_primary",
    "pair_candle_primary", "pair_l2_primary",
))
def test_W05_public_failure_metamorphics(run_id):
    value = public.create(run_id)
    before = (value.state, value.rows, value.episodes)
    wrong = "atomic_pair_entry" if not run_id.startswith("pair_") else "submit_spot_target"
    with pytest.raises((public.AuthorityError, ValueError, TypeError)):
        getattr(value, wrong)(Decimal("0.1"))
    assert (value.state, value.rows, value.episodes) == before
    value.open_next_interval()
    before = (value.state, value.rows, value.episodes)
    authorized = {
        "spot_candle_primary": "submit_spot_target",
        "directional_candle_primary": "submit_directional_target",
        "pair_candle_primary": "atomic_pair_entry",
        "pair_l2_primary": "atomic_pair_entry",
    }[run_id]
    with pytest.raises((ValueError, TypeError)):
        getattr(value, authorized)(True)
    assert (value.state, value.rows, value.episodes) == before


def test_W06_blind_oracle_input_handoff_is_canonical_data_only():
    value = public.create("directional_candle_primary")
    value.open_next_interval(); value.submit_directional_target(Decimal("0.1")); value.close_interval()
    artifacts = value.artifacts
    handoff = artifacts["oracle_handoff"]
    assert isinstance(artifacts, FrozenDict) and isinstance(handoff, FrozenDict)
    assert set(handoff) == {
        "schema_version", "run_spec_id", "run_spec_digest",
        "source_authority_sha256", "rows", "episodes",
    }
    assert artifacts["oracle_handoff_digest"] == sha256(canonical_json_bytes(handoff)).hexdigest()
    assert b"_LedgerEngine" not in canonical_json_bytes(handoff)
    assert b"_PairEngine" not in canonical_json_bytes(handoff)
    with pytest.raises(TypeError):
        handoff["rows"] = ()
