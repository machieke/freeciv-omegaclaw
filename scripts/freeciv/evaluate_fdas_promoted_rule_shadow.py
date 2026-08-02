#!/usr/bin/env python3
"""Evaluate an approved FDAS rule basis on a fresh outcome cohort."""

import argparse
import hashlib
import json
import math
import os
import random
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(REPO, "src")
BENCHMARKS = os.path.join(REPO, "benchmarks")
for location in (SCRIPT_DIR, SRC, BENCHMARKS):
    if location not in sys.path:
        sys.path.insert(0, location)

import run_fdas_induction_holdout as shared  # noqa: E402
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    EpisodeInductionSpec,
    FdasEpisodeInductionAdapter,
    FdasEpisodeInductionShadow,
)
from freeciv_agent.pressure import (  # noqa: E402
    InducedRuleProposal,
    InductionPromotionApproval,
    PromotedRuleConsolidation,
    PromotedRuleShadowReadout,
    ReplayValidation,
)
from freeciv.harness.runner import _source_identity  # noqa: E402


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical(path):
    absolute = os.path.abspath(path)
    relative = os.path.relpath(absolute, REPO)
    if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
        return relative.replace(os.sep, "/")
    return absolute


def _verified_report(path):
    with open(path, encoding="utf-8") as stream:
        value = json.load(stream)
    expected = value.get("structural_hash")
    material = dict(value)
    material.pop("structural_hash", None)
    if expected != structural_hash(material):
        raise ValueError("report structural hash mismatch: {}".format(path))
    if value.get("acceptance", {}).get("accepted") is not True:
        raise ValueError("input report is not accepted: {}".format(path))
    return value


def _approved_artifacts(report):
    result = report["result"]
    promoted_ids = set(result["promoted_rule_ids"])
    proposals = tuple(
        InducedRuleProposal.from_dict(value)
        for value in result["proposals"]
        if value["proposal_id"] in promoted_ids)
    validations = tuple(
        ReplayValidation.from_dict(value)
        for value in result["validations"]
        if value["proposal_id"] in promoted_ids)
    approvals = tuple(
        InductionPromotionApproval.from_dict(value)
        for value in result["approvals"])
    if not (
            promoted_ids
            == set(value.proposal_id for value in proposals)
            == set(value.proposal_id for value in validations)
            == set(value.proposal_id for value in approvals)):
        raise ValueError("approved report artifacts are incomplete")
    return proposals, validations, approvals


def _wilson(positives, samples):
    if samples < 1:
        return None
    count = float(samples)
    observed = float(positives) / count
    z = 1.959963984540054
    z_squared = z * z
    denominator = 1.0 + z_squared / count
    center = (observed + z_squared / (2.0 * count)) / denominator
    radius = z * math.sqrt(
        observed * (1.0 - observed) / count
        + z_squared / (4.0 * count * count)) / denominator
    return {
        "confidence": 0.95,
        "lower": max(0.0, center - radius),
        "method": "wilson-score/1.0",
        "upper": min(1.0, center + radius),
    }


def _log_loss(probability, outcome):
    bounded = min(1.0 - 1e-12, max(1e-12, probability))
    return -math.log(bounded if outcome else 1.0 - bounded)


def _paired_bootstrap_interval(values, samples=10000, seed=7717):
    values = tuple(float(value) for value in values)
    if not values:
        return None
    generator = random.Random(int(seed))
    count = len(values)
    means = sorted(
        sum(values[generator.randrange(count)] for _index in range(count))
        / float(count)
        for _sample in range(int(samples)))
    lower_index = int(math.floor(0.025 * (len(means) - 1)))
    upper_index = int(math.ceil(0.975 * (len(means) - 1)))
    return {
        "confidence": 0.95,
        "lower": means[lower_index],
        "method": "paired-percentile-bootstrap/1.0",
        "samples": int(samples),
        "seed": int(seed),
        "upper": means[upper_index],
    }


def _metrics(rows):
    rows = tuple(rows)
    if not rows:
        return None
    outcomes = tuple(bool(value["outcome"]) for value in rows)
    predictions = tuple(
        float(value["readout"]["selected_probability"])
        for value in rows)
    baselines = tuple(
        float(value["readout"]["selected_baseline_probability"])
        for value in rows)
    count = float(len(rows))
    candidate_brier = sum(
        (prediction - int(outcome)) ** 2
        for prediction, outcome in zip(predictions, outcomes)) / count
    baseline_brier = sum(
        (baseline - int(outcome)) ** 2
        for baseline, outcome in zip(baselines, outcomes)) / count
    paired_brier_improvements = tuple(
        (baseline - int(outcome)) ** 2
        - (prediction - int(outcome)) ** 2
        for prediction, baseline, outcome in zip(
            predictions, baselines, outcomes))
    groups = {}
    for prediction, outcome in zip(predictions, outcomes):
        groups.setdefault(prediction, []).append(outcome)
    expected_calibration_error = sum(
        len(values) * abs(
            prediction
            - float(sum(values)) / len(values))
        for prediction, values in groups.items()) / count
    positives = sum(outcomes)
    return {
        "baseline_brier": baseline_brier,
        "baseline_log_loss": sum(
            _log_loss(value, outcome)
            for value, outcome in zip(baselines, outcomes)) / count,
        "brier_improvement": baseline_brier - candidate_brier,
        "brier_improvement_interval": _paired_bootstrap_interval(
            paired_brier_improvements),
        "candidate_brier": candidate_brier,
        "candidate_log_loss": sum(
            _log_loss(value, outcome)
            for value, outcome in zip(predictions, outcomes)) / count,
        "exact_prediction_ece": expected_calibration_error,
        "negative": len(rows) - positives,
        "outcome_rate": float(positives) / count,
        "outcome_rate_interval": _wilson(positives, len(rows)),
        "positive": positives,
        "samples": len(rows),
    }


def _strata(rows, key):
    groups = {}
    for row in rows:
        value = dict(row["context"]).get(key, "<missing>")
        groups.setdefault(value, []).append(row)
    return dict(
        (value, _metrics(groups[value])) for value in sorted(groups))


def _readout_strata(rows):
    groups = {}
    for row in rows:
        identity = "+".join(row["readout"]["maximal_rule_ids"])
        groups.setdefault(identity, []).append(row)
    return dict(
        (value, _metrics(groups[value])) for value in sorted(groups))


def run(arguments):
    approved_report = _verified_report(arguments.approved_report)
    consolidation_report = _verified_report(arguments.consolidation_report)
    if consolidation_report["source_report"]["sha256"] != _sha256(
            arguments.approved_report):
        raise ValueError(
            "consolidation is not bound to the approved report")
    proposals, validations, approvals = _approved_artifacts(approved_report)
    consolidation = PromotedRuleConsolidation.from_dict(
        consolidation_report["consolidation"])
    readout = PromotedRuleShadowReadout(
        proposals, validations, approvals, consolidation)

    episodes, episode_sources = shared._partition(
        arguments.episode_store, "promoted-rule-shadow")
    outcome_labels, outcome_sources = shared._outcome_label_partition(
        arguments.outcome_label_store, "promoted-rule-shadow")
    if not shared._outcome_labels_match_partition(
            episodes, outcome_labels, arguments.outcome_target):
        raise ValueError("outcome labels do not match the episode partition")
    adapter = FdasEpisodeInductionAdapter(episodes, outcome_labels)
    evaluations = []
    encoded_count = 0
    encoding_abstentions = 0
    for episode in episodes.episodes():
        base = FdasEpisodeInductionShadow._spec(episode)
        encoded = adapter.encode(EpisodeInductionSpec(
            base.episode_id,
            base.context_keys,
            base.feature_context_keys,
            base.linked_features,
            arguments.outcome_target))
        if not encoded.accepted:
            encoding_abstentions += 1
            continue
        encoded_count += 1
        prediction = readout.read(encoded.induction_episode)
        evaluations.append({
            "context": [list(value) for value in episode.context_signature],
            "episode_id": episode.episode_id,
            "outcome": bool(encoded.induction_episode.outcome),
            "readout": prediction.to_dict(),
        })
    accepted_rows = tuple(
        value for value in evaluations if value["readout"]["accepted"])
    ambiguity_count = sum(
        value["readout"]["reason"] == "ambiguous_maximal_predictions"
        for value in evaluations)
    overall = _metrics(accepted_rows)
    readout_count = len(accepted_rows)
    denominator = float(encoded_count or 1)
    brier_improvement = (
        None if overall is None else overall["brier_improvement"])
    brier_lower = (
        None if overall is None else
        overall["brier_improvement_interval"]["lower"])
    execution_source = dict(
        _source_identity(), runner_sha256=_sha256(os.path.abspath(__file__)))
    engine_sources = episode_sources
    checks = {
        "ambiguity_rate_within_gate": (
            float(ambiguity_count) / denominator
            <= arguments.maximum_ambiguity_rate),
        "brier_improvement_gate_met": (
            brier_improvement is not None
            and brier_improvement
            >= arguments.minimum_brier_improvement),
        "brier_lower_bound_gate_met": (
            brier_lower is not None
            and brier_lower
            >= arguments.minimum_brier_lower_bound),
        "encoded_population_gate_met": (
            encoded_count >= arguments.minimum_encoded),
        "engine_source_requirement_met": (
            not arguments.require_engine_source
            or all(
                value.get("engine_evidence", {}).get("accepted") is True
                for value in engine_sources)),
        "execution_source_requirement_met": (
            not arguments.require_clean_source
            or execution_source.get("dirty") is False),
        "horizon_requirement_met": (
            not arguments.require_horizon
            or all(
                value.get("engine_evidence", {}).get("horizon_reached")
                is True for value in engine_sources)),
        "no_truth_policy_readout_or_action_authority": all(
            value["readout"]["truth_mutated"] is False
            and value["readout"]["policy_authority"] is False
            and value["readout"]["readout_authority"] is False
            and value["readout"]["action_selection_changed"] is False
            for value in evaluations),
        "readout_population_gate_met": (
            readout_count >= arguments.minimum_readouts),
        "source_artifact_chain_is_valid": True,
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "artifacts": {
            "approved_report": {
                "path": _logical(arguments.approved_report),
                "sha256": _sha256(arguments.approved_report),
                "structural_hash": approved_report["structural_hash"],
            },
            "consolidation_report": {
                "path": _logical(arguments.consolidation_report),
                "sha256": _sha256(arguments.consolidation_report),
                "structural_hash": consolidation_report["structural_hash"],
            },
        },
        "claim_scope": (
            "outcome-blind, non-authorizing readout coverage and predictive "
            "calibration on an explicit episode cohort; no action selection, "
            "causal-intervention, gameplay, score, or win-rate claim"),
        "configuration": {
            "maximum_ambiguity_rate": arguments.maximum_ambiguity_rate,
            "minimum_brier_improvement": arguments.minimum_brier_improvement,
            "minimum_brier_lower_bound": (
                arguments.minimum_brier_lower_bound),
            "minimum_encoded": arguments.minimum_encoded,
            "minimum_readouts": arguments.minimum_readouts,
            "outcome_target": arguments.outcome_target,
        },
        "counts": {
            "ambiguous_readouts": ambiguity_count,
            "encoded": encoded_count,
            "encoding_abstentions": encoding_abstentions,
            "no_matching_rule": sum(
                value["readout"]["reason"] == "no_approved_rule_matches"
                for value in evaluations),
            "readouts": readout_count,
        },
        "episode_sources": list(episode_sources),
        "evaluations": evaluations,
        "metrics": {
            "by_actor_homecity_relation": _strata(
                accepted_rows, "actor_homecity_relation"),
            "by_city_production_class": _strata(
                accepted_rows, "city_production_class"),
            "by_readout_rules": _readout_strata(accepted_rows),
            "by_turn_phase": _strata(accepted_rows, "turn_phase_band"),
            "overall": overall,
            "readout_coverage": float(readout_count) / denominator,
            "readout_conflict_rate": float(ambiguity_count) / denominator,
        },
        "outcome_label_sources": list(outcome_sources),
        "schema_version": "1.0",
        "source": execution_source,
    }
    report["structural_hash"] = structural_hash(report)
    if arguments.output:
        shared._write(arguments.output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-report", required=True)
    parser.add_argument("--consolidation-report", required=True)
    parser.add_argument("--episode-store", action="append", required=True)
    parser.add_argument(
        "--outcome-label-store", action="append", required=True)
    parser.add_argument("--outcome-target", required=True)
    parser.add_argument("--output")
    parser.add_argument("--minimum-encoded", type=int, default=1)
    parser.add_argument("--minimum-readouts", type=int, default=1)
    parser.add_argument(
        "--maximum-ambiguity-rate", type=float, default=1.0)
    parser.add_argument(
        "--minimum-brier-improvement", type=float, default=-1.0)
    parser.add_argument(
        "--minimum-brier-lower-bound", type=float, default=-1.0)
    parser.add_argument("--require-engine-source", action="store_true")
    parser.add_argument("--require-horizon", action="store_true")
    parser.add_argument("--require-clean-source", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.minimum_encoded < 1 or arguments.minimum_readouts < 1:
        parser.error("population gates must be positive")
    if not 0.0 <= arguments.maximum_ambiguity_rate <= 1.0:
        parser.error("maximum ambiguity rate must be in [0,1]")
    report = run(arguments)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "brier_improvement": (
            None if report["metrics"]["overall"] is None
            else report["metrics"]["overall"]["brier_improvement"]),
        "encoded": report["counts"]["encoded"],
        "output": arguments.output,
        "readouts": report["counts"]["readouts"],
        "structural_hash": report["structural_hash"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
