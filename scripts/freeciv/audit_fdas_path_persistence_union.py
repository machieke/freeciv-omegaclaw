#!/usr/bin/env python3
"""Audit fresh engine-backed FDAS path-persistence candidate unions."""

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

from audit_fdas_probe_candidate_union import (  # noqa: E402
    _completed_endpoint,
    _read_json,
    _wilson,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    FdasCandidateChoiceSetStore,
    PATH_PERSISTENCE_CANDIDATE_UNION_IDENTITY,
)


AUDIT_IDENTITY = "fdas-path-persistence-candidate-union-audit/1.0"
COMPONENT_ID = "fdas-path-persistence-candidate-union"
PROBE_COMPONENT_ID = "fdas-probe-candidate-union"
CONFIG_SOURCE = (
    "profile/dependent_atomspace_defense_choice_surface_shadow.yaml")
MANIFEST_SOURCE = (
    "profile/fdas_manifest_defense_path_persistence_union_shadow.json")
PERSISTENCE_CONFIG = {
    "diversity_floor": 0.0,
    "dwell_bonus": 0.05,
    "minimum_dwell_steps": 2,
    "route_momentum": 0.15,
    "smoothing": 0.35,
    "switch_margin": 0.01,
}
MAXIMUM_REACHABILITY_REGRET = 0.05
DEFAULT_THRESHOLDS = {
    "expired_routes": 1,
    "game_addition_rate_wilson_lower": 0.10,
    "games_with_temporal_additions": 4,
    "persistence_readouts": 500,
    "regret_rejections": 1,
    "temporal_additions": 8,
    "temporal_retentions": 8,
    "union_events": 300,
}


def _hash(value):
    return bool(
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value))


def _finite(value):
    return bool(
        not isinstance(value, bool) and isinstance(value, (int, float))
        and math.isfinite(float(value)))


def _validate_signal_ledger(ledger):
    errors = []
    if not isinstance(ledger, dict):
        return ("persistence-signal-ledger-invalid",)
    semantic = dict(ledger)
    ledger_hash = semantic.pop("ledger_hash", None)
    if ledger_hash != structural_hash(semantic):
        errors.append("persistence-signal-ledger-hash-differs")
    uses = ledger.get("uses")
    if not isinstance(uses, list):
        return tuple(errors + ["persistence-signal-uses-invalid"])
    by_signal = dict((value.get("signal_name"), value) for value in uses)
    protected = {
        "corrected_bridge_overlap",
        "corridor_dwell_state",
        "raw_route_momentum",
        "smoothed_corridor_reachability",
    }
    if (not protected.issubset(by_signal)
            or any(by_signal[value].get("used_in_final_score") is not False
                   for value in protected)):
        errors.append("persistence-signals-gained-score-authority")
    return tuple(errors)


def _validate_path_persistence_union(details, payload, probe_parent=None):
    errors = []
    if not isinstance(details, dict):
        return ("persistence-details-not-object",), {}
    semantic = dict(details)
    result_hash = semantic.pop("result_hash", None)
    if result_hash != structural_hash(semantic):
        errors.append("persistence-union-result-hash-differs")
    if details.get("identity") != PATH_PERSISTENCE_CANDIDATE_UNION_IDENTITY:
        errors.append("persistence-union-identity-differs")
    if (details.get("snapshot_id") != payload.get("snapshot_id")
            or details.get("revision_id") != payload.get("revision_id")):
        errors.append("persistence-revision-binding-differs")
    if any(details.get(name) is not False for name in (
            "action_selection_changed", "capacity_solver_enabled",
            "flow_advection_enabled", "path_persistence_authority",
            "policy_authority", "readout_authority",
            "source_sink_flow_enabled", "truth_mutated")):
        errors.append("persistence-shadow-authority-differs")
    if details.get("scalar_final_score_authority") is not True:
        errors.append("persistence-scalar-authority-differs")
    if (details.get("config") != PERSISTENCE_CONFIG
            or details.get("maximum_reachability_regret")
            != MAXIMUM_REACHABILITY_REGRET):
        errors.append("frozen-persistence-configuration-differs")
    for name in ("state_before_hash", "state_after_hash",
                 "probe_union_result_hash"):
        if not _hash(details.get(name)):
            errors.append("{}-invalid".format(name.replace("_", "-")))
    errors.extend(_validate_signal_ledger(details.get("signal_ledger")))

    readouts = details.get("readouts")
    members = details.get("members")
    base_ids = details.get("base_probe_operation_ids")
    additions = details.get("persistence_added_operation_ids")
    expired = details.get("expired_route_ids")
    if (not isinstance(readouts, list) or not readouts
            or not isinstance(members, list) or not members
            or not isinstance(base_ids, list) or not base_ids
            or not isinstance(additions, list)
            or not isinstance(expired, list)):
        return tuple(errors + ["persistence-union-collections-invalid"]), {}
    readout_ids = tuple(value.get("operation_id") for value in readouts)
    member_ids = tuple(value.get("operation_id") for value in members)
    base_ids = tuple(base_ids)
    additions = tuple(additions)
    expired = tuple(expired)
    if any(len(values) != len(set(values)) for values in (
            readout_ids, member_ids, base_ids, additions, expired)):
        errors.append("persistence-union-ids-not-unique")
    selected = details.get("persistence_selected_operation_id")
    selected_route = details.get("persistence_selected_route_id")
    expected_additions = (
        () if selected is None or selected in base_ids else (selected,))
    if (set(base_ids) - set(member_ids)
            or set(member_ids) - set(readout_ids)
            or set(additions) - set(member_ids)
            or set(additions).intersection(base_ids)
            or additions != expected_additions
            or len(additions) > 1
            or len(member_ids) > len(base_ids) + 1
            or ((selected is None) != (selected_route is None))):
        errors.append("persistence-union-membership-bound-differs")
    ranks = tuple(value.get("baseline_rank") for value in readouts)
    if ranks != tuple(range(1, len(readouts) + 1)):
        errors.append("persistence-scalar-ranking-differs")
    readout_by_id = dict(zip(readout_ids, readouts))
    member_by_id = dict(zip(member_ids, members))
    if (details.get("baseline_selected_operation_id") != base_ids[0]
            or base_ids[0] != readout_ids[0]):
        errors.append("persistence-scalar-winner-protection-differs")

    for readout in readouts:
        operation_id = readout.get("operation_id")
        numeric = tuple(readout.get(name) for name in (
            "instantaneous_reachability", "smoothed_reachability",
            "route_momentum", "dwell_bonus", "persistence_score"))
        if (any(not _finite(value) for value in numeric)
                or not 0.0 <= float(numeric[0]) <= 1.0
                or not 0.0 <= float(numeric[1]) <= 1.0
                or float(numeric[3]) < 0.0
                or abs(float(numeric[4]) - sum(map(float, numeric[1:4])))
                > 1e-12):
            errors.append("persistence-readout-numeric-domain-differs")
        if (readout.get("probe_member") != (operation_id in base_ids)
                or readout.get("persistence_selected")
                != (operation_id == selected)
                or not isinstance(readout.get("route_id"), str)
                or not readout.get("route_id", "").startswith(
                    "fdas-path-corridor:")):
            errors.append("persistence-readout-membership-differs")
    selected_readout = readout_by_id.get(selected)
    if selected is not None and (
            selected not in member_by_id or selected_readout is None
            or selected_readout.get("route_id") != selected_route
            or "path-persistence-recall" not in
            member_by_id[selected].get("reasons", ())):
        errors.append("persistence-selected-member-differs")
    if any(
            "path-persistence-recall" in value.get("reasons", ())
            and value.get("operation_id") != selected
            for value in members):
        errors.append("persistence-member-reason-differs")

    fallback = details.get("fallback_required")
    regret_rejected = details.get("regret_rejected")
    retention = tuple(details.get(name) for name in (
        "retained_by_smoothing", "retained_by_dwell",
        "retained_by_hysteresis"))
    if (not isinstance(fallback, bool)
            or not isinstance(regret_rejected, bool)
            or any(not isinstance(value, bool) for value in retention)):
        errors.append("persistence-control-state-invalid")
    elif (sum(retention) > 1
            or fallback != (details.get("fallback_reason") is not None)
            or (fallback and (selected is not None or additions))):
        errors.append("persistence-fallback-or-retention-state-differs")
    cause = details.get("switch_cause")
    cause_flags = {
        "retained-by-smoothing": retention[0],
        "retained-by-dwell": retention[1],
        "retained-by-hysteresis": retention[2],
        "reachability-regret-rejected": regret_rejected,
    }
    if any(bool(value) != (cause == name)
           for name, value in cause_flags.items()):
        errors.append("persistence-switch-cause-attribution-differs")
    allowed_causes = {
        "corridor-retained", "corridor-switched", "initial-selection",
        "no-current-corridor", "no-positive-reachability",
        "previous-corridor-expired", "probe-union-fallback",
        "reachability-regret-rejected", "retained-by-dwell",
        "retained-by-hysteresis", "retained-by-smoothing",
        "turn-regression-reset",
    }
    if cause not in allowed_causes:
        errors.append("persistence-switch-cause-invalid")
    regret = details.get("reachability_regret")
    if not _finite(regret) or not 0.0 <= float(regret) <= 1.0:
        errors.append("persistence-reachability-regret-invalid")
    elif regret_rejected:
        if float(regret) <= MAXIMUM_REACHABILITY_REGRET:
            errors.append("persistence-regret-rejection-bound-differs")
    elif float(regret) > MAXIMUM_REACHABILITY_REGRET + 1e-12:
        errors.append("persistence-regret-bound-differs")
    if selected_readout is not None and retention and any(retention):
        maximum = max(float(value["instantaneous_reachability"])
                      for value in readouts)
        if (maximum - float(selected_readout["instantaneous_reachability"])
                <= 1e-12):
            errors.append("persistence-retention-lacks-current-regret")

    if probe_parent is None:
        errors.append("persistence-probe-parent-missing")
    else:
        parent_members = tuple(
            value.get("operation_id")
            for value in probe_parent.get("members", ()))
        if (details.get("probe_union_result_hash")
                != probe_parent.get("result_hash")
                or base_ids != parent_members
                or details.get("baseline_selected_operation_id")
                != probe_parent.get("baseline_selected_operation_id")):
            errors.append("persistence-probe-parent-binding-differs")
        parent_reason_by_id = dict(
            (value.get("operation_id"), set(value.get("reasons", ())))
            for value in probe_parent.get("members", ()))
        for operation_id, member in member_by_id.items():
            expected = set(parent_reason_by_id.get(operation_id, ()))
            if operation_id == selected:
                expected.add("path-persistence-recall")
            if set(member.get("reasons", ())) != expected:
                errors.append("persistence-probe-member-reasons-differ")

    temporal_retention = any(retention) if all(
        isinstance(value, bool) for value in retention) else False
    return tuple(errors), {
        "additions": len(additions),
        "expired_routes": len(expired),
        "fallbacks": int(fallback is True),
        "members": len(members),
        "readouts": len(readouts),
        "regret_rejections": int(regret_rejected is True),
        "retained_by_dwell": int(retention[1] is True),
        "retained_by_hysteresis": int(retention[2] is True),
        "retained_by_smoothing": int(retention[0] is True),
        "selection_changes": int(
            details.get("action_selection_changed") is True),
        "temporal_additions": int(bool(additions) and temporal_retention),
        "temporal_retentions": int(temporal_retention),
    }


def audit(run_root, expected_seeds, expected_source_commit, thresholds=None,
          cohort_id="fdas_path_persistence_union_confirmation_v1"):
    run_root = os.path.abspath(run_root)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (not expected_seeds
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError("path persistence audit requires unique seeds")
    if not isinstance(expected_source_commit, str) or len(
            expected_source_commit) != 40:
        raise ValueError("path persistence audit requires full source commit")
    if not isinstance(cohort_id, str) or not cohort_id:
        raise ValueError("path persistence audit requires cohort identity")
    thresholds = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    if set(thresholds) != set(DEFAULT_THRESHOLDS):
        raise ValueError("path persistence audit thresholds differ")
    for name, value in thresholds.items():
        if name == "game_addition_rate_wilson_lower":
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not 0.0 <= float(value) <= 1.0):
                raise ValueError("path persistence rate threshold is invalid")
        elif (isinstance(value, bool) or not isinstance(value, int)
                or value < 1):
            raise ValueError("path persistence count threshold is invalid")

    game_dirs = tuple(sorted(glob.glob(os.path.join(
        run_root, "games", "main", "e_full_loop", "*"))))
    total_keys = (
        "additions", "expired_routes", "fallbacks", "members", "readouts",
        "regret_rejections", "retained_by_dwell",
        "retained_by_hysteresis", "retained_by_smoothing",
        "selection_changes", "temporal_additions", "temporal_retentions",
        "union_events",
    )
    totals = dict((key, 0) for key in total_keys)
    games = []
    all_errors = []
    for game_dir in game_dirs:
        manifest = _read_json(os.path.join(game_dir, "manifest.json"))
        status = _read_json(os.path.join(game_dir, "status.json"))
        event_path = os.path.join(game_dir, "events.jsonl")
        choice_path = os.path.join(game_dir, "fdas-candidate-choice-sets.json")
        choice_raw = _read_json(choice_path)
        choice_store = FdasCandidateChoiceSetStore.load(
            choice_path, choice_raw["persistence_identity"])
        validation = validate_file(event_path)
        with open(event_path, encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream]
        event_by_id = dict((value.get("event_id"), value) for value in events)
        game_totals = dict((key, 0) for key in total_keys)
        union_errors = []
        previous_state_after = None
        for event in events:
            payload = event.get("payload", {})
            if (event.get("type") != "atomspace_shadow_decision"
                    or payload.get("component_id") != COMPONENT_ID):
                continue
            game_totals["union_events"] += 1
            parents = tuple(
                event_by_id.get(value) for value in event.get("caused_by", ()))
            probes = tuple(
                value.get("payload", {}).get("details")
                for value in parents if value is not None
                and value.get("payload", {}).get("component_id")
                == PROBE_COMPONENT_ID)
            parent = probes[0] if len(probes) == 1 else None
            details = payload.get("details")
            errors, measures = _validate_path_persistence_union(
                details, payload, parent)
            if (previous_state_after is not None and isinstance(details, dict)
                    and details.get("state_before_hash")
                    != previous_state_after):
                errors = tuple(errors) + (
                    "persistence-controller-state-continuity-differs",)
            if isinstance(details, dict):
                previous_state_after = details.get("state_after_hash")
            union_errors.extend(
                "{}:{}".format(event.get("event_id"), value)
                for value in errors)
            for key, value in measures.items():
                game_totals[key] += int(value)
        for key, value in game_totals.items():
            totals[key] += value
        declaration = manifest.get("dependent_atomspace", {})
        source = manifest.get("source", {})
        status_pairs = {
            "additions": "fdas_path_persistence_union_additions",
            "expired_routes": "fdas_path_persistence_union_expired_routes",
            "fallbacks": "fdas_path_persistence_union_fallbacks",
            "members": "fdas_path_persistence_union_members",
            "readouts": "fdas_path_persistence_union_readouts",
            "regret_rejections": (
                "fdas_path_persistence_union_regret_rejections"),
            "retained_by_dwell": (
                "fdas_path_persistence_union_retained_by_dwell"),
            "retained_by_hysteresis": (
                "fdas_path_persistence_union_retained_by_hysteresis"),
            "retained_by_smoothing": (
                "fdas_path_persistence_union_retained_by_smoothing"),
            "selection_changes": (
                "fdas_path_persistence_union_selection_changes"),
            "union_events": "fdas_path_persistence_union_evaluations",
        }
        game_gates = {
            "candidate_choice_count_matches_union_events": (
                len(choice_store.choice_sets())
                == game_totals["union_events"]),
            "completed_preregistered_endpoint_without_infrastructure_failure": (
                _completed_endpoint(status)),
            "event_ledger_valid_without_warnings": (
                validation.valid and not validation.warnings),
            "manifest_profile_is_frozen": (
                declaration.get("config_source") == CONFIG_SOURCE
                and declaration.get("manifest_source") == MANIFEST_SOURCE),
            "persistence_counters_match_status": all(
                status.get(status_name) == game_totals[measure]
                for measure, status_name in status_pairs.items()),
            "persistence_events_are_semantically_valid": not union_errors,
            "source_is_clean_and_frozen": (
                source.get("dirty") is False
                and source.get("commit") == expected_source_commit),
            "zero_persistence_fallbacks": game_totals["fallbacks"] == 0,
            "zero_rejected_actions": status.get("rejected_actions") == 0,
        }
        if not all(game_gates.values()):
            all_errors.extend(
                "seed-{}:{}".format(manifest.get("seed"), name)
                for name, passed in game_gates.items() if not passed)
        all_errors.extend(union_errors)
        games.append({
            "attempt_id": manifest.get("attempt_id"),
            "game_gates": game_gates,
            "game_id": manifest.get("game_id"),
            "measures": game_totals,
            "runtime_ms": status.get("engine_backend_latency_ms"),
            "seed": manifest.get("seed"),
            "source": source,
            "union_errors": union_errors,
        })

    games_with_temporal_additions = sum(
        value["measures"]["temporal_additions"] > 0 for value in games)
    rate_lower, rate_upper = _wilson(
        games_with_temporal_additions, len(games))
    mechanical_gates = {
        "all_game_gates_pass": bool(games) and not all_errors,
        "exact_preregistered_seeds_completed": (
            tuple(sorted(value["seed"] for value in games))
            == tuple(sorted(expected_seeds))),
        "source_identity_is_identical": bool(games) and len({
            structural_hash(value["source"]) for value in games}) == 1,
    }
    progression_gates = {
        "expiry_mechanism_observed": (
            totals["expired_routes"] >= thresholds["expired_routes"]),
        "game_level_temporal_recurrence": (
            games_with_temporal_additions
            >= thresholds["games_with_temporal_additions"]),
        "game_level_temporal_recurrence_interval": (
            rate_lower
            >= thresholds["game_addition_rate_wilson_lower"]),
        "persistence_readout_yield": (
            totals["readouts"] >= thresholds["persistence_readouts"]),
        "regret_gate_observed": (
            totals["regret_rejections"] >= thresholds["regret_rejections"]),
        "temporal_addition_yield": (
            totals["temporal_additions"]
            >= thresholds["temporal_additions"]),
        "temporal_retention_yield": (
            totals["temporal_retentions"]
            >= thresholds["temporal_retentions"]),
        "union_event_yield": (
            totals["union_events"] >= thresholds["union_events"]),
    }
    semantic = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "bounded temporal corridor persistence recurrently adds protected "
            "candidate membership beyond corrected probes on fresh engine "
            "games; no ranking, action-selection, gameplay, score, or "
            "win-rate claim"),
        "cohort_id": cohort_id,
        "completion_semantics": "fixed-horizon-or-genuine-absorbing-terminal",
        "expected_source_commit": expected_source_commit,
        "games": games,
        "games_with_temporal_additions": games_with_temporal_additions,
        "mechanical_gates": mechanical_gates,
        "mechanically_accepted": all(mechanical_gates.values()),
        "progression_gate_passed": all(progression_gates.values()),
        "progression_gates": progression_gates,
        "thresholds": thresholds,
        "totals": totals,
        "wilson_game_temporal_addition_rate": {
            "interval_lower": rate_lower,
            "interval_upper": rate_upper,
            "observed_rate": (
                games_with_temporal_additions / float(len(games))
                if games else 0.0),
        },
    }
    semantic["passed"] = (
        semantic["mechanically_accepted"]
        and semantic["progression_gate_passed"])
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--output")
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument(
        "--cohort-id", default=(
            "fdas_path_persistence_union_confirmation_v1"))
    parser.add_argument("--minimum-expired-routes", type=int, default=1)
    parser.add_argument(
        "--minimum-game-addition-rate-wilson-lower", type=float, default=0.10)
    parser.add_argument(
        "--minimum-games-with-temporal-additions", type=int, default=4)
    parser.add_argument(
        "--minimum-persistence-readouts", type=int, default=500)
    parser.add_argument("--minimum-regret-rejections", type=int, default=1)
    parser.add_argument("--minimum-temporal-additions", type=int, default=8)
    parser.add_argument("--minimum-temporal-retentions", type=int, default=8)
    parser.add_argument("--minimum-union-events", type=int, default=300)
    args = parser.parse_args(argv)
    thresholds = {
        "expired_routes": args.minimum_expired_routes,
        "game_addition_rate_wilson_lower": (
            args.minimum_game_addition_rate_wilson_lower),
        "games_with_temporal_additions": (
            args.minimum_games_with_temporal_additions),
        "persistence_readouts": args.minimum_persistence_readouts,
        "regret_rejections": args.minimum_regret_rejections,
        "temporal_additions": args.minimum_temporal_additions,
        "temporal_retentions": args.minimum_temporal_retentions,
        "union_events": args.minimum_union_events,
    }
    report = audit(
        args.run_root, tuple(args.expected_seed), args.expected_source_commit,
        thresholds, args.cohort_id)
    payload = canonical_json_bytes(report) + b"\n"
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "wb") as stream:
            stream.write(payload)
    else:
        sys.stdout.buffer.write(payload)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
