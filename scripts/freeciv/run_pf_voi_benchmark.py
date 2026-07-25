#!/usr/bin/env python3
"""Deterministic PF-PLN Phase 3 exhaustive-VOI and test-selection benchmark."""

import argparse
import json
import math
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.beliefs import ModelProvenance  # noqa: E402
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    CostVector,
    Hypothesis,
    ObservationOutcome,
    ObservationTest,
    ValueOfInformationPlanner,
)


def _entropy(probabilities):
    return -sum(
        value * math.log(value, 2)
        for value in probabilities if value > 0)


def _exhaustive_gain(hypotheses, test):
    prior = dict(
        (row.hypothesis_id, row.probability) for row in hypotheses)
    expected = 0.0
    for outcome in test.outcomes:
        probability = sum(
            prior[key] * outcome.likelihood(key) for key in prior)
        if not probability:
            continue
        posterior = tuple(
            prior[key] * outcome.likelihood(key) / probability
            for key in prior)
        expected += probability * _entropy(posterior)
    return _entropy(prior.values()) - expected


def _test(case, label, reliability, provenance):
    return ObservationTest(
        test_id="case-{:04d}-{}".format(case, label),
        atom_id="abduction-conflict-{:04d}".format(case),
        outcomes=(
            ObservationOutcome("attack-signal", (
                ("attack", reliability),
                ("transit", 1.0 - reliability),
            )),
            ObservationOutcome("transit-signal", (
                ("attack", 1.0 - reliability),
                ("transit", reliability),
            )),
        ),
        cost=CostVector(compute=1.0),
        model_provenance=provenance,
    )


def run(cases=256):
    provenance = ModelProvenance(
        "simulator",
        "freeciv-abduction-observation-model",
        "1.0",
        structural_hash({
            "model": "freeciv-abduction-observation-model",
            "version": "1.0",
        }),
        False,
        0.6,
    )
    parity_errors = 0
    selected_total = 0.0
    random_total = 0.0
    selected_counts = {}
    tests_evaluated = 0
    for case in range(int(cases)):
        attack_probability = 0.1 + 0.8 * (
            float(case % 17) / 16.0)
        hypotheses = (
            Hypothesis("attack", attack_probability),
            Hypothesis("transit", 1.0 - attack_probability),
        )
        tests = (
            _test(case, "destination-scout", 0.95, provenance),
            _test(case, "settler-inspection", 0.78, provenance),
            _test(case, "diplomatic-check", 0.64, provenance),
            _test(case, "banner-color", 0.50, provenance),
        )
        ranked = ValueOfInformationPlanner.rank(hypotheses, tests)
        exhaustive = sorted(
            tests,
            key=lambda row: (
                -_exhaustive_gain(hypotheses, row), row.test_id))
        if [row.test.test_id for row in ranked] != [
                row.test_id for row in exhaustive]:
            parity_errors += 1
        selected = ranked[0]
        selected_total += selected.expected_information_gain
        random_total += sum(
            row.expected_information_gain for row in ranked) / len(ranked)
        label = selected.test.test_id.rsplit("-", 2)[-2] + "-" + (
            selected.test.test_id.rsplit("-", 1)[-1])
        selected_counts[label] = selected_counts.get(label, 0) + 1
        tests_evaluated += len(tests)

    selected_mean = selected_total / float(cases)
    random_mean = random_total / float(cases)
    absolute_margin = selected_mean - random_mean
    report = {
        "schema_version": "1.0",
        "benchmark": "pf-pln-phase-3-exhaustive-voi",
        "configuration": {
            "cases": int(cases),
            "hypotheses_per_case": 2,
            "tests_per_case": 4,
        },
        "exhaustive_parity": {
            "cases": int(cases),
            "ranking_errors": parity_errors,
            "tests_evaluated": tests_evaluated,
        },
        "selection": {
            "absolute_information_gain_margin_bits": absolute_margin,
            "relative_lift_over_uniform_random": (
                absolute_margin / random_mean if random_mean else None),
            "selected_mean_information_gain_bits": selected_mean,
            "selected_test_counts": dict(sorted(selected_counts.items())),
            "uniform_random_expected_mean_information_gain_bits": random_mean,
        },
        "simulator_provenance": provenance.to_dict(),
    }
    report["artifact_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=256)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    if args.cases < 1:
        parser.error("--cases must be positive")
    report = run(args.cases)
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.out:
        parent = os.path.dirname(os.path.abspath(args.out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    sys.stdout.write(rendered)
    return 0 if (
        report["exhaustive_parity"]["ranking_errors"] == 0
        and report["selection"]["absolute_information_gain_margin_bits"] > 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
