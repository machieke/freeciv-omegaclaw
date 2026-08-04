"""Audit delayed durable-relief labels for PF-retained capacity queues."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning.fdas_capacity_outcomes import (
    FdasRetainedCapacityOutcomeLabel,
    FdasRetainedCapacityOutcomeLabeler,
    FdasRetainedCapacityOutcomeStore,
    RETAINED_CAPACITY_OUTCOME_TARGET,
)

from .fdas_replacement_capacity_retained_queue_live import (
    audit_fdas_replacement_capacity_retained_queue_live,
)


_COMPONENT = "fdas-retained-capacity-outcome"
_MECHANISM = "fdas-replacement-capacity-retained-queue-lifecycle"
_EVENT_TRANSITIONS = {
    "operation_outcome_label_opened": ("opened", "pending_product"),
    "operation_outcome_label_product_observed": (
        "product_observed", "pending_relief"),
    "operation_outcome_label_observed": ("observed", "observed"),
}
_DIAGNOSTIC = {
    "action_selection_changed": False,
    "deficit_authority": "current-dependent-revision",
    "induction_readout": False,
    "observation_window_turns": 32,
    "policy_authority": False,
    "product_identity_required": True,
    "readout_authority": False,
    "terminal_failure_semantics": "immediate-no-progress",
    "transition_value_estimated": False,
    "truth_mutated": False,
}
_COUNTERS = (
    "fdas_retained_capacity_outcomes_opened",
    "fdas_retained_capacity_outcomes_pending_product",
    "fdas_retained_capacity_outcomes_products_observed",
    "fdas_retained_capacity_outcomes_pending_relief",
    "fdas_retained_capacity_outcomes_terminal_no_progress",
    "fdas_retained_capacity_outcomes_relief_observed",
    "fdas_retained_capacity_outcomes_relief_positive",
    "fdas_retained_capacity_outcomes_relief_negative",
)
_AUTHORITY_FIELDS = (
    "action_selection_changed", "induction_readout", "policy_authority",
    "readout_authority", "transition_value_estimated", "truth_mutated",
)
_RELIEF_KEYS = frozenset((
    "deficit_absent", "product_at_source", "product_owned",
    "product_present", "product_type_matches",
    "source_city_owned_and_present", "target_city_owned_and_present",
))
_TERMINAL_REFRESH_BRIDGE_TYPES = frozenset((
    "atomspace_revision_started", "snapshot_delta_computed",
    "projection_batch_applied", "atomspace_revision_committed",
))


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


def _typed_label(value):
    try:
        return FdasRetainedCapacityOutcomeLabel.from_dict(value)
    except (KeyError, TypeError, ValueError):
        return None


def _valid_digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def _terminal_refresh_cause(row, operation_id, event_by_id):
    """Require one exact lifecycle terminal through only the FDAS refresh."""
    parent_ids = tuple(row.get("caused_by", ()))
    seen = set()
    while True:
        if len(parent_ids) != 1 or parent_ids[0] in seen:
            return False
        event_id = parent_ids[0]
        seen.add(event_id)
        cause = event_by_id.get(event_id)
        if cause is None:
            return False
        if (cause.get("type") in (
                "operation_abandoned", "operation_expired",
                "operation_failed")
                and cause.get("payload", {}).get("mechanism") == _MECHANISM
                and cause.get("payload", {}).get("operation_id")
                    == operation_id):
            return True
        if cause.get("type") not in _TERMINAL_REFRESH_BRIDGE_TYPES:
            return False
        parent_ids = tuple(cause.get("caused_by", ()))


def audit_fdas_replacement_capacity_retained_queue_outcome_live(
        game_dir, repo=None):
    """Verify exact product attribution remains separate from delayed relief."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_capacity_retained_queue_live(
        game_dir, repo=repo)
    paths = {
        name: os.path.join(game_dir, name)
        for name in (
            "events.jsonl", "fdas-retained-capacity-outcome-labels.json",
            "manifest.json", "status.json")
    }
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    raw_store = _load(paths["fdas-retained-capacity-outcome-labels.json"])
    completed = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        completed[0].get("payload", {}).get("summary", {})
        if len(completed) == 1 else {})
    terminal_turn = completed[0].get("turn") if len(completed) == 1 else None
    declared = manifest.get("dependent_atomspace", {}).get("manifest", {})
    persistence_identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"),
        FdasRetainedCapacityOutcomeLabeler.LABELER_IDENTITY,
        RETAINED_CAPACITY_OUTCOME_TARGET,
    ])
    store = FdasRetainedCapacityOutcomeStore.load(
        paths["fdas-retained-capacity-outcome-labels.json"],
        persistence_identity)
    labels = () if store.quarantined else store.labels()
    label_by_id = dict((label.label_id, label) for label in labels)
    label_by_operation = dict((label.operation_id, label) for label in labels)

    lifecycle = tuple(
        row for row in events
        if row.get("payload", {}).get("mechanism") == _MECHANISM)
    proposals = tuple(
        row for row in lifecycle if row.get("type") == "operation_proposed")
    lifecycle_by_id = dict(
        (row.get("event_id"), row) for row in lifecycle
        if isinstance(row.get("event_id"), str))
    event_by_id = dict(
        (row.get("event_id"), row) for row in events
        if isinstance(row.get("event_id"), str))
    proposal_by_operation = dict(
        (row.get("payload", {}).get("operation_id"), row) for row in proposals)
    outcome_events = tuple(
        row for row in events
        if row.get("payload", {}).get("component_id") == _COMPONENT)
    by_label = {}
    typed_event_labels = {}
    for row in outcome_events:
        details = row.get("payload", {}).get("details", {})
        label_id = details.get("label_id")
        by_label.setdefault(label_id, []).append(row)
        typed_event_labels[row.get("event_id")] = _typed_label(details)

    opened = tuple(
        row for row in outcome_events
        if row.get("type") == "operation_outcome_label_opened")
    products = tuple(
        row for row in outcome_events
        if row.get("type") == "operation_outcome_label_product_observed")
    observed = tuple(
        row for row in outcome_events
        if row.get("type") == "operation_outcome_label_observed")
    terminal_no_progress = tuple(
        row for row in observed
        if row.get("payload", {}).get("details", {}).get("outcome_kind")
        == "terminal-no-progress")
    relief = tuple(
        row for row in observed
        if row.get("payload", {}).get("details", {}).get("outcome_kind")
        == "durable-capacity-relief")
    relief_positive = tuple(
        row for row in relief
        if row.get("payload", {}).get("details", {}).get("outcome") is True)
    relief_negative = tuple(
        row for row in relief
        if row.get("payload", {}).get("details", {}).get("outcome") is False)
    pending_product = tuple(
        label for label in labels if label.status == "pending_product")
    pending_relief = tuple(
        label for label in labels if label.status == "pending_relief")
    event_counts = {
        _COUNTERS[0]: len(opened),
        _COUNTERS[1]: len(pending_product),
        _COUNTERS[2]: len(products),
        _COUNTERS[3]: len(pending_relief),
        _COUNTERS[4]: len(terminal_no_progress),
        _COUNTERS[5]: len(relief),
        _COUNTERS[6]: len(relief_positive),
        _COUNTERS[7]: len(relief_negative),
    }

    def event_shape(row):
        expected = _EVENT_TRANSITIONS.get(row.get("type"))
        details = row.get("payload", {}).get("details", {})
        typed = typed_event_labels.get(row.get("event_id"))
        provenance_prefix = (
            "proposal-revision:"
            if expected and expected[0] == "opened" else
            "lifecycle-revision:")
        provenance_revision = next(
            (value.split(":", 1)[1]
             for value in details.get("provenance_ids", ())
             if value.startswith(provenance_prefix)), None)
        expected_revision = (
            details.get("observed_revision_id")
            if expected and expected[0] == "observed"
            else provenance_revision)
        return bool(
            expected is not None and typed is not None
            and details.get("identity") == (
                "fdas-retained-capacity-outcome/1.0")
            and details.get("transition") == expected[0]
            and details.get("status") == expected[1]
            and details.get("state_digest") == typed.state_digest
            and _valid_digest(details.get("store_digest"))
            and all(details.get(name) is False for name in _AUTHORITY_FIELDS)
            and row.get("payload", {}).get("revision_id")
                == expected_revision
            and row.get("payload", {}).get("snapshot_id")
                == (details.get("product_snapshot_id")
                    if expected[0] == "product_observed"
                    else (details.get("proposed_snapshot_id")
                          if expected[0] == "opened"
                          else row.get("payload", {}).get("snapshot_id"))))

    def causal_shape(label):
        rows = by_label.get(label.label_id, ())
        kinds = [row.get("type") for row in rows]
        opened_rows = [row for row in rows if row.get("type") == (
            "operation_outcome_label_opened")]
        product_rows = [row for row in rows if row.get("type") == (
            "operation_outcome_label_product_observed")]
        observed_rows = [row for row in rows if row.get("type") == (
            "operation_outcome_label_observed")]
        proposal = proposal_by_operation.get(label.operation_id)
        if (len(opened_rows) != 1 or proposal is None
                or proposal.get("event_id") not in opened_rows[0].get(
                    "caused_by", ())):
            return False
        expected_kinds = ["operation_outcome_label_opened"]
        if label.status in ("pending_relief", "observed") and label.product_ref:
            expected_kinds.append("operation_outcome_label_product_observed")
        if label.status == "observed":
            expected_kinds.append("operation_outcome_label_observed")
        if kinds != expected_kinds:
            return False
        if product_rows:
            product = product_rows[0]
            parent_ids = product.get("caused_by", ())
            causes = [lifecycle_by_id.get(value) for value in parent_ids]
            cause = next((row for row in causes if row is not None), None)
            if not (cause is not None and cause.get("type") == "operation_completed"
                    and cause.get("payload", {}).get("operation_id")
                        == label.operation_id
                    and cause.get("payload", {}).get("product_ref")
                        == label.product_ref):
                return False
        if label.outcome_kind == "terminal-no-progress":
            if not _terminal_refresh_cause(
                    observed_rows[0], label.operation_id, event_by_id):
                return False
        return True

    def label_matches_proposal(label):
        proposal = proposal_by_operation.get(label.operation_id)
        if proposal is None:
            return False
        payload = proposal.get("payload", {})
        return bool(
            payload.get("operation_digest") == label.operation_digest
            and proposal.get("turn") == label.proposed_turn
            and payload.get("snapshot_id") == label.proposed_snapshot_id
            and "proposal-event:" + proposal.get("event_id", "")
                in label.provenance_ids)

    def relief_is_exact(row):
        details = row.get("payload", {}).get("details", {})
        values = details.get("observed_value", {})
        if frozenset(values) != _RELIEF_KEYS:
            return False
        outcome = all(value is True for value in values.values())
        failed = tuple(sorted(
            key.replace("_", "-") for key, value in values.items()
            if value is not True))
        reason = (
            "retained-capacity-relief-durable-at-due-turn"
            if outcome else
            "retained-capacity-relief-not-durable:" + ",".join(failed))
        return bool(
            details.get("outcome") is outcome
            and details.get("reason") == reason
            and details.get("due_turn") == details.get("product_turn") + 32
            and row.get("turn") == details.get("observed_turn")
            and row.get("turn") >= details.get("due_turn"))

    checks = {
        "parent_retained_queue_audit_passes": parent["acceptance"]["accepted"],
        "manifest_freezes_shadow_delayed_relief_contract": (
            declared.get("capabilities", {}).get(
                "replacement_capacity_retained_queue_outcome")
            == "shadow-live"
            and declared.get(
                "replacement_capacity_retained_queue_outcome_diagnostic")
            == _DIAGNOSTIC),
        "outcome_store_is_typed_identity_bound_and_digest_valid": (
            not store.quarantined
            and raw_store.get("persistence_identity") == persistence_identity
            and raw_store.get("store_digest") == store.store_digest
            and raw_store.get("quarantine_reason") is None),
        "one_label_is_opened_for_every_registered_retained_queue": (
            len(labels) == len(proposals)
            and set(label_by_operation) == set(proposal_by_operation)
            and len(opened) == len(labels)),
        "label_identity_is_bound_to_exact_proposal": all(
            label_matches_proposal(label) for label in labels),
        "event_transitions_are_typed_digest_valid_and_non_authorizing": (
            all(event_shape(row) for row in outcome_events)),
        "label_transitions_are_unique_ordered_and_causally_grounded": all(
            causal_shape(label) for label in labels),
        "persistent_terminal_state_equals_last_emitted_label_state": all(
            bool(by_label.get(label.label_id))
            and typed_event_labels.get(
                by_label[label.label_id][-1].get("event_id")) == label
            for label in labels),
        "event_counters_match_status_and_terminal_exactly": all(
            status.get(name) == count and terminal.get(name) == count
            for name, count in event_counts.items()),
        "accepted_product_and_delayed_relief_are_separate_transitions": all(
            row.get("turn") <= next(
                observed_row.get("turn") for observed_row in observed
                if observed_row.get("payload", {}).get("details", {}).get(
                    "label_id") == row.get("payload", {}).get(
                        "details", {}).get("label_id"))
            for row in products
            if any(observed_row.get("payload", {}).get("details", {}).get(
                       "label_id") == row.get("payload", {}).get(
                           "details", {}).get("label_id")
                   for observed_row in observed)),
        "durable_relief_is_exact_seven_conjunct_due_turn_attribution": all(
            relief_is_exact(row) for row in relief),
        "terminal_failures_are_immediate_no_progress_without_product": all(
            row.get("payload", {}).get("details", {}).get("product_ref") is None
            and row.get("payload", {}).get("details", {}).get("outcome")
                is False
            and row.get("payload", {}).get("details", {}).get("reason", "")
                .startswith("retained-capacity-terminal-no-progress:")
            for row in terminal_no_progress),
        "pending_labels_are_explicitly_retained_and_right_censored": (
            isinstance(terminal_turn, int)
            and all(label.due_turn is None or label.due_turn > terminal_turn
                    for label in (*pending_product, *pending_relief))),
        "final_store_digest_is_last_outcome_transition_digest": (
            not outcome_events or outcome_events[-1].get(
                "payload", {}).get("details", {}).get("store_digest")
            == store.store_digest),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "exact retained-queue acceptance, exact product identity, and "
            "32-turn durable replacement-capacity relief attribution; labels "
            "are shadow-only and make no causal policy, transition-value, "
            "score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "labels_opened": len(opened),
            "pending_product": len(pending_product),
            "products_observed": len(products),
            "pending_relief": len(pending_relief),
            "terminal_no_progress": len(terminal_no_progress),
            "relief_observed": len(relief),
            "relief_positive": len(relief_positive),
            "relief_negative": len(relief_negative),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
