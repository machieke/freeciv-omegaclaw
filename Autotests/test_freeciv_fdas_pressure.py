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
    CandidateOperationFactory,
    GoalFactory,
)
from freeciv_agent.pressure import (  # noqa: E402
    DependentAtomPressureAdapter,
    MaterializationBudget,
)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    CityEconomyProjector,
    DependentAtomSpaceStore,
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


def test_stale_goal_revision_is_rejected(ir):
    _snapshot_value, revision, goals, candidates = _case(ir)
    stale = replace(goals[0], snapshot_id="stale-snapshot")

    with pytest.raises(ValueError, match="stale snapshot"):
        DependentAtomPressureAdapter().build_context(
            revision, (stale,), candidates)
