"""Controller-inclusive live-parity, fallback, and timing gates for G3."""

import json
import os
import platform
import time

from freeciv.pf_unified.bridge_experiment import (
    run_g3_bridge_experiment,
)
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.flow_control import BridgeScalarConfig
from freeciv_agent.paths import REPO_ROOT
from freeciv_agent.planning import GroundedImpactPlanner
from freeciv_agent.pressure import ImpactPressureRankerV2
from freeciv_agent.state import ProxyStateDTO


def _fixture():
    relative = "benchmarks/freeciv/samples/real_state_turn1.json"
    with open(
            os.path.join(REPO_ROOT, relative),
            encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse(
            "pf-g3-bridge", 1,
            json.load(stream)).to_snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(snapshot)
    return relative, snapshot, candidates


def _config(**kwargs):
    values = {
        "maximum_regions_per_goal": 64,
        "probe_max_steps": 32,
        "probe_minimum_path_diversity": 0.0,
        "probe_path_count": 32,
        "probe_reference_fraction": 0.25,
        "seed": 1729,
    }
    values.update(kwargs)
    return BridgeScalarConfig(**values)


def _rank(ranker, snapshot, candidates):
    return ranker.rank(
        snapshot, candidates,
        expansion_city_target=5,
        horizon_turn=int(snapshot.turn) + 200)


def run_g3_verification(
        train_seeds_per_family=64,
        heldout_seeds_per_family=64):
    relative, snapshot, candidates = _fixture()
    before = snapshot.event_payload()
    scalar = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True),
        snapshot, candidates)
    healthy = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True,
            bridge_scalar_enabled=True,
            bridge_scalar_config=_config()),
        snapshot, candidates)
    replay = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True,
            bridge_scalar_enabled=True,
            bridge_scalar_config=_config()),
        snapshot, candidates)
    guarded = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True,
            bridge_scalar_enabled=True,
            bridge_scalar_config=_config(
                maximum_regions_per_goal=8)),
        snapshot, candidates)
    faulted = _rank(
        ImpactPressureRankerV2(
            teleological_enabled=True,
            bridge_scalar_enabled=True,
            bridge_scalar_config=_config(
                force_fallback_reason=(
                    "g3-fault-injection"))),
        snapshot, candidates)
    experiment = run_g3_bridge_experiment(
        train_seeds_per_family,
        heldout_seeds_per_family,
        timing_repetitions=1)
    bridge = healthy[1]["bridge"]
    packet = bridge["packet_schedule"]
    probe_health = tuple(
        health
        for goal in bridge["goal_selections"]
        for health in (
            goal["forward_probe"]["health"],
            goal["backward_probe"]["health"]))
    signal_uses = tuple(
        use
        for goal in bridge["goal_selections"]
        for use in goal["selection"][
            "signal_ledger"]["uses"])
    report = {
        "claim_status": (
            "G3-synthetic-control-gate;"
            "not-a-FreeCiv-gameplay-score-claim"),
        "fallback": {
            "fault_injection_preserves_scalar_selection": (
                faulted[0][0].action_key
                == scalar[0][0].action_key),
            "fault_reason": faulted[1][
                "bridge"]["fallback_reason"],
            "unvalidated_policy_preserves_scalar_selection": (
                guarded[0][0].action_key
                == scalar[0][0].action_key),
            "unvalidated_disagreement_reason": guarded[1][
                "bridge"]["fallback_reason"],
        },
        "heldout_experiment": {
            "bridge_completion_rate": experiment[
                "arms"]["explicit_bridge"][
                    "completion_rate"],
            "claim_status": experiment["claim_status"],
            "context_completion_rate": experiment[
                "arms"]["scalar_context_conductance"][
                    "completion_rate"],
            "primary_comparison": experiment[
                "comparisons"][
                    "bridge_vs_context_conductance"],
            "verification_hash": experiment[
                "verification_hash"],
        },
        "live_controller": {
            "candidate_count": len(candidates),
            "deterministic": healthy == replay,
            "edge_count": bridge[
                "flow_summary"]["edge_count"],
            "goal_selection_count": len(
                bridge["goal_selections"]),
            "healthy": not bridge["fallback_required"],
            "minimum_effective_sample_fraction": min(
                row["effective_sample_fraction"]
                for row in probe_health),
            "minimum_path_diversity": min(
                row["path_diversity"]
                for row in probe_health),
            "node_count": bridge[
                "flow_summary"]["node_count"],
            "packet_conserved": packet["conserved"],
            "packet_selected_once": (
                packet["committed_operation_ids"] == [
                    bridge["selected_operation_id"]]),
            "parity_selected_action": (
                healthy[0][0].action_key
                == scalar[0][0].action_key),
            "potential_process_semantics": bridge[
                "potential_summary"]["process_semantics"],
            "probe_telemetry_is_non_evidential": all(
                set(goal["forward_probe"]).isdisjoint({
                    "evidence_ids", "truth", "confidence"})
                and set(goal["backward_probe"]).isdisjoint({
                    "evidence_ids", "truth", "confidence"})
                for goal in bridge["goal_selections"]),
            "selected_action_legal": (
                healthy[0][0].action_key in {
                    row.action_key for row in candidates}),
            "signal_single_use": (
                not any(
                    row["signal_name"] in (
                        "bridge_height",
                        "raw_probe_count")
                    and row["used_in_final_score"]
                    for row in signal_uses)
                and sum(
                    row["signal_name"] == "typed_advantage"
                    and row["used_in_final_score"]
                    for row in signal_uses)
                == len(bridge["goal_selections"])),
            "snapshot_path": relative,
            "snapshot_unchanged": (
                snapshot.event_payload() == before),
        },
        "recovery_policy": {
            "collapsed_path_diversity": (
                "deterministic_messages"),
            "high_clipped_weight_fraction": (
                "deterministic_messages"),
            "low_effective_sample_size": (
                "deterministic_messages"),
            "recovery_actions": [
                "increase_reference_probes",
                "increase_temperature",
                "weaken_route_momentum",
                "increase_exploration",
            ],
        },
        "schema_version": "1.0",
    }
    live = report["live_controller"]
    fallback = report["fallback"]
    report["valid"] = all((
        experiment["valid"],
        experiment["comparisons"][
            "bridge_vs_context_conductance"][
                "bootstrap_95_ci"][0] > 0.0,
        live["deterministic"],
        live["healthy"],
        live["minimum_effective_sample_fraction"] >= 0.2,
        live["minimum_path_diversity"] >= 0.0,
        live["packet_conserved"],
        live["packet_selected_once"],
        live["parity_selected_action"],
        live["probe_telemetry_is_non_evidential"],
        live["selected_action_legal"],
        live["signal_single_use"],
        live["snapshot_unchanged"],
        fallback["fault_injection_preserves_scalar_selection"],
        fallback[
            "unvalidated_policy_preserves_scalar_selection"],
    ))
    report["verification_hash"] = structural_hash(report)
    return report


def _distribution(values):
    values = tuple(sorted(float(value) for value in values))
    return {
        "maximum_ms": max(values),
        "mean_ms": sum(values) / len(values),
        "p95_ms": values[min(
            len(values) - 1,
            int(math_ceil(0.95 * len(values))) - 1)],
    }


def math_ceil(value):
    integer = int(value)
    return integer if value == integer else integer + 1


def run_g3_live_timing(
        repetitions=10, controller_budget_ms=500.0):
    repetitions = max(1, int(repetitions))
    controller_budget_ms = float(controller_budget_ms)
    if controller_budget_ms <= 0.0:
        raise ValueError(
            "controller budget must be positive")
    _, snapshot, candidates = _fixture()
    scalar_times = []
    bridge_times = []
    for _ in range(repetitions):
        started = time.perf_counter()
        _rank(
            ImpactPressureRankerV2(
                teleological_enabled=True),
            snapshot, candidates)
        scalar_times.append(
            (time.perf_counter() - started) * 1000.0)
        started = time.perf_counter()
        _rank(
            ImpactPressureRankerV2(
                teleological_enabled=True,
                bridge_scalar_enabled=True,
                bridge_scalar_config=_config()),
            snapshot, candidates)
        bridge_times.append(
            (time.perf_counter() - started) * 1000.0)
    scalar = _distribution(scalar_times)
    bridge = _distribution(bridge_times)
    semantic = {
        "candidate_count": len(candidates),
        "controller_budget_ms": controller_budget_ms,
        "measurement_scope": (
            "snapshot-to-ranked-candidates including pressure, "
            "teleology, factor graph, potentials, corrected probes, "
            "region selection, strong scalar selection, packets, "
            "and artifact serialization"),
        "repetitions": repetitions,
        "schema_version": "1.0",
    }
    report = dict(semantic)
    report.update({
        "bridge_scalar": bridge,
        "bridge_within_budget": (
            bridge["p95_ms"] <= controller_budget_ms),
        "platform": {
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "system": platform.system(),
        },
        "scalar_v2_teleological": scalar,
        "teleological_bridge_over_scalar_ratio": (
            bridge["mean_ms"] / scalar["mean_ms"]),
    })
    report["timing_hash"] = structural_hash({
        "bridge_scalar": bridge,
        "platform": report["platform"],
        "scalar_v2_teleological": scalar,
        "semantic": semantic,
    })
    return report
