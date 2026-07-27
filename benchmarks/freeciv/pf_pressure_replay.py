"""Read-only PF decision replay over versioned FreeCiv event artifacts."""

import copy
import hashlib
import json
import os
from collections import Counter
from types import SimpleNamespace

from freeciv_agent.events.schema import canonical_json_bytes, structural_hash
from freeciv_agent.planning import GroundedImpactPlanner, ImpactCandidate
from freeciv_agent.pressure import ImpactPressureRanker, PressureConfig
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


def opportunity_rescore(scores, pressure):
    """Apply the current cross-goal cost and safety policy to recorded relief.

    This is deliberately a read-only counterfactual. It preserves the recorded
    pressure field, conductance, candidate set, and operation-value estimates;
    only the adapter's scheduling cost and lexicographic safety admissibility
    are recomputed.
    """
    scores = tuple(scores)
    candidates = [_candidate(score) for score in scores]
    if not scores or any(candidate is None for candidate in candidates):
        raise ValueError("opportunity rescore requires complete candidates")
    goal_by_operation = {}
    goal_utility_ceilings = {}
    for candidate in candidates:
        goal_name = ImpactPressureRanker.goal_for_category(
            candidate["category"])
        goal_by_operation[candidate["operation_id"]] = goal_name
        goal_utility_ceilings[goal_name] = max(
            goal_utility_ceilings.get(goal_name, 0.0),
            candidate["utility"])

    survival_goal_id = "pf-impact:survival"
    survival_goal = next((
        goal for goal in pressure.get("goals", ())
        if goal.get("goal_id") == survival_goal_id), None)
    survival_demand = 0.0
    if survival_goal is not None:
        survival_demand = float(pressure.get("dependency", {}).get(
            survival_goal_id, {}).get(
                survival_goal.get("target_atom_id"), 0.0))
    safety_active = bool(
        survival_demand > 0.0
        and goal_utility_ceilings.get("survival", 0.0) > 0.0)
    opportunity_ceiling = (
        goal_utility_ceilings["survival"] if safety_active else
        max(goal_utility_ceilings.values()))

    config = pressure.get("config", {})
    cost_weights = config.get("cost_weights", {})
    epsilon = float(config.get("cost_epsilon", 1e-9))
    rescored = []
    for score in scores:
        row = copy.deepcopy(score)
        operation = row["operation"]
        operation_id = operation["operation_id"]
        goal_name = goal_by_operation[operation_id]
        opportunity = max(
            0.0,
            opportunity_ceiling - goal_utility_ceilings[goal_name])
        operation["cost"]["opportunity"] = opportunity
        scalar_cost = sum(
            float(value) * float(cost_weights.get(name, 1.0))
            for name, value in operation["cost"].items())
        row["scalar_cost"] = scalar_cost
        if not bool(row.get("admissible")):
            row["priority"] = 0.0
        elif safety_active and goal_name != "survival":
            row["admissible"] = False
            row["reason"] = "safety_firewall"
            row["priority"] = 0.0
        else:
            row["priority"] = (
                float(row["value"])
                * float(operation.get("feasibility", 1.0))
                * float(operation.get("deadline_fit", 1.0))
                / (scalar_cost + epsilon)
                - float(operation.get("redundancy", 0.0))
                - float(operation.get("contradiction_risk", 0.0)))
        rescored.append(row)
    ordered = sorted(rescored, key=_pressure_key)
    selected = next(
        (row for row in ordered if row.get("admissible")), None)
    return {
        "goal_utility_ceilings": dict(sorted(
            goal_utility_ceilings.items())),
        "opportunity_ceiling": float(opportunity_ceiling),
        "safety_active": bool(safety_active),
        "scores": ordered,
        "selected_operation_id": (
            None if selected is None
            else selected["operation"]["operation_id"]),
    }


class _RecordedConductance(object):
    """Read-only conductance view for decision counterfactual replay."""

    def __init__(self, snapshot, direct_completion_floor):
        self._snapshot = copy.deepcopy(snapshot or {})
        configuration = self._snapshot.get("configuration", {})
        self.initial_conductance = (
            float(configuration.get("initial_conductance", 1.0))
            if direct_completion_floor else 0.0)

    def value(self, category):
        row = self._snapshot.get("routes", {}).get(str(category), {})
        return float(row.get(
            "conductance",
            self._snapshot.get("configuration", {}).get(
                "initial_conductance", 1.0)))

    def decision_snapshot(self):
        return copy.deepcopy(self._snapshot)


def _pressure_config(value):
    value = dict(value or {})
    if isinstance(value.get("cost_weights"), dict):
        value["cost_weights"] = tuple(sorted(
            (str(name), float(weight))
            for name, weight in value["cost_weights"].items()))
    return PressureConfig(**value)


def _recorded_goal_specs(pressure):
    """Recover adapter inputs from a complete pressure decision artifact."""
    dependency = pressure.get("dependency", {})
    specs = {}
    for goal in pressure.get("goals", ()):
        goal_id = str(goal["goal_id"])
        name = goal_id.rsplit(":", 1)[-1]
        utility = float(goal["utility"])
        urgency = float(goal["urgency"])
        commitment = float(goal["commitment"])
        demand = float(dependency.get(goal_id, {}).get(
            goal["target_atom_id"], 0.0))
        weight = utility * urgency * commitment
        gap = min(1.0, demand / weight) if weight > 0.0 else 0.0
        strength = max(
            0.0, min(1.0, float(goal["target_strength"]) - gap))
        context = tuple(goal.get("context", ()))
        specs[name] = (
            strength, utility, bool(goal.get("safety")),
            context[0] if context else "recorded:no-context")
    required = {"survival", "expansion", "score", "exploration"}
    if not required.issubset(set(specs)):
        raise ValueError(
            "direct completion replay requires the core grounded goals")
    return specs


def direct_completion_rescore(scores, pressure, conductance_state, turn):
    """Recompute one recorded decision with candidate-scoped direct optimism.

    Goal truth, candidates, utilities, learned conductance, and pressure
    configuration are recovered from the immutable event artifacts. The only
    changed input is whether a newly grounded direct completion receives the
    conductance state's initial prior instead of another context's learned
    category penalty.
    """
    candidates = []
    by_action = {}
    for score in scores:
        value = _candidate(score)
        payload = score.get("operation", {}).get("payload", {})
        if value is None:
            raise ValueError(
                "direct completion rescore requires complete candidates")
        candidate = ImpactCandidate(
            value["action"], value["category"], value["utility"],
            payload.get("rationale", "recorded grounded candidate"),
            payload.get("projection"))
        candidates.append(candidate)
        by_action[candidate.action_key] = value["operation_id"]
    if len(by_action) != len(candidates):
        raise ValueError(
            "direct completion rescore requires unique candidate actions")

    goals = pressure.get("goals", ())
    score_goal = next(
        goal for goal in goals
        if goal.get("goal_id") == "pf-impact:score")
    score_urgency = float(score_goal.get("urgency", 1.0))
    remaining = (
        max(1, int(round(1.0 / (score_urgency - 1.0))))
        if score_urgency > 1.0 else 1)
    horizon_turn = int(turn) + remaining
    specs = _recorded_goal_specs(pressure)
    snapshot = SimpleNamespace(turn=int(turn))
    config = _pressure_config(pressure.get("config"))

    results = {}
    for name, floor in (
            ("recorded_semantics", False),
            ("direct_completion_semantics", True)):
        ordered, artifact = ImpactPressureRanker(
            config, _RecordedConductance(
                conductance_state, direct_completion_floor=floor)).rank(
                    snapshot, candidates, expansion_city_target=1,
                    horizon_turn=horizon_turn,
                    _goal_specs_override=specs)
        selected = ordered[0]
        results[name] = {
            "category": selected.category,
            "operation_id": by_action[selected.action_key],
            "utility": float(selected.utility),
        }
        if name == "direct_completion_semantics":
            results["decision_routes"] = artifact[
                "conductance_state"].get("decision_routes", {})
    return results


def score_alignment_rescore(
        scores, pressure, conductance_state, turn,
        exploration_information_enabled=False,
        score_alignment_utility_tolerance=0.0):
    """Recompute a recorded decision under score-aligned PF semantics."""
    candidates = []
    by_action = {}
    for score in scores:
        value = _candidate(score)
        payload = score.get("operation", {}).get("payload", {})
        if value is None:
            raise ValueError(
                "score alignment rescore requires complete candidates")
        candidate = ImpactCandidate(
            value["action"], value["category"], value["utility"],
            payload.get("rationale", "recorded grounded candidate"),
            payload.get("projection"))
        candidates.append(candidate)
        by_action[candidate.action_key] = value["operation_id"]
    if len(by_action) != len(candidates):
        raise ValueError(
            "score alignment rescore requires unique candidate actions")

    goals = pressure.get("goals", ())
    score_goal = next(
        goal for goal in goals
        if goal.get("goal_id") == "pf-impact:score")
    score_urgency = float(score_goal.get("urgency", 1.0))
    remaining = (
        max(1, int(round(1.0 / (score_urgency - 1.0))))
        if score_urgency > 1.0 else 1)
    horizon_turn = int(turn) + remaining
    specs = _recorded_goal_specs(pressure)
    score_actionable = any(
        ImpactPressureRanker._guaranteed_horizon_score(candidate) > 0.0
        for candidate in candidates)
    specs["score"] = (
        0.0 if score_actionable else 1.0,
        specs["score"][1], specs["score"][2],
        ("authoritative:grounded-guaranteed-horizon-score-action"
         if score_actionable else
         "authoritative:no-grounded-score-action"))
    known_hut_actionable = any(
        candidate.category == "hut_exploration"
        for candidate in candidates)
    exploration_actionable = any(
        ImpactPressureRanker.goal_for_category(candidate.category)
        == "exploration" for candidate in candidates)
    if exploration_actionable:
        exploration_grounding = (
            "authoritative:grounded-known-hut-action"
            if known_hut_actionable else
            "authoritative:grounded-exploration-action"
            if exploration_information_enabled else
            "authoritative:no-information-gain-and-no-known-hut")
        specs["exploration"] = (
            (0.0 if known_hut_actionable
             or exploration_information_enabled else 1.0),
            specs["exploration"][1], specs["exploration"][2],
            exploration_grounding)

    snapshot = SimpleNamespace(turn=int(turn))
    ordered, artifact = ImpactPressureRanker(
        _pressure_config(pressure.get("config")),
        _RecordedConductance(
            conductance_state, direct_completion_floor=True),
        score_alignment=True,
        exploration_information_enabled=(
            exploration_information_enabled),
        score_alignment_utility_tolerance=(
            score_alignment_utility_tolerance)).rank(
                snapshot, candidates, expansion_city_target=1,
                horizon_turn=horizon_turn, _goal_specs_override=specs,
                _conservative_safety_replay=True)
    selected = ordered[0]
    return {
        "category": selected.category,
        "operation_id": by_action[selected.action_key],
        "schedule": artifact["schedule"],
        "utility": float(selected.utility),
    }


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


def opportunity_counterfactual_paths(
        paths, maximum_files=None, relative_to=None):
    """Rescore recorded decisions under current cross-goal scheduling."""
    files = discover_event_files(paths, maximum_files)
    if not files:
        raise ValueError("no events.jsonl files found")
    relative_to = (
        os.path.abspath(relative_to) if relative_to is not None else None)
    decisions = []
    source_set = []
    for path in files:
        display = (
            os.path.relpath(path, relative_to)
            if relative_to is not None else path)
        source_hash = _file_sha256(path)
        events = _load_events(path)
        pressure_by_id = dict(
            (event.get("payload", {}).get("pressure_id"),
             event.get("payload", {}))
            for event in events
            if event.get("type") == "pressure_propagated")
        for event in events:
            if event.get("type") != "operation_scored":
                continue
            payload = event.get("payload", {})
            pressure = pressure_by_id.get(payload.get("pressure_id"))
            scores = payload.get("scores")
            if pressure is None or not isinstance(scores, list) or not scores:
                continue
            candidates = [_candidate(score) for score in scores]
            if any(candidate is None for candidate in candidates):
                continue
            by_operation = dict(
                (candidate["operation_id"], candidate)
                for candidate in candidates)
            baseline = min(candidates, key=_baseline_key)
            recorded = by_operation.get(payload.get(
                "selected_operation_id"))
            rescored = opportunity_rescore(scores, pressure)
            counterfactual = by_operation.get(
                rescored["selected_operation_id"])
            if recorded is None or counterfactual is None:
                continue
            decisions.append({
                "baseline_category": baseline["category"],
                "baseline_operation_id": baseline["operation_id"],
                "baseline_utility": baseline["utility"],
                "counterfactual_category": counterfactual["category"],
                "counterfactual_operation_id": counterfactual[
                    "operation_id"],
                "counterfactual_utility": counterfactual["utility"],
                "decision_event_id": event.get("event_id"),
                "path": display,
                "recorded_category": recorded["category"],
                "recorded_operation_id": recorded["operation_id"],
                "recorded_utility": recorded["utility"],
                "safety_active": rescored["safety_active"],
                "turn": int(event.get("turn", 0)),
            })
        after_hash = _file_sha256(path)
        if after_hash != source_hash:
            raise RuntimeError(
                "counterfactual source changed while it was being read")
        source_set.append({"path": display, "sha256": source_hash})

    recorded_changed = [
        row for row in decisions
        if row["recorded_operation_id"] != row[
            "counterfactual_operation_id"]]
    baseline_recorded = [
        row for row in decisions
        if row["baseline_operation_id"] != row["recorded_operation_id"]]
    baseline_counterfactual = [
        row for row in decisions
        if row["baseline_operation_id"] != row[
            "counterfactual_operation_id"]]
    recorded_transitions = Counter(
        "{} -> {}".format(
            row["baseline_category"], row["recorded_category"])
        for row in baseline_recorded)
    counterfactual_transitions = Counter(
        "{} -> {}".format(
            row["baseline_category"], row["counterfactual_category"])
        for row in baseline_counterfactual)
    safe_rows = [row for row in decisions if not row["safety_active"]]
    safety_rows = [row for row in decisions if row["safety_active"]]

    def displacements(rows, prefix, selected):
        return sum(
            row["baseline_category"] == prefix
            and row[selected] != prefix
            for row in rows)

    value = {
        "baseline_to_counterfactual_changed_decisions": len(
            baseline_counterfactual),
        "baseline_to_counterfactual_change_rate": (
            float(len(baseline_counterfactual)) / len(decisions)
            if decisions else None),
        "baseline_to_counterfactual_transitions": dict(sorted(
            counterfactual_transitions.items())),
        "baseline_to_recorded_changed_decisions": len(baseline_recorded),
        "baseline_to_recorded_transitions": dict(sorted(
            recorded_transitions.items())),
        "counterfactual_changed_from_recorded": len(recorded_changed),
        "counterfactual_city_founding_displacements": displacements(
            decisions, "city_founding", "counterfactual_category"),
        "counterfactual_hut_displacements": displacements(
            decisions, "hut_exploration", "counterfactual_category"),
        "counterfactual_safe_city_founding_displacements": displacements(
            safe_rows, "city_founding", "counterfactual_category"),
        "counterfactual_safe_hut_displacements": displacements(
            safe_rows, "hut_exploration", "counterfactual_category"),
        "counterfactual_utility_regret": sum(
            row["baseline_utility"] - row["counterfactual_utility"]
            for row in decisions),
        "decisions": decisions,
        "files_scanned": len(files),
        "limitations": [
            "Counterfactual replay holds the recorded pressure field, conductance, candidates, and operation-value estimates fixed.",
            "It measures scheduling semantics only and cannot measure downstream engine score.",
            "Results describe the supplied traces and are not a gameplay win-rate claim.",
        ],
        "mode": "cross-goal-opportunity-cost-counterfactual",
        "recorded_city_founding_displacements": displacements(
            decisions, "city_founding", "recorded_category"),
        "recorded_hut_displacements": displacements(
            decisions, "hut_exploration", "recorded_category"),
        "recorded_safe_city_founding_displacements": displacements(
            safe_rows, "city_founding", "recorded_category"),
        "recorded_safe_hut_displacements": displacements(
            safe_rows, "hut_exploration", "recorded_category"),
        "recorded_utility_regret": sum(
            row["baseline_utility"] - row["recorded_utility"]
            for row in decisions),
        "safety_active_decisions": len(safety_rows),
        "schema_version": REPLAY_SCHEMA_VERSION,
        "source_set": source_set,
        "source_set_hash": structural_hash(source_set),
        "sources_unchanged": True,
        "total_decisions": len(decisions),
    }
    value["artifact_hash"] = structural_hash(value)
    return value


def direct_completion_counterfactual_paths(
        paths, maximum_files=None, relative_to=None):
    """Replay candidate-scoped direct-completion conductance over event files."""
    files = discover_event_files(paths, maximum_files)
    if not files:
        raise ValueError("no events.jsonl files found")
    relative_to = (
        os.path.abspath(relative_to) if relative_to is not None else None)
    decisions = []
    integrity_failures = 0
    source_set = []
    for path in files:
        display = (
            os.path.relpath(path, relative_to)
            if relative_to is not None else path)
        source_hash = _file_sha256(path)
        events = _load_events(path)
        pressure_by_id = dict(
            (event.get("payload", {}).get("pressure_id"),
             event.get("payload", {}))
            for event in events
            if event.get("type") == "pressure_propagated")
        for event in events:
            if event.get("type") != "operation_scored":
                continue
            payload = event.get("payload", {})
            pressure = pressure_by_id.get(payload.get("pressure_id"))
            scores = payload.get("scores")
            if pressure is None or not isinstance(scores, list) or not scores:
                continue
            rescored = direct_completion_rescore(
                scores, pressure, pressure.get("conductance_state"),
                event.get("turn", 0))
            recorded_id = payload.get("selected_operation_id")
            old = rescored["recorded_semantics"]
            revised = rescored["direct_completion_semantics"]
            integrity_passed = old["operation_id"] == recorded_id
            if not integrity_passed:
                integrity_failures += 1
            changed = old["operation_id"] != revised["operation_id"]
            direct_route = rescored["decision_routes"].get(
                revised["category"], {})
            decisions.append({
                "changed": changed,
                "decision_event_id": event.get("event_id"),
                "direct_completion_source": direct_route.get(
                    "direct_completion_source"),
                "integrity_passed": integrity_passed,
                "path": display,
                "recorded_category": old["category"],
                "recorded_operation_id": old["operation_id"],
                "recorded_utility": old["utility"],
                "revised_category": revised["category"],
                "revised_operation_id": revised["operation_id"],
                "revised_utility": revised["utility"],
                "turn": int(event.get("turn", 0)),
            })
        if _file_sha256(path) != source_hash:
            raise RuntimeError(
                "counterfactual source changed while it was being read")
        source_set.append({"path": display, "sha256": source_hash})

    changed = [row for row in decisions if row["changed"]]
    transitions = Counter(
        "{} -> {}".format(
            row["recorded_category"], row["revised_category"])
        for row in changed)
    value = {
        "changed_decisions": len(changed),
        "changed_rate": (
            float(len(changed)) / len(decisions) if decisions else None),
        "decisions": decisions,
        "files_scanned": len(files),
        "integrity_failures": int(integrity_failures),
        "limitations": [
            "Counterfactual replay holds grounded goals, candidates, utilities, learned conductance, and pressure configuration fixed.",
            "It changes only decision-scoped conductance for a newly legal city or exact known-hut completion.",
            "It cannot measure downstream engine score and is not a gameplay win-rate claim.",
        ],
        "mode": "candidate-scoped-direct-completion-counterfactual",
        "schema_version": REPLAY_SCHEMA_VERSION,
        "source_set": source_set,
        "source_set_hash": structural_hash(source_set),
        "sources_unchanged": True,
        "total_decisions": len(decisions),
        "transitions": dict(sorted(transitions.items())),
        "utility_delta": sum(
            row["revised_utility"] - row["recorded_utility"]
            for row in changed),
    }
    value["artifact_hash"] = structural_hash(value)
    return value


def score_alignment_counterfactual_paths(
        paths, maximum_files=None, relative_to=None,
        exploration_information_enabled=False,
        score_alignment_utility_tolerance=0.0):
    """Replay score alignment over immutable grounded treatment decisions."""
    files = discover_event_files(paths, maximum_files)
    if not files:
        raise ValueError("no events.jsonl files found")
    relative_to = (
        os.path.abspath(relative_to) if relative_to is not None else None)
    decisions = []
    source_set = []
    for path in files:
        display = (
            os.path.relpath(path, relative_to)
            if relative_to is not None else path)
        source_hash = _file_sha256(path)
        events = _load_events(path)
        pressure_by_id = dict(
            (event.get("payload", {}).get("pressure_id"),
             event.get("payload", {}))
            for event in events
            if event.get("type") == "pressure_propagated")
        for event in events:
            if event.get("type") != "operation_scored":
                continue
            payload = event.get("payload", {})
            pressure = pressure_by_id.get(payload.get("pressure_id"))
            scores = payload.get("scores")
            if pressure is None or not isinstance(scores, list) or not scores:
                continue
            candidates = [_candidate(score) for score in scores]
            if any(candidate is None for candidate in candidates):
                continue
            by_operation = dict(
                (candidate["operation_id"], candidate)
                for candidate in candidates)
            baseline = min(candidates, key=_baseline_key)
            recorded = by_operation.get(payload.get(
                "selected_operation_id"))
            rescored = score_alignment_rescore(
                scores, pressure, pressure.get("conductance_state"),
                event.get("turn", 0),
                exploration_information_enabled=(
                    exploration_information_enabled),
                score_alignment_utility_tolerance=(
                    score_alignment_utility_tolerance))
            aligned = by_operation.get(rescored["operation_id"])
            if recorded is None or aligned is None:
                continue
            reasons = Counter(
                row.get("reason") for row in rescored["schedule"]["scores"]
                if row.get("reason") in (
                    "score_alignment_guard",
                    "score_alignment_deadline"))
            decisions.append({
                "aligned_category": aligned["category"],
                "aligned_operation_id": aligned["operation_id"],
                "aligned_utility": aligned["utility"],
                "baseline_category": baseline["category"],
                "baseline_operation_id": baseline["operation_id"],
                "baseline_utility": baseline["utility"],
                "changed_from_recorded": (
                    aligned["operation_id"] != recorded["operation_id"]),
                "decision_event_id": event.get("event_id"),
                "deadline_rejections": int(
                    reasons["score_alignment_deadline"]),
                "guard_rejections": int(
                    reasons["score_alignment_guard"]),
                "path": display,
                "recorded_category": recorded["category"],
                "recorded_operation_id": recorded["operation_id"],
                "recorded_utility": recorded["utility"],
                "turn": int(event.get("turn", 0)),
            })
        if _file_sha256(path) != source_hash:
            raise RuntimeError(
                "counterfactual source changed while it was read")
        source_set.append({"path": display, "sha256": source_hash})

    changed = [row for row in decisions if row["changed_from_recorded"]]
    baseline_aligned = [
        row for row in decisions
        if row["baseline_operation_id"] != row["aligned_operation_id"]]
    transitions = Counter(
        "{} -> {}".format(
            row["recorded_category"], row["aligned_category"])
        for row in changed)
    baseline_transitions = Counter(
        "{} -> {}".format(
            row["baseline_category"], row["aligned_category"])
        for row in baseline_aligned)
    recorded_utility_regret = sum(
        row["baseline_utility"] - row["recorded_utility"]
        for row in decisions)
    aligned_utility_regret = sum(
        row["baseline_utility"] - row["aligned_utility"]
        for row in decisions)
    value = {
        "aligned_changed_from_baseline": len(baseline_aligned),
        "aligned_decision_change_rate": (
            float(len(baseline_aligned)) / len(decisions)
            if decisions else None),
        "aligned_transitions_from_baseline": dict(sorted(
            baseline_transitions.items())),
        "aligned_utility_regret": aligned_utility_regret,
        "changed_from_recorded": len(changed),
        "changed_from_recorded_rate": (
            float(len(changed)) / len(decisions)
            if decisions else None),
        "decisions": decisions,
        "deadline_rejections": sum(
            row["deadline_rejections"] for row in decisions),
        "files_scanned": len(files),
        "guard_rejections": sum(
            row["guard_rejections"] for row in decisions),
        "limitations": [
            "Counterfactual replay holds grounded candidates, utilities, learned conductance, and authoritative survival and expansion state fixed.",
            "It applies score-aligned goal grounding, category cost, horizon guards, the declared exploration setting, and utility tolerance locally; recorded artifacts do not retain enough actor geometry to replay the new threat-target binding, so existing survival candidates remain conservatively eligible.",
            "Later engine state may diverge after the first changed action; this is not a gameplay score or win-rate claim.",
        ],
        "mode": "score-alignment-counterfactual",
        "policy": {
            "exploration_information_enabled": bool(
                exploration_information_enabled),
            "score_alignment_utility_tolerance": float(
                score_alignment_utility_tolerance),
        },
        "recorded_utility_regret": recorded_utility_regret,
        "schema_version": REPLAY_SCHEMA_VERSION,
        "source_set": source_set,
        "source_set_hash": structural_hash(source_set),
        "sources_unchanged": True,
        "total_decisions": len(decisions),
        "transitions": dict(sorted(transitions.items())),
        "utility_regret_reduction": (
            recorded_utility_regret - aligned_utility_regret),
        "utility_regret_reduction_rate": (
            (recorded_utility_regret - aligned_utility_regret)
            / recorded_utility_regret
            if recorded_utility_regret else None),
    }
    value["artifact_hash"] = structural_hash(value)
    return value


def replay_snapshot_file(path, display_path=None, policy=None):
    """Run pressure off/on over one byte-real snapshot without execution."""
    path = os.path.abspath(path)
    source_hash = _file_sha256(path)
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    # Captures made before the game starts can predate authoritative map
    # projection entirely.  They are useful as explicit no-decision controls,
    # but must not weaken the live ProxyStateDTO contract for playable turns.
    # Normalize only the byte-real, empty turn-zero shape in the replay copy.
    replay_raw = raw
    if (
            raw.get("turn") == 0
            and raw.get("map") == {}
            and not raw.get("cities")
            and not raw.get("units")):
        replay_raw = dict(raw)
        replay_raw["map"] = {
            "height": 1, "tiles": [], "visibility": [], "width": 1}
    snapshot = ProxyStateDTO.parse(
        "pf-snapshot-replay", 1, replay_raw).to_snapshot()
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
