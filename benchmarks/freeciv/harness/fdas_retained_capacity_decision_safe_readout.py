"""Frozen feasibility audit for retained-capacity decision-safe readout."""

import hashlib
import json

from freeciv_agent.events.schema import canonical_json_bytes, structural_hash
from freeciv_agent.planning import (
    FdasRetainedCapacityTransitionModel,
    PR100_RETAINED_CAPACITY_CONFIRMATION_HASH,
    PR100_RETAINED_CAPACITY_CONFIRMATION_SHA256,
    RETAINED_CAPACITY_DECISION_SAFE_READOUT_IDENTITY,
)


READOUT_FEASIBILITY_IDENTITY = (
    "fdas-retained-capacity-decision-safe-readout-feasibility/1.0")


def _sha256(value):
    return hashlib.sha256(canonical_json_bytes(value) + b"\n").hexdigest()


def _contains_nonselected_outcome_role(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if (key in ("selection_role", "assignment_role")
                    and isinstance(item, str)
                    and "nonselected" in item.lower()):
                return True
            if _contains_nonselected_outcome_role(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_nonselected_outcome_role(item) for item in value)
    return False


def audit_fdas_retained_capacity_decision_safe_readout(
        model_report, confirmation_report):
    """Determine whether the frozen selected-action model can compare."""
    if not isinstance(model_report, dict) or not isinstance(
            confirmation_report, dict):
        raise TypeError("retained capacity feasibility inputs must be mappings")
    model = FdasRetainedCapacityTransitionModel.from_dict(
        model_report["model"])
    confirmation_hash = confirmation_report.get("structural_hash")
    confirmation_sha = _sha256(confirmation_report)
    confirmation_source_valid = bool(
        confirmation_hash == PR100_RETAINED_CAPACITY_CONFIRMATION_HASH
        and confirmation_sha == PR100_RETAINED_CAPACITY_CONFIRMATION_SHA256
        and confirmation_report.get("acceptance", {}).get("accepted") is True
        and confirmation_report.get("confirmation_ready") is True
        and confirmation_report.get("model", {}).get("model_result_hash")
            == model.result_hash
        and confirmation_report.get("model", {}).get("refitted") is False)

    usable = {}
    for value in model.bins:
        if not value.numerically_usable:
            continue
        key = (value.level, value.feature_values)
        usable.setdefault(key, {})[value.target] = value
    groups = []
    for (level, features), targets in sorted(usable.items()):
        product = targets.get("exact-product-effect")
        relief = targets.get("durable-goal-relief")
        if product is None or relief is None:
            continue
        groups.append({
            "feature_values": dict(features),
            "level": level,
            "product_effect": {
                "bin_id": product.bin_id,
                "estimate": product.estimate,
                "independent_games": product.independent_games,
                "interval_lower": product.interval_lower,
                "interval_upper": product.interval_upper,
            },
            "goal_relief": {
                "bin_id": relief.bin_id,
                "estimate": relief.estimate,
                "independent_games": relief.independent_games,
                "interval_lower": relief.interval_lower,
                "interval_upper": relief.interval_upper,
            },
        })

    ordered_pairs = []
    separated = []
    decision_safe = []
    for baseline in groups:
        for alternative in groups:
            if baseline is alternative:
                continue
            relief_separated = bool(
                alternative["goal_relief"]["interval_lower"]
                > baseline["goal_relief"]["interval_upper"])
            product_noninferior = bool(
                alternative["product_effect"]["interval_lower"]
                >= baseline["product_effect"]["interval_lower"])
            row = {
                "alternative_goal_relief_bin_id": (
                    alternative["goal_relief"]["bin_id"]),
                "alternative_product_effect_bin_id": (
                    alternative["product_effect"]["bin_id"]),
                "baseline_goal_relief_bin_id": (
                    baseline["goal_relief"]["bin_id"]),
                "baseline_product_effect_bin_id": (
                    baseline["product_effect"]["bin_id"]),
                "decision_safe_interval_pair": bool(
                    relief_separated and product_noninferior),
                "product_lower_bound_noninferior": product_noninferior,
                "relief_intervals_strictly_separated": relief_separated,
            }
            ordered_pairs.append(row)
            if relief_separated:
                separated.append(row)
            if row["decision_safe_interval_pair"]:
                decision_safe.append(row)

    nonselected_outcomes_confirmed = bool(
        _contains_nonselected_outcome_role(model_report)
        and _contains_nonselected_outcome_role(confirmation_report))
    checks = {
        "at_least_one_decision_safe_interval_pair": bool(decision_safe),
        "at_least_one_strict_relief_interval_pair": bool(separated),
        "at_least_two_usable_joint_target_bins": len(groups) >= 2,
        "frozen_pr99_model_is_exact_and_typed": model.result_hash == (
            "909e8170d9dc797f69b71337243633ddd5fd5e007a7627c44e150d0a05439a6f"),
        "frozen_pr100_confirmation_is_exact_and_accepted": (
            confirmation_source_valid),
        "nonselected_candidate_outcomes_are_confirmed": (
            nonselected_outcomes_confirmed),
    }
    progression_ready = all(checks.values())
    semantic = {
        "acceptance": {
            "accepted": True,
            "checks": {
                "all_ordered_pairs_are_retained": len(ordered_pairs)
                    == len(groups) * max(0, len(groups) - 1),
                "all_truth_policy_readout_and_action_authority_disabled": True,
                "frozen_sources_are_valid": bool(
                    checks["frozen_pr99_model_is_exact_and_typed"]
                    and confirmation_source_valid),
            },
        },
        "action_authority": False,
        "candidate_surface_changed": False,
        "decision": "ready-for-shadow-opportunity-cohort"
            if progression_ready else "not-ready",
        "feasibility": {
            "checks": checks,
            "decision_safe_interval_pairs": decision_safe,
            "joint_usable_target_bins": groups,
            "ordered_pair_checks": ordered_pairs,
            "strict_relief_interval_pairs": separated,
        },
        "identity": READOUT_FEASIBILITY_IDENTITY,
        "model": {
            "model_result_hash": model.result_hash,
            "refitted": False,
        },
        "policy_authority": False,
        "pressure_selection_changed": False,
        "readout_authority": False,
        "readout_identity": RETAINED_CAPACITY_DECISION_SAFE_READOUT_IDENTITY,
        "source": {
            "confirmation_report_sha256": confirmation_sha,
            "confirmation_structural_hash": confirmation_hash,
        },
        "summary": {
            "decision_safe_interval_pairs": len(decision_safe),
            "joint_usable_target_bins": len(groups),
            "nonselected_outcomes_confirmed": nonselected_outcomes_confirmed,
            "ordered_pair_checks": len(ordered_pairs),
            "strict_relief_interval_pairs": len(separated),
        },
        "truth_mutated": False,
    }
    semantic["acceptance"]["accepted"] = all(
        semantic["acceptance"]["checks"].values())
    return {**semantic, "structural_hash": structural_hash(semantic)}


def load_and_audit_fdas_retained_capacity_decision_safe_readout(
        model_path, confirmation_path):
    with open(model_path, encoding="utf-8") as stream:
        model = json.load(stream)
    with open(confirmation_path, encoding="utf-8") as stream:
        confirmation = json.load(stream)
    return audit_fdas_retained_capacity_decision_safe_readout(
        model, confirmation)
