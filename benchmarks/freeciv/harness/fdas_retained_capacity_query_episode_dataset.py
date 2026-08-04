"""Deterministic cohort export of retained-capacity query/episode rows."""

from concurrent.futures import ProcessPoolExecutor
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import (
    DecisionEpisodeStore,
    FdasRetainedCapacityQueryEpisodeRow,
    FdasRetainedCapacityTransitionQueryStore,
    RETAINED_CAPACITY_EPISODE_BRIDGE_IDENTITY,
    RETAINED_CAPACITY_TRANSITION_QUERY_IDENTITY,
    join_retained_capacity_transition_queries,
)

from .fdas_retained_capacity_transition_query_live import (
    audit_fdas_retained_capacity_transition_query_live,
)


DATASET_IDENTITY = "fdas-retained-capacity-query-episode-dataset/1.0"
_TERMINAL_STATUSES = (
    "no-effect-observed", "effect-without-goal-relief",
    "goal-relief-observed",
)


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _logical(path, repo=None):
    absolute = os.path.abspath(path)
    if repo is not None:
        relative = os.path.relpath(absolute, os.path.abspath(repo))
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
            return relative.replace(os.sep, "/")
    return absolute


def _expected_hashes(values, seeds):
    if values is None:
        return None
    result = dict((int(seed), str(value)) for seed, value in dict(values).items())
    if (set(result) != set(seeds)
            or any(not value for value in result.values())):
        raise ValueError("retained capacity parent audit hashes differ")
    return result


def _audit_parent(arguments):
    seed, game_dir, repo = arguments
    return seed, audit_fdas_retained_capacity_transition_query_live(
        game_dir, repo=repo)


def export_fdas_retained_capacity_query_episode_dataset(
        run_dir, expected_seeds, expected_source_commit, repo=None,
        expected_parent_report_hashes=None, audit_workers=1):
    """Export every query as a terminal or explicitly censored row."""
    run_dir = os.path.abspath(run_dir)
    seeds = tuple(int(value) for value in expected_seeds)
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("retained capacity query dataset seeds must be unique")
    if not isinstance(expected_source_commit, str) or not expected_source_commit:
        raise ValueError("retained capacity query dataset commit is required")
    expected_hashes = _expected_hashes(
        expected_parent_report_hashes, seeds)
    audit_workers = int(audit_workers)
    if audit_workers < 1:
        raise ValueError("retained capacity audit workers must be positive")
    game_dirs = dict((seed, os.path.join(
        run_dir, "games", "main", "e_full_loop", "{}-00".format(seed)))
                     for seed in seeds)
    audit_arguments = tuple(
        (seed, game_dirs[seed], repo) for seed in seeds)
    if audit_workers == 1:
        parents = dict(_audit_parent(value) for value in audit_arguments)
    else:
        with ProcessPoolExecutor(max_workers=audit_workers) as executor:
            parents = dict(executor.map(_audit_parent, audit_arguments))

    game_rows = []
    joined_rows = []
    extraction_errors = []
    parent_hashes = {}
    for seed in seeds:
        game_dir = game_dirs[seed]
        manifest_path = os.path.join(game_dir, "manifest.json")
        manifest = _load(manifest_path)
        game_id = manifest.get("game_id")
        parent = parents[seed]
        parent_hashes[seed] = parent["structural_hash"]
        query_identity = structural_hash([
            manifest.get("manifest_identity"), manifest.get("attempt_id"),
            game_id, RETAINED_CAPACITY_TRANSITION_QUERY_IDENTITY,
        ])
        episode_identity = structural_hash([
            manifest.get("manifest_identity"), manifest.get("attempt_id"),
            game_id, RETAINED_CAPACITY_EPISODE_BRIDGE_IDENTITY,
        ])
        query_store = FdasRetainedCapacityTransitionQueryStore.load(
            os.path.join(
                game_dir, "fdas-retained-capacity-transition-queries.json"),
            query_identity)
        episode_store = DecisionEpisodeStore.load(
            os.path.join(
                game_dir, "fdas-retained-capacity-decision-episodes.json"),
            episode_identity)
        rows = ()
        error = None
        try:
            rows = join_retained_capacity_transition_queries(
                query_store, episode_store)
            reparsed = tuple(
                FdasRetainedCapacityQueryEpisodeRow.from_dict(row.to_dict())
                for row in rows)
            if reparsed != rows:
                raise ValueError("retained capacity query rows do not roundtrip")
        except (KeyError, TypeError, ValueError) as caught:
            error = str(caught)
            extraction_errors.append({"error": error, "seed": seed})
        for row in rows:
            joined_rows.append({
                "game_id": game_id,
                "parent_audit_hash": parent["structural_hash"],
                "row": row.to_dict(),
                "seed": seed,
            })
        game_rows.append({
            "censored_rows": sum(
                row.observation_status == "right-censored" for row in rows),
            "game_dir": _logical(game_dir, repo),
            "game_id": game_id,
            "parent_audit_accepted": parent["acceptance"]["accepted"],
            "parent_audit_hash": parent["structural_hash"],
            "query_rows": len(rows),
            "seed": seed,
            "source_commit": manifest.get("source", {}).get("commit"),
            "source_dirty": manifest.get("source", {}).get("dirty"),
            "terminal_rows": sum(
                row.observation_status == "terminal-observed" for row in rows),
        })

    joined_rows.sort(key=lambda value: (
        value["seed"], value["row"]["row_id"]))
    status_counts = dict((status, sum(
        value["row"]["outcome_status"] == status for value in joined_rows))
                         for status in _TERMINAL_STATUSES)
    terminal_rows = sum(
        value["row"]["observation_status"] == "terminal-observed"
        for value in joined_rows)
    censored_rows = sum(
        value["row"]["observation_status"] == "right-censored"
        for value in joined_rows)
    feature_groups = {}
    for value in joined_rows:
        row = value["row"]
        signature = row["feature_signature"]
        group = feature_groups.setdefault(signature, {
            "censored_rows": 0,
            "feature_schema": row["query"]["feature_schema"],
            "features": row["query"]["features"],
            "query_rows": 0,
            "status_counts": dict((status, 0) for status in _TERMINAL_STATUSES),
            "terminal_rows": 0,
        })
        group["query_rows"] += 1
        if row["observation_status"] == "right-censored":
            group["censored_rows"] += 1
        else:
            group["terminal_rows"] += 1
            group["status_counts"][row["outcome_status"]] += 1
    feature_rows = [dict({"feature_signature": signature}, **value)
                    for signature, value in sorted(feature_groups.items())]

    identity_sets = {
        "episode": [value["row"]["episode_id"] for value in joined_rows
                    if value["row"]["episode_id"] is not None],
        "game": [value["game_id"] for value in game_rows],
        "label": [value["row"]["query"]["label_id"]
                  for value in joined_rows],
        "operation": [value["row"]["query"]["operation_id"]
                      for value in joined_rows],
        "query": [value["row"]["query"]["query_id"]
                  for value in joined_rows],
        "row": [value["row"]["row_id"] for value in joined_rows],
        "seed": [value["seed"] for value in game_rows],
    }
    identities_unique = all(
        len(values) == len(set(values))
        for values in identity_sets.values())
    checks = {
        "all_fixed_games_are_retained_once": (
            len(game_rows) == len(seeds)
            and tuple(value["seed"] for value in game_rows) == seeds),
        "all_parent_query_audits_pass": all(
            value["parent_audit_accepted"] for value in game_rows),
        "all_queries_partition_into_terminal_or_right_censored_rows": (
            terminal_rows + censored_rows == len(joined_rows)),
        "all_sources_are_clean_and_exact_commit_bound": all(
            value["source_commit"] == expected_source_commit
            and value["source_dirty"] is False for value in game_rows),
        "expected_parent_audit_hashes_match": (
            expected_hashes is None or parent_hashes == expected_hashes),
        "game_seed_operation_label_query_episode_and_row_identities_unique": (
            identities_unique),
        "query_episode_export_has_no_extraction_errors": (
            not extraction_errors),
        "terminal_status_partition_is_complete": (
            sum(status_counts.values()) == terminal_rows),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "deterministic outcome-safe join of proposal-time abstaining "
            "queries to terminal retained-capacity episodes with pending "
            "queries retained as right-censored; no model, calibration, "
            "learning, readout, causal, score, or win-rate claim"),
        "dataset_identity": DATASET_IDENTITY,
        "extraction_errors": extraction_errors,
        "feature_signatures": feature_rows,
        "games": game_rows,
        "rows": joined_rows,
        "schema_version": "1.0",
        "source": {
            "expected_commit": expected_source_commit,
            "expected_parent_report_hashes": (
                None if expected_hashes is None else dict(
                    (str(seed), expected_hashes[seed]) for seed in seeds)),
            "run_dir": _logical(run_dir, repo),
            "seeds": list(seeds),
        },
        "summary": {
            "fixed_games": len(game_rows),
            "games_with_queries": sum(
                value["query_rows"] > 0 for value in game_rows),
            "query_rows": len(joined_rows),
            "right_censored_rows": censored_rows,
            "terminal_rows": terminal_rows,
            "zero_query_games": sum(
                value["query_rows"] == 0 for value in game_rows),
            **status_counts,
        },
        "truth_mutated": False,
        "learning_authority": False,
        "policy_authority": False,
        "readout_authority": False,
    }
    report["dataset_hash"] = structural_hash(report)
    return report
