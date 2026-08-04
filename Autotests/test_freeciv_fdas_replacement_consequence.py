import copy

import pytest

from freeciv.harness.fdas_replacement_consequence import (
    replacement_chain_consequence,
)
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import FdasReplacementChainOutcomeLabel


def _label():
    material = {
        "action_selection_changed": False,
        "completion_snapshot_id": "snapshot-10",
        "completion_turn": 10,
        "due_turn": 42,
        "game_id": "game",
        "label_id": "pending",
        "observed_revision_id": "revision-44",
        "observed_turn": 44,
        "observed_value": {
            "reinforcement_actor_id": 7,
            "reinforcement_at_target": False,
            "reinforcement_nontransported": False,
            "reinforcement_present": False,
            "replacement_actor_id": 8,
            "replacement_at_source": False,
            "replacement_nontransported": False,
            "replacement_present": False,
            "source_city_id": 3,
            "source_city_owned_and_present": True,
            "target_city_id": 4,
            "target_city_owned_and_present": True,
        },
        "operation_id": "operation-proof",
        "operation_spec_digest": "spec-proof",
        "outcome": False,
        "player_id": 0,
        "policy_authority": False,
        "provenance_ids": ("proof",),
        "readout_authority": False,
        "reason": "completed-replacement-chain-not-durable:actors",
        "reinforcement_actor_id": 7,
        "replacement_actor_id": 8,
        "schema_version": 1,
        "source_city_id": 3,
        "status": "observed",
        "target_city_id": 4,
        "target_id": (
            "durable-completed-coordinated-replacement/32-turn/1.0"),
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    identity = dict(
        (name, material[name]) for name in (
            "completion_snapshot_id", "completion_turn", "due_turn",
            "game_id", "operation_id", "operation_spec_digest",
            "player_id", "reinforcement_actor_id", "replacement_actor_id",
            "schema_version", "source_city_id", "target_city_id",
            "target_id"))
    material["label_id"] = "replacement-outcome-label-" + structural_hash(
        identity)[:24]
    return FdasReplacementChainOutcomeLabel.from_dict(material).to_dict()


def _assignment():
    return {
        "operation_id": "operation-proof",
        "operation_spec_digest": "spec-proof",
        "reinforcement_actor_id": 7,
        "replacement_actor_id": 8,
        "source_city_id": 3,
        "target_city_id": 4,
    }


def _removal(actor_id, turn, cause="combat_defender_lost"):
    payload = {
        "cause": cause,
        "detail": "Exact removal evidence.",
        "evidence_event_ids": ["combat-{}".format(actor_id)],
        "evidence_quality": "exact",
        "last_position": {"x": actor_id, "y": 1},
        "lifecycle_id": "lifecycle-{}".format(actor_id),
        "transition": "disappeared",
        "unit_id": actor_id,
        "unit_type": "Defender",
    }
    return {
        "caused_by": ["snapshot-{}".format(turn)],
        "event_id": "removal-{}".format(actor_id),
        "payload": payload,
        "turn": turn,
        "type": "unit_lifecycle",
    }


def test_replacement_consequence_preserves_negative_and_decomposes_losses():
    consequence = replacement_chain_consequence(
        _assignment(), _label(), (_removal(7, 20), _removal(8, 30)))

    assert consequence["durability_outcome"] is False
    assert consequence["cities"] == {
        "source_city_retained": True,
        "target_city_retained": True,
    }
    assert consequence["summary"] == {
        "assigned_actor_survival_count": 0,
        "city_retention_count": 2,
        "exact_combat_attributed_loss_count": 2,
    }
    assert consequence["result_hash"] == structural_hash(dict(
        (key, value) for key, value in consequence.items()
        if key != "result_hash"))


def test_replacement_consequence_fails_closed_without_actor_removal():
    with pytest.raises(ValueError, match="lacks one disappearance"):
        replacement_chain_consequence(
            _assignment(), _label(), (_removal(7, 20),))


def test_replacement_consequence_rejects_identity_drift():
    assignment = copy.deepcopy(_assignment())
    assignment["target_city_id"] = 99

    with pytest.raises(ValueError, match="identity differs"):
        replacement_chain_consequence(
            assignment, _label(), (_removal(7, 20), _removal(8, 30)))
