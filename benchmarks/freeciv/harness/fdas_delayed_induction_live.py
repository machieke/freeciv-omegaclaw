"""Audit engine-live delayed FDAS induction labels and authority isolation."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.validator import validate_file
from freeciv_agent.planning import (
    CAUSAL_INDUCTION_FEATURE_SCHEMA,
    DURABLE_ACTOR_CITY_DEFENSE_TARGET,
    DURABLE_CITY_COVERAGE_TARGET,
    DecisionEpisodeStore,
    EpisodeInductionOutcomeLabelStore,
    INDUCTION_FEATURE_SCHEMA,
    delayed_outcome_episode_eligible,
)


ACTIVATION_TARGETS = {
    (
        "profile/dependent_atomspace_defense_delayed_induction_shadow.yaml",
        "profile/fdas_manifest_defense_delayed_induction_shadow.json",
    ): (DURABLE_CITY_COVERAGE_TARGET, 8, None),
    (
        "profile/"
        "dependent_atomspace_defense_actor_persistence_induction_shadow.yaml",
        "profile/"
        "fdas_manifest_defense_actor_persistence_induction_shadow.json",
    ): (DURABLE_ACTOR_CITY_DEFENSE_TARGET, 32, None),
    (
        "profile/"
        "dependent_atomspace_defense_actor_persistence_causal_"
        "induction_shadow.yaml",
        "profile/"
        "fdas_manifest_defense_actor_persistence_causal_"
        "induction_shadow.json",
    ): (
        DURABLE_ACTOR_CITY_DEFENSE_TARGET,
        32,
        CAUSAL_INDUCTION_FEATURE_SCHEMA,
    ),
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


def _verified_episode_store(path):
    raw = _load(path)
    identity = raw.get("persistence_identity")
    store = DecisionEpisodeStore.load(path, identity or "missing")
    return raw, store


def _verified_label_store(path):
    raw = _load(path)
    identity = raw.get("persistence_identity")
    store = EpisodeInductionOutcomeLabelStore.load(
        path, identity or "missing")
    return raw, store


def audit_fdas_delayed_induction_live(game_dir, repo=None):
    """Verify delayed labels are durable, due-turn safe, and non-authorizing."""
    game_dir = os.path.abspath(game_dir)
    paths = dict(
        (name, os.path.join(game_dir, name))
        for name in (
            "events.jsonl",
            "fdas-decision-episodes.json",
            "fdas-induction-outcome-labels.json",
            "manifest.json",
            "status.json",
        ))
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError("missing delayed-label evidence: {}".format(
            ", ".join(missing)))

    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    episode_raw, episode_store = _verified_episode_store(
        paths["fdas-decision-episodes.json"])
    label_raw, label_store = _verified_label_store(
        paths["fdas-induction-outcome-labels.json"])
    event_validation = validate_file(paths["events.jsonl"])

    declaration = manifest.get("dependent_atomspace", {})
    config = declaration.get("config", {})
    activation = declaration.get("manifest", {})
    capabilities = activation.get("capabilities", {})
    diagnostic = activation.get("delayed_induction_outcome_diagnostic")
    activation_sources = (
        declaration.get("config_source"),
        declaration.get("manifest_source"))
    expected_target, observation_window_turns, expected_feature_schema = (
        ACTIVATION_TARGETS.get(
            activation_sources,
            ("unrecognized-delayed-outcome-target", 0, None)))
    expected_diagnostic = {
        "induced_rule_readout": False,
        "observation_window_turns": observation_window_turns,
        "policy_authority": False,
        "target_id": expected_target,
    }
    if expected_feature_schema is not None:
        expected_diagnostic[
            "induction_feature_schema"] = expected_feature_schema
    episodes = episode_store.episodes()
    labels = label_store.labels()
    relief_episodes = tuple(
        value for value in episodes
        if delayed_outcome_episode_eligible(value, expected_target))
    observed_labels = tuple(
        value for value in labels if value.status == "observed")
    pending_labels = tuple(
        value for value in labels if value.status == "pending")
    open_events = tuple(
        value for value in events
        if value["type"] == "episode_outcome_label_opened")
    observed_events = tuple(
        value for value in events
        if value["type"] == "episode_outcome_label_observed")
    promotion_events = tuple(
        value for value in events
        if value["type"] == "induced_rule_promoted")

    label_by_episode = dict((value.episode_id, value) for value in labels)
    observed_event_labels = tuple(
        value["payload"].get("details", {}).get("label", {})
        for value in observed_events)
    event_policy_details = tuple(
        value["payload"].get("details", {})
        for value in open_events + observed_events)
    checks = {
        "activation_is_exact_default_off_shadow_target": (
            activation_sources in ACTIVATION_TARGETS
            and capabilities.get("delayed_induction_outcome_labels")
            == "shadow-live"
            and (
                expected_feature_schema is None
                or capabilities.get("causal_episode_feature_schema")
                == "shadow-live")
            and diagnostic == expected_diagnostic
            and config.get("learning", {}).get(
                "episode_attribution_enabled") is True
            and config.get("learning", {}).get("induction_enabled") is True
            and config.get("learning", {}).get(
                "induced_rule_readout_enabled") is False),
        "event_ledger_is_schema_valid_without_warnings": (
            event_validation.valid and not event_validation.warnings),
        "stores_are_hash_valid_and_not_quarantined": (
            episode_store.quarantined is False
            and label_store.quarantined is False
            and episode_raw.get("store_digest") == episode_store.store_digest
            and label_raw.get("store_digest") == label_store.store_digest),
        "episode_feature_schema_matches_activation": (
            bool(relief_episodes)
            and all(
                dict(value.context_signature).get(
                    "induction_feature_schema")
                == (expected_feature_schema or INDUCTION_FEATURE_SCHEMA)
                for value in relief_episodes)),
        "every_relief_episode_has_exactly_one_target_label": (
            bool(relief_episodes)
            and len(label_by_episode) == len(labels) == len(relief_episodes)
            and set(label_by_episode)
            == {value.episode_id for value in relief_episodes}
            and all(
                label.target_id == expected_target
                and label.episode_digest == episode.immutable_digest
                and label.relief_revision_id == episode.after_revision_id
                and label.relief_turn
                == (episode.observed_delta or {}).get("observed_turn")
                for episode in relief_episodes
                for label in (label_by_episode[episode.episode_id],))),
        "label_window_and_observation_timing_are_exact": (
            bool(observed_labels)
            and all(
                value.due_turn
                == value.relief_turn + observation_window_turns
                and (value.status != "observed"
                     or value.observed_turn >= value.due_turn)
                for value in labels)),
        "events_match_durable_lifecycle": (
            len(open_events) == len(labels)
            and len(observed_events) == len(observed_labels)
            and {value["payload"]["details"]["label"]["label_id"]
                 for value in open_events}
            == {value.label_id for value in labels}
            and {value.get("label_id") for value in observed_event_labels}
            == {value.label_id for value in observed_labels}
            and all(value.get("observed_turn", -1) >= value.get("due_turn", 0)
                    for value in observed_event_labels)
            and all(value.get("caused_by")
                    for value in open_events + observed_events)),
        "status_counters_match_durable_labels": (
            status.get("fdas_delayed_outcome_labels_opened") == len(labels)
            and status.get("fdas_delayed_outcome_labels_observed")
            == len(observed_labels)
            and status.get("fdas_delayed_outcome_labels_pending")
            == len(pending_labels)
            and status.get("fdas_delayed_outcome_positive")
            == sum(value.outcome is True for value in observed_labels)
            and status.get("fdas_delayed_outcome_negative")
            == sum(value.outcome is False for value in observed_labels)),
        "labels_have_zero_truth_policy_or_readout_authority": (
            not promotion_events
            and all(
                value.get("policy_authority") is False
                and value.get("readout_enabled") is False
                and value.get("truth_mutated") is False
                and value.get("label", {}).get("policy_authority") is False
                and value.get("label", {}).get("truth_mutated") is False
                for value in event_policy_details)),
        "source_is_clean_and_horizon_completed": (
            manifest.get("source", {}).get("dirty") is False
            and status.get("completed") is True
            and status.get("horizon_reached") is True),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "engine-live authoritative immediate relief opens one durable "
            "revision-bound delayed label for target {}; due-turn authoritative "
            "own state resolves it after exactly {} turns with zero truth "
            "mutation, policy authority, or induced-rule readout; no causal, "
            "score, or gameplay-improvement claim".format(
                expected_target, observation_window_turns)),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "labels_negative": sum(
                value.outcome is False for value in observed_labels),
            "labels_observed": len(observed_labels),
            "labels_opened": len(labels),
            "labels_pending": len(pending_labels),
            "labels_positive": sum(
                value.outcome is True for value in observed_labels),
            "induction_feature_schema": (
                expected_feature_schema or INDUCTION_FEATURE_SCHEMA),
            "observation_window_turns": observation_window_turns,
            "relief_episodes": len(relief_episodes),
            "target_id": expected_target,
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
