import copy
from dataclasses import replace
import gc
import json
import os
import sys
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    ControlEventEmitter,
    DecisionEpisodeStore,
    ImpactCandidate,
)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state import ProxyStateDTO, SnapshotConflict  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    CityEconomyProjector,
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


def _two_city_snapshot(seq=431, mutate_city_three=False):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = json.load(stream)
    second = copy.deepcopy(payload["cities"]["3"])
    second.update({"id": 4, "name": "Antium", "tile": 84,
                   "x": 4, "y": 2})
    payload["cities"]["4"] = second
    if mutate_city_three:
        payload["cities"]["3"]["surplus"][0] += 1
    return ProxyStateDTO.parse(
        "fdas-runtime", seq, payload).to_snapshot()


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


def _enabled_corridor_only_declaration():
    declaration = load_runtime_declaration()
    value = copy.deepcopy(declaration)
    value["config"]["enabled"] = True
    for name in value["config"]["projection"]:
        value["config"]["projection"][name] = name in (
            "empire", "route_corridors", "world")
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


def test_calibrated_candidate_union_event_is_revision_bound_and_shadow_only(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    details = {
        "action_selection_changed": False,
        "capacity_solver_enabled": False,
        "flow_advection_enabled": False,
        "policy_authority": False,
        "readout_authority": False,
        "result_hash": "union-result-hash",
        "scalar_final_score_authority": True,
        "truth_mutated": False,
    }
    candidate_union = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    path = os.path.join(str(tmp_path), "calibrated-union-events.jsonl")
    writer = EventWriter(path, snapshot.identity.game_id, durable=False)

    event = runtime.emit_calibrated_candidate_union(
        writer, snapshot, candidate_union, "calibration-artifact-hash",
        "confirmation-report-hash")

    assert event["type"] == "atomspace_shadow_decision"
    assert event["payload"]["component_id"] == (
        "fdas-calibrated-candidate-union")
    assert event["payload"]["details"]["action_selection_changed"] is False
    assert event["payload"]["details"]["calibration_artifact_hash"] == (
        "calibration-artifact-hash")
    assert event["payload"]["details"]["confirmation_report_hash"] == (
        "confirmation-report-hash")
    assert validate_file(path).valid

    stale = SimpleNamespace(
        revision_id="fdas-revision-stale",
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    with pytest.raises(RuntimeError, match="revision-current"):
        runtime.emit_calibrated_candidate_union(
            writer, snapshot, stale, "calibration-artifact-hash",
            "confirmation-report-hash")


def test_grounded_transition_union_event_is_revision_bound_and_shadow_only(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    details = {
        "action_selection_changed": False,
        "capacity_solver_enabled": False,
        "flow_advection_enabled": False,
        "policy_authority": False,
        "readout_authority": False,
        "result_hash": "grounded-transition-union-result-hash",
        "scalar_final_score_authority": True,
        "truth_mutated": False,
    }
    candidate_union = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    path = os.path.join(
        str(tmp_path), "grounded-transition-union-events.jsonl")
    writer = EventWriter(path, snapshot.identity.game_id, durable=False)

    event = runtime.emit_grounded_transition_candidate_union(
        writer, snapshot, candidate_union, "calibration-artifact-hash",
        "confirmation-report-hash")

    assert event["type"] == "atomspace_shadow_decision"
    assert event["payload"]["component_id"] == (
        "fdas-grounded-transition-candidate-union")
    assert event["payload"]["details"]["calibration_model_kind"] == (
        "grounded-transition")
    assert event["payload"]["details"]["action_selection_changed"] is False
    assert validate_file(path).valid

    stale = SimpleNamespace(
        revision_id="fdas-revision-stale",
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    with pytest.raises(RuntimeError, match="revision-current"):
        runtime.emit_grounded_transition_candidate_union(
            writer, snapshot, stale, "calibration-artifact-hash",
            "confirmation-report-hash")


def test_scalar_baseline_readout_event_is_revision_bound_and_shadow_only(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    details = {
        "action_selection_changed": False,
        "control_semantics": "protected-fdas-scalar-top-1",
        "policy_authority": False,
        "readout_authority": False,
        "result_hash": "scalar-baseline-readout-result-hash",
        "truth_mutated": False,
    }
    readout = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    path = os.path.join(str(tmp_path), "scalar-baseline-events.jsonl")
    writer = EventWriter(path, snapshot.identity.game_id, durable=False)

    event = runtime.emit_scalar_baseline_candidate_readout(
        writer, snapshot, readout)

    assert event["type"] == "atomspace_shadow_decision"
    assert event["payload"]["component_id"] == (
        "fdas-scalar-baseline-candidate-readout")
    assert event["payload"]["details"]["control_semantics"] == (
        "protected-fdas-scalar-top-1")
    assert event["payload"]["details"]["action_selection_changed"] is False
    assert validate_file(path).valid

    stale = SimpleNamespace(
        revision_id="fdas-revision-stale",
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    with pytest.raises(RuntimeError, match="revision-current"):
        runtime.emit_scalar_baseline_candidate_readout(
            writer, snapshot, stale)


def test_decision_safe_filter_event_is_revision_bound_and_shadow_only(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    details = {
        "action_selection_changed": False,
        "calibrated_union_input_filtered": True,
        "candidate_surface_preserved": True,
        "policy_authority": False,
        "readout_authority": False,
        "result_hash": "decision-safe-filter-result-hash",
        "truth_mutated": False,
    }
    candidate_filter = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    path = os.path.join(str(tmp_path), "decision-safe-filter-events.jsonl")
    writer = EventWriter(path, snapshot.identity.game_id, durable=False)

    event = runtime.emit_decision_safe_candidate_filter(
        writer, snapshot, candidate_filter)

    assert event["type"] == "atomspace_shadow_decision"
    assert event["payload"]["component_id"] == (
        "fdas-decision-safe-candidate-filter")
    assert event["payload"]["details"]["candidate_surface_preserved"] is True
    assert event["payload"]["details"][
        "calibrated_union_input_filtered"] is True
    assert event["payload"]["details"]["action_selection_changed"] is False
    assert validate_file(path).valid

    stale = SimpleNamespace(
        revision_id="fdas-revision-stale",
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    with pytest.raises(RuntimeError, match="revision-current"):
        runtime.emit_decision_safe_candidate_filter(
            writer, snapshot, stale)


def test_target_scoped_filter_event_is_revision_bound_and_shadow_only(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    details = {
        "action_selection_changed": False,
        "calibrated_union_input_filtered": True,
        "candidate_surface_preserved": True,
        "policy_authority": False,
        "readout_authority": False,
        "result_hash": "target-filter-result-hash",
        "truth_mutated": False,
    }
    candidate_filter = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    path = os.path.join(str(tmp_path), "target-filter-events.jsonl")
    writer = EventWriter(path, snapshot.identity.game_id, durable=False)

    event = runtime.emit_target_scoped_candidate_filter(
        writer, snapshot, candidate_filter)

    assert event["type"] == "atomspace_shadow_decision"
    assert event["payload"]["component_id"] == (
        "fdas-target-scoped-candidate-filter")
    assert event["payload"]["details"]["candidate_surface_preserved"] is True
    assert event["payload"]["details"]["action_selection_changed"] is False
    assert validate_file(path).valid

    stale = SimpleNamespace(
        revision_id="fdas-revision-stale",
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    with pytest.raises(RuntimeError, match="revision-current"):
        runtime.emit_target_scoped_candidate_filter(
            writer, snapshot, stale)


def test_probe_candidate_union_event_is_revision_bound_and_shadow_only(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    details = {
        "action_selection_changed": False,
        "capacity_solver_enabled": False,
        "flow_advection_enabled": False,
        "policy_authority": False,
        "readout_authority": False,
        "result_hash": "probe-union-result-hash",
        "scalar_final_score_authority": True,
        "truth_mutated": False,
    }
    candidate_union = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    path = os.path.join(str(tmp_path), "probe-union-events.jsonl")
    writer = EventWriter(path, snapshot.identity.game_id, durable=False)

    event = runtime.emit_probe_candidate_union(
        writer, snapshot, candidate_union)

    assert event["type"] == "atomspace_shadow_decision"
    assert event["payload"]["component_id"] == (
        "fdas-probe-candidate-union")
    assert event["payload"]["details"]["action_selection_changed"] is False
    assert event["payload"]["details"][
        "scalar_final_score_authority"] is True
    assert validate_file(path).valid

    stale = SimpleNamespace(
        revision_id="fdas-revision-stale",
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    with pytest.raises(RuntimeError, match="revision-current"):
        runtime.emit_probe_candidate_union(
            writer, snapshot, stale)


def test_path_persistence_union_event_is_revision_bound_and_shadow_only(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    details = {
        "action_selection_changed": False,
        "capacity_solver_enabled": False,
        "flow_advection_enabled": False,
        "path_persistence_authority": False,
        "policy_authority": False,
        "readout_authority": False,
        "result_hash": "path-persistence-result-hash",
        "scalar_final_score_authority": True,
        "source_sink_flow_enabled": False,
        "truth_mutated": False,
    }
    candidate_union = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    path = os.path.join(str(tmp_path), "path-persistence-events.jsonl")
    writer = EventWriter(path, snapshot.identity.game_id, durable=False)

    event = runtime.emit_path_persistence_union(
        writer, snapshot, candidate_union)

    assert event["type"] == "atomspace_shadow_decision"
    assert event["payload"]["component_id"] == (
        "fdas-path-persistence-candidate-union")
    assert event["payload"]["details"]["path_persistence_authority"] is False
    assert validate_file(path).valid

    stale = SimpleNamespace(
        revision_id="fdas-revision-stale",
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    with pytest.raises(RuntimeError, match="revision-current"):
        runtime.emit_path_persistence_union(
            writer, snapshot, stale)


def test_alternative_collection_event_requires_propensity_and_no_authority(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    details = {
        "action_selection_changed": False,
        "assignment_executed": False,
        "claim_eligible": False,
        "config": {"mode": "shadow"},
        "outcome_update_scope": "control-model-only",
        "policy_authority": False,
        "selection_policy_kind": "stochastic",
        "selection_propensity": 0.5,
        "source_sink_flow_enabled": False,
        "status": "eligible-shadow",
        "truth_mutated": False,
    }
    readout = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details))
    path = os.path.join(str(tmp_path), "alternative-collection-events.jsonl")
    writer = EventWriter(path, snapshot.identity.game_id, durable=False)

    event = runtime.emit_alternative_outcome_collection(
        writer, snapshot, readout)

    assert event["type"] == "atomspace_shadow_decision"
    assert event["payload"]["component_id"] == (
        "fdas-safe-alternative-outcome-collection")
    assert event["payload"]["details"]["selection_propensity"] == 0.5
    assert validate_file(path).valid

    missing_propensity = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details, selection_propensity=None))
    with pytest.raises(RuntimeError, match="lacks propensity"):
        runtime.emit_alternative_outcome_collection(
            writer, snapshot, missing_propensity)

    authority_leak = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        to_dict=lambda: dict(details, assignment_executed=True))
    with pytest.raises(RuntimeError, match="declared scope"):
        runtime.emit_alternative_outcome_collection(
            writer, snapshot, authority_leak)


def test_randomized_alternative_assignment_and_execution_are_authority_events(
        tmp_path):
    runtime = build_runtime(_enabled_city_declaration())
    snapshot = _snapshot()
    update = runtime.replace(snapshot)
    details = {
        "action_selection_changed": True,
        "assigned_arm": "treatment",
        "assignment_executed": False,
        "claim_eligible": False,
        "config": {"mode": "randomized-diagnostic"},
        "outcome_update_scope": "control-model-only",
        "policy_authority": True,
        "selection_policy_kind": "stochastic",
        "selection_propensity": 0.5,
        "source_sink_flow_enabled": False,
        "status": "eligible-randomized-diagnostic",
        "truth_mutated": False,
    }
    assignment = SimpleNamespace(
        revision_id=update.revision_id,
        snapshot_id=snapshot.snapshot_id,
        status="eligible-randomized-diagnostic",
        policy_authority=True,
        claim_eligible=False,
        truth_mutated=False,
        action_selection_changed=True,
        assigned_action_key="test-action-key",
        assigned_arm="treatment",
        assigned_operation_id="test-operation",
        result_hash="test-assignment-result",
        selection_propensity=0.5,
        to_dict=lambda: dict(details))
    path = os.path.join(str(tmp_path), "alternative-execution-events.jsonl")
    writer = EventWriter(path, snapshot.identity.game_id, durable=False)

    assignment_event = runtime.emit_alternative_outcome_collection(
        writer, snapshot, assignment)
    execution_event = runtime.emit_alternative_outcome_execution(
        writer, snapshot, assignment, True, "action-result-1",
        True,
        episode_id="episode-1",
        caused_by=(assignment_event["event_id"],))

    assert assignment_event["type"] == "atomspace_authority_decision"
    assert execution_event["type"] == "atomspace_authority_decision"
    assert execution_event["payload"]["details"]["assignment_executed"]
    assert execution_event["payload"]["details"]["episode_id"] == (
        "episode-1")
    assert execution_event["payload"]["details"][
        "authority_catalog_reprojected"] is True
    assert execution_event["payload"]["component_version"] == "1.1"
    assert validate_file(path).valid


def test_checked_city_stability_authority_runtime_assembles_explicitly():
    declaration = load_runtime_declaration(
        os.path.join(
            REPO, "profile",
            "dependent_atomspace_city_stability_authority.yaml"),
        os.path.join(
            REPO, "profile",
            "fdas_manifest_city_stability_authority.json"),
    )
    ir = compile_ruleset(_ruleset_root(), "civ2civ3")

    runtime = build_runtime(
        declaration,
        ruleset_ir=ir,
        operation_records_source=lambda: ())

    assert runtime.enabled is True
    assert runtime.config.authority_enabled is True
    assert runtime.config.section("domain_authority") == {
        "city_defense": False,
        "city_production": False,
        "city_stability": True,
        "combat": False,
        "expansion": False,
        "local_movement": False,
        "research": False,
        "transport": False,
    }
    assert runtime._authority_adapter is not None
    assert runtime.activation_payload()["policy_authority"] is True


def test_checked_defense_shadow_runtime_assembles_only_declared_projectors():
    declaration = load_runtime_declaration(
        os.path.join(
            REPO, "profile", "dependent_atomspace_defense_shadow.yaml"),
        os.path.join(
            REPO, "profile", "fdas_manifest_defense_shadow.json"),
    )
    ir = compile_ruleset(_ruleset_root(), "civ2civ3")

    runtime = build_runtime(
        declaration,
        ruleset_ir=ir,
        operation_records_source=lambda: ())

    assert runtime.enabled is True
    assert runtime.config.shadow_enabled is True
    assert runtime.config.authority_enabled is False
    assert runtime.projector_ids == (
        "fdas-city-economy-shadow",
        "fdas-unit-defense-shadow",
        "fdas-city-region-shadow",
        "fdas-operation-projector",
    )
    assert runtime._authority_adapter is None
    activation = runtime.activation_payload()
    assert activation["manifest_status"] == "shadow-live"
    assert activation["policy_authority"] is False
    assert activation["shadow_refresh_policy"] == (
        "turn-boundary-before-readout")


def test_checked_defense_authority_runtime_installs_only_defense_adapter():
    declaration = load_runtime_declaration(
        os.path.join(
            REPO, "profile", "dependent_atomspace_defense_authority.yaml"),
        os.path.join(
            REPO, "profile", "fdas_manifest_defense_authority.json"),
    )
    ir = compile_ruleset(_ruleset_root(), "civ2civ3")

    runtime = build_runtime(
        declaration,
        ruleset_ir=ir,
        operation_records_source=lambda: (),
        episode_source=DecisionEpisodeStore(
            "fdas-defense-authority-runtime-test"))

    assert runtime.config.authority_enabled is True
    assert runtime._authority_domain == "city_defense"
    assert runtime._authority_adapter.AUTHORITY_IDENTITY == (
        "fdas-bounded-defense-fortification/1.0")
    assert runtime.projector_ids == (
        "fdas-unit-defense-shadow",
        "fdas-operation-projector",
        "fdas-episode-projector",
    )
    update = runtime.replace(_snapshot())
    legacy = runtime.snapshot_store.current_atomspaces("fdas-runtime", 0)
    assert update.atom_count > 0
    assert not legacy.authoritative
    assert not legacy.visible
    assert not legacy.uncertain
    assert runtime.dependent_store.snapshot_dependency_roots
    assert runtime.config.shadow_refresh_policy == (
        "authority-domain-before-readout")
    assert "units" in runtime.dependent_store.snapshot_dependency_roots
    assert "map_tiles" not in runtime.dependent_store.snapshot_dependency_roots
    assert "research" not in runtime.dependent_store.snapshot_dependency_roots


def test_defense_authority_domain_gate_is_available_before_materialization():
    declaration = load_runtime_declaration(
        os.path.join(
            REPO, "profile", "dependent_atomspace_defense_authority.yaml"),
        os.path.join(
            REPO, "profile", "fdas_manifest_defense_authority.json"),
    )
    runtime = build_runtime(
        declaration,
        ruleset_ir=compile_ruleset(_ruleset_root(), "civ2civ3"),
        operation_records_source=(),
        episode_source=DecisionEpisodeStore("fdas-runtime-domain-gate"),
    )

    assert not runtime.authority_relevant(None)
    assert runtime.authority_relevant(ImpactCandidate(
        {"action_type": "unit_fortify", "actor_id": 7},
        "city_defense", 1.0, "test defense winner"))
    assert not runtime.authority_relevant(ImpactCandidate(
        {"action_type": "unit_move", "actor_id": 7,
         "target": {"x": 2, "y": 2}},
        "unit_movement", 1.0, "test movement winner"))


def test_post_projection_reconciler_is_read_before_final_revision():
    runtime = build_runtime(_enabled_city_declaration())
    calls = []

    def reconcile(snapshot, revision):
        calls.append((snapshot.snapshot_id, revision.revision_id))
        return False

    runtime.configure_post_projection_reconciler(reconcile)
    update = runtime.replace(_snapshot())

    assert calls == [(update.snapshot_id, update.revision_id)]


def test_post_projection_reconciler_rematerializes_changed_durable_source(
        monkeypatch):
    runtime = build_runtime(_enabled_city_declaration())
    rematerializations = []
    original = runtime.snapshot_store.rematerialize_dependent

    def observe_rematerialization(game_id, player_id):
        rematerializations.append((game_id, player_id))
        return original(game_id, player_id)

    monkeypatch.setattr(
        runtime.snapshot_store, "rematerialize_dependent",
        observe_rematerialization)
    runtime.configure_post_projection_reconciler(
        lambda _snapshot_value, _revision: True)

    snapshot = _snapshot()
    update = runtime.replace(snapshot)

    assert rematerializations == [(
        snapshot.identity.game_id, snapshot.player_id)]
    assert update.revision_id == runtime.snapshot_store.current_dependent_revision(
        snapshot.identity.game_id, snapshot.player_id).revision_id


def test_post_projection_reconciler_fails_closed_on_untyped_result():
    runtime = build_runtime(_enabled_city_declaration())
    runtime.configure_post_projection_reconciler(
        lambda _snapshot_value, _revision: "changed")

    with pytest.raises(RuntimeError, match="must return a boolean"):
        runtime.replace(_snapshot())


def test_route_corridor_shadow_projection_can_be_activated_independently():
    runtime = build_runtime(_enabled_corridor_only_declaration())

    assert runtime.projector_ids == ("fdas-route-corridor-projector",)
    update = runtime.replace(_snapshot())
    assert update.revision_id is not None


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
    assert update.cold_verification.to_dict()["diagnostics"] == {
        "changed_atom_count": 0,
        "changed_atom_ids": [],
        "incremental_only_atom_count": 0,
        "incremental_only_atom_ids": [],
        "missing_from_incremental_atom_count": 0,
        "missing_from_incremental_atom_ids": [],
    }
    assert update.materialization_metrics.recomputed_projector_ids == ()
    assert update.materialization_metrics.reused_projector_ids == (
        "fdas-city-economy-shadow",)
    assert update.materialization_metrics.rich_recomputed_records == 0
    assert update.materialization_metrics.rich_reused_records > 0
    assert current[0] is second
    assert current[1].revision_id == update.revision_id


def test_sample_schedule_uses_stable_turn_identity_and_deduplicates():
    first = _snapshot(game_id="fdas-stable-sample", seq=431)
    second = _snapshot(game_id="fdas-stable-sample", seq=999)
    assert first.snapshot_id != second.snapshot_id
    assert first.turn == second.turn
    from freeciv_agent.events.schema import structural_hash
    sample = int(structural_hash([
        "fdas-cold-verification/2.0",
        first.identity.game_id,
        first.player_id,
        first.turn,
    ])[:13], 16) / float(16 ** 13)
    declaration = _enabled_city_declaration()
    declaration["config"]["cold_verify_sample_rate"] = (sample + 1.0) / 2.0
    semantic = dict(declaration)
    semantic.pop("declaration_hash")
    declaration["declaration_hash"] = structural_hash(semantic)
    first_runtime = build_runtime(declaration)
    second_runtime = build_runtime(declaration)

    assert first_runtime._sample_cold_verification(first)
    assert second_runtime._sample_cold_verification(second)
    assert not first_runtime._sample_cold_verification(second)
    assert not second_runtime._sample_cold_verification(first)


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
    assert update.materialization_metrics.reused_projector_ids == (
        "fdas-city-economy-shadow",)
    assert update.materialization_metrics.rich_recomputed_records > 0
    assert update.materialization_metrics.rich_reused_records > 0


def test_city_input_change_recomputes_only_affected_entity_shards():
    declaration = _enabled_city_declaration()
    declaration["config"]["cold_verify_sample_rate"] = 1.0
    semantic = dict(declaration)
    semantic.pop("declaration_hash")
    from freeciv_agent.events.schema import structural_hash
    declaration["declaration_hash"] = structural_hash(semantic)
    runtime = build_runtime(declaration)
    first = _two_city_snapshot(seq=431)
    second = _two_city_snapshot(seq=432, mutate_city_three=True)

    runtime.replace(first)
    update = runtime.replace(second)
    metrics = update.materialization_metrics

    assert update.cold_verification.equivalent
    assert metrics.recomputed_projector_ids == (
        "fdas-city-economy-shadow",)
    assert metrics.reused_projector_ids == (
        "fdas-city-economy-shadow",)
    assert metrics.recomputed_shard_ids == (
        "fdas-city-economy-shadow/empire",
        "fdas-city-economy-shadow/city:3",
    )
    assert "fdas-city-economy-shadow/city:4" in metrics.reused_shard_ids
    assert len(tuple(
        value for value in metrics.reused_shard_ids
        if "/legal-action:" in value)) == 2
    assert metrics.rich_recomputed_records > 0
    assert metrics.rich_reused_records > 0


def test_legal_action_addition_reuses_stable_action_record_shards():
    declaration = _enabled_city_declaration()
    declaration["config"]["cold_verify_sample_rate"] = 1.0
    semantic = dict(declaration)
    semantic.pop("declaration_hash")
    from freeciv_agent.events.schema import structural_hash
    declaration["declaration_hash"] = structural_hash(semantic)
    runtime = build_runtime(declaration)
    with open(FIXTURE, encoding="utf-8") as stream:
        before = json.load(stream)
    after = copy.deepcopy(before)
    after["legal_actions"].append({
        "action_type": "player_rates",
        "actor_id": 0,
        "is_valid": True,
        "luxury": 20,
        "science": 50,
        "tax": 30,
    })
    first = ProxyStateDTO.parse("fdas-runtime", 431, before).to_snapshot()
    second = ProxyStateDTO.parse("fdas-runtime", 432, after).to_snapshot()

    runtime.replace(first)
    update = runtime.replace(second)
    metrics = update.materialization_metrics

    assert update.cold_verification.equivalent
    assert len(metrics.recomputed_shard_ids) == 1
    assert metrics.recomputed_shard_ids[0].startswith(
        "fdas-city-economy-shadow/legal-action:")
    assert dict(metrics.recomputed_shard_records)[
        metrics.recomputed_shard_ids[0]] == 2
    assert len(tuple(
        value for value in metrics.reused_shard_ids
        if "/legal-action:" in value)) == 2
    assert sum(
        count for shard_id, count in metrics.reused_shard_records
        if "/legal-action:" in shard_id) == 4

    after_removal = copy.deepcopy(after)
    after_removal["legal_actions"].pop(0)
    third = ProxyStateDTO.parse(
        "fdas-runtime", 433, after_removal).to_snapshot()
    removed_actions = set(second.legal_action_json).difference(
        third.legal_action_json)
    assert len(removed_actions) == 1
    removed_action_id = CityEconomyProjector._legal_action_identity(
        next(iter(removed_actions)))[1]
    removal = runtime.replace(third)
    current = runtime.snapshot_store.current_dependent_revision(
        third.identity.game_id, third.player_id)

    assert removal.cold_verification.equivalent
    assert removal.materialization_metrics.recomputed_shard_ids == ()
    assert all(
        not (record.key.predicate in (
            "legal-action-for", "legal-action-type")
            and record.key.arguments[0].entity_id == removed_action_id)
        for record in current.records)


def test_overlapping_shards_require_valid_explicit_record_owner(monkeypatch):
    monkeypatch.delattr(
        CityEconomyProjector, "projection_shard_for_record")
    runtime = build_runtime(_enabled_city_declaration())

    with pytest.raises(
            SnapshotConflict,
            match="overlapping projection shard scopes require explicit"):
        runtime.replace(_snapshot())


def test_overlapping_shards_reject_invalid_record_owner(monkeypatch):
    monkeypatch.setattr(
        CityEconomyProjector, "projection_shard_for_record",
        staticmethod(lambda _record: "unknown-shard"))
    runtime = build_runtime(_enabled_city_declaration())

    with pytest.raises(SnapshotConflict, match="returned invalid shard owner"):
        runtime.replace(_snapshot())


def test_rich_projector_undeclared_snapshot_read_fails_closed(monkeypatch):
    monkeypatch.setattr(
        CityEconomyProjector,
        "incremental_dependency_roots",
        CityEconomyProjector.incremental_dependency_roots.difference(
            ("cities",)),
    )
    runtime = build_runtime(_enabled_city_declaration())

    with pytest.raises(
            SnapshotConflict,
            match=(
                "projection shard dependencies exceed projector "
                "declaration: empire")):
        runtime.replace(_snapshot())


def test_city_entity_shard_undeclared_dependency_fails_closed(monkeypatch):
    original = CityEconomyProjector.projection_shards

    def missing_city_prefix(self, snapshot, scopes):
        return tuple(
            replace(spec, snapshot_prefixes=("player_id",))
            if spec.shard_id == "city:3" else spec
            for spec in original(self, snapshot, scopes))

    monkeypatch.setattr(
        CityEconomyProjector, "projection_shards", missing_city_prefix)
    runtime = build_runtime(_enabled_city_declaration())

    with pytest.raises(
            SnapshotConflict,
            match=(
                "fdas-city-economy-shadow shard city:3 emitted undeclared "
                "dependencies")):
        runtime.replace(_snapshot())


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
        tmp_path, monkeypatch):
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

    observed_gc = []
    instantiate = runtime._goal_factory.instantiate

    def recording_instantiate(*args, **kwargs):
        observed_gc.append(gc.isenabled())
        return instantiate(*args, **kwargs)

    monkeypatch.setattr(
        runtime._goal_factory, "instantiate", recording_instantiate)
    evaluation = runtime.evaluate_shadow(snapshot, ())
    assert observed_gc == [False]
    assert gc.isenabled()
    assert evaluation.snapshot_id == snapshot.snapshot_id
    assert evaluation.revision_id == update.revision_id
    assert evaluation.comparison.legacy_candidate_count == 0
    assert evaluation.pressure.context.policy_authority is False
    assert evaluation.decision_explanation.route_kind == "none"
    assert evaluation.decision_explanation.selected_operation_id is None
    assert evaluation.decision_explanation.explanation_hash
    assert set(dict(evaluation.stage_latency_ms)) == {
        "candidate_instantiation", "decision_explanation",
        "goal_instantiation", "legacy_comparison", "pressure_evaluation",
        "revision_query",
    }
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
    assert events[-1]["payload"]["details"][
        "decision_explanation_hash"] == (
            evaluation.decision_explanation.explanation_hash)
    assert events[-1]["payload"]["details"]["stage_latency_ms"]
    assert validate_file(path).valid

    with pytest.raises(RuntimeError, match="revision-current"):
        runtime.emit_shadow(
            writer, snapshot,
            replace(evaluation, revision_id="fdas-revision-stale"))

    stale_snapshot = _snapshot(seq=snapshot.identity.source_seq + 1)
    assert gc.isenabled()
    with pytest.raises(RuntimeError, match="current revision"):
        runtime.evaluate_shadow(stale_snapshot, ())
    assert gc.isenabled()
