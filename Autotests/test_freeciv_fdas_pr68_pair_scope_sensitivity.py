import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_pr68_pair_scope_sensitivity import (  # noqa: E402
    _reconstruct_pair,
    _unit_resources,
)


def _action(actor, x):
    return (
        '{{"action_type":"unit_move","actor_id":{},'
        '"target":{{"x":{},"y":2}}}}'.format(actor, x))


def _case(baseline_actor=7, alternative_actor=7,
          baseline_source="atom-city-3", alternative_source="atom-city-3"):
    baseline_action = _action(baseline_actor, 1)
    alternative_action = _action(alternative_actor, 2)
    union = {
        "event_id": "union-event",
        "payload": {"details": {"readouts": [
            {
                "action_key": baseline_action,
                "operation_id": "baseline",
                "operation_type": "reinforcement-move",
            },
            {
                "action_key": alternative_action,
                "operation_id": "alternative",
                "operation_type": "reinforcement-move",
            },
        ]}},
    }
    candidate_filter = {
        "event_id": "filter-event",
        "payload": {"details": {"readouts": [
            {
                "operation_id": "baseline",
                "source_atom_id": baseline_source,
            },
            {
                "operation_id": "alternative",
                "source_atom_id": alternative_source,
            },
        ]}},
    }
    readout = {
        "baseline_operation_id": "baseline",
        "result_hash": "readout-hash",
    }
    return readout, union, candidate_filter


def test_pair_scope_sensitivity_reconstructs_same_actor_substitution():
    row = _reconstruct_pair(
        "game-test", 17, *_case(), "alternative")

    assert row["predicates"] == {
        "bounded_target_support_matches": True,
        "duplicate_action": False,
        "identical_inferred_resource_set": True,
        "operation_type_matches": True,
        "shared_inferred_resources": ["unit-action:7"],
    }
    assert row["row_hash"]


def test_pair_scope_sensitivity_distinguishes_actor_and_target_support():
    row = _reconstruct_pair(
        "game-test", 17,
        *_case(alternative_actor=8, alternative_source="atom-city-4"),
        "alternative")

    assert row["predicates"]["bounded_target_support_matches"] is False
    assert row["predicates"]["identical_inferred_resource_set"] is False
    assert row["predicates"]["shared_inferred_resources"] == []


def test_pair_scope_sensitivity_resource_inference_is_fail_closed():
    assert _unit_resources({"action_type": "unit_move"}) is None
    assert _unit_resources({
        "action_type": "unit_move", "actor_id": True}) is None
    assert _unit_resources({
        "action_type": "unit_move", "actor_id": 11}) == (
            "unit-action:11",)
