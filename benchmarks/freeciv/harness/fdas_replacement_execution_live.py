"""Audit the claim-ineligible bounded replacement execution pilot."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import (
    FdasReplacementExecutionAssignment,
    FdasReplacementExecutionAttempt,
    FdasReplacementExecutionStore,
    REPLACEMENT_CHAIN_OUTCOME_TARGET,
    REPLACEMENT_EXECUTION_ASSIGNMENT_UNIT,
    REPLACEMENT_EXECUTION_TREATMENT_ID,
)

from .fdas_replacement_chain_outcome_live import (
    audit_fdas_replacement_chain_outcome_live,
)


_COMPONENT_ID = "fdas-coordinated-replacement-execution-pilot"
_EXPERIMENT_ID = "fdas-replacement-bounded-execution-pilot-v1"


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


def audit_fdas_replacement_execution_live(
        game_dir, repo=None, expected_source_commit=None):
    """Verify one exact forced-treatment chain through completion and label."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_chain_outcome_live(
        game_dir, repo=repo, expected_source_commit=expected_source_commit)
    names = (
        "events.jsonl", "fdas-coordinated-replacement-execution.json",
        "fdas-coordinated-replacement-operations.json",
        "fdas-coordinated-replacement-outcome-labels.json",
        "manifest.json", "status.json")
    paths = dict((name, os.path.join(game_dir, name)) for name in names)
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError("missing replacement execution evidence: {}".format(
            ", ".join(missing)))
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    operation_store = _load(
        paths["fdas-coordinated-replacement-operations.json"])
    outcome_store = _load(
        paths["fdas-coordinated-replacement-outcome-labels.json"])
    execution_store = _load(
        paths["fdas-coordinated-replacement-execution.json"])
    source = manifest.get("source", {})
    declaration = manifest.get("dependent_atomspace", {}).get("manifest", {})
    expected_diagnostic = {
        "assignment_unit": REPLACEMENT_EXECUTION_ASSIGNMENT_UNIT,
        "claim_eligible": False,
        "experiment_id": _EXPERIMENT_ID,
        "forced_arm": "treatment",
        "maximum_assigned_operations": 1,
        "outcome_target": REPLACEMENT_CHAIN_OUTCOME_TARGET,
        "planner_rematerialization_required": True,
        "policy_authority": True,
        "randomized": False,
        "treatment_id": REPLACEMENT_EXECUTION_TREATMENT_ID,
        "truth_mutated": False,
    }
    replacement_identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"),
        "fdas-coordinated-replacement-operations/1.0",
    ])
    expected_execution_identity = structural_hash([
        replacement_identity, REPLACEMENT_EXECUTION_TREATMENT_ID,
        _EXPERIMENT_ID,
    ])
    semantic_store = dict(execution_store)
    claimed_store_digest = semantic_store.pop("store_digest", None)
    assignment_value = execution_store.get("assignment")
    assignment = (
        None if assignment_value is None else
        FdasReplacementExecutionAssignment.from_dict(assignment_value))
    records = {
        row.get("spec", {}).get("operation_id"): row
        for row in operation_store.get("records", ())}
    selected_record = (
        None if assignment is None else records.get(assignment.operation_id))
    labels = {
        row.get("operation_id"): row
        for row in outcome_store.get("labels", ())}

    component_events = tuple(
        row for row in events
        if (row.get("type") == "atomspace_authority_decision"
            and row.get("payload", {}).get("component_id") == _COMPONENT_ID))
    transitions = tuple(
        row.get("payload", {}).get("details", {}).get("transition")
        for row in component_events)
    attempt_events = tuple(
        row for row in component_events
        if row.get("payload", {}).get("details", {}).get("transition")
        in ("attempt-accepted", "attempt-rejected"))
    event_attempts = tuple(
        FdasReplacementExecutionAttempt.from_dict({
            key: value for key, value in row["payload"]["details"].items()
            if key not in ("claim_eligible", "randomized", "store_digest",
                           "transition", "truth_mutated")})
        for row in attempt_events)
    result_events = {
        row.get("event_id"): row for row in events
        if row.get("type") == "action_result"}
    rejected_result_events = tuple(
        row for row in result_events.values()
        if row.get("payload", {}).get("status") != "accepted")
    final = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        final[0].get("payload", {}).get("summary", {})
        if len(final) == 1 else {})
    expected_counters = {
        "fdas_replacement_execution_assignments": 1,
        "fdas_replacement_execution_attempts": (
            0 if assignment is None else len(assignment.attempts)),
        "fdas_replacement_execution_accepted": (
            0 if assignment is None else
            sum(value.accepted for value in assignment.attempts)),
        "fdas_replacement_execution_rejected": (
            0 if assignment is None else
            sum(not value.accepted for value in assignment.attempts)),
    }

    checks = {
        "parent_completion_indexed_outcome_audit_passes": (
            parent["acceptance"]["accepted"]),
        "source_is_clean_and_expected_commit": (
            source.get("dirty") is False
            and (expected_source_commit is None
                 or source.get("commit") == expected_source_commit)),
        "manifest_freezes_one_forced_claim_ineligible_treatment": (
            declaration.get("capabilities", {}).get(
                "coordinated_replacement_execution") == "bounded-pilot"
            and declaration.get(
                "coordinated_replacement_execution_diagnostic")
            == expected_diagnostic),
        "execution_store_is_valid_unquarantined_and_identity_bound": (
            execution_store.get("schema_version") == 1
            and execution_store.get("store_identity")
            == FdasReplacementExecutionStore.STORE_IDENTITY
            and execution_store.get("quarantine_reason") is None
            and execution_store.get("persistence_identity")
            == expected_execution_identity
            and claimed_store_digest == structural_hash(semantic_store)),
        "exactly_one_assignment_is_bound_to_completed_operation": bool(
            assignment is not None
            and assignment.game_id == manifest.get("game_id")
            and assignment.experiment_id == _EXPERIMENT_ID
            and assignment.terminal_state == "completed"
            and selected_record is not None
            and selected_record.get("spec", {}).get("spec_digest")
            == assignment.operation_spec_digest
            and selected_record.get("progress", {}).get("state")
            == "completed"),
        "all_persisted_attempts_are_accepted_and_engine_linked": bool(
            assignment is not None and assignment.attempts
            and all(
                value.accepted
                and value.result_event_id in result_events
                and result_events[value.result_event_id].get(
                    "payload", {}).get("status") == "accepted"
                for value in assignment.attempts)),
        "attempt_events_match_persisted_attempts_exactly": bool(
            assignment is not None
            and event_attempts == assignment.attempts
            and all(
                value == "attempt-accepted"
                for value in transitions
                if isinstance(value, str) and value.startswith("attempt-"))),
        "authority_events_are_revision_current_and_pilot_bounded": bool(
            component_events
            and "authorized" in transitions
            and "terminal" in transitions
            and all(
                isinstance(row["payload"].get("snapshot_id"), str)
                and bool(row["payload"].get("revision_id"))
                and row["payload"]["details"].get("claim_eligible") is False
                and row["payload"]["details"].get("randomized") is False
                and row["payload"]["details"].get("truth_mutated") is False
                and isinstance(
                    row["payload"]["details"].get("store_digest"), str)
                for row in component_events)),
        "completion_opens_exactly_one_chain_outcome_label": bool(
            assignment is not None
            and assignment.operation_id in labels
            and parent["summary"]["labels"] >= 1),
        "status_and_terminal_attempt_counters_match_store": all(
            status.get(name) == value and terminal.get(name) == value
            for name, value in expected_counters.items()),
        "engine_actions_are_rejection_free": bool(
            status.get("rejected_actions") == 0
            and not rejected_result_events
            and len(result_events) == status.get("engine_actions")
            and len(result_events) == terminal.get("actions")),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "known-seed forced-treatment execution mechanics only; one "
            "completed coordinated replacement and its completion-indexed "
            "label; no causal value, policy, score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": source,
        "summary": {
            "accepted_attempts": expected_counters[
                "fdas_replacement_execution_accepted"],
            "assignment_id": (
                None if assignment is None else assignment.assignment_id),
            "completion_turn": (
                None if selected_record is None else
                selected_record.get("progress", {}).get("last_updated_turn")),
            "operation_id": (
                None if assignment is None else assignment.operation_id),
            "outcome_status": (
                None if assignment is None
                or assignment.operation_id not in labels else
                labels[assignment.operation_id].get("status")),
            "step_attempts": expected_counters[
                "fdas_replacement_execution_attempts"],
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
