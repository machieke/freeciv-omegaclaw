"""Audit observation-only episodes derived from retained-capacity outcomes."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning.fdas_capacity_episode_bridge import (
    FdasRetainedCapacityEpisodeBridge,
    RETAINED_CAPACITY_EPISODE_BRIDGE_IDENTITY,
)
from freeciv_agent.planning.fdas_capacity_outcomes import (
    FdasRetainedCapacityOutcomeLabeler,
    FdasRetainedCapacityOutcomeStore,
    RETAINED_CAPACITY_OUTCOME_TARGET,
)
from freeciv_agent.planning.fdas_episodes import (
    DecisionEpisode,
    DecisionEpisodeStore,
)

from .fdas_replacement_capacity_retained_queue_outcome_live import (
    audit_fdas_replacement_capacity_retained_queue_outcome_live,
)


_COMPONENT = "fdas-retained-capacity-episode-bridge"
_MECHANISM = "fdas-replacement-capacity-retained-queue-lifecycle"
_DIAGNOSTIC = {
    "action_selection_changed": False,
    "action_submitted": False,
    "episode_store": "separate-observation-only",
    "learning_authority": False,
    "mapping": {
        "durable-negative": "effect-without-goal-relief",
        "durable-positive": "goal-relief-observed",
        "terminal-no-progress": "no-effect-observed",
    },
    "policy_authority": False,
    "prediction_ids_required_empty": True,
    "readout_authority": False,
    "transition_value_estimated": False,
    "truth_mutated": False,
}
_AUTHORITY_FIELDS = (
    "action_selection_changed", "learning_authority", "policy_authority",
    "readout_authority", "transition_value_estimated", "truth_mutated",
)
_COUNTERS = {
    "fdas_retained_capacity_episodes_encoded": None,
    "fdas_retained_capacity_episodes_no_effect": "no-effect-observed",
    "fdas_retained_capacity_episodes_effect_without_relief": (
        "effect-without-goal-relief"),
    "fdas_retained_capacity_episodes_goal_relief": "goal-relief-observed",
}


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


def _typed_episode(value):
    try:
        return DecisionEpisode.from_dict(value)
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


def audit_fdas_replacement_capacity_retained_queue_episode_live(
        game_dir, repo=None):
    """Verify exact common episodes without learning or control authority."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_capacity_retained_queue_outcome_live(
        game_dir, repo=repo)
    paths = {
        name: os.path.join(game_dir, name)
        for name in (
            "events.jsonl", "fdas-decision-episodes.json",
            "fdas-retained-capacity-decision-episodes.json",
            "fdas-retained-capacity-outcome-labels.json", "manifest.json",
            "status.json")
    }
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    completed = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        completed[0].get("payload", {}).get("summary", {})
        if len(completed) == 1 else {})
    declared = manifest.get("dependent_atomspace", {}).get("manifest", {})
    learning = manifest.get("dependent_atomspace", {}).get(
        "config", {}).get("learning", {})

    outcome_identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"),
        FdasRetainedCapacityOutcomeLabeler.LABELER_IDENTITY,
        RETAINED_CAPACITY_OUTCOME_TARGET,
    ])
    outcome_store = FdasRetainedCapacityOutcomeStore.load(
        paths["fdas-retained-capacity-outcome-labels.json"], outcome_identity)
    labels = () if outcome_store.quarantined else outcome_store.labels()
    observed_labels = tuple(label for label in labels if label.status == "observed")
    observed_by_id = dict((label.label_id, label) for label in observed_labels)

    persistence_identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"), RETAINED_CAPACITY_EPISODE_BRIDGE_IDENTITY,
    ])
    raw_store = _load(paths[
        "fdas-retained-capacity-decision-episodes.json"])
    store = DecisionEpisodeStore.load(
        paths["fdas-retained-capacity-decision-episodes.json"],
        persistence_identity)
    episodes = () if store.quarantined else store.episodes()
    episode_by_operation = dict(
        (episode.operation_id, episode) for episode in episodes)

    proposals = tuple(
        row for row in events
        if row.get("type") == "operation_proposed"
        and row.get("payload", {}).get("mechanism") == _MECHANISM)
    proposal_by_operation = dict(
        (row.get("payload", {}).get("operation_id"), row)
        for row in proposals)
    expected_store = DecisionEpisodeStore("retained-capacity-audit-expected")
    expected_bridge = FdasRetainedCapacityEpisodeBridge(expected_store)
    expected_by_operation = {}
    expected_error = None
    try:
        for label in observed_labels:
            expected = expected_bridge.encode(
                label, proposal_by_operation[label.operation_id])
            expected_by_operation[label.operation_id] = expected
    except (KeyError, TypeError, ValueError) as error:
        expected_error = str(error)

    outcome_events = tuple(
        row for row in events
        if row.get("type") == "operation_outcome_label_observed"
        and row.get("payload", {}).get("component_id") == (
            "fdas-retained-capacity-outcome"))
    outcome_event_by_label = dict(
        (row.get("payload", {}).get("details", {}).get("label_id"), row)
        for row in outcome_events)
    episode_events = tuple(
        row for row in events
        if row.get("type") == "episode_opened"
        and row.get("payload", {}).get("component_id") == _COMPONENT)
    typed_event_episodes = tuple(
        _typed_episode(row.get("payload", {}).get(
            "details", {}).get("episode"))
        for row in episode_events)

    replay_store = DecisionEpisodeStore(persistence_identity)
    replay_valid = True
    for row, episode in zip(episode_events, typed_event_episodes):
        if episode is None:
            replay_valid = False
            continue
        try:
            replay_store.record(episode)
        except ValueError:
            replay_valid = False
            continue
        if row.get("payload", {}).get(
                "details", {}).get("store_digest") != replay_store.store_digest:
            replay_valid = False

    def event_shape(row, episode):
        if episode is None:
            return False
        details = row.get("payload", {}).get("details", {})
        expected = expected_by_operation.get(episode.operation_id)
        label_id = episode.observed_delta.get("label_id")
        label = observed_by_id.get(label_id)
        outcome_event = outcome_event_by_label.get(label_id)
        return bool(
            expected is not None and episode == expected
            and label is not None and outcome_event is not None
            and row.get("caused_by") == [outcome_event.get("event_id")]
            and row.get("turn") == label.observed_turn
            and row.get("payload", {}).get("revision_id")
                == episode.after_revision_id == label.observed_revision_id
            and row.get("payload", {}).get("snapshot_id")
                == outcome_event.get("payload", {}).get("snapshot_id")
            and row.get("payload", {}).get("component_version") == "1.0"
            and details.get("identity")
                == RETAINED_CAPACITY_EPISODE_BRIDGE_IDENTITY
            and all(details.get(name) is False for name in _AUTHORITY_FIELDS)
            and episode.prediction_ids == ()
            and episode.execution_event_id is None
            and dict(episode.context_signature).get("action_submitted")
                == "false"
            and dict(episode.context_signature).get(
                "selection_policy_authority") == "false"
            and _payload_hash_is_valid(row.get("payload")))

    main_identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"), "fdas-defense-decision-episodes/1.0",
    ])
    main_store = DecisionEpisodeStore.load(
        paths["fdas-decision-episodes.json"], main_identity)
    main_ids = set(
        episode.episode_id for episode in main_store.episodes()
        if not main_store.quarantined)
    capacity_ids = set(episode.episode_id for episode in episodes)
    other_events = tuple(row for row in events if row not in episode_events)
    counts = {
        name: (len(episodes) if outcome_status is None else sum(
            episode.outcome_status == outcome_status for episode in episodes))
        for name, outcome_status in _COUNTERS.items()
    }
    checks = {
        "parent_delayed_outcome_audit_passes": parent["acceptance"]["accepted"],
        "manifest_freezes_observation_only_episode_contract": (
            declared.get("capabilities", {}).get(
                "replacement_capacity_retained_queue_episode_bridge")
            == "shadow-live"
            and declared.get(
                "replacement_capacity_retained_queue_episode_bridge_diagnostic")
            == _DIAGNOSTIC
            and learning.get("episode_attribution_enabled") is True
            and learning.get("contextual_conductance_enabled") is False
            and learning.get("contextual_conductance_authority_enabled") is False
            and learning.get("induced_rule_readout_enabled") is False),
        "separate_episode_store_is_typed_identity_bound_and_digest_valid": (
            not store.quarantined
            and raw_store.get("persistence_identity") == persistence_identity
            and raw_store.get("store_digest") == store.store_digest
            and raw_store.get("quarantine_reason") is None),
        "one_episode_exists_for_every_terminal_outcome_label": (
            len(episodes) == len(observed_labels)
            and len(episode_by_operation) == len(episodes)
            and set(episode_by_operation) == set(
                label.operation_id for label in observed_labels)),
        "episodes_recompute_exactly_from_proposal_and_outcome_evidence": (
            expected_error is None
            and episode_by_operation == expected_by_operation),
        "one_typed_causal_non_authorizing_event_exists_per_episode": (
            len(episode_events) == len(episodes)
            and all(event_shape(row, episode) for row, episode in zip(
                episode_events, typed_event_episodes))),
        "incremental_event_store_digests_replay_to_final_store": (
            replay_valid and replay_store.episodes() == episodes
            and replay_store.store_digest == store.store_digest),
        "episode_counters_match_store_status_and_terminal_exactly": all(
            status.get(name) == count and terminal.get(name) == count
            for name, count in counts.items()),
        "capacity_episodes_are_isolated_from_learning_and_induction_store": (
            not main_store.quarantined
            and not capacity_ids.intersection(main_ids)
            and all(not _contains(row.get("payload", {}), episode_id)
                    for row in other_events for episode_id in capacity_ids)),
        "final_store_digest_is_last_episode_event_digest": (
            not episode_events or episode_events[-1].get(
                "payload", {}).get("details", {}).get("store_digest")
            == store.store_digest),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "exact observation-only mapping of retained-capacity terminal "
            "labels into common decision episodes; the isolated store has no "
            "learning, induction, transition-value, policy, score, or win-rate "
            "authority"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "episodes_encoded": len(episodes),
            "effect_without_goal_relief": counts[
                "fdas_retained_capacity_episodes_effect_without_relief"],
            "goal_relief_observed": counts[
                "fdas_retained_capacity_episodes_goal_relief"],
            "no_effect_observed": counts[
                "fdas_retained_capacity_episodes_no_effect"],
            "terminal_labels": len(observed_labels),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
