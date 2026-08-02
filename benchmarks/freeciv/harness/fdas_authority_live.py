"""Deterministic audit for a bounded FDAS authority engine run."""

from collections import Counter, deque
import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash


_AUTHORITY_CHECKS = {
    "fdas-bounded-city-stability/1.0": frozenset((
        "domain-authority-gate",
        "revision-current-evaluation",
        "legacy-winner-fdas-route-binding",
        "bounded-city-stability-contract",
        "authority-pressure-readout",
        "resource-and-packet-schedule",
        "exact-fdas-commit-validation",
    )),
    "fdas-bounded-defense-fortification/1.0": frozenset((
        "domain-authority-gate",
        "legacy-defense-category-gate",
        "revision-current-evaluation",
        "legacy-winner-fdas-fortification-route-binding",
        "bounded-defense-fortification-contract",
        "authority-pressure-readout",
        "resource-and-packet-schedule",
        "exact-fdas-commit-validation",
    )),
}
_COMMIT_CHECKS = frozenset((
    "snapshot-and-legal-action-refresh",
    "fdas-revision-identity",
    "fdas-source-supports",
    "fdas-candidate-identity",
    "server-legal-action-membership",
    "causal-effect-and-requirement-firewall",
    "domain-authority-gate",
))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _load_events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


def _action_key(action):
    return json.dumps(
        action, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _bounded_action_shape(authority_slice, action):
    if authority_slice == "fdas-bounded-city-stability/1.0":
        return bool(
            isinstance(action, dict)
            and action.get("action_type") == "city_governor"
            and isinstance(action.get("city_id"), int)
            and not isinstance(action.get("city_id"), bool)
            and action.get("target") == {"food_surplus_reserve": 1})
    if authority_slice == "fdas-bounded-defense-fortification/1.0":
        return bool(
            isinstance(action, dict)
            and set(action) == {"action_type", "actor_id"}
            and action.get("action_type") == "unit_fortify"
            and isinstance(action.get("actor_id"), int)
            and not isinstance(action.get("actor_id"), bool))
    return False


def _causal_path(ancestor, descendant, parents):
    """Return one deterministic ancestor-to-descendant event path."""
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


def _logical_path(path, repo=None):
    absolute = os.path.abspath(path)
    if repo is not None:
        try:
            relative = os.path.relpath(absolute, os.path.abspath(repo))
            if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
                return relative.replace(os.sep, "/")
        except ValueError:
            pass
    return absolute


def audit_fdas_authority_live(game_dir, repo=None):
    """Audit one completed engine-live game with bounded FDAS authority."""
    game_dir = os.path.abspath(game_dir)
    paths = dict(
        (name, os.path.join(game_dir, name))
        for name in ("events.jsonl", "manifest.json", "status.json"))
    absent = tuple(name for name, path in paths.items() if not os.path.isfile(path))
    if absent:
        raise ValueError("missing engine evidence files: {}".format(", ".join(absent)))

    events = _load_events(paths["events.jsonl"])
    manifest = _load_json(paths["manifest.json"])
    status = _load_json(paths["status.json"])
    by_id = dict((row["event_id"], row) for row in events)
    if len(by_id) != len(events):
        raise ValueError("events contain duplicate event IDs")
    parents = dict((event_id, tuple(row.get("caused_by", ())))
                   for event_id, row in by_id.items())

    authority = tuple(
        row for row in events if row["type"] == "atomspace_authority_decision")
    authorized = tuple(
        row for row in authority
        if row["payload"].get("details", {}).get("status") == "authorized")
    fallbacks = tuple(
        row for row in authority
        if row["payload"].get("details", {}).get("status") == "fallback")
    sent = tuple(row for row in events if row["type"] == "action_sent")
    results = tuple(row for row in events if row["type"] == "action_result")
    completed = tuple(row for row in events if row["type"] == "run_completed")
    failed = tuple(row for row in events if row["type"] == "run_failed")

    authorization_rows = []
    binding_failures = []
    for decision in authorized:
        details = decision["payload"]["details"]
        matching_sent = []
        for row in sent:
            payload = row["payload"]
            if (_action_key(payload.get("action", {})) != details.get("action_key")
                    or payload.get("snapshot_id") != details.get("snapshot_id")):
                continue
            path = _causal_path(decision["event_id"], row["event_id"], parents)
            if path:
                matching_sent.append((row, path))
        sent_row = matching_sent[0][0] if len(matching_sent) == 1 else None
        sent_path = matching_sent[0][1] if len(matching_sent) == 1 else ()
        matching_results = []
        if sent_row is not None:
            action_id = sent_row["payload"].get("action_id")
            for row in results:
                if row["payload"].get("action_id") != action_id:
                    continue
                path = _causal_path(sent_row["event_id"], row["event_id"], parents)
                if path:
                    matching_results.append((row, path))
        result_row = (
            matching_results[0][0] if len(matching_results) == 1 else None)
        result_path = (
            matching_results[0][1] if len(matching_results) == 1 else ())
        if len(matching_sent) != 1 or len(matching_results) != 1:
            binding_failures.append({
                "authority_event_id": decision["event_id"],
                "matching_action_results": len(matching_results),
                "matching_actions_sent": len(matching_sent),
            })
        commit = details.get("commit_validation") or {}
        scheduling = details.get("scheduling") or {}
        resource = scheduling.get("resource_schedule") or {}
        packet = scheduling.get("packet_schedule") or {}
        pressure = details.get("authority_pressure") or {}
        try:
            bounded_action = json.loads(details.get("action_key") or "null")
        except (TypeError, ValueError):
            bounded_action = None
        authorization_rows.append({
            "action_id": (
                None if sent_row is None else sent_row["payload"].get("action_id")),
            "action_key": details.get("action_key"),
            "action_result_event_id": (
                None if result_row is None else result_row["event_id"]),
            "action_result_status": (
                None if result_row is None else result_row["payload"].get("status")),
            "action_sent_event_id": (
                None if sent_row is None else sent_row["event_id"]),
            "authority_event_id": decision["event_id"],
            "authority_checks": list(details.get("checks", ())),
            "authority_slice": details.get("authority_slice"),
            "authority_pressure_status": pressure.get("status"),
            "authority_to_send_distance": (
                None if not sent_path else len(sent_path) - 1),
            "authority_to_send_path_types": [
                by_id[event_id]["type"] for event_id in sent_path],
            "commit_disposition": commit.get("disposition"),
            "commit_checks": list(commit.get("checks", ())),
            "commit_current_revision_id": commit.get("current_revision_id"),
            "commit_current_snapshot_id": commit.get("current_snapshot_id"),
            "commit_execution_authority": commit.get("execution_authority"),
            "event_revision_id": decision["payload"].get("revision_id"),
            "event_snapshot_id": decision["payload"].get("snapshot_id"),
            "operation_id": details.get("operation_id"),
            "packet_conserved": packet.get("conserved"),
            "packet_policy_authority": packet.get("policy_authority"),
            "plan_materialization_authorized": commit.get(
                "plan_materialization_authorized"),
            "policy_authority": details.get("policy_authority"),
            "resource_policy_authority": resource.get("policy_authority"),
            "resource_shadow_only": resource.get("shadow_only"),
            "resource_status": resource.get("status"),
            "scheduling_policy_authority": scheduling.get("policy_authority"),
            "result_causal_distance": (
                None if not result_path else len(result_path) - 1),
            "revision_id": details.get("revision_id"),
            "snapshot_id": details.get("snapshot_id"),
            "turn": decision["turn"],
            "within_bounded_action_shape": (
                _bounded_action_shape(
                    details.get("authority_slice"), bounded_action)),
        })

    terminal_summary = (
        completed[0]["payload"].get("summary", {}) if len(completed) == 1 else {})
    source = manifest.get("source", {})
    fdas_manifest = manifest.get("dependent_atomspace", {})
    fallback_reasons = Counter(
        row["payload"].get("details", {}).get("reason") or "unspecified"
        for row in fallbacks)
    checks = {
        "all_authorizations_bind_one_causal_action_and_result": (
            not binding_failures and len(authorization_rows) == len(authorized)),
        "all_authorized_actions_accepted": all(
            row["action_result_status"] == "accepted"
            for row in authorization_rows),
        "all_commit_validations_are_materialization_only": all(
            row["commit_disposition"] == "commit"
            and row["plan_materialization_authorized"] is True
            and row["commit_execution_authority"] is False
            for row in authorization_rows),
        "all_commit_and_event_identities_are_current": all(
            row["commit_current_snapshot_id"] == row["snapshot_id"]
            and row["commit_current_revision_id"] == row["revision_id"]
            and row["event_snapshot_id"] == row["snapshot_id"]
            and row["event_revision_id"] == row["revision_id"]
            for row in authorization_rows),
        "all_declared_authority_and_commit_checks_ran": all(
            row["authority_slice"] in _AUTHORITY_CHECKS
            and _AUTHORITY_CHECKS[row["authority_slice"]].issubset(
                row["authority_checks"])
            and _COMMIT_CHECKS.issubset(row["commit_checks"])
            for row in authorization_rows),
        "all_packet_schedules_are_conserved_non_authoritative": all(
            row["packet_conserved"] is True
            and row["packet_policy_authority"] in (None, False)
            and row["scheduling_policy_authority"] is False
            for row in authorization_rows),
        "all_pressure_readouts_complete": all(
            row["authority_pressure_status"] == "complete"
            for row in authorization_rows),
        "all_resource_schedules_are_exact_shadow": all(
            row["resource_status"] == "exact"
            and row["resource_shadow_only"] is True
            and row["resource_policy_authority"] is False
            for row in authorization_rows),
        "all_readouts_are_classified": len(authority) == len(authorized) + len(fallbacks),
        "authority_counters_match_terminal_summary": (
            terminal_summary.get("fdas_authority_opportunities") == len(authority)
            and terminal_summary.get("fdas_authority_actions") == len(authorized)
            and terminal_summary.get("fdas_authority_fallbacks") == len(fallbacks)),
        "bounded_policy_authority_is_explicit": all(
            row["policy_authority"] is True for row in authorization_rows),
        "bounded_action_shape_is_not_broadened": all(
            row["within_bounded_action_shape"] is True
            for row in authorization_rows),
        "clean_pinned_source": (
            source.get("dirty") is False
            and isinstance(source.get("commit"), str)
            and len(source["commit"]) == 40),
        "completed_exactly_once_without_run_failure": (
            len(completed) == 1 and not failed),
        "horizon_reached": terminal_summary.get("horizon_reached") is True,
        "positive_authority_observed": bool(authorized),
        "zero_rejected_engine_actions": status.get("rejected_actions") == 0,
    }
    report = {
        "acceptance": {
            "accepted": all(checks.values()),
            "checks": checks,
            "failures": binding_failures,
        },
        "authorizations": authorization_rows,
        "evidence": {
            "events": {
                "path": _logical_path(paths["events.jsonl"], repo),
                "sha256": _sha256(paths["events.jsonl"]),
            },
            "manifest": {
                "path": _logical_path(paths["manifest.json"], repo),
                "sha256": _sha256(paths["manifest.json"]),
            },
            "status": {
                "path": _logical_path(paths["status.json"], repo),
                "sha256": _sha256(paths["status.json"]),
            },
        },
        "fallback_reasons": dict(sorted(fallback_reasons.items())),
        "identity": {
            "configuration_hash": manifest.get("configuration_hash"),
            "fdas_config_source": fdas_manifest.get("config_source"),
            "fdas_declaration_hash": fdas_manifest.get("declaration_hash"),
            "fdas_manifest_source": fdas_manifest.get("manifest_source"),
            "game_id": manifest.get("game_id"),
            "implementation_sha256": source.get("implementation_sha256"),
            "seed": manifest.get("seed"),
            "source_commit": source.get("commit"),
            "source_dirty": source.get("dirty"),
            "turn_limit": manifest.get("turn_limit"),
        },
        "schema_version": "1.0",
        "summary": {
            "action_results": len(results),
            "actions_sent": len(sent),
            "authority_opportunities": len(authority),
            "authorized": len(authorized),
            "event_count": len(events),
            "fallbacks": len(fallbacks),
            "max_turn": max((row["turn"] for row in events), default=None),
            "run_completed": len(completed),
            "run_failed": len(failed),
        },
        "terminal_summary": {
            "actions": terminal_summary.get("actions"),
            "fdas_authority_actions": terminal_summary.get("fdas_authority_actions"),
            "fdas_authority_fallbacks": terminal_summary.get(
                "fdas_authority_fallbacks"),
            "fdas_authority_opportunities": terminal_summary.get(
                "fdas_authority_opportunities"),
            "horizon_reached": terminal_summary.get("horizon_reached"),
            "opponent_score": terminal_summary.get("opponent_score"),
            "score": terminal_summary.get("score"),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
