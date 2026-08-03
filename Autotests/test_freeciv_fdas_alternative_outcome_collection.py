import copy
import json
import os

import pytest

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import (
    CandidateInstantiation,
    CandidateOperationFactory,
    FdasAlternativeOutcomeCollectionConfig,
    FdasAlternativeOutcomeCollectionEvaluator,
    FdasPathPersistenceCandidateUnion,
    FdasPathPersistenceMember,
    FdasPathPersistenceReadout,
    GoalFactory,
    ImpactCandidate,
)
from freeciv_agent.planning.fdas_path_persistence_candidate_union import (
    _signal_ledger,
)
from freeciv_agent.pressure import (
    DependentAtomPressureAdapter,
    ScalarBaselineConfig,
)
from freeciv_agent.rulesets.compiler import compile_ruleset
from freeciv_agent.state import ProxyStateDTO
from freeciv_agent.state.atomspace import (
    CityEconomyProjector,
    CompositeDomainProjector,
    DependentAtomSpaceStore,
    FdasRuntime,
    FdasShadowEvaluation,
    RevisionQueryContext,
    UnitDefenseProjector,
    ruleset_digest,
)


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append("/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data")
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(
                candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for FDAS alternative collection")


@pytest.fixture(scope="module")
def ir():
    return compile_ruleset(_root(), "civ2civ3")


def _persistence_union(snapshot, revision, baseline, treatment):
    config = ScalarBaselineConfig(
        smoothing=0.35,
        route_momentum=0.15,
        minimum_dwell_steps=2,
        dwell_bonus=0.05,
        switch_margin=0.01,
        diversity_floor=0.0)
    baseline_id = baseline.operation.operation_id
    treatment_id = treatment.operation.operation_id
    route_id = "test-persistence-route"
    readouts = (
        FdasPathPersistenceReadout(
            baseline_id, baseline.operation.operation_type,
            "test-baseline-route", 1, 0.80, 0.80, 0.0, 0.0, 0.80,
            True, False),
        FdasPathPersistenceReadout(
            treatment_id, treatment.operation.operation_type,
            route_id, 2, 0.79, 0.80, 0.0, 0.05, 0.85,
            False, True),
    )
    members = (
        FdasPathPersistenceMember(baseline_id, ("scalar-winner",)),
        FdasPathPersistenceMember(
            treatment_id, ("path-persistence-recall",)),
    )
    ledger = _signal_ledger()
    semantic = {
        "action_selection_changed": False,
        "base_probe_operation_ids": [baseline_id],
        "baseline_selected_operation_id": baseline_id,
        "capacity_solver_enabled": False,
        "config": config.to_dict(),
        "expired_route_ids": [],
        "fallback_reason": None,
        "fallback_required": False,
        "flow_advection_enabled": False,
        "identity": "fdas-path-persistence-candidate-union/1.0",
        "maximum_reachability_regret": 0.05,
        "members": [value.to_dict() for value in members],
        "path_persistence_authority": False,
        "persistence_added_operation_ids": [treatment_id],
        "persistence_selected_operation_id": treatment_id,
        "persistence_selected_route_id": route_id,
        "policy_authority": False,
        "probe_union_result_hash": "test-probe-union-hash",
        "reachability_regret": 0.01,
        "readout_authority": False,
        "readouts": [value.to_dict() for value in readouts],
        "regret_rejected": False,
        "retained_by_dwell": False,
        "retained_by_hysteresis": False,
        "retained_by_smoothing": True,
        "revision_id": revision.revision_id,
        "scalar_final_score_authority": True,
        "signal_ledger": ledger.to_dict(),
        "snapshot_id": snapshot.snapshot_id,
        "source_sink_flow_enabled": False,
        "state_after_hash": "test-state-after",
        "state_before_hash": "test-state-before",
        "switch_cause": "retained-by-smoothing",
        "truth_mutated": False,
        "turn": snapshot.turn,
    }
    return FdasPathPersistenceCandidateUnion(
        snapshot.snapshot_id,
        revision.revision_id,
        snapshot.turn,
        "test-probe-union-hash",
        baseline_id,
        (baseline_id,),
        config,
        0.05,
        "test-state-before",
        "test-state-after",
        (),
        members,
        readouts,
        treatment_id,
        route_id,
        (treatment_id,),
        True,
        False,
        False,
        False,
        0.01,
        "retained-by-smoothing",
        False,
        None,
        ledger,
        structural_hash(semantic),
    )


def _case(ir):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    second = copy.deepcopy(payload["units"]["7"])
    second["id"] = 8
    payload["units"]["8"] = second
    payload["legal_actions"].extend((
        {"type": "unit_fortify", "unit_id": 7, "is_valid": True},
        {"type": "unit_fortify", "unit_id": 8, "is_valid": True},
    ))
    payload["authoritative"]["source_seq"] = 911
    snapshot = ProxyStateDTO.parse(
        "fdas-alternative-collection", 911, payload).to_snapshot()
    digest = ruleset_digest(ir)
    store = DependentAtomSpaceStore(
        domain_projector=CompositeDomainProjector((
            CityEconomyProjector(ir, digest),
            UnitDefenseProjector(ir, digest),
        )))
    revision = store.build(snapshot)
    goals = tuple(
        value for value in GoalFactory().instantiate(
            revision,
            store.query_current(snapshot.identity.game_id, snapshot.player_id))
        if value.deficit_predicate == "unit-fortification-opportunity")
    candidates = tuple(
        value for value in CandidateOperationFactory(ir, digest).instantiate(
            snapshot, goals, revision=revision)
        if value.action.get("action_type") == "unit_fortify")
    assert len(candidates) == 2
    adapter = DependentAtomPressureAdapter()
    pressure = adapter.evaluate(revision, goals, candidates)
    scores = adapter.scheduler.score_all(
        pressure.context.operations, pressure.pressure_result)
    baseline_id = pressure.schedule["selected_operation_id"]
    baseline = next(
        value for value in candidates
        if value.operation.operation_id == baseline_id)
    treatment = next(value for value in candidates if value != baseline)
    instantiation = CandidateInstantiation(
        candidates, 0, (), (), structural_hash(tuple(
            value.candidate_hash for value in candidates)))
    explanation = FdasRuntime.explain_shadow_decision(
        revision, RevisionQueryContext(revision), goals, candidates,
        instantiation, pressure)
    evaluation = FdasShadowEvaluation(
        snapshot.snapshot_id, revision.revision_id, goals, candidates,
        instantiation, pressure, None, explanation, (), 0.0)
    legacy = ImpactCandidate(
        baseline.action, "city_defense", 1.0,
        "active exact scalar fortification")
    union = _persistence_union(
        snapshot, revision, baseline, treatment)
    return (
        snapshot, revision, evaluation, legacy,
        candidates, scores, union)


def _movement_case(ir):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    payload["legal_actions"] = [
        value for value in payload["legal_actions"]
        if value.get("action_type") != "unit_move"]
    for unit_id in (7, 8):
        unit = copy.deepcopy(payload["units"]["7"])
        unit.update({
            "id": unit_id, "tile": 83, "transported": False,
            "x": 3, "y": 2,
        })
        payload["units"][str(unit_id)] = unit
        payload["legal_actions"].append({
            "action_type": "unit_move",
            "actor_id": unit_id,
            "is_valid": True,
            "movement_cost": 3,
            "target": {"x": 2, "y": 2},
            "transport_required": False,
        })
    payload["authoritative"]["source_seq"] = 912
    payload["authoritative"]["movement_routes"] = [
        {
            "authority": "freeciv-server-pathfinder",
            "destination_tile": 82,
            "estimated_turns": 1,
            "first_step_movement_cost": 3,
            "first_step_tile": 82,
            "initially_transported": False,
            "movement_points_remaining": 0,
            "moves_left_at_request": 3,
            "origin_tile": 83,
            "path_directions": [6],
            "path_length": 1,
            "reachable": True,
            "schema_version": "1.0",
            "source_seq": 912,
            "total_movement_cost": 3,
            "transported_at_request": False,
            "turn": payload["turn"],
            "unit_id": unit_id,
        }
        for unit_id in (7, 8)]
    snapshot = ProxyStateDTO.parse(
        "fdas-alternative-movement", 912, payload).to_snapshot()
    digest = ruleset_digest(ir)
    store = DependentAtomSpaceStore(
        domain_projector=CompositeDomainProjector((
            CityEconomyProjector(ir, digest),
            UnitDefenseProjector(ir, digest),
        )))
    revision = store.build(snapshot)
    goals = tuple(
        value for value in GoalFactory().instantiate(
            revision,
            store.query_current(snapshot.identity.game_id, snapshot.player_id))
        if value.deficit_predicate == "city-garrison-deficit")
    candidates = tuple(
        value for value in CandidateOperationFactory(ir, digest).instantiate(
            snapshot, goals, revision=revision)
        if value.action.get("action_type") == "unit_move")
    assert len(candidates) == 2
    adapter = DependentAtomPressureAdapter()
    pressure = adapter.evaluate(revision, goals, candidates)
    scores = adapter.scheduler.score_all(
        pressure.context.operations, pressure.pressure_result)
    baseline_id = pressure.schedule["selected_operation_id"]
    baseline = next(
        value for value in candidates
        if value.operation.operation_id == baseline_id)
    treatment = next(value for value in candidates if value != baseline)
    instantiation = CandidateInstantiation(
        candidates, 0, (), (), structural_hash(tuple(
            value.candidate_hash for value in candidates)))
    explanation = FdasRuntime.explain_shadow_decision(
        revision, RevisionQueryContext(revision), goals, candidates,
        instantiation, pressure)
    evaluation = FdasShadowEvaluation(
        snapshot.snapshot_id, revision.revision_id, goals, candidates,
        instantiation, pressure, None, explanation, (), 0.0)
    legacy = ImpactCandidate(
        baseline.action, "city_garrison_move", 1.0,
        "active exact scalar reinforcement")
    union = _persistence_union(
        snapshot, revision, baseline, treatment)
    return (
        snapshot, revision, evaluation, legacy,
        candidates, scores, union)


def test_alternative_collection_records_stable_safe_shadow_assignment(ir):
    case = _case(ir)
    evaluator = FdasAlternativeOutcomeCollectionEvaluator(
        FdasAlternativeOutcomeCollectionConfig(
            "fdas-fortification-outcome-smoke-v1", 1729,
            maximum_priority_regret=0.01))

    first = evaluator.evaluate(*case)
    second = evaluator.evaluate(*case)

    assert first == second
    assert first.status == "eligible-shadow"
    assert first.reason is None
    assert first.selection_policy_kind == "stochastic"
    assert first.selection_propensity == 0.5
    assert first.assigned_arm in ("control", "treatment")
    assert first.checks[-1] == "stable-propensity-recorded-assignment"
    assert tuple(value.arm for value in first.arms) == (
        "control", "treatment")
    assert first.arms[0].resource_keys != first.arms[1].resource_keys
    assert not first.action_selection_changed
    assert not first.policy_authority
    assert not first.truth_mutated
    assert not first.claim_eligible
    assert first.to_dict()["assignment_executed"] is False
    assert first.to_dict()["source_sink_flow_enabled"] is False


def test_alternative_collection_fails_closed_when_active_winner_differs(ir):
    case = list(_case(ir))
    case[3] = ImpactCandidate(
        {"action_type": "unit_move", "actor_id": 7,
         "target": {"direction": "e", "x": 3, "y": 2}},
        "unit_movement", 1.0, "outside randomized slice")
    evaluator = FdasAlternativeOutcomeCollectionEvaluator(
        FdasAlternativeOutcomeCollectionConfig(
            "fdas-fortification-outcome-smoke-v1", 1729))

    readout = evaluator.evaluate(*case)

    assert readout.status == "ineligible"
    assert readout.reason == (
        "active-winner-is-not-configured-defense-slice")
    assert readout.assigned_arm is None
    assert readout.selection_propensity is None
    assert not readout.policy_authority


def test_alternative_collection_preflights_matched_reinforcement_pair(ir):
    case = _movement_case(ir)
    evaluator = FdasAlternativeOutcomeCollectionEvaluator(
        FdasAlternativeOutcomeCollectionConfig(
            "fdas-reinforcement-outcome-smoke-v1", 1777,
            allowed_action_type="unit_move"))

    readout = evaluator.evaluate(*case)

    assert readout.status == "eligible-shadow"
    assert readout.config["allowed_action_type"] == "unit_move"
    assert readout.config["require_same_target_ref"] is True
    assert readout.selection_propensity == 0.5
    assert readout.checks[-3:] == (
        "control-exact-preflight",
        "treatment-exact-preflight",
        "stable-propensity-recorded-assignment",
    )
    assert all(
        value.target_ref == "city:3" for value in readout.arms)
    assert all(value.source_atom_id for value in readout.arms)


def test_alternative_collection_declaration_rejects_authority_leak():
    values = FdasAlternativeOutcomeCollectionConfig(
        "fdas-fortification-outcome-smoke-v1", 1729).to_dict()
    values["claim_eligible"] = True

    with pytest.raises(ValueError):
        FdasAlternativeOutcomeCollectionConfig.from_dict(values)
