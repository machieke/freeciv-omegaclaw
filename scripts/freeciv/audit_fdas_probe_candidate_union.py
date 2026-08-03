#!/usr/bin/env python3
"""Audit fresh engine-backed FDAS probe candidate-union evidence."""

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
from freeciv_agent.planning import (  # noqa: E402
    DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateChoiceSetStore,
    PROBE_CANDIDATE_REACHABILITY_IDENTITY,
)


AUDIT_IDENTITY = "fdas-probe-candidate-union-audit/1.0"
COMPONENT_ID = "fdas-probe-candidate-union"
CALIBRATED_COMPONENT_ID = "fdas-calibrated-candidate-union"
CONFIG_SOURCE = (
    "profile/dependent_atomspace_defense_choice_surface_shadow.yaml")
MANIFEST_SOURCE = "profile/fdas_manifest_defense_probe_union_shadow.json"
PROBE_CONFIG = {
    "advantage_gain": 1.0,
    "congestion_gain": 1.0,
    "cost_gain": 1.0,
    "current_following_gain": 0.0,
    "max_steps": 16,
    "maximum_clipped_fraction": 0.25,
    "maximum_importance_weight": 10.0,
    "minimum_ess_fraction": 0.2,
    "minimum_path_diversity": 0.0,
    "mode": "two_stream",
    "path_count": 128,
    "reference_fraction": 0.25,
    "risk_gain": 1.0,
    "seed": 1729,
    "temperature": 1.0,
}
DEFAULT_THRESHOLDS = {
    "game_addition_rate_wilson_lower": 0.10,
    "games_with_additions": 4,
    "mixed_action_unions": 8,
    "probe_additions": 8,
    "probe_readouts": 500,
    "union_events": 300,
}


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _wilson(successes, samples, z=1.959963984540054):
    if samples < 1:
        return 0.0, 1.0
    n = float(samples)
    p = float(successes) / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    radius = z * math.sqrt(
        p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def _completed_endpoint(status):
    return bool(
        status.get("completed") is True
        and status.get("infrastructure_failure") is False
        and (status.get("horizon_reached") is True
             or status.get("terminal_game_over") is True
             or status.get("terminal_player_elimination") is True))


def _hash(value):
    return bool(
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value))


def _validate_signal_ledger(ledger):
    errors = []
    if not isinstance(ledger, dict):
        return ("probe-signal-ledger-invalid",)
    semantic = dict(ledger)
    ledger_hash = semantic.pop("ledger_hash", None)
    if ledger_hash != structural_hash(semantic):
        errors.append("probe-signal-ledger-hash-differs")
    uses = ledger.get("uses")
    if not isinstance(uses, list):
        return tuple(errors + ["probe-signal-uses-invalid"])
    by_signal = dict((value.get("signal_name"), value) for value in uses)
    protected = {
        "calibrated_transition_estimate",
        "corrected_bridge_overlap",
        "corrected_probe_weight",
        "raw_probe_count",
    }
    if (not protected.issubset(by_signal)
            or any(by_signal[value].get("used_in_final_score") is not False
                   for value in protected)
            or by_signal["raw_probe_count"].get("transformation")
            != "count_only"):
        errors.append("probe-signals-gained-score-authority")
    return tuple(errors)


def _validate_probe_union(details, payload, calibrated_parent=None):
    errors = []
    if not isinstance(details, dict):
        return ("probe-details-not-object",), {}
    semantic = dict(details)
    result_hash = semantic.pop("result_hash", None)
    if result_hash != structural_hash(semantic):
        errors.append("probe-union-result-hash-differs")
    if details.get("identity") != PROBE_CANDIDATE_REACHABILITY_IDENTITY:
        errors.append("probe-union-identity-differs")
    if (details.get("snapshot_id") != payload.get("snapshot_id")
            or details.get("revision_id") != payload.get("revision_id")):
        errors.append("probe-revision-binding-differs")
    if any(details.get(name) is not False for name in (
            "action_selection_changed", "capacity_solver_enabled",
            "flow_advection_enabled", "policy_authority",
            "readout_authority", "truth_mutated")):
        errors.append("probe-shadow-authority-differs")
    if details.get("scalar_final_score_authority") is not True:
        errors.append("probe-scalar-authority-differs")
    if (details.get("maximum_probe_regions") != 1
            or details.get("probe_per_action") != 1
            or details.get("probe_config") != PROBE_CONFIG
            or details.get("goal_id")
            != DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET):
        errors.append("frozen-probe-configuration-differs")
    for name in (
            "backward_probe_batch_hash", "bridge_selection_hash",
            "calibrated_union_result_hash", "forward_probe_batch_hash",
            "graph_artifact_hash", "graph_probe_semantic_hash"):
        if not _hash(details.get(name)):
            errors.append("{}-invalid".format(name.replace("_", "-")))
    errors.extend(_validate_signal_ledger(details.get("signal_ledger")))
    readouts = details.get("readouts")
    members = details.get("members")
    base_ids = details.get("base_calibrated_operation_ids")
    selected = details.get("probe_selected_operation_ids")
    additions = details.get("probe_added_operation_ids")
    collections = (readouts, members, base_ids, selected, additions)
    if (not isinstance(readouts, list) or not readouts
            or not isinstance(members, list) or not members
            or not isinstance(base_ids, list) or not base_ids
            or not all(isinstance(value, list) for value in collections)):
        return tuple(errors + ["probe-union-collections-invalid"]), {}
    readout_ids = tuple(value.get("operation_id") for value in readouts)
    member_ids = tuple(value.get("operation_id") for value in members)
    base_ids = tuple(base_ids)
    selected = tuple(selected)
    additions = tuple(additions)
    if any(len(values) != len(set(values)) for values in (
            readout_ids, member_ids, base_ids, selected, additions)):
        errors.append("probe-union-ids-not-unique")
    if (set(base_ids) - set(member_ids)
            or set(member_ids) - set(readout_ids)
            or set(selected) - set(member_ids)
            or set(additions) - set(selected)
            or set(additions).intersection(base_ids)
            or len(selected) > 1
            or len(additions) > 1
            or len(member_ids) > len(base_ids) + 1):
        errors.append("probe-union-membership-bound-differs")
    ranks = tuple(value.get("baseline_rank") for value in readouts)
    if ranks != tuple(range(1, len(readouts) + 1)):
        errors.append("probe-scalar-ranking-differs")
    readout_by_id = dict(zip(readout_ids, readouts))
    member_by_id = dict(zip(member_ids, members))
    baseline_id = details.get("baseline_selected_operation_id")
    if (baseline_id != base_ids[0]
            or baseline_id != readout_ids[0]
            or baseline_id not in member_by_id
            or set(member_by_id[baseline_id].get("reasons", ()))
            < {"scalar-top-k", "scalar-winner"}):
        errors.append("probe-scalar-winner-protection-differs")
    for readout in readouts:
        values = tuple(readout.get(name) for name in (
            "forward_support", "backward_support", "corrected_overlap",
            "location_eligibility", "uncertainty"))
        if (any(isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0 for value in values)):
            errors.append("probe-readout-numeric-domain-differs")
            continue
        overlap = math.sqrt(float(values[0]) * float(values[1]))
        if (abs(float(values[2]) - overlap) > 1e-12
                or abs(float(values[3]) - float(values[2])) > 1e-12):
            errors.append("probe-corrected-overlap-differs")
        if (readout.get("selected_for_probe_recall")
                != (readout.get("operation_id") in selected)):
            errors.append("probe-readout-selection-differs")
        if readout.get("operation_type") not in (
                DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES):
            errors.append("probe-readout-action-differs")
    for operation_id in selected:
        member = member_by_id.get(operation_id, {})
        if ("probe-informed-reachability"
                not in member.get("reasons", ())
                or readout_by_id.get(operation_id, {}).get(
                    "location_eligibility", 0.0) <= 0.0):
            errors.append("probe-selected-member-lacks-reachability")
    if any(
            "probe-informed-reachability" in value.get("reasons", ())
            and value.get("operation_id") not in selected
            for value in members):
        errors.append("probe-member-reason-differs")
    fallback = details.get("fallback_required")
    graph_complete = details.get("graph_complete")
    probe_healthy = details.get("probe_healthy")
    if any(not isinstance(value, bool)
           for value in (fallback, graph_complete, probe_healthy)):
        errors.append("probe-health-state-invalid")
    elif (fallback != (not graph_complete or not probe_healthy)
            or fallback != (details.get("fallback_reason") is not None)
            or (fallback and (selected or additions))):
        errors.append("probe-fallback-state-differs")
    if calibrated_parent is None:
        errors.append("probe-calibrated-parent-missing")
    else:
        parent_members = tuple(
            value.get("operation_id")
            for value in calibrated_parent.get("members", ()))
        if (details.get("calibrated_union_result_hash")
                != calibrated_parent.get("result_hash")
                or base_ids != parent_members
                or baseline_id != calibrated_parent.get(
                    "baseline_selected_operation_id")):
            errors.append("probe-calibrated-parent-binding-differs")
    return tuple(errors), {
        "additions": len(additions),
        "fallbacks": int(fallback is True),
        "healthy": int(probe_healthy is True),
        "incomplete_graphs": int(graph_complete is False),
        "members": len(members),
        "mixed_action": len(set(
            value.get("operation_type") for value in readouts)) > 1,
        "readouts": len(readouts),
        "selected": len(selected),
        "selection_changes": int(
            details.get("action_selection_changed") is True),
    }


def audit(run_root, expected_seeds, expected_source_commit, thresholds=None,
          cohort_id="fdas_probe_candidate_union_confirmation_v1"):
    run_root = os.path.abspath(run_root)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (not expected_seeds
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError("probe union audit requires unique seeds")
    if not isinstance(expected_source_commit, str) or len(
            expected_source_commit) != 40:
        raise ValueError("probe union audit requires full source commit")
    if not isinstance(cohort_id, str) or not cohort_id:
        raise ValueError("probe union audit requires cohort identity")
    thresholds = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    if set(thresholds) != set(DEFAULT_THRESHOLDS):
        raise ValueError("probe union audit thresholds differ")
    for name, value in thresholds.items():
        if name == "game_addition_rate_wilson_lower":
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not 0.0 <= float(value) <= 1.0):
                raise ValueError("probe union rate threshold is invalid")
        elif (isinstance(value, bool) or not isinstance(value, int)
                or value < 1):
            raise ValueError("probe union count threshold is invalid")
    game_dirs = tuple(sorted(glob.glob(os.path.join(
        run_root, "games", "main", "e_full_loop", "*"))))
    totals = {
        "additions": 0,
        "fallbacks": 0,
        "healthy": 0,
        "incomplete_graphs": 0,
        "members": 0,
        "mixed_action": 0,
        "readouts": 0,
        "selected": 0,
        "selection_changes": 0,
        "union_events": 0,
    }
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
        events = []
        with open(event_path, encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream]
        event_by_id = dict((value.get("event_id"), value) for value in events)
        game_totals = dict((key, 0) for key in totals)
        union_errors = []
        for event in events:
            payload = event.get("payload", {})
            if (event.get("type") != "atomspace_shadow_decision"
                    or payload.get("component_id") != COMPONENT_ID):
                continue
            game_totals["union_events"] += 1
            parent_events = tuple(
                event_by_id.get(value) for value in event.get("caused_by", ()))
            calibrated = tuple(
                value.get("payload", {}).get("details")
                for value in parent_events if value is not None
                and value.get("payload", {}).get("component_id")
                == CALIBRATED_COMPONENT_ID)
            parent = calibrated[0] if len(calibrated) == 1 else None
            errors, measures = _validate_probe_union(
                payload.get("details"), payload, parent)
            union_errors.extend(
                "{}:{}".format(event.get("event_id"), value)
                for value in errors)
            for key, value in measures.items():
                game_totals[key] += int(value)
        for key, value in game_totals.items():
            totals[key] += value
        declaration = manifest.get("dependent_atomspace", {})
        source = manifest.get("source", {})
        game_gates = {
            "candidate_choice_count_matches_union_events": (
                len(choice_store.choice_sets())
                == game_totals["union_events"]
                == status.get("fdas_candidate_choice_sets")),
            "completed_preregistered_endpoint_without_infrastructure_failure": (
                _completed_endpoint(status)),
            "event_ledger_valid_without_warnings": (
                validation.valid and not validation.warnings),
            "manifest_profile_is_frozen": (
                declaration.get("config_source") == CONFIG_SOURCE
                and declaration.get("manifest_source") == MANIFEST_SOURCE),
            "probe_counters_match_status": all((
                    status.get("fdas_probe_candidate_union_additions")
                    == game_totals["additions"],
                    status.get("fdas_probe_candidate_union_evaluations")
                    == game_totals["union_events"],
                    status.get("fdas_probe_candidate_union_fallbacks")
                    == game_totals["fallbacks"],
                    status.get("fdas_probe_candidate_union_incomplete_graphs")
                    == game_totals["incomplete_graphs"],
                    status.get("fdas_probe_candidate_union_members")
                    == game_totals["members"],
                    status.get("fdas_probe_candidate_union_readouts")
                    == game_totals["readouts"],
                    status.get("fdas_probe_candidate_union_selected")
                    == game_totals["selected"],
                    status.get("fdas_probe_candidate_union_selection_changes")
                    == game_totals["selection_changes"],
                    status.get("fdas_probe_candidate_union_unhealthy")
                    == game_totals["union_events"] - game_totals["healthy"],
                )),
            "probe_events_are_semantically_valid": not union_errors,
            "source_is_clean_and_frozen": (
                source.get("dirty") is False
                and source.get("commit") == expected_source_commit),
            "zero_probe_fallbacks": (
                game_totals["fallbacks"] == 0
                and game_totals["incomplete_graphs"] == 0
                and game_totals["healthy"] == game_totals["union_events"]),
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
    games_with_additions = sum(
        value["measures"]["additions"] > 0 for value in games)
    rate_lower, rate_upper = _wilson(games_with_additions, len(games))
    mechanical_gates = {
        "all_game_gates_pass": bool(games) and not all_errors,
        "exact_preregistered_seeds_completed": (
            tuple(sorted(value["seed"] for value in games))
            == tuple(sorted(expected_seeds))),
        "source_identity_is_identical": bool(games) and len({
            structural_hash(value["source"]) for value in games}) == 1,
    }
    progression_gates = {
        "game_level_recurrence": (
            games_with_additions >= thresholds["games_with_additions"]),
        "game_level_recurrence_interval": (
            rate_lower >= thresholds[
                "game_addition_rate_wilson_lower"]),
        "mixed_action_opportunity_yield": (
            totals["mixed_action"] >= thresholds["mixed_action_unions"]),
        "probe_addition_yield": (
            totals["additions"] >= thresholds["probe_additions"]),
        "probe_readout_yield": (
            totals["readouts"] >= thresholds["probe_readouts"]),
        "union_event_yield": (
            totals["union_events"] >= thresholds["union_events"]),
    }
    semantic = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "corrected probes recurrently add bounded candidate recall beyond "
            "the frozen calibrated union on fresh engine games; no ranking, "
            "action-selection, gameplay, score, or win-rate claim"),
        "cohort_id": cohort_id,
        "completion_semantics": (
            "fixed-horizon-or-genuine-absorbing-terminal"),
        "expected_source_commit": expected_source_commit,
        "games": games,
        "games_with_additions": games_with_additions,
        "mechanical_gates": mechanical_gates,
        "mechanically_accepted": all(mechanical_gates.values()),
        "progression_gate_passed": all(progression_gates.values()),
        "progression_gates": progression_gates,
        "thresholds": thresholds,
        "totals": totals,
        "wilson_game_addition_rate": {
            "interval_lower": rate_lower,
            "interval_upper": rate_upper,
            "observed_rate": (
                games_with_additions / float(len(games)) if games else 0.0),
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
        "--cohort-id", default="fdas_probe_candidate_union_confirmation_v1")
    parser.add_argument(
        "--minimum-game-addition-rate-wilson-lower", type=float, default=0.10)
    parser.add_argument("--minimum-games-with-additions", type=int, default=4)
    parser.add_argument("--minimum-mixed-action-unions", type=int, default=8)
    parser.add_argument("--minimum-probe-additions", type=int, default=8)
    parser.add_argument("--minimum-probe-readouts", type=int, default=500)
    parser.add_argument("--minimum-union-events", type=int, default=300)
    args = parser.parse_args(argv)
    thresholds = {
        "game_addition_rate_wilson_lower": (
            args.minimum_game_addition_rate_wilson_lower),
        "games_with_additions": args.minimum_games_with_additions,
        "mixed_action_unions": args.minimum_mixed_action_unions,
        "probe_additions": args.minimum_probe_additions,
        "probe_readouts": args.minimum_probe_readouts,
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
