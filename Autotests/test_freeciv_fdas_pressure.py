import copy
import json
import os
import sys
from dataclasses import replace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    CandidateInstantiation,
    CandidateOperationFactory,
    FDASCommitBinding,
    FDASCommitValidator,
    GoalFactory,
    ImpactCandidate,
    ValidationDisposition,
    legacy_shadow_goal_routes,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    DependentAtomPressureAdapter,
    DependentAtomSchedulingBridge,
    MaterializationBudget,
    PacketBudget,
    ResourceKind,
)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    CityEconomyProjector,
    DependentAtomSpaceStore,
    FdasRuntime,
    RevisionQueryContext,
    ruleset_digest,
)


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
    pytest.skip("set FREECIV_RULESET_ROOT for FDAS pressure integration")


@pytest.fixture(scope="module")
def ir():
    return compile_ruleset(_root(), "civ2civ3")


def _payload():
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = json.load(stream)
    payload = copy.deepcopy(payload)
    payload["cities"]["3"].update({
        "disorder": True,
        "surplus": [0, 0, 4, 1, 0, 9],
    })
    payload["authoritative"]["player"].update({
        "gold": 0,
        "gold_per_turn": -2,
        "gold_upkeep_reserve": 3,
        "gold_upkeep_style": "Mixed",
        "unit_gold_upkeep": 3,
    })
    payload["authoritative"]["research"]["beakers_per_turn"] = 0
    payload["legal_actions"].extend(({
        "type": "city_governor",
        "city_id": 3,
        "target": {
            "food_surplus_reserve": 1,
            "require_happy": True,
        },
        "is_valid": True,
    }, {
        "type": "player_rates",
        "player_id": 0,
        "target": {
            "tax_rate": 50,
            "science_rate": 40,
            "luxury_rate": 10,
        },
        "is_valid": True,
    }))
    return payload


def _case(ir, seq=440):
    snapshot = ProxyStateDTO.parse(
        "fdas-pressure", seq, _payload()).to_snapshot()
    digest = ruleset_digest(ir)
    store = DependentAtomSpaceStore(
        domain_projector=CityEconomyProjector(ir, digest))
    revision = store.build(snapshot)
    goals = GoalFactory().instantiate(
        revision,
        store.query_current(snapshot.identity.game_id, snapshot.player_id),
    )
    candidates = CandidateOperationFactory(ir, digest).instantiate(
        snapshot, goals)
    return snapshot, revision, goals, candidates


def test_pressure_shadow_is_deterministic_read_only_and_explainable(ir):
    _snapshot_value, revision, goals, candidates = _case(ir)
    before = revision.to_dict()

    assert len({
        candidate.operation.operation_id for candidate in candidates
    }) == len(candidates)

    first = DependentAtomPressureAdapter().evaluate(
        revision, goals, candidates)
    second = DependentAtomPressureAdapter().evaluate(
        revision, goals, candidates)

    assert first.status == "complete"
    assert first.reason is None
    assert first.evaluation_hash == second.evaluation_hash
    assert first.to_dict() == second.to_dict()
    assert first.context.policy_authority is False
    assert first.context.truncated is False
    assert first.context.goals
    assert first.context.gap_atom_ids
    assert revision.to_dict() == before
    assert all(
        rule.source["deficit_atom_id"]
        and rule.source["explanation_hash"]
        and rule.source["revision_id"] == revision.revision_id
        for rule in first.context.graph.rules)


def test_selected_gap_has_revision_bound_why_not_explanation(ir):
    _snapshot_value, revision, goals, _candidates = _case(ir)
    result = DependentAtomPressureAdapter().evaluate(revision, goals, ())
    instantiation = CandidateInstantiation(
        (), 0, (), (), structural_hash("gap-only-instantiation"))

    explanation = FdasRuntime.explain_shadow_decision(
        revision, RevisionQueryContext(revision), goals, (), instantiation,
        result)

    assert explanation.route_kind == "gap"
    assert explanation.selected_operation_id.startswith("fdas-expand-gap:")
    assert explanation.candidate is None
    assert explanation.blockers == ("no-current-legal-causal-route",)
    assert len(explanation.goal_routes) == 1
    assert explanation.causal_rules[0]["causal_kind"] == "diagnostic"
    assert explanation.pressure_operation["payload"]["reason"] == (
        "no-current-legal-causal-route")

    unknown_schedule = dict(
        result.schedule, selected_operation_id="fdas-unknown-operation")
    with pytest.raises(RuntimeError, match="no candidate or gap route"):
        FdasRuntime.explain_shadow_decision(
            revision, RevisionQueryContext(revision), goals, (),
            instantiation, replace(result, schedule=unknown_schedule))

    scoreless_schedule = dict(result.schedule, scores=[])
    with pytest.raises(RuntimeError, match="unique scheduler evidence"):
        FdasRuntime.explain_shadow_decision(
            revision, RevisionQueryContext(revision), goals, (),
            instantiation, replace(result, schedule=scoreless_schedule))


def test_candidate_budget_preserves_protected_legacy_binding(ir):
    payload = _payload()
    payload["legal_actions"].extend({
        "type": "city_governor",
        "city_id": 3,
        "target": {"food_surplus_reserve": reserve},
        "is_valid": True,
    } for reserve in (2, 3, 4))
    snapshot = ProxyStateDTO.parse(
        "fdas-pressure-budget", 441, payload).to_snapshot()
    digest = ruleset_digest(ir)
    store = DependentAtomSpaceStore(
        domain_projector=CityEconomyProjector(ir, digest))
    revision = store.build(snapshot)
    goals = GoalFactory().instantiate(
        revision,
        store.query_current(snapshot.identity.game_id, snapshot.player_id))
    uncapped = CandidateOperationFactory(
        ir, digest,
        maximum_unprotected_candidates_per_goal=1000).instantiate(
            snapshot, goals, revision=revision)
    by_goal = {}
    for candidate in uncapped:
        for goal_id in candidate.operation.goal_ids:
            by_goal.setdefault(goal_id, []).append(candidate)
    alternatives = next(
        sorted(values, key=lambda value: value.action_key)
        for values in by_goal.values() if len(values) > 2)
    protected = alternatives[-1].action_key

    report = CandidateOperationFactory(
        ir, digest,
        maximum_unprotected_candidates_per_goal=1).instantiate_report(
            snapshot, goals, revision=revision,
            protected_action_keys=(protected,))

    assert protected in {
        candidate.action_key for candidate in report.candidates}
    assert report.omitted_unprotected_count > 0
    assert report.diagnostics == (
        "unprotected-candidate-budget-exhausted:{}".format(
            report.omitted_unprotected_count),)
    assert report.instantiation_hash


def test_legacy_category_route_is_projected_but_remains_noncausal(ir):
    snapshot, revision, goals, _candidates = _case(ir)
    food_goal = next(
        goal for goal in goals
        if goal.deficit_predicate == "city-food-deficit")
    action = next(
        json.loads(action_key) for action_key in snapshot.legal_action_json
        if json.loads(action_key).get("action_type") == "city_production")
    legacy = ImpactCandidate(
        action, "production_food_stabilization", 1.0,
        "frozen legacy comparison route")
    routes = legacy_shadow_goal_routes((legacy,))

    report = CandidateOperationFactory(ir, ruleset_digest(ir)).instantiate_report(
        snapshot, goals, revision=revision,
        protected_action_keys=(legacy.action_key,),
        protected_goal_routes=routes)
    projected = next(
        candidate for candidate in report.candidates
        if (candidate.action_key == legacy.action_key
            and food_goal.goal.goal_id in candidate.operation.goal_ids))

    assert routes == ((legacy.action_key, "city-food-deficit"),)
    assert "legacy-shadow-control-route-uncompiled" in projected.blockers
    assert projected.authority_eligible is False
    assert "legacy-impact-control-route/1.0" in projected.provenance

    defense_goal = replace(
        food_goal, deficit_predicate="city-garrison-deficit")
    defense_legacy = replace(legacy, category="production_defense")
    defense_report = CandidateOperationFactory(
        ir, ruleset_digest(ir)).instantiate_report(
            snapshot, (defense_goal,), revision=revision,
            protected_action_keys=(defense_legacy.action_key,),
            protected_goal_routes=legacy_shadow_goal_routes((
                defense_legacy,)))
    defense = next(
        candidate for candidate in defense_report.candidates
        if candidate.action_key == defense_legacy.action_key)
    assert "uncompiled-action-effect" in defense.blockers
    assert "legacy-shadow-control-route-uncompiled" in defense.blockers


def test_unknown_effects_can_expand_but_never_receive_act_pressure(ir):
    _snapshot_value, revision, goals, candidates = _case(ir)
    result = DependentAtomPressureAdapter().evaluate(
        revision, goals, candidates)
    operation_by_id = {
        value.operation_id: value for value in result.context.operations}

    for operation_id, atom_id in result.context.candidate_atom_ids:
        operation = operation_by_id[operation_id]
        assert operation.mode == "expand"
        assert operation.causal_kind == "diagnostic"
        assert operation.payload["blockers"] == [
            "uncompiled-action-effect"]
        assert operation.payload["authority_eligible"] is False
        assert all(
            result.pressure_result.pressure(
                goal.goal_id, atom_id).value("act") == 0.0
            for goal in result.context.goals)

    selected = operation_by_id[result.schedule["selected_operation_id"]]
    assert selected.mode == "expand"
    assert selected.payload["authority_eligible"] is False
    assert not any(
        value.mode == "act" for value in result.context.operations)


def test_procedural_route_boundary_remains_shadow_only(ir):
    _snapshot_value, revision, goals, candidates = _case(ir)
    source = candidates[0]
    route_goal_id = source.operation.goal_ids[0]
    route_goal = next(
        value for value in goals if value.goal.goal_id == route_goal_id)
    compiled_effect_candidate = replace(source, blockers=())

    result = DependentAtomPressureAdapter().evaluate(
        revision, (route_goal,), (compiled_effect_candidate,))
    operation = result.context.operations[0]
    atom_id = result.context.candidate_atom_ids[0][1]

    assert result.status == "complete"
    assert operation.mode == "act"
    assert operation.causal_kind == "procedural"
    assert result.pressure_result.pressure(
        route_goal_id, atom_id).value("act") > 0.0
    assert operation.payload["authority_eligible"] is False
    assert result.context.policy_authority is False

    instantiation = CandidateInstantiation(
        (compiled_effect_candidate,), 0, (), (),
        structural_hash((compiled_effect_candidate.candidate_hash,)))
    explanation = FdasRuntime.explain_shadow_decision(
        revision, RevisionQueryContext(revision), (route_goal,),
        (compiled_effect_candidate,), instantiation, result)

    assert explanation.route_kind == "candidate"
    assert explanation.selected_operation_id == operation.operation_id
    assert explanation.candidate["legal_bound"] is True
    assert explanation.candidate["resource_keys"]
    assert explanation.candidate["operation"]["steps"][0][
        "completion_predicate_id"]
    assert explanation.goal_routes[0]["deficit_explanation"][
        "structural_hash"] == route_goal.explanation_hash
    assert explanation.causal_rules[0]["source"][
        "deficit_atom_id"] == route_goal.deficit_atom_id
    assert explanation.explanation_hash


def test_budget_exhaustion_is_unknown_without_orphan_false_target(ir):
    _snapshot_value, revision, goals, candidates = _case(ir)
    result = DependentAtomPressureAdapter().evaluate(
        revision,
        goals,
        candidates,
        MaterializationBudget(
            maximum_atoms=1,
            maximum_rules=1,
            maximum_operations=1),
    )

    assert result.status == "unknown"
    assert result.reason == "materialization-budget-exhausted"
    assert result.pressure_result is None
    assert result.context.truncated
    assert result.context.diagnostics == ("atom-budget-exhausted",)
    assert result.context.graph.atoms == ()
    assert result.schedule["selected_operation_id"] is None

    instantiation = CandidateInstantiation(
        tuple(candidates), 0, (), (), structural_hash("budget-case"))
    explanation = FdasRuntime.explain_shadow_decision(
        revision, RevisionQueryContext(revision), goals, candidates,
        instantiation, result)
    assert explanation.route_kind == "none"
    assert explanation.selected_operation_id is None
    assert "materialization-budget-exhausted" in explanation.blockers
    assert "atom-budget-exhausted" in explanation.blockers


def test_stale_goal_revision_is_rejected(ir):
    _snapshot_value, revision, goals, candidates = _case(ir)
    stale = replace(goals[0], snapshot_id="stale-snapshot")

    with pytest.raises(ValueError, match="stale snapshot"):
        DependentAtomPressureAdapter().build_context(
            revision, (stale,), candidates)


def test_blocked_routes_request_no_action_resources(ir):
    snapshot, revision, goals, candidates = _case(ir)
    evaluation = DependentAtomPressureAdapter().evaluate(
        revision, goals, candidates)
    scheduling = DependentAtomSchedulingBridge().schedule(
        evaluation,
        candidates,
        snapshot,
        packet_budgets=(
            PacketBudget(ResourceKind.ACTION, 1),
            PacketBudget(ResourceKind.CPU, 8),
        ),
    )

    assert scheduling.resource_schedule.requests == ()
    assert scheduling.resource_schedule.capacities == ()
    assert scheduling.resource_schedule.selected_operation_ids == ()
    assert scheduling.packet_schedule.committed_operation_ids == ()
    assert scheduling.joint_selected_operation_ids == ()
    assert scheduling.policy_authority is False


def test_exact_resource_and_packet_bridge_select_one_shared_city_slot(ir):
    snapshot, revision, goals, candidates = _case(ir)
    governor = tuple(
        replace(value, blockers=())
        for value in candidates
        if value.resource_keys == ("city-governor-slot:3",))
    goal_ids = {
        goal_id for value in governor for goal_id in value.operation.goal_ids}
    route_goals = tuple(
        value for value in goals if value.goal.goal_id in goal_ids)
    assert len(governor) == len(route_goals) == 2
    evaluation = DependentAtomPressureAdapter().evaluate(
        revision, route_goals, governor)
    bridge = DependentAtomSchedulingBridge()
    first = bridge.schedule(
        evaluation,
        governor,
        snapshot,
        packet_budgets=(
            PacketBudget(ResourceKind.ACTION, 1),
            PacketBudget(ResourceKind.CPU, 1),
        ),
    )
    second = bridge.schedule(
        evaluation,
        governor,
        snapshot,
        packet_budgets=(
            PacketBudget(ResourceKind.ACTION, 1),
            PacketBudget(ResourceKind.CPU, 1),
        ),
    )

    assert len(first.resource_schedule.requests) == 2
    assert len(first.resource_schedule.capacities) == 1
    assert len(first.resource_schedule.selected_operation_ids) == 1
    assert len(first.packet_schedule.committed_operation_ids) == 1
    assert first.joint_selected_operation_ids == (
        first.resource_schedule.selected_operation_ids)
    rejected = tuple(
        value for value in first.resource_schedule.entries
        if not value.selected)
    assert len(rejected) == 1
    assert rejected[0].reason == "exclusive-resource-conflict"
    assert rejected[0].conflicting_operation_ids
    assert all(
        claim.exclusive
        for request in first.resource_schedule.requests
        for claim in request.claims)
    assert first.artifact_hash == second.artifact_hash
    assert (first.resource_schedule.decision_digest
            == second.resource_schedule.decision_digest)
    assert first.policy_authority is False


def test_unmapped_resource_identity_fails_closed(ir):
    snapshot, revision, goals, candidates = _case(ir)
    source = candidates[0]
    goal_id = source.operation.goal_ids[0]
    goal = next(value for value in goals if value.goal.goal_id == goal_id)
    malformed = replace(
        source, blockers=(), resource_keys=("unmapped-resource:3",))
    evaluation = DependentAtomPressureAdapter().evaluate(
        revision, (goal,), (malformed,))
    scheduling = DependentAtomSchedulingBridge().schedule(
        evaluation, (malformed,), snapshot)

    assert scheduling.resource_schedule.requests == ()
    assert scheduling.joint_selected_operation_ids == ()
    assert "unmapped-resource-identity:{}".format(
        malformed.operation.operation_id) in scheduling.diagnostics
    assert "packet-budgets-not-provided" in scheduling.diagnostics


def test_commit_binding_revalidates_supports_and_rejects_shadow_authority(ir):
    snapshot, revision, goals, candidates = _case(ir)
    candidate = candidates[0]
    binding = FDASCommitBinding.create(
        revision, snapshot, candidate, goals)
    validator = FDASCommitValidator()

    blocked = validator.validate(
        binding, revision, snapshot, candidate,
        authority_enabled=False)
    assert blocked.disposition == ValidationDisposition.REJECT
    assert blocked.reason == "fdas-candidate-has-causal-blockers"
    assert "fdas-source-supports" in blocked.checks
    assert not blocked.plan_materialization_authorized
    assert not blocked.execution_authority

    compiled_effect = replace(candidate, blockers=())
    compiled_binding = FDASCommitBinding.create(
        revision, snapshot, compiled_effect, goals)
    disabled = validator.validate(
        compiled_binding, revision, snapshot, compiled_effect,
        authority_enabled=True)
    assert disabled.disposition == ValidationDisposition.REJECT
    assert disabled.reason == "fdas-domain-authority-disabled"
    assert disabled.checks[-1] == "domain-authority-gate"
    assert compiled_effect.authority_eligible is False


def test_commit_binding_rejects_changed_revision_and_candidate(ir):
    snapshot, revision, goals, candidates = _case(ir)
    candidate = candidates[0]
    binding = FDASCommitBinding.create(
        revision, snapshot, candidate, goals)
    validator = FDASCommitValidator()

    changed_revision = replace(
        revision,
        revision_id="fdas-revision-changed",
        build_hash="changed-build-hash")
    stale = validator.validate(
        binding, changed_revision, snapshot, candidate)
    assert stale.disposition == ValidationDisposition.REGENERATE
    assert stale.reason == "fdas-revision-changed"

    changed_candidate = replace(
        candidate, candidate_hash="changed-candidate-hash")
    changed = validator.validate(
        binding, revision, snapshot, changed_candidate)
    assert changed.disposition == ValidationDisposition.REGENERATE
    assert changed.reason == "fdas-candidate-changed"
