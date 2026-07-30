"""Grounded server-solved city-worker macro and result tests."""

import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    CityWorkerMacroAssembler,
    CityWorkerMacroIntent,
    ImpactCandidate,
)
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateAuthority,
    EstimateValidity,
    GroundedCityWorkerTransitionModel,
)
from freeciv_agent.pressure import (  # noqa: E402
    BoundedExactScheduler,
    ClaimHardness,
    GameResourceKind,
    ResourceCapacityExtractor,
)


def _city(
        city_id=10, food=-1,
        governor_enabled=False,
        minimum=(0, 0, 0, 0, 0, 0),
        require_happy=False,
        was_happy=False,
        disorder=False,
        complete_output=True):
    return SimpleNamespace(
        city_id=city_id,
        owner=0,
        name="City {}".format(city_id),
        governor_available=True,
        governor_enabled=governor_enabled,
        governor_minimal_surplus=tuple(minimum),
        governor_require_happy=require_happy,
        was_happy=was_happy,
        disorder=disorder,
        surplus=(
            (food, 4, 3, 2, 0, 3)
            if complete_output else (food,)),
        production=(
            (food + 4, 7, 5, 4, 0, 5)
            if complete_output else (food + 4,)),
        usage=(
            (4, 3, 2, 2, 0, 2)
            if complete_output else (4,)))


def _snapshot(
        intents, cities=None,
        turn=5, suffix="a"):
    cities = tuple(
        cities or tuple(
            _city(intent.city_id)
            for intent in intents))
    actions = tuple(sorted(
        canonical_json_bytes(
            intent.action()).decode("utf-8")
        for intent in intents))
    return SimpleNamespace(
        player_id=0,
        turn=turn,
        snapshot_id="snapshot:{}:{}".format(
            turn, suffix),
        legal_actions_digest="legal:{}:{}".format(
            turn, suffix),
        legal_action_json=actions,
        cities=cities,
        units=(),
        research=SimpleNamespace(available=False),
        economy=SimpleNamespace(gold=50),
        city=lambda city_id: next((
            city for city in cities
            if city.city_id == city_id
        ), None))


def _estimate(snapshot, intent):
    action = intent.action()
    return GroundedCityWorkerTransitionModel().estimate(
        DomainEstimateRequest(
            request_id="w" * 64,
            snapshot=snapshot,
            ruleset_ir=SimpleNamespace(rules=()),
            legal_action=action,
            candidate=ImpactCandidate(
                action=action,
                category=(
                    "city_happiness_governor"
                    if intent.require_happy
                    else "city_food_governor"),
                utility=100.0,
                rationale="city-worker macro test"),
            goal_losses=((
                "pf-impact:survival", 4.0),),
            operation_context=None,
            validity=EstimateValidity(
                snapshot.snapshot_id,
                snapshot.legal_actions_digest,
                "ruleset", snapshot.turn,
                snapshot.turn),
            horizon_turn=snapshot.turn + 1))


def _assembly(snapshot, intent):
    return CityWorkerMacroAssembler.assemble(
        snapshot, intent,
        _estimate(snapshot, intent),
        ("pf-impact:survival",),
        "ruleset")


def test_grounded_macro_never_invents_assignment_or_output_prediction():
    intent = CityWorkerMacroIntent(
        city_id=10,
        food_surplus_minimum=1,
        require_happy=False,
        scheduling_bid=4.0)
    snapshot = _snapshot((intent,))

    estimate = _estimate(snapshot, intent)
    artifact = estimate.to_dict()["model_artifact"]

    assert estimate.authority == (
        EstimateAuthority.DETERMINISTIC_DERIVED)
    assert estimate.transition.residual_probability == 0.0
    assert artifact["assignment"][
        "macro_action_atomic"] is True
    assert artifact["assignment"][
        "citizen_actions_emitted"] is False
    assert artifact["predicted_output_vector"][
        "point_estimate"] is None
    assert artifact["solver"]["status"] == (
        "advertised-macro-not-yet-executed")
    assert artifact["solver"]["optimality_gap"] is None
    assert artifact["current_output_vector"]["net"]["food"] == -1
    assert estimate.transition.outcomes[
        0].next_goal_features == (
            ("pf-impact:survival", 4.0),)


def test_macro_assembly_claims_one_city_assignment_and_action_budget():
    intent = CityWorkerMacroIntent(
        city_id=10,
        food_surplus_minimum=1,
        require_happy=False,
        scheduling_bid=4.0)
    snapshot = _snapshot((intent,))
    assembly = _assembly(snapshot, intent)

    assert assembly is not None
    assert len(assembly.spec.steps) == 1
    assert assembly.spec.steps[0].action_type == "city_governor"
    assert {
        row.resource.kind
        for row in assembly.resource_request.claims
        if row.hardness == ClaimHardness.HARD_CURRENT
    } == {
        GameResourceKind.CITY_WORKER_ASSIGNMENT,
        GameResourceKind.ACTION_BUDGET,
    }
    assert assembly.model_artifact[
        "pressure_decision"][
            "city_budget_target"] == "city:10"


def test_pressure_budget_selects_one_city_macro_without_citizen_decomposition():
    low = CityWorkerMacroIntent(
        city_id=10,
        food_surplus_minimum=1,
        require_happy=False,
        scheduling_bid=2.0)
    high = CityWorkerMacroIntent(
        city_id=11,
        food_surplus_minimum=1,
        require_happy=False,
        scheduling_bid=5.0)
    snapshot = _snapshot(
        (low, high),
        cities=(_city(10), _city(11)))
    assemblies = (
        _assembly(snapshot, low),
        _assembly(snapshot, high),
    )
    capacity = ResourceCapacityExtractor().extract(
        snapshot, action_budget=1)
    schedule = BoundedExactScheduler().schedule(
        tuple(row.resource_request for row in assemblies),
        capacity.capacities,
        requirement_sets=tuple(
            row.requirement_set for row in assemblies),
        premise_packets=dict(
            pair
            for row in assemblies
            for pair in row.premise_packets))

    assert schedule.selected_operation_ids == (
        assemblies[1].spec.operation_id,)
    assert all(
        len(row.spec.steps) == 1
        for row in assemblies)
    assert all(
        row.model_artifact["assignment"][
            "citizen_actions_emitted"] is False
        for row in assemblies)


def test_observed_result_reports_outputs_constraints_and_unknown_gap():
    intent = CityWorkerMacroIntent(
        city_id=10,
        food_surplus_minimum=1,
        require_happy=False,
        scheduling_bid=4.0)
    before = _snapshot((intent,))
    assembly = _assembly(before, intent)
    after = _snapshot(
        (intent,),
        cities=(_city(
            10, food=2,
            governor_enabled=True,
            minimum=(1, 0, 0, 0, 0, 0)),),
        turn=6, suffix="result")

    result = CityWorkerMacroAssembler.observe_result(
        assembly, before, after,
        accepted=True)

    assert result.solver_status == (
        "observed-constraints-satisfied")
    assert result.configuration_observed
    assert result.constraints_met is True
    assert result.actual_output_vector["net"]["food"] == 2
    assert result.optimality_gap is None
    assert result.optimality_gap_status == (
        "not-exposed-by-server-interface")
    assert not result.citizen_assignments_visible


def test_happiness_result_and_infeasible_output_are_typed():
    intent = CityWorkerMacroIntent(
        city_id=10,
        food_surplus_minimum=0,
        require_happy=True,
        scheduling_bid=4.0)
    before = _snapshot((intent,))
    assembly = _assembly(before, intent)
    after = _snapshot(
        (intent,),
        cities=(_city(
            10, food=0,
            governor_enabled=True,
            minimum=(0, 0, 0, 0, 0, 0),
            require_happy=True,
            was_happy=False,
            disorder=True),),
        turn=6, suffix="infeasible")

    result = CityWorkerMacroAssembler.observe_result(
        assembly, before, after,
        accepted=True)

    assert result.solver_status == (
        "observed-constraints-unsatisfied")
    assert result.constraints_met is False

    incomplete = _snapshot(
        (intent,),
        cities=(_city(
            10, complete_output=False),))
    abstention = _estimate(
        incomplete, intent)
    assert abstention.authority == EstimateAuthority.ABSTAIN
    assert abstention.abstention_reason == (
        "city-worker-input-missing")
