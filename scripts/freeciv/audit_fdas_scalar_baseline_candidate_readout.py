#!/usr/bin/env python3
"""Audit a fresh protected scalar-baseline candidate readout smoke."""

import argparse
import glob
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_grounded_transition_candidate_readout import (  # noqa: E402
    UNION_COMPONENT_ID,
    _completed_endpoint,
    _validate_union,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    FdasCandidateChoiceSetStore,
    FdasDecisionSafeCandidateReadoutConfig,
    SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY,
    SCALAR_BASELINE_CONTROL_SEMANTICS,
)


AUDIT_IDENTITY = "fdas-scalar-baseline-candidate-readout-audit/1.0"
READOUT_COMPONENT_ID = "fdas-scalar-baseline-candidate-readout"
LEGACY_READOUT_COMPONENT_ID = "fdas-decision-safe-candidate-readout"
CONFIG_SOURCE = (
    "profile/dependent_atomspace_defense_choice_surface_shadow.yaml")
MANIFEST_SOURCE = (
    "profile/fdas_manifest_defense_scalar_baseline_readout_shadow.json")
REQUIRED_NONINFERIORITY_CHECKS = frozenset({
    "estimated-turns",
    "first-step-movement-cost",
    "homecity-relation",
    "hit-points",
    "moves-left",
    "total-movement-cost",
    "unit-type",
    "veteran-level",
})


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _validate_readout(details, payload, protected_parent):
    errors = []
    if not isinstance(details, dict):
        return ("details-not-object",), {}
    semantic = dict(details)
    result_hash = semantic.pop("result_hash", None)
    if result_hash != structural_hash(semantic):
        errors.append("scalar-baseline-result-hash-differs")
    if details.get("identity") != SCALAR_BASELINE_CANDIDATE_READOUT_IDENTITY:
        errors.append("scalar-baseline-identity-differs")
    if details.get("control_semantics") != SCALAR_BASELINE_CONTROL_SEMANTICS:
        errors.append("scalar-baseline-control-semantics-differ")
    if any(details.get(name) is not False for name in (
            "action_selection_changed", "policy_authority",
            "readout_authority", "truth_mutated")):
        errors.append("scalar-baseline-shadow-authority-differs")
    if (details.get("snapshot_id") != payload.get("snapshot_id")
            or details.get("revision_id") != payload.get("revision_id")):
        errors.append("scalar-baseline-event-binding-differs")
    if (not isinstance(protected_parent, dict)
            or details.get("protected_union_result_hash")
            != protected_parent.get("result_hash")
            or details.get("snapshot_id")
            != protected_parent.get("snapshot_id")
            or details.get("revision_id")
            != protected_parent.get("revision_id")):
        errors.append("scalar-baseline-parent-binding-differs")
    try:
        config = FdasDecisionSafeCandidateReadoutConfig.from_dict(
            details.get("config"))
        if config.to_dict() != details.get("config"):
            errors.append("scalar-baseline-config-is-not-canonical")
    except (TypeError, ValueError):
        config = None
        errors.append("scalar-baseline-config-is-invalid")

    candidates = details.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
        errors.append("scalar-baseline-candidates-are-invalid")
    by_id = dict(
        (value.get("operation_id"), value)
        for value in candidates if isinstance(value, dict))
    if len(by_id) != len(candidates) or None in by_id:
        errors.append("scalar-baseline-candidate-identities-differ")
    parent_members = set(
        value.get("operation_id")
        for value in protected_parent.get("members", ())
        if isinstance(value, dict)) if isinstance(protected_parent, dict) else set()
    baseline_id = details.get("baseline_operation_id")
    proposed_id = details.get("proposed_operation_id")
    if (not isinstance(protected_parent, dict)
            or baseline_id
            != protected_parent.get("baseline_selected_operation_id")
            or set(by_id) - parent_members):
        errors.append("scalar-baseline-protected-membership-differs")
    control = by_id.get(baseline_id)
    if control is not None and control.get(
            "eligibility_reason") != "protected-scalar-control":
        errors.append("scalar-baseline-control-grounding-differs")

    status = details.get("status")
    if status == "eligible-shadow":
        proposed = by_id.get(proposed_id)
        if (details.get("shadow_preference") is not True
                or control is None or proposed is None
                or proposed_id == baseline_id
                or details.get("reason")
                != "calibrated-and-grounded-dominance"):
            errors.append("scalar-baseline-eligible-binding-differs")
        if control is not None and proposed is not None:
            separation = (
                0.0 if config is None
                else config.minimum_interval_separation)
            if not (
                    proposed.get("interval_lower")
                    > control.get("interval_upper")
                    and proposed.get("interval_lower")
                    >= control.get("interval_upper") + separation):
                errors.append("scalar-baseline-intervals-are-not-separated")
            homecity_rank = {"none": 0, "other": 1, "target": 2}
            noninferior = (
                proposed.get("unit_type") == control.get("unit_type")
                and proposed.get("estimated_turns")
                <= control.get("estimated_turns")
                and proposed.get("total_movement_cost")
                <= control.get("total_movement_cost")
                and proposed.get("first_step_movement_cost")
                <= control.get("first_step_movement_cost")
                and proposed.get("hp") >= control.get("hp")
                and proposed.get("moves_left") >= control.get("moves_left")
                and proposed.get("veteran") >= control.get("veteran")
                and homecity_rank.get(proposed.get("homecity_relation"), -1)
                >= homecity_rank.get(control.get("homecity_relation"), 99))
            if not noninferior:
                errors.append("scalar-baseline-grounded-noninferiority-differs")
            if (set(proposed.get("noninferiority_checks", ()))
                    != REQUIRED_NONINFERIORITY_CHECKS
                    or proposed.get("eligibility_reason") != "eligible"):
                errors.append("scalar-baseline-grounded-checks-differ")
    elif status == "abstained":
        if (details.get("shadow_preference") is not False
                or proposed_id is not None):
            errors.append("scalar-baseline-abstention-gained-preference")
    else:
        errors.append("scalar-baseline-status-is-invalid")
    rejected = details.get("rejected", ())
    if (not isinstance(rejected, list)
            or any(not isinstance(value, str) or not value
                   for value in rejected)):
        rejected = []
        errors.append("scalar-baseline-rejections-are-invalid")
    grounded_alternatives = max(0, len(candidates) - int(control is not None))
    return tuple(sorted(set(errors))), {
        "abstentions": int(status == "abstained"),
        "eligible": int(status == "eligible-shadow"),
        "evaluations": 1,
        "grounded_alternatives": grounded_alternatives,
        "interval_overlaps": sum(
            value.endswith(":calibrated-interval-overlap")
            for value in rejected),
        "shadow_preferences": int(details.get("shadow_preference") is True),
    }


def audit(run_root, expected_seeds, expected_source_commit):
    run_root = os.path.abspath(run_root)
    expected_seeds = tuple(int(value) for value in expected_seeds)
    if (not expected_seeds
            or len(expected_seeds) != len(set(expected_seeds))):
        raise ValueError("scalar-baseline audit requires unique seeds")
    if (not isinstance(expected_source_commit, str)
            or len(expected_source_commit) != 40):
        raise ValueError("scalar-baseline audit requires full commit")
    game_dirs = tuple(sorted(glob.glob(os.path.join(
        run_root, "games", "main", "e_full_loop", "*"))))
    totals = {
        "abstentions": 0,
        "eligible": 0,
        "evaluations": 0,
        "grounded_alternatives": 0,
        "interval_overlaps": 0,
        "shadow_preferences": 0,
        "union_abstentions": 0,
        "union_additions": 0,
        "union_broad_backoff_predictions": 0,
        "union_candidate_specific_predictions": 0,
        "union_estimated_predictions": 0,
        "union_events": 0,
        "union_members": 0,
        "union_readouts": 0,
    }
    games = []
    for game_dir in game_dirs:
        manifest = _read_json(os.path.join(game_dir, "manifest.json"))
        status = _read_json(os.path.join(game_dir, "status.json"))
        event_path = os.path.join(game_dir, "events.jsonl")
        choice_path = os.path.join(game_dir, "fdas-candidate-choice-sets.json")
        choice_raw = _read_json(choice_path)
        choice_store = FdasCandidateChoiceSetStore.load(
            choice_path, choice_raw["persistence_identity"])
        validation = validate_file(event_path)
        game_totals = dict((name, 0) for name in totals)
        union_by_hash = {}
        readouts = []
        errors = []
        legacy_readout_events = 0
        with open(event_path, encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                payload = event.get("payload", {})
                details = payload.get("details", {})
                component = payload.get("component_id")
                if event.get("type") != "atomspace_shadow_decision":
                    continue
                if component == UNION_COMPONENT_ID:
                    union_errors, measures = _validate_union(details, payload)
                    errors.extend(
                        "{}:{}".format(event.get("event_id"), value)
                        for value in union_errors)
                    mapping = {
                        "abstentions": "union_abstentions",
                        "additions": "union_additions",
                        "broad_backoff_predictions": (
                            "union_broad_backoff_predictions"),
                        "candidate_specific_predictions": (
                            "union_candidate_specific_predictions"),
                        "estimated_predictions": "union_estimated_predictions",
                        "members": "union_members",
                        "readouts": "union_readouts",
                        "union_events": "union_events",
                    }
                    for name, value in measures.items():
                        game_totals[mapping[name]] += int(value)
                    if isinstance(details, dict):
                        union_by_hash[details.get("result_hash")] = details
                elif component == READOUT_COMPONENT_ID:
                    readouts.append(event)
                elif component == LEGACY_READOUT_COMPONENT_ID:
                    legacy_readout_events += 1
        for event in readouts:
            payload = event.get("payload", {})
            details = payload.get("details", {})
            readout_errors, measures = _validate_readout(
                details, payload,
                union_by_hash.get(details.get("protected_union_result_hash")))
            errors.extend(
                "{}:{}".format(event.get("event_id"), value)
                for value in readout_errors)
            for name, value in measures.items():
                game_totals[name] += int(value)
        for name, value in game_totals.items():
            totals[name] += value

        declaration = manifest.get("dependent_atomspace", {})
        source = manifest.get("source", {})
        game_gates = {
            "choice_union_and_readout_counts_match": (
                len(choice_store.choice_sets())
                == game_totals["union_events"]
                == game_totals["evaluations"]
                == status.get("fdas_candidate_choice_sets")),
            "completed_endpoint_without_infrastructure_failure": (
                _completed_endpoint(status)),
            "event_ledger_valid_without_warnings": (
                validation.valid and not validation.warnings),
            "exact_manifest_and_config": (
                declaration.get("config_source") == CONFIG_SOURCE
                and declaration.get("manifest_source") == MANIFEST_SOURCE),
            "grounded_transition_counters_match_status": all(
                status.get("fdas_grounded_transition_" + suffix)
                == game_totals[name]
                for suffix, name in (
                    ("candidate_union_abstentions", "union_abstentions"),
                    ("candidate_union_additions", "union_additions"),
                    ("broad_backoff_predictions",
                     "union_broad_backoff_predictions"),
                    ("candidate_specific_predictions",
                     "union_candidate_specific_predictions"),
                    ("candidate_union_members", "union_members"),
                    ("candidate_union_readouts", "union_events"),
                )),
            "legacy_control_readout_is_absent": legacy_readout_events == 0,
            "parent_calibrated_counters_match_status": all(
                status.get("fdas_calibrated_candidate_union_" + suffix)
                == game_totals[name]
                for suffix, name in (
                    ("abstentions", "union_abstentions"),
                    ("additions", "union_additions"),
                    ("members", "union_members"),
                    ("readouts", "union_events"),
                )) and status.get(
                    "fdas_calibrated_candidate_union_selection_changes") == 0,
            "readout_counters_match_status": all(
                status.get("fdas_scalar_baseline_candidate_readout_" + suffix)
                == game_totals[name]
                for suffix, name in (
                    ("abstentions", "abstentions"),
                    ("eligible", "eligible"),
                    ("evaluations", "evaluations"),
                    ("grounded_alternatives", "grounded_alternatives"),
                    ("interval_overlaps", "interval_overlaps"),
                    ("shadow_preferences", "shadow_preferences"),
                )),
            "events_are_semantically_valid": not errors,
            "source_is_clean_and_frozen": (
                source.get("dirty") is False
                and source.get("commit") == expected_source_commit),
            "zero_rejected_actions": status.get("rejected_actions") == 0,
        }
        games.append({
            "errors": errors,
            "event_errors": list(validation.errors),
            "event_warnings": list(validation.warnings),
            "game_gates": game_gates,
            "game_id": manifest.get("game_id"),
            "measures": game_totals,
            "runtime_ms": status.get("engine_backend_latency_ms"),
            "seed": manifest.get("seed"),
            "source": source,
        })

    mechanical_gates = {
        "all_game_gates_pass": (
            bool(games)
            and all(all(value["game_gates"].values()) for value in games)),
        "exact_expected_seeds_completed": (
            tuple(sorted(value["seed"] for value in games))
            == tuple(sorted(expected_seeds))),
        "source_identity_is_identical": bool(games) and len({
            structural_hash(value["source"]) for value in games}) == 1,
    }
    yield_gates = {
        "candidate_specific_prediction_observed": (
            totals["union_candidate_specific_predictions"] > 0),
        "grounded_protected_alternative_compared": (
            totals["grounded_alternatives"] > 0),
        "scalar_baseline_readout_observed": totals["evaluations"] > 0,
        "shadow_preference_cannot_change_action": (
            totals["shadow_preferences"] == totals["eligible"]),
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "protected scalar-top-1 control alignment and shadow preference "
            "mechanics only; no counterfactual outcome, ranking quality, "
            "gameplay, score, or win-rate claim"),
        "expected_source_commit": expected_source_commit,
        "games": games,
        "mechanical_gates": mechanical_gates,
        "mechanically_accepted": all(mechanical_gates.values()),
        "passed": all(mechanical_gates.values()) and all(yield_gates.values()),
        "totals": totals,
        "yield_gates": yield_gates,
    }
    report["report_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = audit(
        args.run_root, args.expected_seed, args.expected_source_commit)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    print(json.dumps({
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
        "totals": report["totals"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
