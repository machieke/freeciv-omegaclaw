"""Held-out synthetic conductance-versus-bridge experiment for Gate G3."""

import math
import random
import time

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.pressure import (
    ScalarRouteBid,
    SmoothedScalarController,
)


GRAPH_FAMILIES = (
    "useful_but_unreachable_prerequisite",
    "reachable_but_irrelevant_branch",
    "long_corridor_with_distractors",
    "and_coalition_one_unreachable",
    "or_alternatives_forward_feasibility",
    "dynamic_edge_failure",
    "hidden_observation_unlock",
    "context_specific_conductance_transfer",
    "freeciv_historical_route_changed_legality",
)

ARM_NAMES = (
    "scalar_generic_conductance",
    "scalar_context_conductance",
    "explicit_bridge",
    "calibrated_conductance_bridge_fusion",
    "bridge_shuffled_forward",
    "bridge_shuffled_backward",
    "conductance_shuffled_values",
    "bridge_only_without_pf_typing",
    "oracle_forward_reachability",
    "learned_forward_predictor",
)


def _clamp(value):
    return max(1e-6, min(1.0 - 1e-6, float(value)))


def _case(family, seed, split):
    rng = random.Random(seed)
    viable = seed % 3
    unreachable = (viable + 1) % 3
    irrelevant = (viable + 2) % 3
    candidates = []
    for index in range(3):
        role = (
            "viable" if index == viable
            else "unreachable" if index == unreachable
            else "irrelevant")
        advantage = (
            0.78 + rng.uniform(-0.05, 0.05)
            if role == "viable"
            else 0.96 + rng.uniform(-0.03, 0.03)
            if role == "unreachable"
            else 0.72 + rng.uniform(-0.05, 0.05))
        oracle_forward = (
            0.90 + rng.uniform(-0.04, 0.04)
            if role == "viable"
            else 0.04 + rng.uniform(0.0, 0.04)
            if role == "unreachable"
            else 0.91 + rng.uniform(-0.04, 0.04))
        backward = (
            0.90 + rng.uniform(-0.04, 0.04)
            if role in ("viable", "unreachable")
            else 0.05 + rng.uniform(0.0, 0.05))
        generic = (
            0.88 + rng.uniform(-0.06, 0.06)
            if role == "unreachable"
            else 0.60 + rng.uniform(-0.08, 0.08)
            if role == "viable"
            else 0.55 + rng.uniform(-0.08, 0.08))
        context_recovers = (
            (seed + GRAPH_FAMILIES.index(family)) % 5 < 3)
        contextual = (
            0.82 + rng.uniform(-0.05, 0.05)
            if role == "viable" and context_recovers
            else 0.76 + rng.uniform(-0.06, 0.06)
            if role == "unreachable" and not context_recovers
            else 0.58 + rng.uniform(-0.10, 0.10))
        deadline = (
            0.92 + rng.uniform(-0.04, 0.04)
            if role == "viable"
            else 0.75 + rng.uniform(-0.10, 0.10))
        if family == "long_corridor_with_distractors":
            oracle_forward *= (
                0.72 if role == "viable" else 0.85)
        elif family == "and_coalition_one_unreachable":
            if role == "unreachable":
                oracle_forward = 0.01 + rng.uniform(0.0, 0.01)
        elif family == "or_alternatives_forward_feasibility":
            if role == "irrelevant":
                oracle_forward = 0.96 + rng.uniform(-0.02, 0.02)
                backward = 0.92 + rng.uniform(-0.02, 0.02)
                advantage = 0.35 + rng.uniform(-0.03, 0.03)
        elif family == "dynamic_edge_failure":
            if role == "unreachable":
                generic = 0.96
                contextual = 0.90
        elif family == "hidden_observation_unlock":
            if role == "viable":
                advantage = 0.70
                contextual = 0.50
        elif family == "context_specific_conductance_transfer":
            if role == "unreachable":
                generic = 0.97
                contextual = 0.84
        elif family == (
                "freeciv_historical_route_changed_legality"):
            if role == "unreachable":
                generic = 0.99
                contextual = 0.88
                oracle_forward = 1e-6
        estimated_forward = _clamp(
            oracle_forward + rng.uniform(-0.06, 0.06))
        compatibility = _clamp(
            0.88 + rng.uniform(-0.08, 0.08))
        resolvability = _clamp(
            0.86 + rng.uniform(-0.08, 0.08))
        success = _clamp(
            0.90 + rng.uniform(-0.05, 0.05))
        cost = 0.08 + rng.uniform(0.0, 0.06)
        risk = 0.02 + rng.uniform(0.0, 0.04)
        completion = bool(
            oracle_forward >= 0.5
            and backward >= 0.5
            and deadline >= 0.5)
        realized_relief = (
            max(0.0, advantage - cost - risk)
            * oracle_forward * backward
            * deadline * success
            if completion else 0.0)
        candidates.append({
            "advantage": advantage,
            "backward": _clamp(backward),
            "candidate_id": "{}:{}:{}".format(
                family, seed, index),
            "compatibility": compatibility,
            "completion": completion,
            "contextual_conductance": _clamp(contextual),
            "cost": cost,
            "deadline": _clamp(deadline),
            "estimated_forward": estimated_forward,
            "generic_conductance": _clamp(generic),
            "index": index,
            "oracle_forward": _clamp(oracle_forward),
            "realized_relief": realized_relief,
            "resolvability": resolvability,
            "risk": risk,
            "role": role,
            "success": success,
        })
    best = max(
        candidates,
        key=lambda row: (
            row["realized_relief"],
            row["candidate_id"]))
    return {
        "case_id": "{}:{}:{}".format(family, split, seed),
        "candidates": tuple(candidates),
        "family": family,
        "seed": seed,
        "split": split,
        "target_candidate_id": best["candidate_id"],
    }


def _cohort(split, seeds_per_family):
    offset = 100000 if split == "heldout" else 0
    return tuple(
        _case(
            family,
            offset + family_index * 1000 + index,
            split)
        for family_index, family in enumerate(GRAPH_FAMILIES)
        for index in range(seeds_per_family))


def _operation_score(row):
    return (
        row["advantage"]
        - row["cost"] - row["risk"])


def _select(case, score):
    return max(
        case["candidates"],
        key=lambda row: (
            float(score(row)),
            row["candidate_id"]))


def _accuracy(cases, score):
    return sum(
        _select(case, score)["completion"]
        for case in cases) / float(len(cases))


def _fit_weight(cases, feature):
    weights = (
        0.0, 0.125, 0.25, 0.5,
        1.0, 1.5, 2.0, 3.0, 4.0)
    return max(
        weights,
        key=lambda weight: (
            _accuracy(
                cases,
                lambda row: (
                    _operation_score(row)
                    + weight * feature(row))),
            -weight))


def _fit_fusion(cases):
    weights = (0.0, 0.25, 0.5, 1.0, 2.0)
    return max(
        ((conductance, bridge)
         for conductance in weights
         for bridge in weights),
        key=lambda pair: (
            _accuracy(
                cases,
                lambda row: (
                    _operation_score(row)
                    + pair[0]
                    * row["contextual_conductance"]
                    + pair[1]
                    * row["estimated_forward"]
                    * row["backward"]
                    * row["compatibility"])),
            -sum(pair)))


def _fit_forward_predictor(cases):
    rows = tuple(
        candidate for case in cases
        for candidate in case["candidates"])
    coefficients = [0.0] * 7
    rate = 0.08
    for _ in range(600):
        gradient = [0.0] * len(coefficients)
        for row in rows:
            features = (
                1.0,
                row["generic_conductance"],
                row["contextual_conductance"],
                row["compatibility"],
                row["resolvability"],
                row["deadline"],
                row["success"],
            )
            linear = sum(
                value * feature for value, feature
                in zip(coefficients, features))
            predicted = 1.0 / (
                1.0 + math.exp(
                    -max(-30.0, min(30.0, linear))))
            error = (
                predicted - row["oracle_forward"])
            for index, feature in enumerate(features):
                gradient[index] += error * feature
        scale = rate / len(rows)
        coefficients = [
            value - scale * gradient[index]
            for index, value in enumerate(coefficients)]
    return tuple(coefficients)


def _predict_forward(row, coefficients):
    features = (
        1.0,
        row["generic_conductance"],
        row["contextual_conductance"],
        row["compatibility"],
        row["resolvability"],
        row["deadline"],
        row["success"],
    )
    linear = sum(
        value * feature for value, feature
        in zip(coefficients, features))
    return 1.0 / (
        1.0 + math.exp(
            -max(-30.0, min(30.0, linear))))


def _shuffled(cases, field, seed):
    rng = random.Random(seed)
    values = [
        row[field] for case in cases
        for row in case["candidates"]]
    rng.shuffle(values)
    lookup = {}
    index = 0
    for case in cases:
        for row in case["candidates"]:
            lookup[row["candidate_id"]] = values[index]
            index += 1
    return lookup


def _arm_scores(train, heldout):
    generic_weight = _fit_weight(
        train, lambda row: row["generic_conductance"])
    context_weight = _fit_weight(
        train, lambda row: row["contextual_conductance"])
    bridge_weight = _fit_weight(
        train,
        lambda row: (
            row["estimated_forward"]
            * row["backward"]
            * row["compatibility"]))
    fusion_weights = _fit_fusion(train)
    coefficients = _fit_forward_predictor(train)
    shuffled_forward = _shuffled(
        heldout, "estimated_forward", 7001)
    shuffled_backward = _shuffled(
        heldout, "backward", 7002)
    shuffled_conductance = _shuffled(
        heldout, "contextual_conductance", 7003)
    scores = {
        "scalar_generic_conductance": lambda row: (
            _operation_score(row)
            + generic_weight * row["generic_conductance"]),
        "scalar_context_conductance": lambda row: (
            _operation_score(row)
            + context_weight
            * row["contextual_conductance"]),
        "explicit_bridge": lambda row: (
            _operation_score(row)
            + bridge_weight
            * row["estimated_forward"]
            * row["backward"]
            * row["compatibility"]),
        "calibrated_conductance_bridge_fusion": lambda row: (
            _operation_score(row)
            + fusion_weights[0]
            * row["contextual_conductance"]
            + fusion_weights[1]
            * row["estimated_forward"]
            * row["backward"]
            * row["compatibility"]),
        "bridge_shuffled_forward": lambda row: (
            _operation_score(row)
            + bridge_weight
            * shuffled_forward[row["candidate_id"]]
            * row["backward"]
            * row["compatibility"]),
        "bridge_shuffled_backward": lambda row: (
            _operation_score(row)
            + bridge_weight
            * row["estimated_forward"]
            * shuffled_backward[row["candidate_id"]]
            * row["compatibility"]),
        "conductance_shuffled_values": lambda row: (
            _operation_score(row)
            + context_weight
            * shuffled_conductance[row["candidate_id"]]),
        "bridge_only_without_pf_typing": lambda row: (
            row["estimated_forward"]
            * row["backward"]
            * row["compatibility"]),
        "oracle_forward_reachability": lambda row: (
            _operation_score(row)
            + bridge_weight
            * row["oracle_forward"]
            * row["backward"]
            * row["compatibility"]),
        "learned_forward_predictor": lambda row: (
            _operation_score(row)
            + bridge_weight
            * _predict_forward(row, coefficients)
            * row["backward"]
            * row["compatibility"]),
    }
    tuning = {
        "bridge_weight": bridge_weight,
        "context_weight": context_weight,
        "forward_predictor_coefficients": list(
            coefficients),
        "fusion_weights": {
            "bridge": fusion_weights[1],
            "conductance": fusion_weights[0],
        },
        "generic_weight": generic_weight,
    }
    return scores, tuning


def _arm_metrics(cases, score):
    selections = tuple(
        _select(case, score) for case in cases)
    return {
        "complete_packets_before_deadline": sum(
            row["completion"] for row in selections),
        "completion_rate": sum(
            row["completion"] for row in selections)
        / float(len(selections)),
        "false_corridor_allocations": sum(
            not row["completion"] for row in selections),
        "candidate_invalidation_rate": sum(
            not row["completion"] for row in selections)
        / float(len(selections)),
        "expensive_rule_or_simulator_calls": sum(
            row["role"] == "unreachable"
            for row in selections),
        "mean_verified_goal_loss_relief": sum(
            row["realized_relief"] for row in selections)
        / float(len(selections)),
        "selected_candidate_hash": structural_hash([
            row["candidate_id"] for row in selections]),
    }


def _strong_scalar_equivalent(cases, score):
    for case in cases:
        expected = _select(case, score)["candidate_id"]
        controller = SmoothedScalarController()
        decision = controller.rank(tuple(
            ScalarRouteBid(
                row["candidate_id"],
                float(score(row)))
            for row in case["candidates"]), step=0)
        if decision.selected_route_id != expected:
            return False
    return True


def _paired_interval(cases, left, right, seed=991):
    differences = [
        int(_select(case, left)["completion"])
        - int(_select(case, right)["completion"])
        for case in cases]
    rng = random.Random(seed)
    bootstrap = []
    for _ in range(4000):
        bootstrap.append(sum(
            differences[
                rng.randrange(len(differences))]
            for _ in differences) / float(len(differences)))
    bootstrap.sort()
    wins = sum(value > 0 for value in differences)
    losses = sum(value < 0 for value in differences)
    discordant = wins + losses
    if discordant:
        smaller = min(wins, losses)
        probability = min(1.0, 2.0 * sum(
            math.comb(discordant, index)
            for index in range(smaller + 1))
            / float(2 ** discordant))
    else:
        probability = 1.0
    return {
        "bootstrap_95_ci": [
            bootstrap[int(0.025 * len(bootstrap))],
            bootstrap[int(0.975 * len(bootstrap))],
        ],
        "losses": losses,
        "mean_paired_completion_lift": (
            sum(differences) / float(len(differences))),
        "two_sided_exact_sign_p": probability,
        "wins": wins,
    }


def _conditional_mutual_information(cases):
    counts = {}
    total = 0
    for case in cases:
        for row in case["candidates"]:
            existing = (
                int(row["contextual_conductance"] >= 0.65),
                int(row["advantage"] >= 0.80),
                int(row["backward"] >= 0.5),
                int(row["deadline"] >= 0.8),
            )
            forward = int(row["estimated_forward"] >= 0.5)
            outcome = int(row["completion"])
            counts[(existing, forward, outcome)] = (
                counts.get(
                    (existing, forward, outcome), 0) + 1)
            total += 1
    by_x = {}
    for (existing, forward, outcome), count in counts.items():
        group = by_x.setdefault(existing, {
            "count": 0, "f": {}, "y": {}, "fy": {}})
        group["count"] += count
        group["f"][forward] = (
            group["f"].get(forward, 0) + count)
        group["y"][outcome] = (
            group["y"].get(outcome, 0) + count)
        group["fy"][(forward, outcome)] = (
            group["fy"].get(
                (forward, outcome), 0) + count)
    result = 0.0
    for group in by_x.values():
        for (forward, outcome), count in (
                group["fy"].items()):
            numerator = count * group["count"]
            denominator = (
                group["f"][forward]
                * group["y"][outcome])
            result += (
                count / float(total)
                * math.log(
                    numerator / float(denominator), 2))
    return result


def _bridge_calibration(cases):
    rows = []
    for case in cases:
        for row in case["candidates"]:
            prediction = _clamp(
                row["estimated_forward"]
                * row["backward"]
                * row["deadline"])
            rows.append((
                prediction, int(row["completion"])))
    brier = sum(
        (prediction - outcome) ** 2
        for prediction, outcome in rows) / len(rows)
    bins = []
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        group = [
            row for row in rows
            if lower <= row[0] < lower + 0.2]
        if group:
            bins.append({
                "count": len(group),
                "mean_observed": sum(
                    row[1] for row in group)
                / float(len(group)),
                "mean_predicted": sum(
                    row[0] for row in group)
                / float(len(group)),
                "range": [lower, lower + 0.2],
            })
    return {
        "bins": bins,
        "brier_score": brier,
        "claim_eligible": False,
        "synthetic_gate_eligible": True,
        "scope": "held-out synthetic graph packets only",
    }


def run_g3_bridge_experiment(
        train_seeds_per_family=64,
        heldout_seeds_per_family=64,
        timing_repetitions=20):
    train = _cohort(
        "train", int(train_seeds_per_family))
    heldout = _cohort(
        "heldout", int(heldout_seeds_per_family))
    scores, tuning = _arm_scores(train, heldout)
    metrics = dict(
        (name, _arm_metrics(heldout, scores[name]))
        for name in ARM_NAMES)
    timing = {}
    repetitions = max(1, int(timing_repetitions))
    for name in ARM_NAMES:
        started = time.perf_counter()
        for _ in range(repetitions):
            for case in heldout:
                _select(case, scores[name])
        seconds = time.perf_counter() - started
        timing[name] = {
            "candidate_evaluations": (
                repetitions * len(heldout) * 3),
            "mean_microseconds_per_case": (
                seconds * 1000000.0
                / repetitions / len(heldout)),
            "total_seconds": seconds,
        }
    comparisons = {
        "bridge_vs_context_conductance": _paired_interval(
            heldout, scores["explicit_bridge"],
            scores["scalar_context_conductance"]),
        "bridge_vs_generic_conductance": _paired_interval(
            heldout, scores["explicit_bridge"],
            scores["scalar_generic_conductance"],
            seed=992),
        "bridge_vs_shuffled_forward": _paired_interval(
            heldout, scores["explicit_bridge"],
            scores["bridge_shuffled_forward"],
            seed=993),
        "bridge_vs_shuffled_backward": _paired_interval(
            heldout, scores["explicit_bridge"],
            scores["bridge_shuffled_backward"],
            seed=994),
    }
    family_metrics = {}
    for family in GRAPH_FAMILIES:
        subset = tuple(
            case for case in heldout
            if case["family"] == family)
        family_metrics[family] = {
            "context_completion_rate": _arm_metrics(
                subset,
                scores["scalar_context_conductance"])[
                    "completion_rate"],
            "explicit_bridge_completion_rate": _arm_metrics(
                subset, scores["explicit_bridge"])[
                    "completion_rate"],
        }
    primary = comparisons[
        "bridge_vs_context_conductance"]
    report = {
        "arms": metrics,
        "bridge_calibration": _bridge_calibration(
            heldout),
        "claim_status": (
            "synthetic-control-evidence-only;"
            "not-a-FreeCiv-gameplay-score-claim"),
        "comparisons": comparisons,
        "conditional_mutual_information_bits": (
            _conditional_mutual_information(heldout)),
        "controller_inclusive_timing": timing,
        "fixed_compute_contract": {
            "candidate_evaluations_per_case": 3,
            "candidate_sets_identical": True,
            "operation_score_fields_identical": True,
            "packet_completion_rule_identical": True,
            "scope": (
                "ranking-kernel timing; final G3 additionally "
                "requires live graph/probe/controller overhead"),
        },
        "family_metrics": family_metrics,
        "graph_families": list(GRAPH_FAMILIES),
        "heldout": {
            "case_count": len(heldout),
            "cohort_hash": structural_hash([
                case["case_id"] for case in heldout]),
            "seed_range": [
                min(case["seed"] for case in heldout),
                max(case["seed"] for case in heldout),
            ],
        },
        "primary_metric": (
            "complete operation packets before deadline"),
        "preregistered_primary_comparison": (
            "explicit_bridge versus "
            "scalar_context_conductance"),
        "schema_version": "1.0",
        "strong_smoothed_scalar_baseline": {
            "arm": "scalar_context_conductance",
            "controller_identity": (
                SmoothedScalarController.SOLVER_IDENTITY),
            "first_step_selection_equivalent": (
                _strong_scalar_equivalent(
                    heldout,
                    scores["scalar_context_conductance"])),
            "independent_query_state_reset": True,
        },
        "training": {
            "case_count": len(train),
            "cohort_hash": structural_hash([
                case["case_id"] for case in train]),
            "seed_range": [
                min(case["seed"] for case in train),
                max(case["seed"] for case in train),
            ],
            "tuning": tuning,
        },
    }
    report["valid"] = all((
        set(report["arms"]) == set(ARM_NAMES),
        set(report["graph_families"])
        == set(GRAPH_FAMILIES),
        report["training"]["cohort_hash"]
        != report["heldout"]["cohort_hash"],
        primary["bootstrap_95_ci"][0] > 0.0,
        primary["two_sided_exact_sign_p"] < 0.05,
        comparisons["bridge_vs_shuffled_forward"][
            "mean_paired_completion_lift"] > 0.0,
        comparisons["bridge_vs_shuffled_backward"][
            "mean_paired_completion_lift"] > 0.0,
        metrics["explicit_bridge"][
            "mean_verified_goal_loss_relief"]
        > metrics["bridge_only_without_pf_typing"][
            "mean_verified_goal_loss_relief"],
        report["conditional_mutual_information_bits"] > 0.0,
        report["strong_smoothed_scalar_baseline"][
            "first_step_selection_equivalent"],
    ))
    report["verification_hash"] = structural_hash(dict(
        (key, value) for key, value in report.items()
        if key != "controller_inclusive_timing"))
    return report
