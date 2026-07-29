"""Scalar PF-v2 semantic correctness and v1 compatibility gates."""

import os
import sys
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_unified.golden import reproduce_golden  # noqa: E402
from freeciv.pf_unified.v2_benchmark import (  # noqa: E402
    run_v2_verification,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pf_runtime import (  # noqa: E402
    PFRuntimeConfigurationError,
    build_controller_activation,
    controller_declaration,
)
from freeciv_agent.pressure import (  # noqa: E402
    AtomState,
    CloneState,
    CloneManager,
    CostVector,
    DeadlineFit,
    DeadlineState,
    FactorDemand,
    GoalState,
    Operation,
    PressureEngine,
    PressureEngineV2,
    PressureArtifactValidationError,
    PressureGraph,
    PressureMagnitude,
    PressureRule,
    PressureScheduler,
    PressureVector,
    PressureV2Policy,
    ProofPressureAdapterV2,
    Resolvability,
    RequirementSet,
    RiskHysteresis,
    RiskProfile,
    SignedPressureVector,
    TruthAssessment,
    TruthState,
    decision_relevant_uncertainty,
    estimate_uncertain_loss,
    evaluate_deadline,
    premise_support_requests,
    requirement_set_for_rule,
    validate_pressure_artifact,
)


def _single_atom_result(confidence, policy=None, strength=0.5):
    graph = PressureGraph()
    graph.add_atom(
        AtomState(
            "target", TruthState(strength, confidence, crisp=False)),
        Resolvability(infer=1.0, observe=1.0, act=1.0))
    goal = GoalState("goal", "target", utility=10.0)
    result = PressureEngineV2(policy=policy).propagate(graph, (goal,))
    return graph, goal, result


def test_equal_strength_different_confidence_has_equal_action_deficit():
    _, goal, high = _single_atom_result(0.9)
    _, _, low = _single_atom_result(0.2)
    action = Operation(
        "act", "target", "act", CostVector(compute=1.0),
        causal_kind="procedural")
    scheduler = PressureScheduler()

    assert high.demand(goal.goal_id).achievement == 5.0
    assert low.demand(goal.goal_id).achievement == 5.0
    assert high.pressure("goal", "target").value("act") == (
        low.pressure("goal", "target").value("act"))
    assert scheduler.score(action, high).priority == (
        scheduler.score(action, low).priority)


def test_low_confidence_increases_observation_pressure():
    _, _, high = _single_atom_result(0.9)
    _, _, low = _single_atom_result(0.2)

    assert low.demand("goal").epistemic > high.demand("goal").epistemic
    assert low.pressure("goal", "target").value("observe") > (
        high.pressure("goal", "target").value("observe"))
    assert low.epistemic_pressure(
        "goal", "target").value("observe") > (
        high.epistemic_pressure(
            "goal", "target").value("observe"))


def test_low_confidence_does_not_automatically_increase_action_pressure():
    _, _, certain = _single_atom_result(1.0, strength=1.0)
    _, _, uncertain = _single_atom_result(0.1, strength=1.0)

    assert certain.pressure("goal", "target").value("act") == 0.0
    assert uncertain.pressure("goal", "target").value("act") == 0.0
    assert uncertain.pressure("goal", "target").value("observe") > 0.0


def test_precautionary_action_requires_explicit_risk_policy():
    _, _, default = _single_atom_result(0.1, strength=1.0)
    policy = PressureV2Policy(
        precautionary_action_enabled=True,
        precautionary_action_scale=0.5)
    _, _, precautionary = _single_atom_result(
        0.1, policy=policy, strength=1.0)

    assert default.pressure("goal", "target").value("act") == 0.0
    assert precautionary.pressure(
        "goal", "target").value("act") == 0.45
    assert precautionary.to_dict()["policy"][
        "precautionary_action_enabled"]


def _premise_graph(first_confidence):
    graph = PressureGraph()
    graph.add_atom(
        AtomState("goal", TruthState(0.0, 1.0)),
        Resolvability(infer=1.0))
    graph.add_atom(
        AtomState("first", TruthState(0.5, first_confidence)),
        Resolvability(act=1.0))
    graph.add_atom(
        AtomState("second", TruthState(0.5, 0.9)),
        Resolvability(act=1.0))
    graph.add_rule(PressureRule(
        "requirements", ("first", "second"), "goal",
        kind="and", causal_kind="procedural"))
    return graph


def test_supported_strength_is_not_used_as_v2_achievement_deficit():
    goal = GoalState("g", "goal")
    low = PressureEngineV2().propagate(
        _premise_graph(0.1), (goal,))
    high = PressureEngineV2().propagate(
        _premise_graph(0.9), (goal,))

    assert low.achievement_dependency("g", "first") == (
        high.achievement_dependency("g", "first"))
    assert low.achievement_pressure(
        "g", "first").value("act") == (
        high.achievement_pressure(
            "g", "first").value("act"))

    legacy_low = PressureEngine().propagate(
        _premise_graph(0.1), (goal,))
    legacy_high = PressureEngine().propagate(
        _premise_graph(0.9), (goal,))
    assert legacy_low.pressure("g", "first").act != (
        legacy_high.pressure("g", "first").act)


def test_v2_artifact_serializes_separate_demands_and_identity():
    _, _, result = _single_atom_result(0.25)
    value = result.to_dict()

    assert value["pressure_artifact_schema"] == "2.0"
    assert value["teleology_semantics"] == (
        "achievement-uncertainty-split/1.0")
    assert value["demands"]["goal"] == {
        "achievement_demand": 5.0,
        "deadline_demand": 0.0,
        "direction": 1.0,
        "epistemic_demand": 0.75,
        "safety_demand": 0.0,
        "source_goal_id": "goal",
    }
    assert value["achievement_pressure"] != value["epistemic_pressure"]
    assert result.artifact_hash == structural_hash(value)


def test_truth_assessment_and_observation_uncertainty_are_state_separate():
    truth = TruthState(0.8, 0.2)
    assessment = TruthAssessment.from_truth(
        truth, posterior_variance=0.12)
    value = decision_relevant_uncertainty(
        truth, decision_sensitivity=2.0,
        posterior_variance=0.12)

    assert assessment.achievement_deficit(1.0) == (
        1.0 - truth.strength)
    assert assessment.epistemic_uncertainty() == 0.12
    assert value.amount == 0.24
    assert value.to_dict()["semantics"] == (
        "decision-relevant-uncertainty/1.0")


def _proof_query():
    nodes = [
        {
            "atom": {
                "args": ["player", "Writing"],
                "atom_id": "goal-atom",
                "crisp": True,
                "predicate": "researchable",
                "provenance_ids": [],
                "tv": {"confidence": 0.4, "strength": 0.0},
            },
            "crisp": True,
            "kind": "goal",
            "node_id": "root",
            "premise_node_refs": ["leaf"],
            "rule_applied": "compiled-writing",
            "satisfied": False,
            "subtree_hash": "1" * 64,
            "tv": {"confidence": 0.4, "strength": 0.0},
        },
        {
            "atom": {
                "args": ["player", "Alphabet"],
                "atom_id": "leaf-atom",
                "crisp": False,
                "predicate": "has-tech",
                "provenance_ids": [],
                "tv": {"confidence": 0.3, "strength": 0.8},
            },
            "crisp": False,
            "kind": "premise",
            "node_id": "leaf",
            "premise_node_refs": [],
            "rule_applied": None,
            "satisfied": False,
            "subtree_hash": "2" * 64,
            "tv": {"confidence": 0.3, "strength": 0.8},
        },
    ]
    return SimpleNamespace(
        goal=SimpleNamespace(goal_id="research-writing"),
        proof={
            "nodes": nodes,
            "root_node_id": "root",
            "structural_hash": structural_hash(nodes),
        })


def test_proof_adapter_can_opt_into_v2_without_changing_v1_default():
    artifact = ProofPressureAdapterV2().decision_artifact(
        _proof_query(), utility=4.0)

    assert artifact["pressure"]["pressure_artifact_schema"] == "2.0"
    assert artifact["schedule"]["selected_operation_id"] is not None


def test_v1_golden_artifacts_remain_byte_exact_in_compatibility_mode():
    report = reproduce_golden()

    assert report["byte_exact"], report["mismatches"]


def test_signed_pressure_addition_is_commutative_and_associative():
    left = SignedPressureVector(
        positive=PressureMagnitude(act=2.0, infer=1.0),
        negative=PressureMagnitude(observe=0.5))
    middle = SignedPressureVector(
        positive=PressureMagnitude(observe=1.5),
        negative=PressureMagnitude(act=0.25))
    right = SignedPressureVector(
        positive=PressureMagnitude(retain=0.75),
        negative=PressureMagnitude(infer=0.5))

    assert left.plus(middle) == middle.plus(left)
    assert left.plus(middle).plus(right) == (
        left.plus(middle.plus(right)))


def test_equal_opposing_pressure_preserves_conflict_mass():
    pressure = SignedPressureVector(
        positive=PressureMagnitude(act=3.0),
        negative=PressureMagnitude(act=3.0))

    assert pressure.net("act") == 0.0
    assert pressure.conflict("act") == 3.0
    assert pressure.value("act") == 6.0
    assert pressure.total_conflict == 3.0
    assert pressure.to_dict()["positive"]["act"] == 3.0
    assert pressure.to_dict()["negative"]["act"] == 3.0


def test_clone_pressure_projection_preserves_signed_channels():
    first = CloneState(
        "first", "atom", 0.25, TruthState(0.5, 0.8),
        pressure=(("goal", SignedPressureVector(
            positive=PressureMagnitude(act=4.0),
            negative=PressureMagnitude(observe=2.0))),))
    second = CloneState(
        "second", "atom", 0.75, TruthState(0.5, 0.8),
        pressure=(("goal", SignedPressureVector(
            positive=PressureMagnitude(act=2.0),
            negative=PressureMagnitude(observe=4.0))),))
    manager = CloneManager()

    projected = manager.visible_pressure((first, second), "goal")
    serialized = first.to_dict()
    restored = CloneState.from_dict(serialized)

    assert projected.positive.act == 2.5
    assert projected.negative.observe == 3.5
    assert serialized["pressure_schema_version"] == "2.0"
    assert restored == first


def test_v1_pressure_artifact_round_trip_is_explicitly_versioned():
    legacy = PressureVector(act=2.0, observe=1.0, direction=-1.0)
    signed = SignedPressureVector.from_v1(legacy)

    assert signed.negative.act == 2.0
    assert signed.positive.total == 0.0
    with pytest.raises(ValueError, match="conflict_policy"):
        PressureVector.from_signed(signed)
    assert PressureVector.from_signed(
        signed, conflict_policy="net") == legacy

    mixed = SignedPressureVector(
        positive=PressureMagnitude(act=1.0),
        negative=PressureMagnitude(observe=1.0))
    with pytest.raises(ValueError, match="mixed channel"):
        PressureVector.from_signed(mixed, conflict_policy="net")


def test_signed_conflict_is_visible_to_scheduler_and_tie_breaking_is_fixed():
    goal = GoalState("goal", "target", utility=1.0)
    pressures = {
        "conflicted": SignedPressureVector(
            positive=PressureMagnitude(act=1.0),
            negative=PressureMagnitude(act=1.0)),
        "clear": SignedPressureVector(
            positive=PressureMagnitude(act=1.0)),
    }
    result = SimpleNamespace(
        goals=(goal,),
        config=PressureEngineV2().config,
        artifact_hash="v2-pressure",
        pressure=lambda goal_id, atom_id: pressures[atom_id])
    conflicted = Operation(
        "z-conflicted", "conflicted", "act",
        CostVector(compute=1.0), causal_kind="procedural")
    clear = Operation(
        "a-clear", "clear", "act",
        CostVector(compute=1.0), causal_kind="procedural")
    scheduler = PressureScheduler()

    forward = scheduler.score_all((conflicted, clear), result)
    reverse = scheduler.score_all((clear, conflicted), result)

    assert [row.operation_id for row in forward] == [
        row.operation_id for row in reverse]
    assert forward[0].operation_id == "a-clear"
    conflict_score = next(
        row for row in forward if row.operation_id == "z-conflicted")
    assert conflict_score.conflict_penalty == 1.0
    assert conflict_score.goal_effects[0].conflict_pressure == 1.0


def _risk_result(goals, pressure=1.0):
    vector = SignedPressureVector(
        positive=PressureMagnitude(act=pressure))
    return SimpleNamespace(
        goals=tuple(goals),
        config=PressureEngineV2().config,
        artifact_hash="risk-pressure",
        pressure=lambda goal_id, atom_id: vector)


def test_goal_risk_sensitivity_monotonically_penalizes_risky_operation():
    estimate = estimate_uncertain_loss(
        0.2, outcome_variance=0.1, confidence=0.9,
        provenance=("authoritative-projection",))
    operation = Operation(
        "risky", "target", "act", CostVector(compute=1.0),
        causal_kind="procedural",
        risk_estimates=(("*", estimate),))
    neutral = GoalState(
        "goal", "target", risk_sensitivity=0.0)
    averse = GoalState(
        "goal", "target", risk_sensitivity=1.0)
    scheduler = PressureScheduler()

    neutral_score = scheduler.score(
        operation, _risk_result((neutral,)))
    averse_score = scheduler.score(
        operation, _risk_result((averse,)))

    assert averse_score.priority < neutral_score.priority
    assert averse_score.risk_penalty > neutral_score.risk_penalty
    assert averse_score.risk_traces[0].provenance == (
        "authoritative-projection",)


def test_same_operation_has_different_risk_value_for_survival_and_score_goals():
    estimate = estimate_uncertain_loss(
        0.2, outcome_variance=0.05, confidence=0.9)
    operation = Operation(
        "shared-risk", "target", "act", CostVector(compute=1.0),
        causal_kind="procedural",
        risk_estimates=(("*", estimate),))
    survival = GoalState(
        "survival", "target", risk_sensitivity=1.0, safety=True)
    score = GoalState(
        "score", "target", risk_sensitivity=0.0)

    result = PressureScheduler().score(
        operation, _risk_result((survival, score)))
    traces = dict(
        (trace.goal_id, trace) for trace in result.risk_traces)

    assert traces["survival"].penalty > 0.0
    assert traces["score"].penalty == 0.0
    assert traces["survival"].tail_loss == traces["score"].tail_loss


def test_low_confidence_widens_risk_without_becoming_harm_probability():
    certain = estimate_uncertain_loss(
        0.2, outcome_variance=0.01, confidence=1.0)
    uncertain = estimate_uncertain_loss(
        0.2, outcome_variance=0.01, confidence=0.2)

    assert uncertain.expected_loss == certain.expected_loss
    assert uncertain.variance > certain.variance
    assert uncertain.cvar > certain.cvar
    assert uncertain.confidence == 0.2


def test_safety_tail_risk_hard_vetoes_irreversible_commitment():
    profile = RiskProfile(
        aversion=1.0, max_tail_loss=0.5, hard_gate=True)
    goal = GoalState(
        "survival", "target", safety=True, risk_profile=profile)
    estimate = estimate_uncertain_loss(
        0.4, outcome_variance=0.2, confidence=0.8)
    operation = Operation(
        "irreversible", "target", "act", CostVector(compute=1.0),
        causal_kind="procedural",
        risk_estimates=(("survival", estimate),),
        reversible=False, externally_consequential=True)

    score = PressureScheduler().score(
        operation, _risk_result((goal,)))

    assert not score.admissible
    assert score.reason == "risk_tail_firewall:max_tail_loss"
    assert score.risk_traces[0].hard_gate
    assert score.risk_traces[0].gate_reason == "max_tail_loss"


def test_reversible_low_cost_operation_uses_soft_risk_gate():
    profile = RiskProfile(
        aversion=0.5, max_tail_loss=0.2, hard_gate=True)
    goal = GoalState(
        "survival", "target", safety=True, risk_profile=profile)
    estimate = estimate_uncertain_loss(
        0.2, outcome_variance=0.1, confidence=0.8)
    operation = Operation(
        "reversible", "target", "act", CostVector(compute=0.1),
        causal_kind="procedural",
        risk_estimates=(("survival", estimate),),
        reversible=True)

    score = PressureScheduler().score(
        operation, _risk_result((goal,)))

    assert score.admissible
    assert score.risk_penalty > 0.0
    assert not score.risk_traces[0].hard_gate
    assert score.risk_traces[0].gate_reason == "max_tail_loss"


def test_plan_risk_hysteresis_prevents_threshold_chatter():
    policy = RiskProfile(
        hysteresis_enter=0.30, hysteresis_exit=0.50)
    state = RiskHysteresis()

    assert state.evaluate("plan", 0.25, policy)
    assert state.evaluate("plan", 0.45, policy)
    assert not state.evaluate("plan", 0.55, policy)
    assert not state.evaluate("plan", 0.40, policy)
    assert state.evaluate("plan", 0.20, policy)


def test_deadline_state_exposes_completion_slack_and_probability():
    certain = DeadlineState(
        current_turn=10, deadline_turn=20,
        expected_completion_turn=18.0)
    uncertain = DeadlineState(
        current_turn=10, deadline_turn=20,
        expected_completion_turn=20.0,
        completion_variance=4.0)

    assert certain.slack == 2.0
    assert evaluate_deadline(certain).probability == 1.0
    estimate = evaluate_deadline(uncertain)
    assert estimate.probability == 0.5
    assert estimate.method == "normal-completion/1.0"
    assert estimate.to_dict()["state"]["slack"] == 0.0


def test_known_completion_after_horizon_is_a_hard_deadline_gate():
    state = DeadlineState(
        current_turn=5, deadline_turn=20,
        expected_completion_turn=21.0)
    estimate = evaluate_deadline(
        state, hard_horizon_turn=20)
    goal = GoalState("goal", "target")
    operation = Operation(
        "late", "target", "act", CostVector(compute=1.0),
        causal_kind="procedural", deadline_estimate=estimate)

    score = PressureScheduler().score(
        operation, _risk_result((goal,)))

    assert estimate.hard_gate
    assert estimate.probability == 0.0
    assert not score.admissible
    assert score.reason == (
        "deadline_firewall:known-completion-after-horizon")


def test_absent_deadline_is_explicit_and_does_not_create_urgency():
    goal = GoalState("goal", "target", deadline=None)
    state = goal.deadline_state(
        current_turn=4, expected_completion_turn=10.0)
    estimate = evaluate_deadline(state)

    assert state.deadline_turn is None
    assert state.slack is None
    assert estimate.probability == 1.0
    assert estimate.deadline_urgency == 0.0
    assert estimate.method == "no-deadline/1.0"


def test_deadline_urgency_is_not_double_counted_in_operation_priority():
    state = DeadlineState(
        current_turn=0, deadline_turn=10,
        expected_completion_turn=5.0)
    low_urgency = DeadlineFit(
        state, probability=0.8, deadline_urgency=0.1,
        hard_gate=False, gate_reason=None, method="test")
    high_urgency = DeadlineFit(
        state, probability=0.8, deadline_urgency=0.9,
        hard_gate=False, gate_reason=None, method="test")
    goal = GoalState("goal", "target", urgency=2.0)
    low = Operation(
        "low", "target", "act", CostVector(compute=1.0),
        causal_kind="procedural", deadline_estimate=low_urgency)
    high = Operation(
        "high", "target", "act", CostVector(compute=1.0),
        causal_kind="procedural", deadline_estimate=high_urgency)
    result = _risk_result((goal,))
    scheduler = PressureScheduler()

    assert scheduler.score(low, result).priority == (
        scheduler.score(high, result).priority)
    assert high.to_dict()["deadline_estimate"][
        "deadline_urgency"] == 0.9


def _and_graph(arity):
    graph = PressureGraph()
    graph.add_atom(
        AtomState("goal", TruthState(0.0, 1.0)),
        Resolvability(infer=1.0))
    premise_ids = tuple(
        "premise-{}".format(index) for index in range(arity))
    for premise_id in premise_ids:
        graph.add_atom(
            AtomState(premise_id, TruthState(0.0, 1.0)),
            Resolvability(act=1.0))
    rule = PressureRule(
        "all-required", premise_ids, "goal",
        kind="and", causal_kind="procedural")
    graph.add_rule(rule)
    return graph, rule


def test_and_requirement_set_retains_full_parent_demand():
    graph, _ = _and_graph(4)
    result = PressureEngineV2().propagate(
        graph, (GoalState("g", "goal"),))
    factor = result.factor_demands[0]

    assert isinstance(factor, FactorDemand)
    assert factor.amount == 0.85
    matching = [
        row for row in result.premise_support_requests
        if row.requirement_set_id == factor.factor_id
        and row.demand_component == "achievement"]
    assert abs(sum(row.requested_amount for row in matching)
               - factor.amount) < 1e-12
    assert abs(sum(row.share for row in matching) - 1.0) < 1e-12


def test_and_total_coalition_demand_is_arity_invariant():
    one, _ = _and_graph(1)
    eight, _ = _and_graph(8)
    goal = GoalState("g", "goal")
    one_result = PressureEngineV2().propagate(one, (goal,))
    eight_result = PressureEngineV2().propagate(eight, (goal,))

    assert one_result.factor_demands[0].amount == (
        eight_result.factor_demands[0].amount)
    assert len(eight_result.requirement_sets) == 1
    assert len(eight_result.requirement_sets[0].premise_ids) == 8


def test_partial_and_completion_cannot_fire_rule():
    graph, rule = _and_graph(3)
    requirement_set = requirement_set_for_rule(rule)

    assert not requirement_set.complete({
        "premise-0": 1, "premise-1": 1})
    assert requirement_set.complete({
        "premise-0": 1, "premise-1": 1, "premise-2": 1})


def test_lazy_coalition_generation_never_enumerates_power_set():
    _, rule = _and_graph(16)
    requirement_set = requirement_set_for_rule(rule)

    assert isinstance(requirement_set, RequirementSet)
    assert len(requirement_set.premise_ids) == 16
    assert len(requirement_set.to_dict()["role_ids"]) == 16
    assert requirement_set_for_rule(PressureRule(
        "or-route", ("left", "right"), "goal", kind="or")) is None


def test_temporal_critical_path_gets_more_support_without_erasing_others():
    _, rule = _and_graph(3)
    requirement_set = requirement_set_for_rule(rule)
    requests = premise_support_requests(
        requirement_set, 10.0,
        raw_weights=(10.0, 1.0, 1.0),
        exploration_floor=0.10,
        goal_id="g")
    shares = dict(
        (row.premise_id, row.share) for row in requests)

    assert shares["premise-0"] > shares["premise-1"]
    assert shares["premise-1"] > 0.0
    assert shares["premise-2"] > 0.0
    assert abs(sum(shares.values()) - 1.0) < 1e-12


def test_controller_activation_preserves_v1_and_declares_v2_layers():
    legacy = build_controller_activation({})
    v2 = build_controller_activation({
        "pressure_semantics_version": "v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_distributional_risk_enabled": True,
    })

    assert controller_declaration()["schema_version"] == "2.0"
    assert legacy["layers"]["scalar_pf_v1"]["enabled"]
    assert not legacy["layers"]["scalar_pf_v2"]["enabled"]
    assert v2["layers"]["scalar_pf_v2"]["enabled"]
    assert v2["layers"]["packet_scheduler"]["enabled"]
    assert not v2["layers"]["bridge"]["enabled"]
    assert legacy["controller_policy"][
        "pressure_controller_mode"] == "legacy_scalar"
    assert v2["controller_policy"][
        "pressure_controller_mode"] == "scalar_v2"
    assert v2["activation_hash"] == structural_hash({
        key: value for key, value in v2.items()
        if key != "activation_hash"
    })

    bridge = build_controller_activation({
        "pressure_controller_mode": "bridge_scalar",
        "pressure_semantics_version": "v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_bridge_enabled": True,
    })
    assert bridge["layers"]["bridge"]["enabled"]
    assert bridge["layers"][
        "teleological_cost_to_go"]["enabled"]
    assert not bridge["layers"]["source_sink_flow"]["enabled"]


def test_controller_activation_invalid_combinations_fail_closed():
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="require pressure semantics v2"):
        build_controller_activation({
            "pressure_semantics_version": "v1",
            "pressure_packet_scheduler_enabled": True,
        })
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="flow requires bridge"):
        build_controller_activation({
            "pressure_semantics_version": "v2",
            "pressure_packet_scheduler_enabled": True,
            "pressure_flow_enabled": True,
        })
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="bridge_scalar mode requires"):
        build_controller_activation({
            "pressure_controller_mode": "bridge_scalar",
            "pressure_semantics_version": "v2",
            "pressure_packet_scheduler_enabled": True,
        })


def test_pressure_artifact_validator_decodes_v1_and_v2():
    graph, goal, v2 = _single_atom_result(0.5)
    v1 = PressureEngine().propagate(graph, (goal,))

    assert validate_pressure_artifact(
        v1.to_dict())["pressure_artifact_schema"] == "1.0"
    assert validate_pressure_artifact(
        v2.to_dict())["pressure_artifact_schema"] == "2.0"
    changed = v2.to_dict()
    changed["pressure_representation"] = "unknown"
    with pytest.raises(
            PressureArtifactValidationError,
            match="representation"):
        validate_pressure_artifact(changed)


def test_g1_verification_replays_v1_v2_packets_and_real_snapshots():
    report = run_v2_verification()

    assert report["valid"]
    assert report["v1_byte_exact"]
    assert report["v2_deterministic"]
    assert report["snapshot_replay_safe_and_legal"]
    playable = next(
        row for row in report["snapshot_replay"]
        if row["candidate_count"])
    assert playable["v1_selected"] == playable["v2_selected"]
