"""Audit and pair intention-indexed coordinated-replacement outcomes."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.validator import validate_file
from freeciv_agent.planning import (
    FdasReplacementExecutionAssignment,
    FdasReplacementExecutionStore,
    FdasReplacementIntentionAssignment,
    FdasReplacementIntentionStore,
    REPLACEMENT_INTENTION_ASSIGNMENT_UNIT,
    REPLACEMENT_INTENTION_OUTCOME_TARGET,
    REPLACEMENT_INTENTION_TREATMENT_ID,
)

from .statistics import (
    paired_binary_discordance,
    paired_binary_effect,
    paired_delta,
)


EXPERIMENT_ID = "fdas-replacement-intention-paired-pilot-v1"
COMPONENT_ID = "fdas-coordinated-replacement-intention-outcome"
EXECUTION_COMPONENT_ID = "fdas-coordinated-replacement-execution-pilot"
FIXED_SEEDS = (
    109701, 109703, 109709, 109721, 109723, 109727, 109741, 109751,
    109789, 109793, 109807, 109819, 109829, 109831, 109841, 109843,
)


def expected_arm_order(seed):
    """Return the frozen SHA-256 low-bit launch order for one seed."""
    payload = "{}:{}".format(EXPERIMENT_ID, int(seed)).encode("utf-8")
    low_bit = hashlib.sha256(payload).digest()[-1] & 1
    return (
        ("control", "treatment")
        if low_bit == 0 else ("treatment", "control"))


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical(path, repo=None):
    absolute = os.path.abspath(path)
    if repo is not None:
        relative = os.path.relpath(absolute, os.path.abspath(repo))
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
            return relative.replace(os.sep, "/")
    return absolute


def _assignment_from_event(row):
    value = dict(row.get("payload", {}).get("details", {}))
    for name in (
            "identity", "policy_authority", "readout_authority",
            "store_digest", "transition"):
        value.pop(name, None)
    return FdasReplacementIntentionAssignment.from_dict(value)


def _removal(events, actor_id, assignment, present):
    observed_turn = assignment.outcome.observed_turn
    rows = tuple(
        row for row in events
        if (row.get("type") == "unit_lifecycle"
            and row.get("payload", {}).get("unit_id") == actor_id
            and row.get("payload", {}).get("transition") == "disappeared"
            and assignment.assignment_turn <= int(row.get("turn", -1))
            <= observed_turn))
    if present:
        unresolved = bool(rows and not any(
            row.get("type") == "unit_lifecycle"
            and row.get("payload", {}).get("unit_id") == actor_id
            and row.get("payload", {}).get("transition") == "appeared"
            and int(row.get("turn", -1)) > int(rows[-1].get("turn", -1))
            and int(row.get("turn", -1)) <= observed_turn
            for row in events))
        return {
            "cause": None,
            "evidence_quality": None,
            "event_id": None,
            "exact": not unresolved,
            "unexplained": unresolved,
        }
    if len(rows) != 1:
        return {
            "cause": None,
            "evidence_quality": None,
            "event_id": None,
            "exact": False,
            "unexplained": True,
        }
    row = rows[0]
    payload = row.get("payload", {})
    exact = bool(
        payload.get("evidence_quality") == "exact"
        and isinstance(payload.get("cause"), str)
        and bool(payload.get("cause"))
        and payload.get("evidence_event_ids")
        and row.get("caused_by"))
    return {
        "cause": payload.get("cause"),
        "detail": payload.get("detail"),
        "evidence_event_ids": list(payload.get("evidence_event_ids", ())),
        "evidence_quality": payload.get("evidence_quality"),
        "event_id": row.get("event_id"),
        "exact": exact,
        "turn": row.get("turn"),
        "unexplained": not exact,
    }


def _expected_diagnostic(arm):
    return {
        "assigned_arm": arm,
        "assignment_unit": REPLACEMENT_INTENTION_ASSIGNMENT_UNIT,
        "claim_eligible": False,
        "experiment_id": EXPERIMENT_ID,
        "maximum_assignments": 1,
        "observation_window_turns": 32,
        "outcome_target": REPLACEMENT_INTENTION_OUTCOME_TARGET,
        "policy_authority": False,
        "readout_authority": False,
        "treatment_executor_required": arm == "treatment",
        "truth_mutated": False,
    }


def audit_fdas_replacement_intention_arm(
        game_dir, repo=None, expected_source_commit=None):
    """Verify one control or treatment arm and return its outcome vector."""
    game_dir = os.path.abspath(game_dir)
    names = (
        "events.jsonl", "fdas-coordinated-replacement-intention.json",
        "fdas-coordinated-replacement-operations.json", "manifest.json",
        "status.json",
    )
    paths = dict((name, os.path.join(game_dir, name)) for name in names)
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError("missing replacement intention evidence: {}".format(
            ", ".join(missing)))
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    events = _events(paths["events.jsonl"])
    intention_store = _load(
        paths["fdas-coordinated-replacement-intention.json"])
    operation_store = _load(
        paths["fdas-coordinated-replacement-operations.json"])
    validation = validate_file(paths["events.jsonl"])
    declaration = manifest.get("dependent_atomspace", {}).get("manifest", {})
    diagnostic = declaration.get(
        "coordinated_replacement_intention_outcome_diagnostic", {})
    arm = diagnostic.get("assigned_arm")
    if arm not in ("control", "treatment"):
        raise ValueError("replacement intention arm is unavailable")
    assignment_value = intention_store.get("assignment")
    assignment = (
        None if assignment_value is None else
        FdasReplacementIntentionAssignment.from_dict(assignment_value))
    replacement_identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"),
        "fdas-coordinated-replacement-operations/1.0",
    ])
    expected_store_identity = structural_hash([
        replacement_identity, REPLACEMENT_INTENTION_TREATMENT_ID,
        EXPERIMENT_ID, arm,
    ])
    semantic_store = dict(intention_store)
    claimed_store_digest = semantic_store.pop("store_digest", None)
    component_events = tuple(
        row for row in events
        if row.get("payload", {}).get("component_id") == COMPONENT_ID)
    assigned_events = tuple(
        row for row in component_events
        if row.get("payload", {}).get("details", {}).get("transition")
        == "assigned")
    outcome_events = tuple(
        row for row in component_events
        if row.get("payload", {}).get("details", {}).get("transition")
        in ("observed", "censored"))
    run_completed = tuple(
        row for row in events if row.get("type") == "run_completed")
    run_started = tuple(
        row for row in events if row.get("type") == "run_started")
    terminal = (
        run_completed[0].get("payload", {}).get("summary", {})
        if len(run_completed) == 1 else {})
    action_results = tuple(
        row for row in events if row.get("type") == "action_result")
    execution_events = tuple(
        row for row in events
        if row.get("payload", {}).get("component_id")
        == EXECUTION_COMPONENT_ID)
    execution_path = os.path.join(
        game_dir, "fdas-coordinated-replacement-execution.json")
    execution_assignment = None
    execution_store = None
    if os.path.isfile(execution_path):
        paths["fdas-coordinated-replacement-execution.json"] = execution_path
        execution_store = _load(execution_path)
        if execution_store.get("assignment") is not None:
            execution_assignment = FdasReplacementExecutionAssignment.from_dict(
                execution_store["assignment"])
    records = {
        row.get("spec", {}).get("operation_id"): row
        for row in operation_store.get("records", ())}

    consequence = None
    if assignment is not None and assignment.outcome is not None:
        outcome = assignment.outcome
        consequence = {
            "assigned_actor_survival_count": (
                outcome.assigned_actor_survival_count),
            "both_cities_owned_and_present": (
                outcome.city_retention_count == 2
                if outcome.status == "observed" else None),
            "city_retention_count": outcome.city_retention_count,
            "defended_city_count": outcome.defended_city_count,
            "operation_state": outcome.operation_state,
            "outcome_status": outcome.status,
            "reinforcement_removal": (
                None if outcome.status != "observed" else
                _removal(
                    events, assignment.reinforcement_actor_id, assignment,
                    outcome.reinforcement_present)),
            "replacement_removal": (
                None if outcome.status != "observed" else
                _removal(
                    events, assignment.replacement_actor_id, assignment,
                    outcome.replacement_present)),
        }
        consequence["exact_combat_attributed_actor_losses"] = (
            None if outcome.status != "observed" else sum(
                row["exact"] and str(row.get("cause", "")).startswith(
                    "combat_")
                for row in (
                    consequence["replacement_removal"],
                    consequence["reinforcement_removal"])))
        consequence["unexplained_actor_removals"] = (
            None if outcome.status != "observed" else sum(
                row["unexplained"] for row in (
                    consequence["replacement_removal"],
                    consequence["reinforcement_removal"])))

    assignment_events_match = bool(
        (assignment is None and not assigned_events and not outcome_events)
        or (assignment is not None
            and len(assigned_events) == 1
            and _assignment_from_event(assigned_events[0]).identity_material
            == assignment.identity_material
            and ((assignment.outcome is None and not outcome_events)
                 or (assignment.outcome is not None
                     and len(outcome_events) == 1
                     and _assignment_from_event(outcome_events[0])
                     == assignment))))
    treatment_binding_valid = bool(
        (arm == "control"
         and execution_store is None
         and not execution_events
         and declaration.get("capabilities", {}).get(
             "coordinated_replacement_execution") is None)
        or (arm == "treatment"
            and execution_store is not None
            and execution_store.get("store_identity")
            == FdasReplacementExecutionStore.STORE_IDENTITY
            and execution_store.get("quarantine_reason") is None
            and ((assignment is None and execution_assignment is None)
                 or (assignment is not None
                     and execution_assignment is not None
                     and (
                         assignment.operation_id,
                         assignment.operation_spec_digest,
                         assignment.logical_pair,
                         assignment.assignment_turn,
                     ) == (
                         execution_assignment.operation_id,
                         execution_assignment.operation_spec_digest,
                         (
                             execution_assignment.replacement_actor_id,
                             execution_assignment.reinforcement_actor_id,
                             execution_assignment.source_city_id,
                             execution_assignment.target_city_id,
                         ),
                         execution_assignment.assignment_turn,
                     )
                     and all(
                         attempt.accepted
                         and any(
                             row.get("event_id") == attempt.result_event_id
                             and row.get("payload", {}).get("status")
                             == "accepted"
                             for row in action_results)
                         for attempt in execution_assignment.attempts)))))
    complete_vector = bool(
        consequence is None
        or consequence["outcome_status"] == "censored"
        or consequence["unexplained_actor_removals"] == 0)
    source = manifest.get("source", {})
    expected_counters = {
        "fdas_replacement_intention_assignments": int(assignment is not None),
        "fdas_replacement_intention_censored": int(
            assignment is not None and assignment.outcome is not None
            and assignment.outcome.status == "censored"),
        "fdas_replacement_intention_observed": int(
            assignment is not None and assignment.outcome is not None
            and assignment.outcome.status == "observed"),
        "fdas_replacement_intention_pending": int(
            assignment is not None and assignment.outcome is None),
    }
    checks = {
        "source_is_clean_and_expected_commit": bool(
            source.get("dirty") is False
            and (expected_source_commit is None
                 or source.get("commit") == expected_source_commit)),
        "run_completed_with_valid_warning_free_ledger": bool(
            status.get("completed") is True
            and len(run_completed) == 1
            and validation.valid
            and not validation.warnings),
        "manifest_is_arm_locked_and_claim_ineligible": bool(
            declaration.get("capabilities", {}).get(
                "coordinated_replacement_intention_outcome") == "shadow-live"
            and diagnostic == _expected_diagnostic(arm)),
        "intention_store_is_identity_bound_and_unquarantined": bool(
            intention_store.get("schema_version") == 1
            and intention_store.get("store_identity")
            == FdasReplacementIntentionStore.STORE_IDENTITY
            and intention_store.get("persistence_identity")
            == expected_store_identity
            and intention_store.get("quarantine_reason") is None
            and claimed_store_digest == structural_hash(semantic_store)),
        "assignment_and_outcome_events_match_store": assignment_events_match,
        "outcome_is_terminal_and_vector_is_complete": bool(
            assignment is None
            or (assignment.outcome is not None and complete_vector)),
        "arm_execution_boundary_and_identity_match": treatment_binding_valid,
        "engine_actions_are_rejection_free": bool(
            status.get("rejected_actions") == 0
            and all(row.get("payload", {}).get("status") == "accepted"
                    for row in action_results)
            and len(action_results) == status.get("engine_actions")
            and len(action_results) == terminal.get("actions")),
        "terminal_intention_counters_match_store": all(
            status.get(name) == value and terminal.get(name) == value
            for name, value in expected_counters.items()),
        "control_has_zero_replacement_selection_changes": bool(
            arm == "treatment"
            or (status.get("fdas_replacement_execution_selection_changes", 0)
                == 0
                and terminal.get(
                    "fdas_replacement_execution_selection_changes", 0) == 0)),
    }
    selected_record = (
        None if assignment is None else records.get(assignment.operation_id))
    summary = {
        "arm": arm,
        "assignment_turn": (
            None if assignment is None else assignment.assignment_turn),
        "consequence": consequence,
        "execution_accepted": (
            0 if execution_assignment is None else
            sum(attempt.accepted for attempt in execution_assignment.attempts)),
        "execution_attempts": (
            0 if execution_assignment is None else
            len(execution_assignment.attempts)),
        "execution_completion_turn": (
            None if selected_record is None
            or selected_record.get("progress", {}).get("state") != "completed"
            else selected_record.get("progress", {}).get("last_updated_turn")),
        "logical_pair": (
            None if assignment is None else list(assignment.logical_pair)),
        "opportunity": assignment is not None,
        "run_started_at": (
            run_started[0].get("ts") if len(run_started) == 1 else None),
        "seed": manifest.get("seed"),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "one intention-indexed mechanism arm; no causal value, policy, "
            "score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "event_validation": validation.to_dict(),
        "schema_version": "1.0",
        "source": source,
        "summary": summary,
    }
    report["structural_hash"] = structural_hash(report)
    return report


def paired_replacement_intention_analysis(control_by_seed, treatment_by_seed):
    """Classify fixed pairs and compute the preregistered descriptive effects."""
    rows = []
    observed = []
    mechanical_failures = []
    for seed in FIXED_SEEDS:
        control = control_by_seed.get(seed)
        treatment = treatment_by_seed.get(seed)
        classification = None
        if control is None or treatment is None:
            classification = "incomplete-pair"
        elif not control.get("opportunity") and not treatment.get("opportunity"):
            classification = "no-opportunity"
        elif (not control.get("opportunity")
              or not treatment.get("opportunity")
              or control.get("assignment_turn")
              != treatment.get("assignment_turn")
              or control.get("logical_pair") != treatment.get("logical_pair")):
            classification = "opportunity-mismatch"
        else:
            control_status = (
                control.get("consequence") or {}).get("outcome_status")
            treatment_status = (
                treatment.get("consequence") or {}).get("outcome_status")
            if control_status == treatment_status == "censored":
                classification = "matched-censored"
            elif control_status == treatment_status == "observed":
                classification = "matched-observed"
            else:
                classification = "outcome-mismatch"
        row = {
            "classification": classification,
            "control": control,
            "seed": seed,
            "treatment": treatment,
        }
        expected_order = expected_arm_order(seed)
        starts = (
            None if control is None else control.get("run_started_at"),
            None if treatment is None else treatment.get("run_started_at"),
        )
        observed_order = None
        if all(isinstance(value, str) and value for value in starts):
            observed_order = (
                ("control", "treatment")
                if starts[0] < starts[1] else ("treatment", "control"))
        row["expected_arm_order"] = list(expected_order)
        row["observed_arm_order"] = (
            None if observed_order is None else list(observed_order))
        row["arm_order_valid"] = observed_order == expected_order
        rows.append(row)
        if classification == "matched-observed":
            observed.append(row)
        if (classification in (
                "incomplete-pair", "opportunity-mismatch",
                "outcome-mismatch") or not row["arm_order_valid"]):
            mechanical_failures.append(seed)

    def values(arm, key):
        return dict(
            (row["seed"], row[arm]["consequence"][key])
            for row in observed)

    control_cities = values("control", "both_cities_owned_and_present")
    treatment_cities = values("treatment", "both_cities_owned_and_present")
    primary = {
        "discordance": paired_binary_discordance(
            control_cities, treatment_cities),
        "risk_difference": paired_binary_effect(
            control_cities, treatment_cities),
    }
    secondary = {}
    for key in (
            "city_retention_count", "defended_city_count",
            "assigned_actor_survival_count",
            "exact_combat_attributed_actor_losses"):
        secondary[key] = paired_delta(
            values("control", key), values("treatment", key))
    return {
        "classification_counts": dict(
            (name, sum(row["classification"] == name for row in rows))
            for name in (
                "matched-observed", "matched-censored", "no-opportunity",
                "opportunity-mismatch", "outcome-mismatch",
                "incomplete-pair")),
        "mechanical_failure_seeds": mechanical_failures,
        "primary": primary,
        "progression": {
            "city_retention_point_estimate_nonnegative": bool(
                primary["risk_difference"]["estimate"] is not None
                and primary["risk_difference"]["estimate"] >= 0),
            "minimum_four_observed_pairs": len(observed) >= 4,
            "minimum_two_treatment_completions": sum(
                row["treatment"].get("execution_completion_turn") is not None
                for row in observed) >= 2,
            "no_mechanical_failures": not mechanical_failures,
            "no_treatment_excess_unexplained_removal": all(
                row["treatment"]["consequence"][
                    "unexplained_actor_removals"]
                <= row["control"]["consequence"][
                    "unexplained_actor_removals"]
                for row in observed),
        },
        "rows": rows,
        "schema_version": "1.0",
        "secondary": secondary,
    }


def audit_fdas_replacement_intention_cohort(
        control_game_dirs, treatment_game_dirs, repo=None,
        expected_source_commit=None):
    """Audit all fixed arms and apply the preregistered paired analysis."""
    reports = {"control": {}, "treatment": {}}
    for arm, directories in (
            ("control", control_game_dirs),
            ("treatment", treatment_game_dirs)):
        for directory in sorted(os.path.abspath(path) for path in directories):
            report = audit_fdas_replacement_intention_arm(
                directory, repo=repo,
                expected_source_commit=expected_source_commit)
            summary = report["summary"]
            if summary["arm"] != arm:
                raise ValueError("replacement intention cohort arm differs")
            seed = summary["seed"]
            if seed in reports[arm]:
                raise ValueError(
                    "duplicate replacement intention {} seed {}".format(
                        arm, seed))
            reports[arm][seed] = report
    control_summaries = dict(
        (seed, report["summary"])
        for seed, report in reports["control"].items())
    treatment_summaries = dict(
        (seed, report["summary"])
        for seed, report in reports["treatment"].items())
    analysis = paired_replacement_intention_analysis(
        control_summaries, treatment_summaries)
    source_commits = sorted(set(
        report.get("source", {}).get("commit")
        for arm in reports.values() for report in arm.values()),
        key=lambda value: "" if value is None else value)
    checks = {
        "all_fixed_control_arms_are_present": (
            sorted(reports["control"]) == list(FIXED_SEEDS)),
        "all_fixed_treatment_arms_are_present": (
            sorted(reports["treatment"]) == list(FIXED_SEEDS)),
        "all_arm_audits_pass": all(
            report["acceptance"]["accepted"]
            for arm in reports.values() for report in arm.values()),
        "all_arms_share_one_expected_clean_source": bool(
            len(source_commits) == 1
            and source_commits[0] is not None
            and (expected_source_commit is None
                 or source_commits[0] == expected_source_commit)),
        "no_pair_has_a_mechanical_failure": not analysis[
            "mechanical_failure_seeds"],
        "minimum_four_pairs_are_matched_and_observed": (
            analysis["classification_counts"]["matched-observed"] >= 4),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "analysis": analysis,
        "arm_reports": dict(
            (arm, dict(
                (str(seed), {
                    "acceptance": value["acceptance"]["accepted"],
                    "structural_hash": value["structural_hash"],
                    "summary": value["summary"],
                }) for seed, value in sorted(rows.items())))
            for arm, rows in reports.items()),
        "claim_scope": (
            "16-seed paired descriptive mechanism pilot; no calibrated "
            "transition-value, general policy, score, or win-rate claim"),
        "experiment_id": EXPERIMENT_ID,
        "fixed_seeds": list(FIXED_SEEDS),
        "schema_version": "1.0",
        "source_commits": source_commits,
    }
    report["structural_hash"] = structural_hash(report)
    return report
