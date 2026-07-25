"""PF-PLN transport, scheduling, provenance, clone, and adapter gates."""

import json
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
BENCHMARKS = os.path.join(REPO, "benchmarks")
for candidate in (SRC, BENCHMARKS):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_pressure_benchmark import (  # noqa: E402
    run_pressure_concentration_benchmark,
)
from freeciv.pf_pressure_replay import (  # noqa: E402
    direct_completion_counterfactual_paths,
    direct_completion_rescore,
    opportunity_counterfactual_paths,
    opportunity_rescore,
    replay_event_file,
    replay_paths,
    replay_snapshot_file,
    replay_snapshot_paths,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.beliefs import (  # noqa: E402
    BeliefKey,
    ConflictAtom,
    ModelProvenance,
)
from freeciv_agent.pressure import (  # noqa: E402
    AtomState,
    CloneLifecycleStore,
    CloneManager,
    CloneState,
    CloneTransactionError,
    ConductanceLearner,
    ConductanceState,
    CostVector,
    EvidenceLedger,
    EvidenceToken,
    GoalState,
    Hypothesis,
    ImpactPressureRanker,
    ObservationOutcome,
    ObservationPolicy,
    ObservationTest,
    Operation,
    PressureConfig,
    PressureEngine,
    PressureGraph,
    PressureRule,
    PressureScheduler,
    PressureVector,
    ProofPressureAdapter,
    Resolvability,
    TruthState,
    ValueOfInformationPlanner,
    confidence_to_weight,
    expected_information_value,
)


def _atom(atom_id, strength=0.0, confidence=1.0, resolvability=None):
    return (
        AtomState(atom_id, TruthState(strength, confidence, crisp=True)),
        resolvability or Resolvability(infer=1.0),
    )


def _capital_graph():
    graph = PressureGraph()
    rows = (
        _atom("survives", 0.42, 0.65, Resolvability(infer=0.5, retain=0.5)),
        _atom("no-attack", 0.25, 0.8, Resolvability(observe=0.8, act=0.2)),
        _atom("defense", 0.25, 0.9, Resolvability(infer=0.3, act=0.8)),
        _atom("treasury", 0.70, 0.70, Resolvability(observe=1.0, infer=0.2)),
        _atom("archer-available", 0.95, 0.90, Resolvability(observe=0.1, infer=0.2)),
        _atom("buy-archer", 0.0, 1.0, Resolvability(act=1.0)),
    )
    for atom, resolvability in rows:
        graph.add_atom(atom, resolvability)
    graph.add_rule(PressureRule(
        "survival-routes", ("defense", "no-attack"), "survives",
        kind="or", causal_kind="procedural", premise_weights=(0.69, 0.31)))
    graph.add_rule(PressureRule(
        "buy-route", ("treasury", "archer-available", "buy-archer"),
        "defense", kind="and", causal_kind="procedural"))
    return graph


def test_capital_pressure_is_reproducible_and_truth_is_firewalled():
    graph = _capital_graph()
    before = [atom.to_dict() for atom in graph.atoms]
    goal = GoalState("defend-capital", "survives", 0.90, utility=100.0)
    engine = PressureEngine()
    first = engine.propagate(graph, (goal,))
    second = engine.propagate(graph, (goal,))

    assert first.artifact_hash == second.artifact_hash
    assert abs(first.dependency("defend-capital", "survives") - 48.0) < 1e-12
    assert first.dependency("defend-capital", "defense") > (
        first.dependency("defend-capital", "no-attack"))
    assert first.pressure("defend-capital", "buy-archer").act > 0
    assert first.pressure("defend-capital", "treasury").observe > 0
    assert [atom.to_dict() for atom in graph.atoms] == before


def test_pressure_concentrates_and_bounds_irrelevant_route_expansion():
    first = run_pressure_concentration_benchmark()
    second = run_pressure_concentration_benchmark()
    assert first.to_dict() == second.to_dict()
    assert first.truth_unchanged
    assert first.relevant_route_selected
    assert len(first.selected_root_routes) == 32
    assert first.pressure_concentration >= 0.90
    assert first.expansion_reduction >= 0.70
    assert first.pressure_expansions < first.exhaustive_expansions
    with open(os.path.join(
            REPO, "docs", "freeciv", "evidence",
            "pf-pressure-concentration.json"), encoding="utf-8") as stream:
        assert json.load(stream) == first.to_dict()


def test_requirement_pressure_reaches_multiple_false_and_prerequisites():
    graph = PressureGraph()
    for atom_id in ("goal", "left", "right"):
        atom, resolvability = _atom(atom_id, 0.0, 1.0)
        graph.add_atom(atom, resolvability)
    graph.add_rule(PressureRule(
        "both-required", ("left", "right"), "goal",
        kind="and", causal_kind="definitional"))
    result = PressureEngine().propagate(
        graph, (GoalState("g", "goal", 1.0),))
    assert result.dependency("g", "left") > 0
    assert result.dependency("g", "right") > 0
    assert result.dependency("g", "left") == result.dependency("g", "right")


def test_cycles_are_damped_bounded_and_deterministic():
    graph = PressureGraph()
    for atom_id in ("a", "b"):
        atom, resolvability = _atom(atom_id)
        graph.add_atom(atom, resolvability)
    graph.add_rule(PressureRule(
        "a-from-b", ("b",), "a", causal_kind="definitional"))
    graph.add_rule(PressureRule(
        "b-from-a", ("a",), "b", causal_kind="definitional"))
    config = PressureConfig(damping=0.5, max_hops=100, residual_floor=1e-12)
    result = PressureEngine(config).propagate(
        graph, (GoalState("g", "a"),))
    assert result.dependency("g", "a") < 4.0
    assert result.dependency("g", "b") < 4.0
    assert result.artifact_hash == PressureEngine(config).propagate(
        graph, (GoalState("g", "a"),)).artifact_hash


def test_causal_context_and_safety_firewalls_block_action_pressure():
    graph = PressureGraph()
    goal_atom, goal_resolvability = _atom(
        "goal", resolvability=Resolvability(act=1.0))
    correlate, correlate_resolvability = _atom(
        "correlate", resolvability=Resolvability(infer=1.0, act=1.0))
    graph.add_atom(goal_atom, goal_resolvability)
    graph.add_atom(correlate, correlate_resolvability)
    graph.add_rule(PressureRule(
        "association", ("correlate",), "goal",
        causal_kind="associative"))
    result = PressureEngine().propagate(
        graph, (GoalState("safe-goal", "goal", safety=True),))
    assert result.pressure("safe-goal", "correlate").infer > 0
    assert result.pressure("safe-goal", "correlate").act == 0

    scheduler = PressureScheduler()
    associative_action = Operation(
        "bad-action", "goal", "act", CostVector(compute=1),
        causal_kind="associative")
    assert scheduler.score(associative_action, result).reason == "causal_firewall"
    harmful_action = Operation(
        "harmful", "goal", "act", CostVector(compute=1),
        causal_kind="procedural", goal_effects=(("safe-goal", -1.0),))
    assert scheduler.score(harmful_action, result).reason == "safety_firewall"


def test_cost_is_applied_by_scheduler_not_dependency_transport():
    graph = PressureGraph()
    atom, resolvability = _atom("goal", resolvability=Resolvability(act=1.0))
    graph.add_atom(atom, resolvability)
    result = PressureEngine().propagate(
        graph, (GoalState("g", "goal", utility=10.0),))
    before = result.pressure("g", "goal").act
    cheap = Operation(
        "cheap", "goal", "act", CostVector(compute=1),
        causal_kind="procedural")
    costly = Operation(
        "costly", "goal", "act", CostVector(compute=10),
        causal_kind="procedural")
    scores = PressureScheduler().score_all((costly, cheap), result)
    assert scores[0].operation_id == "cheap"
    assert result.pressure("g", "goal").act == before


def test_exact_token_union_overlap_conflict_and_observation_policy():
    ledger = EvidenceLedger(
        confidence_k=1.0, decay_rates=(("default", 0.0), ("volatile", 0.1)))
    policy = ObservationPolicy("defend", "observe", 4.2, propensity=0.5)
    ledger.register(EvidenceToken(
        "one", 1.0, confidence_to_weight(0.8), 1, "volatile",
        "scout", policy))
    ledger.register(EvidenceToken(
        "two", 0.0, confidence_to_weight(0.8), 1, "volatile",
        "independent-scout"))
    once = ledger.truth(("one",), 1)
    duplicated = ledger.truth(("one", "one"), 1)
    assert once == duplicated
    assert ledger.union(("one",), ("one", "two")) == ("one", "two")
    assert abs(ledger.overlap(("one",), ("one", "two"), 1) - 0.5) < 1e-12
    assert ledger.conflict_severity(("one",), ("two",), 1) > 0
    assert ledger.token("one").observation_policy == policy
    assert ledger.truth(("one",), 5).confidence < once.confidence


def _simulator_provenance(exact=False, confidence_cap=0.6):
    return ModelProvenance(
        "simulator", "freeciv-observation-model", "1.0",
        structural_hash({"model": "freeciv-observation-model/1.0"}),
        exact, confidence_cap)


def _observation_test(test_id, atom_id, likelihoods, cost=1.0):
    return ObservationTest(
        test_id=test_id,
        atom_id=atom_id,
        outcomes=tuple(
            ObservationOutcome(outcome_id, tuple(sorted(rows.items())))
            for outcome_id, rows in sorted(likelihoods.items())),
        cost=CostVector(compute=cost),
        model_provenance=_simulator_provenance())


def _brute_force_information_gain(hypotheses, test):
    prior = dict(
        (row.hypothesis_id, row.probability) for row in hypotheses)

    def entropy(values):
        import math
        return -sum(
            value * math.log(value, 2) for value in values if value > 0)

    prior_entropy = entropy(prior.values())
    posterior_entropy = 0.0
    for outcome in test.outcomes:
        probability = sum(
            prior[key] * outcome.likelihood(key) for key in prior)
        if probability:
            posterior_entropy += probability * entropy(tuple(
                prior[key] * outcome.likelihood(key) / probability
                for key in prior))
    return prior_entropy - posterior_entropy


def test_small_graph_voi_matches_independent_exhaustive_ranking():
    tests = (
        _observation_test("perfect", "conflict", {
            "left": {"attack": 1.0, "transit": 0.0},
            "right": {"attack": 0.0, "transit": 1.0},
        }),
        _observation_test("weak", "conflict", {
            "left": {"attack": 0.7, "transit": 0.3},
            "right": {"attack": 0.3, "transit": 0.7},
        }),
        _observation_test("uninformative", "conflict", {
            "left": {"attack": 0.5, "transit": 0.5},
            "right": {"attack": 0.5, "transit": 0.5},
        }),
    )
    for attack_probability in (0.1, 0.25, 0.5, 0.75, 0.9):
        hypotheses = (
            Hypothesis("attack", attack_probability),
            Hypothesis("transit", 1.0 - attack_probability),
        )
        ranked = ValueOfInformationPlanner.rank(hypotheses, tests)
        exhaustive = sorted(
            tests,
            key=lambda row: (
                -_brute_force_information_gain(hypotheses, row),
                row.test_id))
        assert [row.test.test_id for row in ranked] == [
            row.test_id for row in exhaustive]
        for row in ranked:
            assert abs(
                row.expected_information_gain
                - _brute_force_information_gain(hypotheses, row.test)) < 1e-12
        assert ranked[0].test.test_id == "perfect"
        assert ranked[-1].expected_information_gain == 0.0


def test_conflict_observation_schedule_uses_voi_and_preserves_truth():
    key = BeliefKey("enemy-intent", ("enemy",))
    conflict = ConflictAtom(
        "conflict-intent", key, ("scout",), ("diplomacy",),
        {"strength": 1.0, "confidence": 0.8},
        {"strength": 0.0, "confidence": 0.8},
        0.0, 0.64, ("context-a", "context-b"), 4)
    before = conflict.to_dict()
    hypotheses = (
        Hypothesis("attack", 0.5), Hypothesis("transit", 0.5))
    tests = (
        _observation_test("scout-destination", conflict.conflict_id, {
            "toward-us": {"attack": 0.9, "transit": 0.1},
            "away": {"attack": 0.1, "transit": 0.9},
        }),
        _observation_test("inspect-banner", conflict.conflict_id, {
            "red": {"attack": 0.55, "transit": 0.45},
            "blue": {"attack": 0.45, "transit": 0.55},
        }),
    )
    decision = ValueOfInformationPlanner().decision_for_conflict(
        conflict, hypotheses, tests, utility=10.0)
    assert decision["schedule"]["selected_operation_id"] == (
        "observe:scout-destination")
    selected = next(
        row for row in decision["operations"]
        if row.operation_id == decision["schedule"]["selected_operation_id"])
    assert selected.mode == "observe"
    assert selected.payload["model_provenance"]["source_kind"] == "simulator"
    assert selected.payload["observation_policy"]["channel"] == "observe"
    assert decision["pressure"].pressure(
        decision["goal"].goal_id, conflict.conflict_id).observe > 0
    assert conflict.to_dict() == before


def test_observation_and_action_share_cost_aware_scheduler():
    graph = PressureGraph()
    atom, _ = _atom(
        "uncertain-threat", strength=0.2,
        resolvability=Resolvability(observe=1.0, act=1.0))
    graph.add_atom(atom, Resolvability(observe=1.0, act=1.0))
    result = PressureEngine().propagate(
        graph, (GoalState("survive", "uncertain-threat", utility=10.0),))
    informative = Operation(
        "observe", "uncertain-threat", "observe", CostVector(compute=1),
        causal_kind="diagnostic", information_gain=0.8)
    expensive_action = Operation(
        "act", "uncertain-threat", "act", CostVector(resource=20),
        causal_kind="procedural")
    assert PressureScheduler().select(
        (expensive_action, informative), result).operation_id == "observe"
    cheap_action = Operation(
        "cheap-act", "uncertain-threat", "act", CostVector(resource=0.1),
        causal_kind="procedural")
    uninformative = Operation(
        "weak-observe", "uncertain-threat", "observe",
        CostVector(compute=10), causal_kind="diagnostic")
    assert PressureScheduler().select(
        (uninformative, cheap_action), result).operation_id == "cheap-act"


def test_conductance_credit_and_no_progress_never_change_truth():
    rule = PressureRule(
        "r", ("a",), "b", conductance=0.5, causal_kind="procedural")
    learner = ConductanceLearner(learning_rate=0.5, no_progress_rate=0.5)
    credited = learner.update(rule, 1.0, 1.0, 0.5, 0.0, 0.0)
    penalized = learner.no_progress(credited)
    assert credited.conductance > rule.conductance
    assert penalized.conductance < credited.conductance
    assert credited.premise_ids == rule.premise_ids
    assert not hasattr(credited, "truth")


def test_conductance_feedback_is_persisted_idempotent_and_truth_free():
    truth = TruthState(0.61, 0.73, ("engine-packet",))
    before = truth.to_dict()
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "conductance.json")
        state = ConductanceState(path, "attempt-1")
        credited = state.feedback(
            "city_defense", True, "action-result-success")
        assert credited.applied
        assert credited.conductance > credited.previous_conductance
        persisted_hash = state.state_hash

        replay = ConductanceState(path, "attempt-1")
        duplicate = replay.feedback(
            "city_defense", True, "action-result-success")
        assert not duplicate.applied
        assert duplicate.conductance == credited.conductance
        assert replay.state_hash == persisted_hash

        penalized = replay.feedback(
            "city_defense", False, "action-result-no-progress")
        assert penalized.applied
        assert penalized.conductance < credited.conductance
        assert ConductanceState(path, "attempt-1").state_hash == replay.state_hash
    assert truth.to_dict() == before


def test_goal_relief_feedback_separates_effect_decay_from_positive_credit():
    state = ConductanceState(
        identity="goal-relief-semantics", initial_conductance=1.0)
    effect_only = state.feedback(
        "expansion_move", True, "move-effect",
        realized_relief=0.0,
        relief_source="authoritative:no-measurable-expansion-goal-progress")
    assert effect_only.credit_kind == "effect_without_goal_relief"
    assert effect_only.no_progress_amount == 0.25
    assert effect_only.realized_relief == 0.0
    assert effect_only.conductance < effect_only.previous_conductance

    credited = state.feedback(
        "expansion_move", True, "move-downstream-credit",
        realized_relief=1.0 / 3.0,
        relief_source="authoritative:downstream-expansion-goal-trace",
        caused_by_feedback_id="city-founded")
    assert credited.credit_kind == "downstream_goal_relief"
    assert credited.caused_by_feedback_id == "city-founded"
    assert credited.no_progress_amount == 0.0
    assert credited.conductance > effect_only.conductance
    # The downstream update credits the already counted movement effect.
    assert credited.successes == effect_only.successes == 1

    duplicate = state.feedback(
        "expansion_move", True, "move-downstream-credit",
        realized_relief=1.0 / 3.0,
        relief_source="authoritative:downstream-expansion-goal-trace",
        caused_by_feedback_id="city-founded")
    assert not duplicate.applied
    assert duplicate.conductance == credited.conductance


def test_goal_relief_feedback_rejects_unobserved_or_ungrounded_credit():
    state = ConductanceState(identity="invalid-goal-relief")
    for values in (
            {"effect_observed": False, "realized_relief": 0.5,
             "relief_source": "authoritative:impossible"},
            {"effect_observed": True, "realized_relief": 0.5,
             "relief_source": None}):
        try:
            state.feedback(
                "city_founding", values["effect_observed"], "invalid",
                realized_relief=values["realized_relief"],
                relief_source=values["relief_source"])
            assert False, "invalid goal credit was accepted"
        except ValueError:
            pass


def test_impact_category_goal_mapping_matches_outcome_semantics():
    assert ImpactPressureRanker.goal_for_category(
        "production_defense") == "survival"
    assert ImpactPressureRanker.goal_for_category(
        "population_recovery") == "score"
    assert ImpactPressureRanker.goal_for_category(
        "population_recovery_move") == "score"


def test_clone_projection_loses_confidence_under_maximal_disagreement():
    manager = CloneManager()
    clones = (
        CloneState("left", "visible", 0.5, TruthState(
            0.0, 0.9, ("left-evidence",))),
        CloneState("right", "visible", 0.5, TruthState(
            1.0, 0.9, ("right-evidence",))),
    )
    visible = manager.visible_truth(clones)
    assert visible.strength == 0.5
    assert visible.confidence == 0.0
    assert manager.split_score(1, 1, 1, 1) == 1.0
    assert manager.accept_split(2, 3.0, 2, 1.0)


def test_clone_pressure_supports_expected_and_worst_tail_projection():
    manager = CloneManager()
    clones = (
        CloneState(
            "safe", "visible", 0.8, TruthState(1.0, 0.8),
            pressure=(("survival", PressureVector(act=1.0)),)),
        CloneState(
            "danger", "visible", 0.2, TruthState(0.0, 0.8),
            pressure=(("survival", PressureVector(act=9.0)),)),
    )
    assert manager.visible_pressure(clones, "survival").act == 2.6
    assert manager.visible_pressure(
        clones, "survival", risk_alpha=0.2).act == 9.0
    with pytest.raises(ValueError):
        manager.visible_pressure(clones, "survival", risk_alpha=0.0)


def test_clone_merge_rejects_divergent_successor_distributions():
    manager = CloneManager(merge_successor_tolerance=0.1)
    left = CloneState(
        "left", "visible", 0.5, TruthState(0.5, 0.8),
        successor_distribution=(("attack", 0.9), ("transit", 0.1)))
    right = CloneState(
        "right", "visible", 0.5, TruthState(0.5, 0.8),
        successor_distribution=(("attack", 0.1), ("transit", 0.9)))
    assert not manager.merge_eligible(left, right)


def test_clone_lifecycle_persists_lineage_forwards_and_enforces_cap():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "clones.json")
        manager = CloneManager(
            maximum_clones=2, split_threshold=0.5,
            merge_truth_tolerance=0.1, merge_pressure_tolerance=0.1)
        store = CloneLifecycleStore(path, manager)
        root = CloneState(
            "root", "enemy-intent", 1.0,
            TruthState(0.5, 0.4, ("root-evidence",)))
        store.initialize("enemy-intent", (root,))
        left = CloneState(
            "left", "enemy-intent", 0.5,
            TruthState(0.48, 0.8, ("left-evidence",)))
        right = CloneState(
            "right", "enemy-intent", 0.5,
            TruthState(0.52, 0.8, ("right-evidence",)))
        store.split(
            "enemy-intent", "root", (left, right),
            predictive_gain=2.0, added_parameters=1, split_score=1.0,
            event_id="split-root")
        assert store.resolve("root") == ("left", "right")
        with pytest.raises(CloneTransactionError):
            store.split(
                "enemy-intent", "left", (
                    CloneState(
                        "left-a", "enemy-intent", 0.25,
                        TruthState(0.4, 0.8)),
                    CloneState(
                        "left-b", "enemy-intent", 0.25,
                        TruthState(0.6, 0.8)),
                ),
                predictive_gain=2.0, added_parameters=1, split_score=1.0,
                event_id="split-over-cap")

        merged = CloneState(
            "merged", "enemy-intent", 1.0,
            TruthState(0.5, 0.8, ("left-evidence", "right-evidence")))
        store.merge(
            "enemy-intent", "left", "right", merged, "merge-children")
        assert store.resolve("root") == ("merged",)
        expected_hash = store.state_hash
        reopened = CloneLifecycleStore(path, manager)
        assert reopened.resolve("root") == ("merged",)
        assert reopened.state_hash == expected_hash
        assert reopened.clones("enemy-intent") == (merged,)
        # Replaying an already committed event is an idempotent read.
        assert reopened.merge(
            "enemy-intent", "left", "right", merged,
            "merge-children") == (merged,)


def test_clone_bayes_update_is_atomic_normalized_and_persistent():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "clones.json")
        store = CloneLifecycleStore(path, CloneManager(maximum_clones=2))
        store.initialize("hidden-route", (
            CloneState(
                "attack", "hidden-route", 0.5,
                TruthState(1.0, 0.8, ("attack-model",))),
            CloneState(
                "transit", "hidden-route", 0.5,
                TruthState(0.0, 0.8, ("transit-model",))),
        ))
        updated = store.bayes_update(
            "hidden-route", {"attack": 0.9, "transit": 0.1},
            "observation-1")
        assert [round(row.posterior, 12) for row in updated] == [0.9, 0.1]
        assert abs(sum(row.posterior for row in updated) - 1.0) < 1e-12
        persisted = CloneLifecycleStore(
            path, CloneManager(maximum_clones=2))
        assert persisted.clones("hidden-route") == updated
        assert persisted.bayes_update(
            "hidden-route", {"attack": 0.0, "transit": 1.0},
            "observation-1") == updated


def _proof_query():
    leaf_atom = {
        "args": ["player", "Alphabet"], "atom_id": "leaf-atom",
        "crisp": True, "predicate": "has-tech", "provenance_ids": [],
        "tv": {"confidence": 0.99, "strength": 1.0},
    }
    goal_atom = {
        "args": ["player", "Writing"], "atom_id": "goal-atom",
        "crisp": True, "predicate": "researchable", "provenance_ids": [],
        "tv": {"confidence": 0.99, "strength": 1.0},
    }
    nodes = [
        {
            "atom": goal_atom, "crisp": True, "kind": "goal",
            "node_id": "root", "premise_node_refs": ["leaf"],
            "rule_applied": "compiled-writing", "satisfied": False,
            "subtree_hash": "1" * 64,
            "tv": {"confidence": 0.99, "strength": 0.0},
        },
        {
            "atom": leaf_atom, "crisp": True, "kind": "premise",
            "node_id": "leaf", "premise_node_refs": [],
            "rule_applied": None, "satisfied": False,
            "subtree_hash": "2" * 64,
            "tv": {"confidence": 0.99, "strength": 0.0},
        },
    ]
    return SimpleNamespace(
        goal=SimpleNamespace(goal_id="research-writing"),
        proof={"nodes": nodes, "root_node_id": "root",
               "structural_hash": structural_hash(nodes)})


def test_existing_proof_dag_adapts_to_pressure_without_truth_recalculation():
    query = _proof_query()
    adapter = ProofPressureAdapter()
    context, result = adapter.evaluate(query, utility=4.0)
    leaf_id = dict(context.node_atom_ids)["leaf"]
    assert result.pressure(context.goal.goal_id, leaf_id).act > 0
    artifact = adapter.decision_artifact(query, utility=4.0)
    assert artifact["schedule"]["selected_operation_id"] is not None
    assert query.proof["nodes"][0]["tv"] == {
        "confidence": 0.99, "strength": 0.0}


class _Candidate(object):
    def __init__(self, category, utility, suffix, projection=None):
        self.category = category
        self.utility = utility
        self.action = {"action_type": suffix}
        self.rationale = suffix
        self.projection = projection

    @property
    def action_key(self):
        return self.action["action_type"]

    def to_dict(self):
        return {
            "action": self.action, "category": self.category,
            "rationale": self.rationale, "utility": self.utility,
        }


def test_learned_category_conductance_can_abandon_a_no_progress_branch():
    snapshot = SimpleNamespace(cities=(), turn=5)
    candidates = (
        _Candidate("production_economy", 1000.0, "economy"),
        _Candidate("production_military_score", 900.0, "military"),
    )
    state = ConductanceState(identity="branch-abandonment")
    ranker = ImpactPressureRanker(conductance_state=state)
    initial, _ = ranker.rank(
        snapshot, candidates, expansion_city_target=3, horizon_turn=30)
    assert initial[0].category == "production_economy"
    for index in range(8):
        state.feedback(
            "production_economy", False, "no-progress-{}".format(index))
    revised, artifact = ranker.rank(
        snapshot, candidates, expansion_city_target=3, horizon_turn=30)
    assert revised[0].category == "production_military_score"
    assert artifact["conductance_state"]["routes"][
        "production_economy"]["no_progress"] == 8


def test_optimistic_untried_route_preserves_direct_goal_completion():
    snapshot = SimpleNamespace(
        cities=(object(),), turn=5, visible_enemy_units=())
    candidates = (
        _Candidate("city_founding", 1000.0, "found"),
        _Candidate("expansion_move", 850.0, "move"),
    )
    state = ConductanceState(
        identity="optimistic-rare-route", initial_conductance=1.0)
    for index in range(20):
        state.feedback(
            "expansion_move", True, "move-success-{}".format(index))
    ordered, artifact = ImpactPressureRanker(
        conductance_state=state).rank(
            snapshot, candidates, expansion_city_target=3, horizon_turn=30)
    assert ordered[0].category == "city_founding"
    routes = artifact["conductance_state"]["routes"]
    assert routes["expansion_move"]["successes"] == 20
    assert state.value("city_founding") == 1.0
    assert state.value("expansion_move") < state.value("city_founding")


def test_failed_sites_do_not_penalize_a_new_legal_city_completion():
    snapshot = SimpleNamespace(
        cities=(object(),), turn=30, visible_enemy_units=())
    candidates = (
        _Candidate("city_founding", 1000.0, "unit_build_city"),
        _Candidate("expansion_move", 955.0, "unit_move"),
    )
    state = ConductanceState(
        identity="candidate-scoped-city-completion",
        initial_conductance=1.0)
    for index in range(4):
        state.feedback(
            "city_founding", False,
            "failed-site-{}".format(index))
    for index in range(13):
        state.feedback(
            "expansion_move", True,
            "expansion-route-{}".format(index))

    ordered, artifact = ImpactPressureRanker(
        conductance_state=state).rank(
            snapshot, candidates, expansion_city_target=3, horizon_turn=60)

    assert state.value("city_founding") < 1.0
    assert ordered[0].category == "city_founding"
    route = artifact["conductance_state"]["decision_routes"][
        "city_founding"]
    assert route == {
        "direct_completion_source":
            "authoritative:new-legal-settlement-site",
        "effective_conductance": 1.0,
        "learned_conductance": state.value("city_founding"),
        "optimistic_floor_applied": True,
    }


def test_direct_completion_floor_does_not_override_better_same_goal_action():
    snapshot = SimpleNamespace(
        cities=(object(),), turn=18, visible_enemy_units=())
    candidates = (
        _Candidate("city_founding", 1000.0, "unit_build_city"),
        _Candidate("expansion_move", 1015.0, "unit_move"),
    )
    state = ConductanceState(
        identity="better-grounded-expansion-action",
        initial_conductance=1.0)
    for index in range(4):
        state.feedback(
            "city_founding", False,
            "failed-site-{}".format(index))

    ordered, artifact = ImpactPressureRanker(
        conductance_state=state).rank(
            snapshot, candidates, expansion_city_target=3, horizon_turn=60)

    assert ordered[0].category == "expansion_move"
    route = artifact["conductance_state"]["decision_routes"][
        "city_founding"]
    assert route["direct_completion_source"] is None
    assert route["effective_conductance"] == state.value("city_founding")
    assert not route["optimistic_floor_applied"]


def test_known_hut_completion_is_not_penalized_by_other_hut_approaches():
    snapshot = SimpleNamespace(
        cities=(object(),), turn=15, visible_enemy_units=())
    candidates = (
        _Candidate(
            "hut_exploration", 945.0, "unit_move",
            {"target_is_known_hut": True}),
        _Candidate("exploration_move", 670.0, "explore"),
    )
    state = ConductanceState(
        identity="candidate-scoped-hut-completion",
        initial_conductance=1.0)
    for index in range(12):
        state.feedback(
            "hut_exploration", False,
            "failed-hut-approach-{}".format(index))

    ordered, artifact = ImpactPressureRanker(
        conductance_state=state).rank(
            snapshot, candidates, expansion_city_target=3, horizon_turn=60)

    assert state.value("hut_exploration") < 1.0
    assert ordered[0].category == "hut_exploration"
    route = artifact["conductance_state"]["decision_routes"][
        "hut_exploration"]
    assert route["direct_completion_source"] == (
        "authoritative:move-enters-packet-known-hut")
    assert route["effective_conductance"] == 1.0
    assert route["optimistic_floor_applied"]


def test_preparatory_hut_routes_retain_learned_conductance():
    snapshot = SimpleNamespace(
        cities=(object(),), turn=15, visible_enemy_units=())
    candidates = (
        _Candidate(
            "hut_exploration", 929.0, "unit_move",
            {"target_is_known_hut": False}),
        _Candidate("exploration_move", 690.0, "explore"),
    )
    state = ConductanceState(
        identity="learnable-hut-approach", initial_conductance=1.0)
    for index in range(12):
        state.feedback(
            "hut_exploration", False,
            "failed-hut-approach-{}".format(index))

    _, artifact = ImpactPressureRanker(
        conductance_state=state).rank(
            snapshot, candidates, expansion_city_target=3, horizon_turn=60)

    route = artifact["conductance_state"]["decision_routes"][
        "hut_exploration"]
    assert route["direct_completion_source"] is None
    assert route["effective_conductance"] == state.value("hut_exploration")
    assert not route["optimistic_floor_applied"]


def test_direct_completion_rescore_reconstructs_recorded_semantics_exactly():
    snapshot = SimpleNamespace(
        cities=(object(),), turn=30, visible_enemy_units=())
    candidates = (
        _Candidate("city_founding", 1000.0, "unit_build_city"),
        _Candidate("expansion_move", 955.0, "unit_move"),
    )
    state = ConductanceState(
        identity="direct-completion-replay",
        initial_conductance=1.0)
    for index in range(4):
        state.feedback(
            "city_founding", False,
            "failed-site-{}".format(index))
    for index in range(13):
        state.feedback(
            "expansion_move", True,
            "expansion-route-{}".format(index))

    class HistoricalView(object):
        # Disable only the new floor while retaining the complete recorded
        # state artifact expected by counterfactual replay.
        initial_conductance = 0.0

        def value(self, category):
            return state.value(category)

        def decision_snapshot(self):
            return state.decision_snapshot()

    old_ordered, old_artifact = ImpactPressureRanker(
        conductance_state=HistoricalView()).rank(
            snapshot, candidates, expansion_city_target=3, horizon_turn=60)
    rescored = direct_completion_rescore(
        old_artifact["schedule"]["scores"],
        old_artifact["pressure"],
        state.decision_snapshot(),
        turn=30)

    assert old_ordered[0].category == "expansion_move"
    assert rescored["recorded_semantics"]["category"] == "expansion_move"
    assert rescored["direct_completion_semantics"]["category"] == (
        "city_founding")
    assert rescored["decision_routes"]["city_founding"][
        "optimistic_floor_applied"]


def test_live_goal_truth_is_grounded_in_authoritative_threat_state():
    candidates = (
        _Candidate("production_economy", 1000.0, "produce"),
        _Candidate("tactical_move", 900.0, "advance"),
    )
    city = SimpleNamespace(x=0, y=0)
    safe = SimpleNamespace(
        cities=(city,), units=(), turn=5, visible_enemy_units=(),
        map_width=100, map_height=100)
    distant = SimpleNamespace(
        cities=(city,), units=(), turn=5,
        visible_enemy_units=(SimpleNamespace(x=20, y=20),),
        map_width=100, map_height=100)
    # Wrapping makes x=99 one tile from the city at x=0.
    threatened = SimpleNamespace(
        cities=(city,), units=(), turn=5,
        visible_enemy_units=(SimpleNamespace(x=99, y=0),),
        map_width=100, map_height=100)
    safe_ordered, safe_artifact = ImpactPressureRanker().rank(
        safe, candidates, expansion_city_target=3, horizon_turn=30)
    distant_ordered, distant_artifact = ImpactPressureRanker().rank(
        distant, candidates, expansion_city_target=3, horizon_turn=30)
    threat_ordered, threat_artifact = ImpactPressureRanker().rank(
        threatened, candidates, expansion_city_target=3, horizon_turn=30)

    assert safe_ordered[0].category == "production_economy"
    assert distant_ordered[0].category == "production_economy"
    assert threat_ordered[0].category == "tactical_move"
    safe_goals = dict(
        (row["goal_id"], row) for row in safe_artifact["pressure"]["goals"])
    threat_goals = dict(
        (row["goal_id"], row)
        for row in threat_artifact["pressure"]["goals"])
    distant_goals = dict(
        (row["goal_id"], row)
        for row in distant_artifact["pressure"]["goals"])
    assert safe_goals["pf-impact:survival"]["context"] == [
        "authoritative:no-proximate-visible-threat-or-defense-deficit"]
    assert distant_goals["pf-impact:survival"]["context"] == [
        "authoritative:no-proximate-visible-threat-or-defense-deficit"]
    assert threat_goals["pf-impact:survival"]["context"] == [
        "authoritative:visible-enemy-within-city-threat-radius:3"]
    threat_scores = threat_artifact["schedule"]["scores"]
    assert next(
        row for row in threat_scores
        if row["operation"]["payload"]["category"] == "production_economy"
    )["reason"] == "safety_firewall"
    assert next(
        row for row in threat_scores
        if row["operation"]["payload"]["category"] == "tactical_move"
    )["operation"]["cost"]["opportunity"] == 0.0


def test_fortification_opportunity_is_not_a_defense_deficit():
    candidates = (
        _Candidate("production_economy", 1000.0, "produce"),
        _Candidate("city_defense", 600.0, "fortify"),
    )
    city = SimpleNamespace(x=0, y=0)
    safe = SimpleNamespace(
        cities=(city,), units=(), turn=5, visible_enemy_units=(),
        map_width=100, map_height=100)
    distant = SimpleNamespace(
        cities=(city,), units=(), turn=5,
        visible_enemy_units=(SimpleNamespace(x=20, y=20),),
        map_width=100, map_height=100)
    threatened = SimpleNamespace(
        cities=(city,), units=(), turn=5,
        visible_enemy_units=(SimpleNamespace(x=2, y=1),),
        map_width=100, map_height=100)

    safe_ordered, safe_artifact = ImpactPressureRanker().rank(
        safe, candidates, expansion_city_target=3, horizon_turn=30)
    distant_ordered, distant_artifact = ImpactPressureRanker().rank(
        distant, candidates, expansion_city_target=3, horizon_turn=30)
    threat_ordered, threat_artifact = ImpactPressureRanker().rank(
        threatened, candidates, expansion_city_target=3, horizon_turn=30)

    assert safe_ordered[0].category == "production_economy"
    assert distant_ordered[0].category == "production_economy"
    assert threat_ordered[0].category == "city_defense"
    for artifact in (safe_artifact, distant_artifact):
        goals = dict(
            (row["goal_id"], row)
            for row in artifact["pressure"]["goals"])
        assert goals["pf-impact:survival"]["context"] == [
            "authoritative:no-proximate-visible-threat-or-defense-deficit"]
    threat_goals = dict(
        (row["goal_id"], row)
        for row in threat_artifact["pressure"]["goals"])
    assert threat_goals["pf-impact:survival"]["context"] == [
        "authoritative:visible-enemy-within-city-threat-radius:3"]


def test_impact_category_selection_is_invariant_to_legal_alternative_count():
    snapshot = SimpleNamespace(
        cities=(SimpleNamespace(x=0, y=0),), units=(), turn=5,
        visible_enemy_units=(), map_width=100, map_height=100)
    exploration = _Candidate("exploration_move", 650.0, "explore")
    one_expansion = (
        _Candidate("expansion_move", 900.0, "best expansion"),)
    many_expansion = tuple(
        _Candidate("expansion_move", 700.0 + index, "expansion {}".format(index))
        for index in range(8)) + one_expansion

    one_ordered, one_artifact = ImpactPressureRanker().rank(
        snapshot, one_expansion + (exploration,),
        expansion_city_target=3, horizon_turn=30)
    many_ordered, many_artifact = ImpactPressureRanker().rank(
        snapshot, many_expansion + (exploration,),
        expansion_city_target=3, horizon_turn=30)

    assert one_ordered[0] is one_expansion[0]
    assert many_ordered[0] is one_expansion[0]
    one_scores = one_artifact["schedule"]["scores"]
    many_scores = many_artifact["schedule"]["scores"]
    one_expansion_priority = next(
        row["priority"] for row in one_scores
        if row["operation"]["payload"]["category"] == "expansion_move")
    many_expansion_priorities = {
        row["priority"] for row in many_scores
        if row["operation"]["payload"]["category"] == "expansion_move"}
    assert many_expansion_priorities == {one_expansion_priority}
    one_expansion_cost = next(
        row["scalar_cost"] for row in one_scores
        if row["operation"]["payload"]["category"] == "expansion_move")
    many_expansion_costs = {
        row["scalar_cost"] for row in many_scores
        if row["operation"]["payload"]["category"] == "expansion_move"}
    assert many_expansion_costs == {one_expansion_cost} == {1.0}
    assert max(many_expansion_priorities) > next(
        row["priority"] for row in many_scores
        if row["operation"]["payload"]["category"] == "exploration_move")


def test_cross_goal_opportunity_cost_preserves_higher_grounded_action_value():
    snapshot = SimpleNamespace(
        cities=(SimpleNamespace(x=0, y=0),), units=(), turn=5,
        visible_enemy_units=(), map_width=100, map_height=100)
    hut = _Candidate("hut_exploration", 937.0, "resolve-known-hut")
    expansion = _Candidate("expansion_move", 859.0, "advance-founder")

    ordered, artifact = ImpactPressureRanker().rank(
        snapshot, (expansion, hut),
        expansion_city_target=3, horizon_turn=30)

    assert ordered[0] is hut
    scores = artifact["schedule"]["scores"]
    hut_score = next(
        row for row in scores
        if row["operation"]["payload"]["category"] == "hut_exploration")
    expansion_score = next(
        row for row in scores
        if row["operation"]["payload"]["category"] == "expansion_move")
    assert hut_score["operation"]["cost"]["opportunity"] == 0.0
    assert expansion_score["operation"]["cost"]["opportunity"] == 78.0
    assert hut_score["priority"] > expansion_score["priority"]
    rescored = opportunity_rescore(
        scores, artifact["pressure"])
    assert rescored["selected_operation_id"] == artifact[
        "schedule"]["selected_operation_id"]


def test_impact_adapter_keeps_goals_separate_and_emits_schema_valid_events():
    snapshot = SimpleNamespace(cities=(), turn=5)
    candidates = (
        _Candidate("production_economy", 1000.0, "produce"),
        _Candidate("production_defense", 600.0, "defend"),
    )
    ordered, artifact = ImpactPressureRanker().rank(
        snapshot, candidates, expansion_city_target=3, horizon_turn=30)
    assert ordered[0].category == "production_defense"
    assert {goal["goal_id"] for goal in artifact["pressure"]["goals"]} == {
        "pf-impact:survival", "pf-impact:expansion",
        "pf-impact:score", "pf-impact:exploration"}
    goals = dict(
        (row["goal_id"], row) for row in artifact["pressure"]["goals"])
    assert goals["pf-impact:survival"]["context"] == [
        "authoritative:grounded-production-defense-deficit"]

    pressure = artifact["pressure"]
    pressure_hash = structural_hash(pressure)
    pressure_id = "pressure-" + pressure_hash[:20]
    schedule = artifact["schedule"]
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "pressure-test", durable=False)
        root = writer.emit("run_started", 0, {
            "condition_id": "e_full_loop", "manifest_identity": "m"})
        propagated = writer.emit("pressure_propagated", 5, {
            "conductance_state": artifact["conductance_state"],
            "config": pressure["config"], "dependency": pressure["dependency"],
            "goals": pressure["goals"], "graph_hash": pressure["graph_hash"],
            "operational_pressure": pressure["pressure"],
            "pressure_id": pressure_id, "result_hash": pressure_hash,
            "traces": pressure["traces"],
        }, caused_by=[root["event_id"]])
        writer.emit("operation_scored", 5, {
            "allocations": schedule["allocations"],
            "decision_id": "decision-" + schedule["structural_hash"][:20],
            "pressure_id": pressure_id, "scores": schedule["scores"],
            "selected_operation_id": schedule["selected_operation_id"],
            "solver_identity": schedule["solver_identity"],
            "structural_hash": schedule["structural_hash"],
        }, caused_by=[propagated["event_id"]])
        update = ConductanceState(identity="event-test").feedback(
            "city_defense", True, "result-event")
        writer.emit(
            "conductance_updated", 5, update.to_dict(),
            caused_by=[propagated["event_id"]])
        relief_update = ConductanceState(
            identity="event-relief-test").feedback(
                "expansion_move", True, "result-relief-event",
                realized_relief=0.0,
                relief_source=(
                    "authoritative:no-measurable-expansion-goal-progress"))
        writer.emit(
            "conductance_updated", 5, relief_update.to_dict(),
            caused_by=[propagated["event_id"]])
        report = validate_file(path)
        replay = replay_event_file(path, "pressure-fixture")
        aggregate_replay = replay_paths(
            (path,), relative_to=directory)
        counterfactual = opportunity_counterfactual_paths(
            (path,), relative_to=directory)
        direct_counterfactual = direct_completion_counterfactual_paths(
            (path,), relative_to=directory)
    assert report.valid, report.to_dict()
    assert replay["eligibility"] == "exact_candidate_replay"
    assert replay["source_unchanged"]
    assert len(replay["decisions"]) == 1
    assert replay["decisions"][0]["changed"]
    assert replay["decisions"][0]["integrity_passed"]
    assert aggregate_replay["files_scanned"] == 1
    assert aggregate_replay["exact_replay_files"] == 1
    assert aggregate_replay["decision_change_rate"] == 1.0
    assert aggregate_replay["integrity_failures"] == 0
    assert direct_counterfactual["files_scanned"] == 1
    assert direct_counterfactual["total_decisions"] == 1
    assert direct_counterfactual["integrity_failures"] == 0
    assert direct_counterfactual["changed_decisions"] == 0
    assert aggregate_replay["sources_unchanged"]
    assert counterfactual["total_decisions"] == 1
    assert counterfactual["safety_active_decisions"] == 1
    assert counterfactual[
        "baseline_to_counterfactual_changed_decisions"] == 1
    assert counterfactual["counterfactual_changed_from_recorded"] == 0
    assert counterfactual["sources_unchanged"]


def test_legacy_event_trace_is_explicitly_audit_only_and_read_only():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "legacy-pressure-test", durable=False)
        writer.emit("run_started", 0, {
            "condition_id": "e_full_loop", "manifest_identity": "legacy"})
        first = replay_event_file(path, "legacy-fixture")
        second = replay_event_file(path, "legacy-fixture")
    assert first == second
    assert first["eligibility"] == "audit_only"
    assert first["reason"] == "legacy_missing_operation_scored"
    assert first["source_unchanged"]


def test_byte_real_snapshot_pressure_ablation_is_exact_and_read_only():
    turn_zero = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn0.json")
    turn_one = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn1.json")
    first = replay_snapshot_file(turn_one, "turn-one")
    second = replay_snapshot_file(turn_one, "turn-one")
    assert first == second
    assert first["source_unchanged"] and first["snapshot_unchanged"]
    assert first["candidate_sets_match"]
    assert first["legal_action_count"] == 134
    assert first["baseline"]["category"] == "city_founding"
    assert first["pressure"]["category"] == "city_founding"
    assert first["baseline"]["action"]["actor_id"] == 102
    assert first["pressure"]["action"]["actor_id"] == 102
    assert not first["changed_action"] and not first["changed_category"]
    assert first["pressure_integrity_passed"]

    aggregate = replay_snapshot_paths(
        (turn_zero, turn_one), relative_to=REPO)
    assert aggregate["snapshots_scanned"] == 2
    assert aggregate["comparable_snapshots"] == 1
    assert aggregate["changed_actions"] == 0
    assert aggregate["changed_categories"] == 0
    assert aggregate["changed_action_rate"] == 0.0
    assert aggregate["sources_unchanged"]
    assert aggregate["states_unchanged"]
    with open(os.path.join(
            REPO, "docs", "freeciv", "evidence",
            "pf-pressure-snapshot-replay.json"), encoding="utf-8") as stream:
        assert json.load(stream) == aggregate
