#!/usr/bin/env python3
"""Evaluate delayed relevance of persistence-only FDAS corridors."""

import argparse
import glob
import json
import math
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402


EVALUATOR_IDENTITY = "fdas-path-persistence-delayed-relevance/1.0"
COMPONENT_ID = "fdas-path-persistence-candidate-union"
DEFAULT_LOOKAHEAD_DECISIONS = 8


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _verify_report(report, expected_hash):
    if not isinstance(report, dict):
        raise ValueError("path persistence audit report is invalid")
    semantic = dict(report)
    report_hash = semantic.pop("report_hash", None)
    if (report_hash != structural_hash(semantic)
            or report_hash != expected_hash
            or report.get("passed") is not True):
        raise ValueError("path persistence audit report is not frozen passing")


def _route_rows(readouts):
    result = {}
    for readout in readouts:
        route_id = readout.get("route_id")
        if not isinstance(route_id, str) or not route_id:
            raise ValueError("path persistence readout lacks route identity")
        previous = result.get(route_id)
        order = (
            -float(readout["instantaneous_reachability"]),
            int(readout["baseline_rank"]),
            str(readout["operation_id"]),
        )
        if previous is None or order < previous[0]:
            result[route_id] = (order, readout)
    return dict((key, value[1]) for key, value in result.items())


def _select_control(readouts, treatment_route_id):
    routes = _route_rows(readouts)
    treatment = routes.get(treatment_route_id)
    if treatment is None:
        raise ValueError("persistence treatment route is absent")
    controls = tuple(
        value for route_id, value in routes.items()
        if route_id != treatment_route_id
        and value.get("probe_member") is False)
    if not controls:
        return None
    return min(controls, key=lambda value: (
        value.get("operation_type") != treatment.get("operation_type"),
        abs(float(value["instantaneous_reachability"])
            - float(treatment["instantaneous_reachability"])),
        abs(int(value["baseline_rank"])
            - int(treatment["baseline_rank"])),
        value["route_id"],
    ))


def _route_outcome(rows, start_index, route_id, lookahead_decisions):
    probe_reentry = False
    scalar_winner = False
    probe_delay = None
    scalar_delay = None
    expiry_delay = None
    end_index = min(len(rows), start_index + lookahead_decisions + 1)
    for index in range(start_index + 1, end_index):
        readouts = tuple(
            value for value in rows[index]["readouts"]
            if value["route_id"] == route_id)
        delay = index - start_index
        if not readouts:
            expiry_delay = delay
            break
        if not probe_reentry and any(
                value["probe_member"] is True for value in readouts):
            probe_reentry = True
            probe_delay = delay
        if not scalar_winner and any(
                value["baseline_rank"] == 1 for value in readouts):
            scalar_winner = True
            scalar_delay = delay
        if probe_reentry and scalar_winner:
            break
    horizon_censored = bool(
        expiry_delay is None
        and end_index == len(rows)
        and len(rows) - 1 - start_index < lookahead_decisions
        and not (probe_reentry and scalar_winner))
    return {
        "expiry_delay_decisions": expiry_delay,
        "horizon_censored": horizon_censored,
        "probe_delay_decisions": probe_delay,
        "probe_reentry_observed": probe_reentry or not horizon_censored,
        "probe_reentry": probe_reentry,
        "scalar_delay_decisions": scalar_delay,
        "scalar_winner_observed": scalar_winner or not horizon_censored,
        "scalar_winner": scalar_winner,
    }


def _exact_sign_test(positive, negative):
    discordant = int(positive) + int(negative)
    if discordant == 0:
        return 1.0
    tail = sum(
        math.comb(discordant, value)
        for value in range(0, min(positive, negative) + 1)) / (
            2.0 ** discordant)
    return min(1.0, 2.0 * tail)


def _paired_summary(pairs, metric):
    observed_name = metric + "_observed"
    eligible = tuple(
        value for value in pairs
        if value["treatment_outcome"][observed_name]
        and value["control_outcome"][observed_name])
    positive = sum(
        value["treatment_outcome"][metric]
        and not value["control_outcome"][metric]
        for value in eligible)
    negative = sum(
        not value["treatment_outcome"][metric]
        and value["control_outcome"][metric]
        for value in eligible)
    both = sum(
        value["treatment_outcome"][metric]
        and value["control_outcome"][metric]
        for value in eligible)
    neither = len(eligible) - positive - negative - both
    treatment_successes = sum(
        value["treatment_outcome"][metric] for value in eligible)
    control_successes = sum(
        value["control_outcome"][metric] for value in eligible)
    return {
        "both": both,
        "control_successes": control_successes,
        "eligible_pairs": len(eligible),
        "exact_two_sided_sign_p": _exact_sign_test(positive, negative),
        "negative_discordant": negative,
        "neither": neither,
        "paired_rate_delta": (
            (treatment_successes - control_successes) / float(len(eligible))
            if eligible else None),
        "positive_discordant": positive,
        "treatment_successes": treatment_successes,
    }


def evaluate(run_root, audit_report_path, expected_audit_report_hash,
             lookahead_decisions=DEFAULT_LOOKAHEAD_DECISIONS):
    if (isinstance(lookahead_decisions, bool)
            or not isinstance(lookahead_decisions, int)
            or lookahead_decisions < 1):
        raise ValueError("relevance lookahead must be a positive integer")
    audit_report = _read_json(audit_report_path)
    _verify_report(audit_report, expected_audit_report_hash)
    run_root = os.path.abspath(run_root)
    expected_seeds = tuple(sorted(
        value["seed"] for value in audit_report["games"]))
    game_dirs = tuple(sorted(glob.glob(os.path.join(
        run_root, "games", "main", "e_full_loop", "*"))))
    games = []
    all_pairs = []
    errors = []
    for game_dir in game_dirs:
        manifest = _read_json(os.path.join(game_dir, "manifest.json"))
        event_path = os.path.join(game_dir, "events.jsonl")
        validation = validate_file(event_path)
        rows = []
        with open(event_path, encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                payload = event.get("payload", {})
                if (event.get("type") != "atomspace_shadow_decision"
                        or payload.get("component_id") != COMPONENT_ID):
                    continue
                details = payload["details"]
                readouts = details["readouts"]
                additions = details["persistence_added_operation_ids"]
                by_operation = dict(
                    (value["operation_id"], value) for value in readouts)
                treatment_route = (
                    by_operation[additions[0]]["route_id"]
                    if additions else None)
                rows.append({
                    "event_id": event["event_id"],
                    "readouts": readouts,
                    "treatment_route_id": treatment_route,
                    "turn": event["turn"],
                })
        seen_treatment_routes = set()
        game_pairs = []
        unmatched = []
        for index, row in enumerate(rows):
            treatment_route = row["treatment_route_id"]
            if (treatment_route is None
                    or treatment_route in seen_treatment_routes):
                continue
            seen_treatment_routes.add(treatment_route)
            control = _select_control(row["readouts"], treatment_route)
            if control is None:
                unmatched.append({
                    "event_id": row["event_id"],
                    "reason": "no-non-probe-control-route",
                    "treatment_route_id": treatment_route,
                    "turn": row["turn"],
                })
                continue
            treatment = _route_rows(row["readouts"])[treatment_route]
            pair = {
                "control_instantaneous_reachability": (
                    control["instantaneous_reachability"]),
                "control_operation_type": control["operation_type"],
                "control_outcome": _route_outcome(
                    rows, index, control["route_id"], lookahead_decisions),
                "control_route_id": control["route_id"],
                "event_id": row["event_id"],
                "same_operation_type": (
                    control["operation_type"]
                    == treatment["operation_type"]),
                "seed": manifest["seed"],
                "treatment_instantaneous_reachability": (
                    treatment["instantaneous_reachability"]),
                "treatment_operation_type": treatment["operation_type"],
                "treatment_outcome": _route_outcome(
                    rows, index, treatment_route, lookahead_decisions),
                "treatment_route_id": treatment_route,
                "turn": row["turn"],
            }
            game_pairs.append(pair)
            all_pairs.append(pair)
        game_errors = []
        if not validation.valid or validation.warnings:
            game_errors.append("event-ledger-invalid-or-warning")
        errors.extend(
            "seed-{}:{}".format(manifest["seed"], value)
            for value in game_errors)
        games.append({
            "errors": game_errors,
            "matched_pairs": len(game_pairs),
            "seed": manifest["seed"],
            "treatment_routes": len(seen_treatment_routes),
            "unmatched_treatments": unmatched,
        })
    probe_summary = _paired_summary(all_pairs, "probe_reentry")
    scalar_summary = _paired_summary(all_pairs, "scalar_winner")
    matched = len(all_pairs)
    treatment_routes = sum(value["treatment_routes"] for value in games)
    semantic = {
        "audit_report_hash": expected_audit_report_hash,
        "claim_scope": (
            "exploratory delayed relevance proxy for first unique "
            "persistence-only routes versus deterministic within-decision "
            "non-probe controls; no causal candidate-value, gameplay, score, "
            "or win-rate claim"),
        "evaluator_identity": EVALUATOR_IDENTITY,
        "expected_seeds": list(expected_seeds),
        "games": games,
        "lookahead_decisions": lookahead_decisions,
        "matched_control_coverage": (
            matched / float(treatment_routes) if treatment_routes else 0.0),
        "matched_pairs": matched,
        "mechanically_valid": (
            not errors
            and tuple(sorted(value["seed"] for value in games))
            == expected_seeds),
        "probe_reentry": probe_summary,
        "scalar_winner": scalar_summary,
        "treatment_routes": treatment_routes,
        "unmatched_treatments": treatment_routes - matched,
    }
    semantic["incremental_relevance_observed"] = bool(
        probe_summary["paired_rate_delta"] is not None
        and probe_summary["paired_rate_delta"] > 0.0
        and scalar_summary["paired_rate_delta"] is not None
        and scalar_summary["paired_rate_delta"] >= 0.0)
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--audit-report", required=True)
    parser.add_argument("--expected-audit-report-hash", required=True)
    parser.add_argument("--lookahead-decisions", type=int, default=8)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = evaluate(
        args.run_root, args.audit_report, args.expected_audit_report_hash,
        args.lookahead_decisions)
    payload = canonical_json_bytes(report) + b"\n"
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "wb") as stream:
            stream.write(payload)
    else:
        sys.stdout.buffer.write(payload)
    return 0 if report["mechanically_valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
