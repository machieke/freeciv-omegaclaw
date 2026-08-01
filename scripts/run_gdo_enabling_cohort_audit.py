#!/usr/bin/env python3
"""Audit the fresh shadow-only GDO-7 production/research engine cohort."""

import argparse
from collections import Counter, defaultdict
import glob
import hashlib
import json
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
for path in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.config import load as load_harness_config  # noqa: E402
from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402


COHORT = "grounded_enabling_operations_diagnostic_v1"
MECHANISMS = (
    "gdo7a-production-enabling",
    "gdo7b-research-enabling",
)
LIFECYCLE_TYPES = frozenset((
    "operation_proposed",
    "operation_reserved",
    "operation_activated",
    "operation_step_selected",
    "operation_step_revalidated",
    "operation_step_committed",
    "operation_blocked",
    "operation_repaired",
    "operation_completed",
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
))
TERMINAL_TYPES = frozenset((
    "operation_completed",
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
))


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _fraction(numerator, denominator):
    return (
        None if not denominator
        else float(numerator) / float(denominator))


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(
            json.loads(line)
            for line in stream
            if line.strip())


def _event_paths(root, cohort, arm):
    return sorted(glob.glob(os.path.join(
        root, "games", "impact_pair",
        cohort, arm, "e_full_loop",
        "*", "events.jsonl")))


def _metric(events, name):
    values = [
        row.get("payload", {}).get("value")
        for row in events
        if (
            row.get("type") == "metric_sample"
            and row.get("payload", {}).get("name") == name)
    ]
    return values[-1] if values else None


def analyze_trace(events):
    """Return source-fresh mechanism observations for one engine trace."""
    proposals = {}
    lifecycle = defaultdict(Counter)
    terminal = {}
    domain_estimates = Counter()
    domain_abstentions = Counter()
    resource = defaultdict(Counter)
    reason_codes = defaultdict(Counter)
    duplicate_proposals = []
    malformed_proposals = []
    for event in events:
        event_type = str(event.get("type", ""))
        payload = event.get("payload", {})
        estimator = payload.get("estimator_id")
        if event_type in (
                "domain_estimate_emitted",
                "domain_estimate_abstained") and estimator in (
                    "grounded_city_production_queue",
                    "grounded_research_selection"):
            target = (
                domain_estimates
                if event_type == "domain_estimate_emitted"
                else domain_abstentions)
            target[str(estimator)] += 1
        operation_id = payload.get("operation_id")
        mechanism = payload.get("mechanism")
        if (
                event_type == "operation_proposed"
                and mechanism in MECHANISMS
                and isinstance(operation_id, str)):
            if operation_id in proposals:
                duplicate_proposals.append(operation_id)
            proposals[operation_id] = dict(payload)
            if (
                    payload.get("shadow_only") is not True
                    or payload.get("policy_authority") is not False
                    or not isinstance(
                        payload.get("requirement_set"), dict)
                    or not payload.get("claims")
                    or not payload.get(
                        "domain_estimate_request_id")):
                malformed_proposals.append(operation_id)
        if (
                event_type in LIFECYCLE_TYPES
                and operation_id in proposals):
            mechanism = proposals[operation_id]["mechanism"]
            lifecycle[mechanism][event_type] += 1
            reason = payload.get("reason_code")
            if isinstance(reason, str) and reason:
                reason_codes[mechanism][reason] += 1
            if event_type in TERMINAL_TYPES:
                terminal[operation_id] = event_type
        if (
                event_type.startswith("resource_claim_")
                and operation_id in proposals):
            mechanism = proposals[operation_id]["mechanism"]
            resource[mechanism][event_type] += 1
    mechanisms = {}
    for mechanism in MECHANISMS:
        operation_ids = {
            operation_id
            for operation_id, payload in proposals.items()
            if payload["mechanism"] == mechanism
        }
        committed_ids = {
            event.get("payload", {}).get("operation_id")
            for event in events
            if event.get("type") == "operation_step_committed"
        } & operation_ids
        completed_ids = {
            operation_id for operation_id in operation_ids
            if terminal.get(operation_id)
            == "operation_completed"
        }
        terminal_ids = set(terminal) & operation_ids
        mechanisms[mechanism] = {
            "completion_rate_per_commit": _fraction(
                len(completed_ids), len(committed_ids)),
            "committed_unique": len(committed_ids),
            "completed_unique": len(completed_ids),
            "lifecycle_events": dict(sorted(
                lifecycle[mechanism].items())),
            "nonterminal_at_trace_end": len(
                operation_ids - terminal_ids),
            "proposed_unique": len(operation_ids),
            "reason_codes": dict(sorted(
                reason_codes[mechanism].items())),
            "resource_events": dict(sorted(
                resource[mechanism].items())),
            "terminal_unique": len(terminal_ids),
        }
    return {
        "domain_abstentions": dict(sorted(
            domain_abstentions.items())),
        "domain_estimates": dict(sorted(
            domain_estimates.items())),
        "duplicate_proposals": sorted(duplicate_proposals),
        "malformed_proposals": sorted(malformed_proposals),
        "mechanisms": mechanisms,
        "metrics": {
            "engine_rejected_action_rate": _metric(
                events, "engine_rejected_action_rate"),
            "meaningful_actions_per_turn": _metric(
                events, "meaningful_actions_per_turn"),
            "score_lead_turn_n": _metric(
                events, "score_lead_turn_n"),
            "score_turn_n": _metric(
                events, "score_turn_n"),
            "technology_gain": _metric(
                events, "technologies_acquired"),
        },
    }


def _combine(rows):
    result = {
        "domain_abstentions": Counter(),
        "domain_estimates": Counter(),
        "duplicate_proposals": [],
        "malformed_proposals": [],
        "mechanisms": {},
    }
    for row in rows:
        result["domain_abstentions"].update(
            row["domain_abstentions"])
        result["domain_estimates"].update(
            row["domain_estimates"])
        result["duplicate_proposals"].extend(
            row["duplicate_proposals"])
        result["malformed_proposals"].extend(
            row["malformed_proposals"])
    for mechanism in MECHANISMS:
        lifecycle = Counter()
        resource = Counter()
        reasons = Counter()
        proposed = committed = completed = terminal = nonterminal = 0
        for row in rows:
            value = row["mechanisms"][mechanism]
            lifecycle.update(value["lifecycle_events"])
            resource.update(value["resource_events"])
            reasons.update(value["reason_codes"])
            proposed += value["proposed_unique"]
            committed += value["committed_unique"]
            completed += value["completed_unique"]
            terminal += value["terminal_unique"]
            nonterminal += value["nonterminal_at_trace_end"]
        result["mechanisms"][mechanism] = {
            "attribution_rate_per_proposal": _fraction(
                committed, proposed),
            "completion_rate_per_commit": _fraction(
                completed, committed),
            "committed_unique": committed,
            "completed_unique": completed,
            "lifecycle_events": dict(sorted(lifecycle.items())),
            "nonterminal_at_trace_end": nonterminal,
            "proposed_unique": proposed,
            "reason_codes": dict(sorted(reasons.items())),
            "resource_events": dict(sorted(resource.items())),
            "terminal_coverage": _fraction(terminal, proposed),
            "terminal_unique": terminal,
        }
    result["domain_abstentions"] = dict(sorted(
        result["domain_abstentions"].items()))
    result["domain_estimates"] = dict(sorted(
        result["domain_estimates"].items()))
    result["duplicate_proposals"] = sorted(
        result["duplicate_proposals"])
    result["malformed_proposals"] = sorted(
        result["malformed_proposals"])
    return result


def run(root, profile, cohort=COHORT):
    aggregate_path = os.path.join(
        root, "impact-aggregate.json")
    aggregate = _load(aggregate_path)
    if aggregate.get("design", {}).get("cohort") != cohort:
        raise ValueError("aggregate cohort does not match requested audit")
    config = load_harness_config(profile)
    design = config["paired_impact"]["cohorts"][cohort]
    expected = int(aggregate.get("complete_pairs", 0))
    paths = {
        arm: _event_paths(root, cohort, arm)
        for arm in ("baseline", "treatment")
    }
    if any(len(value) != expected for value in paths.values()):
        raise ValueError(
            "cohort trace counts do not match complete pairs")
    arms = {}
    trace_rows = []
    validation = Counter()
    paired_metrics = defaultdict(dict)
    for arm in ("baseline", "treatment"):
        analyses = []
        for path in paths[arm]:
            report = validate_file(path)
            validation["event_count"] += report.event_count
            validation["error_count"] += len(report.errors)
            validation["warning_count"] += len(report.warnings)
            events = _events(path)
            analysis = analyze_trace(events)
            analyses.append(analysis)
            manifest = _load(os.path.join(
                os.path.dirname(path), "manifest.json"))
            seed = int(manifest["seed"])
            paired_metrics[seed][arm] = analysis["metrics"]
            trace_rows.append({
                "arm": arm,
                "path": os.path.relpath(path, root),
                "seed": seed,
                "sha256": _sha256_file(path),
            })
        arms[arm] = _combine(analyses)
    parity = {}
    for name in (
            "score_turn_n", "score_lead_turn_n",
            "meaningful_actions_per_turn",
            "technology_gain"):
        mismatches = [
            seed for seed, values in sorted(
                paired_metrics.items())
            if (
                set(values) == {"baseline", "treatment"}
                and values["baseline"].get(name)
                != values["treatment"].get(name))
        ]
        parity[name] = {
            "mismatch_count": len(mismatches),
            "mismatch_seeds": mismatches,
            "passed": not mismatches,
        }
    baseline_proposals = sum(
        value["proposed_unique"]
        for value in arms["baseline"][
            "mechanisms"].values())
    treatment = arms["treatment"]
    treatment_proposals = sum(
        value["proposed_unique"]
        for value in treatment[
            "mechanisms"].values())
    treatment_commits = sum(
        value["committed_unique"]
        for value in treatment[
            "mechanisms"].values())
    treatment_completions = sum(
        value["completed_unique"]
        for value in treatment[
            "mechanisms"].values())
    gates = {
        "all_predeclared_pairs_completed": (
            expected == design["planned_pairs"]),
        "behavioral_score_and_action_parity": all(
            parity[name]["passed"]
            for name in (
                "score_turn_n",
                "score_lead_turn_n",
                "meaningful_actions_per_turn")),
        "engine_acceptance_attributed": treatment_commits > 0,
        "event_schema_valid": validation["error_count"] == 0,
        "fresh_authoritative_completion_observed": (
            treatment_completions > 0),
        "no_duplicate_operation_identity": (
            not treatment["duplicate_proposals"]),
        "no_malformed_operation_contract": (
            not treatment["malformed_proposals"]),
        "production_and_research_both_exercised": all(
            treatment["mechanisms"][mechanism][
                "proposed_unique"] > 0
            for mechanism in MECHANISMS),
        "shadow_flags_have_no_baseline_write_through": (
            baseline_proposals == 0),
        "treatment_shadow_mechanism_active": (
            treatment_proposals > 0),
    }
    return {
        "schema_version": "1.0",
        "cohort": cohort,
        "claim_eligible": False,
        "complete_pairs": expected,
        "planned_pairs": design["planned_pairs"],
        "arms": arms,
        "paired_behavior_parity": parity,
        "gates": gates,
        "overall_passed": all(gates.values()),
        "validation": dict(sorted(validation.items())),
        "trace_sources": sorted(
            trace_rows,
            key=lambda row: (
                row["seed"], row["arm"])),
        "aggregate_source": {
            "path": os.path.relpath(
                aggregate_path, root),
            "sha256": _sha256_file(
                aggregate_path),
        },
        "design": design.get(
            "grounded_enabling_design"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cohort_root")
    parser.add_argument(
        "--profile",
        default=os.path.join(
            REPO, "profile",
            "freeciv_harness.yaml"))
    parser.add_argument(
        "--cohort", default=COHORT)
    parser.add_argument("--out")
    args = parser.parse_args()
    result = run(
        os.path.abspath(args.cohort_root),
        os.path.abspath(args.profile),
        cohort=args.cohort)
    encoded = canonical_json_bytes(result) + b"\n"
    if args.out:
        path = os.path.abspath(args.out)
        os.makedirs(
            os.path.dirname(path),
            exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(encoded)
    sys.stdout.buffer.write(encoded)
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
