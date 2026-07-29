"""Stage-S5 unified shadow-mode safety and replay gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pf_runtime import (  # noqa: E402
    PFRuntimeConfigurationError,
    build_controller_activation,
)
from freeciv_agent.planning import (  # noqa: E402
    ControlDecision,
    ImpactCandidate,
    ImpactControlAdapter,
    ShadowBudgetConfig,
)
from freeciv_agent.pressure import (  # noqa: E402
    PacketBudget,
    PacketCost,
    PacketReservation,
    PacketSchedule,
    ResourceKind,
)


class _Snapshot:
    snapshot_id = "shadow-snapshot"
    legal_actions_digest = "shadow-legal"
    turn = 8
    ruleset_name = "classic"

    def event_payload(self):
        return {
            "legal_actions_digest":
                self.legal_actions_digest,
            "snapshot_id": self.snapshot_id,
            "turn": self.turn,
        }


class _Ranker:
    def rank(
            self, snapshot, candidates,
            expansion_city_target, horizon_turn,
            survival_threat_radius, **kwargs):
        del (
            snapshot, expansion_city_target,
            horizon_turn, survival_threat_radius,
            kwargs)
        return tuple(reversed(candidates)), {
            "ranker": "shadow-fixture"}


def _candidates():
    return (
        ImpactCandidate(
            {"action_type": "unit_move", "actor_id": 1},
            "exploration_move", 10.0, "canonical-first"),
        ImpactCandidate(
            {"action_type": "unit_move", "actor_id": 2},
            "exploration_move", 1.0, "shadow-first"),
    )


def _packet_schedule(operation_id):
    cost = PacketCost(ResourceKind.ACTION, 1)
    return PacketSchedule(
        budgets=(PacketBudget(
            ResourceKind.ACTION, 1),),
        reservations=(PacketReservation(
            operation_id=operation_id,
            costs=(cost,), reserved=(cost,),
            state="committed"),),
        committed_operation_ids=(operation_id,),
        stranded_quanta=(),
        integrality_gap=0.0,
        relaxed_value=1.0,
        committed_value=1.0,
        scheduler_identity="shadow-fixture")


def _flow_engine(query, snapshot):
    del snapshot
    keys = tuple(reversed(query.candidate_keys))
    return ControlDecision(
        ordered_candidate_keys=keys,
        selected_candidate_key=keys[0],
        packet_schedule=_packet_schedule(keys[0]),
        controller_mode="unified_flow",
        artifact={"engine": "shadow-flow"},
        health="healthy",
        fallback_chain=())


def _adapter(flow_engine=_flow_engine):
    ranker = _Ranker()
    return ImpactControlAdapter(
        scalar_v2_ranker=ranker,
        bridge_scalar_ranker=ranker,
        unified_flow_engine=flow_engine,
        shadow_budget=ShadowBudgetConfig(
            per_controller_ms=1000.0,
            total_ms=3000.0))


def _query(adapter):
    return adapter.build_query(
        snapshot=_Snapshot(),
        candidates=_candidates(),
        expansion_city_target=5,
        horizon_turn=40,
        survival_threat_radius=6,
        goal_facts={"exploration": {}},
        normalization_contract_hash="normalization-v1",
        ruleset_digest="ruleset-v1")


def test_shadow_never_changes_canonical_live_selection():
    adapter = _adapter()
    query = _query(adapter)
    canonical = adapter.rank_or_schedule(
        query, "canonical")
    shadow = adapter.rank_or_schedule(
        query, "unified_shadow")

    assert shadow.controller_mode == "unified_shadow"
    assert shadow.ordered_candidate_keys == (
        canonical.ordered_candidate_keys)
    assert shadow.selected_candidate_key == (
        canonical.selected_candidate_key)
    assert shadow.packet_schedule is None
    assert shadow.artifact[
        "live_execution_ledger_writes"] == 0
    assert not shadow.artifact[
        "shadow_packets_spendable"]
    assert shadow.artifact["snapshot_unchanged"]
    assert shadow.artifact["candidate_set_unchanged"]


def test_shadow_packets_are_conserved_but_never_spendable():
    adapter = _adapter()
    shadow = adapter.rank_or_schedule(
        _query(adapter), "unified_shadow")
    rows = shadow.artifact["shadow_decisions"]

    assert rows
    assert all(not row["spendable"] for row in rows)
    flow = next(
        row for row in rows
        if row["controller_mode"] == "unified_flow")
    assert flow["packet_conserved"]
    assert flow["decision"]["packet_schedule"]["conserved"]


def test_shadow_replay_hash_excludes_latency_telemetry():
    adapter = _adapter()
    query = _query(adapter)
    first = adapter.rank_or_schedule(
        query, "unified_shadow")
    second = adapter.rank_or_schedule(
        query, "unified_shadow")

    assert first.decision_hash == second.decision_hash
    assert first.artifact[
        "controller_telemetry"]["total_latency_ms"] >= 0.0
    assert second.artifact[
        "controller_telemetry"]["total_latency_ms"] >= 0.0


def test_shadow_fault_isolated_from_live_canonical_decision():
    def failed_flow(query, snapshot):
        del query, snapshot
        raise RuntimeError("injected")

    adapter = _adapter(failed_flow)
    query = _query(adapter)
    canonical = adapter.rank_or_schedule(
        query, "canonical")
    shadow = adapter.rank_or_schedule(
        query, "unified_shadow")
    flow = next(
        row for row in shadow.artifact[
            "shadow_decisions"]
        if row["controller_mode"] == "unified_flow")

    assert shadow.selected_candidate_key == (
        canonical.selected_candidate_key)
    assert flow["health"] == "unhealthy"
    assert flow["error_type"] == "RuntimeError"
    assert not flow["spendable"]


def test_runtime_accepts_only_fully_declared_unified_shadow():
    activation = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "unified_shadow",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_bridge_enabled": True,
        "pressure_flow_enabled": True,
    })

    assert activation["controller_policy"][
        "pressure_controller_mode"] == "unified_shadow"
    assert activation["layers"]["bridge"]["enabled"]
    assert activation["layers"][
        "source_sink_flow"]["enabled"]
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="requires pressure flow"):
        build_controller_activation({
            "pressure_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_controller_mode": "unified_shadow",
            "pressure_packet_scheduler_enabled": True,
            "pressure_bridge_enabled": True,
            "pressure_flow_enabled": False,
        })


def test_shadow_can_preserve_the_existing_legacy_live_baseline():
    snapshot = _Snapshot()
    candidates = _candidates()
    adapter = ImpactControlAdapter(
        legacy_ranker=_Ranker(),
        scalar_v2_ranker=_Ranker(),
        shadow_live_mode="legacy_scalar")
    query = adapter.build_query(
        snapshot, candidates, 5, 40, 6,
        {"expansion": {}},
        normalization_contract_hash="normalization-v1",
        ruleset_digest="ruleset-v1")

    legacy = adapter.rank_or_schedule(
        query, "legacy_scalar")
    shadow = adapter.rank_or_schedule(
        query, "unified_shadow")

    assert shadow.selected_candidate_key == (
        legacy.selected_candidate_key)
    assert shadow.ordered_candidate_keys == (
        legacy.ordered_candidate_keys)
    assert shadow.artifact[
        "live_baseline_mode"] == "legacy_scalar"
