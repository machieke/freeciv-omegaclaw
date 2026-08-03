"""Audit randomized FDAS alternative execution and delayed outcomes."""

import json
import math
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.validator import validate_file
from freeciv_agent.planning import (
    DecisionEpisodeStore,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    EpisodeInductionOutcomeLabelStore,
    FdasCandidateChoiceSetStore,
)


AUDIT_IDENTITY = "fdas-randomized-alternative-live-audit/1.4"
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


def wilson_interval(successes, trials, z=1.959963984540054):
    """Return a bounded Wilson score interval for one Bernoulli arm."""
    successes = int(successes)
    trials = int(trials)
    z = float(z)
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("Wilson counts are invalid")
    if not math.isfinite(z) or z <= 0.0:
        raise ValueError("Wilson critical value is invalid")
    if trials == 0:
        return None
    rate = successes / float(trials)
    scale = 1.0 + z * z / trials
    center = (rate + z * z / (2.0 * trials)) / scale
    radius = z * math.sqrt(
        rate * (1.0 - rate) / trials
        + z * z / (4.0 * trials * trials)) / scale
    return (max(0.0, center - radius), min(1.0, center + radius))


def randomized_outcome_summary(assignments):
    """Summarize only due-turn-observed outcomes without imputing censoring."""
    assignments = tuple(assignments)
    arms = {}
    for arm in ("control", "treatment"):
        assigned = tuple(
            value for value in assignments if value["assigned_arm"] == arm)
        observed = tuple(
            value for value in assigned if value["label_status"] == "observed")
        positives = sum(value["label_outcome"] is True for value in observed)
        weights = tuple(
            1.0 / float(value["selection_propensity"])
            for value in observed)
        ess = (
            0.0 if not weights else
            sum(weights) ** 2 / sum(value * value for value in weights))
        interval = wilson_interval(positives, len(observed))
        arms[arm] = {
            "administratively_pending": sum(
                value["label_status"] == "pending"
                and value.get("label_due_by_endpoint") is False
                for value in assigned),
            "assigned": len(assigned),
            "assigned_games": len({
                value["game_id"] for value in assigned}),
            "effective_sample_size": ess,
            "observed": len(observed),
            "observed_games": len({
                value["game_id"] for value in observed}),
            "positive": positives,
            "rate": (
                None if not observed else positives / float(len(observed))),
            "wilson_interval": (
                None if interval is None else list(interval)),
        }
    control = arms["control"]
    treatment = arms["treatment"]
    if control["observed"] and treatment["observed"]:
        difference = treatment["rate"] - control["rate"]
        # Newcombe's score-interval construction without continuity
        # correction. It is intentionally conservative for a progression
        # gate and does not treat censored alternatives as negative.
        interval = (
            treatment["wilson_interval"][0]
            - control["wilson_interval"][1],
            treatment["wilson_interval"][1]
            - control["wilson_interval"][0],
        )
    else:
        difference, interval = None, None
    return {
        "arms": arms,
        "estimand": (
            "treatment-minus-control durable selected-actor city-defense "
            "probability among assignments with due turn observed"),
        "risk_difference": difference,
        "risk_difference_interval": (
            None if interval is None else list(interval)),
        "unresolved_after_due": sum(
            value["label_status"] == "pending"
            and value.get("label_due_by_endpoint") is True
            for value in assignments),
    }


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


def _incomplete_failed_game_report(
        game_dir, missing, expected_source_commit=None,
        expected_implementation_sha256=None):
    """Preserve an early failed game as an explicitly rejected audit row."""
    manifest_path = os.path.join(game_dir, "manifest.json")
    status_path = os.path.join(game_dir, "status.json")
    events_path = os.path.join(game_dir, "events.jsonl")
    manifest = _load(manifest_path) if os.path.isfile(manifest_path) else {}
    status = _load(status_path) if os.path.isfile(status_path) else {}
    events = _events(events_path) if os.path.isfile(events_path) else ()
    validation = validate_file(events_path) if os.path.isfile(
        events_path) else None
    source = manifest.get("source", {})
    assignment_events = tuple(
        value for value in events
        if (value.get("type") == "atomspace_authority_decision"
            and _details(value).get("identity") == ASSIGNMENT_IDENTITY
            and _details(value).get("status")
            == "eligible-randomized-diagnostic"))
    gates = {
        "complete_randomized_evidence_present": False,
        "event_ledger_valid_without_warnings": bool(
            validation is not None and validation.valid
            and not validation.warnings),
        "failed_game_is_preserved_not_completed": bool(
            status.get("completed") is False
            and status.get("infrastructure_failure") is True),
        "source_is_clean_and_expected": bool(
            source.get("dirty") is False
            and (expected_source_commit is None
                 or source.get("commit") == expected_source_commit)
            and (expected_implementation_sha256 is None
                 or source.get("implementation_sha256")
                 == expected_implementation_sha256)),
    }
    semantic = {
        "assignment_errors": [
            "missing-randomized-evidence:" + ",".join(sorted(missing))],
        "assignments": [],
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": CLAIM_SCOPE,
        "event_errors": (
            ["events-missing"] if validation is None
            else list(validation.errors)),
        "event_warnings": (
            [] if validation is None else list(validation.warnings)),
        "failure": {
            "error": status.get("error"),
            "infrastructure_failure": status.get("infrastructure_failure"),
            "missing_evidence": sorted(missing),
        },
        "game_id": manifest.get("game_id"),
        "gates": gates,
        "passed": False,
        "seed": manifest.get("seed"),
        "source": source,
        "status_counts": {
            "assignment_events_before_failure": len(assignment_events),
            "assignments": 0,
            "control": 0,
            "execution_links": 0,
            "labels_observed": 0,
            "labels_pending": 0,
            "negative_outcomes": 0,
            "positive_outcomes": 0,
            "treatment": 0,
        },
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def audit_randomized_alternative_game(
        game_dir, expected_source_commit=None,
        expected_implementation_sha256=None, require_treatment=False,
        require_catalog_reprojection=False, require_assignment=True,
        preserve_incomplete_failure=False):
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
        if preserve_incomplete_failure:
            return _incomplete_failed_game_report(
                game_dir, missing,
                expected_source_commit=expected_source_commit,
                expected_implementation_sha256=(
                    expected_implementation_sha256))
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
        if (isinstance(probability, bool)
                or not isinstance(probability, (int, float))
                or not 0.0 < probability < 1.0):
            errors.append("assignment-probability-is-invalid")
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
            execution_component_version = execution.get(
                "payload", {}).get("component_version")
            catalog_reprojected = execution_details.get(
                "authority_catalog_reprojected")
            episode = episode_store.get(execution_details.get("episode_id"))
            action_result = event_by_id.get(
                execution_details.get("execution_event_id"))
            if (execution_details.get("status")
                    != "execution-accepted-episode-linked"
                    or execution_details.get("assigned_arm") != expected_arm
                    or execution_details.get("selection_propensity")
                    != expected_propensity):
                errors.append("execution-link-semantics-differ")
            if (execution_component_version == "1.0"
                    and catalog_reprojected is not None):
                errors.append(
                    "legacy-execution-has-reprojection-provenance")
            elif (execution_component_version == "1.1"
                    and not isinstance(catalog_reprojected, bool)):
                errors.append(
                    "execution-reprojection-provenance-is-not-typed")
            elif execution_component_version not in ("1.0", "1.1"):
                errors.append("execution-component-version-is-unsupported")
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
            "game_id": manifest.get("game_id"),
            "label_due_turn": None if label is None else label.due_turn,
            "label_due_by_endpoint": bool(
                label is not None and isinstance(final_turn, int)
                and final_turn >= label.due_turn),
            "label_id": None if label is None else label.label_id,
            "label_outcome": None if label is None else label.outcome,
            "label_status": None if label is None else label.status,
            "authority_catalog_reprojected": (
                None if execution is None else _details(execution).get(
                    "authority_catalog_reprojected")),
            "execution_component_version": (
                None if execution is None else execution.get(
                    "payload", {}).get("component_version")),
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
        "one_or_more_randomized_assignments_when_required": bool(
            assignment_events or not require_assignment),
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
            == 0
            and (
                status.get(
                    "fdas_alternative_collection_authority_catalog_"
                    "reprojections") is None
                or status.get(
                    "fdas_alternative_collection_authority_catalog_"
                    "reprojections") == sum(
                        _details(value).get(
                            "authority_catalog_reprojected") is True
                        for value in execution_events))),
        "stores_are_hash_valid_and_not_quarantined": store_hashes_valid,
        "treatment_exercised_when_required": bool(
            not require_treatment
            or any(value["assigned_arm"] == "treatment"
                   for value in assignment_rows)),
        "catalog_reprojection_exercised_when_required": bool(
            not require_catalog_reprojection
            or any(value["authority_catalog_reprojected"] is True
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
            "authority_catalog_reprojections": sum(
                value["authority_catalog_reprojected"] is True
                for value in assignment_rows),
        },
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def audit_randomized_alternative_run(
        run_dir, expected_seeds=(), expected_source_commit=None,
        expected_implementation_sha256=None, require_treatment=False,
        minimum_observed_per_arm=0, allow_zero_assignment_games=False,
        required_treatment_seeds=(), required_catalog_reprojection_seeds=()):
    """Audit all engine games in one frozen randomized run."""
    run_dir = os.path.abspath(run_dir)
    root = os.path.join(run_dir, "games", "main", "e_full_loop")
    game_dirs = tuple(sorted(
        os.path.join(root, directory)
        for directory in os.listdir(root)
        if os.path.isfile(os.path.join(root, directory, "status.json"))))
    required_treatment_seeds = frozenset(
        int(value) for value in required_treatment_seeds)
    required_catalog_reprojection_seeds = frozenset(
        int(value) for value in required_catalog_reprojection_seeds)
    games = []
    for value in game_dirs:
        manifest_path = os.path.join(value, "manifest.json")
        manifest_seed = (
            _load(manifest_path).get("seed")
            if os.path.isfile(manifest_path) else None)
        games.append(audit_randomized_alternative_game(
            value,
            expected_source_commit=expected_source_commit,
            expected_implementation_sha256=expected_implementation_sha256,
            require_treatment=(
                require_treatment
                or manifest_seed in required_treatment_seeds),
            require_catalog_reprojection=(
                manifest_seed in required_catalog_reprojection_seeds),
            require_assignment=not allow_zero_assignment_games,
            preserve_incomplete_failure=True))
    games = tuple(games)
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
        "required_treatment_seeds_are_expected": (
            required_treatment_seeds.issubset(observed_seeds)),
        "required_catalog_reprojection_seeds_are_expected": (
            required_catalog_reprojection_seeds.issubset(observed_seeds)),
    }
    assignment_events = tuple(
        row for game in games for row in game["assignments"])
    assignments = tuple(
        row for game in games if game["passed"]
        for row in game["assignments"])
    outcome_summary = randomized_outcome_summary(assignments)
    minimum_observed_per_arm = int(minimum_observed_per_arm)
    if minimum_observed_per_arm < 0:
        raise ValueError("minimum observed outcomes per arm cannot be negative")
    gates["minimum_observed_effective_sample_and_game_clusters_per_arm"] = all(
        outcome_summary["arms"][arm]["effective_sample_size"]
        >= minimum_observed_per_arm
        and outcome_summary["arms"][arm]["observed_games"]
        >= minimum_observed_per_arm
        for arm in ("control", "treatment"))
    gates["zero_unresolved_outcomes_after_due_turn"] = (
        outcome_summary["unresolved_after_due"] == 0)
    semantic = {
        "assignments": len(assignments),
        "assignment_events": len(assignment_events),
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": CLAIM_SCOPE,
        "control_assignments": sum(
            value["assigned_arm"] == "control" for value in assignments),
        "games": list(games),
        "gates": gates,
        "invalid_game_assignment_events": (
            len(assignment_events) - len(assignments)),
        "negative_outcomes": sum(
            value["label_outcome"] is False for value in assignments),
        "outcome_summary": outcome_summary,
        "passed": all(gates.values()),
        "positive_outcomes": sum(
            value["label_outcome"] is True for value in assignments),
        "treatment_assignments": sum(
            value["assigned_arm"] == "treatment" for value in assignments),
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic
