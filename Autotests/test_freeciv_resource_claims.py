"""Identity, time-window, and legacy packet resource contracts."""

import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    ClaimHardness,
    GameResourceKind,
    PacketBudget,
    PacketCost,
    ResourceKind,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
    capacities_from_packet_budgets,
    claims_from_packet_costs,
)
from freeciv_agent.events.schema import PAYLOADS_PATH  # noqa: E402


def test_published_event_schema_covers_every_game_resource_kind():
    with open(PAYLOADS_PATH, encoding="utf-8") as stream:
        schema = json.load(stream)
    published = set(
        schema["$defs"]["resourceRef"][
            "properties"]["kind"]["enum"])

    assert published == {
        kind.value for kind in GameResourceKind}


def test_half_open_turn_windows_overlap_and_cover_exactly():
    current = TurnWindow(4, 5)
    next_turn = TurnWindow(5, 6)
    interval = TurnWindow(4, 7)

    assert not current.overlaps(next_turn)
    assert interval.overlaps(current)
    assert interval.covers(current)
    assert interval.duration == 3

    with pytest.raises(
            ValueError,
            match="at least one turn"):
        TurnWindow(4, 4)


def test_resource_identity_and_claim_digest_are_candidate_independent():
    resource = ResourceRef(
        GameResourceKind.ACTOR,
        "unit:143", "whole_actor",
        "player:2")
    claim = ResourceClaim(
        resource=resource,
        quantity=1,
        window=TurnWindow(40, 41),
        hardness=(
            ClaimHardness.HARD_CURRENT),
        exclusive=True,
        source_operation_id="defend:7",
        source_step_id="move:1")

    assert len(resource.resource_id) == 64
    assert len(claim.claim_id) == 64
    assert claim.to_dict()[
        "resource"]["owner_id"] == (
            "unit:143")
    assert claim.to_dict()[
        "window"] == {
            "end_turn_exclusive": 41,
            "start_turn": 40,
        }


def test_legacy_packets_adapt_without_mutating_v1_identity():
    costs = (
        PacketCost(
            ResourceKind.ACTION, 1),
        PacketCost(
            ResourceKind.EXACT_RULE, 2),
    )
    budgets = (
        PacketBudget(
            ResourceKind.ACTION, 1),
        PacketBudget(
            ResourceKind.EXACT_RULE, 4),
    )

    claims = claims_from_packet_costs(
        "operation", "step", costs, 9)
    capacities = capacities_from_packet_budgets(
        budgets, 9, "snapshot")

    assert [
        row.resource.owner_id
        for row in claims
    ] == [
        "legacy-packet:action",
        "legacy-packet:exact_rule",
    ]
    assert [
        row.quantity
        for row in claims
    ] == [1, 2]
    assert [
        row.quantity
        for row in capacities
    ] == [1, 4]
    assert costs[0] == PacketCost(
        ResourceKind.ACTION, 1)


def test_resource_contracts_reject_ambiguous_values():
    with pytest.raises(TypeError):
        ResourceRef(
            "actor", "unit:1",
            None, "player:1")
    with pytest.raises(
            ValueError,
            match="positive"):
        ResourceClaim(
            ResourceRef(
                GameResourceKind.ACTOR,
                "unit:1", None,
                "player:1"),
            0, TurnWindow(1, 2),
            ClaimHardness.HARD_CURRENT,
            False, "operation", "step")
    with pytest.raises(
            ValueError,
            match="operation and step"):
        claims_from_packet_costs(
            "", "step", (), 1)
