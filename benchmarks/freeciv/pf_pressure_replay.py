"""Read-only PF decision replay over versioned FreeCiv event artifacts."""

import hashlib
import json
import os
from collections import Counter

from freeciv_agent.events.schema import canonical_json_bytes, structural_hash
from freeciv_agent.planning import GroundedImpactPlanner
from freeciv_agent.state import ProxyStateDTO


REPLAY_SCHEMA_VERSION = "1.0"


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _load_events(path):
    events = []
    with open(path, encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise ValueError(
                    "{}:{} is not valid JSON: {}".format(
                        path, line_number, exc))
            if not isinstance(event, dict):
                raise ValueError(
                    "{}:{} event must be an object".format(path, line_number))
            events.append(event)
    return tuple(events)


def _candidate(score):
    operation = score.get("operation")
    payload = operation.get("payload") if isinstance(operation, dict) else None
    if not isinstance(payload, dict):
        return None
    action = payload.get("action")
    category = payload.get("category")
    utility = payload.get("utility")
    if (not isinstance(action, dict) or not isinstance(category, str)
            or isinstance(utility, bool)
            or not isinstance(utility, (int, float))):
        return None
    return {
        "action": action,
        "category": category,
        "operation_id": operation.get("operation_id"),
        "utility": float(utility),
    }


def _baseline_key(candidate):
    return (
        -candidate["utility"], candidate["category"],
        canonical_json_bytes(candidate["action"]),
        candidate["operation_id"],
    )


def _pressure_key(score):
    return (
        not bool(score.get("admissible")),
        -float(score.get("priority", float("-inf"))),
        score.get("operation", {}).get("operation_id", ""),
    )


def _schedule_hash(operation_payload, pressure_payload):
    value = {
        "allocations": operation_payload["allocations"],
        "pressure_hash": pressure_payload["result_hash"],
        "scores": operation_payload["scores"],
        "selected_operation_id": operation_payload[
            "selected_operation_id"],
        "solver_identity": operation_payload["solver_identity"],
    }
    return structural_hash(value)


def _plan_action_for(events, decision_event_id):
    children = [
        event for event in events
        if event.get("type") == "plan_created"
        and decision_event_id in event.get("caused_by", ())
    ]
    if not children:
        return None
    if len(children) != 1:
        return "ambiguous"
    steps = children[0].get("payload", {}).get(
        "plan", {}).get("steps", ())
    if not steps:
        return "missing"
    return steps[0].get("target")


def replay_event_file(path, display_path=None):
    """Replay one file without mutating it or importing engine state."""
    path = os.path.abspath(path)
    source_hash = _file_sha256(path)
    events = _load_events(path)
    pressure_by_id = {}
    for event in events:
        if event.get("type") == "pressure_propagated":
            payload = event.get("payload", {})
            pressure_id = payload.get("pressure_id")
            if pressure_id:
                pressure_by_id[pressure_id] = payload
    operation_events = [
        event for event in events if event.get("type") == "operation_scored"]
    decisions = []
    invalid_reasons = Counter()
    for event in operation_events:
        payload = event.get("payload", {})
        pressure = pressure_by_id.get(payload.get("pressure_id"))
        if pressure is None:
            invalid_reasons["missing_pressure_artifact"] += 1
            continue
        scores = payload.get("scores")
        if not isinstance(scores, list) or not scores:
            invalid_reasons["missing_operation_scores"] += 1
            continue
        candidates = [_candidate(score) for score in scores]
        if any(candidate is None for candidate in candidates):
            invalid_reasons["incomplete_candidate_payload"] += 1
            continue
        if any(not candidate["operation_id"] for candidate in candidates):
            invalid_reasons["missing_operation_id"] += 1
            continue
        baseline = min(candidates, key=_baseline_key)
        pressure_scores = sorted(scores, key=_pressure_key)
        recomputed = next(
            (score for score in pressure_scores if score.get("admissible")),
            None)
        recomputed_id = (
            None if recomputed is None
            else recomputed["operation"]["operation_id"])
        recorded_id = payload.get("selected_operation_id")
        candidate_by_id = dict(
            (candidate["operation_id"], candidate)
            for candidate in candidates)
        recorded_candidate = candidate_by_id.get(recorded_id)
        if recorded_candidate is None:
            invalid_reasons["selected_operation_missing"] += 1
            continue
        schedule_hash_matches = (
            _schedule_hash(payload, pressure)
            == payload.get("structural_hash"))
        selection_matches = recorded_id == recomputed_id
        plan_action = _plan_action_for(events, event.get("event_id"))
        plan_matches = (
            None if plan_action is None
            else plan_action == recorded_candidate["action"])
        decisions.append({
            "baseline_category": baseline["category"],
            "baseline_operation_id": baseline["operation_id"],
            "baseline_utility": baseline["utility"],
            "candidate_count": len(candidates),
            "changed": baseline["operation_id"] != recorded_id,
            "decision_event_id": event.get("event_id"),
            "integrity_passed": bool(
                schedule_hash_matches and selection_matches
                and plan_matches is not False),
            "plan_action_matches": plan_matches,
            "pressure_category": recorded_candidate["category"],
            "pressure_operation_id": recorded_id,
            "pressure_utility": recorded_candidate["utility"],
            "schedule_hash_matches": schedule_hash_matches,
            "selection_matches": selection_matches,
            "turn": int(event.get("turn", 0)),
            "utility_delta": (
                recorded_candidate["utility"] - baseline["utility"]),
        })
    if not operation_events:
        eligibility = "audit_only"
        reason = "legacy_missing_operation_scored"
    elif not decisions:
        eligibility = "audit_only"
        reason = (
            sorted(invalid_reasons)[0]
            if invalid_reasons else "no_replayable_decisions")
    else:
        eligibility = "exact_candidate_replay"
        reason = None
    after_hash = _file_sha256(path)
    if after_hash != source_hash:
        raise RuntimeError("replay source changed while it was being read")
    return {
        "decisions": decisions,
        "eligibility": eligibility,
        "events": len(events),
        "game_ids": sorted(set(
            str(event.get("game_id")) for event in events
            if event.get("game_id") is not None)),
        "invalid_decision_reasons": dict(sorted(invalid_reasons.items())),
        "path": display_path or path,
        "reason": reason,
        "source_sha256": source_hash,
        "source_unchanged": True,
    }


def discover_event_files(paths, maximum_files=None):
    files = []
    for value in paths:
        path = os.path.abspath(value)
        if os.path.isfile(path):
            files.append(path)
        elif os.path.isdir(path):
            for root, _, names in os.walk(path):
                if "events.jsonl" in names:
                    files.append(os.path.join(root, "events.jsonl"))
        else:
            raise ValueError("replay input does not exist: {}".format(value))
    files = sorted(set(files))
    if maximum_files is not None:
        if isinstance(maximum_files, bool) or int(maximum_files) < 1:
            raise ValueError("maximum_files must be positive")
        files = files[:int(maximum_files)]
    return tuple(files)


def replay_paths(paths, maximum_files=None, relative_to=None):
    files = discover_event_files(paths, maximum_files)
    if not files:
        raise ValueError("no events.jsonl files found")
    relative_to = (
        os.path.abspath(relative_to) if relative_to is not None else None)
    rows = []
    for path in files:
        display = (
            os.path.relpath(path, relative_to)
            if relative_to is not None else path)
        rows.append(replay_event_file(path, display))
    decisions = [
        decision for row in rows for decision in row["decisions"]]
    changed = sum(bool(row["changed"]) for row in decisions)
    integrity_failures = sum(
        not bool(row["integrity_passed"]) for row in decisions)
    eligibility = Counter(row["eligibility"] for row in rows)
    reasons = Counter(
        row["reason"] for row in rows if row["reason"] is not None)
    source_set = [
        {"path": row["path"], "sha256": row["source_sha256"]}
        for row in rows]
    value = {
        "audit_only_files": int(eligibility["audit_only"]),
        "changed_decisions": int(changed),
        "decision_change_rate": (
            float(changed) / len(decisions) if decisions else None),
        "decisions": decisions,
        "exact_replay_files": int(
            eligibility["exact_candidate_replay"]),
        "files_scanned": len(rows),
        "integrity_failures": int(integrity_failures),
        "limitations": [
            "Legacy snapshots retain legal-action digests but not full legal-action sets.",
            "Exact replay compares the recorded grounded candidate set; it does not recreate omitted candidates.",
            "Replay results are diagnostic and do not establish a gameplay score or win-rate claim.",
        ],
        "mode": "recorded-grounded-candidate-selection-replay",
        "reasons": dict(sorted(reasons.items())),
        "schema_version": REPLAY_SCHEMA_VERSION,
        "source_set": source_set,
        "source_set_hash": structural_hash(source_set),
        "sources_unchanged": all(row["source_unchanged"] for row in rows),
        "total_decisions": len(decisions),
    }
    value["artifact_hash"] = structural_hash(value)
    return value


def replay_snapshot_file(path, display_path=None, policy=None):
    """Run pressure off/on over one byte-real snapshot without execution."""
    path = os.path.abspath(path)
    source_hash = _file_sha256(path)
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    snapshot = ProxyStateDTO.parse(
        "pf-snapshot-replay", 1, raw).to_snapshot()
    snapshot_before = snapshot.event_payload()
    policy = dict(policy or {})
    forbidden = set(policy) & {
        "pressure_enabled", "pressure_learning_enabled"}
    if forbidden:
        raise ValueError(
            "snapshot replay owns pressure ablation keys: {}".format(
                sorted(forbidden)))
    baseline_policy = dict(policy, pressure_enabled=False)
    pressure_policy = dict(
        policy, pressure_enabled=True, pressure_learning_enabled=False)
    baseline_planner = GroundedImpactPlanner(baseline_policy)
    pressure_planner = GroundedImpactPlanner(pressure_policy)
    baseline_candidates = baseline_planner.candidates(snapshot)
    pressure_candidates = pressure_planner.candidates(snapshot)
    baseline_keys = tuple(row.action_key for row in baseline_candidates)
    pressure_keys = tuple(row.action_key for row in pressure_candidates)
    candidate_sets_match = baseline_keys == pressure_keys
    baseline = baseline_planner.plan(snapshot)
    pressure = pressure_planner.plan(snapshot)

    baseline_value = (
        None if baseline is None else baseline.candidate.to_dict())
    pressure_value = (
        None if pressure is None else pressure.candidate.to_dict())
    pressure_integrity = None
    if pressure is not None:
        schedule = pressure.pressure_artifact["schedule"]
        selected_id = schedule["selected_operation_id"]
        selected_rows = [
            row for row in schedule["scores"]
            if row["operation"]["operation_id"] == selected_id]
        pressure_integrity = bool(
            len(selected_rows) == 1
            and selected_rows[0]["operation"]["payload"]
            == pressure.candidate.to_dict()
            and schedule["structural_hash"] == structural_hash({
                key: value for key, value in schedule.items()
                if key != "structural_hash"
            }))
    snapshot_after = snapshot.event_payload()
    after_hash = _file_sha256(path)
    if after_hash != source_hash:
        raise RuntimeError(
            "snapshot replay source changed while it was being read")
    return {
        "baseline": baseline_value,
        "candidate_count": len(baseline_candidates),
        "candidate_sets_match": candidate_sets_match,
        "changed_action": (
            baseline_value is not None and pressure_value is not None
            and baseline_value["action"] != pressure_value["action"]),
        "changed_category": (
            baseline_value is not None and pressure_value is not None
            and baseline_value["category"] != pressure_value["category"]),
        "legal_action_count": len(snapshot.legal_action_json),
        "path": display_path or path,
        "planner_identity": GroundedImpactPlanner.SOLVER_IDENTITY,
        "policy": policy,
        "pressure": pressure_value,
        "pressure_integrity_passed": pressure_integrity,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_unchanged": snapshot_before == snapshot_after,
        "source_sha256": source_hash,
        "source_unchanged": source_hash == after_hash,
        "turn": snapshot.turn,
    }


def replay_snapshot_paths(paths, relative_to=None, policy=None):
    files = []
    for value in paths:
        path = os.path.abspath(value)
        if os.path.isfile(path):
            files.append(path)
        else:
            raise ValueError(
                "snapshot replay input must be a file: {}".format(value))
    files = sorted(set(files))
    if not files:
        raise ValueError("snapshot replay requires at least one input")
    relative_to = (
        os.path.abspath(relative_to) if relative_to is not None else None)
    rows = []
    for path in files:
        display = (
            os.path.relpath(path, relative_to)
            if relative_to is not None else path)
        rows.append(replay_snapshot_file(
            path, display_path=display, policy=policy))
    comparable = [
        row for row in rows
        if row["baseline"] is not None and row["pressure"] is not None]
    changed_actions = sum(row["changed_action"] for row in comparable)
    changed_categories = sum(row["changed_category"] for row in comparable)
    source_set = [
        {"path": row["path"], "sha256": row["source_sha256"]}
        for row in rows]
    value = {
        "changed_action_rate": (
            float(changed_actions) / len(comparable)
            if comparable else None),
        "changed_actions": int(changed_actions),
        "changed_categories": int(changed_categories),
        "comparable_snapshots": len(comparable),
        "limitations": [
            "Replay is execution-free and cannot measure downstream score.",
            "Captured samples without a ruleset IR use the planner's declared bounded fallbacks.",
            "Results describe these snapshots only and are not a gameplay win-rate claim.",
        ],
        "mode": "authoritative-legal-set-pressure-ablation",
        "schema_version": REPLAY_SCHEMA_VERSION,
        "snapshots": rows,
        "snapshots_scanned": len(rows),
        "source_set": source_set,
        "source_set_hash": structural_hash(source_set),
        "sources_unchanged": all(row["source_unchanged"] for row in rows),
        "states_unchanged": all(row["snapshot_unchanged"] for row in rows),
    }
    value["artifact_hash"] = structural_hash(value)
    return value
