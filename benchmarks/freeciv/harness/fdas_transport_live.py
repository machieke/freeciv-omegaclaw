"""Deterministic audit for a paired FDAS transport-capability shadow cohort."""

from collections import Counter
import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash


_COHORT = "fdas_transport_shadow_diagnostic_v1"
_PROXY_SERIES = (
    "26ba7124249f34fd3050ef29bf191bd4d8808018+patch-sha256:"
    "d8f586ad5741106beb23b24c3e5f599fd74cb8e1b0f0a33961f2c966e66fe7d4")
_REQUIRED_PREDICATES = frozenset((
    "transport-accepts-unit-class",
    "transport-backed-by-unit",
    "transport-cargo-compatible",
    "transport-compatible-founder",
    "transport-seat-available",
    "transport-seat-resource",
    "unit-ruleset-founder-capable",
))
_OPERATION_EVENTS = frozenset((
    "operation_activated", "operation_completed", "operation_expired",
    "operation_failed", "operation_projected",
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
    values = sorted(float(value) for value in values)
    if not values:
        return None
    index = min(
        len(values) - 1,
        max(0, int(round((len(values) - 1) * fraction))))
    return values[index]


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
        root, "games", "impact_pair", _COHORT, arm, "e_full_loop")
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
    names = ("events.jsonl", "manifest.json", "status.json")
    paths = dict((name, os.path.join(game_dir, name)) for name in names)
    absent = tuple(name for name, path in paths.items() if not os.path.isfile(path))
    if absent:
        raise ValueError("missing {} evidence: {}".format(
            arm, ", ".join(absent)))
    events = _load_events(paths["events.jsonl"])
    manifest = _load_json(paths["manifest.json"])
    status = _load_json(paths["status.json"])
    event_ids = tuple(row.get("event_id") for row in events)
    sent = tuple(row for row in events if row["type"] == "action_sent")
    results = tuple(row for row in events if row["type"] == "action_result")
    completed = tuple(row for row in events if row["type"] == "run_completed")
    failed = tuple(row for row in events if row["type"] == "run_failed")
    authority = tuple(
        row for row in events
        if row["type"] == "atomspace_authority_decision")
    operations = tuple(row for row in events if row["type"] in _OPERATION_EVENTS)
    transport_scopes = tuple(
        row for row in events
        if (row["type"] == "scope_materialized"
            and row["payload"].get("details", {}).get("scope_kind")
            == "transport"))
    predicates = Counter(
        row["payload"]["details"]["predicate"] for row in events
        if (row["type"] == "atom_rederived"
            and row["payload"].get("details", {}).get("predicate", "")
            .startswith(("transport-", "unit-carried-",
                         "unit-ruleset-founder-"))))
    cold = tuple(
        row for row in events
        if (row["type"] == "metric_sample"
            and row["payload"].get("name") == "fdas_projection_latency_ms"
            and row["payload"].get("labels", {}).get("cold_verified")
            == "True"))
    projection_latency = _latency(events, "fdas_projection_latency_ms")
    shadow_latency = _latency(events, "fdas_shadow_evaluation_latency_ms")
    full_latency = _latency(events, "turn_full_loop_latency_ms")
    declaration = manifest.get("dependent_atomspace", {})
    config = declaration.get("config", {})
    projection = config.get("projection", {})
    domains = config.get("domain_authority", {})
    capability_manifest = declaration.get("manifest", {})
    capabilities = capability_manifest.get("capabilities", {})
    terminal = (
        completed[0]["payload"].get("summary", {})
        if len(completed) == 1 else {})
    checks = {
        "action_results_are_complete_and_accepted": (
            len(sent) == len(results) == status.get("engine_actions")
            and bool(sent)
            and all(row["payload"].get("status") == "accepted"
                    for row in results)
            and status.get("rejected_actions") == 0),
        "cold_verification_is_equivalent": (
            bool(cold) and all(
                row["payload"]["labels"].get("cold_equivalent") == "True"
                for row in cold)),
        "engine_run_completed_at_horizon": (
            len(completed) == 1 and not failed
            and status.get("completed") is True
            and status.get("horizon_reached") is True
            and terminal.get("horizon_reached") is True),
        "event_ids_are_complete_and_unique": (
            bool(event_ids) and None not in event_ids
            and len(event_ids) == len(set(event_ids))),
        "fdas_projection_p95_within_budget": (
            projection_latency["p95_ms"] is not None
            and projection_latency["p95_ms"] <= 150.0),
        "ferry_start_condition_is_declared": (
            manifest.get("release_game_config", {}).get("startunits") == "csdf"),
        "manifest_is_transport_capability_shadow_only": (
            declaration.get("config_source")
            == "profile/dependent_atomspace_transport_shadow.yaml"
            and declaration.get("manifest_source")
            == "profile/fdas_manifest_transport_shadow.json"
            and config.get("enabled") is True
            and config.get("shadow_enabled") is True
            and config.get("authority_enabled") is False
            and domains and not any(domains.values())
            and projection.get("ruleset") is True
            and projection.get("unit") is True
            and projection.get("transport") is True
            and projection.get("operations") is False
            and capability_manifest.get("policy_authority") is False
            and capability_manifest.get("status") == "shadow-live"
            and capabilities.get("transport_capability_projection")
            == "shadow-live"
            and capabilities.get("transport_operation_projection")
            == "component-only"),
        "no_capacity_contradiction": predicates.get(
            "transport-at-capacity", 0) == 0,
        "no_fdas_authority": (
            not authority
            and terminal.get("fdas_authority_actions") == 0
            and terminal.get("operation_authority_actions") == 0),
        "no_transport_operation_was_fabricated": not operations,
        "proxy_contract_includes_transport_semantic_fix": (
            manifest.get("engine", {}).get("proxy_commit") == _PROXY_SERIES),
        "required_transport_predicates_are_live": (
            _REQUIRED_PREDICATES.issubset(predicates)),
        "seat_capacity_is_present_for_every_transport_scope": (
            bool(transport_scopes)
            and predicates.get("transport-seat-resource")
            == len(transport_scopes)
            and predicates.get("transport-seat-available")
            == len(transport_scopes)),
        "source_is_clean": manifest.get("source", {}).get("dirty") is False,
    }
    return {
        "acceptance": {
            "accepted": all(checks.values()),
            "checks": checks,
            "performance_observation": {
                "full_controller_p95_target_ms": 500.0,
                "full_controller_p95_within_target": bool(
                    full_latency["p95_ms"] is not None
                    and full_latency["p95_ms"] <= 500.0),
            },
        },
        "arm": arm,
        "evidence": dict(
            (name, {"path": _logical_path(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "latency": {
            "fdas_projection": projection_latency,
            "fdas_shadow_evaluation": shadow_latency,
            "full_controller": full_latency,
        },
        "predicates": dict(sorted(predicates.items())),
        "source": manifest.get("source"),
        "summary": {
            "accepted_action_results": sum(
                row["payload"].get("status") == "accepted" for row in results),
            "actions": len(sent),
            "cold_verifications": len(cold),
            "transport_scopes": len(transport_scopes),
        },
    }


def audit_fdas_transport_live(root, repo=None):
    """Verify clean paired transport capability, load, and no authority."""
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
    pair_checks = {
        "both_arms_pass_capability_acceptance": all(
            arm["acceptance"]["accepted"] for arm in arms),
        "cohort_completed_without_failures": (
            aggregate.get("complete_pairs") == 1
            and not aggregate.get("failures")
            and run_summary.get("completed") == 2
            and run_summary.get("infrastructure_failures") == 0),
        "cohort_is_predeclared_and_claim_ineligible": (
            aggregate.get("design", {}).get("cohort") == _COHORT
            and aggregate.get("design", {}).get("claim_eligible") is False
            and aggregate.get("claim_evaluation", {}).get("status")
            == "ineligible"),
        "paired_source_is_clean_and_stable": (
            len(commits) == 1 and None not in commits
            and len(implementation_hashes) == 1
            and None not in implementation_hashes
            and run_summary.get("source_stable") is True
            and aggregate.get("source_freeze", {}).get("passed") is True),
    }
    report = {
        "acceptance": {
            "accepted": all(pair_checks.values()),
            "checks": pair_checks,
        },
        "arms": arms,
        "claim_scope": (
            "transport-capability-shadow-and-corrected-seat-readout; "
            "no-operation-authority-or-gameplay-improvement-claim"),
        "cohort": _COHORT,
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
            "actions": sum(arm["summary"]["actions"] for arm in arms),
            "cold_verifications": sum(
                arm["summary"]["cold_verifications"] for arm in arms),
            "transport_scopes": sum(
                arm["summary"]["transport_scopes"] for arm in arms),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
