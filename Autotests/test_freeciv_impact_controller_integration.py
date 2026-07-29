"""The versioned controller is wired behind the grounded Impact boundary."""

from copy import deepcopy
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import GroundedImpactPlanner  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _snapshot():
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    return ProxyStateDTO.parse(
        "impact-controller-integration",
        1, payload).to_snapshot()


def _shadow_config():
    return {
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "unified_shadow",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_bridge_enabled": True,
        "pressure_flow_enabled": True,
    }


def test_unified_shadow_preserves_legacy_plan_and_snapshot_byte_semantics():
    snapshot = _snapshot()
    before = snapshot.event_payload()
    advertised = frozenset(
        snapshot.legal_action_json)
    legacy = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v1",
        "pressure_controller_mode": "legacy_scalar",
    })
    shadow = GroundedImpactPlanner(
        _shadow_config())

    legacy_decision = legacy.plan(snapshot)
    shadow_decision = shadow.plan(snapshot)

    assert legacy_decision is not None
    assert shadow_decision is not None
    assert shadow_decision.candidate.action_key == (
        legacy_decision.candidate.action_key)
    assert shadow_decision.plan.to_dict() == (
        legacy_decision.plan.to_dict())
    assert shadow_decision.pressure_artifact == (
        legacy_decision.pressure_artifact)
    assert snapshot.event_payload() == before
    assert shadow.last_control_decision.controller_mode == (
        "unified_shadow")
    assert shadow.last_control_decision.artifact[
        "live_baseline_mode"] == "legacy_scalar"
    flow = next(
        row for row in shadow.last_control_decision.artifact[
            "shadow_decisions"]
        if row["controller_mode"] == "unified_flow")
    assert flow["health"] == "healthy"
    assert not flow["spendable"]
    assert flow["packet_conserved"]
    flow_decision = flow["decision"]
    assert not flow_decision["artifact"][
        "calibrated"]
    assert flow_decision["packet_schedule"][
        "conserved"]
    assert flow_decision["packet_schedule"][
        "committed_operation_ids"]
    assert set(flow_decision["artifact"][
        "admissible_candidate_keys"]) <= advertised
    assert all(
        value >= -1e-9
        for projection in flow_decision[
            "artifact"]["flow"][
                "projection_results"]
        for value in projection[
            "feasible_current"])
    assert flow_decision["artifact"]["flow"][
        "health"]["healthy"]


def test_scalar_v2_materializes_only_an_authoritative_candidate():
    snapshot = _snapshot()
    planner = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
    })
    advertised = frozenset(
        snapshot.legal_action_json)
    decision = planner.plan(snapshot)

    assert decision is not None
    assert decision.candidate.action_key in advertised
    assert planner.last_control_decision.selected_candidate_key == (
        decision.candidate.action_key)
    assert decision.pressure_artifact[
        "pressure"]["pressure_artifact_schema"] == "2.0"
    assert planner.last_control_decision.packet_schedule is not None
    assert planner.last_control_decision.packet_schedule.conserved
    assert (
        planner.last_control_decision.packet_schedule
        .committed_operation_ids)
    assert decision.plan.solver_identity == (
        GroundedImpactPlanner.SOLVER_IDENTITY)


def test_unified_flow_semantic_artifact_is_deterministic():
    decisions = []
    for _ in range(2):
        planner = GroundedImpactPlanner(
            _shadow_config())
        planner.plan(_snapshot())
        row = next(
            value for value in
            planner.last_control_decision.artifact[
                "shadow_decisions"]
            if value["controller_mode"]
            == "unified_flow")
        decision = deepcopy(row["decision"])
        decision["artifact"].pop(
            "controller_telemetry")
        decisions.append(decision)

    assert decisions[0] == decisions[1]


def test_unified_flow_fault_falls_back_without_changing_live_shadow_plan():
    snapshot = _snapshot()
    legacy = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v1",
        "pressure_controller_mode": "legacy_scalar",
    })
    expected = legacy.plan(snapshot)
    planner = GroundedImpactPlanner(
        _shadow_config())
    engine = planner._control_adapter.controllers[
        "unified_flow"].engine

    class BrokenFactorBuilder:
        @staticmethod
        def build(*_args, **_kwargs):
            raise ValueError(
                "injected-factorization-failure")

    engine.factor_builder = BrokenFactorBuilder()
    actual = planner.plan(snapshot)
    row = next(
        value for value in
        planner.last_control_decision.artifact[
            "shadow_decisions"]
        if value["controller_mode"]
        == "unified_flow")

    assert actual.candidate.action_key == (
        expected.candidate.action_key)
    assert row["health"] == "unhealthy"
    assert not row["spendable"]
    assert row["decision"]["artifact"][
        "fallback_reason"] == (
            "flow-exception:ValueError")
    assert row["decision"]["artifact"]["flow"] == {
        "exception_message":
            "injected-factorization-failure",
        "exception_type": "ValueError",
    }
    assert row["decision"]["packet_schedule"][
        "conserved"]
