"""Deterministic offline export of retained-capacity decision episodes."""

import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning.fdas_capacity_episode_bridge import (
    FdasRetainedCapacityEpisodeBridge,
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

from .fdas_replacement_capacity_retained_queue_outcome_cohort import (
    audit_fdas_replacement_capacity_retained_queue_outcome_cohort,
)
from .statistics import wilson


DATASET_IDENTITY = "fdas-retained-capacity-episode-dataset/1.0"
DEFAULT_ADEQUACY_THRESHOLDS = {
    "effect_without_goal_relief": 10,
    "games_with_episode": 20,
    "goal_relief_observed": 10,
    "no_effect_observed": 10,
    "terminal_episodes": 30,
}
DEFAULT_PARENT_RECURRENCE_THRESHOLDS = {
    "label": 2,
    "positive_relief": 1,
    "product": 1,
    "relief": 1,
}
_MECHANISM = "fdas-replacement-capacity-retained-queue-lifecycle"


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


def _logical(path, repo=None):
    absolute = os.path.abspath(path)
    if repo is not None:
        relative = os.path.relpath(absolute, os.path.abspath(repo))
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
            return relative.replace(os.sep, "/")
    return absolute


def _thresholds(values):
    result = dict(DEFAULT_ADEQUACY_THRESHOLDS if values is None else values)
    if set(result) != set(DEFAULT_ADEQUACY_THRESHOLDS):
        raise ValueError("retained capacity adequacy thresholds differ")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1
           for value in result.values()):
        raise ValueError("retained capacity adequacy thresholds are invalid")
    return result


def _episode_complete(episode):
    context = dict(episode.context_signature)
    prefixes = tuple(episode.provenance_ids)
    return bool(
        episode.before_revision_id and episode.after_revision_id
        and len(episode.source_atom_ids) == 1
        and episode.resource_claim_ids
        and any(value.startswith("requirement-set:")
                for value in episode.grounding_result_ids)
        and any(value.startswith("operation-digest:")
                for value in episode.grounding_result_ids)
        and any(value.startswith("proposal-event:") for value in prefixes)
        and any(value.startswith("outcome-label:") for value in prefixes)
        and context.get("requirement_set_id")
        and context.get("action_submitted") == "false"
        and episode.prediction_ids == ()
        and episode.execution_event_id is None)


def export_fdas_retained_capacity_episode_dataset(
        run_dir, expected_seeds, expected_source_commit,
        expected_parent_report_hash, repo=None, adequacy_thresholds=None,
        parent_recurrence_thresholds=None):
    """Export exact labels and report evidence adequacy without fitting."""
    run_dir = os.path.abspath(run_dir)
    seeds = tuple(int(value) for value in expected_seeds)
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("retained capacity dataset seeds must be unique")
    if not isinstance(expected_source_commit, str) or not expected_source_commit:
        raise ValueError("retained capacity dataset source commit is required")
    if (not isinstance(expected_parent_report_hash, str)
            or not expected_parent_report_hash):
        raise ValueError("retained capacity parent report hash is required")
    thresholds = _thresholds(adequacy_thresholds)
    parent_thresholds = dict(
        DEFAULT_PARENT_RECURRENCE_THRESHOLDS
        if parent_recurrence_thresholds is None
        else parent_recurrence_thresholds)
    if (set(parent_thresholds) != set(DEFAULT_PARENT_RECURRENCE_THRESHOLDS)
            or any(isinstance(value, bool) or not isinstance(value, int)
                   or value < 0 for value in parent_thresholds.values())):
        raise ValueError("retained capacity parent thresholds are invalid")
    parent = audit_fdas_replacement_capacity_retained_queue_outcome_cohort(
        run_dir, seeds, expected_source_commit=expected_source_commit,
        repo=repo,
        minimum_games_with_label=parent_thresholds["label"],
        minimum_games_with_product=parent_thresholds["product"],
        minimum_games_with_relief=parent_thresholds["relief"],
        minimum_positive_relief=parent_thresholds["positive_relief"])
    parent_rows = dict((row["seed"], row) for row in parent["games"])
    game_rows = []
    episode_rows = []
    extraction_errors = []
    for seed in seeds:
        game_dir = os.path.join(
            run_dir, "games", "main", "e_full_loop", "{}-00".format(seed))
        manifest_path = os.path.join(game_dir, "manifest.json")
        events_path = os.path.join(game_dir, "events.jsonl")
        outcome_path = os.path.join(
            game_dir, "fdas-retained-capacity-outcome-labels.json")
        manifest = _load(manifest_path)
        events = _events(events_path)
        game_id = manifest.get("game_id")
        outcome_identity = structural_hash([
            manifest.get("manifest_identity"), manifest.get("attempt_id"),
            game_id, FdasRetainedCapacityOutcomeLabeler.LABELER_IDENTITY,
            RETAINED_CAPACITY_OUTCOME_TARGET,
        ])
        store = FdasRetainedCapacityOutcomeStore.load(
            outcome_path, outcome_identity)
        proposals = tuple(
            row for row in events
            if row.get("type") == "operation_proposed"
            and row.get("payload", {}).get("mechanism") == _MECHANISM)
        proposal_by_operation = dict(
            (row.get("payload", {}).get("operation_id"), row)
            for row in proposals)
        encoded_ids = []
        error = None
        if store.quarantined:
            error = store.quarantine_reason
        else:
            local_store = DecisionEpisodeStore(
                "offline-retained-capacity-dataset:{}".format(game_id))
            bridge = FdasRetainedCapacityEpisodeBridge(local_store)
            try:
                for label in store.labels():
                    if label.status != "observed":
                        raise ValueError("retained capacity label is nonterminal")
                    proposal = proposal_by_operation.get(label.operation_id)
                    if proposal is None:
                        raise ValueError(
                            "retained capacity label lacks proposal evidence")
                    episode = bridge.encode(label, proposal)
                    encoded_ids.append(episode.episode_id)
                    episode_rows.append({
                        "episode": episode.to_dict(),
                        "game_id": game_id,
                        "label_id": label.label_id,
                        "parent_audit_hash": parent_rows[seed]["report_hash"],
                        "proposal_event_id": proposal.get("event_id"),
                        "seed": seed,
                    })
            except (KeyError, TypeError, ValueError) as caught:
                error = str(caught)
        if error is not None:
            extraction_errors.append({"error": error, "seed": seed})
        game_rows.append({
            "episode_count": len(encoded_ids),
            "episode_ids": sorted(encoded_ids),
            "game_dir": _logical(game_dir, repo),
            "game_id": game_id,
            "parent_audit_accepted": parent_rows[seed]["accepted"],
            "parent_audit_hash": parent_rows[seed]["report_hash"],
            "seed": seed,
            "source_commit": manifest.get("source", {}).get("commit"),
            "source_dirty": manifest.get("source", {}).get("dirty"),
        })
    episode_rows.sort(key=lambda row: (
        row["seed"], row["episode"]["episode_id"]))
    identity_sets = {
        "episode": [row["episode"]["episode_id"] for row in episode_rows],
        "game": [row["game_id"] for row in game_rows],
        "label": [row["label_id"] for row in episode_rows],
        "operation": [row["episode"]["operation_id"] for row in episode_rows],
        "seed": [row["seed"] for row in game_rows],
    }
    identities_unique = all(
        len(values) == len(set(values)) for values in identity_sets.values())
    status_counts = {
        status: sum(row["episode"]["outcome_status"] == status
                    for row in episode_rows)
        for status in (
            "no-effect-observed", "effect-without-goal-relief",
            "goal-relief-observed")
    }
    games_with_episode = sum(row["episode_count"] > 0 for row in game_rows)
    terminal_episodes = len(episode_rows)
    # Reparse the exported form so the completeness gate covers serialization.
    complete_provenance = all(
        _episode_complete(DecisionEpisode.from_dict(row["episode"]))
        for row in episode_rows)
    measures = {
        "effect_without_goal_relief": status_counts[
            "effect-without-goal-relief"],
        "games_with_episode": games_with_episode,
        "goal_relief_observed": status_counts["goal-relief-observed"],
        "no_effect_observed": status_counts["no-effect-observed"],
        "terminal_episodes": terminal_episodes,
    }
    adequacy_checks = {
        name + "_minimum_met": measures[name] >= thresholds[name]
        for name in sorted(thresholds)
    }
    adequacy_checks.update({
        "discovery_and_confirmation_cohorts_declared_disjoint": False,
        "every_episode_has_exact_complete_provenance": complete_provenance,
    })
    rates = {
        "durable_goal_relief_per_terminal_episode": wilson(
            status_counts["goal-relief-observed"], terminal_episodes),
        "exact_product_effect_per_terminal_episode": wilson(
            status_counts["effect-without-goal-relief"]
            + status_counts["goal-relief-observed"], terminal_episodes),
        "games_with_episode": wilson(games_with_episode, len(game_rows)),
    }
    mechanics_checks = {
        "all_fixed_games_are_retained_once": (
            len(game_rows) == len(seeds)
            and tuple(row["seed"] for row in game_rows) == seeds),
        "all_parent_outcome_audits_pass": (
            parent["acceptance"]["accepted"]
            and all(row["parent_audit_accepted"] for row in game_rows)),
        "all_sources_are_clean_and_exact_commit_bound": all(
            row["source_commit"] == expected_source_commit
            and row["source_dirty"] is False for row in game_rows),
        "episode_export_has_no_extraction_errors": not extraction_errors,
        "episode_provenance_is_complete_and_prediction_free": (
            complete_provenance),
        "game_seed_operation_label_and_episode_identities_are_unique": (
            identities_unique),
        "parent_report_matches_frozen_structural_hash": (
            parent["structural_hash"] == expected_parent_report_hash),
        "terminal_status_partition_is_complete": (
            sum(status_counts.values()) == terminal_episodes),
    }
    report = {
        "acceptance": {
            "accepted": all(mechanics_checks.values()),
            "checks": mechanics_checks,
        },
        "adequacy": {
            "checks": adequacy_checks,
            "decision": (
                "eligible-for-preregistered-discovery-and-confirmation"
                if all(adequacy_checks.values()) else "insufficient-evidence"),
            "measures": measures,
            "thresholds": thresholds,
        },
        "claim_scope": (
            "deterministic offline reconstruction of the reused PR92 "
            "diagnostic cohort into observation-only episodes; descriptive "
            "fixed-cohort intervals only; no fitted model, calibration, "
            "learning, readout, causal, score, or win-rate claim"),
        "dataset_identity": DATASET_IDENTITY,
        "episodes": episode_rows,
        "extraction_errors": extraction_errors,
        "games": game_rows,
        "parent_cohort_hash": parent["structural_hash"],
        "rates": rates,
        "schema_version": "1.0",
        "source": {
            "expected_commit": expected_source_commit,
            "run_dir": _logical(run_dir, repo),
            "seeds": list(seeds),
        },
        "summary": {
            "fixed_games": len(game_rows),
            "games_with_episode": games_with_episode,
            "terminal_episodes": terminal_episodes,
            **status_counts,
        },
        "truth_mutated": False,
        "learning_authority": False,
        "policy_authority": False,
        "readout_authority": False,
    }
    report["dataset_hash"] = structural_hash(report)
    return report
