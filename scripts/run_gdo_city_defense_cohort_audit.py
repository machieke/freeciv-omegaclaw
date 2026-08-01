#!/usr/bin/env python3
"""Audit a paired GDO-4 engine cohort at the defence-mechanism boundary."""

import argparse
from collections import Counter, defaultdict
import glob
import hashlib
import json
import math
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
for path in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.config import load as load_harness_config  # noqa: E402
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402


TERMINAL_TYPES = frozenset((
    "operation_completed",
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
))
ADVERSE_TERMINAL_TYPES = frozenset((
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
))
LIFECYCLE_TYPES = frozenset((
    "operation_proposed",
    "operation_reserved",
    "operation_step_selected",
    "operation_activated",
    "operation_step_revalidated",
    "operation_step_committed",
    "operation_completed",
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
    "operation_blocked",
))
SUPPORTED_OPERATION_TYPES = frozenset((
    "fortify_existing_defender",
    "move_defender_to_city",
))


def _fraction(numerator, denominator):
    return (
        None
        if not denominator
        else float(numerator)
        / float(denominator))


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(
        float(value)
        for value in values)
    rank = max(
        0,
        int(math.ceil(
            float(fraction)
            * len(ordered))) - 1)
    return ordered[rank]


def _operation_id(event):
    value = event.get(
        "payload", {}).get(
            "operation_id")
    return (
        value
        if isinstance(value, str)
        and value
        else None)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(
                1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _actor_ref(value):
    if isinstance(value, int):
        return "unit:{}".format(value)
    if isinstance(value, str):
        if value.startswith("unit:"):
            return value
        if value.isdigit():
            return "unit:{}".format(value)
    return None


def _exclusive_claim_keys(payload):
    result = set()
    for claim in payload.get(
            "claims", ()):
        if (
                not isinstance(claim, dict)
                or claim.get("hardness")
                != "hard_current"
                or claim.get("exclusive")
                is not True):
            continue
        result.add(
            canonical_json_bytes({
                "resource":
                    claim.get("resource"),
                "window":
                    claim.get("window"),
            }))
    return result


def _city_ids(event):
    cities = event.get(
        "payload", {}).get(
            "own_state", {}).get(
                "cities")
    if not isinstance(cities, list):
        return None
    return frozenset(
        city.get("city_id")
        for city in cities
        if (
            isinstance(city, dict)
            and isinstance(
                city.get("city_id"),
                int)))


def analyze_trace(events):
    """Return order-sensitive GDO-4 observations for one event stream."""
    counts = Counter()
    selected = set()
    activated = set()
    terminal = {
        event_type: set()
        for event_type in
        TERMINAL_TYPES
    }
    selected_response_turns = 0
    activated_response_turns = 0
    selected_response_observations = set()
    activated_response_observations = set()
    selected_at_risk_cities = defaultdict(
        list)
    reservations = defaultdict(list)
    protected_actors = defaultdict(set)
    movement_activations = []
    authority_rows = []
    winner_changing_rows = []
    unsupported_authority = []
    preparation_latency_ms = []
    full_loop_latency_ms = []
    previous_cities = None
    previous_snapshot_id = None
    lost_city_ids = set()
    city_losses = []
    selected_at_risk_city_losses = []
    for event in events:
        event_type = str(
            event.get("type", ""))
        payload = event.get(
            "payload", {})
        if event_type == (
                "state_snapshot"):
            current_cities = _city_ids(
                event)
            snapshot_id = payload.get(
                "snapshot_id")
            if current_cities is not None:
                if previous_cities is not None:
                    for city_id in sorted(
                            previous_cities
                            - current_cities):
                        if city_id in lost_city_ids:
                            continue
                        lost_city_ids.add(
                            city_id)
                        city_losses.append({
                            "city_id": city_id,
                            "from_snapshot_id":
                                previous_snapshot_id,
                            "to_snapshot_id":
                                snapshot_id,
                            "turn": int(
                                event.get(
                                    "turn", 0)),
                        })
                        loss_turn = int(
                            event.get(
                                "turn", 0))
                        matching = [
                            row for row in
                            selected_at_risk_cities.get(
                                city_id, ())
                            if (
                                row[
                                    "selected_turn"]
                                <= loss_turn
                                <= row[
                                    "deadline_turn"]
                                + 1)
                        ]
                        if matching:
                            selected_at_risk_city_losses.append({
                                "city_id":
                                    city_id,
                                "deadline_turn":
                                    min(
                                        row[
                                            "deadline_turn"]
                                        for row in
                                        matching),
                                "from_snapshot_id":
                                    previous_snapshot_id,
                                "selected_snapshot_ids":
                                    sorted(set(
                                        row[
                                            "snapshot_id"]
                                        for row in
                                        matching)),
                                "to_snapshot_id":
                                    snapshot_id,
                                "turn":
                                    loss_turn,
                            })
                previous_cities = (
                    current_cities)
                previous_snapshot_id = (
                    snapshot_id)
            continue
        if event_type == (
                "metric_sample"):
            name = payload.get("name")
            value = payload.get("value")
            if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)):
                if name == (
                        "city_defense_authority_preparation_latency_ms"):
                    preparation_latency_ms.append(
                        float(value))
                elif name == (
                        "turn_full_loop_latency_ms"):
                    full_loop_latency_ms.append(
                        float(value))
            if name == (
                    "operation_authority_selection"):
                labels = payload.get(
                    "labels", {})
                if (
                        isinstance(labels, dict)
                        and labels.get(
                            "changed_winner")
                        == "true"):
                    winner_changing_rows.append({
                        "authority_kind":
                            labels.get(
                                "authority_kind"),
                        "operation_type":
                            labels.get(
                                "operation_type"),
                        "typed": bool(
                            labels.get(
                                "authority_kind")
                            == "city_defense"
                            and labels.get(
                                "operation_type")
                            in SUPPORTED_OPERATION_TYPES),
                    })
            continue
        if event_type not in (
                LIFECYCLE_TYPES):
            continue
        operation_id = (
            _operation_id(event))
        if operation_id is None:
            continue
        counts[event_type] += 1
        snapshot_id = payload.get(
            "snapshot_id")
        if event_type == (
                "operation_proposed"):
            actor = _actor_ref(
                payload.get(
                    "actor_id"))
            if (
                    isinstance(snapshot_id, str)
                    and actor is not None
                    and (
                        payload.get(
                            "operation_type")
                        == "hold_sole_defender"
                        or payload.get(
                            "reason_code")
                        == "protected-sole-defender")):
                protected_actors[
                    snapshot_id].add(
                        actor)
            if (
                    payload.get(
                        "policy_authority")
                    is True
                    and payload.get(
                        "reason_code")
                    is not None):
                unsupported_authority.append({
                    "operation_id":
                        operation_id,
                    "reason_code":
                        payload.get(
                            "reason_code"),
                    "snapshot_id":
                        snapshot_id,
                })
        elif event_type == (
                "operation_reserved"):
            if isinstance(
                    snapshot_id, str):
                reservations[
                    snapshot_id].append((
                        operation_id,
                        _exclusive_claim_keys(
                            payload)))
        elif event_type == (
                "operation_step_selected"):
            selected.add(
                operation_id)
            selected_response_turns += 1
            target_id = payload.get(
                "target_id")
            observation = (
                snapshot_id,
                target_id)
            if (
                    isinstance(
                        snapshot_id, str)
                    and snapshot_id
                    and isinstance(
                        target_id, str)
                    and target_id):
                selected_response_observations.add(
                    observation)
            if (
                    isinstance(
                        target_id, str)
                    and target_id.startswith(
                        "city:")):
                try:
                    city_id = int(
                        target_id.split(
                            ":", 1)[1])
                    deadline_turn = int(
                        payload.get(
                            "deadline_turn"))
                except (TypeError, ValueError):
                    pass
                else:
                    selected_at_risk_cities[
                        city_id].append({
                            "deadline_turn":
                                deadline_turn,
                            "selected_turn":
                                int(
                                    event.get(
                                        "turn", 0)),
                            "snapshot_id":
                                snapshot_id,
                        })
        elif event_type == (
                "operation_activated"):
            activated.add(
                operation_id)
            activated_response_turns += 1
            target_id = payload.get(
                "target_id")
            observation = (
                snapshot_id,
                target_id)
            if (
                    isinstance(
                        snapshot_id, str)
                    and snapshot_id
                    and isinstance(
                        target_id, str)
                    and target_id):
                activated_response_observations.add(
                    observation)
            action = payload.get(
                "next_action", {})
            action_type = (
                action.get(
                    "action_type")
                if isinstance(
                    action, dict)
                else None)
            actor = _actor_ref(
                payload.get(
                    "actor_id"))
            authority_rows.append({
                "action_type":
                    action_type,
                "operation_id":
                    operation_id,
                "operation_type":
                    payload.get(
                        "operation_type"),
                "policy_authority":
                    payload.get(
                        "policy_authority"),
            })
            if (
                    action_type
                    == "unit_move"
                    and isinstance(
                        snapshot_id, str)
                    and actor is not None):
                movement_activations.append({
                    "actor_id": actor,
                    "operation_id":
                        operation_id,
                    "snapshot_id":
                        snapshot_id,
                })
        elif event_type in (
                TERMINAL_TYPES):
            terminal[
                event_type].add(
                    operation_id)
    hard_conflicts = []
    for snapshot_id, rows in (
            reservations.items()):
        for index, (
                first_id,
                first_claims) in enumerate(
                    rows):
            for second_id, second_claims in (
                    rows[index + 1:]):
                overlap = (
                    first_claims
                    & second_claims)
                if (
                        first_id != second_id
                        and overlap):
                    hard_conflicts.append({
                        "first_operation_id":
                            first_id,
                        "overlap_count":
                            len(overlap),
                        "second_operation_id":
                            second_id,
                        "snapshot_id":
                            snapshot_id,
                    })
    sole_defender_violations = [
        row for row in
        movement_activations
        if row["actor_id"] in
        protected_actors.get(
            row["snapshot_id"], ())
    ]
    completed = terminal[
        "operation_completed"]
    adverse = set().union(*(
        terminal[event_type]
        for event_type in
        ADVERSE_TERMINAL_TYPES))
    return {
        "authority_rows":
            authority_rows,
        "city_losses":
            city_losses,
        "selected_at_risk_city_losses":
            selected_at_risk_city_losses,
        "event_counts":
            dict(counts),
        "full_loop_latency_ms":
            full_loop_latency_ms,
        "hard_current_reservation_conflicts":
            hard_conflicts,
        "lifecycle": {
            "activated_adverse":
                len(activated & adverse),
            "activated_completed":
                len(activated & completed),
            "activated_unique":
                len(activated),
            "activated_response_turns":
                activated_response_turns,
            "activated_response_observations":
                len(
                    activated_response_observations),
            "selected_adverse":
                len(selected & adverse),
            "selected_completed":
                len(selected & completed),
            "selected_unique":
                len(selected),
            "selected_response_turns":
                selected_response_turns,
            "selected_response_observations":
                len(
                    selected_response_observations),
            "uncovered_threat_turns":
                max(
                    0,
                    selected_response_turns
                    - activated_response_turns),
            "uncovered_unique_city_snapshot_observations":
                len(
                    selected_response_observations
                    - activated_response_observations),
        },
        "preparation_latency_ms":
            preparation_latency_ms,
        "sole_defender_violations":
            sole_defender_violations,
        "unsupported_authority":
            unsupported_authority,
        "winner_changing_rows":
            winner_changing_rows,
    }


def _combine_arm(rows):
    lifecycle = Counter()
    event_counts = Counter()
    city_losses = []
    selected_at_risk_city_losses = []
    authority_rows = []
    winner_rows = []
    preparation_latency = []
    full_loop_latency = []
    result = {
        "hard_current_reservation_conflicts": [],
        "sole_defender_violations": [],
        "unsupported_authority": [],
    }
    for row in rows:
        lifecycle.update(
            row["lifecycle"])
        event_counts.update(
            row["event_counts"])
        city_losses.extend(
            row["city_losses"])
        selected_at_risk_city_losses.extend(
            row[
                "selected_at_risk_city_losses"])
        authority_rows.extend(
            row["authority_rows"])
        winner_rows.extend(
            row["winner_changing_rows"])
        preparation_latency.extend(
            row[
                "preparation_latency_ms"])
        full_loop_latency.extend(
            row[
                "full_loop_latency_ms"])
        for key in result:
            result[key].extend(
                row[key])
    selected = lifecycle[
        "selected_unique"]
    activated = lifecycle[
        "activated_unique"]
    typed_rows = sum(
        row["typed"]
        for row in winner_rows)
    result.update({
        "authority": {
            "action_types":
                dict(sorted(Counter(
                    row["action_type"]
                    for row in
                    authority_rows).items())),
            "operation_types":
                dict(sorted(Counter(
                    row["operation_type"]
                    for row in
                    authority_rows).items())),
            "policy_authority_values":
                dict(sorted(Counter(
                    str(row[
                        "policy_authority"])
                    for row in
                    authority_rows).items())),
            "row_count":
                len(authority_rows),
        },
        "city_loss": {
            "count": len(
                city_losses),
            "observations":
                city_losses,
            "scope":
                "own-city-identity-disappearance-between-authoritative-snapshots",
        },
        "selected_at_risk_city_loss": {
            "count": len(
                selected_at_risk_city_losses),
            "observations":
                selected_at_risk_city_losses,
            "scope":
                "selected-at-risk-city-identity-disappearance-by-deadline-plus-one",
        },
        "event_counts":
            dict(sorted(
                event_counts.items())),
        "full_loop_latency_ms": {
            "maximum":
                max(
                    full_loop_latency,
                    default=None),
            "p50":
                _percentile(
                    full_loop_latency,
                    0.50),
            "p95":
                _percentile(
                    full_loop_latency,
                    0.95),
            "sample_count":
                len(
                    full_loop_latency),
        },
        "lifecycle": {
            **dict(lifecycle),
            "activation_rate_per_selection":
                _fraction(
                    activated,
                    selected),
            "adverse_terminal_rate_per_selection":
                _fraction(
                    lifecycle[
                        "selected_adverse"],
                    selected),
            "completion_rate_per_selection":
                _fraction(
                    lifecycle[
                        "selected_completed"],
                    selected),
        },
        "preparation_latency_ms": {
            "maximum":
                max(
                    preparation_latency,
                    default=None),
            "p50":
                _percentile(
                    preparation_latency,
                    0.50),
            "p95":
                _percentile(
                    preparation_latency,
                    0.95),
            "sample_count":
                len(
                    preparation_latency),
        },
        "typed_winner_changing_coverage": {
            "coverage":
                _fraction(
                    typed_rows,
                    len(winner_rows)),
            "row_count":
                len(winner_rows),
            "typed_row_count":
                typed_rows,
        },
    })
    return result


def _analyze_file(path):
    digest = hashlib.sha256()

    def events():
        with open(
                path, "rb") as stream:
            for raw_line in stream:
                digest.update(
                    raw_line)
                if not raw_line.strip():
                    continue
                yield json.loads(
                    raw_line.decode(
                        "utf-8"))

    result = analyze_trace(
        events())
    return result, digest.hexdigest()


def _cohort_event_paths(root, cohort, arm):
    return sorted(glob.glob(
        os.path.join(
            root,
            "games",
            "impact_pair",
            cohort,
            arm,
            "e_full_loop",
            "*",
            "events.jsonl")))


def _predeclared_design(profile, cohort):
    config = load_harness_config(
        profile)
    row = config[
        "paired_impact"][
            "cohorts"][cohort]
    design = row.get(
        "city_defense_mechanism_design")
    return (
        design
        if isinstance(design, dict)
        else None)


def _delta(treatment, baseline):
    if (
            treatment is None
            or baseline is None):
        return None
    return float(treatment) - float(
        baseline)


def run(cohort_root, profile):
    aggregate_path = os.path.join(
        cohort_root,
        "impact-aggregate.json")
    with open(
            aggregate_path,
            encoding="utf-8") as stream:
        aggregate = json.load(
            stream)
    cohort = aggregate.get(
        "design", {}).get(
            "cohort")
    if not isinstance(cohort, str):
        raise ValueError(
            "impact aggregate has no cohort identity")
    design = _predeclared_design(
        profile, cohort)
    corrected_observation_metrics = bool(
        design is not None
        and design.get(
            "schema_version")
        in (
            "1.1",
            "1.2",
            "1.3",
            "1.4",
            "1.5",
            "1.6",
            "1.7",
        ))
    declared_types = tuple(
        design.get(
            "declared_operation_types",
            sorted(
                SUPPORTED_OPERATION_TYPES))
        if design is not None
        else sorted(
            SUPPORTED_OPERATION_TYPES))
    latency_design = (
        design.get("latency", {})
        if design is not None
        else {})
    typed_design = (
        design.get(
            "typed_winner_change", {})
        if design is not None
        else {})
    preparation_ceiling = (
        latency_design.get(
            "preparation_p95_ceiling_ms"))
    full_loop_ratio_ceiling = (
        latency_design.get(
            "full_loop_p95_ratio_ceiling"))
    minimum_typed_coverage = (
        typed_design.get(
            "minimum_coverage"))
    event_paths = {
        arm: _cohort_event_paths(
            cohort_root,
            cohort,
            arm)
        for arm in (
            "baseline",
            "treatment")
    }
    expected_games = int(
        aggregate.get(
            "complete_pairs", 0))
    for arm, paths in event_paths.items():
        if len(paths) != expected_games:
            raise ValueError(
                "{} has {} traces, expected {}"
                .format(
                    arm,
                    len(paths),
                    expected_games))
    arm_results = {}
    trace_sources = []
    validation = Counter()
    for arm in (
            "baseline",
            "treatment"):
        rows = []
        for path in event_paths[arm]:
            report = validate_file(
                path)
            validation[
                "event_count"] += (
                    report.event_count)
            validation[
                "error_count"] += len(
                    report.errors)
            validation[
                "warning_count"] += len(
                    report.warnings)
            row, digest = _analyze_file(
                path)
            rows.append(row)
            trace_sources.append({
                "arm": arm,
                "path": os.path.relpath(
                    path,
                    cohort_root),
                "sha256": digest,
            })
        arm_results[arm] = (
            _combine_arm(rows))
    baseline = arm_results[
        "baseline"]
    treatment = arm_results[
        "treatment"]
    completion_delta = _delta(
        treatment["lifecycle"][
            "completion_rate_per_selection"],
        baseline["lifecycle"][
            "completion_rate_per_selection"])
    uncovered_metric = (
        "uncovered_unique_city_snapshot_observations"
        if corrected_observation_metrics
        else "uncovered_threat_turns")
    city_loss_key = (
        "selected_at_risk_city_loss"
        if corrected_observation_metrics
        else "city_loss")
    uncovered_delta = (
        treatment["lifecycle"][
            uncovered_metric]
        - baseline["lifecycle"][
            uncovered_metric])
    city_loss_delta = (
        treatment[
            city_loss_key]["count"]
        - baseline[
            city_loss_key]["count"])
    raw_city_loss_delta = (
        treatment[
            "city_loss"]["count"]
        - baseline[
            "city_loss"]["count"])
    baseline_full_loop = (
        baseline[
            "full_loop_latency_ms"][
                "p95"])
    treatment_full_loop = (
        treatment[
            "full_loop_latency_ms"][
                "p95"])
    full_loop_ratio = (
        None
        if (
            baseline_full_loop is None
            or baseline_full_loop <= 0.0
            or treatment_full_loop
            is None)
        else treatment_full_loop
        / baseline_full_loop)
    generic_safety = aggregate.get(
        "safety_gates", {})
    engine_rejection_gate = (
        generic_safety.get(
            "engine_rejected_action_rate",
            {}).get("passed")
        is True)
    policy_limited = (
        treatment["authority"][
            "row_count"] > 0
        and set(
            treatment["authority"][
                "operation_types"])
        <= set(declared_types)
        and set(
            treatment["authority"][
                "action_types"])
        <= set(
            "unit_fortify"
            if operation_type
            == "fortify_existing_defender"
            else "unit_move"
            for operation_type in
            declared_types)
        and set(
            treatment["authority"][
                "policy_authority_values"])
        == {"True"})
    latency_gate = bool(
        isinstance(
            preparation_ceiling,
            (int, float))
        and treatment[
            "preparation_latency_ms"][
                "p95"] is not None
        and treatment[
            "preparation_latency_ms"][
                "p95"]
        <= float(
            preparation_ceiling)
        and isinstance(
            full_loop_ratio_ceiling,
            (int, float))
        and full_loop_ratio
        is not None
        and full_loop_ratio
        <= float(
            full_loop_ratio_ceiling))
    typed_gate = bool(
        isinstance(
            minimum_typed_coverage,
            (int, float))
        and treatment[
            "typed_winner_changing_coverage"][
                "row_count"] > 0
        and treatment[
            "typed_winner_changing_coverage"][
                "coverage"] is not None
        and treatment[
            "typed_winner_changing_coverage"][
                "coverage"]
        >= float(
            minimum_typed_coverage))
    gates = {
        "city_loss_not_increased":
            city_loss_delta <= 0,
        "hard_current_reservation_conflicts_zero":
            (
                not baseline[
                    "hard_current_reservation_conflicts"]
                and not treatment[
                    "hard_current_reservation_conflicts"]),
        "legality_violations_zero":
            (
                engine_rejection_gate
                and (
                    corrected_observation_metrics
                    or treatment[
                        "event_counts"].get(
                            "operation_failed", 0)
                    == 0)),
        "lower_uncovered_threat_turns_than_b1":
            uncovered_delta < 0,
        "planning_latency_within_predeclared_bounds":
            latency_gate,
        "policy_authority_limited_to_declared_operation_types":
            policy_limited,
        "positive_operation_completion_delta":
            (
                completion_delta is not None
                and completion_delta > 0.0),
        "sole_defender_violations_zero":
            not treatment[
                "sole_defender_violations"],
        "source_freeze_passed":
            bool(aggregate.get(
                "source_freeze", {}).get(
                    "passed")),
        "trace_validation_passed":
            validation[
                "error_count"] == 0,
        "typed_winner_changing_coverage_at_least_predeclared_minimum":
            typed_gate,
        "unsupported_states_have_zero_policy_authority":
            not treatment[
                "unsupported_authority"],
    }
    purpose = aggregate.get(
        "design", {}).get(
            "cohort_purpose")
    pilot_gate_passed = (
        purpose == "pilot"
        and design is not None
        and all(gates.values()))
    result = {
        "arms": arm_results,
        "authority": {
            "claim_status": (
                "bounded-mechanism-pilot"
                if purpose == "pilot"
                else "diagnostic-only"),
            "policy_authority_eligible":
                pilot_gate_passed,
            "score_claim_eligible":
                False,
        },
        "cohort": {
            "aggregate_path":
                os.path.relpath(
                    aggregate_path,
                    cohort_root),
            "aggregate_sha256":
                _sha256_file(
                    aggregate_path),
            "complete_pairs":
                aggregate.get(
                    "complete_pairs"),
            "configuration_hash":
                aggregate.get(
                    "configuration_hash"),
            "id": cohort,
            "primary_score_delta":
                aggregate.get(
                    "primary_outcome"),
            "purpose": purpose,
            "source_freeze":
                aggregate.get(
                    "source_freeze"),
        },
        "deltas": {
            "city_loss_count":
                city_loss_delta,
            "raw_city_loss_count":
                raw_city_loss_delta,
            "completion_rate_per_selection":
                completion_delta,
            "full_loop_p95_ratio":
                full_loop_ratio,
            "uncovered_threat_turns":
                uncovered_delta,
        },
        "gates": gates,
        "pilot_gate_passed":
            pilot_gate_passed,
        "predeclared_mechanism_design": {
            "design": design,
            "present":
                design is not None,
        },
        "report_schema_version": (
            "1.1"
            if corrected_observation_metrics
            else "1.0"),
        "trace_sources": trace_sources,
        "trace_validation": {
            "error_count":
                validation[
                    "error_count"],
            "event_count":
                validation[
                    "event_count"],
            "valid":
                validation[
                    "error_count"] == 0,
            "warning_count":
                validation[
                    "warning_count"],
        },
    }
    result["report_hash"] = (
        structural_hash(result))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cohort-root",
        required=True)
    parser.add_argument(
        "--output",
        required=True)
    parser.add_argument(
        "--profile",
        default=os.path.join(
            REPO,
            "profile",
            "freeciv_harness.yaml"))
    args = parser.parse_args()
    result = run(
        os.path.abspath(
            args.cohort_root),
        os.path.abspath(
            args.profile))
    output = os.path.abspath(
        args.output)
    os.makedirs(
        os.path.dirname(output),
        exist_ok=True)
    with open(
            output, "w",
            encoding="utf-8") as stream:
        json.dump(
            result, stream,
            sort_keys=True,
            indent=2)
        stream.write("\n")
    print(json.dumps({
        "output": output,
        "pilot_gate_passed":
            result[
                "pilot_gate_passed"],
        "report_hash":
            result[
                "report_hash"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
