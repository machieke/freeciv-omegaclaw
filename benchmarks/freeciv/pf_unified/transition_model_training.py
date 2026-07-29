"""Fit a frozen transition-value model from claim-ineligible engine traces."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.pressure import (
    TransitionValueKey,
    TransitionValueModel,
    TransitionValueObservation,
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
