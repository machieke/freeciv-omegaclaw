"""Fit a frozen transition-value model from claim-ineligible engine traces."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.pressure import (
    ContextualCalibrationGate,
    ContextualTransitionValueModel,
    TransitionValueKey,
    TransitionValueModel,
    TransitionValueObservation,
    contextual_outcome_from_dict,
)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(
                lambda: stream.read(1024 * 1024),
                b""):
            digest.update(block)
    return digest.hexdigest()


def _observation(value):
    if not isinstance(value, dict):
        raise ValueError(
            "transition observation must be an object")
    key = value.get("key")
    if not isinstance(key, dict):
        raise ValueError(
            "transition observation key is required")
    return TransitionValueObservation(
        observation_id=str(
            value.get("observation_id", "")),
        key=TransitionValueKey(
            action_category=str(
                key.get("action_category", "")),
            lifecycle_state=str(
                key.get("lifecycle_state", "")),
            goal_id=str(key.get("goal_id", ""))),
        predicted_relief=float(
            value.get("predicted_relief")),
        realized_relief=float(
            value.get("realized_relief")),
        effect_observed=value.get(
            "effect_observed"),
        relief_source=str(
            value.get("relief_source", "")),
        context_digest=str(
            value.get("context_digest", "")),
        selection_propensity=value.get(
            "selection_propensity"),
        update_scope=str(value.get(
            "update_scope",
            "control-model-only")))


def _eligible_event_files(root, cohort, arm):
    rows = []
    games = os.path.join(
        os.path.abspath(root), "games")
    for directory, names, files in os.walk(games):
        names[:] = sorted(
            name for name in names
            if name != "__pycache__")
        if ("events.jsonl" not in files
                or "manifest.json" not in files
                or "status.json" not in files):
            continue
        manifest_path = os.path.join(
            directory, "manifest.json")
        status_path = os.path.join(
            directory, "status.json")
        with open(
                manifest_path,
                encoding="utf-8") as stream:
            manifest = json.load(stream)
        with open(
                status_path,
                encoding="utf-8") as stream:
            status = json.load(stream)
        pair = manifest.get("impact_pair")
        if not isinstance(pair, dict):
            continue
        if (pair.get("cohort") != cohort
                or pair.get("arm") != arm):
            continue
        if (pair.get("claim_eligible") is not False
                or pair.get("cohort_purpose")
                not in ("development", "diagnostic")):
            raise ValueError(
                "transition training requires claim-ineligible "
                "development or diagnostic traces")
        source = manifest.get("source")
        if (not isinstance(source, dict)
                or source.get("dirty") is not False):
            raise ValueError(
                "transition training requires clean source traces")
        if (status.get("status") != "completed"
                or not status.get("completed", False)):
            raise ValueError(
                "transition training trace is incomplete")
        rows.append((
            os.path.join(directory, "events.jsonl"),
            manifest))
    if not rows:
        raise ValueError(
            "no eligible transition training traces found")
    return tuple(sorted(
        rows, key=lambda row: row[0]))


def fit_transition_value_model(
        artifact_root, output_path, identity,
        cohort, arm="treatment",
        minimum_samples=30,
        maximum_half_width=0.50,
        alpha=0.05,
        overwrite=False):
    """Pool selected-action outcomes and write one frozen evaluation fit."""
    output_path = os.path.abspath(output_path)
    if os.path.exists(output_path):
        if not overwrite:
            raise ValueError(
                "transition model output already exists")
        os.remove(output_path)
    files = _eligible_event_files(
        artifact_root, cohort, arm)
    observations = []
    event_files = []
    source_identities = set()
    seeds = set()
    for path, manifest in files:
        pair = manifest["impact_pair"]
        seeds.add(int(manifest["seed"]))
        source_identities.add(structural_hash(
            manifest["source"]))
        event_count = 0
        with open(path, encoding="utf-8") as stream:
            for line_number, line in enumerate(
                    stream, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except ValueError as error:
                    raise ValueError(
                        "invalid JSON at {}:{}: {}".format(
                            path, line_number, error))
                if event.get("type") != (
                        "transition_value_updated"):
                    continue
                summary = event.get(
                    "payload", {}).get(
                        "summary", {})
                if not isinstance(summary, dict):
                    raise ValueError(
                        "transition update summary is invalid")
                observations.append(
                    _observation(
                        summary.get("observation")))
                event_count += 1
        event_files.append({
            "arm": pair["arm"],
            "events_sha256": _sha256(path),
            "path": os.path.relpath(
                path,
                os.path.abspath(artifact_root)),
            "seed": int(manifest["seed"]),
            "transition_update_events":
                event_count,
        })
    if len(source_identities) != 1:
        raise ValueError(
            "transition training source identities differ")
    model = TransitionValueModel(
        path=output_path,
        identity=str(identity),
        minimum_samples=int(minimum_samples),
        maximum_half_width=float(
            maximum_half_width),
        alpha=float(alpha))
    updates = model.observe_many(observations)
    keys = sorted(set(
        row.key for row in observations))
    support = []
    for key in keys:
        estimate = model.estimate(key, 0.5)
        support.append({
            "calibrated": estimate.calibrated,
            "confidence_half_width":
                estimate.confidence_half_width,
            "key": key.to_dict(),
            "sample_count":
                estimate.sample_count,
        })
    report = {
        "arm": str(arm),
        "claim_eligible": False,
        "cohort": str(cohort),
        "duplicate_observations":
            sum(not row.applied for row in updates),
        "event_files": event_files,
        "exact_support": support,
        "fit_scope": (
            "selected actions with authoritative realized "
            "goal relief; no off-policy correction"),
        "identity": str(identity),
        "model_path": output_path,
        "model_sha256": _sha256(output_path),
        "model_state_hash": model.state_hash,
        "observation_count": len(
            model.snapshot()["observations"]),
        "schema_version": "1.0",
        "seed_count": len(seeds),
        "source_identity":
            next(iter(source_identities)),
        "supported_key_count": sum(
            row["calibrated"]
            for row in support),
        "total_key_count": len(support),
        "update_scope": "control-model-only",
    }
    report["training_hash"] = structural_hash(
        report)
    return report


def _contextual_outcomes(
        files):
    outcomes = []
    event_files = []
    source_identities = set()
    seeds = set()
    for path, manifest in files:
        pair = manifest["impact_pair"]
        seeds.add(int(manifest["seed"]))
        source_identities.add(
            structural_hash(
                manifest["source"]))
        event_count = 0
        with open(
                path,
                encoding="utf-8") as stream:
            for line_number, line in enumerate(
                    stream, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except ValueError as error:
                    raise ValueError(
                        "invalid JSON at {}:{}: {}".format(
                            path,
                            line_number,
                            error))
                if event.get("type") != (
                        "transition_value_updated"):
                    continue
                summary = (
                    event.get(
                        "payload", {})
                    .get("summary", {}))
                observation = (
                    summary.get("observation")
                    if isinstance(summary, dict)
                    else None)
                key = (
                    observation.get("key")
                    if isinstance(
                        observation, dict)
                    else None)
                if (
                        not isinstance(key, dict)
                        or key.get(
                            "schema_version")
                        != "2.0"
                ):
                    continue
                outcomes.append(
                    contextual_outcome_from_dict(
                        observation))
                event_count += 1
        event_files.append({
            "arm": pair["arm"],
            "events_sha256": _sha256(path),
            "path": (
                "games/{}".format(
                    path.split(
                        "{}games{}".format(
                            os.sep, os.sep),
                        1)[1])
                if "{}games{}".format(
                    os.sep, os.sep)
                in path else os.path.basename(
                    path)),
            "seed": int(manifest["seed"]),
            "v2_contextual_update_events":
                event_count,
        })
    if len(source_identities) != 1:
        raise ValueError(
            "contextual source identities differ")
    if not outcomes:
        raise ValueError(
            "no v2 contextual outcomes found")
    return (
        tuple(outcomes),
        event_files,
        next(iter(source_identities)),
        seeds)


def fit_contextual_transition_value_model(
        artifact_root, output_path, identity,
        cohort, arm="treatment",
        minimum_samples=30,
        maximum_half_width=0.50,
        alpha=0.05,
        shrinkage_kappa=10.0,
        legacy_v1_path=None,
        legacy_ruleset_family=None,
        overwrite=False):
    """Fit a v2 model without turning v1 rows into contextual support."""
    declared_output_path = str(output_path)
    output_path = os.path.abspath(output_path)
    if os.path.exists(output_path):
        if not overwrite:
            raise ValueError(
                "contextual model output already exists")
        os.remove(output_path)
    files = _eligible_event_files(
        artifact_root, cohort, arm)
    (
        outcomes, event_files,
        source_identity, seeds,
    ) = _contextual_outcomes(files)
    model = ContextualTransitionValueModel(
        path=output_path,
        identity=str(identity),
        minimum_samples=int(
            minimum_samples),
        maximum_half_width=float(
            maximum_half_width),
        alpha=float(alpha),
        shrinkage_kappa=float(
            shrinkage_kappa))
    if legacy_v1_path is not None:
        if not legacy_ruleset_family:
            raise ValueError(
                "legacy migration requires ruleset family")
        model.import_legacy_v1(
            legacy_v1_path,
            str(legacy_ruleset_family))
    updates = model.observe_many(
        outcomes)
    frozen = ContextualTransitionValueModel(
        path=output_path,
        identity=str(identity),
        minimum_samples=int(
            minimum_samples),
        maximum_half_width=float(
            maximum_half_width),
        alpha=float(alpha),
        shrinkage_kappa=float(
            shrinkage_kappa),
        read_only=True)
    keys = tuple(sorted(set(
        row.key for row in outcomes)))
    support = []
    for key in keys:
        raw = next(
            row.predicted_relief
            for row in outcomes
            if row.key == key)
        estimate = frozen.estimate(
            key, raw)
        support.append({
            "calibrated":
                estimate.calibrated,
            "confidence_half_width":
                estimate.confidence_half_width,
            "contextual_conductance":
                estimate.contextual_conductance,
            "conductance_sample_count":
                estimate.conductance_sample_count,
            "key": key.to_dict(),
            "sample_count":
                estimate.sample_count,
            "support_key": (
                estimate.support_key.to_dict()
                if estimate.support_key
                is not None else None),
        })
    report = {
        "arm": str(arm),
        "claim_eligible": False,
        "cohort": str(cohort),
        "duplicate_outcomes":
            sum(
                not row.applied
                for row in updates),
        "event_files": event_files,
        "fit_scope": (
            "causally eligible selected actions with authoritative "
            "goal relief; unknown outcomes retained but excluded"),
        "identity": str(identity),
        "legacy_migration_scope":
            "category-prior-only",
        "model_path": declared_output_path,
        "model_sha256": _sha256(
            output_path),
        "model_state_hash":
            frozen.state_hash,
        "outcome_count":
            frozen.decision_snapshot()[
                "outcome_count"],
        "schema_version": "2.0",
        "seed_count": len(seeds),
        "source_identity":
            source_identity,
        "support": support,
        "supported_key_count":
            sum(
                row["calibrated"]
                for row in support),
        "total_key_count":
            len(support),
        "unknown_outcome_count":
            frozen.decision_snapshot()[
                "unknown_outcome_count"],
        "update_scope":
            "control-model-only",
    }
    report["training_hash"] = (
        structural_hash(report))
    return report


def evaluate_contextual_transition_value_model(
        artifact_root, model_path, identity,
        cohort, output_path,
        arm="treatment",
        minimum_samples=30,
        maximum_half_width=0.50,
        alpha=0.05,
        shrinkage_kappa=10.0,
        minimum_coverage=0.80,
        maximum_context_brier_regression=0.02,
        bootstrap_iterations=2000,
        overwrite=False):
    """Write a model-bound, deterministic holdout authority bundle."""
    output_path = os.path.abspath(
        output_path)
    if os.path.exists(output_path) and not overwrite:
        raise ValueError(
            "contextual approval output already exists")
    files = _eligible_event_files(
        artifact_root, cohort, arm)
    (
        outcomes, event_files,
        source_identity, seeds,
    ) = _contextual_outcomes(files)
    model = ContextualTransitionValueModel(
        path=os.path.abspath(
            model_path),
        identity=str(identity),
        minimum_samples=int(
            minimum_samples),
        maximum_half_width=float(
            maximum_half_width),
        alpha=float(alpha),
        shrinkage_kappa=float(
            shrinkage_kappa),
        read_only=True)
    report = ContextualCalibrationGate(
        minimum_coverage=float(
            minimum_coverage),
        maximum_context_brier_regression=float(
            maximum_context_brier_regression),
        bootstrap_iterations=int(
            bootstrap_iterations)
    ).evaluate(model, outcomes)
    report.pop("report_hash", None)
    report.update({
        "arm": str(arm),
        "claim_eligible": False,
        "cohort": str(cohort),
        "event_files": event_files,
        "model_identity": str(identity),
        "model_sha256": _sha256(
            os.path.abspath(model_path)),
        "seed_count": len(seeds),
        "source_identity":
            source_identity,
    })
    report["report_hash"] = structural_hash(
        report)
    parent = os.path.dirname(
        output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(
            output_path, "wb") as stream:
        stream.write(
            json.dumps(
                report,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":")
            ).encode("utf-8"))
        stream.write(b"\n")
    return report
