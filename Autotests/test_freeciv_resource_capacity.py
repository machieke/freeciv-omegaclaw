"""Authoritative current-turn game resource capacity extraction."""

import copy
import json
import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    GameResourceKind,
    ResourceCapacityExtractor,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _payload():
    with open(os.path.join(
            REPO, "benchmarks", "freeciv",
            "samples", "real_state_turn1.json"),
            encoding="utf-8") as stream:
        return json.load(stream)


def _transport_rule(name, capacity):
    return SimpleNamespace(
        target_kind="unit",
        display_name=name,
        rule_name=name,
        quantitative={
            "transport_capacity": {
                "value": capacity,
            },
        })


def _by_kind(result, kind):
    return tuple(
        row for row in result.capacities
        if row.resource.kind == kind)


def test_capacity_extractor_preserves_identity_and_current_window():
    snapshot = ProxyStateDTO.parse(
        "capacity-test", 1,
        _payload()).to_snapshot()
    result = ResourceCapacityExtractor().extract(
        snapshot,
        action_budget=3,
        cpu_budget=7)

    actors = _by_kind(
        result, GameResourceKind.ACTOR)
    moves = _by_kind(
        result,
        GameResourceKind.MOVE_POINTS)
    city_slots = _by_kind(
        result,
        GameResourceKind.CITY_PRODUCTION_SLOT)
    treasury = _by_kind(
        result,
        GameResourceKind.TREASURY)

    assert len(actors) == len(
        snapshot.units)
    assert len(moves) == len(
        snapshot.units)
    assert len(city_slots) == len(
        snapshot.cities)
    assert treasury[0].quantity == (
        snapshot.economy.gold)
    assert all(
        row.window.start_turn
        == snapshot.turn
        and row.window
        .end_turn_exclusive
        == snapshot.turn + 1
        for row in result.capacities)
    assert (
        "tile-occupancy-rules-unavailable"
        in result.omissions)
    assert result == (
        ResourceCapacityExtractor().extract(
            snapshot,
            action_budget=3,
            cpu_budget=7))


def test_transport_seats_require_ruleset_capacity_and_visible_load():
    payload = copy.deepcopy(
        _payload())
    payload["units"]["102"][
        "carrying"] = 1
    payload["units"]["102"][
        "type"] = "Ferry"
    snapshot = ProxyStateDTO.parse(
        "transport-capacity", 1,
        payload).to_snapshot()
    ruleset = SimpleNamespace(
        rules=(
            _transport_rule(
                "Ferry", 3),))

    result = ResourceCapacityExtractor().extract(
        snapshot, ruleset_ir=ruleset)
    seats = _by_kind(
        result,
        GameResourceKind.TRANSPORT_SEAT)

    assert len(seats) == 1
    assert seats[0].resource.owner_id == (
        "unit:102")
    assert seats[0].quantity == 2
    assert seats[0].authority == (
        "derived-ruleset-and-unit-state")


def test_missing_research_or_treasury_is_an_omission_not_capacity():
    payload = copy.deepcopy(
        _payload())
    payload["economic"].pop(
        "gold", None)
    payload["economic"].pop(
        "research", None)
    snapshot = ProxyStateDTO.parse(
        "missing-capacity", 1,
        payload).to_snapshot()

    result = ResourceCapacityExtractor().extract(
        snapshot)

    assert not _by_kind(
        result,
        GameResourceKind.TREASURY)
    assert not _by_kind(
        result,
        GameResourceKind.RESEARCH_SLOT)
    assert "treasury-stockpile-unavailable" in (
        result.omissions)
    assert "research-slot-unavailable" in (
        result.omissions)
