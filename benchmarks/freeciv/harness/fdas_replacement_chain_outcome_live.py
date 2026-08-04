"""Audit completion-indexed coordinated-replacement outcome labels."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import (
    FdasReplacementChainOutcomeLabel,
    FdasReplacementChainOutcomeLabeler,
    FdasReplacementChainOutcomeStore,
    REPLACEMENT_CHAIN_OUTCOME_TARGET,
)

from .fdas_replacement_readout_live import (
    audit_fdas_replacement_readout_live,
)


_COMPONENT_ID = "fdas-coordinated-replacement-chain-outcome"
_IDENTITY = "fdas-coordinated-replacement-chain-outcome/1.0"


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


def _label_from_event(details):
    material = dict(details)
    for name in ("identity", "induction_readout", "store_digest", "transition"):
        material.pop(name, None)
    return FdasReplacementChainOutcomeLabel.from_dict(material)


def audit_fdas_replacement_chain_outcome_live(
        game_dir, repo=None, expected_source_commit=None):
    """Verify exact completion indexing and non-authorizing observations."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_readout_live(game_dir, repo=repo)
    names = (
        "events.jsonl", "fdas-coordinated-replacement-operations.json",
        "fdas-coordinated-replacement-outcome-labels.json",
        "manifest.json", "status.json")
    paths = dict((name, os.path.join(game_dir, name)) for name in names)
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError("missing replacement outcome evidence: {}".format(
            ", ".join(missing)))
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    operation_store = _load(
        paths["fdas-coordinated-replacement-operations.json"])
    outcome_store = _load(
        paths["fdas-coordinated-replacement-outcome-labels.json"])
    source = manifest.get("source", {})
    declaration = manifest.get("dependent_atomspace", {}).get("manifest", {})
    expected_diagnostic = {
        "action_selection_changed": False,
        "completion_index_required": True,
        "induction_readout": False,
        "observation_window_turns": 32,
        "policy_authority": False,
        "readout_authority": False,
        "target_id": REPLACEMENT_CHAIN_OUTCOME_TARGET,
        "transition_value_estimated": False,
        "truth_mutated": False,
    }

    records = {
        row.get("spec", {}).get("operation_id"): row
        for row in operation_store.get("records", ())}
    completed = {
        operation_id: row for operation_id, row in records.items()
        if row.get("progress", {}).get("state") == "completed"}
    semantic_store = dict(outcome_store)
    claimed_store_digest = semantic_store.pop("store_digest", None)
    labels = tuple(
        FdasReplacementChainOutcomeLabel.from_dict(row)
        for row in outcome_store.get("labels", ()))
    labels_by_operation = {
        value.operation_id: value for value in labels}
    replacement_identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"),
        "fdas-coordinated-replacement-operations/1.0",
    ])
    expected_persistence_identity = structural_hash([
        replacement_identity,
        FdasReplacementChainOutcomeLabeler.LABELER_IDENTITY,
        REPLACEMENT_CHAIN_OUTCOME_TARGET,
    ])

    label_bindings_valid = bool(
        len(labels_by_operation) == len(labels)
        and all(
            label.operation_id in completed
            and label.operation_spec_digest
            == completed[label.operation_id]["spec"].get("spec_digest")
            and label.completion_turn
            == completed[label.operation_id]["progress"].get(
                "last_updated_turn")
            and label.completion_snapshot_id
            == completed[label.operation_id]["progress"].get(
                "last_snapshot_id")
            and label.due_turn == label.completion_turn + 32
            for label in labels))

    rows = tuple(
        row for row in events
        if (row.get("type") in (
                "operation_outcome_label_opened",
                "operation_outcome_label_observed")
            and row.get("payload", {}).get("component_id") == _COMPONENT_ID))
    opened = tuple(
        row for row in rows
        if row.get("type") == "operation_outcome_label_opened")
    observed = tuple(
        row for row in rows
        if row.get("type") == "operation_outcome_label_observed")
    event_labels = tuple(
        _label_from_event(row["payload"]["details"]) for row in rows)
    final = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        final[0].get("payload", {}).get("summary", {})
        if len(final) == 1 else {})
    expected_counters = {
        "fdas_replacement_chain_outcomes_negative": sum(
            value.outcome is False for value in labels),
        "fdas_replacement_chain_outcomes_observed": sum(
            value.status == "observed" for value in labels),
        "fdas_replacement_chain_outcomes_opened": len(labels),
        "fdas_replacement_chain_outcomes_pending": sum(
            value.status == "pending" for value in labels),
        "fdas_replacement_chain_outcomes_positive": sum(
            value.outcome is True for value in labels),
    }

    checks = {
        "parent_replacement_lifecycle_and_readout_audit_passes": (
            parent["acceptance"]["accepted"]),
        "source_is_clean_and_expected_commit": (
            source.get("dirty") is False
            and (expected_source_commit is None
                 or source.get("commit") == expected_source_commit)),
        "manifest_freezes_completion_indexed_non_authority": (
            declaration.get("capabilities", {}).get(
                "coordinated_replacement_chain_outcome") == "shadow-live"
            and declaration.get(
                "coordinated_replacement_chain_outcome_diagnostic")
            == expected_diagnostic),
        "outcome_store_is_valid_unquarantined_and_identity_bound": (
            outcome_store.get("schema_version") == 1
            and outcome_store.get("store_identity")
            == FdasReplacementChainOutcomeStore.STORE_IDENTITY
            and outcome_store.get("quarantine_reason") is None
            and outcome_store.get("persistence_identity")
            == expected_persistence_identity
            and claimed_store_digest == structural_hash(semantic_store)),
        "completed_operations_and_labels_are_one_to_one": (
            set(labels_by_operation) == set(completed)
            and label_bindings_valid),
        "events_are_revision_current_non_authorizing_and_store_bound": all(
            isinstance(row["payload"].get("snapshot_id"), str)
            and bool(row["payload"].get("snapshot_id"))
            and isinstance(row["payload"].get("revision_id"), str)
            and bool(row["payload"].get("revision_id"))
            for row in rows),
        "events_have_exact_transition_and_authority_contract": all(
            detail.get("identity") == _IDENTITY
            and detail.get("induction_readout") is False
            and detail.get("transition") in ("opened", "observed")
            and isinstance(detail.get("store_digest"), str)
            and detail.get("action_selection_changed") is False
            and detail.get("policy_authority") is False
            and detail.get("readout_authority") is False
            and detail.get("transition_value_estimated") is False
            and detail.get("truth_mutated") is False
            for detail in (row["payload"]["details"] for row in rows)),
        "event_labels_match_persisted_lifecycle": (
            len(opened) == len(labels)
            and len(observed) == expected_counters[
                "fdas_replacement_chain_outcomes_observed"]
            and all(value.operation_id in labels_by_operation
                    for value in event_labels)),
        "status_and_terminal_counters_match_store": all(
            status.get(name) == value and terminal.get(name) == value
            for name, value in expected_counters.items()),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "completion-indexed coordinated-replacement outcome lifecycle "
            "only; zero completions are activation evidence, not value data; "
            "no transition value, preference, action, score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": source,
        "summary": {
            "completed_operations": len(completed),
            "labels": len(labels),
            "negative": expected_counters[
                "fdas_replacement_chain_outcomes_negative"],
            "observed": expected_counters[
                "fdas_replacement_chain_outcomes_observed"],
            "pending": expected_counters[
                "fdas_replacement_chain_outcomes_pending"],
            "positive": expected_counters[
                "fdas_replacement_chain_outcomes_positive"],
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
