#!/usr/bin/env python3
"""Freeze quarantined FDAS induction proposals before held-out collection."""

import argparse
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
BENCHMARKS = os.path.join(REPO, "benchmarks")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for location in (SRC, BENCHMARKS, SCRIPT_DIR):
    if location not in sys.path:
        sys.path.insert(0, location)

import run_fdas_induction_holdout as shared  # noqa: E402

from freeciv.harness.runner import _source_identity  # noqa: E402
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    EpisodeInductionSpec,
    FdasEpisodeInductionAdapter,
    FdasEpisodeInductionShadow,
    IMMEDIATE_GOAL_RELIEF_TARGET,
    delayed_outcome_episode_eligible,
)
from freeciv_agent.pressure import InductionLedger, PatternMiner  # noqa: E402


def run(arguments):
    training, training_sources = shared._partition(
        arguments.training_store, "discovery")
    delayed_target = (
        arguments.outcome_target != IMMEDIATE_GOAL_RELIEF_TARGET)
    if delayed_target:
        if not arguments.training_outcome_label_store:
            raise ValueError(
                "delayed discovery target requires outcome-label stores")
        outcomes, outcome_sources = shared._outcome_label_partition(
            arguments.training_outcome_label_store, "discovery")
    else:
        if arguments.training_outcome_label_store:
            raise ValueError(
                "immediate discovery target cannot accept delayed labels")
        outcomes = None
        outcome_sources = ()
    configuration = {
        "maximum_antecedents": arguments.maximum_antecedents,
        "maximum_candidates": arguments.maximum_candidates,
        "minimum_residual": arguments.minimum_residual,
        "minimum_support": arguments.minimum_support,
        "outcome_target": arguments.outcome_target,
    }
    ledger_identity = "fdas-discovery-ledger:{}".format(structural_hash({
        "configuration": configuration,
        "outcome_label_store_digest": (
            None if outcomes is None else outcomes.store_digest),
        "training_store_digest": training.store_digest,
    }))
    ledger = InductionLedger(arguments.ledger, identity=ledger_identity)
    if ledger.promoted_rules():
        raise ValueError("discovery ledger cannot contain promoted rules")
    adapter = FdasEpisodeInductionAdapter(training, outcomes)

    def spec(episode):
        base = FdasEpisodeInductionShadow._spec(episode)
        return EpisodeInductionSpec(
            base.episode_id,
            base.context_keys,
            base.feature_context_keys,
            base.linked_features,
            arguments.outcome_target)

    encodings = tuple(
        adapter.encode(spec(episode)) for episode in training.episodes())
    rows = tuple(
        value.induction_episode for value in encodings if value.accepted)
    miner = PatternMiner(
        minimum_support=arguments.minimum_support,
        maximum_antecedents=arguments.maximum_antecedents,
        minimum_residual=arguments.minimum_residual,
        maximum_candidates=arguments.maximum_candidates)
    if len(rows) < miner.minimum_support:
        proposals = ()
        mining_reason = "insufficient-attributable-discovery-support"
    else:
        proposals = miner.mine(
            rows,
            "defense-operation-relieves-goal"
            if not delayed_target else arguments.outcome_target)
        mining_reason = (
            "quarantined-discovery-candidates-mined"
            if proposals else "no-pattern-cleared-residual-gate")
    newly_quarantined = []
    duplicate_proposals = []
    for proposal in proposals:
        target = (
            newly_quarantined
            if ledger.propose(proposal) else duplicate_proposals)
        target.append(proposal.proposal_id)
    ledger.save()
    execution_source = dict(
        _source_identity(),
        runner_sha256=shared._sha256(os.path.abspath(__file__)))
    checks = {
        "engine_source_requirement_met": (
            not arguments.require_engine_source
            or all(
                value.get("engine_evidence", {}).get("accepted") is True
                for value in training_sources)),
        "execution_source_requirement_met": (
            not arguments.require_engine_source
            or execution_source.get("dirty") is False),
        "horizon_requirement_met": (
            not arguments.require_horizon
            or all(
                value.get("engine_evidence", {}).get("horizon_reached")
                is True for value in training_sources)),
        "ledger_is_persisted_and_hash_bound": (
            os.path.isfile(arguments.ledger)
            and ledger.snapshot()["state_hash"] == ledger.state_hash),
        "no_validation_promotion_or_authority": (
            not ledger.promoted_rules()),
        "outcome_label_coverage_requirement_met": (
            not delayed_target
            or all(
                outcomes.for_episode(
                    episode.episode_id, arguments.outcome_target) is not None
                for episode in training.episodes()
                if delayed_outcome_episode_eligible(
                    episode, arguments.outcome_target))),
        "outcome_label_target_requirement_met": (
            not delayed_target
            or (all(
                value.target_id == arguments.outcome_target
                for value in outcomes.labels())
                and shared._outcome_labels_match_partition(
                    training, outcomes, arguments.outcome_target))),
        "resolved_discovery_population_is_nonempty": bool(rows),
        "proposal_requirement_met": (
            not arguments.require_proposal or bool(proposals)),
        "training_sources_are_nonempty": bool(training.episodes()),
    }
    semantic_result = {
        "duplicate_proposal_ids": sorted(duplicate_proposals),
        "encoding_results": [value.to_dict() for value in encodings],
        "ledger_hash": ledger.state_hash,
        "mining_reason": mining_reason,
        "newly_quarantined_proposal_ids": sorted(newly_quarantined),
        "policy_authority": False,
        "proposals": [value.to_dict() for value in proposals],
        "readout_authority": False,
        "truth_mutated": False,
    }
    semantic_result["result_hash"] = structural_hash(semantic_result)
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "verified source-bound delayed discovery encoding, bounded "
            "proposal mining, durable quarantine, and zero validation, "
            "promotion, truth, policy, or readout authority; proposals require "
            "a future disjoint held-out cohort"),
        "configuration": configuration,
        "ledger": {
            "identity": ledger_identity,
            "path": shared._logical(arguments.ledger),
            "state_hash": ledger.state_hash,
        },
        "outcome_label_sources": list(outcome_sources),
        "result": semantic_result,
        "schema_version": "1.0",
        "source": execution_source,
        "training_sources": list(training_sources),
    }
    report["structural_hash"] = structural_hash(report)
    if arguments.output:
        shared._write(arguments.output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-store", action="append", required=True)
    parser.add_argument("--training-outcome-label-store", action="append")
    parser.add_argument(
        "--outcome-target", default=IMMEDIATE_GOAL_RELIEF_TARGET)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--output")
    parser.add_argument("--minimum-support", type=int, default=4)
    parser.add_argument("--maximum-antecedents", type=int, default=2)
    parser.add_argument("--minimum-residual", type=float, default=0.05)
    parser.add_argument("--maximum-candidates", type=int, default=32)
    parser.add_argument("--require-engine-source", action="store_true")
    parser.add_argument("--require-horizon", action="store_true")
    parser.add_argument("--require-proposal", action="store_true")
    arguments = parser.parse_args(argv)
    report = run(arguments)
    summary = {
        "accepted": report["acceptance"]["accepted"],
        "output": arguments.output,
        "proposals": len(report["result"]["proposals"]),
        "structural_hash": report["structural_hash"],
    }
    print(__import__("json").dumps(summary, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
