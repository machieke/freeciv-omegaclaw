"""Corrected snapshot-local GDO-7A pilot audit contracts."""

import hashlib
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
SRC = os.path.join(REPO, "src")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from run_gdo_production_persistence_snapshot_pilot_audit import (  # noqa: E402
    analyze_snapshot_contract,
)


PROTECTED = {
    "action_type": "city_production",
    "city_id": 103,
    "production_kind": 6,
    "production_value": 10,
}
COMPETING = {
    "action_type": "city_production",
    "city_id": 103,
    "production_kind": 3,
    "production_value": 14,
}


def _guard(turn=8):
    return {
        "type": "operation_step_selected",
        "turn": turn,
        "payload": {
            "deadline_turn": 20,
            "excluded_action_ids": [hashlib.sha256(
                canonical_json_bytes(COMPETING)).hexdigest()],
            "mechanism": "gdo7a-production-enabling",
            "next_action": PROTECTED,
            "operation_id": "production-operation",
            "persistence_maximum_remaining_turns": 12,
            "persistence_threat_radius": 3,
            "production_persistence_safety": {
                "build_cost": 50,
                "future_gold_upkeep": 1,
                "shield_stock": 30,
            },
            "protected_city_id": 103,
            "reason_code": "bounded-production-persistence-authority",
            "snapshot_id": "snapshot-8",
        },
    }


def _state(turn=9, enemies=(), operating=2):
    return {
        "type": "state_snapshot",
        "turn": turn,
        "payload": {
            "grounded_context": {
                "map_topology": {
                    "wrap_x": False,
                    "wrap_y": False,
                },
                "visible_enemy_units": list(enemies),
            },
            "map": {"height": 20, "width": 20},
            "own_state": {
                "cities": [{
                    "city_id": 103,
                    "disorder": False,
                    "had_famine": False,
                    "production_kind": 6,
                    "production_value": 10,
                    "shield_stock": 34,
                    "surplus": [2, 3],
                    "x": 4,
                    "y": 5,
                }],
                "economy": {
                    "available": True,
                    "gold": 20,
                    "operating_gold_per_turn": operating,
                },
            },
        },
    }


def _sent(turn=9):
    return {
        "type": "action_sent",
        "turn": turn,
        "payload": {
            "action": COMPETING,
            "action_id": "switch-action",
        },
    }


def _accepted(turn=9):
    return {
        "type": "action_result",
        "turn": turn,
        "payload": {
            "action_id": "switch-action",
            "status": "accepted",
        },
    }


def _diverged(turn=9):
    return {
        "type": "operation_blocked",
        "turn": turn,
        "payload": {
            "mechanism": "gdo7a-production-enabling",
            "operation_id": "production-operation",
            "reason_code": (
                "production-target-diverged-before-product-observation"),
        },
    }


def test_snapshot_contract_rejects_accepted_excluded_action_before_refresh():
    result = analyze_snapshot_contract((
        _guard(), _sent(turn=8), _accepted(turn=8), _state()))

    assert len(result["protected_snapshot_switches"]) == 1
    assert result["unattributed_relinquishments"] == []


def test_snapshot_contract_attributes_later_visible_threat_relinquishment():
    result = analyze_snapshot_contract((
        _guard(),
        _state(enemies=({"x": 6, "y": 5},)),
        _sent(), _accepted(), _diverged()))

    assert result["protected_snapshot_switches"] == []
    assert result["relinquishment_reason_counts"] == {
        "visible_threat": 1}
    assert result["unattributed_relinquishments"] == []


def test_snapshot_contract_attributes_later_upkeep_relinquishment():
    result = analyze_snapshot_contract((
        _guard(), _state(operating=-1),
        _sent(), _accepted(), _diverged()))

    assert result["protected_snapshot_switches"] == []
    assert result["relinquishment_reason_counts"] == {
        "upkeep_unaffordable": 1}
    assert result["unattributed_relinquishments"] == []


def test_snapshot_contract_rejects_unattributed_later_switch():
    result = analyze_snapshot_contract((
        _guard(), _state(), _sent(), _accepted(), _diverged()))

    assert result["protected_snapshot_switches"] == []
    assert len(result["unattributed_relinquishments"]) == 1
    assert result["unattributed_relinquishments"][0]["diagnostics"] == []
