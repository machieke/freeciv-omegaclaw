"""Audit paired FDAS legacy-bound observation return evidence."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash


COHORT = "fdas_observation_execution_shadow_diagnostic_v1"
MECHANISM = "fdas-visibility-observation-execution/1.0"
RETURN_SOURCE = "authoritative-player-visibility-delta"


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


def _arm_directory(root, arm):
    parent = os.path.join(
        root, "games", "impact_pair", COHORT, arm, "e_full_loop")
    candidates = tuple(
        os.path.join(parent, name) for name in sorted(os.listdir(parent))
        if os.path.isfile(os.path.join(parent, name, "manifest.json"))) \
        if os.path.isdir(parent) else ()
    if len(candidates) != 1:
        raise ValueError("expected one {} observation-return game".format(arm))
    return candidates[0]


def _audit_arm(root, arm, repo=None):
    game_dir = _arm_directory(root, arm)
    paths = dict(
        (name, os.path.join(game_dir, name))
        for name in ("events.jsonl", "manifest.json", "status.json"))
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError("missing {} evidence: {}".format(
            arm, ", ".join(missing)))
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    by_id = dict((row["event_id"], row) for row in events)
    position = dict((row["event_id"], index)
                    for index, row in enumerate(events))
    declaration = manifest.get("dependent_atomspace", {})
    config = declaration.get("config", {})
    capability_manifest = declaration.get("manifest", {})
    execution = capability_manifest.get("observation_execution", {})
    pressures = tuple(
        row for row in events
        if (row["type"] == "pressure_propagated"
            and row["payload"].get("config", {}).get("mechanism")
            == MECHANISM))
    packets = tuple(
        row for row in events
        if (row["type"] == "packet_reserved"
            and row["payload"].get("summary", {}).get("mechanism")
            == MECHANISM))
    revalidations = tuple(
        row for row in events
        if row["type"] == "candidate_revalidated"
        and row["payload"].get("summary", {}).get(
            "binding", {}).get("operation_id", "").startswith("observe:"))
    returns = tuple(
        row for row in events
        if row["type"] == "packet_returned"
        and row["payload"].get("summary", {}).get(
            "authoritative_return", {}).get(
                "evidence_token", {}).get("source") == RETURN_SOURCE)
    observations = tuple(
        row for row in events
        if (row["type"] == "observation"
            and row["payload"].get("source") == RETURN_SOURCE))
    sent = tuple(row for row in events if row["type"] == "action_sent")
    results = tuple(row for row in events if row["type"] == "action_result")
    authority = tuple(
        row for row in events
        if row["type"] == "atomspace_authority_decision")
    return_rows = []
    for returned in returns:
        value = returned["payload"]["summary"]["authoritative_return"]
        binding_hash = value.get("binding_hash")
        operation_id = value.get("operation_id")
        matching_revalidations = tuple(
            row for row in revalidations
            if (row["payload"]["summary"]["binding"].get("binding_hash")
                == binding_hash
                and row["payload"]["summary"]["binding"].get("operation_id")
                == operation_id))
        revalidated = (
            matching_revalidations[0]
            if len(matching_revalidations) == 1 else None)
        binding = (
            revalidated["payload"]["summary"]["binding"]
            if revalidated is not None else {})
        validation = (
            revalidated["payload"]["summary"]["commit_validation"]
            if revalidated is not None else {})
        matching_sent = tuple(
            row for row in sent
            if (row["payload"].get("action") == binding.get("action")
                and revalidated is not None
                and position[row["event_id"]] > position[
                    revalidated["event_id"]]
                and position[row["event_id"]] < position[returned["event_id"]]))
        action_sent = matching_sent[0] if len(matching_sent) == 1 else None
        matching_results = tuple(
            row for row in results
            if (action_sent is not None
                and action_sent["event_id"] in row.get("caused_by", ())))
        action_result = (
            matching_results[0] if len(matching_results) == 1 else None)
        token = value.get("evidence_token", {})
        matching_observations = tuple(
            row for row in observations
            if row["payload"].get("provenance_id") == token.get("token_id"))
        observation = (
            matching_observations[0]
            if len(matching_observations) == 1 else None)
        return_rows.append({
            "action_result_accepted_and_causal": (
                action_result is not None
                and action_result["payload"].get("status") == "accepted"
                and action_result["event_id"] in returned.get("caused_by", ())),
            "binding_is_exact_non_authorizing_move": (
                binding.get("action", {}).get("action_type") == "unit_move"
                and binding.get("action_key")
                and binding.get("policy_authority") is False
                and binding.get("selection_record", {}).get("selected") is True),
            "commit_is_exact_and_non_authorizing": (
                validation.get("status") == "committed"
                and validation.get("reason") is None
                and validation.get("policy_authority") is False),
            "evidence_is_registered_after_return": (
                observation is not None
                and returned["event_id"] in observation.get("caused_by", ())
                and token.get("source") == RETURN_SOURCE
                and token.get("observation_policy", {}).get("channel")
                == "observe"),
            "operation_id": operation_id,
            "outcome_id": value.get("outcome_id"),
            "visibility_delta_count": len(value.get(
                "new_visible_tile_ids", ())),
        })
    planning_closed = all(
        row["payload"]["summary"].get("truth_mutated") is False
        and row["payload"]["summary"].get("evidence_count_before_planning")
        == row["payload"]["summary"].get("evidence_count_after_planning")
        and row["payload"]["summary"].get(
            "evidence_store_hash_before_planning")
        == row["payload"]["summary"].get(
            "evidence_store_hash_after_planning")
        for row in packets)
    checks = {
        "actions_complete_and_accepted": (
            bool(sent) and len(sent) == len(results)
            == status.get("engine_actions")
            and all(row["payload"].get("status") == "accepted"
                    for row in results)
            and status.get("rejected_actions") == 0),
        "manifest_binds_legacy_selected_return_mode": (
            declaration.get("config_source")
            == "profile/dependent_atomspace_observation_execution_shadow.yaml"
            and declaration.get("manifest_source")
            == "profile/fdas_manifest_observation_execution_shadow.json"
            and manifest.get("release_game_config", {}).get("fogofwar") is True
            and config.get("authority_enabled") is False
            and config.get("projection", {}).get("beliefs") is True
            and config.get("inference", {}).get(
                "uncertain_assessment_enabled") is True
            and execution.get("mode")
            == "legacy-selected-visibility-return-shadow"
            and execution.get("authoritative_return_required") is True
            and execution.get("policy_authority") is False),
        "planning_firewall_stays_closed_until_return": (
            bool(packets) and len(pressures) == len(packets)
            and planning_closed),
        "every_binding_commit_return_is_complete": (
            bool(returns)
            and len(revalidations) == len(returns) == len(observations)
            and all(all(value for key, value in row.items()
                        if key not in (
                            "operation_id", "outcome_id",
                            "visibility_delta_count"))
                    for row in return_rows)),
        "status_counters_match_return_artifacts": (
            status.get("fdas_observation_action_bindings")
            == len(revalidations)
            and status.get("fdas_observation_commit_revalidations")
            == len(revalidations)
            and status.get("fdas_observation_authoritative_returns")
            == len(returns)
            and status.get("fdas_observation_evidence_write_throughs")
            == len(observations)
            and status.get("fdas_observation_visibility_expansions")
            == sum(row["visibility_delta_count"] > 0 for row in return_rows)
            and status.get("fdas_observation_visibility_unchanged")
            == sum(row["visibility_delta_count"] == 0 for row in return_rows)),
        "no_enemy_absence_or_policy_authority": (
            all(row["outcome_id"] in (
                    "visibility-expanded", "no-visibility-expansion")
                for row in return_rows)
            and all("enemy" not in row["payload"].get("source", "")
                    for row in observations)
            and not authority
            and status.get("fdas_authority_actions") == 0
            and status.get("operation_authority_actions") == 0),
        "source_is_clean_and_horizon_completed": (
            manifest.get("source", {}).get("dirty") is False
            and status.get("completed") is True
            and status.get("horizon_reached") is True),
    }
    return {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "arm": arm,
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "source": manifest.get("source"),
        "summary": {
            "actions": len(sent),
            "bindings": len(revalidations),
            "evidence_returns": len(returns),
            "visibility_expansions": sum(
                row["visibility_delta_count"] > 0 for row in return_rows),
            "visibility_unchanged": sum(
                row["visibility_delta_count"] == 0 for row in return_rows),
        },
    }


def audit_fdas_observation_return_live(root, repo=None):
    root = os.path.abspath(root)
    aggregate_path = os.path.join(root, "impact-aggregate.json")
    summary_path = os.path.join(root, "impact-run-summary.json")
    if not os.path.isfile(aggregate_path) or not os.path.isfile(summary_path):
        raise ValueError("paired aggregate and run summary are required")
    aggregate = _load(aggregate_path)
    run_summary = _load(summary_path)
    arms = tuple(_audit_arm(root, arm, repo)
                 for arm in ("baseline", "treatment"))
    commits = {row["source"].get("commit") for row in arms}
    implementations = {
        row["source"].get("implementation_sha256") for row in arms}
    checks = {
        "both_arms_pass_return_acceptance": all(
            row["acceptance"]["accepted"] for row in arms),
        "cohort_completed_without_failures": (
            aggregate.get("complete_pairs") == 1
            and not aggregate.get("failures")
            and run_summary.get("completed") == 2
            and run_summary.get("infrastructure_failures") == 0),
        "cohort_is_predeclared_and_claim_ineligible": (
            aggregate.get("design", {}).get("cohort") == COHORT
            and aggregate.get("design", {}).get("claim_eligible") is False
            and aggregate.get("claim_evaluation", {}).get("status")
            == "ineligible"),
        "paired_source_is_clean_and_stable": (
            len(commits) == 1 and None not in commits
            and len(implementations) == 1 and None not in implementations
            and run_summary.get("source_stable") is True
            and aggregate.get("source_freeze", {}).get("passed") is True),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "arms": arms,
        "claim_scope": (
            "packet-budgeted visibility observation bound only to a byte-"
            "identical legacy-selected move, exact commit revalidation, fresh "
            "authoritative visibility return, selection-adjusted evidence "
            "registration, and zero policy authority; no FDAS action choice, "
            "enemy-absence, score, or gameplay-improvement claim"),
        "cohort": COHORT,
        "evidence": {
            "impact_aggregate": {
                "path": _logical(aggregate_path, repo),
                "sha256": _sha256(aggregate_path),
            },
            "impact_run_summary": {
                "path": _logical(summary_path, repo),
                "sha256": _sha256(summary_path),
            },
        },
        "schema_version": "1.0",
        "source": {
            "commit": next(iter(commits)),
            "implementation_sha256": next(iter(implementations)),
        },
        "summary": dict(
            (name, sum(row["summary"][name] for row in arms))
            for name in (
                "actions", "bindings", "evidence_returns",
                "visibility_expansions", "visibility_unchanged")),
    }
    report["structural_hash"] = structural_hash(report)
    return report
