"""Audit one engine-live coordinated-replacement shadow lifecycle."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.validator import validate_file


_COMPONENT_ID = "fdas-coordinated-replacement-lifecycle"
_IDENTITY = "fdas-coordinated-replacement-lifecycle/1.0"
_OPERATION_TYPE = "fdas-defense:coordinated-replacement"
_STORE_IDENTITY = "freeciv-operation-store/1.0"
_TERMINAL_STATES = frozenset(("completed", "expired", "failed", "abandoned"))


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


def _spec_digest_valid(spec):
    material = dict(spec)
    claimed = material.pop("spec_digest", None)
    return isinstance(claimed, str) and claimed == structural_hash(material)


def _lifecycle_key(record):
    spec = record.get("spec", {})
    participants = dict(
        (row.get("role"), row.get("actor_id"))
        for row in spec.get("participants", ()))
    steps = spec.get("steps", ())
    if (set(participants) != {"replacement", "reinforcement"}
            or len(steps) != 2):
        return None
    return (
        participants["replacement"],
        participants["reinforcement"],
        steps[0].get("target_ref"),
        spec.get("target_ref"),
    )


def audit_fdas_replacement_live(game_dir, repo=None):
    """Verify durable, deduplicated, revision-bound shadow reconciliation."""
    game_dir = os.path.abspath(game_dir)
    names = (
        "events.jsonl", "fdas-coordinated-replacement-operations.json",
        "manifest.json", "status.json")
    paths = dict((name, os.path.join(game_dir, name)) for name in names)
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError("missing replacement evidence: {}".format(
            ", ".join(missing)))

    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    store = _load(paths["fdas-coordinated-replacement-operations.json"])
    validation = validate_file(paths["events.jsonl"])
    declaration = manifest.get("dependent_atomspace", {})
    activation = declaration.get("manifest", {})
    capabilities = activation.get("capabilities", {})

    semantic_store = dict(store)
    claimed_store_digest = semantic_store.pop("store_digest", None)
    records = tuple(store.get("records", ()))
    record_by_id = dict(
        (row.get("spec", {}).get("operation_id"), row) for row in records)
    record_ids_unique = bool(
        None not in record_by_id and len(record_by_id) == len(records))
    expected_persistence_identity = structural_hash([
        manifest.get("manifest_identity"), manifest.get("attempt_id"),
        manifest.get("game_id"),
        "fdas-coordinated-replacement-operations/1.0",
    ])
    records_valid = bool(
        record_ids_unique
        and all(
            row.get("spec", {}).get("operation_type") == _OPERATION_TYPE
            and _spec_digest_valid(row.get("spec", {}))
            and _lifecycle_key(row) is not None
            for row in records))
    active_keys = tuple(
        _lifecycle_key(row) for row in records
        if row.get("progress", {}).get("state") not in _TERMINAL_STATES)

    lifecycle = tuple(
        row for row in events
        if (row.get("type") == "atomspace_shadow_decision"
            and row.get("payload", {}).get("component_id") == _COMPONENT_ID))
    details = tuple(row["payload"].get("details", {}) for row in lifecycle)
    event_operation_ids = tuple(row.get("operation_id") for row in details)
    dispositions = tuple(row.get("disposition") for row in details)
    reconciliation_dispositions = tuple(
        value for value in dispositions
        if not (isinstance(value, str) and value.startswith("execution-")))
    final = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        final[0].get("payload", {}).get("summary", {})
        if len(final) == 1 else {})

    expected_counters = {
        "fdas_replacement_blocked": dispositions.count("blocked"),
        "fdas_replacement_completions": dispositions.count("completed"),
        "fdas_replacement_expirations": dispositions.count("expired"),
        "fdas_replacement_operations": len(records),
        # The execution pilot emits the same operation-lifecycle component so
        # its durable transitions remain causally visible.  They are not
        # adapter reconciliation passes and therefore do not increment the
        # long-standing reconciliation counter.
        "fdas_replacement_reconciliations": len(
            reconciliation_dispositions),
        "fdas_replacement_reservable": sum(
            value in ("reservable", "reconciled") for value in dispositions),
        "fdas_replacement_step_advances": dispositions.count("step-advanced"),
    }
    counter_match = all(
        status.get(name) == value and terminal.get(name) == value
        for name, value in expected_counters.items())

    checks = {
        "event_ledger_valid_without_warnings": (
            validation.valid and not validation.warnings),
        "manifest_activates_shadow_live_replacement": (
            capabilities.get("coordinated_replacement_lifecycle")
            == "shadow-live"
            and declaration.get("config", {}).get("projection", {}).get(
                "operations") is True),
        "source_is_clean_and_run_completed": (
            manifest.get("source", {}).get("dirty") is False
            and status.get("completed") is True
            and status.get("horizon_reached") is True
            and len(final) == 1),
        "store_is_valid_unquarantined_and_identity_bound": (
            store.get("schema_version") == 1
            and store.get("store_identity") == _STORE_IDENTITY
            and store.get("quarantine_reason") is None
            and store.get("persistence_identity")
            == expected_persistence_identity
            and claimed_store_digest == structural_hash(semantic_store)
            and records_valid),
        "active_logical_lifecycles_are_unique": (
            len(active_keys) == len(set(active_keys))),
        "lifecycle_events_are_revision_bound_and_non_authorizing": all(
            row.get("snapshot_id") == detail.get("snapshot_id")
            and row.get("component_version") == "1.0"
            and detail.get("identity") == _IDENTITY
            and detail.get("action_selection_changed") is False
            and detail.get("policy_authority") is False
            and detail.get("readout_authority") is False
            and detail.get("truth_mutated") is False
            and isinstance(detail.get("store_digest"), str)
            and bool(detail.get("store_digest"))
            for row, detail in zip(
                (value["payload"] for value in lifecycle), details)),
        "lifecycle_events_reference_persisted_operations": (
            set(event_operation_ids).issubset(set(record_by_id))),
        "status_and_terminal_counters_match_evidence": counter_match,
        "candidate_counter_covers_persisted_operations": (
            isinstance(status.get("fdas_replacement_candidates"), int)
            and status.get("fdas_replacement_candidates") >= len(records)
            and terminal.get("fdas_replacement_candidates")
            == status.get("fdas_replacement_candidates")),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "engine-live activation, persistence, logical deduplication, and "
            "revision-current non-authorizing lifecycle evidence only; zero "
            "opportunity is mechanically acceptable; no action, outcome, "
            "score, or win-rate improvement claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "candidates": status.get("fdas_replacement_candidates"),
            "dispositions": dict(
                (value, dispositions.count(value))
                for value in sorted(set(dispositions))),
            "execution_lifecycle_events": (
                len(dispositions) - len(reconciliation_dispositions)),
            "lifecycle_events": len(lifecycle),
            "opportunity_observed": bool(records),
            "operations": len(records),
            "store_digest": claimed_store_digest,
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
