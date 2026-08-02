"""Deterministic audit for one non-authorizing FDAS expansion shadow run."""

from collections import deque
import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash


_EXPANSION_TYPES = frozenset((
    "fdas_expansion_found_city",
    "fdas_expansion_recover_population",
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


def _causal_path(ancestor, descendant, parents):
    pending = deque(((descendant, (descendant,)),))
    visited = set()
    while pending:
        event_id, reverse_path = pending.popleft()
        if event_id == ancestor:
            return tuple(reversed(reverse_path))
        if event_id in visited:
            continue
        visited.add(event_id)
        for parent in sorted(parents.get(event_id, ())):
            pending.append((parent, reverse_path + (parent,)))
    return ()


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


def _logical_path(path, repo=None):
    absolute = os.path.abspath(path)
    if repo is not None:
        relative = os.path.relpath(absolute, os.path.abspath(repo))
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
            return relative.replace(os.sep, "/")
    return absolute


def audit_fdas_expansion_live(game_dir, repo=None):
    """Verify persistence, exact legacy matching, effects, and no authority."""
    game_dir = os.path.abspath(game_dir)
    names = (
        "events.jsonl", "fdas-expansion-operations.json",
        "manifest.json", "status.json")
    paths = dict((name, os.path.join(game_dir, name)) for name in names)
    absent = tuple(name for name, path in paths.items() if not os.path.isfile(path))
    if absent:
        raise ValueError("missing engine evidence files: {}".format(
            ", ".join(absent)))

    events = _load_events(paths["events.jsonl"])
    manifest = _load_json(paths["manifest.json"])
    status = _load_json(paths["status.json"])
    store = _load_json(paths["fdas-expansion-operations.json"])
    by_id = dict((row["event_id"], row) for row in events)
    if len(by_id) != len(events):
        raise ValueError("events contain duplicate event IDs")
    parents = dict(
        (event_id, tuple(row.get("caused_by", ())))
        for event_id, row in by_id.items())

    sent = tuple(row for row in events if row["type"] == "action_sent")
    results = tuple(row for row in events if row["type"] == "action_result")
    authority = tuple(
        row for row in events
        if row["type"] == "atomspace_authority_decision")
    projected = tuple(
        row for row in events if row["type"] == "operation_projected")
    lifecycle = dict(
        (event_type, tuple(row for row in events if row["type"] == event_type))
        for event_type in (
            "operation_activated", "operation_completed",
            "operation_expired", "operation_failed"))
    completed_events = tuple(
        row for row in events if row["type"] == "run_completed")
    failed_events = tuple(
        row for row in events if row["type"] == "run_failed")
    terminal = (
        completed_events[0]["payload"].get("summary", {})
        if len(completed_events) == 1 else {})

    semantic_store = dict(store)
    claimed_store_digest = semantic_store.pop("store_digest", None)
    store_valid = bool(
        store.get("store_identity") == "freeciv-operation-store/1.0"
        and store.get("quarantine_reason") is None
        and claimed_store_digest == structural_hash(semantic_store))
    records = tuple(store.get("records", ()))
    record_by_id = dict(
        (row.get("spec", {}).get("operation_id"), row) for row in records)
    record_ids_unique = bool(
        None not in record_by_id and len(record_by_id) == len(records))
    spec_digests_valid = all(
        row["spec"].get("spec_digest") == structural_hash(dict(
            (key, value) for key, value in row["spec"].items()
            if key != "spec_digest"))
        for row in records)
    expected_types = all(
        row["spec"].get("operation_type") in _EXPANSION_TYPES
        for row in records)

    projected_ids = tuple(
        row["payload"].get("details", {}).get("operation_id")
        for row in projected)
    operation_rows = []
    causal_failures = []
    for operation_id, record in sorted(record_by_id.items()):
        progress = record["progress"]
        spec = record["spec"]
        activations = tuple(
            row for row in lifecycle["operation_activated"]
            if row["payload"].get("operation_id") == operation_id)
        completions = tuple(
            row for row in lifecycle["operation_completed"]
            if row["payload"].get("operation_id") == operation_id)
        expirations = tuple(
            row for row in lifecycle["operation_expired"]
            if row["payload"].get("operation_id") == operation_id)
        failures = tuple(
            row for row in lifecycle["operation_failed"]
            if row["payload"].get("operation_id") == operation_id)
        activation = activations[0] if len(activations) == 1 else None
        completion = completions[0] if len(completions) == 1 else None
        expiration = expirations[0] if len(expirations) == 1 else None
        exact_sent = ()
        exact_result = ()
        paths_for_record = {}
        if activation is not None:
            exact_sent = tuple(
                row for row in sent
                if (row["payload"].get("action")
                    == activation["payload"].get("next_action")
                    and row["payload"].get("snapshot_id")
                    == activation["payload"].get("snapshot_id")))
            if len(exact_sent) == 1:
                exact_result = tuple(
                    row for row in results
                    if row["payload"].get("action_id")
                    == exact_sent[0]["payload"].get("action_id"))
            if len(exact_sent) == 1 and len(exact_result) == 1:
                paths_for_record["sent_to_result"] = _causal_path(
                    exact_sent[0]["event_id"], exact_result[0]["event_id"],
                    parents)
                paths_for_record["result_to_activation"] = _causal_path(
                    exact_result[0]["event_id"], activation["event_id"],
                    parents)
            if completion is not None:
                paths_for_record["activation_to_completion"] = _causal_path(
                    activation["event_id"], completion["event_id"], parents)
        expected_terminal_count = {
            "completed": len(completions),
            "expired": len(expirations),
            "failed": len(failures),
        }.get(progress.get("state"), 0)
        causal = dict(
            (name, bool(path)) for name, path in paths_for_record.items())
        if progress.get("state") == "completed" and not (
                len(activations) == 1
                and len(completions) == 1
                and len(exact_sent) == 1
                and len(exact_result) == 1
                and exact_result[0]["payload"].get("status") == "accepted"
                and all(causal.values())
                and len(causal) == 3):
            causal_failures.append(operation_id)
        operation_rows.append({
            "activation_count": len(activations),
            "attempt_count": progress.get("attempt_count"),
            "causal": causal,
            "completion_count": len(completions),
            "exact_action_results": len(exact_result),
            "exact_actions_sent": len(exact_sent),
            "expiration_count": len(expirations),
            "failure_count": len(failures),
            "operation_id": operation_id,
            "operation_type": spec.get("operation_type"),
            "projected": operation_id in projected_ids,
            "state": progress.get("state"),
            "terminal_event_count": expected_terminal_count,
            "terminal_reason": progress.get("terminal_reason"),
        })

    completed_records = tuple(
        row for row in records if row["progress"].get("state") == "completed")
    expired_records = tuple(
        row for row in records if row["progress"].get("state") == "expired")
    failed_records = tuple(
        row for row in records if row["progress"].get("state") == "failed")
    cold = tuple(
        row for row in events
        if (row["type"] == "metric_sample"
            and row["payload"].get("name") == "fdas_projection_latency_ms"
            and row["payload"].get("labels", {}).get("cold_verified")
            == "True"))
    projection_latency = _latency(events, "fdas_projection_latency_ms")
    shadow_latency = _latency(events, "fdas_shadow_evaluation_latency_ms")
    full_latency = _latency(events, "turn_full_loop_latency_ms")
    config = manifest.get("dependent_atomspace", {}).get("config", {})
    fdas_manifest = manifest.get("dependent_atomspace", {}).get("manifest", {})
    domains = config.get("domain_authority", {})
    checks = {
        "all_action_results_accepted": (
            len(sent) == len(results) == status.get("engine_actions")
            and all(row["payload"].get("status") == "accepted"
                    for row in results)
            and status.get("rejected_actions") == 0),
        "all_completed_operations_have_exact_causal_legacy_actions": (
            bool(completed_records) and not causal_failures),
        "all_lifecycle_events_are_non_authorizing_shadow": all(
            row["payload"].get("policy_authority") is False
            and row["payload"].get("shadow_only") is True
            and row["payload"].get("selected") is False
            for rows in lifecycle.values() for row in rows),
        "all_operations_are_projected": (
            bool(records) and set(record_by_id) == set(projected_ids)),
        "cold_verification_is_equivalent": (
            bool(cold) and all(row["payload"]["labels"].get(
                "cold_equivalent") == "True" for row in cold)),
        "completed_effects_are_explicit": all(
            row["progress"].get("attempt_count") == 1
            and row["progress"].get("terminal_reason")
            == "authoritative-expansion-effect-observed"
            for row in completed_records),
        "engine_run_completed_at_horizon": (
            len(completed_events) == 1 and not failed_events
            and status.get("completed") is True
            and status.get("horizon_reached") is True),
        "expirations_are_unattempted_not_failures": all(
            row["progress"].get("attempt_count") == 0
            and row["progress"].get("terminal_reason")
            == "operation-deadline-passed-without-expansion-effect"
            for row in expired_records),
        "fdas_projection_p95_within_budget": (
            projection_latency["p95_ms"] is not None
            and projection_latency["p95_ms"] <= 150.0),
        "manifest_is_expansion_shadow_only": (
            config.get("enabled") is True
            and config.get("shadow_enabled") is True
            and config.get("authority_enabled") is False
            and domains and not any(domains.values())
            and fdas_manifest.get("policy_authority") is False
            and fdas_manifest.get("status") == "shadow-live"),
        "no_failed_expansion_effects": (
            not failed_records and not lifecycle["operation_failed"]),
        "no_fdas_authority_events": not authority,
        "source_is_clean": manifest.get("source", {}).get("dirty") is False,
        "store_is_valid_and_unquarantined": (
            store_valid and record_ids_unique and spec_digests_valid
            and expected_types),
        "terminal_counters_match_evidence": (
            terminal.get("fdas_expansion_action_matches")
            == len(lifecycle["operation_activated"])
            and terminal.get("fdas_expansion_completions")
            == len(completed_records)
            and terminal.get("fdas_expansion_expirations")
            == len(expired_records)
            and terminal.get("fdas_expansion_failures")
            == len(failed_records)),
    }
    report = {
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
        "claim_scope": (
            "expansion-shadow-lifecycle-and-behavior-preservation; "
            "no-policy-authority-or-gameplay-improvement-claim"),
        "evidence": dict(
            (name, {"path": _logical_path(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "latency": {
            "fdas_projection": projection_latency,
            "fdas_shadow_evaluation": shadow_latency,
            "full_controller": full_latency,
        },
        "operations": operation_rows,
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "accepted_action_results": sum(
                row["payload"].get("status") == "accepted" for row in results),
            "action_matches": len(lifecycle["operation_activated"]),
            "actions": len(sent),
            "cold_verifications": len(cold),
            "completions": len(completed_records),
            "expirations": len(expired_records),
            "failures": len(failed_records),
            "operations": len(records),
            "projected_operations": len(projected_ids),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
