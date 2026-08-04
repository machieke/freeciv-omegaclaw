"""Audit proposal-time retained-capacity transition-query abstentions."""

import hashlib
import json
import os
from types import SimpleNamespace

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import (
    DecisionEpisodeStore,
    FdasRetainedCapacityOutcomeLabel,
    FdasRetainedCapacityTransitionQuery,
    FdasRetainedCapacityTransitionQueryBuilder,
    FdasRetainedCapacityTransitionQueryStore,
    RETAINED_CAPACITY_TRANSITION_QUERY_IDENTITY,
)
from freeciv_agent.state import snapshot_from_event

from .fdas_replacement_capacity_retained_queue_episode_live import (
    audit_fdas_replacement_capacity_retained_queue_episode_live,
)


_COMPONENT = "fdas-retained-capacity-transition-query"
_MECHANISM = "fdas-replacement-capacity-retained-queue-lifecycle"
_DIAGNOSTIC = {
    "abstention_reason": "insufficient-independent-calibration-evidence",
    "action_selection_changed": False,
    "episode_prediction_link": False,
    "feature_schema": "retained-capacity-transition-features/1.0",
    "learning_authority": False,
    "numerical_estimate": False,
    "policy_authority": False,
    "query_store": "separate-observation-only",
    "readout_authority": False,
    "transition_value_estimated": False,
    "truth_mutated": False,
}
_AUTHORITY_FIELDS = (
    "action_selection_changed", "learning_authority", "policy_authority",
    "readout_authority", "transition_value_estimated", "truth_mutated",
)


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


def _typed_query(value):
    try:
        return FdasRetainedCapacityTransitionQuery.from_dict(value)
    except (KeyError, TypeError, ValueError):
        return None


def _typed_label(value):
    try:
        return FdasRetainedCapacityOutcomeLabel.from_dict(value)
    except (KeyError, TypeError, ValueError):
        return None


def _payload_hash_is_valid(payload):
    if not isinstance(payload, dict):
        return False
    expected = payload.get("structural_hash")
    material = dict(payload)
    material.pop("structural_hash", None)
    return expected == structural_hash(material)


def _contains(value, target):
    if value == target:
        return True
    if isinstance(value, dict):
        return any(_contains(item, target) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains(item, target) for item in value)
    return False


def audit_fdas_retained_capacity_transition_query_live(game_dir, repo=None):
    """Verify exact outcome-blind feature capture and mandatory abstention."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_capacity_retained_queue_episode_live(
        game_dir, repo=repo)
    paths = {
        name: os.path.join(game_dir, name)
        for name in (
            "events.jsonl", "fdas-decision-episodes.json",
            "fdas-retained-capacity-decision-episodes.json",
            "fdas-retained-capacity-transition-queries.json",
            "manifest.json", "status.json")
    }
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    completed = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        completed[0].get("payload", {}).get("summary", {})
        if len(completed) == 1 else {})
    declared = manifest.get("dependent_atomspace", {}).get("manifest", {})
    identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"), RETAINED_CAPACITY_TRANSITION_QUERY_IDENTITY,
    ])
    raw_store = _load(paths[
        "fdas-retained-capacity-transition-queries.json"])
    store = FdasRetainedCapacityTransitionQueryStore.load(
        paths["fdas-retained-capacity-transition-queries.json"], identity)
    queries = () if store.quarantined else store.queries()
    query_by_operation = dict(
        (query.operation_id, query) for query in queries)

    proposals = tuple(
        row for row in events
        if row.get("type") == "operation_proposed"
        and row.get("payload", {}).get("mechanism") == _MECHANISM)
    proposal_by_operation = dict(
        (row.get("payload", {}).get("operation_id"), row)
        for row in proposals)
    opened_events = tuple(
        row for row in events
        if row.get("type") == "operation_outcome_label_opened"
        and row.get("payload", {}).get("component_id") == (
            "fdas-retained-capacity-outcome"))
    opened_by_label = dict(
        (row.get("payload", {}).get("details", {}).get("label_id"), row)
        for row in opened_events)
    opened_labels = tuple(
        _typed_label(row.get("payload", {}).get("details", {}))
        for row in opened_events)
    snapshot_events = tuple(
        row for row in events if row.get("type") == "state_snapshot")
    snapshots_by_id = {}
    for row in snapshot_events:
        snapshots_by_id.setdefault(
            row.get("payload", {}).get("snapshot_id"), []).append(row)
    expected_by_operation = {}
    recomputation_errors = []
    for label in opened_labels:
        if label is None:
            recomputation_errors.append("opened label is not typed")
            continue
        query = query_by_operation.get(label.operation_id)
        proposal = proposal_by_operation.get(label.operation_id)
        snapshots = snapshots_by_id.get(label.proposed_snapshot_id, ())
        if query is None or proposal is None or len(snapshots) != 1:
            recomputation_errors.append(
                "query proposal or exact snapshot is missing:{}".format(
                    label.operation_id))
            continue
        try:
            snapshot = snapshot_from_event(snapshots[0])
            revision = SimpleNamespace(
                revision_id=query.revision_id,
                snapshot_id=query.snapshot_id,
                record=lambda atom_id, expected=label.deficit_atom_id: (
                    object() if atom_id == expected else None))
            expected = FdasRetainedCapacityTransitionQueryBuilder.build(
                proposal, label, snapshot, revision)
            expected_by_operation[label.operation_id] = expected
        except (KeyError, TypeError, ValueError) as error:
            recomputation_errors.append(str(error))

    query_events = tuple(
        row for row in events
        if row.get("type") == "transition_prediction_abstained"
        and row.get("payload", {}).get("component_id") == _COMPONENT)
    typed_event_queries = tuple(
        _typed_query(row.get("payload", {}).get(
            "details", {}).get("query"))
        for row in query_events)
    replay_store = FdasRetainedCapacityTransitionQueryStore(identity)
    replay_valid = True
    for row, query in zip(query_events, typed_event_queries):
        if query is None:
            replay_valid = False
            continue
        try:
            replay_store.record(query)
        except ValueError:
            replay_valid = False
            continue
        if row.get("payload", {}).get(
                "details", {}).get("store_digest") != replay_store.store_digest:
            replay_valid = False

    def event_shape(row, query):
        if query is None:
            return False
        details = row.get("payload", {}).get("details", {})
        opened = opened_by_label.get(query.label_id)
        expected = expected_by_operation.get(query.operation_id)
        return bool(
            query == expected and opened is not None
            and row.get("caused_by") == [opened.get("event_id")]
            and row.get("turn") == query.proposed_turn
            and row.get("payload", {}).get("snapshot_id") == query.snapshot_id
            and row.get("payload", {}).get("revision_id") == query.revision_id
            and row.get("payload", {}).get("component_version") == "1.0"
            and details.get("identity")
                == RETAINED_CAPACITY_TRANSITION_QUERY_IDENTITY
            and all(details.get(name) is False for name in _AUTHORITY_FIELDS)
            and query.status == "abstained"
            and all(getattr(query, name) is None for name in (
                "estimate", "interval_lower", "interval_upper", "model_id"))
            and _payload_hash_is_valid(row.get("payload")))

    main_identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"), "fdas-defense-decision-episodes/1.0",
    ])
    main_store = DecisionEpisodeStore.load(
        paths["fdas-decision-episodes.json"], main_identity)
    capacity_episode_raw = _load(paths[
        "fdas-retained-capacity-decision-episodes.json"])
    prediction_ids = tuple(
        prediction_id
        for row in capacity_episode_raw.get("episodes", ())
        for prediction_id in row.get("prediction_ids", ()))
    query_ids = set(query.query_id for query in queries)
    other_events = tuple(row for row in events if row not in query_events)
    counts = {
        "fdas_retained_capacity_transition_queries_captured": len(queries),
        "fdas_retained_capacity_transition_queries_abstained": sum(
            query.status == "abstained" for query in queries),
    }
    checks = {
        "parent_episode_audit_passes": parent["acceptance"]["accepted"],
        "manifest_freezes_outcome_blind_abstention_contract": (
            declared.get("capabilities", {}).get(
                "replacement_capacity_transition_prediction_query")
            == "shadow-live"
            and declared.get(
                "replacement_capacity_transition_prediction_query_diagnostic")
            == _DIAGNOSTIC),
        "query_store_is_typed_identity_bound_and_digest_valid": (
            not store.quarantined
            and raw_store.get("persistence_identity") == identity
            and raw_store.get("store_digest") == store.store_digest
            and raw_store.get("quarantine_reason") is None),
        "one_query_exists_for_every_opened_outcome_label": (
            len(queries) == len(opened_labels) == len(opened_events)
            and len(query_by_operation) == len(queries)
            and all(label is not None and label.operation_id in query_by_operation
                    for label in opened_labels)),
        "queries_recompute_from_exact_proposal_time_snapshot": (
            not recomputation_errors
            and query_by_operation == expected_by_operation),
        "one_typed_causal_non_authorizing_abstention_event_per_query": (
            len(query_events) == len(queries)
            and all(event_shape(row, query) for row, query in zip(
                query_events, typed_event_queries))),
        "incremental_event_store_digests_replay_to_final_store": (
            replay_valid and replay_store.queries() == queries
            and replay_store.store_digest == store.store_digest),
        "query_counters_match_store_status_and_terminal_exactly": all(
            status.get(name) == value and terminal.get(name) == value
            for name, value in counts.items()),
        "queries_do_not_enter_episode_learning_induction_or_readout": (
            not main_store.quarantined and not prediction_ids
            and all(not _contains(row.get("payload", {}), query_id)
                    for row in other_events for query_id in query_ids)),
        "final_store_digest_is_last_query_event_digest": (
            not query_events or query_events[-1].get(
                "payload", {}).get("details", {}).get("store_digest")
            == store.store_digest),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "exact proposal-time retained-capacity categorical feature "
            "capture with mandatory numerical abstention; no episode link, "
            "learning, induction, readout, policy, score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "recomputation_errors": recomputation_errors,
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "abstained": counts[
                "fdas_retained_capacity_transition_queries_abstained"],
            "queries": len(queries),
            "terminal_episodes": len(capacity_episode_raw.get("episodes", ())),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
