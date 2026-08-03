"""Audit randomized FDAS alternative execution and delayed outcomes."""

import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.validator import validate_file
from freeciv_agent.planning import (
    DecisionEpisodeStore,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    EpisodeInductionOutcomeLabelStore,
    FdasCandidateChoiceSetStore,
)


AUDIT_IDENTITY = "fdas-randomized-alternative-live-audit/1.0"
ASSIGNMENT_IDENTITY = "fdas-safe-alternative-outcome-collection/4.0"
ASSIGNMENT_POLICY = "fdas-defense-nearest-score-randomized/4.0"
ASSIGNMENT_UNIT = "game-turn-exact-action-pair/1.0"
CLAIM_SCOPE = (
    "randomized bounded-alternative mechanics and selected-action outcomes; "
    "no candidate-value, gameplay, score, or win-rate claim")


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


def assignment_material(event):
    """Reconstruct the exact exogenous assignment unit from one event."""
    details = event.get("payload", {}).get("details", {})
    arms = dict((value.get("arm"), value) for value in details.get("arms", ()))
    if set(arms) != {"control", "treatment"}:
        raise ValueError("randomized assignment requires two named arms")
    config = details.get("config", {})
    return {
        "assignment_unit": ASSIGNMENT_UNIT,
        "control_action_key": arms["control"].get("action_key"),
        "experiment_id": details.get("experiment_id"),
        "game_id": event.get("game_id"),
        "policy_version": ASSIGNMENT_POLICY,
        "randomization_seed": config.get("randomization_seed"),
        "treatment_action_key": arms["treatment"].get("action_key"),
        "turn": event.get("turn"),
    }


def assignment_draw(event):
    material_hash = structural_hash(assignment_material(event))
    return material_hash, int(material_hash[:16], 16) / float(2 ** 64)


def _load_store(path, store_type):
    raw = _load(path)
    identity = raw.get("persistence_identity")
    store = store_type.load(path, identity or "missing-persistence-identity")
    return raw, store


def _ancestors(event_by_id, event_id):
    result = set()
    pending = list(event_by_id[event_id].get("caused_by", ()))
    while pending:
        parent = pending.pop()
        if parent in result:
            continue
        if parent not in event_by_id:
            raise ValueError("event causal parent is absent")
        result.add(parent)
        pending.extend(event_by_id[parent].get("caused_by", ()))
    return result


def _details(event):
    return event.get("payload", {}).get("details", {})


def _provenance_has(values, prefix, expected):
    return "{}{}".format(prefix, expected) in values


def audit_randomized_alternative_game(
        game_dir, expected_source_commit=None,
        expected_implementation_sha256=None, require_treatment=False):
    """Audit one engine-backed randomized alternative game fail-closed."""
    game_dir = os.path.abspath(game_dir)
    paths = dict((name, os.path.join(game_dir, name)) for name in (
        "events.jsonl",
        "fdas-candidate-choice-sets.json",
        "fdas-decision-episodes.json",
        "fdas-induction-outcome-labels.json",
        "manifest.json",
        "status.json",
    ))
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError(
            "missing randomized evidence: {}".format(", ".join(missing)))

    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    events = _events(paths["events.jsonl"])
    validation = validate_file(paths["events.jsonl"])
    episode_raw, episode_store = _load_store(
        paths["fdas-decision-episodes.json"], DecisionEpisodeStore)
    label_raw, label_store = _load_store(
        paths["fdas-induction-outcome-labels.json"],
        EpisodeInductionOutcomeLabelStore)
    choice_raw, choice_store = _load_store(
        paths["fdas-candidate-choice-sets.json"],
        FdasCandidateChoiceSetStore)
    event_by_id = dict((value["event_id"], value) for value in events)
    source = manifest.get("source", {})
    final_turn = status.get("final_global_observed_turn")

    assignment_events = tuple(
        value for value in events
        if (value.get("type") == "atomspace_authority_decision"
            and _details(value).get("identity") == ASSIGNMENT_IDENTITY
            and _details(value).get("status")
            == "eligible-randomized-diagnostic"))
    execution_events = tuple(
        value for value in events
        if (value.get("type") == "atomspace_authority_decision"
            and _details(value).get("assignment_executed") is True))

    assignment_rows = []
    assignment_errors = []
    for assignment in assignment_events:
        details = _details(assignment)
        arms = dict((value["arm"], value) for value in details.get("arms", ()))
        config = details.get("config", {})
        material = assignment_material(assignment)
        material_hash, draw = assignment_draw(assignment)
        probability = config.get("treatment_probability")
        expected_arm = (
            "treatment" if isinstance(probability, (int, float))
            and draw < probability else "control")
        expected_propensity = (
            probability if expected_arm == "treatment" else
            None if not isinstance(probability, (int, float)) else
            1.0 - probability)
        result_hash = details.get("result_hash")
        linked = tuple(
            value for value in execution_events
            if _details(value).get("assignment_result_hash") == result_hash)
        errors = []
        if details.get("policy_version") != ASSIGNMENT_POLICY:
            errors.append("assignment-policy-version-differs")
        if details.get("assignment_material_hash") != material_hash:
            errors.append("assignment-material-hash-differs")
        if details.get("assignment_draw") != draw:
            errors.append("assignment-draw-differs")
        if details.get("assigned_arm") != expected_arm:
            errors.append("assigned-arm-differs-from-draw")
        if details.get("selection_propensity") != expected_propensity:
            errors.append("selection-propensity-differs")
        if details.get("action_selection_changed") is not (
                expected_arm == "treatment"):
            errors.append("selection-change-semantics-differ")
        if (details.get("policy_authority") is not True
                or details.get("claim_eligible") is not False
                or details.get("truth_mutated") is not False
                or details.get("source_sink_flow_enabled") is not False):
            errors.append("assignment-authority-boundary-differs")
        if (set(material) != {
                "assignment_unit", "control_action_key", "experiment_id",
                "game_id", "policy_version", "randomization_seed",
                "treatment_action_key", "turn"}):
            errors.append("assignment-unit-fields-differ")
        if (set(arms) != {"control", "treatment"}
                or not set(arms["control"].get("resource_keys", ())).isdisjoint(
                    arms["treatment"].get("resource_keys", ()))
                or any(not arms[name].get(key) for name in arms for key in (
                    "commit_validation_hash", "pressure_evaluation_hash",
                    "resource_packet_artifact_hash"))):
            errors.append("assignment-arm-preflight-evidence-incomplete")
        if len(linked) != 1:
            errors.append("assignment-does-not-have-one-execution-link")

        episode = None
        label = None
        choice = None
        action_result = None
        execution = linked[0] if len(linked) == 1 else None
        if execution is not None:
            execution_details = _details(execution)
            episode = episode_store.get(execution_details.get("episode_id"))
            action_result = event_by_id.get(
                execution_details.get("execution_event_id"))
            if (execution_details.get("status")
                    != "execution-accepted-episode-linked"
                    or execution_details.get("assigned_arm") != expected_arm
                    or execution_details.get("selection_propensity")
                    != expected_propensity):
                errors.append("execution-link-semantics-differ")
            if (action_result is None
                    or action_result.get("type") != "action_result"
                    or action_result.get("payload", {}).get("status")
                    != "accepted"):
                errors.append("linked-action-result-is-not-accepted")
            elif (assignment["event_id"] not in _ancestors(
                    event_by_id, action_result["event_id"])
                    or action_result["event_id"] not in _ancestors(
                        event_by_id, execution["event_id"])):
                errors.append("assignment-action-execution-chain-is-broken")

        if episode is None:
            errors.append("linked-episode-is-missing")
        else:
            provenance = frozenset(episode.provenance_ids)
            assigned = arms.get(expected_arm, {})
            if (episode.action_key != assigned.get("action_key")
                    or episode.operation_id != assigned.get("operation_id")
                    or episode.execution_event_id
                    != _details(execution).get("execution_event_id")
                    or not _provenance_has(
                        provenance, "alternative-assignment-result:",
                        result_hash)
                    or not _provenance_has(
                        provenance, "assigned-arm:", expected_arm)
                    or not _provenance_has(
                        provenance, "selection-propensity:",
                        "{:.17g}".format(expected_propensity))
                    or "claim-eligible:false" not in provenance):
                errors.append("episode-assignment-provenance-differs")
            label = label_store.for_episode(
                episode.episode_id,
                DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET)
            choice = choice_store.for_episode(episode.episode_id)

        if label is None:
            errors.append("selected-episode-label-is-missing")
        elif (label.episode_digest != episode.immutable_digest
                or label.relief_turn != assignment["turn"]
                or label.relief_revision_id != episode.before_revision_id
                or label.due_turn != assignment["turn"] + 32
                or (label.status == "pending"
                    and isinstance(final_turn, int)
                    and final_turn >= label.due_turn)
                or (label.status == "observed"
                    and label.observed_turn < label.due_turn)):
            errors.append("selected-episode-label-lifecycle-differs")

        if choice is None:
            errors.append("selected-episode-choice-set-is-missing")
        else:
            selected = tuple(
                value for value in choice.choices
                if value.selection_role == "selected")
            if (len(selected) != 1
                    or selected[0].action_key != episode.action_key
                    or selected[0].operation_id != episode.operation_id
                    or choice.execution_status != "accepted"
                    or choice.execution_event_id != episode.execution_event_id
                    or any(value.selection_role != "nonselected-censored"
                           for value in choice.choices if value not in selected)):
                errors.append("candidate-choice-selection-link-differs")
            if label is not None and label.status == "observed" and (
                    choice.outcome_status != "observed"
                    or choice.outcome_label_id != label.label_id
                    or choice.observed_outcome is not label.outcome
                    or choice.observed_revision_id
                    != label.observed_revision_id):
                errors.append("candidate-choice-observed-outcome-differs")

        label_open_events = tuple(
            value for value in events
            if (value.get("type") == "episode_outcome_label_opened"
                and _details(value).get("label", {}).get("label_id")
                == (None if label is None else label.label_id)))
        if label is not None and len(label_open_events) != 1:
            errors.append("label-does-not-have-one-open-event")
        elif label_open_events and execution is not None:
            if execution["event_id"] not in _ancestors(
                    event_by_id, label_open_events[0]["event_id"]):
                errors.append("execution-label-causal-chain-is-broken")
        if label is not None and label.status == "observed":
            observed_events = tuple(
                value for value in events
                if (value.get("type") == "episode_outcome_label_observed"
                    and _details(value).get("label", {}).get("label_id")
                    == label.label_id))
            if len(observed_events) != 1:
                errors.append("observed-label-event-is-not-unique")
            elif label_open_events and label_open_events[0]["event_id"] not in (
                    _ancestors(event_by_id, observed_events[0]["event_id"])):
                errors.append("label-open-observe-causal-chain-is-broken")

        assignment_errors.extend(errors)
        assignment_rows.append({
            "assigned_arm": expected_arm,
            "assignment_draw": draw,
            "assignment_event_id": assignment["event_id"],
            "assignment_material": material,
            "assignment_material_hash": material_hash,
            "choice_set_id": None if choice is None else choice.choice_set_id,
            "episode_id": None if episode is None else episode.episode_id,
            "errors": errors,
            "label_due_turn": None if label is None else label.due_turn,
            "label_id": None if label is None else label.label_id,
            "label_outcome": None if label is None else label.outcome,
            "label_status": None if label is None else label.status,
            "selection_propensity": expected_propensity,
            "turn": assignment["turn"],
        })

    all_labels_have_selected_choices = all(
        choice_store.for_episode(value.episode_id) is not None
        for value in label_store.labels())
    store_hashes_valid = bool(
        not episode_store.quarantined
        and not label_store.quarantined
        and not choice_store.quarantined
        and episode_raw.get("store_digest") == episode_store.store_digest
        and label_raw.get("store_digest") == label_store.store_digest
        and choice_raw.get("store_digest") == choice_store.store_digest)
    gates = {
        "all_assignment_lifecycles_are_exact": not assignment_errors,
        "all_labels_belong_to_selected_choices": (
            all_labels_have_selected_choices),
        "event_ledger_valid_without_warnings": (
            validation.valid and not validation.warnings),
        "fixed_endpoint_completed_without_infrastructure_failure": bool(
            status.get("completed") is True
            and status.get("horizon_reached") is True
            and status.get("infrastructure_failure") is False),
        "manifest_is_exact_randomized_profile": bool(
            manifest.get("dependent_atomspace", {}).get("manifest_source")
            == "profile/fdas_manifest_defense_alternative_collection_"
               "randomized_pilot.json"),
        "one_or_more_randomized_assignments": bool(assignment_events),
        "source_is_clean_and_expected": bool(
            source.get("dirty") is False
            and (expected_source_commit is None
                 or source.get("commit") == expected_source_commit)
            and (expected_implementation_sha256 is None
                 or source.get("implementation_sha256")
                 == expected_implementation_sha256)),
        "status_counters_match_events": bool(
            status.get("fdas_alternative_collection_eligible")
            == len(assignment_events)
            and status.get("fdas_alternative_collection_execution_attempts")
            == len(execution_events)
            and status.get("fdas_alternative_collection_episode_links")
            == len(execution_events)
            and status.get("fdas_alternative_collection_execution_rejected")
            == 0),
        "stores_are_hash_valid_and_not_quarantined": store_hashes_valid,
        "treatment_exercised_when_required": bool(
            not require_treatment
            or any(value["assigned_arm"] == "treatment"
                   for value in assignment_rows)),
        "zero_rejected_engine_actions": status.get("rejected_actions") == 0,
    }
    semantic = {
        "assignment_errors": assignment_errors,
        "assignments": assignment_rows,
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": CLAIM_SCOPE,
        "event_errors": list(validation.errors),
        "event_warnings": list(validation.warnings),
        "game_id": manifest.get("game_id"),
        "gates": gates,
        "passed": all(gates.values()),
        "seed": manifest.get("seed"),
        "source": source,
        "status_counts": {
            "assignments": len(assignment_events),
            "control": sum(value["assigned_arm"] == "control"
                           for value in assignment_rows),
            "execution_links": len(execution_events),
            "labels_observed": sum(
                value["label_status"] == "observed"
                for value in assignment_rows),
            "labels_pending": sum(
                value["label_status"] == "pending"
                for value in assignment_rows),
            "negative_outcomes": sum(
                value["label_outcome"] is False
                for value in assignment_rows),
            "positive_outcomes": sum(
                value["label_outcome"] is True
                for value in assignment_rows),
            "treatment": sum(value["assigned_arm"] == "treatment"
                             for value in assignment_rows),
        },
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def audit_randomized_alternative_run(
        run_dir, expected_seeds=(), expected_source_commit=None,
        expected_implementation_sha256=None, require_treatment=False):
    """Audit all engine games in one frozen randomized run."""
    run_dir = os.path.abspath(run_dir)
    root = os.path.join(run_dir, "games", "main", "e_full_loop")
    game_dirs = tuple(sorted(
        os.path.join(root, directory)
        for directory in os.listdir(root)
        if os.path.isfile(os.path.join(root, directory, "status.json"))))
    games = tuple(audit_randomized_alternative_game(
        value,
        expected_source_commit=expected_source_commit,
        expected_implementation_sha256=expected_implementation_sha256,
        require_treatment=require_treatment)
        for value in game_dirs)
    observed_seeds = tuple(sorted(value["seed"] for value in games))
    expected_seeds = tuple(sorted(int(value) for value in expected_seeds))
    gates = {
        "all_game_gates_pass": bool(games) and all(
            value["passed"] for value in games),
        "exact_expected_seeds_completed": bool(
            not expected_seeds or observed_seeds == expected_seeds),
        "source_identity_is_identical": len({
            (value["source"].get("commit"),
             value["source"].get("implementation_sha256"))
            for value in games}) == 1,
    }
    assignments = tuple(
        row for game in games for row in game["assignments"])
    semantic = {
        "assignments": len(assignments),
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": CLAIM_SCOPE,
        "control_assignments": sum(
            value["assigned_arm"] == "control" for value in assignments),
        "games": list(games),
        "gates": gates,
        "negative_outcomes": sum(
            value["label_outcome"] is False for value in assignments),
        "passed": all(gates.values()),
        "positive_outcomes": sum(
            value["label_outcome"] is True for value in assignments),
        "treatment_assignments": sum(
            value["assigned_arm"] == "treatment" for value in assignments),
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic
