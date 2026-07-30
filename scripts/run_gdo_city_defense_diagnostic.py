#!/usr/bin/env python3
"""Run the synthetic GDO-4 B1/B3/B4 city-defence diagnostic."""

import argparse
import itertools
import json
import os
import statistics
import sys
import time


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    CityDefenseAnalysis,
    CityDefenseOperation,
    CityDefenseRequirement,
    DefenseOperationType,
    ExactCityDefenseAssignmentSolver,
)
from freeciv_agent.pressure.resource_claims import (  # noqa: E402
    ClaimHardness,
    GameResourceKind,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
)


DEFAULT_OUTPUT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo4_city_defense_diagnostic.local.json")


def _percentile(rows, fraction):
    ordered = sorted(
        float(value)
        for value in rows)
    return ordered[
        int(float(fraction)
            * (len(ordered) - 1))]


def _summary(rows):
    return {
        "maximum_ms": max(rows),
        "mean_ms": statistics.mean(
            rows),
        "p50_ms": statistics.median(
            rows),
        "p95_ms": _percentile(
            rows, 0.95),
        "p99_ms": _percentile(
            rows, 0.99),
        "sample_count": len(rows),
    }


def _requirement(city_id):
    return CityDefenseRequirement(
        city_id=city_id,
        city_position=(city_id, 0),
        current_defenders=0,
        required_defenders=1,
        response_slots=1,
        deadline_turn=2,
        threat_ids=(
            "visible-threat-{}".format(
                city_id),),
        threat_priority=100.0,
        confidence=1.0)


def _operation(
        operation_id, requirement,
        actor_id, bid):
    claim = ResourceClaim(
        resource=ResourceRef(
            kind=GameResourceKind.ACTOR,
            owner_id="unit:{}".format(
                actor_id),
            subresource="whole_actor",
            scope="player:1"),
        quantity=1,
        window=TurnWindow(1, 2),
        hardness=ClaimHardness.HARD_CURRENT,
        exclusive=True,
        source_operation_id=operation_id,
        source_step_id="move")
    return CityDefenseOperation(
        operation_id=operation_id,
        operation_type=(
            DefenseOperationType
            .MOVE_DEFENDER_TO_CITY),
        requirement_id=(
            requirement.requirement_id),
        city_id=requirement.city_id,
        actor_id=actor_id,
        next_action={
            "action_type": "unit_move",
            "actor_id": actor_id,
            "is_valid": True,
        },
        arrival_turn=1,
        deadline_turn=2,
        expected_prevented_loss=bid,
        opportunity_cost=0.0,
        bid=bid,
        claims=(claim,),
        support_reason=None,
        provenance=(
            "synthetic-gdo4-diagnostic",))


def _analysis(requirements, operations):
    return CityDefenseAnalysis(
        snapshot_id=structural_hash({
            "operations": [
                row.operation_id
                for row in operations],
            "scenario":
                "gdo4-small-graph",
        }),
        threats=(),
        requirements=tuple(
            requirements),
        defenders=(),
        operations=tuple(
            operations),
        omissions=(),
        analyzer_identity=(
            "synthetic-gdo4-diagnostic"))


def _valid(selected, requirements):
    actors = [
        row.actor_id
        for row in selected]
    if len(actors) != len(
            set(actors)):
        return False
    capacities = {
        row.requirement_id:
        row.response_slots
        for row in requirements}
    counts = {}
    for row in selected:
        counts[
            row.requirement_id] = (
                counts.get(
                    row.requirement_id,
                    0) + 1)
    return all(
        count
        <= capacities.get(
            requirement_id, 0)
        for requirement_id, count
        in counts.items())


def _oracle(requirements, operations):
    best = (-1, -1.0, ())
    for count in range(
            len(operations) + 1):
        for selected in itertools.combinations(
                operations, count):
            if not _valid(
                    selected,
                    requirements):
                continue
            candidate = (
                len(selected),
                sum(
                    row.bid
                    for row in selected),
                tuple(sorted(
                    row.operation_id
                    for row in selected)),
            )
            if (candidate[0] > best[0]
                    or (
                        candidate[0]
                        == best[0]
                        and candidate[1]
                        > best[1] + 1e-12)
                    or (
                        candidate[0]
                        == best[0]
                        and abs(
                            candidate[1]
                            - best[1])
                        <= 1e-12
                        and (
                            not best[2]
                            or candidate[2]
                            < best[2]))):
                best = candidate
    return best


def _arm_metrics(
        selected, total_slots):
    covered = len(selected)
    return {
        "actor_conflicts": (
            len(selected)
            - len({
                row.actor_id
                for row in selected})),
        "covered_threat_slots":
            covered,
        "objective_value": sum(
            row.bid
            for row in selected),
        "preventable_loss_proxy":
            float(
                max(
                    0,
                    total_slots
                    - covered)
                * 100),
        "uncovered_threat_slots":
            max(
                0,
                total_slots
                - covered),
    }


def _add(target, row):
    for key, value in row.items():
        target[key] = (
            target.get(key, 0)
            + value)


def run(timing_iterations):
    requirements = (
        _requirement(10),
        _requirement(20),
    )
    bids = {
        (1, 10): 100.0,
        (1, 20): 99.0,
        (2, 10): 98.0,
        (2, 20): 1.0,
        (3, 10): 50.0,
        (3, 20): 49.0,
    }
    all_edges = tuple(
        _operation(
            "actor-{}-city-{}".format(
                actor_id,
                requirement.city_id),
            requirement,
            actor_id,
            bids[
                actor_id,
                requirement.city_id])
        for actor_id in (1, 2, 3)
        for requirement in requirements)
    solver = (
        ExactCityDefenseAssignmentSolver())
    totals = {
        "B1": {},
        "B3": {},
        "B4": {},
    }
    exact_never_worse = True
    exact_matches_oracle = True
    exact_beats_greedy_count = 0
    exact_objective_gain_count = 0
    known_counterexample_passed = False
    scenarios = []
    analyses = []
    for edge_mask in range(
            1 << len(all_edges)):
        operations = tuple(
            row
            for index, row
            in enumerate(all_edges)
            if edge_mask
            & (1 << index))
        analysis = _analysis(
            requirements,
            operations)
        analyses.append(
            analysis)
        ordered = sorted(
            operations,
            key=lambda row: (
                -float(row.bid),
                row.operation_id))
        b1_selected = tuple(
            ordered[:1])
        b3_selected = solver._greedy(
            requirements,
            operations)
        b4 = solver.schedule(
            analysis)
        selected_ids = frozenset(
            b4.selected_operation_ids)
        b4_selected = tuple(
            row for row
            in operations
            if row.operation_id
            in selected_ids)
        arm_rows = {
            "B1": _arm_metrics(
                b1_selected, 2),
            "B3": _arm_metrics(
                b3_selected, 2),
            "B4": _arm_metrics(
                b4_selected, 2),
        }
        for name, row in (
                arm_rows.items()):
            _add(
                totals[name], row)
        oracle = _oracle(
            requirements,
            operations)
        exact_matches_oracle = bool(
            exact_matches_oracle
            and (
                b4.covered_slots,
                b4.objective_value,
                b4.selected_operation_ids,
            ) == oracle)
        exact_never_worse = bool(
            exact_never_worse
            and b4.covered_slots
            >= len(b3_selected))
        if b4.covered_slots > len(
                b3_selected):
            exact_beats_greedy_count += 1
        elif (b4.covered_slots
              == len(b3_selected)
              and b4.objective_value
              > sum(
                  row.bid
                  for row
                  in b3_selected)
              + 1e-12):
            exact_objective_gain_count += 1
        edge_ids = frozenset(
            row.operation_id
            for row in operations)
        counterexample_ids = frozenset((
            "actor-1-city-10",
            "actor-1-city-20",
            "actor-2-city-10",
        ))
        if edge_ids == (
                counterexample_ids):
            known_counterexample_passed = bool(
                len(b3_selected) == 1
                and b4.covered_slots == 2)
        scenarios.append({
            "b1_covered":
                len(b1_selected),
            "b3_covered":
                len(b3_selected),
            "b4_covered":
                b4.covered_slots,
            "edge_mask": edge_mask,
            "exact_status":
                b4.status,
        })

    exact_latency = []
    greedy_latency = []
    for _ in range(
            int(timing_iterations)):
        for analysis in analyses:
            started = (
                time.perf_counter())
            solver._greedy(
                analysis.requirements,
                analysis.operations)
            greedy_latency.append(
                (
                    time.perf_counter()
                    - started) * 1000.0)
            started = (
                time.perf_counter())
            solver.schedule(
                analysis)
            exact_latency.append(
                (
                    time.perf_counter()
                    - started) * 1000.0)

    result = {
        "arms": {
            "B1": {
                "description":
                    "synthetic one-action readout proxy for frozen scalar PF-v2",
                **totals["B1"],
            },
            "B3": {
                "description":
                    "typed identity-aware greedy city-defence assignment",
                **totals["B3"],
            },
            "B4": {
                "description":
                    "typed bounded-exact city-defence assignment",
                **totals["B4"],
            },
        },
        "claim_status":
            "synthetic-mechanism-diagnostic-only",
        "exact_beats_greedy_scenario_count":
            exact_beats_greedy_count,
        "exact_objective_gain_scenario_count":
            exact_objective_gain_count,
        "gates": {
            "all_exact_results_match_brute_force":
                exact_matches_oracle,
            "exact_never_covers_fewer_slots_than_greedy":
                exact_never_worse,
            "known_greedy_counterexample_improved":
                known_counterexample_passed,
            "no_actor_conflicts": all(
                totals[name][
                    "actor_conflicts"] == 0
                for name in (
                    "B1", "B3", "B4")),
            "no_live_authority": True,
            "synthetic_p95_exact_below_50_ms":
                _summary(
                    exact_latency)[
                        "p95_ms"]
                <= 50.0,
        },
        "latency": {
            "B3_greedy":
                _summary(
                    greedy_latency),
            "B4_exact":
                _summary(
                    exact_latency),
        },
        "limitations": [
            "The graph cohort is synthetic and contains no engine outcomes.",
            "B1 is a one-action readout proxy, not a replay of the live controller.",
            "Preventable loss is a fixed uncovered-slot proxy, not calibrated realized loss.",
            "This report cannot support a Freeciv score or win-rate claim.",
        ],
        "policy_authority": False,
        "scenario_count":
            len(scenarios),
        "scenario_digest":
            structural_hash(
                scenarios),
        "schema_version": "1.0",
        "timing_iterations":
            int(timing_iterations),
    }
    result["passed"] = all(
        result["gates"].values())
    result["report_hash"] = (
        structural_hash(
            result))
    return result


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--timing-iterations",
        type=int, default=100)
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    if arguments.timing_iterations < 1:
        parser.error(
            "timing iterations must be positive")
    result = run(
        arguments.timing_iterations)
    output = os.path.abspath(
        arguments.output)
    os.makedirs(
        os.path.dirname(output),
        exist_ok=True)
    with open(
            output, "w",
            encoding="utf-8") as stream:
        json.dump(
            result, stream,
            indent=2,
            sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "output": output,
        "passed": result["passed"],
        "report_hash":
            result["report_hash"],
    }, sort_keys=True))
    return 0 if result[
        "passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
