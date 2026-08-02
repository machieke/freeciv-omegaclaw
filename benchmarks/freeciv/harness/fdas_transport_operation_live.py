"""Audit a paired engine-live FDAS founder/ferry operation shadow cohort."""

from collections import Counter
import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash


COHORT = "fdas_transport_operation_shadow_diagnostic_v1"
MECHANISM = "fdas-founder-transport-shadow/1.0"
REQUIRED_RESOURCE_KINDS = frozenset((
    "action_budget", "actor", "move_points", "tile_occupancy",
    "transport_seat",
))


def _load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _load_events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical_path(path, repo=None):
    absolute = os.path.abspath(path)
    if repo is not None:
        relative = os.path.relpath(absolute, os.path.abspath(repo))
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
            return relative.replace(os.sep, "/")
    return absolute


def _percentile(values, fraction):
    rows = sorted(float(value) for value in values)
    if not rows:
        return None
    index = min(
        len(rows) - 1,
        max(0, int(round((len(rows) - 1) * fraction))))
    return rows[index]


def _latency(events, name):
    values = tuple(
        row["payload"]["value"] for row in events
        if (row["type"] == "metric_sample"
            and row["payload"].get("name") == name))
    return {
        "count": len(values),
        "maximum_ms": max(values) if values else None,
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
    }


def _arm_directory(root, arm):
    arm_root = os.path.join(
        root, "games", "impact_pair", COHORT, arm, "e_full_loop")
    candidates = []
    if os.path.isdir(arm_root):
        for name in sorted(os.listdir(arm_root)):
            path = os.path.join(arm_root, name)
            if os.path.isfile(os.path.join(path, "manifest.json")):
                candidates.append(path)
    if len(candidates) != 1:
        raise ValueError(
            "expected exactly one {} game, found {}".format(
                arm, len(candidates)))
    return candidates[0]


def _audit_arm(root, arm, repo=None):
    game_dir = _arm_directory(root, arm)
    names = (
        "events.jsonl", "fdas-transport-lifecycle.json", "manifest.json",
        "status.json",
    )
    paths = dict((name, os.path.join(game_dir, name)) for name in names)
    absent = tuple(name for name, path in paths.items() if not os.path.isfile(path))
    if absent:
        raise ValueError("missing {} evidence: {}".format(
            arm, ", ".join(absent)))
    events = _load_events(paths["events.jsonl"])
    manifest = _load_json(paths["manifest.json"])
    status = _load_json(paths["status.json"])
    lifecycle = _load_json(paths["fdas-transport-lifecycle.json"])
    unsigned_lifecycle = dict(lifecycle)
    lifecycle_digest = unsigned_lifecycle.pop("lifecycle_digest", None)
    records = lifecycle.get("operation_store", {}).get("records", [])
    assemblies = lifecycle.get("assemblies", [])
    operation_events = tuple(
        row for row in events
        if row["payload"].get("mechanism") == MECHANISM)
    event_counts = Counter(row["type"] for row in operation_events)
    operation_ids = {
        row["payload"].get("operation_id") for row in operation_events}
    projected_ids = {
        row["payload"].get("details", {}).get("operation_id")
        for row in events if row["type"] == "operation_projected"}
    claims = tuple(
        claim for row in operation_events
        for claim in row["payload"].get("claims", []))
    resource_kinds = {
        claim.get("resource", {}).get("kind") for claim in claims}
    event_ids = {row.get("event_id") for row in events}
    causal_edges_valid = bool(operation_events) and all(
        row.get("caused_by")
        and all(parent in event_ids for parent in row["caused_by"])
        for row in operation_events)
    declaration = manifest.get("dependent_atomspace", {})
    config = declaration.get("config", {})
    projection = config.get("projection", {})
    domains = config.get("domain_authority", {})
    capability_manifest = declaration.get("manifest", {})
    capabilities = capability_manifest.get("capabilities", {})
    declared_intents = capability_manifest.get(
        "transport_operation_intents", {})
    completed = tuple(row for row in events if row["type"] == "run_completed")
    failed = tuple(row for row in events if row["type"] == "run_failed")
    authority = tuple(
        row for row in events
        if row["type"] == "atomspace_authority_decision")
    sent = tuple(row for row in events if row["type"] == "action_sent")
    results = tuple(row for row in events if row["type"] == "action_result")
    record = records[0] if len(records) == 1 else {}
    assembly = assemblies[0] if len(assemblies) == 1 else {}
    operation_id = record.get("spec", {}).get("operation_id")
    fdas_projection_latency = _latency(
        events, "fdas_projection_latency_ms")
    full_controller_latency = _latency(
        events, "turn_full_loop_latency_ms")
    checks = {
        "action_results_are_complete_and_accepted": (
            len(sent) == len(results) == status.get("engine_actions")
            and bool(sent)
            and all(row["payload"].get("status") == "accepted"
                    for row in results)
            and status.get("rejected_actions") == 0),
        "configured_intent_is_diagnostic_only": (
            declared_intents.get("schema_version") == "1.0"
            and declared_intents.get("mode")
            == "diagnostic-configured-shadow-only"
            and declared_intents.get("policy_authority") is False
            and len(declared_intents.get("intents_by_seed", {}).get(
                str(manifest.get("seed")), [])) == 1),
        "engine_run_completed_at_horizon": (
            len(completed) == 1 and not failed
            and status.get("completed") is True
            and status.get("horizon_reached") is True),
        "fdas_projection_p95_within_budget": (
            fdas_projection_latency["p95_ms"] is not None
            and fdas_projection_latency["p95_ms"] <= 150.0),
        "lifecycle_bundle_is_canonical_and_unquarantined": (
            lifecycle.get("schema_version") == 1
            and lifecycle.get("controller_identity")
            == "freeciv-founder-transport-lifecycle/1.0"
            and lifecycle.get("policy_authority") is False
            and lifecycle.get("shadow_only") is True
            and lifecycle.get("operation_store", {}).get(
                "quarantine_reason") is None
            and lifecycle_digest == structural_hash(unsigned_lifecycle)),
        "manifest_is_transport_operation_shadow_only": (
            declaration.get("config_source")
            == "profile/dependent_atomspace_transport_operation_shadow.yaml"
            and declaration.get("manifest_source")
            == "profile/fdas_manifest_transport_operation_shadow.json"
            and config.get("enabled") is True
            and config.get("shadow_enabled") is True
            and config.get("authority_enabled") is False
            and domains and not any(domains.values())
            and projection.get("unit") is True
            and projection.get("route_corridors") is True
            and projection.get("transport") is True
            and projection.get("operations") is True
            and capability_manifest.get("policy_authority") is False
            and capabilities.get("transport_operation_projection")
            == "shadow-live"),
        "operation_is_durably_resolved_from_authoritative_change": (
            len(records) == len(assemblies) == 1
            and operation_id
            and assembly.get("intent", {}).get("founder_unit_id") == 102
            and record.get("progress", {}).get("state") == "abandoned"
            and record.get("progress", {}).get("terminal_reason")
            == "required-founder-removed"),
        "operation_projection_matches_lifecycle": (
            len(operation_ids) == 1
            and operation_id in operation_ids
            and operation_id in projected_ids),
        "operation_resource_contract_is_complete": (
            REQUIRED_RESOURCE_KINDS.issubset(resource_kinds)
            and all(claim.get("source_operation_id") == operation_id
                    for claim in claims)),
        "operation_shadow_events_are_non_authorizing": (
            bool(operation_events)
            and all(
                row["payload"].get("policy_authority") is False
                and row["payload"].get("shadow_only") is True
                and row["payload"].get("selected") is False
                for row in operation_events)
            and not authority
            and status.get("fdas_authority_actions") == 0
            and status.get("operation_authority_actions") == 0),
        "registration_reestimation_and_resolution_are_observed": (
            event_counts["operation_reserved"] == 1
            and event_counts["operation_step_selected"] >= 1
            and event_counts["operation_abandoned"] == 1
            and event_counts["operation_step_committed"] == 0
            and event_counts["operation_completed"] == 0),
        "transport_status_counters_match_events": (
            status.get("fdas_transport_operations") == 1
            and status.get("fdas_transport_action_matches") == 0
            and status.get("fdas_transport_completions") == 0
            and status.get("fdas_transport_failures") == 1
            and status.get("fdas_transport_reconciliations")
            == len(operation_events)),
        "transition_events_have_existing_causal_parents": causal_edges_valid,
        "source_is_clean": manifest.get("source", {}).get("dirty") is False,
    }
    return {
        "acceptance": {
            "accepted": all(checks.values()),
            "checks": checks,
            "performance_observation": {
                "full_controller_p95_target_ms": 500.0,
                "full_controller_p95_within_target": bool(
                    full_controller_latency["p95_ms"] is not None
                    and full_controller_latency["p95_ms"] <= 500.0),
            },
        },
        "arm": arm,
        "evidence": dict(
            (name, {"path": _logical_path(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "event_counts": dict(sorted(event_counts.items())),
        "latency": {
            "fdas_projection": fdas_projection_latency,
            "full_controller": full_controller_latency,
        },
        "operation_id": operation_id,
        "resource_kinds": sorted(value for value in resource_kinds if value),
        "source": manifest.get("source"),
        "summary": {
            "accepted_action_results": sum(
                row["payload"].get("status") == "accepted" for row in results),
            "action_matches": status.get("fdas_transport_action_matches"),
            "actions": len(sent),
            "operations": status.get("fdas_transport_operations"),
            "reconciliations": status.get("fdas_transport_reconciliations"),
        },
    }


def audit_fdas_transport_operation_live(root, repo=None):
    """Verify grounded operation registration without implying authority."""
    root = os.path.abspath(root)
    aggregate_path = os.path.join(root, "impact-aggregate.json")
    summary_path = os.path.join(root, "impact-run-summary.json")
    if not os.path.isfile(aggregate_path) or not os.path.isfile(summary_path):
        raise ValueError("paired aggregate and run summary are required")
    aggregate = _load_json(aggregate_path)
    run_summary = _load_json(summary_path)
    arms = tuple(_audit_arm(root, arm, repo) for arm in ("baseline", "treatment"))
    commits = {arm["source"].get("commit") for arm in arms}
    implementation_hashes = {
        arm["source"].get("implementation_sha256") for arm in arms}
    operation_ids = {arm["operation_id"] for arm in arms}
    pair_checks = {
        "both_arms_pass_operation_acceptance": all(
            arm["acceptance"]["accepted"] for arm in arms),
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
        "operation_identity_is_deterministic_across_pair": (
            len(operation_ids) == 1 and None not in operation_ids),
        "paired_source_is_clean_and_stable": (
            len(commits) == 1 and None not in commits
            and len(implementation_hashes) == 1
            and None not in implementation_hashes
            and run_summary.get("source_stable") is True
            and aggregate.get("source_freeze", {}).get("passed") is True),
    }
    report = {
        "acceptance": {"accepted": all(pair_checks.values()), "checks": pair_checks},
        "arms": arms,
        "claim_scope": (
            "configured founder/ferry operation assembly, durable projection, "
            "resource contract, re-estimation, and fail-closed abandonment; "
            "no action-match, operation-completion, authority, score, or gameplay "
            "improvement claim"),
        "cohort": COHORT,
        "evidence": {
            "impact_aggregate": {
                "path": _logical_path(aggregate_path, repo),
                "sha256": _sha256(aggregate_path),
            },
            "impact_run_summary": {
                "path": _logical_path(summary_path, repo),
                "sha256": _sha256(summary_path),
            },
        },
        "schema_version": "1.0",
        "source": {
            "commit": next(iter(commits)),
            "implementation_sha256": next(iter(implementation_hashes)),
        },
        "summary": {
            "accepted_action_results": sum(
                arm["summary"]["accepted_action_results"] for arm in arms),
            "action_matches": sum(
                arm["summary"]["action_matches"] for arm in arms),
            "actions": sum(arm["summary"]["actions"] for arm in arms),
            "operations": sum(arm["summary"]["operations"] for arm in arms),
            "reconciliations": sum(
                arm["summary"]["reconciliations"] for arm in arms),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
