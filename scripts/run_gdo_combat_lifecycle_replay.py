#!/usr/bin/env python3
"""Exercise GDO-5 combat lifecycle and release semantics in shadow replay."""

import argparse
import copy
from dataclasses import replace
import json
import os
import statistics
import sys
import time


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(
    REPO, "scripts")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    CombatOperationAssembler,
    CombatOperationLifecycle,
    combat_target_capacities,
)
from freeciv_agent.pressure import (  # noqa: E402
    BoundedExactScheduler,
    ResourceCapacityExtractor,
)
import run_gdo_combat_operation_replay as mechanism  # noqa: E402


DEFAULT_CORPUS = os.path.join(
    REPO, "benchmarks", "gdo",
    "combat_operation_scenarios_v1.json")
DEFAULT_OUTPUT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo5_combat_operation_lifecycle_diagnostic.json")
FLOW_IDS = (
    "first-step-neutralizes",
    "follow-up-neutralizes",
    "follow-up-no-effect",
    "blocked-repaired",
    "participant-removed",
    "action-rejected",
    "expires-uncommitted",
    "external-neutralization-before-commit",
    "next-step-capacity-blocked",
)
EXPECTED_FINAL_STATES = {
    "action-rejected": "failed",
    "blocked-repaired": "completed",
    "expires-uncommitted": "expired",
    "external-neutralization-before-commit":
        "completed",
    "first-step-neutralizes": "completed",
    "follow-up-neutralizes": "completed",
    "follow-up-no-effect": "failed",
    "next-step-capacity-blocked":
        "blocked",
    "participant-removed": "abandoned",
}


def _percentile(values, fraction):
    rows = sorted(
        float(value)
        for value in values)
    return rows[
        int(float(fraction)
            * (len(rows) - 1))]


def _summary(values):
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


def _next_snapshot(
        snapshot, source_seq,
        turn=None, **changes):
    identity = replace(
        snapshot.identity,
        source_seq=int(
            source_seq),
        state_hash=structural_hash({
            "changes": sorted(
                changes),
            "source_seq":
                int(source_seq),
            "turn": (
                snapshot.turn
                if turn is None
                else int(turn)),
        }),
        turn=(
            snapshot.turn
            if turn is None
            else int(turn)))
    return replace(
        snapshot,
        identity=identity,
        **changes)


def _assembly_schedule(snapshot):
    assembly = (
        CombatOperationAssembler()
        .assemble(
            snapshot,
            "ruleset-proof",
            ruleset_ir=(
                mechanism
                ._synthetic_ruleset()))[0])
    capacities = (
        ResourceCapacityExtractor()
        .extract(
            snapshot,
            action_budget=8)
        .capacities
        + combat_target_capacities(
            (assembly,), snapshot))
    schedule = (
        BoundedExactScheduler(
            node_budget=128,
            time_budget_ms=20.0)
        .schedule(
            (assembly.resource_request,),
            capacities,
            requirement_sets=(
                assembly
                .requirement_set,),
            premise_packets=dict(
                assembly
                .initial_premise_packets)))
    return assembly, schedule


def _update_row(update):
    reservation = update.reservation
    released = (
        update.released_reservation)
    return {
        "disposition":
            update.disposition,
        "next_action":
            update.next_action,
        "operation_id":
            update.operation_id,
        "probability_interval": (
            None
            if update
            .probability_interval
            is None
            else update
            .probability_interval
            .to_dict()),
        "reason": update.reason,
        "released_claim_count": (
            0 if released is None else
            len(released.claims)),
        "released_reason": (
            None if released is None
            else released.reason),
        "reservation_action_budget": (
            None
            if reservation is None
            else next(
                (
                    claim.quantity
                    for claim in
                    reservation.claims
                    if claim.resource
                    .kind.value
                    == "action_budget"
                ),
                None)),
        "reservation_claim_count": (
            0 if reservation is None
            else len(
                reservation.claims)),
        "reservation_snapshot_id": (
            None if reservation is None
            else reservation.snapshot_id),
        "state": update.state,
        "step_index":
            update.step_index,
    }


def _record(trace, updates):
    trace.extend(
        _update_row(row)
        for row in updates)


def _run_flow(flow_id, scenario):
    started = time.perf_counter()
    snapshot = mechanism._snapshot(
        scenario)
    assembly, schedule = (
        _assembly_schedule(
            snapshot))
    lifecycle = (
        CombatOperationLifecycle(
            "synthetic:{}".format(
                flow_id)))
    trace = []
    _record(
        trace,
        lifecycle.register_schedule(
            (assembly,),
            schedule,
            snapshot))

    if flow_id == (
            "external-neutralization-before-commit"):
        _record(
            trace,
            lifecycle.observe(
                _next_snapshot(
                    snapshot, 20,
                    visible_enemy_units=())))
    elif flow_id == (
            "expires-uncommitted"):
        _record(
            trace,
            lifecycle.observe(
                _next_snapshot(
                    snapshot, 20,
                    turn=(
                        snapshot.turn
                        + 1))))
    elif flow_id == (
            "action-rejected"):
        _record(
            trace,
            lifecycle.commit_matching_action(
                snapshot,
                assembly.action_for_step(0),
                accepted=False,
                reason="synthetic-rejection"))
    else:
        _record(
            trace,
            lifecycle.commit_matching_action(
                snapshot,
                assembly.action_for_step(0),
                accepted=True))
        if flow_id == (
                "first-step-neutralizes"):
            _record(
                trace,
                lifecycle.observe(
                    _next_snapshot(
                        snapshot, 21,
                        visible_enemy_units=())))
        elif flow_id == (
                "participant-removed"):
            participant_id = int(
                assembly.spec
                .participants[1]
                .actor_id.split(":")[1])
            _record(
                trace,
                lifecycle.observe(
                    _next_snapshot(
                        snapshot, 21,
                        units=tuple(
                            unit for unit
                            in snapshot.units
                            if unit.unit_id
                            != participant_id))))
        elif flow_id == (
                "next-step-capacity-blocked"):
            participant_id = int(
                assembly.spec
                .participants[1]
                .actor_id.split(":")[1])
            _record(
                trace,
                lifecycle.observe(
                    _next_snapshot(
                        snapshot, 21,
                        units=tuple(
                            replace(
                                unit,
                                moves_left=0)
                            if unit.unit_id
                            == participant_id
                            else unit
                            for unit in
                            snapshot.units))))
        elif flow_id == (
                "blocked-repaired"):
            participant_id = int(
                assembly.spec
                .participants[1]
                .actor_id.split(":")[1])
            blocked = _next_snapshot(
                snapshot, 21,
                legal_action_json=tuple(
                    value for value in
                    snapshot
                    .legal_action_json
                    if json.loads(
                        value).get(
                            "actor_id")
                    != participant_id))
            _record(
                trace,
                lifecycle.observe(
                    blocked))
            repaired = _next_snapshot(
                snapshot, 22)
            _record(
                trace,
                lifecycle.observe(
                    repaired))
            _record(
                trace,
                lifecycle.observe(
                    _next_snapshot(
                        repaired, 23,
                        visible_enemy_units=())))
        else:
            after_first = (
                _next_snapshot(
                    snapshot, 21))
            _record(
                trace,
                lifecycle.observe(
                    after_first))
            _record(
                trace,
                lifecycle
                .commit_matching_action(
                    after_first,
                    assembly
                    .action_for_step(1),
                    accepted=True))
            _record(
                trace,
                lifecycle.observe(
                    _next_snapshot(
                        after_first, 22,
                        visible_enemy_units=(
                            ()
                            if flow_id
                            == "follow-up-neutralizes"
                            else after_first
                            .visible_enemy_units))))

    record = lifecycle.store.get(
        assembly.spec.operation_id)
    result = {
        "active_claim_count":
            len(
                lifecycle.ledger
                .active_claims()),
        "decision_digest":
            structural_hash(trace),
        "final_state":
            record.progress
            .state.value,
        "flow_id": flow_id,
        "follow_up_action_claim_exact": (
            any(
                row[
                    "reservation_claim_count"]
                == 4
                and row[
                    "reservation_action_budget"]
                == 1
                and row["step_index"]
                == 1
                for row in trace)
            if flow_id in (
                "blocked-repaired",
                "follow-up-neutralizes",
                "follow-up-no-effect",
            )
            else True),
        "latency_ms": (
            time.perf_counter()
            - started) * 1000.0,
        "policy_authority": False,
        "shadow_only": True,
        "trace": trace,
    }
    return result


def run(corpus, iterations):
    source = next(
        row for row in
        corpus["scenarios"]
        if row["id"]
        == "two-attackers-one-target")
    first = [
        _run_flow(
            flow_id, source)
        for flow_id in FLOW_IDS
    ]
    latencies = [
        row["latency_ms"]
        for row in first
    ]
    digests = {
        row["flow_id"]: {
            row[
                "decision_digest"]
        }
        for row in first
    }
    for _ in range(
            iterations - 1):
        for flow_id in FLOW_IDS:
            row = _run_flow(
                flow_id, source)
            latencies.append(
                row["latency_ms"])
            digests[
                flow_id].add(
                    row[
                        "decision_digest"])
    by_id = {
        row["flow_id"]: row
        for row in first
    }
    gates = {
        "all_final_states_match":
            all(
                row["final_state"]
                == EXPECTED_FINAL_STATES[
                    row["flow_id"]]
                for row in first),
        "all_inactive_or_attributably_blocked":
            all(
                row[
                    "active_claim_count"]
                == 0
                for row in first),
        "blocked_step_repairs":
            any(
                trace[
                    "disposition"]
                == "repaired"
                for trace in
                by_id[
                    "blocked-repaired"
                ]["trace"]),
        "current_step_claims_are_complete":
            all(
                row[
                    "follow_up_action_claim_exact"]
                for row in first),
        "decisions_deterministic":
            all(
                len(values) == 1
                for values in
                digests.values()),
        "external_neutralization_completes":
            by_id[
                "external-neutralization-before-commit"
            ]["final_state"]
            == "completed",
        "follow_up_no_effect_is_not_success":
            by_id[
                "follow-up-no-effect"
            ]["final_state"]
            == "failed",
        "no_policy_authority":
            all(
                row["shadow_only"]
                and not row[
                    "policy_authority"]
                for row in first),
        "p95_compute_below_20_ms":
            _percentile(
                latencies, 0.95)
            < 20.0,
        "participant_loss_abandons":
            by_id[
                "participant-removed"
            ]["final_state"]
            == "abandoned",
        "rejected_action_fails_and_releases":
            by_id[
                "action-rejected"
            ]["final_state"]
            == "failed"
            and by_id[
                "action-rejected"
            ]["active_claim_count"]
            == 0,
    }
    report = {
        "authority":
            "synthetic-lifecycle-mechanism-only",
        "claim_status":
            "diagnostic-only-no-outcome-or-score-claim",
        "corpus_hash":
            structural_hash(corpus),
        "flow_count": len(
            first),
        "flows": first,
        "gates": gates,
        "iterations": int(
            iterations),
        "latency": _summary(
            latencies),
        "passed": all(
            gates.values()),
        "policy_authority": False,
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
        corpus, args.iterations)
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
