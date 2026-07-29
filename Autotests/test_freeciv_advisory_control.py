"""Stage-S5 health-gated advisory ranking and disagreement gates."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pf_runtime import (  # noqa: E402
    build_controller_activation,
)
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    AdvisoryPolicy,
    ControlDecision,
    ControlEventEmitter,
    ImpactCandidate,
    ImpactControlAdapter,
)
from freeciv_agent.pressure import (  # noqa: E402
    PacketBudget,
    PacketCost,
    PacketReservation,
    PacketSchedule,
    ResourceKind,
)


class _Snapshot:
    snapshot_id = "advisory-snapshot"
    legal_actions_digest = "advisory-legal"
    turn = 10
    ruleset_name = "classic"

    def event_payload(self):
        return {
            "legal_actions_digest":
                self.legal_actions_digest,
            "snapshot_id": self.snapshot_id,
            "turn": self.turn,
        }


class _ScalarRanker:
    def rank(
            self, snapshot, candidates,
            expansion_city_target, horizon_turn,
            survival_threat_radius, **kwargs):
        del (
            snapshot, expansion_city_target,
            horizon_turn, survival_threat_radius,
            kwargs)
        return tuple(candidates), {
            "admissible_candidate_keys": [
                row.action_key for row in candidates],
            "scalar": "admissible",
        }


def _candidates():
    return (
        ImpactCandidate(
            {"action_type": "unit_move", "actor_id": 1},
            "exploration_move", 10.0, "baseline"),
        ImpactCandidate(
            {"action_type": "unit_move", "actor_id": 2},
            "exploration_move", 1.0, "advisory"),
    )


def _schedule(key, complete=True):
    cost = PacketCost(ResourceKind.ACTION, 1)
    reservation = PacketReservation(
        operation_id=key,
        costs=(cost,),
        reserved=((cost,) if complete else ()),
        state=("committed" if complete else "pending"))
    return PacketSchedule(
        budgets=(PacketBudget(
            ResourceKind.ACTION, 1),),
        reservations=(reservation,),
        committed_operation_ids=(
            (key,) if complete else ()),
        stranded_quanta=(
            () if complete else (cost,)),
        integrality_gap=(
            0.0 if complete else 1.0),
        relaxed_value=1.0,
        committed_value=(
            1.0 if complete else 0.0),
        scheduler_identity="advisory-fixture")


def _engine(
        calibrated=True, confidence=0.95,
        complete=True, safety_conflict=False):
    def run(query, snapshot):
        del snapshot
        keys = tuple(reversed(
            query.candidate_keys))
        return ControlDecision(
            ordered_candidate_keys=keys,
            selected_candidate_key=keys[0],
            packet_schedule=_schedule(
                keys[0], complete),
            controller_mode="unified_flow",
            artifact={
                "calibrated": calibrated,
                "confidence": confidence,
                "deadline": {"fit": 0.9},
                "evidence_overlap_valid": True,
                "expected_resource_use": {"action": 1},
                "predicted_cost": 1.0,
                "quarantined": False,
                "risk": {"tail": 0.1},
                "safety_conflict": safety_conflict,
                "typed_advantage": {
                    "exploration": 1.0},
            },
            health="healthy",
            fallback_chain=())
    return run


def _adapter(
        require_calibration=True,
        protect_uncalibrated_terminal_actions=True,
        **engine_options):
    return ImpactControlAdapter(
        scalar_v2_ranker=_ScalarRanker(),
        unified_flow_engine=_engine(
            **engine_options),
        advisory_policy=AdvisoryPolicy(
            minimum_confidence=0.8,
            require_calibration=require_calibration,
            protect_uncalibrated_terminal_actions=(
                protect_uncalibrated_terminal_actions),
            fallback_mode="scalar_v2"))


def _query(adapter, candidates=None):
    return adapter.build_query(
        _Snapshot(), (
            _candidates()
            if candidates is None else candidates),
        expansion_city_target=5,
        horizon_turn=40,
        survival_threat_radius=6,
        goal_facts={"exploration": {}},
        normalization_contract_hash="normalization-v1",
        ruleset_digest="ruleset-v1")


def test_healthy_packet_complete_revalidated_advisory_can_reorder():
    adapter = _adapter()
    query = _query(adapter)
    decision = adapter.rank_or_schedule(
        query, "unified_flow_advisory")

    assert decision.health == "healthy"
    assert decision.controller_mode == (
        "unified_flow_advisory")
    assert decision.selected_candidate_key == (
        query.candidate_keys[1])
    assert decision.artifact["advisory_accepted"]
    assert decision.artifact["validation"][
        "plan_materialization_authorized"]
    assert decision.packet_schedule.conserved


def test_advisory_disagreement_has_separate_review_record():
    adapter = _adapter()
    query = _query(adapter)
    decision = adapter.rank_or_schedule(
        query, "unified_flow_advisory")
    record = adapter.disagreement_records[0]

    assert decision.artifact["disagreement_id"] == (
        record.disagreement_id)
    assert record.baseline_candidate_key == (
        query.candidate_keys[0])
    assert record.advisory_candidate_key == (
        query.candidate_keys[1])
    assert record.packet_complete
    assert record.later_outcome_status == (
        "unknown-counterfactual")
    adapter.record_outcome(
        decision, _Snapshot(), _Snapshot(), {
            "effect_observed": True,
            "executed_candidate_key":
                decision.selected_candidate_key,
        })
    assert adapter.disagreement_records[
        0].later_outcome_status == (
            "observed-executed-effect")


def test_uncalibrated_or_low_confidence_advisory_falls_back():
    for options in (
            {"calibrated": False},
            {"confidence": 0.2},
            {"safety_conflict": True}):
        adapter = _adapter(**options)
        query = _query(adapter)
        decision = adapter.rank_or_schedule(
            query, "unified_flow_advisory")

        assert decision.health == "fallback"
        assert decision.controller_mode == "scalar_v2"
        assert decision.selected_candidate_key == (
            query.candidate_keys[0])
        assert not decision.artifact[
            "advisory_accepted"]
        assert decision.artifact["gate_reasons"]


def test_incomplete_packets_cannot_reorder_advisory_candidates():
    adapter = _adapter(complete=False)
    query = _query(adapter)
    decision = adapter.rank_or_schedule(
        query, "unified_flow_advisory")

    assert decision.health == "fallback"
    assert "packet-incomplete" in (
        decision.artifact["gate_reasons"])
    assert decision.selected_candidate_key == (
        query.candidate_keys[0])


def test_uncalibrated_advisory_cannot_displace_terminal_action():
    candidates = (
        ImpactCandidate(
            {
                "action_type": "unit_build_city",
                "actor_id": 1,
            },
            "expansion_move", 10.0,
            "complete settlement"),
        ImpactCandidate(
            {
                "action_type": "unit_move",
                "actor_id": 1,
            },
            "expansion_move", 1.0,
            "continue settlement route"),
    )
    adapter = _adapter(
        calibrated=False,
        require_calibration=False)
    query = _query(adapter, candidates)
    decision = adapter.rank_or_schedule(
        query, "unified_flow_advisory")

    assert decision.health == "fallback"
    assert decision.controller_mode == "scalar_v2"
    assert decision.selected_candidate_key == (
        query.candidate_keys[0])
    assert (
        "uncalibrated-terminal-action-disagreement"
        in decision.artifact["gate_reasons"])
    assert decision.artifact[
        "fallback_candidate_terminal"]
    assert not decision.artifact[
        "advisory_candidate_terminal"]
    assert decision.artifact[
        "fallback_candidate_key"] == (
            query.candidate_keys[0])
    assert decision.artifact[
        "advisory_candidate_key"] == (
            query.candidate_keys[1])
    assert decision.artifact[
        "target_artifact"][
            "selected_candidate_key"] == (
                query.candidate_keys[1])
    assert len(adapter.disagreement_records) == 1


def test_calibrated_advisory_may_displace_terminal_action():
    candidates = (
        ImpactCandidate(
            {
                "action_type": "unit_build_city",
                "actor_id": 1,
            },
            "expansion_move", 10.0,
            "complete settlement"),
        ImpactCandidate(
            {
                "action_type": "unit_move",
                "actor_id": 1,
            },
            "expansion_move", 1.0,
            "continue settlement route"),
    )
    adapter = _adapter(calibrated=True)
    query = _query(adapter, candidates)
    decision = adapter.rank_or_schedule(
        query, "unified_flow_advisory")

    assert decision.health == "healthy"
    assert decision.selected_candidate_key == (
        query.candidate_keys[1])


def test_guarded_fallback_event_preserves_candidate_identities(
        tmp_path):
    candidates = (
        ImpactCandidate(
            {
                "action_type": "unit_build_city",
                "actor_id": 1,
            },
            "expansion_move", 10.0,
            "complete settlement"),
        ImpactCandidate(
            {
                "action_type": "unit_move",
                "actor_id": 1,
            },
            "expansion_move", 1.0,
            "continue settlement route"),
    )
    adapter = _adapter(
        calibrated=False,
        require_calibration=False)
    query = _query(adapter, candidates)
    decision = adapter.rank_or_schedule(
        query, "unified_flow_advisory")
    writer = EventWriter(
        str(tmp_path / "events.jsonl"),
        "guarded-fallback-events",
        durable=False)

    events = ControlEventEmitter().emit_decision(
        writer, _Snapshot.turn,
        query, decision)

    assert [row["type"] for row in events] == [
        "controller_fallback"]
    summary = events[0]["payload"]["summary"]
    assert summary["advisory_candidate_key"] == (
        query.candidate_keys[1])
    assert summary["fallback_candidate_key"] == (
        query.candidate_keys[0])
    assert not summary[
        "advisory_candidate_terminal"]
    assert summary[
        "fallback_candidate_terminal"]


def test_runtime_declares_advisory_layers_without_live_flow():
    activation = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode":
            "unified_flow_advisory",
        "pressure_packet_scheduler_enabled": True,
        "pressure_bridge_enabled": True,
        "pressure_flow_enabled": True,
    })

    assert activation["layers"]["bridge"]["enabled"]
    assert activation["layers"][
        "source_sink_flow"]["enabled"]
