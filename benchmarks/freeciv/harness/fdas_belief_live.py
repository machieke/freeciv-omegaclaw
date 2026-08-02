"""Deterministic audit for a paired FDAS opponent-belief shadow cohort."""

from collections import Counter
import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash


COHORT = "fdas_belief_shadow_diagnostic_v1"
REQUIRED_PREDICATES = frozenset((
    "belief-about-opponent",
    "belief-context",
    "belief-current-revision",
    "belief-proposition",
    "belief-supported-by-evidence",
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


def _negative_predicate(predicate):
    value = str(predicate).lower()
    return any(token in value for token in (
        "absent", "absence", "lacks", "missing", "not-present"))


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
    event_ids = {row.get("event_id") for row in events}
    observations = tuple(row for row in events if row["type"] == "observation")
    revisions = tuple(row for row in events if row["type"] == "revision")
    decay = tuple(
        row for row in revisions
        if row["payload"].get("operation") == "decay")
    apply = tuple(
        row for row in revisions
        if row["payload"].get("operation") == "apply")
    projected_predicates = Counter(
        row["payload"].get("details", {}).get("predicate")
        for row in events
        if (row["type"] == "atom_rederived"
            and row["payload"].get("details", {}).get("predicate", "")
            .startswith("belief-")))
    belief_scopes = tuple(
        row for row in events
        if (row["type"] == "scope_materialized"
            and row["payload"].get("details", {}).get("scope_kind")
            == "opponent-belief"))
    committed = tuple(
        row for row in events
        if row["type"] == "atomspace_revision_committed")
    supported_commits = tuple(
        row for row in committed
        if row["payload"].get("details", {}).get("atom_count", 0) > 0)
    invalidated = tuple(
        row for row in events if row["type"] == "atom_invalidated")
    cold = tuple(
        row for row in events
        if (row["type"] == "metric_sample"
            and row["payload"].get("name") == "fdas_projection_latency_ms"
            and row["payload"].get("labels", {}).get("cold_verified")
            == "True"))
    rematerialization = tuple(
        row for row in events
        if (row["type"] == "metric_sample"
            and row["payload"].get("name")
            == "fdas_belief_rematerialization_latency_ms"))
    sent = tuple(row for row in events if row["type"] == "action_sent")
    results = tuple(row for row in events if row["type"] == "action_result")
    completed = tuple(row for row in events if row["type"] == "run_completed")
    failed = tuple(row for row in events if row["type"] == "run_failed")
    authority = tuple(
        row for row in events
        if row["type"] == "atomspace_authority_decision")
    conflicts = tuple(row for row in events if row["type"] == "belief_conflict")
    quarantines = tuple(
        row for row in events if row["type"] == "context_quarantine")
    epistemic_atoms = tuple(
        row["payload"].get("target_atom") for row in revisions
        if isinstance(row["payload"].get("target_atom"), dict))
    epistemic_atoms += tuple(
        row["payload"].get("atom") for row in observations
        if isinstance(row["payload"].get("atom"), dict))
    projection_latency = _latency(events, "fdas_projection_latency_ms")
    declaration = manifest.get("dependent_atomspace", {})
    config = declaration.get("config", {})
    projection = config.get("projection", {})
    domains = config.get("domain_authority", {})
    capability_manifest = declaration.get("manifest", {})
    capabilities = capability_manifest.get("capabilities", {})
    causal_revisions = all(
        row.get("caused_by")
        and all(parent in event_ids for parent in row["caused_by"])
        for row in decay)
    checks = {
        "action_results_are_complete_and_accepted": (
            len(sent) == len(results) == status.get("engine_actions")
            and bool(sent)
            and all(row["payload"].get("status") == "accepted"
                    for row in results)
            and status.get("rejected_actions") == 0),
        "belief_projection_is_manifest_bound_shadow_only": (
            declaration.get("config_source")
            == "profile/dependent_atomspace_belief_shadow.yaml"
            and declaration.get("manifest_source")
            == "profile/fdas_manifest_belief_shadow.json"
            and config.get("enabled") is True
            and config.get("shadow_enabled") is True
            and config.get("authority_enabled") is False
            and domains and not any(domains.values())
            and projection.get("beliefs") is True
            and not any(
                value for key, value in projection.items()
                if key not in ("beliefs", "world", "empire"))
            and capability_manifest.get("policy_authority") is False
            and capabilities.get("belief_domain_projection") == "shadow-live"
            and capabilities.get("observation_pressure_planning")
            == "component-only"),
        "belief_scopes_and_required_predicates_are_live": (
            bool(belief_scopes)
            and REQUIRED_PREDICATES.issubset(projected_predicates)),
        "cold_verification_is_equivalent": (
            bool(cold)
            and all(row["payload"]["labels"].get("cold_equivalent") == "True"
                    for row in cold)),
        "decay_is_explicit_causal_and_monotone": (
            bool(decay) and causal_revisions
            and all(
                row["payload"].get("formula", {}).get("name")
                == "linear-window"
                and row["payload"].get("provenance_id", "").startswith(
                    "revision-")
                and row["payload"]["posterior_tv"]["confidence"]
                <= row["payload"]["prior_tv"]["confidence"]
                for row in decay)),
        "engine_run_completed_at_horizon": (
            len(completed) == 1 and not failed
            and status.get("completed") is True
            and status.get("horizon_reached") is True),
        "expired_support_is_invalidated_not_negated": (
            bool(invalidated)
            and epistemic_atoms
            and all(atom.get("crisp") is False for atom in epistemic_atoms)
            and all(not _negative_predicate(atom.get("predicate"))
                    for atom in epistemic_atoms)),
        "fdas_projection_p95_within_budget": (
            projection_latency["p95_ms"] is not None
            and projection_latency["p95_ms"] <= 150.0),
        "no_conflict_or_quarantine_is_fabricated": (
            not conflicts and not quarantines),
        "no_fdas_or_observation_authority": (
            not authority
            and status.get("fdas_authority_actions") == 0
            and status.get("operation_authority_actions") == 0),
        "observations_and_revised_beliefs_are_uncertain": (
            bool(observations) and bool(apply)
            and all(atom.get("crisp") is False for atom in epistemic_atoms)
            and all(
                0.0 <= atom.get("tv", {}).get("confidence", -1.0) <= 1.0
                for atom in epistemic_atoms)),
        "projection_commits_retain_one_support_per_atom": (
            bool(supported_commits)
            and all(
                row["payload"]["details"]["atom_count"]
                == row["payload"]["details"]["support_count"]
                for row in supported_commits)),
        "status_counters_match_decay_and_rematerialization_events": (
            status.get("fdas_belief_decay_revisions") == len(decay)
            and status.get("fdas_belief_rematerializations")
            == len(rematerialization)),
        "source_is_clean": manifest.get("source", {}).get("dirty") is False,
    }
    return {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "arm": arm,
        "evidence": dict(
            (name, {"path": _logical_path(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "latency": {
            "belief_rematerialization": _latency(
                events, "fdas_belief_rematerialization_latency_ms"),
            "fdas_projection": projection_latency,
            "full_controller": _latency(events, "turn_full_loop_latency_ms"),
        },
        "projected_predicates": dict(sorted(projected_predicates.items())),
        "source": manifest.get("source"),
        "summary": {
            "accepted_action_results": sum(
                row["payload"].get("status") == "accepted" for row in results),
            "actions": len(sent),
            "belief_scopes": len(belief_scopes),
            "cold_verifications": len(cold),
            "conflicts": len(conflicts),
            "decay_revisions": len(decay),
            "invalidations": len(invalidated),
            "observations": len(observations),
            "quarantines": len(quarantines),
            "rematerializations": len(rematerialization),
        },
    }


def audit_fdas_belief_live(root, repo=None):
    """Verify clean live uncertain projection without observation authority."""
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
        "both_arms_pass_belief_acceptance": all(
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
            "real-observation opponent-belief projection, explicit decay, "
            "support invalidation, cold parity, and non-authority; no conflict, "
            "quarantine, observation-selection, score, or gameplay improvement "
            "claim"),
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
            name: sum(arm["summary"][name] for arm in arms)
            for name in (
                "accepted_action_results", "actions", "belief_scopes",
                "cold_verifications", "conflicts", "decay_revisions",
                "invalidations", "observations", "quarantines",
                "rematerializations")
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
