import copy
from dataclasses import replace
import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.planning import ControlEventEmitter  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state import ProxyStateDTO, SnapshotConflict  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    FdasRuntimeConfigurationError,
    build_runtime,
    load_runtime_declaration,
    validate_runtime_declaration,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _snapshot(game_id="fdas-runtime", seq=431):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = json.load(stream)
    return ProxyStateDTO.parse(game_id, seq, payload).to_snapshot()


def _enabled_city_declaration():
    declaration = load_runtime_declaration()
    value = copy.deepcopy(declaration)
    value["config"]["enabled"] = True
    value["config"]["projection"].update({
        "beliefs": False,
        "operations": False,
        "region": False,
        "research": False,
        "ruleset": False,
        "unit": False,
    })
    semantic = dict(value)
    semantic.pop("declaration_hash")
    from freeciv_agent.events.schema import structural_hash
    value["declaration_hash"] = structural_hash(semantic)
    return value


def _ruleset_root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append(
        "/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data")
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(
                candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for full FDAS runtime assembly")


def test_checked_default_declaration_is_disabled_and_manifest_safe():
    declaration = load_runtime_declaration()
    config = validate_runtime_declaration(declaration)
    runtime = build_runtime(declaration)

    assert config.enabled is False
    assert runtime.enabled is False
    assert runtime.projector_ids == ()
    update = runtime.replace(_snapshot())
    assert update.revision_id is not None
    assert update.atom_count > 0
    assert runtime.activation_payload()["policy_authority"] is False


def test_declaration_tampering_and_missing_enabled_dependencies_fail_closed():
    declaration = load_runtime_declaration()
    tampered = copy.deepcopy(declaration)
    tampered["config"]["authority_enabled"] = True
    with pytest.raises(
            FdasRuntimeConfigurationError, match="hash mismatch"):
        validate_runtime_declaration(tampered)

    enabled = copy.deepcopy(declaration)
    enabled["config"]["enabled"] = True
    semantic = dict(enabled)
    semantic.pop("declaration_hash")
    from freeciv_agent.events.schema import structural_hash
    enabled["declaration_hash"] = structural_hash(semantic)
    with pytest.raises(
            FdasRuntimeConfigurationError, match="ruleset projection"):
        build_runtime(enabled)


def test_enabled_city_shadow_runtime_materializes_and_emits_causal_events(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)

    assert runtime.enabled is True
    assert runtime.projector_ids == ("fdas-city-economy-shadow",)
    assert update.atom_count > 0
    revision = runtime.snapshot_store.current_dependent_revision(
        snapshot.identity.game_id, snapshot.player_id)
    assert "city-food-secure" in {
        value.key.predicate for value in revision.records}

    path = os.path.join(str(tmp_path), "events.jsonl")
    writer = EventWriter(
        path, snapshot.identity.game_id, durable=False,
        clock=lambda: "2026-08-01T00:00:00Z")
    parent = writer.emit(
        "state_snapshot", snapshot.turn, snapshot.event_payload())
    events = runtime.emit_current(
        writer, snapshot, caused_by=(parent["event_id"],))

    assert events[0]["type"] == "atomspace_revision_started"
    assert events[0]["caused_by"] == [parent["event_id"]]
    assert events[-1]["type"] == "atomspace_revision_committed"
    report = validate_file(path)
    assert report.valid, report.errors


def test_runtime_rematerialization_keeps_snapshot_pair_coherent():
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    runtime.replace(snapshot)
    before = runtime.snapshot_store.current_pair(
        snapshot.identity.game_id, snapshot.player_id)

    update = runtime.rematerialize(
        snapshot.identity.game_id, snapshot.player_id)
    after = runtime.snapshot_store.current_pair(
        snapshot.identity.game_id, snapshot.player_id)

    assert before[0] is after[0]
    assert after[1].snapshot_id == snapshot.snapshot_id
    assert update.revision_id == after[1].revision_id


def test_sampled_parity_publishes_verified_incremental_without_third_build():
    declaration = _enabled_city_declaration()
    declaration["config"]["cold_verify_sample_rate"] = 1.0
    semantic = dict(declaration)
    semantic.pop("declaration_hash")
    from freeciv_agent.events.schema import structural_hash
    declaration["declaration_hash"] = structural_hash(semantic)
    runtime = build_runtime(declaration)
    first = _snapshot(seq=431)
    second = _snapshot(seq=432)
    runtime.replace(first)
    prepare = runtime.dependent_store.prepare
    calls = []

    def recording_prepare(*args, **kwargs):
        calls.append(bool(kwargs.get("cold")))
        return prepare(*args, **kwargs)

    runtime.dependent_store.prepare = recording_prepare
    update = runtime.replace(second)
    current = runtime.snapshot_store.current_pair(
        second.identity.game_id, second.player_id)

    assert calls == [False, True]
    assert update.cold_verification.equivalent
    assert update.materialization_metrics.recomputed_projector_ids == ()
    assert update.materialization_metrics.reused_projector_ids == (
        "fdas-city-economy-shadow",)
    assert update.materialization_metrics.rich_recomputed_records == 0
    assert update.materialization_metrics.rich_reused_records > 0
    assert current[0] is second
    assert current[1].revision_id == update.revision_id


def test_declared_city_input_change_recomputes_rich_component():
    declaration = _enabled_city_declaration()
    declaration["config"]["cold_verify_sample_rate"] = 1.0
    semantic = dict(declaration)
    semantic.pop("declaration_hash")
    from freeciv_agent.events.schema import structural_hash
    declaration["declaration_hash"] = structural_hash(semantic)
    runtime = build_runtime(declaration)
    first = _snapshot(seq=431)
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = json.load(stream)
    payload["cities"]["3"]["surplus"][0] += 1
    second = ProxyStateDTO.parse(
        "fdas-runtime", 432, payload).to_snapshot()

    runtime.replace(first)
    update = runtime.replace(second)

    assert update.cold_verification.equivalent
    assert update.materialization_metrics.recomputed_projector_ids == (
        "fdas-city-economy-shadow",)
    assert update.materialization_metrics.reused_projector_ids == ()
    assert update.materialization_metrics.rich_recomputed_records > 0
    assert update.materialization_metrics.rich_reused_records == 0


def test_enabled_runtime_requires_world_and_empire_projection():
    declaration = _enabled_city_declaration()
    declaration["config"]["projection"]["world"] = False
    semantic = dict(declaration)
    semantic.pop("declaration_hash")
    from freeciv_agent.events.schema import structural_hash
    declaration["declaration_hash"] = structural_hash(semantic)

    with pytest.raises(
            FdasRuntimeConfigurationError, match="world and empire"):
        build_runtime(declaration)


def test_configured_global_atom_budget_is_enforced_before_publication():
    declaration = _enabled_city_declaration()
    declaration["config"]["materialization"]["maximum_atoms_global"] = 1
    semantic = dict(declaration)
    semantic.pop("declaration_hash")
    from freeciv_agent.events.schema import structural_hash
    declaration["declaration_hash"] = structural_hash(semantic)
    runtime = build_runtime(declaration)

    with pytest.raises(SnapshotConflict, match="global atom budget"):
        runtime.replace(_snapshot())
    assert runtime.snapshot_store.current_pair("fdas-runtime", 0) == (
        None, None)


def test_full_checked_projector_set_assembles_with_read_only_operations(
        tmp_path):
    declaration = load_runtime_declaration()
    declaration = copy.deepcopy(declaration)
    declaration["config"]["enabled"] = True
    semantic = dict(declaration)
    semantic.pop("declaration_hash")
    from freeciv_agent.events.schema import structural_hash
    declaration["declaration_hash"] = structural_hash(semantic)
    emitter = ControlEventEmitter()
    assert emitter.fdas_operation_records("fdas-runtime") == ()
    assert emitter._operation_stores == {}
    runtime = build_runtime(
        declaration,
        ruleset_ir=compile_ruleset(_ruleset_root(), "civ2civ3"),
        operation_records_source=lambda: emitter.fdas_operation_records(
            "fdas-runtime"),
    )

    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    assert runtime.projector_ids == (
        "fdas-city-economy-shadow", "fdas-operation-projector")
    assert runtime.ruleset_revision is not None
    assert update.atom_count <= declaration["config"]["materialization"][
        "maximum_atoms_global"]

    evaluation = runtime.evaluate_shadow(snapshot, ())
    assert evaluation.snapshot_id == snapshot.snapshot_id
    assert evaluation.revision_id == update.revision_id
    assert evaluation.comparison.legacy_candidate_count == 0
    assert evaluation.pressure.context.policy_authority is False
    assert not any(
        candidate.authority_eligible for candidate in evaluation.candidates)

    path = os.path.join(str(tmp_path), "shadow-events.jsonl")
    writer = EventWriter(
        path, snapshot.identity.game_id, durable=False,
        clock=lambda: "2026-08-01T00:00:00Z")
    parent = writer.emit(
        "state_snapshot", snapshot.turn, snapshot.event_payload())
    events = runtime.emit_shadow(
        writer, snapshot, evaluation, caused_by=(parent["event_id"],))
    assert events[-2]["type"] == "pressure_graph_built"
    assert events[-1]["type"] == "atomspace_shadow_decision"
    assert events[-1]["payload"]["details"]["authority_eligible"] is False
    assert validate_file(path).valid

    with pytest.raises(RuntimeError, match="revision-current"):
        runtime.emit_shadow(
            writer, snapshot,
            replace(evaluation, revision_id="fdas-revision-stale"))
