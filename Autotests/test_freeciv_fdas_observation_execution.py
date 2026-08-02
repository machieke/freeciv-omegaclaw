from types import SimpleNamespace

import pytest

from freeciv.harness.engine_live import _fdas_visibility_observation_decision
from freeciv_agent.beliefs import ModelProvenance
from freeciv_agent.events.schema import canonical_json_bytes, structural_hash
from freeciv_agent.planning import FdasObservationExecutionBridge
from freeciv_agent.pressure import (
    AtomState,
    BoundedDecision,
    CostVector,
    Hypothesis,
    ObservationOutcome,
    ObservationTest,
    PacketBudget,
    ResourceKind,
    TruthState,
    ValueOfInformationPlanner,
)


ACTION = {
    "action_type": "unit_move",
    "actor_id": 7,
    "target": {"x": 1, "y": 1},
}
ACTION_KEY = canonical_json_bytes(ACTION).decode("utf-8")


class Snapshot(object):
    def __init__(
            self, snapshot_id, source_seq, visible, actor_tile,
            legal=True, turn=4):
        self.snapshot_id = snapshot_id
        self.identity = SimpleNamespace(
            game_id="observation-execution-test", source_seq=source_seq)
        self.player_id = 0
        self.turn = turn
        self.map_width = 10
        self.map_height = 10
        self.visible_tile_ids = tuple(visible)
        self.legal_action_json = (ACTION_KEY,) if legal else ()
        self.legal_actions_digest = "legal-a" if legal else "legal-b"
        self._actor = (
            None if actor_tile is None
            else SimpleNamespace(unit_id=7, tile=actor_tile))

    def unit(self, unit_id):
        return self._actor if int(unit_id) == 7 else None


def _decision():
    provenance = ModelProvenance(
        "simulator",
        "visibility-frontier-model",
        "1.0",
        structural_hash({"model": "visibility-frontier-model/1.0"}),
        False,
        0.6,
        ("civ2civ3", "one-legal-move"))
    hypotheses = (
        Hypothesis("frontier-expands", 0.6),
        Hypothesis("frontier-stalls", 0.4),
    )
    test = ObservationTest(
        "visibility-frontier",
        "belief-visibility-frontier",
        (
            ObservationOutcome(
                "visibility-expanded",
                (("frontier-expands", 0.9), ("frontier-stalls", 0.1))),
            ObservationOutcome(
                "no-visibility-expansion",
                (("frontier-expands", 0.1), ("frontier-stalls", 0.9))),
        ),
        CostVector(compute=0.01),
        provenance,
        execution_kind="observation")
    decision = BoundedDecision(
        "continue-frontier-scouting",
        "frontier-expands",
        0.7,
        "replan-scout-route",
        "continue-scout-route")
    atom = AtomState(
        "belief-visibility-frontier",
        TruthState(0.6, 0.5, ("visible-frontier",), crisp=False))
    return ValueOfInformationPlanner(engine_live=True).packet_decision_for_uncertainty(
        atom,
        decision,
        hypotheses,
        (test,),
        (
            PacketBudget(ResourceKind.CPU, 1),
            PacketBudget(ResourceKind.OBSERVATION, 1),
        ))


def _manifest():
    return {
        "beliefs": {"simulation_confidence_cap": 0.6},
        "ruleset": "civ2civ3",
    }


def test_engine_visibility_planner_selects_only_with_unseen_tiles():
    partial = Snapshot("snapshot-partial", 10, (1, 2), 0)
    complete = Snapshot("snapshot-complete", 10, tuple(range(100)), 0)

    decision = _fdas_visibility_observation_decision(
        partial, ACTION, _manifest())

    assert len(decision["selected_operation_ids"]) == 1
    assert decision["packet_schedule"].conserved
    assert {
        row.outcome_id
        for row in decision["information_values"][0].test.outcomes
    } == {"visibility-expanded", "no-visibility-expansion"}
    assert _fdas_visibility_observation_decision(
        complete, ACTION, _manifest()) is None


def test_exact_legacy_scout_binding_registers_only_fresh_authoritative_return():
    before = Snapshot("snapshot-before", 10, (1, 2), 0)
    after = Snapshot("snapshot-after", 11, (1, 2, 3, 4), 11, turn=5)
    bridge = FdasObservationExecutionBridge()

    binding = bridge.bind(_decision(), before, ACTION)
    validation = bridge.revalidate(binding, before, ACTION)

    assert validation.committed
    assert bridge.evidence_ledger.tokens == ()

    result = bridge.authoritative_return(
        binding, validation, before, after,
        {"event_id": "action-result-7", "status": "accepted"})
    replay = bridge.authoritative_return(
        binding, validation, before, after,
        {"event_id": "action-result-7", "status": "accepted"})

    assert result.outcome_id == "visibility-expanded"
    assert result.new_visible_tile_ids == (3, 4)
    assert result.evidence_token.source == (
        "authoritative-player-visibility-delta")
    assert result.evidence_token.observation_policy.goal_id == binding.goal_id
    assert bridge.evidence_ledger.tokens == (result.evidence_token,)
    assert replay == result
    assert result.to_dict()["policy_authority"] is False


def test_commit_revalidation_rejects_changed_snapshot_or_action():
    before = Snapshot("snapshot-before", 10, (1, 2), 0)
    bridge = FdasObservationExecutionBridge()
    binding = bridge.bind(_decision(), before, ACTION)

    changed = Snapshot("snapshot-changed", 11, (1, 2), 0)
    validation = bridge.revalidate(binding, changed, ACTION)
    changed_action = dict(ACTION, target={"x": 2, "y": 1})
    action_validation = bridge.revalidate(binding, before, changed_action)

    assert validation.status == "rejected"
    assert validation.reason == "observation-snapshot-changed"
    assert action_validation.status == "rejected"
    assert action_validation.reason == (
        "legacy-selected-observation-action-changed")
    assert bridge.evidence_ledger.tokens == ()


def test_return_rejects_stale_snapshot_or_unproven_move_without_evidence():
    before = Snapshot("snapshot-before", 10, (1, 2), 0)
    bridge = FdasObservationExecutionBridge()
    binding = bridge.bind(_decision(), before, ACTION)
    validation = bridge.revalidate(binding, before, ACTION)

    stale = Snapshot("snapshot-stale", 10, (1, 2, 3), 11, turn=5)
    unmoved = Snapshot("snapshot-unmoved", 11, (1, 2, 3), 0, turn=5)

    with pytest.raises(ValueError, match="not a fresh snapshot"):
        bridge.authoritative_return(
            binding, validation, before, stale,
            {"event_id": "action-result-7", "status": "accepted"})
    with pytest.raises(ValueError, match="does not prove scout move"):
        bridge.authoritative_return(
            binding, validation, before, unmoved,
            {"event_id": "action-result-7", "status": "accepted"})
    proven = Snapshot("snapshot-proven", 11, (1, 2, 3), 11, turn=5)
    with pytest.raises(ValueError, match="accepted action result"):
        bridge.authoritative_return(
            binding, validation, before, proven,
            {"event_id": "action-result-7", "status": "rejected"})
    assert bridge.evidence_ledger.tokens == ()


def test_authoritative_no_expansion_is_not_enemy_absence_evidence():
    before = Snapshot("snapshot-before", 10, (1, 2), 0)
    after = Snapshot("snapshot-after", 11, (1, 2), 11, turn=5)
    bridge = FdasObservationExecutionBridge()
    binding = bridge.bind(_decision(), before, ACTION)
    validation = bridge.revalidate(binding, before, ACTION)

    result = bridge.authoritative_return(
        binding, validation, before, after,
        {"event_id": "action-result-7", "status": "accepted"})

    assert result.outcome_id == "no-visibility-expansion"
    assert result.new_visible_tile_ids == ()
    assert result.evidence_token.strength == 0.0
    assert "enemy" not in result.evidence_token.source
