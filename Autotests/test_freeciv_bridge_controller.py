"""Stage-S3 bridge-scalar live integration and fallback gates."""

import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    BridgeScalarConfig,
)
from freeciv_agent.planning import GroundedImpactPlanner  # noqa: E402
from freeciv_agent.pressure import ImpactPressureRankerV2  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


@pytest.fixture(scope="module")
def live_fixture():
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse(
            "bridge-controller", 1,
            json.load(stream)).to_snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(snapshot)
    return snapshot, candidates


def _rank(ranker, snapshot, candidates):
    return ranker.rank(
        snapshot, candidates,
        expansion_city_target=5,
        horizon_turn=int(snapshot.turn) + 200)


def _test_config(**kwargs):
    values = {
        "probe_path_count": 32,
        "probe_max_steps": 32,
        "probe_minimum_path_diversity": 0.0,
        "probe_reference_fraction": 0.25,
    }
    values.update(kwargs)
    return BridgeScalarConfig(**values)


def test_bridge_scalar_requires_teleological_scoring():
    with pytest.raises(ValueError, match="requires teleological"):
        ImpactPressureRankerV2(
            bridge_scalar_enabled=True)


def test_unvalidated_live_reordering_falls_back_to_scalar_v2(live_fixture):
    snapshot, candidates = live_fixture
    before = snapshot.event_payload()
    baseline = ImpactPressureRankerV2(
        teleological_enabled=True)
    bridge = ImpactPressureRankerV2(
        teleological_enabled=True,
        bridge_scalar_enabled=True,
        bridge_scalar_config=_test_config(
            maximum_regions_per_goal=1))

    scalar_order, scalar_artifact = _rank(
        baseline, snapshot, candidates)
    bridge_order, bridge_artifact = _rank(
        bridge, snapshot, candidates)

    assert bridge_artifact["bridge"]["fallback_required"]
    assert bridge_artifact["bridge"]["fallback_reason"] == (
        "unvalidated_bridge_reordering")
    assert bridge_order == scalar_order
    assert bridge_artifact["schedule"][
        "selected_operation_id"] == (
            scalar_artifact["schedule"][
                "selected_operation_id"])
    assert snapshot.event_payload() == before


def test_healthy_bridge_scalar_uses_one_conserved_packet(live_fixture):
    snapshot, candidates = live_fixture
    ranker = ImpactPressureRankerV2(
        teleological_enabled=True,
        bridge_scalar_enabled=True,
        bridge_scalar_config=_test_config(
            maximum_regions_per_goal=64))

    ordered, artifact = _rank(
        ranker, snapshot, candidates)
    bridge = artifact["bridge"]

    assert not bridge["fallback_required"]
    assert ordered[0].action_key in {
        candidate.action_key for candidate in candidates}
    assert bridge["selected_operation_id"] == (
        artifact["schedule"]["selected_operation_id"])
    packet = bridge["packet_schedule"]
    assert packet["conserved"]
    assert packet["committed_operation_ids"] == [
        bridge["selected_operation_id"]]
    assert packet["accounting"]["action"] == {
        "consumed": 1, "declared": 1, "stranded": 0}
    assert packet["accounting"]["cpu"] == {
        "consumed": 1, "declared": 1, "stranded": 0}
    assert bridge["scalar_decision"][
        "controller_identity"] == (
            "pf-pln-smoothed-scalar/1.0")
    for goal in bridge["goal_selections"]:
        assert goal["forward_probe"]["health"]["healthy"]
        assert goal["backward_probe"]["health"]["healthy"]
        uses = goal["selection"]["signal_ledger"]["uses"]
        assert not any(
            row["signal_name"] == "bridge_height"
            and row["used_in_final_score"]
            for row in uses)


def test_bridge_scalar_same_snapshot_replay_is_deterministic(live_fixture):
    snapshot, candidates = live_fixture
    config = _test_config(maximum_regions_per_goal=64)

    first = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True,
            bridge_scalar_enabled=True,
            bridge_scalar_config=config),
        snapshot, candidates)
    second = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True,
            bridge_scalar_enabled=True,
            bridge_scalar_config=config),
        snapshot, candidates)

    assert first == second


def test_forced_bridge_fault_preserves_scalar_order(live_fixture):
    snapshot, candidates = live_fixture
    baseline = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True),
        snapshot, candidates)
    faulted = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True,
            bridge_scalar_enabled=True,
            bridge_scalar_config=_test_config(
                force_fallback_reason=(
                    "fault-injected-estimator"))),
        snapshot, candidates)

    assert faulted[0] == baseline[0]
    assert faulted[1]["bridge"]["fallback_required"]
    assert faulted[1]["bridge"]["fallback_reason"] == (
        "fault-injected-estimator")
    assert faulted[1]["bridge"]["packet_schedule"] is None


def test_protected_message_union_skips_probes_and_preserves_scalar(
        live_fixture):
    snapshot, candidates = live_fixture
    baseline = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True),
        snapshot, candidates)
    protected = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True,
            bridge_scalar_enabled=True,
            bridge_scalar_config=_test_config(
                readout_policy=(
                    "protected-message-union"),
                maximum_regions_per_goal=2)),
        snapshot, candidates)

    bridge = protected[1]["bridge"]
    union = bridge["goal_selections"][-1][
        "protected_candidate_union"]
    assert not bridge["fallback_required"]
    assert protected[0] == baseline[0]
    assert union["readout_policy"] == (
        "protected-message-union")
    assert union["scalar_ranked_operation_ids"][0] == (
        bridge["selected_operation_id"])
    assert all(
        row["forward_probe"] is None
        and row["backward_probe"] is None
        for row in bridge["goal_selections"][:-1])


def test_corrected_probe_union_adds_recall_without_scoring_probe_signal(
        live_fixture):
    snapshot, candidates = live_fixture
    ordered, artifact = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True,
            bridge_scalar_enabled=True,
            bridge_scalar_config=_test_config(
                readout_policy="corrected-probe-union",
                maximum_regions_per_goal=2)),
        snapshot, candidates)

    bridge = artifact["bridge"]
    union = bridge["goal_selections"][-1][
        "protected_candidate_union"]
    assert not bridge["fallback_required"]
    assert ordered
    assert union["readout_policy"] == (
        "corrected-probe-union")
    assert union["scalar_ranked_operation_ids"][0] == (
        bridge["selected_operation_id"])
    assert not any(
        row["used_in_final_score"]
        for row in union["signal_ledger"]["uses"]
        if row["signal_name"] in (
            "bridge_height",
            "corrected_probe_weight",
            "raw_probe_count"))
