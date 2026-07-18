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
    parent = root["event_id"]
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
    score = 100.0 + score_shift + randomizer.uniform(-12, 12)
    win_probability = (0.30, 0.47, 0.51, 0.49, 0.55)[index]
    won = randomizer.random() < win_probability
    latency = (5000, 300, 500, 650, 850)[index] + randomizer.uniform(0, 120)
    metrics = [
        ("game_win", int(won)), ("score_turn_n", score),
        ("engine_rejected_action_rate", 0.0),
        ("confabulation_write_through", 0.0), ("loop_latency_ms", latency),
    ]
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
        "status": "completed", "summary": {"score": score, "won": won}},
        caused_by=[metric_parent])
    return {"capability_audit": context.audit(), "completed": True,
            "infrastructure_failure": False, "loss": not won}
