"""Deterministic CI backend exercising the exact harness/event interfaces.

This backend is deliberately labeled representative, never engine-live. The same runner
accepts a live backend for release evidence; CI uses this fast path to test orchestration,
resumption, metrics, statistics, and negative-result reporting.
"""

import os
import random

from freeciv_agent.events.model import atom
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.writer import EventWriter
from freeciv_agent.pf_runtime import (
    emit_runtime_activation,
    validate_runtime_activation,
)


CONDITION_INDEX = {
    "a_stock_llm": 0, "b_state_oracle": 1, "c_dependency_scheduler": 2,
    "d_uncertain_monitor": 3, "e_full_loop": 4,
}


def _metric(writer, turn, parent, name, value, condition, track, **labels):
    label_values = {"condition": condition, "track": track}
    label_values.update({key: str(value) for key, value in labels.items()})
    return writer.emit("metric_sample", turn, {
        "labels": label_values, "name": name, "unit": (
            "ms" if name.endswith("_ms") else "turns" if name.endswith("_turns") else "ratio"),
        "value": float(value),
    }, caused_by=[parent])


def run_game(run_dir, manifest, context):
    condition = manifest["condition_id"]
    index = CONDITION_INDEX[condition]
    seed = manifest["seed"]
    track = manifest["track"]
    randomizer = random.Random(seed * 97 + index * 7919 + (17 if track == "induction" else 0))
    events_path = manifest["events_path"]
    if not events_path.startswith(os.path.sep):
        events_path = os.path.join(run_dir, events_path)
    writer = EventWriter(events_path, manifest["game_id"], durable=False)
    root = writer.emit("run_started", 0, {
        "condition_id": condition, "manifest_identity": manifest["manifest_identity"]})
    pf_runtime = validate_runtime_activation(
        manifest["pf_pln_runtime"],
        "representative",
        context.capabilities,
        manifest["impact_policy"],
    )
    parent, _ = emit_runtime_activation(
        writer,
        0,
        root["event_id"],
        pf_runtime,
        condition,
        track,
    )
    beliefs = manifest["beliefs"]
    for key, value in sorted(beliefs.items()):
        if key in ("decay", "schema_version", "sweep"):
            continue
        event = _metric(
            writer, 0, parent, "belief_{}".format(key), value, condition, track,
            declaration="release_configuration")
        parent = event["event_id"]
    for predicate, schedule in sorted(beliefs["decay"].items()):
        event = _metric(
            writer, 0, parent, "belief_decay_window_turns",
            schedule["window_turns"], condition, track,
            declaration="release_configuration", predicate=predicate,
            formula=schedule["formula"])
        parent = event["event_id"]
    snapshot = writer.emit("state_snapshot", 1, {
        "map": {"height": 10, "visible": [[1, 1]], "width": 10},
        "own_state": {"gold": 20, "score": 10 + index, "turn": 1},
        "player_id": 1, "snapshot_id": "snapshot-{}".format(seed),
        "state_hash": structural_hash([condition, seed, "state"]), "uncertain_atoms": [],
    }, caused_by=[parent])
    proposal = writer.emit("llm_proposal", 1, {
        "claims": [], "goals": [{"goal_atom_id": "goal-evaluate", "predicate": "researchable"}],
        "model": manifest["model"], "prompt_version": "harness-representative/1.0",
        "proposal_id": "proposal-{}".format(seed),
    }, caused_by=[snapshot["event_id"]])
    parent = proposal["event_id"]
    if context.capabilities["authoritative_state"]:
        context.use("authoritative_state")
    if context.capabilities["dependency_oracle"]:
        context.use("dependency_oracle")
    if context.capabilities["scheduler"]:
        context.use("scheduler")
    if context.capabilities["uncertain_beliefs"]:
        context.use("uncertain_beliefs")
    if context.capabilities["assumption_monitor"]:
        context.use("assumption_monitor")
    if context.capabilities["constrained_llm"]:
        context.use("constrained_llm")
    action = writer.emit("action_sent", 1, {
        "action": {"action_type": "end_turn"}, "action_id": "action-{}".format(seed),
        "legal_actions_digest": structural_hash([seed, "legal"]), "plan_id": None,
        "snapshot_id": "snapshot-{}".format(seed), "step_id": None,
    }, caused_by=[parent])
    result = writer.emit("action_result", 1, {
        "action_id": "action-{}".format(seed), "engine_response": {"accepted": True},
        "engine_turn": 1, "status": "accepted",
    }, caused_by=[action["event_id"]])
    # The effect pattern intentionally contains improvements, null effects, and a
    # regression so the report's negative-result path is continuously exercised.
    score_shift = (0.0, 8.0, 3.0, -1.0, 4.0)[index]
    impact_pair = manifest.get("impact_pair")
    pair_pattern = manifest.get("impact_pair", {}).get("pair_index", 0) % 5
    if impact_pair and impact_pair["arm"] == "treatment":
        score_shift += (-2.0, 0.0, 2.0, 4.0, 6.0)[pair_pattern]
    score = 100.0 + score_shift + randomizer.uniform(-12, 12)
    win_probability = (0.30, 0.47, 0.51, 0.49, 0.55)[index]
    if impact_pair:
        win_probability = 0.50
        if impact_pair["arm"] == "treatment":
            win_probability += (-0.10, 0.0, 0.05, 0.10, 0.15)[pair_pattern]
    won = randomizer.random() < win_probability
    opponent_score = score - 1.0 if won else score + 1.0
    score_margin = score - opponent_score
    latency = (5000, 300, 500, 650, 850)[index] + randomizer.uniform(0, 120)
    metrics = [
        ("game_win", int(won)), ("score_lead_turn_n", int(won)),
        ("score_turn_n", score), ("opponent_score_turn_n", opponent_score),
        ("score_margin_turn_n", score_margin),
        ("engine_rejected_action_rate", 0.0),
        ("confabulation_write_through", 0.0), ("loop_latency_ms", latency),
    ]
    impact_actions = (0, 0, 8, 9, 11)[index]
    impact_values = {
        "effect_rate": (0.0, 0.0, 0.9, 0.92, 0.95)[index],
        "failover_attempts": (0, 0, 1, 2, 3)[index],
        "failover_recoveries": (0, 0, 1, 1, 2)[index],
        "no_effect": (0, 0, 1, 1, 1)[index],
        "positions": (0, 0, 5, 6, 8)[index],
        "retries_blocked": (0, 0, 0, 1, 2)[index],
        "tactical": (0, 0, 1, 2, 3)[index],
    }
    treatment = bool(impact_pair and impact_pair["arm"] == "treatment")
    if impact_pair:
        impact_actions = 58 if treatment else 49
        impact_values = {
            "effect_rate": 0.776 if treatment else 0.571,
            "failover_attempts": 11 if treatment else 0,
            "failover_recoveries": 7 if treatment else 0,
            "no_effect": 13 if treatment else 21,
            "positions": 36 if treatment else 19,
            "retries_blocked": 2 if treatment else 60,
            "tactical": 9 if treatment else 2,
        }
    failover_rate = (float(impact_values["failover_recoveries"])
                     / max(1, impact_values["failover_attempts"]))
    metrics.extend((
        ("planned_engine_actions", impact_actions + int(bool(impact_pair))),
        ("meaningful_actions_per_turn", (impact_actions + int(bool(impact_pair)))
         / float(manifest["turn_limit"])),
        ("decision_impact_actions", impact_actions),
        ("decision_impact_turn_rate", min(1.0, impact_actions / float(manifest["turn_limit"]))),
        ("decision_effect_observed_rate", impact_values["effect_rate"]),
        ("decision_effect_confirmation_latency_ms", 25.0 if treatment else 30.0),
        ("decision_effect_confirmation_timeouts", impact_values["no_effect"]),
        ("decision_effect_confirmation_deferred", impact_values["no_effect"]),
        ("decision_effect_confirmation_recovered",
         10 if treatment else 15),
        ("decision_effect_confirmation_expired",
         3 if treatment else 6),
        ("decision_effect_confirmation_pending", 0),
        ("decision_no_effect_actions", impact_values["no_effect"]),
        ("decision_no_effect_retries_blocked", impact_values["retries_blocked"]),
        ("decision_no_effect_failover_attempts", impact_values["failover_attempts"]),
        ("decision_no_effect_failover_recoveries", impact_values["failover_recoveries"]),
        ("decision_no_effect_failover_recovery_rate", failover_rate),
        ("model_safe_fallback_rate", 0.0),
        ("model_corrections_per_turn", 0.0),
        ("model_selection_call_rate", 0.0),
        ("model_selection_call_avoided_rate", 0.0),
        ("action_type_diversity", (1, 1, 3, 3, 4)[index]),
        ("cities_gained", (0, 0, 1, 1, 2)[index]),
        ("cities_founded", (0, 0, 1, 1, 2)[index]),
        ("technologies_acquired", (0, 0, 1, 1, 2)[index]),
        ("positions_explored", impact_values["positions"]),
        ("production_changes", (0, 0, 1, 1, 2)[index]),
        ("founder_production_changes", 1 if treatment else 0),
        ("production_repurpose_changes", 1 if treatment else 0),
        ("production_preexpansion_growth_changes", 1 if treatment else 0),
        ("production_preexpansion_founder_changes", 1 if treatment else 0),
        ("production_military_score_changes", 1 if treatment else 0),
        ("settlement_attempts", 2 if treatment else 1),
        ("settlement_completions", 2 if treatment else 1),
        ("planner_capability_pruned_worker_moves", 4 if treatment else 0),
        ("planner_nonprogress_moves_pruned", 6 if treatment else 2),
        ("planner_repeated_failed_destination_moves_pruned",
         3 if treatment else 1),
        ("planner_founder_unreachable_moves_pruned", 2 if treatment else 0),
        ("planner_founder_cycle_moves_pruned", 1 if treatment else 0),
        ("planner_founder_attrition_moves_pruned", 1 if treatment else 0),
        ("planner_failed_settlement_sites_pruned", 1 if treatment else 0),
        ("planner_founder_route_successes", 4 if treatment else 2),
        ("planner_founder_route_failures", 1 if treatment else 2),
        ("planner_founder_route_success_rate", 0.8 if treatment else 0.5),
        ("planner_founder_cardinal_corridor_attempts", 2 if treatment else 0),
        ("planner_founder_cardinal_corridor_successes", 2 if treatment else 0),
        ("planner_founder_cardinal_corridor_success_rate",
         1.0 if treatment else 0.0),
        ("planner_founder_settlement_site_preference_attempts",
         2 if treatment else 0),
        ("planner_founder_settlement_site_preference_successes",
         2 if treatment else 0),
        ("planner_founder_settlement_site_preference_success_rate",
         1.0 if treatment else 0.0),
        ("planner_founder_capable_unit_types", 1 if treatment else 0),
        ("population_recovery_route_attempts", 3 if treatment else 0),
        ("population_recovery_route_successes", 3 if treatment else 0),
        ("population_recovery_route_success_rate", 1.0 if treatment else 0.0),
        ("population_recovery_attempts", 2 if treatment else 0),
        ("population_recovery_completions", 2 if treatment else 0),
        ("population_recovered", 4 if treatment else 0),
        ("tactical_actions", impact_values["tactical"]),
        ("production_projected_completion_eta_turns", 6.0 if treatment else 0.0),
        ("production_projected_score_value", 1.0 if treatment else 0.0),
        ("production_projected_unit_completions", 10.0 if treatment else 0.0),
        ("production_projected_unit_score_progress", 1.0 if treatment else 0.0),
        ("production_guaranteed_unit_score_points", 1.0 if treatment else 0.0),
        ("production_batch_incremental_unit_completions",
         10.0 if treatment else 0.0),
        ("production_batch_guaranteed_unit_score_points",
         1.0 if treatment else 0.0),
        ("production_projected_build_cost", 40.0 if treatment else 0.0),
        ("production_projected_shield_surplus", 5.0 if treatment else 0.0),
        ("production_projected_pop_cost", 0.0),
        ("production_projection_ruleset_source_rate", 1.0 if treatment else 0.0),
        ("production_projected_population_ready_eta_turns",
         4.0 if treatment else 0.0),
        ("production_projected_settlement_eta_turns", 9.0 if treatment else 0.0),
        ("production_projected_settlement_runway_turns",
         15.0 if treatment else 0.0),
        ("production_projected_founder_route_eta_turns",
         3.0 if treatment else 0.0),
        ("production_projection_route_observed_source_rate",
         1.0 if treatment else 0.0),
        ("production_projection_growth_ruleset_source_rate",
         1.0 if treatment else 0.0),
        ("production_founder_deficit_before", 1.0 if treatment else 0.0),
        ("production_repurpose_avoided_population_cost",
         4.0 if treatment else 0.0),
        ("production_repurpose_discarded_shield_stock",
         12.0 if treatment else 0.0),
        ("production_repurpose_target_completion_rate",
         1.0 if treatment else 0.0),
        ("production_preexpansion_sequence_settlement_eta_turns",
         20.0 if treatment else 0.0),
        ("production_preexpansion_sequence_settlement_runway_turns",
         10.0 if treatment else 0.0),
        ("score_component_citizens_turn_n", 2 + (1 if treatment else 0)),
        ("score_component_technology_turn_n", 2.0),
        ("score_component_residual_turn_n", score_shift - 4.0),
        ("score_component_citizen_delta", 1 if treatment else 0),
        ("score_component_technology_delta", 0.0),
        ("score_gain", score_shift),
    ))
    if context.capabilities["scheduler"]:
        metrics.append(("plan_eta_absolute_error_turns", randomizer.choice((0, 0, 1))))
    if context.capabilities["uncertain_beliefs"]:
        metrics.extend((
            ("calibration_absolute_error", randomizer.uniform(0.02, 0.14)),
            ("replan_latency_ms", randomizer.uniform(5, 60)),
        ))
    if track == "induction":
        sequence = manifest["sequence"]
        learned = 0.50 + (0.015 * sequence if context.capabilities["uncertain_beliefs"] else 0)
        metrics.append(("induction_prediction_accuracy", min(0.9, learned)))
    metric_parent = result["event_id"]
    if context.capabilities["uncertain_beliefs"] and track == "main":
        # Compact CI calibration population. Release evidence comes from the
        # engine-live backend's packet-visible observations and post-game truth.
        sample = _metric(
            writer, manifest["turn_limit"], metric_parent,
            "belief_calibration_sample", 0.95, condition, track,
            seed=seed, sequence=manifest.get("sequence", 0),
            truth=int(randomizer.random() < 0.9),
            opponent=manifest["opponent"]["id"], atom_id="representative-{}".format(seed))
        metric_parent = sample["event_id"]
    for name, value in metrics:
        event = _metric(writer, manifest["turn_limit"], metric_parent, name, value, condition, track,
                        seed=seed, sequence=manifest.get("sequence", 0))
        metric_parent = event["event_id"]
    writer.emit("run_completed", manifest["turn_limit"], {
        "status": "completed", "summary": {
            "opponent_score": opponent_score,
            "outcome_definition": "fixed_horizon_score_lead",
            "score": score, "score_lead": won,
            "score_margin": score_margin, "won": won}},
        caused_by=[metric_parent])
    return {
        "capability_audit": context.audit(), "completed": True,
        "infrastructure_failure": False,
        # The compact backend has no packet assembly. Both paired arms are
        # deliberately assigned the same seed-grounded initial state identity
        # so aggregate fidelity gates exercise the same contract as engine-live.
        "initial_state_fingerprint": structural_hash([
            "representative-initial-state", seed]),
        "loss": not won,
    }
