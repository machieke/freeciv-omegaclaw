"""Audit paired live FDAS belief-conflict and context-quarantine evidence."""

from collections import Counter
import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash


COHORT = "fdas_belief_conflict_shadow_diagnostic_v1"
MODE = "model-prior-versus-visible-roster-shadow"
MODEL_ID = "fdas-opponent-presence-prior"
TARGET_PREDICATE = "opponent-present"
REQUIRED_PREDICATES = frozenset((
    "belief-conflict-lineage",
    "belief-conflict-target",
    "belief-context-quarantine",
    "belief-quarantine-context",
    "belief-quarantine-target",
    "belief-quarantines-evidence",
    "belief-retains-evidence",
))


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
        raise ValueError("expected one {} belief-conflict game".format(arm))
    return candidates[0]


def _is_ancestor(ancestor_id, descendant, by_id):
    pending = list(descendant.get("caused_by", ()))
    visited = set()
    while pending:
        event_id = pending.pop()
        if event_id == ancestor_id:
            return True
        if event_id in visited:
            continue
        visited.add(event_id)
        parent = by_id.get(event_id)
        if parent is not None:
            pending.extend(parent.get("caused_by", ()))
    return False


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
    declaration = manifest.get("dependent_atomspace", {})
    config = declaration.get("config", {})
    capability_manifest = declaration.get("manifest", {})
    diagnostic = capability_manifest.get("belief_conflict_diagnostic", {})
    observations = tuple(row for row in events if row["type"] == "observation")
    revisions = tuple(row for row in events if row["type"] == "revision")
    conflicts = tuple(row for row in events if row["type"] == "belief_conflict")
    quarantines = tuple(
        row for row in events if row["type"] == "context_quarantine")
    sent = tuple(row for row in events if row["type"] == "action_sent")
    results = tuple(row for row in events if row["type"] == "action_result")
    authority = tuple(
        row for row in events
        if row["type"] == "atomspace_authority_decision")
    projected = Counter(
        row["payload"].get("details", {}).get("predicate")
        for row in events
        if row["type"] == "atom_rederived")
    threshold_metrics = tuple(
        row for row in events
        if (row["type"] == "metric_sample"
            and row["payload"].get("name")
            in ("belief_conflict_min_confidence",
                "belief_conflict_severity_threshold")))
    conflict_rows = []
    for event in conflicts:
        value = event["payload"]
        provenance_ids = set(value.get("left_provenance_ids", ())) | set(
            value.get("right_provenance_ids", ()))
        source_lineages = set(value.get("left_source_lineage_ids", ())) | set(
            value.get("right_source_lineage_ids", ()))
        matching_observations = tuple(
            row for row in observations
            if row["payload"].get("provenance_id") in provenance_ids)
        priors = tuple(
            row for row in matching_observations
            if (row["payload"].get("source") == "simulator"
                and row["payload"].get("atom", {}).get("predicate")
                == TARGET_PREDICATE))
        visible = tuple(
            row for row in matching_observations
            if row["payload"].get("source")
            == "player-visible-roster-packet")
        positive_revisions = tuple(
            row for row in revisions
            if (row["payload"].get("provenance_id") in {
                    value["payload"].get("provenance_id")
                    for value in visible}
                and row["payload"].get("target_atom", {}).get("atom_id")
                == value.get("target_atom_id")
                and row["payload"].get("formula", {}).get("name")
                == "provenance-union"))
        matching_quarantines = tuple(
            row for row in quarantines
            if row["payload"].get("conflict_id") == value.get("conflict_id"))
        quarantine_contexts = {
            row["payload"].get("context_id") for row in matching_quarantines}
        partitions = all(
            set(row["payload"].get("excluded_provenance_ids", ()))
            | set(row["payload"].get("retained_provenance_ids", ()))
            == provenance_ids
            and not (
                set(row["payload"].get("excluded_provenance_ids", ()))
                & set(row["payload"].get("retained_provenance_ids", ())))
            for row in matching_quarantines)
        conflict_rows.append({
            "causal_visible_roster_observation": (
                len(visible) == 1 and len(positive_revisions) == 1
                and _is_ancestor(
                    visible[0]["event_id"], positive_revisions[0], by_id)
                and _is_ancestor(
                    positive_revisions[0]["event_id"], event, by_id)),
            "complete_context_partition": (
                len(matching_quarantines) == len(value.get("context_ids", ()))
                and quarantine_contexts == set(value.get("context_ids", ()))
                and partitions
                and all(event["event_id"] in row.get("caused_by", ())
                        for row in matching_quarantines)),
            "explicit_independent_source_lineages": (
                len(source_lineages) == 2
                and any(row.startswith("simulator-model:")
                        for row in source_lineages)
                and any(row.startswith("player-visible-roster-packet:")
                        for row in source_lineages)
                and value.get("overlap") == 0.0),
            "model_prior_is_capped_and_non_crisp": (
                len(priors) == 1
                and priors[0]["payload"].get("atom", {}).get("crisp") is False
                and priors[0]["payload"].get("atom", {}).get(
                    "tv", {}).get("strength") == 0.0
                and priors[0]["payload"].get("model_provenance", {}).get(
                    "exact") is False
                and priors[0]["payload"].get("model_provenance", {}).get(
                    "model_id") == MODEL_ID
                and priors[0]["payload"].get("atom", {}).get(
                    "tv", {}).get("confidence")
                <= priors[0]["payload"].get(
                    "model_provenance", {}).get("confidence_cap", -1.0)),
            "severity_passes_declared_gate": (
                float(value.get("severity", -1.0))
                >= float(diagnostic.get("conflict_severity_threshold", 2.0))),
        })
    all_epistemic_atoms = tuple(
        row["payload"].get("atom") for row in observations
        if isinstance(row["payload"].get("atom"), dict)) + tuple(
        row["payload"].get("target_atom") for row in revisions
        if isinstance(row["payload"].get("target_atom"), dict))
    checks = {
        "actions_complete_and_accepted": (
            bool(sent) and len(sent) == len(results)
            == status.get("engine_actions")
            and all(row["payload"].get("status") == "accepted"
                    for row in results)
            and status.get("rejected_actions") == 0),
        "conflict_profile_is_manifest_bound_shadow_only": (
            declaration.get("config_source")
            == "profile/dependent_atomspace_belief_conflict_shadow.yaml"
            and declaration.get("manifest_source")
            == "profile/fdas_manifest_belief_conflict_shadow.json"
            and config.get("projection", {}).get("beliefs") is True
            and config.get("authority_enabled") is False
            and not any(config.get("domain_authority", {}).values())
            and capability_manifest.get("policy_authority") is False
            and capability_manifest.get("capabilities", {}).get(
                "belief_conflict_quarantine") == "shadow-live"
            and diagnostic.get("mode") == MODE
            and diagnostic.get("policy_authority") is False
            and diagnostic.get("apply_all_context_quarantines") is True
            and diagnostic.get("target_predicate") == TARGET_PREDICATE),
        "effective_conflict_thresholds_are_logged": (
            len(threshold_metrics) == 2
            and all(row["payload"].get("labels", {}).get("declaration")
                    == "fdas_diagnostic_override"
                    for row in threshold_metrics)
            and dict((row["payload"]["name"], row["payload"]["value"])
                     for row in threshold_metrics) == {
                "belief_conflict_min_confidence": float(
                    diagnostic.get("conflict_min_confidence", -1.0)),
                "belief_conflict_severity_threshold": float(
                    diagnostic.get("conflict_severity_threshold", -1.0)),
            }),
        "independent_conflict_and_quarantine_are_causally_complete": (
            bool(conflict_rows)
            and all(all(row.values()) for row in conflict_rows)),
        "conflict_and_quarantine_atoms_are_projected": (
            REQUIRED_PREDICATES.issubset(projected)
            and projected["belief-conflict-lineage"] >= 2),
        "uncertainty_never_becomes_absence_or_authority": (
            all(atom.get("crisp") is False for atom in all_epistemic_atoms)
            and all("absent" not in str(atom.get("predicate", "")).lower()
                    for atom in all_epistemic_atoms)
            and not authority
            and status.get("fdas_authority_actions") == 0
            and status.get("operation_authority_actions") == 0),
        "status_counters_match_conflict_artifacts": (
            status.get("fdas_belief_conflict_model_priors") == 1
            and status.get("fdas_belief_conflicts_detected") == len(conflicts)
            and status.get("fdas_belief_context_quarantines")
            == len(quarantines)),
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
        "projected_predicates": dict(sorted(projected.items())),
        "source": manifest.get("source"),
        "summary": {
            "actions": len(sent),
            "conflicts": len(conflicts),
            "context_quarantines": len(quarantines),
            "model_priors": sum(
                row["payload"].get("source") == "simulator"
                and row["payload"].get("model_provenance", {}).get(
                    "model_id") == MODEL_ID
                for row in observations),
            "visible_roster_revisions": sum(
                row["payload"].get("formula", {}).get("name")
                == "provenance-union"
                and row["payload"].get("target_atom", {}).get("predicate")
                == TARGET_PREDICATE
                and row["payload"].get("provenance_id") in {
                    value["payload"].get("provenance_id")
                    for value in observations
                    if value["payload"].get("source")
                    == "player-visible-roster-packet"}
                for row in revisions),
        },
    }


def audit_fdas_belief_conflict_live(root, repo=None):
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
        "both_arms_pass_conflict_acceptance": all(
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
            "live capped model-prior versus player-visible roster conflict, "
            "explicit independent source lineages, "
            "context-local quarantine projection, and zero authority; no "
            "model accuracy, opponent absence, score, or gameplay-improvement "
            "claim"),
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
                "actions", "conflicts", "context_quarantines",
                "model_priors", "visible_roster_revisions")),
    }
    report["structural_hash"] = structural_hash(report)
    return report
