"""The versioned controller is wired behind the grounded Impact boundary."""

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
    assert flow["health"] == "unavailable"
    assert not flow["spendable"]


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
    assert decision.plan.solver_identity == (
        GroundedImpactPlanner.SOLVER_IDENTITY)
