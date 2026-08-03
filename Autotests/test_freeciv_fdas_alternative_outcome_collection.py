import copy
from dataclasses import replace
import json
import os

import pytest

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import (
    CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY,
    CandidateInstantiation,
    CandidateOperationFactory,
    FdasAlternativeOutcomeCollectionConfig,
    FdasAlternativeOutcomeCollectionEvaluator,
    FdasCalibratedCandidateMember,
    FdasCalibratedCandidateReadout,
    FdasCalibratedCandidateUnion,
    FdasDecisionSafeCandidateReadoutConfig,
    FdasDecisionSafeCandidateReadoutEvaluator,
    FdasDefensiveCapabilityResolver,
    FdasScalarBaselineCandidateReadoutEvaluator,
    RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY,
    build_decision_safe_candidate_filter,
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


def _decision_safe_case(ir, control_interval=(0.30, 0.40, 0.50),
                        treatment_interval=(0.70, 0.80, 0.90),
                        treatment_route_turns=1,
                        prediction_reasons=(
                            "test-control", "test-treatment")):
    case = list(_movement_case(ir))
    snapshot = case[0]
    baseline = next(
        value for value in case[4]
        if value.action_key == case[3].action_key)
    treatment = next(value for value in case[4] if value != baseline)
    baseline_id = baseline.operation.operation_id
    treatment_id = treatment.operation.operation_id
    # The legacy transport fixture predates authoritative home-city and
    # veteran fields. Supply exact values for this decision-safe unit test.
    units = tuple(replace(
        value, homecity=3, veteran=0) for value in snapshot.units)
    routes = tuple(replace(
        value,
        estimated_turns=(
            treatment_route_turns
            if value.unit_id == treatment.action["actor_id"]
            else value.estimated_turns),
        total_movement_cost=(
            value.total_movement_cost * treatment_route_turns
            if value.unit_id == treatment.action["actor_id"]
            else value.total_movement_cost))
        for value in snapshot.movement_routes)
    snapshot = replace(snapshot, units=units, movement_routes=routes)
    case[0] = snapshot
    readouts = (
        FdasCalibratedCandidateReadout(
            baseline_id, baseline.action_key,
            baseline.operation.operation_type,
            1, 0.80, "estimated", prediction_reasons[0],
            "prediction-control", control_interval[1],
            control_interval[0], control_interval[2], 12, True,
            "calibrated-transition-recall"),
        FdasCalibratedCandidateReadout(
            treatment_id, treatment.action_key,
            treatment.operation.operation_type,
            2, 0.79, "estimated", prediction_reasons[1],
            "prediction-treatment", treatment_interval[1],
            treatment_interval[0], treatment_interval[2], 12, True,
            "calibrated-transition-recall"),
    )
    members = (
        FdasCalibratedCandidateMember(
            baseline_id, ("scalar-top-k", "scalar-winner")),
        FdasCalibratedCandidateMember(
            treatment_id, ("calibrated-transition-recall",)),
    )
    semantic = {
        "abstained_operation_ids": [],
        "action_selection_changed": False,
        "baseline_selected_operation_id": baseline_id,
        "calibrated_added_operation_ids": [treatment_id],
        "calibrated_per_action": 1,
        "capacity_solver_enabled": False,
        "flow_advection_enabled": False,
        "identity": "fdas-calibrated-candidate-union/1.0",
        "maximum_interval_width": 0.60,
        "members": [value.to_dict() for value in members],
        "model_result_hash": "test-calibration-model",
        "policy_authority": False,
        "readout_authority": False,
        "readouts": [value.to_dict() for value in readouts],
        "revision_id": case[1].revision_id,
        "scalar_final_score_authority": True,
        "scalar_top_k": 1,
        "snapshot_id": snapshot.snapshot_id,
        "truth_mutated": False,
    }
    calibrated = FdasCalibratedCandidateUnion(
        snapshot.snapshot_id, case[1].revision_id,
        "test-calibration-model", baseline_id, 1, 1, 0.60,
        members, readouts, (treatment_id,), (),
        structural_hash(semantic))
    return tuple(case[:6]) + (calibrated,)


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
    assert first.checks[-1] == (
        "bookkeeping-invariant-propensity-recorded-assignment")
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
        "bookkeeping-invariant-propensity-recorded-assignment",
    )
    assert all(
        value.target_ref == "city:3" for value in readout.arms)
    assert all(value.source_atom_id for value in readout.arms)


def test_bounded_nearest_score_source_does_not_require_scalar_equivalence(ir):
    case = _movement_case(ir)
    evaluator = FdasAlternativeOutcomeCollectionEvaluator(
        FdasAlternativeOutcomeCollectionConfig(
            "fdas-reinforcement-nearest-score-smoke-v1", 1777,
            allowed_action_type="unit_move",
            alternative_source="bounded-nearest-score"))

    readout = evaluator.evaluate(*case)

    assert readout.status == "eligible-shadow"
    assert readout.config["alternative_source"] == "bounded-nearest-score"
    assert "bounded-nearest-score-alternative" in readout.checks
    assert "scalar-active-winner-equivalence" not in readout.checks
    assert "single-persistence-addition" not in readout.checks


def test_randomized_diagnostic_revalidates_one_exact_authority_readout(ir):
    case = _movement_case(ir)
    evaluator = FdasAlternativeOutcomeCollectionEvaluator(
        FdasAlternativeOutcomeCollectionConfig(
            "fdas-reinforcement-randomized-pilot-v1", 1777,
            allowed_action_type="unit_move",
            alternative_source="bounded-nearest-score",
            mode="randomized-diagnostic"))

    assignment = evaluator.evaluate(*case)
    authority = evaluator.authority_readout(assignment, *case)

    assert assignment.status == "eligible-randomized-diagnostic"
    assert assignment.policy_authority
    assert assignment.claim_eligible is False
    assert assignment.action_selection_changed == (
        assignment.assigned_arm == "treatment")
    assert authority.action_key == assignment.assigned_action_key
    assert authority.operation_id == assignment.assigned_operation_id
    assert authority.snapshot_id == case[0].snapshot_id
    assert authority.legal_actions_digest == case[0].legal_actions_digest
    assert "claim-ineligible-randomized-diagnostic" in authority.provenance
    assert any(value.startswith("selection-propensity:")
               for value in authority.provenance)


def test_randomized_assignment_key_excludes_bookkeeping_hashes(ir):
    case = _movement_case(ir)
    evaluator = FdasAlternativeOutcomeCollectionEvaluator(
        FdasAlternativeOutcomeCollectionConfig(
            "fdas-reinforcement-randomized-pilot-v1", 1777,
            allowed_action_type="unit_move",
            alternative_source="bounded-nearest-score",
            mode="randomized-diagnostic"))
    assignment = evaluator.evaluate(*case)
    control, treatment = assignment.arms

    material = evaluator._assignment_material(
        case[0], control, treatment)
    changed_bookkeeping = evaluator._assignment_material(
        case[0],
        replace(
            control,
            operation_id="changed-control-operation",
            pressure_evaluation_hash="changed-control-pressure",
            resource_packet_artifact_hash="changed-control-packet",
            commit_validation_hash="changed-control-commit"),
        replace(
            treatment,
            operation_id="changed-treatment-operation",
            pressure_evaluation_hash="changed-treatment-pressure",
            resource_packet_artifact_hash="changed-treatment-packet",
            commit_validation_hash="changed-treatment-commit"))

    assert material == changed_bookkeeping
    assert set(material) == {
        "assignment_unit",
        "control_action_key",
        "experiment_id",
        "game_id",
        "policy_version",
        "randomization_seed",
        "treatment_action_key",
        "turn",
    }
    assert structural_hash(material) == assignment.assignment_material_hash


def test_shadow_assignment_cannot_be_exposed_as_action_authority(ir):
    case = _movement_case(ir)
    evaluator = FdasAlternativeOutcomeCollectionEvaluator(
        FdasAlternativeOutcomeCollectionConfig(
            "fdas-reinforcement-outcome-smoke-v1", 1777,
            allowed_action_type="unit_move"))
    assignment = evaluator.evaluate(*case)

    with pytest.raises(ValueError, match="cannot gain action authority"):
        evaluator.authority_readout(assignment, *case)


def test_alternative_collection_declaration_rejects_authority_leak():
    values = FdasAlternativeOutcomeCollectionConfig(
        "fdas-fortification-outcome-smoke-v1", 1729).to_dict()
    values["claim_eligible"] = True

    with pytest.raises(ValueError):
        FdasAlternativeOutcomeCollectionConfig.from_dict(values)


def test_decision_safe_readout_requires_interval_and_grounded_dominance(ir):
    case = list(_decision_safe_case(ir))
    case[0] = replace(case[0], movement_routes=tuple(
        replace(value, source_seq=case[0].identity.source_seq - 1)
        for value in case[0].movement_routes))
    evaluator = FdasDecisionSafeCandidateReadoutEvaluator(
        FdasDecisionSafeCandidateReadoutConfig())

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[3], case[4], case[6])

    assert readout.status == "eligible-shadow"
    assert readout.reason == "calibrated-and-grounded-dominance"
    assert readout.proposed_operation_id != readout.baseline_operation_id
    assert readout.counterfactual_change
    assert readout.to_dict()["action_selection_changed"] is False
    assert readout.to_dict()["policy_authority"] is False
    assert readout.to_dict()["readout_authority"] is False
    assert readout.to_dict()["truth_mutated"] is False
    proposed = next(
        value for value in readout.candidates
        if value.operation_id == readout.proposed_operation_id)
    assert proposed.eligibility_reason == "eligible"
    assert set(proposed.noninferiority_checks) == {
        "estimated-turns", "first-step-movement-cost",
        "homecity-relation", "hit-points", "moves-left",
        "total-movement-cost", "unit-type", "veteran-level",
    }


def test_decision_safe_readout_rejects_future_route_revision(ir):
    case = list(_decision_safe_case(ir))
    case[0] = replace(case[0], movement_routes=tuple(
        replace(value, source_seq=case[0].identity.source_seq + 1)
        for value in case[0].movement_routes))
    evaluator = FdasDecisionSafeCandidateReadoutEvaluator()

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[3], case[4], case[6])

    assert readout.status == "abstained"
    assert readout.reason == "control-grounded-transition-input-unavailable"


def test_decision_safe_readout_abstains_when_intervals_overlap(ir):
    case = _decision_safe_case(
        ir, control_interval=(0.30, 0.50, 0.70),
        treatment_interval=(0.50, 0.70, 0.90))
    evaluator = FdasDecisionSafeCandidateReadoutEvaluator()

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[3], case[4], case[6])

    assert readout.status == "abstained"
    assert readout.reason == (
        "no-separated-grounded-noninferior-alternative")
    assert any("calibrated-interval-overlap" in value
               for value in readout.rejected)
    assert not readout.counterfactual_change


def test_decision_safe_readout_abstains_on_inferior_native_route(ir):
    case = _decision_safe_case(ir, treatment_route_turns=2)
    evaluator = FdasDecisionSafeCandidateReadoutEvaluator()

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[3], case[4], case[6])

    assert readout.status == "abstained"
    assert any("grounded-noninferiority-failed" in value
               and "estimated-turns" in value
               and "total-movement-cost" in value
               for value in readout.rejected)
    assert readout.proposed_operation_id is None


def test_scalar_baseline_readout_compares_protected_union_not_live_action(ir):
    case = list(_decision_safe_case(ir))
    case[0] = replace(case[0], movement_routes=tuple(
        replace(value, source_seq=case[0].identity.source_seq - 1)
        for value in case[0].movement_routes))
    # The live action is intentionally unrelated. Scalar-baseline semantics
    # consume only the protected union and leave the live action untouched.
    case[3] = ImpactCandidate(
        {"action_type": "unit_move", "actor_id": 999,
         "target": {"x": 99, "y": 99}},
        "unit_movement", 100.0, "unrelated live action")
    evaluator = FdasScalarBaselineCandidateReadoutEvaluator()

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[4], case[6])

    assert readout.status == "eligible-shadow"
    assert readout.control_semantics == "protected-fdas-scalar-top-1"
    assert readout.baseline_operation_id == (
        case[6].baseline_selected_operation_id)
    assert readout.proposed_operation_id != readout.baseline_operation_id
    assert readout.shadow_preference
    assert readout.to_dict()["action_selection_changed"] is False
    assert readout.to_dict()["policy_authority"] is False
    assert readout.to_dict()["readout_authority"] is False
    assert readout.to_dict()["truth_mutated"] is False


def test_scalar_baseline_readout_abstains_on_interval_overlap(ir):
    case = _decision_safe_case(
        ir, control_interval=(0.30, 0.50, 0.70),
        treatment_interval=(0.50, 0.70, 0.90))
    evaluator = FdasScalarBaselineCandidateReadoutEvaluator()

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[4], case[6])

    assert readout.status == "abstained"
    assert readout.reason == (
        "no-separated-grounded-noninferior-alternative")
    assert len(readout.candidates) == 2
    alternative = next(
        value for value in readout.candidates
        if value.operation_id != readout.baseline_operation_id)
    assert alternative.eligibility_reason == "grounded-noninferior"
    assert set(alternative.noninferiority_checks) == {
        "estimated-turns", "first-step-movement-cost",
        "homecity-relation", "hit-points", "moves-left",
        "total-movement-cost", "unit-type", "veteran-level",
    }
    assert any(value.endswith(":calibrated-interval-overlap")
               for value in readout.rejected)
    assert not readout.shadow_preference


def test_scalar_baseline_overlap_exposes_grounded_failure_independently(ir):
    case = list(_decision_safe_case(
        ir, control_interval=(0.30, 0.50, 0.70),
        treatment_interval=(0.50, 0.70, 0.90)))
    treatment = next(
        value for value in case[4]
        if value.operation.operation_id
        != case[6].baseline_selected_operation_id)
    case[0] = replace(case[0], units=tuple(
        replace(value, unit_type="Different Defensive Unit")
        if value.unit_id == treatment.action["actor_id"] else value
        for value in case[0].units))
    evaluator = FdasScalarBaselineCandidateReadoutEvaluator()

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[4], case[6])

    prefix = treatment.operation.operation_id
    assert prefix + ":calibrated-interval-overlap" in readout.rejected
    assert (prefix + ":grounded-noninferiority-failed:unit-type"
            in readout.rejected)
    alternative = next(
        value for value in readout.candidates
        if value.operation_id == treatment.operation.operation_id)
    assert alternative.eligibility_reason == (
        "grounded-noninferiority-failed")
    assert "unit-type" not in alternative.noninferiority_checks
    assert readout.shadow_preference is False


def test_ruleset_defensive_capability_equates_observed_reinforcement_pair(ir):
    resolver = FdasDefensiveCapabilityResolver(ir)

    riflemen = resolver.resolve("Riflemen")
    alpine = resolver.resolve("Alpine Troops")

    assert riflemen is not None
    assert alpine is not None
    assert alpine.unit_class == riflemen.unit_class == "Land"
    assert alpine.defense == riflemen.defense == 4.0
    assert alpine.maximum_hitpoints == riflemen.maximum_hitpoints == 20.0
    assert alpine.firepower == riflemen.firepower == 1.0
    assert (alpine.defensive_effect_signature
            == riflemen.defensive_effect_signature)
    assert alpine.rule_id != riflemen.rule_id


def test_scalar_readout_uses_ruleset_defense_not_unit_name(ir):
    case = list(_decision_safe_case(ir))
    baseline_id = case[6].baseline_selected_operation_id
    baseline = next(
        value for value in case[4]
        if value.operation.operation_id == baseline_id)
    treatment = next(value for value in case[4] if value != baseline)
    case[0] = replace(case[0], units=tuple(
        replace(
            value,
            unit_type=(
                "Riflemen"
                if value.unit_id == baseline.action["actor_id"]
                else "Alpine Troops"
                if value.unit_id == treatment.action["actor_id"]
                else value.unit_type))
        for value in case[0].units))
    evaluator = FdasScalarBaselineCandidateReadoutEvaluator(
        ruleset_ir=ir)

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[4], case[6])

    assert readout.status == "eligible-shadow"
    assert readout.identity == (
        RULESET_DEFENSIVE_SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY)
    alternative = next(
        value for value in readout.candidates
        if value.operation_id != baseline_id)
    assert alternative.unit_type == "Alpine Troops"
    assert alternative.defensive_capability is not None
    assert "unit-type" not in alternative.noninferiority_checks
    assert set(alternative.noninferiority_checks) == {
        "defensive-effect-signature", "estimated-turns",
        "first-step-movement-cost", "homecity-relation", "hit-points",
        "moves-left", "ruleset-defense", "ruleset-firepower",
        "ruleset-maximum-hitpoints", "total-movement-cost", "unit-class",
        "veteran-level",
    }


def test_scalar_readout_fails_closed_without_ruleset_unit_profile(ir):
    case = list(_decision_safe_case(ir))
    baseline_id = case[6].baseline_selected_operation_id
    baseline = next(
        value for value in case[4]
        if value.operation.operation_id == baseline_id)
    case[0] = replace(case[0], units=tuple(
        replace(value, unit_type="Unknown Defensive Unit")
        if value.unit_id == baseline.action["actor_id"] else value
        for value in case[0].units))
    evaluator = FdasScalarBaselineCandidateReadoutEvaluator(
        ruleset_ir=ir)

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[4], case[6])

    assert readout.status == "abstained"
    assert readout.reason == (
        "control-ruleset-defensive-capability-unavailable")
    assert readout.candidates == ()


def test_scalar_readout_prefers_exact_calibration_grounded_pareto(ir):
    interval = (0.30, 0.40, 0.50)
    case = list(_decision_safe_case(
        ir, control_interval=interval, treatment_interval=interval,
        prediction_reasons=("action-estimate", "action-estimate")))
    baseline_id = case[6].baseline_selected_operation_id
    baseline = next(
        value for value in case[4]
        if value.operation.operation_id == baseline_id)
    case[0] = replace(case[0], movement_routes=tuple(
        replace(
            value,
            estimated_turns=2,
            total_movement_cost=value.total_movement_cost * 2)
        if value.unit_id == baseline.action["actor_id"] else value
        for value in case[0].movement_routes))
    evaluator = FdasScalarBaselineCandidateReadoutEvaluator(
        ruleset_ir=ir, calibrated_equivalence_pareto=True)

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[4], case[6])

    assert readout.status == "eligible-shadow"
    assert readout.identity == (
        CALIBRATED_EQUIVALENCE_PARETO_CANDIDATE_READOUT_IDENTITY)
    assert readout.reason == (
        "calibrated-equivalence-and-grounded-pareto-dominance")
    proposed = next(
        value for value in readout.candidates
        if value.operation_id == readout.proposed_operation_id)
    assert proposed.eligibility_reason == (
        "eligible-calibrated-equivalence-pareto")
    assert proposed.strict_grounded_improvements == (
        "estimated-turns", "total-movement-cost")
    assert proposed.calibration_prediction_reason == "action-estimate"
    assert not any(value.endswith(":calibrated-interval-overlap")
                   for value in readout.rejected)


def test_scalar_equivalence_readout_requires_strict_grounded_improvement(ir):
    interval = (0.30, 0.40, 0.50)
    case = _decision_safe_case(
        ir, control_interval=interval, treatment_interval=interval,
        prediction_reasons=("action-estimate", "action-estimate"))
    evaluator = FdasScalarBaselineCandidateReadoutEvaluator(
        ruleset_ir=ir, calibrated_equivalence_pareto=True)

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[4], case[6])

    assert readout.status == "abstained"
    alternative = next(
        value for value in readout.candidates
        if value.operation_id != readout.baseline_operation_id)
    assert alternative.eligibility_reason == "grounded-noninferior"
    assert alternative.strict_grounded_improvements == ()
    assert any(value.endswith(":calibrated-interval-overlap")
               for value in readout.rejected)


def test_scalar_baseline_readout_exposes_exact_grounding_failure(ir):
    case = list(_decision_safe_case(ir))
    case[0] = replace(case[0], movement_routes=tuple(
        replace(value, source_seq=case[0].identity.source_seq + 1)
        for value in case[0].movement_routes))
    evaluator = FdasScalarBaselineCandidateReadoutEvaluator()

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[4], case[6])

    assert readout.status == "abstained"
    assert readout.reason == (
        "control-bounded-validator-"
        "current-native-reinforcement-route-unavailable")
    assert not readout.shadow_preference


def test_scalar_baseline_readout_exposes_every_pair_scope_failure(ir):
    case = list(_decision_safe_case(ir))
    baseline = next(
        value for value in case[4]
        if value.operation.operation_id
        == case[6].baseline_selected_operation_id)
    treatment = next(value for value in case[4] if value != baseline)
    treatment = replace(
        treatment,
        resource_keys=baseline.resource_keys,
        candidate_hash=structural_hash([
            treatment.candidate_hash, "same-resource-diagnostic",
        ]))
    case[4] = tuple(
        treatment if value.operation.operation_id
        == treatment.operation.operation_id else value
        for value in case[4])
    evaluator = FdasScalarBaselineCandidateReadoutEvaluator()

    readout = evaluator.evaluate(
        case[0], case[1], case[2], case[4], case[6])

    prefix = treatment.operation.operation_id + ":pair-scope:"
    assert readout.status == "abstained"
    assert prefix + "identical-resource-set" in readout.rejected
    assert prefix + "resource-overlap:" + baseline.resource_keys[0] in (
        readout.rejected)
    assert not any(value.endswith(":pair-scope-mismatch")
                   for value in readout.rejected)
    assert len(readout.candidates) == 1
    assert not readout.shadow_preference


def test_decision_safe_filter_excludes_source_garrison_but_preserves_surface(
        ir):
    case = list(_decision_safe_case(ir))
    baseline = next(
        value for value in case[4]
        if value.operation.operation_id
        == case[6].baseline_selected_operation_id)
    unsafe = replace(
        baseline,
        blockers=tuple(sorted(set(
            baseline.blockers + ("protected-source-garrison",)))),
        candidate_hash=structural_hash([
            baseline.candidate_hash, "protected-source-garrison",
        ]))
    candidates = tuple(
        unsafe if value == baseline else value for value in case[4])

    filtered = build_decision_safe_candidate_filter(
        candidates, case[0], case[1], case[2].goals)

    assert len(filtered.readouts) == len(candidates) == 2
    assert unsafe.operation.operation_id in filtered.excluded_operation_ids
    assert len(filtered.eligible_operation_ids) == 1
    rejected = next(
        value for value in filtered.readouts
        if value.operation_id == unsafe.operation.operation_id)
    assert rejected.reason == "candidate-has-noncontractual-blockers"
    assert "protected-source-garrison" in rejected.blockers
    assert filtered.to_dict()["candidate_surface_preserved"] is True
    assert filtered.to_dict()["calibrated_union_input_filtered"] is True
    assert filtered.to_dict()["action_selection_changed"] is False
    assert filtered.to_dict()["policy_authority"] is False
    assert filtered.to_dict()["readout_authority"] is False
    assert filtered.to_dict()["truth_mutated"] is False
