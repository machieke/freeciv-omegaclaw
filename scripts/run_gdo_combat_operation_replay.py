#!/usr/bin/env python3
"""Compare independent combat ranking with atomic GDO-5 shadow assembly."""

import argparse
from collections import Counter
import json
import os
import statistics
import sys
import time


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    CombatOperationAssembler,
    combat_target_capacities,
)
from freeciv_agent.pressure import (  # noqa: E402
    BoundedExactScheduler,
    ResourceCapacityExtractor,
)
from freeciv_agent.pressure.resource_claims import (  # noqa: E402
    GameResourceKind,
)
from freeciv_agent.state.snapshot import (  # noqa: E402
    AuthoritativeSnapshot,
    CombatActionProbabilityState,
    CombatProbabilityState,
    EconomicState,
    ResearchState,
    SnapshotIdentity,
    UnitState,
)


DEFAULT_CORPUS = os.path.join(
    REPO, "benchmarks", "gdo",
    "combat_operation_scenarios_v1.json")
DEFAULT_OUTPUT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo5_combat_operation_synthetic_diagnostic.json")


def _unit(unit_id, owner, tile, unit_type):
    return UnitState(
        unit_id=int(unit_id),
        owner=int(owner),
        unit_type=str(unit_type),
        type_id=0 if owner == 0 else 1,
        tile=int(tile),
        x=int(tile) % 16,
        y=int(tile) // 16,
        moves_left=3,
        hp=10,
        activity="idle",
        veteran=0,
        transported=False,
        done_moving=False)


def _attack_row(minimum, maximum):
    return CombatActionProbabilityState(
        action_id=45,
        action_name="attack",
        minimum=int(minimum),
        maximum=int(maximum),
        status="bounded")


def _action(actor_id, target_tile):
    return {
        "action_type": "unit_attack",
        "actor_id": int(actor_id),
        "target": {
            "x": int(target_tile) % 16,
            "y": int(target_tile) // 16,
        },
    }


def _snapshot(scenario):
    targets = {
        int(row["unit_id"]): row
        for row in scenario["targets"]
    }
    target_units = tuple(
        _unit(
            target_id, 1,
            row["tile"], "Defender")
        for target_id, row in
        sorted(targets.items()))
    own_units = tuple(
        _unit(
            row["unit_id"], 0,
            84 + index, "Attacker")
        for index, row in enumerate(
            sorted(
                scenario["attackers"],
                key=lambda value:
                    value["unit_id"])))
    legal_actions = []
    probabilities = []
    source_seq = 1
    for attacker in sorted(
            scenario["attackers"],
            key=lambda row: row["unit_id"]):
        actor_id = int(
            attacker["unit_id"])
        for attack in sorted(
                attacker["attacks"],
                key=lambda row: (
                    row["target_unit_id"],
                    row["minimum"],
                    row["maximum"])):
            target_id = int(
                attack[
                    "target_unit_id"])
            target_tile = int(
                targets[target_id][
                    "tile"])
            action = _action(
                actor_id, target_tile)
            legal_actions.append(
                json.dumps(
                    action,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":")))
            stack_ids = tuple(sorted(
                int(value)
                for value in attack.get(
                    "visible_stack_ids",
                    (
                        row["unit_id"]
                        for row in
                        scenario["targets"]
                        if int(row["tile"])
                        == target_tile))))
            selected_target = int(
                attack.get(
                    "selected_target_unit_id",
                    target_id))
            probabilities.append(
                CombatProbabilityState(
                    player_id=0,
                    actor_unit_id=actor_id,
                    target_tile_id=target_tile,
                    target_unit_id=(
                        selected_target),
                    target_city_id=0,
                    target_extra_id=-1,
                    target_unit_ids=stack_ids,
                    action_probabilities=(
                        _attack_row(
                            attack["minimum"],
                            attack["maximum"]),),
                    actor_revision_digest=(
                        structural_hash({
                            "actor_id": actor_id,
                            "scenario":
                                scenario["id"],
                        })),
                    target_stack_revision_digest=(
                        structural_hash({
                            "scenario":
                                scenario["id"],
                            "stack_ids":
                                stack_ids,
                            "target_tile":
                                target_tile,
                        })),
                    turn=1,
                    request_source_seq=(
                        source_seq),
                    response_source_seq=(
                        source_seq + 1)))
            source_seq += 2
    legal_actions = tuple(sorted(
        set(legal_actions)))
    state_hash = structural_hash(
        scenario)
    return AuthoritativeSnapshot(
        identity=SnapshotIdentity(
            game_id="gdo5-synthetic-{}".format(
                scenario["id"]),
            turn=1,
            source_seq=source_seq,
            state_hash=state_hash),
        player_id=0,
        player_alive=True,
        phase="playing",
        ruleset_ready=True,
        ruleset_diagnostic=None,
        research=ResearchState(
            known_techs=(),
            target_id=None,
            target_name=None,
            progress=None,
            cost=None,
            beakers_per_turn=None,
            available=False,
            diagnostic=(
                "synthetic-mechanism-corpus")),
        economy=EconomicState(
            gold=0,
            gold_per_turn=0,
            tax_rate=0,
            science_rate=0,
            luxury_rate=0,
            available=True),
        cities=(),
        units=own_units,
        visible_enemy_units=(
            target_units),
        visible_tile_ids=tuple(sorted(
            {
                int(row["tile"])
                for row in
                scenario["targets"]
            })),
        known_hut_tile_ids=(),
        map_width=16,
        map_height=16,
        map_tiles=(),
        legal_action_json=(
            legal_actions),
        legal_actions_digest=(
            structural_hash(
                legal_actions)),
        legal_action_kinds=(
            "unit_attack",),
        combat_probabilities=tuple(
            sorted(
                probabilities,
                key=lambda row: (
                    row.actor_unit_id,
                    row.target_tile_id))))


def _resolved_target(result):
    if result.target_unit_id > 0:
        return result.target_unit_id
    if len(result.target_unit_ids) == 1:
        return result.target_unit_ids[0]
    return None


def _independent_readout(snapshot, action_budget):
    candidates = []
    for result in snapshot.combat_probabilities:
        probability = result.action_probability(
            "attack")
        target_id = _resolved_target(
            result)
        if (
            target_id is None
            or probability is None
            or probability.status
                != "bounded"
            or probability
                .upper_probability
                <= 0.0
        ):
            continue
        candidates.append({
            "actor_id":
                result.actor_unit_id,
            "lower":
                probability
                .lower_probability,
            "target_unit_id":
                target_id,
            "upper":
                probability
                .upper_probability,
        })
    candidates = sorted(
        candidates,
        key=lambda row: (
            -row["lower"],
            -row["upper"],
            row["actor_id"],
            row["target_unit_id"]))
    selected = []
    actors = set()
    for row in candidates:
        if (
            row["actor_id"] in actors
            or len(selected)
                >= action_budget
        ):
            continue
        selected.append(row)
        actors.add(
            row["actor_id"])
    available_by_target = Counter(
        row["target_unit_id"]
        for row in candidates)
    selected_by_target = Counter(
        row["target_unit_id"]
        for row in selected)
    joint_targets = {
        target_id
        for target_id, count
        in available_by_target.items()
        if count >= 2
    }
    return {
        "candidate_count":
            len(candidates),
        "duplicated_target_count":
            sum(
                count > 1
                for count in
                selected_by_target
                .values()),
        "partial_activation_count":
            sum(
                0 < selected_by_target[
                    target_id] < 2
                for target_id in
                joint_targets),
        "selected_action_count":
            len(selected),
        "selected_actions":
            selected,
    }


def _atomic_readout(
        snapshot, scenario,
        ruleset_digest=(
            "synthetic-ruleset-digest")):
    assemblies = (
        CombatOperationAssembler()
        .assemble(
            snapshot,
            str(ruleset_digest)))
    capacity_snapshot = (
        ResourceCapacityExtractor()
        .extract(
            snapshot,
            action_budget=int(
                scenario[
                    "action_budget"])))
    capacities = (
        capacity_snapshot.capacities
        + combat_target_capacities(
            assemblies, snapshot))
    premise_packets = {
        premise_id: value
        for assembly in assemblies
        for premise_id, value in
        assembly.initial_premise_packets
    }
    schedule = (
        BoundedExactScheduler(
            node_budget=4096,
            time_budget_ms=20.0)
        .schedule(
            tuple(
                assembly
                .resource_request
                for assembly
                in assemblies),
            capacities,
            requirement_sets=tuple(
                assembly
                .requirement_set
                for assembly
                in assemblies),
            premise_packets=(
                premise_packets)))
    assembly_by_id = {
        assembly.spec.operation_id:
            assembly
        for assembly in assemblies
    }
    selected = [
        assembly_by_id[operation_id]
        for operation_id in
        schedule.selected_operation_ids
    ]
    targets = Counter(
        assembly.target_unit_id
        for assembly in selected)
    actors = Counter(
        participant.actor_id
        for assembly in selected
        for participant in
        assembly.spec.participants
        if participant.required)
    selected_claims = (
        schedule.selected_claims())
    action_budget_used = sum(
        claim.quantity
        for claim in selected_claims
        if claim.resource.kind
            == GameResourceKind
            .ACTION_BUDGET)
    reservations_complete = all(
        {
            claim.resource.owner_id
            for claim in
            assembly
            .resource_request.claims
            if claim.resource.kind
                == GameResourceKind.ACTOR
        } == {
            participant.actor_id
            for participant in
            assembly.spec.participants
            if participant.required
        }
        for assembly in selected)
    action_claims_exact = all(
        [
            claim.quantity
            for claim in
            assembly
            .resource_request.claims
            if claim.resource.kind
                == GameResourceKind
                .ACTION_BUDGET
        ] == [len(
            assembly.spec.steps)]
        for assembly in assemblies)
    reason_by_operation_id = {
        row.operation_id: (
            "shadow-schedule-selected-no-policy-authority"
            if row.selected
            else row.reason)
        for row in
        schedule.entries
    }
    return {
        "action_budget_used":
            action_budget_used,
        "action_claims_exact":
            action_claims_exact,
        "actor_conflict_count":
            sum(
                count > 1
                for count in
                actors.values()),
        "candidate_count":
            len(assemblies),
        "candidate_operation_ids":
            sorted(
                assembly.spec.operation_id
                for assembly in
                assemblies),
        "decision_digest":
            schedule
            .decision_digest,
        "duplicated_target_count":
            sum(
                count > 1
                for count in
                targets.values()),
        "partial_activation_count":
            0,
        "policy_authority": False,
        "rejection_reasons": dict(sorted(
            Counter(
                row.reason
                for row in
                schedule.entries
                if not row.selected)
            .items())),
        "reason_by_operation_id":
            reason_by_operation_id,
        "reservations_complete":
            reservations_complete,
        "schedule_status":
            schedule.status.value,
        "selected_operation_count":
            len(selected),
        "selected_operation_ids": list(
            schedule
            .selected_operation_ids),
        "selected_target_unit_ids":
            sorted(targets),
        "shadow_only": True,
    }


def _evaluate(scenario):
    started = time.perf_counter()
    snapshot = _snapshot(
        scenario)
    independent = (
        _independent_readout(
            snapshot,
            int(scenario[
                "action_budget"])))
    atomic = _atomic_readout(
        snapshot, scenario)
    return {
        "action_budget": int(
            scenario[
                "action_budget"]),
        "atomic": atomic,
        "expect_atomic_candidates": bool(
            scenario[
                "expect_atomic_candidates"]),
        "independent": independent,
        "latency_ms": (
            time.perf_counter()
            - started) * 1000.0,
        "scenario_id":
            scenario["id"],
        "snapshot_id":
            snapshot.snapshot_id,
    }


def _percentile(values, fraction):
    rows = sorted(
        float(value)
        for value in values)
    return rows[
        int(float(fraction)
            * (len(rows) - 1))]


def _latency_summary(values):
    return {
        "maximum_ms": max(values),
        "mean_ms": statistics.mean(
            values),
        "p50_ms": statistics.median(
            values),
        "p95_ms": _percentile(
            values, 0.95),
        "sample_count": len(values),
    }


def run(corpus, iterations):
    scenarios = tuple(
        corpus["scenarios"])
    first = [
        _evaluate(scenario)
        for scenario in scenarios
    ]
    latency = [
        row["latency_ms"]
        for row in first
    ]
    decision_digests = {
        row["scenario_id"]: {
            row["atomic"][
                "decision_digest"]
        }
        for row in first
    }
    for _ in range(
            iterations - 1):
        for scenario in scenarios:
            row = _evaluate(
                scenario)
            latency.append(
                row["latency_ms"])
            decision_digests[
                row["scenario_id"]].add(
                    row["atomic"][
                        "decision_digest"])
    by_id = {
        row["scenario_id"]: row
        for row in first
    }
    gates = {
        "action_budget_never_exceeded":
            all(
                row["atomic"][
                    "action_budget_used"]
                <= row[
                    "action_budget"]
                for row in first),
        "all_action_budget_claims_exact":
            all(
                row["atomic"][
                    "action_claims_exact"]
                for row in first),
        "ambiguous_target_fails_closed":
            by_id[
                "ambiguous-target-sentinel"
            ]["atomic"][
                "candidate_count"] == 0,
        "atomic_actor_conflicts_zero":
            all(
                row["atomic"][
                    "actor_conflict_count"]
                == 0
                for row in first),
        "atomic_duplicate_targeting_zero":
            all(
                row["atomic"][
                    "duplicated_target_count"]
                == 0
                for row in first),
        "atomic_partial_activation_zero":
            all(
                row["atomic"][
                    "partial_activation_count"]
                == 0
                for row in first),
        "atomic_reservations_complete":
            all(
                row["atomic"][
                    "reservations_complete"]
                for row in first),
        "disjoint_targets_schedule_together":
            by_id[
                "two-disjoint-targets"
            ]["atomic"][
                "selected_operation_count"]
            == 2,
        "independent_duplicate_targeting_observed":
            sum(
                row["independent"][
                    "duplicated_target_count"]
                for row in first) > 0,
        "independent_partial_activation_observed":
            sum(
                row["independent"][
                    "partial_activation_count"]
                for row in first) > 0,
        "insufficient_budget_selects_no_atomic_operation":
            by_id[
                "insufficient-action-budget"
            ]["atomic"][
                "selected_operation_count"]
            == 0,
        "joint_support_expectations_match":
            all(
                (
                    row["atomic"][
                        "candidate_count"] > 0)
                == row[
                    "expect_atomic_candidates"]
                for row in first),
        "no_policy_authority":
            all(
                row["atomic"][
                    "shadow_only"]
                and not row["atomic"][
                    "policy_authority"]
                for row in first),
        "p95_compute_below_20_ms":
            _percentile(
                latency, 0.95)
            < 20.0,
        "schedule_decisions_deterministic":
            all(
                len(values) == 1
                for values in
                decision_digests.values()),
        "unambiguous_sentinel_is_supported":
            by_id[
                "unambiguous-target-sentinel"
            ]["atomic"][
                "candidate_count"] > 0,
        "zero_interval_fails_closed":
            by_id[
                "zero-interval-is-not-support"
            ]["atomic"][
                "candidate_count"] == 0,
    }
    report = {
        "authority":
            "synthetic-mechanism-only",
        "claim_status":
            "diagnostic-only-no-outcome-or-score-claim",
        "corpus_hash":
            structural_hash(corpus),
        "gates": gates,
        "iterations": iterations,
        "latency": _latency_summary(
            latency),
        "passed": all(
            gates.values()),
        "policy_authority": False,
        "scenario_count":
            len(scenarios),
        "scenarios": first,
        "schema_version": "1.0",
    }
    report["report_hash"] = (
        structural_hash(report))
    return report


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--corpus",
        default=DEFAULT_CORPUS)
    parser.add_argument(
        "--iterations",
        type=int,
        default=100)
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10000:
        parser.error(
            "--iterations must be in 1..10000")
    with open(
            args.corpus,
            encoding="utf-8") as stream:
        corpus = json.load(
            stream)
    report = run(
        corpus,
        args.iterations)
    os.makedirs(
        os.path.dirname(
            os.path.abspath(
                args.output)),
        exist_ok=True)
    with open(
            args.output, "wb") as stream:
        stream.write(
            canonical_json_bytes(
                report))
        stream.write(b"\n")
    print(json.dumps({
        "output":
            os.path.abspath(
                args.output),
        "passed":
            report["passed"],
        "report_hash":
            report[
                "report_hash"],
    }, sort_keys=True))
    return 0 if report[
        "passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
