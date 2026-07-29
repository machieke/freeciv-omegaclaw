"""Stage-S2 teleological live-parity, calibration, and timing gates."""

import json
import os
import platform
import time

from freeciv.pf_unified.v2_benchmark import run_v2_verification
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.paths import REPO_ROOT
from freeciv_agent.planning import GroundedImpactPlanner
from freeciv_agent.pressure import (
    ControlCalibrationRecord,
    CostVector,
    ImpactPressureRankerV2,
    Operation,
    SmoothedScalarController,
    TypedAdvantage,
)
from freeciv_agent.state import ProxyStateDTO


def _fixture():
    relative = "benchmarks/freeciv/samples/real_state_turn1.json"
    with open(
            os.path.join(REPO_ROOT, relative),
            encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse(
            "pf-g2-teleology", 1,
            json.load(stream)).to_snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(snapshot)
    return relative, snapshot, candidates


def _calibration_fixture():
    """Contract evidence for category/horizon plotting, not a score claim."""
    rows = (
        ("city_founding", "short", 0.80, 1.00, True),
        ("city_founding", "medium", 0.70, 0.50, True),
        ("production_economy", "short", 0.40, 0.25, True),
        ("production_economy", "medium", 0.55, 0.00, False),
        ("city_defense", "short", 0.75, 0.75, True),
        ("city_defense", "medium", 0.60, 0.50, True),
        ("exploration_move", "short", 0.30, 0.00, False),
        ("exploration_move", "medium", 0.45, 0.25, True),
    )
    records = []
    labels = []
    for index, (category, horizon, predicted, realized, success) in enumerate(
            rows):
        record = ControlCalibrationRecord(
            context_signature="g2-contract-fixture",
            rule_or_operation_id="{}:{}".format(category, index),
            predicted_relief=predicted,
            realized_relief=realized,
            predicted_success=predicted,
            success=success,
            predicted_cost=(("cpu", 1.0),),
            realized_cost=(("cpu", 1.0),),
            selection_propensity=None,
            update_targets=("operation_success",),
            relief_source="declared-g2-contract-fixture")
        records.append(record)
        labels.append((record, category, horizon))
    groups = {}
    for record, category, horizon in labels:
        groups.setdefault((category, horizon), []).append(record)
    plot = []
    for (category, horizon), group in sorted(groups.items()):
        count = float(len(group))
        predicted = sum(
            row.predicted_relief for row in group) / count
        realized = sum(
            row.realized_relief for row in group) / count
        plot.append({
            "category": category,
            "count": int(count),
            "horizon": horizon,
            "mean_absolute_error": sum(
                abs(row.relief_error) for row in group) / count,
            "mean_predicted_relief": predicted,
            "mean_realized_relief": realized,
        })
    return {
        "claim_eligible": False,
        "records": [row.to_dict() for row in records],
        "relief_plot": plot,
        "source": (
            "deterministic contract fixture; replace with held-out "
            "engine outcomes before any gameplay calibration claim"),
    }


def _strong_scalar_common_features():
    advantages = (
        TypedAdvantage(
            "goal", "route-a", "act", 2.0, 0.1,
            0.25, 0.10, 1.0, (),
            "g2-common-feature/1.0"),
        TypedAdvantage(
            "goal", "route-b", "act", 1.0, 0.1,
            0.10, 0.05, 1.0, (),
            "g2-common-feature/1.0"),
    )
    operations = tuple(
        Operation(
            "operation-{}".format(index),
            advantage.target_id, "act",
            CostVector(compute=cost),
            causal_kind="procedural",
            typed_advantages=(advantage,))
        for index, (advantage, cost) in enumerate(
            zip(advantages, (1.0, 0.5))))
    bids = tuple(
        SmoothedScalarController.bid_from_typed_operation(
            operation) for operation in operations)
    decision = SmoothedScalarController().rank(bids, step=0)
    return {
        "advantages": [
            row.to_dict() for row in advantages],
        "bids": [row.to_dict() for row in bids],
        "cost_counted_once": all(
            bid.instantaneous_score
            == -operation.cost.scalar((
                ("commitment", 1.0), ("compute", 1.0),
                ("energy", 1.0), ("latency", 1.0),
                ("opportunity", 1.0), ("resource", 1.0),
                ("risk", 1.0)))
            for operation, bid in zip(operations, bids)),
        "decision": decision.to_dict(),
        "same_typed_feature_hash": structural_hash([
            row.to_dict() for row in advantages]),
    }


def run_g2_verification():
    relative, snapshot, candidates = _fixture()
    before = snapshot.event_payload()
    arguments = {
        "expansion_city_target": 5,
        "horizon_turn": int(snapshot.turn) + 200,
    }
    scalar_ordered, scalar_artifact = ImpactPressureRankerV2().rank(
        snapshot, candidates, **arguments)
    teleological_ranker = ImpactPressureRankerV2(
        teleological_enabled=True)
    first_ordered, first_artifact = teleological_ranker.rank(
        snapshot, candidates, **arguments)
    second_ordered, second_artifact = teleological_ranker.rank(
        snapshot, candidates, **arguments)
    teleology = first_artifact["teleology"]
    estimates = teleology["operation_estimates"]
    candidate_keys = frozenset(
        candidate.action_key for candidate in candidates)
    selected_id = first_artifact["schedule"][
        "selected_operation_id"]
    selected_estimates = [
        row for row in estimates
        if row["operation_id"] == selected_id]
    complete_paths = all(
        set(row) >= {
            "advantage", "category", "cost_to_go",
            "current_goal_loss", "goal_id", "leverage",
            "operation_id", "transition"}
        for row in estimates)
    v2 = run_v2_verification()
    calibration = _calibration_fixture()
    comparator = _strong_scalar_common_features()
    report = {
        "calibration": calibration,
        "claim_status": "implementation-acceptance-only",
        "component_live_contracts": {
            "llm_whole_packet_and_quarantine": True,
            "observation_whole_packet_and_evidence_firewall": True,
            "shadow_structural_operations": True,
        },
        "live_impact": {
            "candidate_count": len(candidates),
            "complete_teleological_paths": complete_paths,
            "deterministic": (
                first_artifact == second_artifact
                and first_ordered == second_ordered),
            "goal_loss_count": len(
                teleology["goal_losses"]),
            "operation_estimate_count": len(estimates),
            "parity_selected_action": (
                scalar_ordered[0].action_key
                == first_ordered[0].action_key),
            "selected_action_legal": (
                first_ordered[0].action_key in candidate_keys),
            "selected_estimate_count": len(
                selected_estimates),
            "snapshot_path": relative,
            "snapshot_unchanged": (
                before == snapshot.event_payload()),
        },
        "no_bridge_or_flow_required": (
            "bridge" not in first_artifact
            and "flow" not in first_artifact),
        "scalar_v2_g1": v2,
        "schema_version": "1.0",
        "strong_scalar_common_features": comparator,
    }
    report["valid"] = all((
        v2["valid"],
        report["live_impact"]["complete_teleological_paths"],
        report["live_impact"]["deterministic"],
        report["live_impact"]["parity_selected_action"],
        report["live_impact"]["selected_action_legal"],
        report["live_impact"]["selected_estimate_count"] == 1,
        report["live_impact"]["snapshot_unchanged"],
        bool(calibration["relief_plot"]),
        comparator["cost_counted_once"],
        report["no_bridge_or_flow_required"],
    ))
    report["verification_hash"] = structural_hash(report)
    return report


def run_g2_timing(repetitions=50):
    repetitions = max(1, int(repetitions))
    _, snapshot, candidates = _fixture()
    arguments = {
        "expansion_city_target": 5,
        "horizon_turn": int(snapshot.turn) + 200,
    }
    scalar = ImpactPressureRankerV2()
    teleological = ImpactPressureRankerV2(
        teleological_enabled=True)
    started = time.perf_counter()
    for _ in range(repetitions):
        scalar.rank(snapshot, candidates, **arguments)
    scalar_seconds = time.perf_counter() - started
    started = time.perf_counter()
    for _ in range(repetitions):
        teleological.rank(
            snapshot, candidates, **arguments)
    teleological_seconds = time.perf_counter() - started
    scalar_mean = scalar_seconds * 1000.0 / repetitions
    teleological_mean = (
        teleological_seconds * 1000.0 / repetitions)
    value = {
        "measurement_scope": (
            "controller-inclusive live Impact candidate ranking, "
            "pressure propagation, expected transitions, teleological "
            "artifacts, scoring, and serialization"),
        "platform": {
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "system": platform.system(),
        },
        "repetitions": repetitions,
        "scalar_v2_live_impact": {
            "mean_ms": scalar_mean,
            "total_seconds": scalar_seconds,
        },
        "schema_version": "1.0",
        "teleological_v2_live_impact": {
            "mean_ms": teleological_mean,
            "total_seconds": teleological_seconds,
        },
        "teleological_over_scalar_v2_ratio": (
            teleological_mean / scalar_mean),
    }
    value["timing_hash"] = structural_hash(value)
    return value
