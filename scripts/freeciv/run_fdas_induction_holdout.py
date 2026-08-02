#!/usr/bin/env python3
"""Run the fail-closed FDAS induction train/holdout lifecycle."""

import argparse
import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
BENCHMARKS = os.path.join(REPO, "benchmarks")
for location in (SRC, BENCHMARKS):
    if location not in sys.path:
        sys.path.insert(0, location)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DecisionEpisodeStore,
    FdasEpisodeInductionHeldoutGate,
    combine_episode_stores,
)
from freeciv_agent.pressure import (  # noqa: E402
    InductionLedger,
    PatternMiner,
    ReplayValidator,
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


def _load_source(path):
    path = os.path.abspath(path)
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    identity = raw.get("persistence_identity")
    if not isinstance(identity, str) or not identity:
        raise ValueError("episode store has no persistence identity: {}".format(
            path))
    store = DecisionEpisodeStore.load(path, identity)
    if store.quarantined:
        raise ValueError("episode store failed verification: {}: {}".format(
            path, store.quarantine_reason))
    source = {
        "path": _logical(path),
        "sha256": _sha256(path),
        "store_digest": store.store_digest,
        "persistence_identity": store.persistence_identity,
        "episodes": len(store.episodes()),
    }
    directory = os.path.dirname(path)
    engine_paths = dict(
        (name, os.path.join(directory, name))
        for name in ("events.jsonl", "manifest.json", "status.json"))
    if all(os.path.isfile(value) for value in engine_paths.values()):
        with open(engine_paths["manifest.json"], encoding="utf-8") as stream:
            manifest = json.load(stream)
        with open(engine_paths["status.json"], encoding="utf-8") as stream:
            status = json.load(stream)
        validation = validate_file(engine_paths["events.jsonl"])
        engine_checks = {
            "completed": status.get("completed") is True,
            "event_ledger_valid_without_warnings": (
                validation.valid and not validation.warnings),
            "source_is_clean": (
                manifest.get("source", {}).get("dirty") is False),
        }
        source["engine_evidence"] = {
            "accepted": all(engine_checks.values()),
            "checks": engine_checks,
            "events": {
                "path": _logical(engine_paths["events.jsonl"]),
                "sha256": _sha256(engine_paths["events.jsonl"]),
                "validation": validation.to_dict(),
            },
            "horizon_reached": status.get("horizon_reached") is True,
            "manifest": {
                "path": _logical(engine_paths["manifest.json"]),
                "sha256": _sha256(engine_paths["manifest.json"]),
                "source": manifest.get("source"),
            },
            "status": {
                "path": _logical(engine_paths["status.json"]),
                "sha256": _sha256(engine_paths["status.json"]),
            },
        }
    return store, source


def _partition(paths, label):
    loaded = tuple(_load_source(path) for path in paths)
    stores = tuple(value[0] for value in loaded)
    sources = tuple(value[1] for value in loaded)
    identity = "fdas-{}-cohort:{}".format(
        label,
        structural_hash(sorted(value.store_digest for value in stores)))
    return combine_episode_stores(stores, identity), sources


def _write(path, value):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    temporary = os.path.abspath(path) + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, os.path.abspath(path))


def run(arguments):
    training, training_sources = _partition(
        arguments.training_store, "training")
    holdout, holdout_sources = _partition(
        arguments.holdout_store, "holdout")
    configuration = {
        "contradiction_threshold": arguments.contradiction_threshold,
        "contradiction_tolerance": arguments.contradiction_tolerance,
        "maximum_antecedents": arguments.maximum_antecedents,
        "maximum_candidates": arguments.maximum_candidates,
        "minimum_activations": arguments.minimum_activations,
        "minimum_brier_improvement": arguments.minimum_brier_improvement,
        "minimum_calibration_improvement": (
            arguments.minimum_calibration_improvement),
        "minimum_residual": arguments.minimum_residual,
        "minimum_samples": arguments.minimum_samples,
        "minimum_support": arguments.minimum_support,
    }
    ledger_identity = "fdas-heldout-ledger:{}".format(structural_hash({
        "configuration": configuration,
        "holdout_store_digest": holdout.store_digest,
        "training_store_digest": training.store_digest,
    }))
    ledger = InductionLedger(
        arguments.ledger, identity=ledger_identity)
    # Persist even an empty ledger so a zero-candidate result remains a
    # durable, hash-verifiable outcome rather than an absent artifact.
    ledger.save()
    gate = FdasEpisodeInductionHeldoutGate(
        training,
        holdout,
        ledger,
        miner=PatternMiner(
            minimum_support=arguments.minimum_support,
            maximum_antecedents=arguments.maximum_antecedents,
            minimum_residual=arguments.minimum_residual,
            maximum_candidates=arguments.maximum_candidates),
        validator=ReplayValidator(
            minimum_samples=arguments.minimum_samples,
            minimum_activations=arguments.minimum_activations,
            minimum_brier_improvement=arguments.minimum_brier_improvement,
            minimum_calibration_improvement=(
                arguments.minimum_calibration_improvement),
            contradiction_tolerance=arguments.contradiction_tolerance,
            contradiction_threshold=arguments.contradiction_threshold))
    result = gate.evaluate()
    result_value = result.to_dict()
    execution_source = dict(
        _source_identity(),
        runner_sha256=_sha256(os.path.abspath(__file__)))
    checks = {
        "all_candidates_received_heldout_verdict": (
            len(result.validations) == len(result.proposals)),
        "every_promotion_has_versioned_approval": (
            len(result.approvals) == len(result.promoted_rule_ids)),
        "ledger_is_persisted_and_hash_bound": (
            os.path.isfile(arguments.ledger)
            and ledger.snapshot()["state_hash"] == result.ledger_hash),
        "engine_source_requirement_met": (
            not arguments.require_engine_source
            or all(
                value.get("engine_evidence", {}).get("accepted") is True
                for value in training_sources + holdout_sources)),
        "execution_source_requirement_met": (
            not arguments.require_engine_source
            or execution_source.get("dirty") is False),
        "horizon_requirement_met": (
            not arguments.require_horizon
            or all(
                value.get("engine_evidence", {}).get("horizon_reached")
                is True
                for value in training_sources + holdout_sources)),
        "no_truth_policy_or_readout_authority": (
            result.truth_mutated is False
            and result.policy_authority is False
            and result.readout_authority is False),
        "proposal_requirement_met": (
            not arguments.require_proposal or bool(result.proposals)),
        "promotion_requirement_met": (
            not arguments.require_promotion
            or bool(result.promoted_rule_ids)),
        "source_partitions_are_nonempty": (
            bool(training.episodes()) and bool(holdout.episodes())),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "verified FDAS episode-store partitioning, bounded pattern mining, "
            "disjoint held-out validation, versioned promotion approval, and "
            "zero truth/policy/readout authority; no live discovery quality, "
            "score, gameplay, or win-rate claim"),
        "configuration": configuration,
        "holdout_sources": list(holdout_sources),
        "ledger": {
            "identity": ledger_identity,
            "path": _logical(arguments.ledger),
            "state_hash": ledger.state_hash,
        },
        "result": result_value,
        "schema_version": "1.0",
        "source": execution_source,
        "training_sources": list(training_sources),
    }
    report["structural_hash"] = structural_hash(report)
    if arguments.output:
        _write(arguments.output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-store", action="append", required=True)
    parser.add_argument("--holdout-store", action="append", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--output")
    parser.add_argument("--minimum-support", type=int, default=4)
    parser.add_argument("--maximum-antecedents", type=int, default=2)
    parser.add_argument("--minimum-residual", type=float, default=0.05)
    parser.add_argument("--maximum-candidates", type=int, default=32)
    parser.add_argument("--minimum-samples", type=int, default=8)
    parser.add_argument("--minimum-activations", type=int, default=4)
    parser.add_argument("--minimum-brier-improvement", type=float, default=0.001)
    parser.add_argument(
        "--minimum-calibration-improvement", type=float, default=0.0)
    parser.add_argument("--contradiction-tolerance", type=float, default=0.0)
    parser.add_argument("--contradiction-threshold", type=float, default=0.70)
    parser.add_argument("--require-proposal", action="store_true")
    parser.add_argument("--require-promotion", action="store_true")
    parser.add_argument("--require-engine-source", action="store_true")
    parser.add_argument("--require-horizon", action="store_true")
    arguments = parser.parse_args(argv)
    report = run(arguments)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "demoted": len(report["result"]["demoted_rule_ids"]),
        "output": arguments.output,
        "promoted": len(report["result"]["promoted_rule_ids"]),
        "proposals": len(report["result"]["proposals"]),
        "structural_hash": report["structural_hash"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
