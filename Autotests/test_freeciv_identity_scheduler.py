"""Deterministic identity-aware greedy and exact resource scheduling."""

import itertools
import os
import random
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    BoundedExactScheduler,
    ClaimHardness,
    GameResourceKind,
    GreedyIdentityScheduler,
    OperationResourceRequest,
    RequirementSet,
    ResourceCapacity,
    ResourceClaim,
    ResourceRef,
    ResourceScheduleStatus,
    TurnWindow,
)


def _resource(
        owner, kind=GameResourceKind.ACTOR,
        subresource="whole", scope="player:1"):
    return ResourceRef(
        kind, owner, subresource, scope)


def _capacity(
        resource, quantity, start=4, end=5,
        snapshot="snapshot"):
    return ResourceCapacity(
        resource, quantity,
        TurnWindow(start, end),
        snapshot, "test-authority")


def _request(
        operation_id, bid, claims,
        requirement_set_id=None):
    return OperationResourceRequest(
        operation_id, bid,
        tuple(claims),
        requirement_set_id)


def _claim(
        operation_id, resource,
        quantity=1, start=4, end=5,
        exclusive=False,
        hardness=ClaimHardness.HARD_CURRENT):
    return ResourceClaim(
        resource=resource,
        quantity=quantity,
        window=TurnWindow(start, end),
        hardness=hardness,
        exclusive=exclusive,
        source_operation_id=operation_id,
        source_step_id="{}:step".format(
            operation_id))


def test_one_actor_cannot_serve_two_current_operations():
    actor = _resource("unit:143")
    requests = (
        _request(
            "defend-city-7", 8.0,
            (_claim(
                "defend-city-7",
                actor),)),
        _request(
            "defend-city-9", 5.0,
            (_claim(
                "defend-city-9",
                actor),)),
    )

    schedule = GreedyIdentityScheduler().schedule(
        requests,
        (_capacity(actor, 1),))

    assert schedule.selected_operation_ids == (
        "defend-city-7",)
    rejected = next(
        row for row in schedule.entries
        if not row.selected)
    assert rejected.reason == (
        "resource-capacity-exceeded")
    assert rejected.conflicting_operation_ids == (
        "defend-city-7",)


def test_two_transport_seats_select_two_of_three_passengers():
    seats = _resource(
        "unit:82",
        GameResourceKind.TRANSPORT_SEAT,
        "cargo")
    requests = tuple(
        _request(
            "passenger:{}".format(index),
            float(10 - index),
            (_claim(
                "passenger:{}".format(index),
                seats),))
        for index in range(3))

    schedule = GreedyIdentityScheduler().schedule(
        requests,
        (_capacity(seats, 2),))

    assert schedule.selected_operation_ids == (
        "passenger:0", "passenger:1")
    assert sum(
        row.quantity
        for row in schedule.selected_claims()
    ) == 2


def test_nonoverlapping_windows_do_not_conflict_and_overlap_does():
    tile = _resource(
        "tile:18:11",
        GameResourceKind.TILE_OCCUPANCY,
        "military-stack", "map")
    requests = (
        _request(
            "turn-4", 3.0,
            (_claim(
                "turn-4", tile,
                start=4, end=5),)),
        _request(
            "turn-5", 2.0,
            (_claim(
                "turn-5", tile,
                start=5, end=6),)),
    )
    capacities = (
        _capacity(
            tile, 1, 4, 5),
        _capacity(
            tile, 1, 5, 6),
    )

    schedule = GreedyIdentityScheduler().schedule(
        requests, capacities)

    assert schedule.selected_operation_ids == (
        "turn-4", "turn-5")


def test_exclusive_claim_blocks_other_use_even_with_quantity_capacity():
    tile = _resource(
        "tile:8:8",
        GameResourceKind.TILE_OCCUPANCY,
        "exclusive", "map")
    requests = (
        _request(
            "block", 9.0,
            (_claim(
                "block", tile,
                exclusive=True),)),
        _request(
            "move", 8.0,
            (_claim(
                "move", tile),)),
    )

    schedule = GreedyIdentityScheduler().schedule(
        requests,
        (_capacity(tile, 5),))

    assert schedule.selected_operation_ids == (
        "block",)
    assert next(
        row for row in schedule.entries
        if row.operation_id == "move"
    ).reason == "exclusive-resource-conflict"


def test_treasury_quantity_and_future_claim_semantics_are_separate():
    gold = _resource(
        "player:1",
        GameResourceKind.TREASURY,
        "gold")
    current = _request(
        "buy-now", 10.0,
        (_claim(
            "buy-now", gold,
            quantity=35),))
    too_much = _request(
        "buy-more", 5.0,
        (_claim(
            "buy-more", gold,
            quantity=20),))
    future = _request(
        "forecast", 1.0,
        (_claim(
            "forecast", gold,
            quantity=100, start=5, end=6,
            hardness=(
                ClaimHardness
                .CONDITIONAL_FUTURE)),))

    schedule = GreedyIdentityScheduler().schedule(
        (current, too_much, future),
        (_capacity(gold, 50),))

    assert schedule.selected_operation_ids == (
        "buy-now", "forecast")
    assert next(
        row for row in schedule.entries
        if row.operation_id == "buy-more"
    ).reason == "resource-capacity-exceeded"


def test_requirement_set_must_be_complete_before_selection():
    actor = _resource("unit:1")
    requirement = RequirementSet(
        "requirements", "rule",
        ("actor-present", "route-valid"),
        ("actor", "route"), "context")
    request = _request(
        "gated", 3.0,
        (_claim(
            "gated", actor),),
        requirement.requirement_set_id)

    incomplete = GreedyIdentityScheduler().schedule(
        (request,), (_capacity(actor, 1),),
        requirement_sets=(requirement,),
        premise_packets={
            "actor-present": 1,
        })
    complete = GreedyIdentityScheduler().schedule(
        (request,), (_capacity(actor, 1),),
        requirement_sets=(requirement,),
        premise_packets={
            "actor-present": 1,
            "route-valid": 1,
        })

    assert incomplete.selected_operation_ids == ()
    assert incomplete.entries[0].reason == (
        "incomplete-requirement-set")
    assert complete.selected_operation_ids == (
        "gated",)


def test_exact_scheduler_beats_constructed_greedy_knapsack():
    budget = _resource(
        "controller",
        GameResourceKind.CPU,
        "bounded")
    requests = (
        _request(
            "large", 5.0,
            (_claim(
                "large", budget,
                quantity=3),)),
        _request(
            "small-a", 3.0,
            (_claim(
                "small-a", budget,
                quantity=2),)),
        _request(
            "small-b", 3.0,
            (_claim(
                "small-b", budget,
                quantity=2),)),
    )
    capacities = (
        _capacity(budget, 4),)

    greedy = GreedyIdentityScheduler().schedule(
        requests, capacities)
    exact = BoundedExactScheduler().schedule(
        requests, capacities)

    assert greedy.selected_operation_ids == (
        "large",)
    assert greedy.objective_value == 5.0
    assert exact.selected_operation_ids == (
        "small-a", "small-b")
    assert exact.objective_value == 6.0
    assert exact.status == (
        ResourceScheduleStatus.EXACT)


def test_node_limit_fallback_and_input_permutations_are_deterministic():
    actor = _resource("unit:1")
    requests = tuple(
        _request(
            "operation:{}".format(index),
            float(index + 1),
            (_claim(
                "operation:{}".format(index),
                actor),))
        for index in range(8))
    capacities = (
        _capacity(actor, 1),)
    scheduler = BoundedExactScheduler(
        node_budget=1)

    first = scheduler.schedule(
        requests, capacities)
    second = scheduler.schedule(
        tuple(reversed(requests)),
        tuple(reversed(capacities)))

    assert first.status == (
        ResourceScheduleStatus
        .GREEDY_FALLBACK)
    assert first.fallback_reason == (
        "node-budget-exhausted")
    assert first.selected_operation_ids == (
        "operation:7",)
    assert first.decision_digest == (
        second.decision_digest)


def test_exact_scheduler_proves_shared_saturated_budget_without_branching():
    action = _resource(
        "legacy-packet:action",
        GameResourceKind.ACTION_BUDGET,
        "current")
    requests = tuple(
        _request(
            "operation:{}".format(index),
            float(20 - index),
            (_claim(
                "operation:{}".format(index),
                action),))
        for index in range(20))

    schedule = BoundedExactScheduler(
        node_budget=100).schedule(
            requests,
            (_capacity(action, 1),))

    assert schedule.status == (
        ResourceScheduleStatus.EXACT)
    assert schedule.explored_nodes == 1
    assert schedule.selected_operation_ids == (
        "operation:0",)
    assert all(
        row.reason
        == "resource-capacity-exceeded"
        for row in schedule.entries
        if not row.selected)


def test_exact_result_is_input_permutation_invariant():
    actor_a = _resource("unit:1")
    actor_b = _resource("unit:2")
    requests = (
        _request(
            "a", 2.0,
            (_claim("a", actor_a),)),
        _request(
            "b", 2.0,
            (_claim("b", actor_b),)),
    )
    capacities = (
        _capacity(actor_a, 1),
        _capacity(actor_b, 1),
    )
    scheduler = BoundedExactScheduler()

    first = scheduler.schedule(
        requests, capacities)
    second = scheduler.schedule(
        tuple(reversed(requests)),
        tuple(reversed(capacities)))

    assert first.selected_operation_ids == (
        "a", "b")
    assert first.decision_digest == (
        second.decision_digest)


def test_exact_scheduler_matches_exhaustive_small_knapsacks():
    rng = random.Random(20260730)
    budget = _resource(
        "controller",
        GameResourceKind.CPU,
        "exhaustive")
    scheduler = BoundedExactScheduler(
        node_budget=100000)
    for case_index in range(200):
        capacity = rng.randint(1, 8)
        rows = tuple(
            (
                "case:{}:operation:{}".format(
                    case_index, index),
                rng.randint(1, 12),
                rng.randint(1, 5),
            )
            for index in range(
                rng.randint(1, 8)))
        requests = tuple(
            _request(
                operation_id, bid,
                (_claim(
                    operation_id,
                    budget,
                    quantity=quantity),))
            for operation_id, bid, quantity
            in rows)
        expected_value = -1
        expected_ids = ()
        for mask in itertools.product(
                (False, True),
                repeat=len(rows)):
            quantity = sum(
                row[2]
                for row, selected
                in zip(rows, mask)
                if selected)
            if quantity > capacity:
                continue
            value = sum(
                row[1]
                for row, selected
                in zip(rows, mask)
                if selected)
            identities = tuple(sorted(
                row[0]
                for row, selected
                in zip(rows, mask)
                if selected))
            if (value > expected_value
                    or (value == expected_value
                        and identities
                        < expected_ids)):
                expected_value = value
                expected_ids = identities

        result = scheduler.schedule(
            requests,
            (_capacity(
                budget, capacity),))

        assert result.status == (
            ResourceScheduleStatus.EXACT)
        assert result.objective_value == (
            expected_value)
        assert result.selected_operation_ids == (
            expected_ids)
        assert sum(
            row.quantity
            for row in result.selected_claims()
        ) <= capacity
