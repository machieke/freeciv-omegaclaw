"""Held-out calibration and decision-safe readout ablation.

This benchmark is intentionally mechanism-scoped.  Synthetic results may
promote a stage to engine diagnostics, but cannot support a gameplay claim.
"""

import copy
import math
import random
import tempfile
import time

from freeciv.pf_unified.v2_benchmark import run_v2_verification
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.flow_control import DecisionSafeCandidateSelector
from freeciv_agent.pressure import (
    ScalarBaselineConfig,
    ScalarRouteBid,
    SmoothedScalarController,
    TransitionValueKey,
    TransitionValueModel,
    TransitionValueObservation,
)


FROZEN_PREDECESSOR = "242fd25"
TRAIN_SAMPLES_PER_KEY = 64
HELDOUT_SAMPLES_PER_KEY = 32
CALIBRATION_MINIMUM_SAMPLES = 30
CALIBRATION_MAXIMUM_HALF_WIDTH = 0.36
CALIBRATION_ALPHA = 0.05

_CATEGORIES = ("expansion", "defense", "economy")
_LIFECYCLES = (
    "terminal-completion",
    "route-progress",
    "production-commitment",
)
_GOALS = (
    "pf-impact:expansion",
    "pf-impact:survival",
    "pf-impact:economy",
)


def _clamp(value):
    return min(1.0, max(0.0, float(value)))


def _keys():
    return tuple(
        TransitionValueKey(category, lifecycle, goal)
        for category in _CATEGORIES
        for lifecycle in _LIFECYCLES
        for goal in _GOALS)


def _seed(key, sample, split):
    return int(structural_hash({
        "key": key.to_dict(),
        "sample": int(sample),
        "split": str(split),
    })[:16], 16)


def _calibration_row(key, sample, split):
    rng = random.Random(_seed(key, sample, split))
    raw = rng.uniform(0.16, 0.78)
    category_bias = {
        "expansion": -0.18,
        "defense": 0.12,
        "economy": -0.10,
    }[key.action_category]
    lifecycle_bias = {
        "terminal-completion": 0.10,
        "route-progress": -0.08,
        "production-commitment": 0.12,
    }[key.lifecycle_state]
    goal_bias = {
        "pf-impact:expansion": 0.05,
        "pf-impact:survival": -0.04,
        "pf-impact:economy": 0.0,
    }[key.goal_id]
    realized = _clamp(
        raw + category_bias + lifecycle_bias
        + goal_bias + rng.gauss(0.0, 0.035))
    return raw, realized


def _model(path, read_only=False):
    return TransitionValueModel(
        path=path,
        identity="transition-readout-heldout-v1",
        minimum_samples=CALIBRATION_MINIMUM_SAMPLES,
        maximum_half_width=CALIBRATION_MAXIMUM_HALF_WIDTH,
        alpha=CALIBRATION_ALPHA,
        read_only=read_only)


def _train_model(path):
    model = _model(path)
    observations = []
    for key in _keys():
        for sample in range(TRAIN_SAMPLES_PER_KEY):
            raw, realized = _calibration_row(
                key, sample, "train")
            observation_id = structural_hash({
                "key": key.to_dict(),
                "sample": sample,
                "split": "train",
            })
            observations.append(TransitionValueObservation(
                observation_id=observation_id,
                key=key,
                predicted_relief=raw,
                realized_relief=realized,
                effect_observed=True,
                relief_source=(
                    "authoritative:synthetic-heldout-protocol"),
                context_digest=structural_hash({
                    "case": observation_id,
                    "semantic_epoch": 1,
                }),
                selection_propensity=1.0))
    model.observe_many(observations)
    return model


def _evaluate_calibration(model):
    raw_absolute_error = []
    calibrated_absolute_error = []
    calibrated_squared_error = []
    covered = 0
    calibrated = 0
    rows = 0
    minimum_count = None
    maximum_half_width = 0.0
    for key in _keys():
        for sample in range(HELDOUT_SAMPLES_PER_KEY):
            raw, realized = _calibration_row(
                key, sample, "heldout")
            estimate = model.estimate(key, raw)
            rows += 1
            raw_absolute_error.append(
                abs(raw - realized))
            calibrated_absolute_error.append(
                abs(
                    estimate.expected_realized_relief
                    - realized))
            calibrated_squared_error.append(
                (
                    estimate.expected_realized_relief
                    - realized) ** 2)
            covered += (
                estimate.lower_bound <= realized
                <= estimate.upper_bound)
            calibrated += estimate.calibrated
            minimum_count = (
                estimate.sample_count
                if minimum_count is None
                else min(
                    minimum_count,
                    estimate.sample_count))
            maximum_half_width = max(
                maximum_half_width,
                estimate.confidence_half_width)
    raw_mae = (
        sum(raw_absolute_error)
        / len(raw_absolute_error))
    calibrated_mae = (
        sum(calibrated_absolute_error)
        / len(calibrated_absolute_error))
    result = {
        "authority_rate": calibrated / float(rows),
        "calibrated_mae": calibrated_mae,
        "calibrated_rmse": math.sqrt(
            sum(calibrated_squared_error)
            / len(calibrated_squared_error)),
        "heldout_rows": rows,
        "interval_coverage": covered / float(rows),
        "mae_improvement": raw_mae - calibrated_mae,
        "maximum_confidence_half_width":
            maximum_half_width,
        "minimum_exact_support": minimum_count,
        "raw_mae": raw_mae,
        "split_contract": (
            "disjoint deterministic train/heldout seeds; "
            "exact category+lifecycle+goal support only"),
    }
    result["mechanism_gate_pass"] = bool(
        result["mae_improvement"] >= 0.02
        and result["interval_coverage"] >= 0.90
        and result["authority_rate"] == 1.0
        and result["minimum_exact_support"]
        >= CALIBRATION_MINIMUM_SAMPLES
        and result["maximum_confidence_half_width"]
        <= CALIBRATION_MAXIMUM_HALF_WIDTH)
    return result


def _calibration_experiment():
    with tempfile.TemporaryDirectory(
            prefix="freeciv-transition-value-") as directory:
        path = "{}/model.json".format(directory)
        trained = _train_model(path)
        trained_hash = trained.state_hash
        frozen = _model(path, read_only=True)
        result = _evaluate_calibration(frozen)
        replay = _model(path, read_only=True)
        replay_result = _evaluate_calibration(replay)
        result.update({
            "frozen_model_read_only":
                frozen.read_only,
            "model_state_hash": frozen.state_hash,
            "replay_byte_exact": (
                result == replay_result
                and frozen.state_hash == replay.state_hash
                and trained_hash == frozen.state_hash),
            "training_observations":
                trained.decision_snapshot()[
                    "observation_count"],
            "update_scope": "control-model-only",
        })
        result["mechanism_gate_pass"] = bool(
            result["mechanism_gate_pass"]
            and result["frozen_model_read_only"]
            and result["replay_byte_exact"])
        return result


def _readout_experiment(cases=300):
    selector = DecisionSafeCandidateSelector()
    scalar_hits = 0
    deterministic_hits = 0
    probe_hits = 0
    terminal_protected = 0
    safety_protected = 0
    started = time.perf_counter()
    for case in range(int(cases)):
        target = "case-{}:target".format(case)
        ordinary = tuple(
            "case-{}:ordinary-{}".format(case, index)
            for index in range(4))
        terminal = "case-{}:terminal".format(case)
        safety = "case-{}:safety".format(case)
        if case % 4 == 0:
            scalar = (
                (target,) + ordinary
                + (terminal, safety))
        else:
            scalar = (
                ordinary[:3] + (target,)
                + ordinary[3:]
                + (terminal, safety))
        available = scalar
        scalar_union = selector.select(
            scalar, available,
            terminal_operation_ids=(terminal,),
            safety_operation_ids=(safety,),
            scalar_top_k=3,
            readout_policy="protected-message-union")
        deterministic_bridge = (
            (target,) if case % 5 != 0 else ())
        deterministic_union = selector.select(
            scalar, available,
            bridge_operation_ids=deterministic_bridge,
            terminal_operation_ids=(terminal,),
            safety_operation_ids=(safety,),
            scalar_top_k=3,
            readout_policy="protected-message-union")
        corrected_probe = (
            (target,)
            if deterministic_bridge
            or case % 13 != 0 else ())
        probe_union = selector.select(
            scalar, available,
            bridge_operation_ids=corrected_probe,
            terminal_operation_ids=(terminal,),
            safety_operation_ids=(safety,),
            scalar_top_k=3,
            readout_policy="corrected-probe-union")
        scalar_hits += target in scalar_union.operation_ids
        deterministic_hits += (
            target in deterministic_union.operation_ids)
        probe_hits += target in probe_union.operation_ids
        terminal_protected += (
            terminal in probe_union.operation_ids)
        safety_protected += (
            safety in probe_union.operation_ids)
    elapsed_ms = (
        time.perf_counter() - started) * 1000.0
    scalar_recall = scalar_hits / float(cases)
    deterministic_recall = (
        deterministic_hits / float(cases))
    probe_recall = probe_hits / float(cases)

    founding = "historical:found-city"
    founding_union = selector.select(
        (
            "historical:move-a",
            "historical:move-b",
            "historical:produce",
            founding,
        ),
        (
            "historical:move-a",
            "historical:move-b",
            "historical:produce",
            founding,
        ),
        terminal_operation_ids=(founding,),
        scalar_top_k=3,
        readout_policy="protected-message-union")
    result = {
        "cases": int(cases),
        "corrected_probe_recall": probe_recall,
        "corrected_probe_recall_gain":
            probe_recall - deterministic_recall,
        "deterministic_bridge_recall":
            deterministic_recall,
        "deterministic_bridge_recall_gain":
            deterministic_recall - scalar_recall,
        "historical_founding_candidate_protected":
            founding in founding_union.operation_ids,
        "mean_case_latency_ms":
            elapsed_ms / float(cases),
        "safety_protection_rate":
            safety_protected / float(cases),
        "scalar_top_k_recall": scalar_recall,
        "terminal_protection_rate":
            terminal_protected / float(cases),
    }
    result["ct2_mechanism_gate_pass"] = bool(
        result["deterministic_bridge_recall_gain"]
        >= 0.15
        and result[
            "historical_founding_candidate_protected"]
        and result["terminal_protection_rate"] == 1.0
        and result["safety_protection_rate"] == 1.0)
    result["ct3_mechanism_gate_pass"] = bool(
        result["ct2_mechanism_gate_pass"]
        and result["corrected_probe_recall_gain"]
        >= 0.05)
    return result


def _persistence_experiment(traces=64, steps=80):
    scalar_switches = 0
    persistent_switches = 0
    selected_regret = []
    retained = 0
    started = time.perf_counter()
    for trace in range(int(traces)):
        controller = SmoothedScalarController(
            ScalarBaselineConfig(
                smoothing=0.25,
                route_momentum=0.10,
                minimum_dwell_steps=3,
                dwell_bonus=0.015,
                switch_margin=0.012,
                diversity_floor=0.10))
        prior_scalar = None
        prior_persistent = None
        for step in range(int(steps)):
            rng = random.Random(
                trace * 100000 + step)
            phase = (trace + step) % 2
            left = (
                0.511 if phase == 0 else 0.500)
            right = (
                0.500 if phase == 0 else 0.511)
            left += rng.uniform(-0.0008, 0.0008)
            right += rng.uniform(-0.0008, 0.0008)
            scalar = (
                "left" if left >= right else "right")
            decision = controller.rank((
                ScalarRouteBid("left", left),
                ScalarRouteBid("right", right),
            ), step)
            persistent = decision.selected_route_id
            if (prior_scalar is not None
                    and scalar != prior_scalar):
                scalar_switches += 1
            if (prior_persistent is not None
                    and persistent != prior_persistent):
                persistent_switches += 1
            retained += (
                decision.retained_by_dwell
                or decision.retained_by_hysteresis)
            selected = (
                left if persistent == "left"
                else right)
            selected_regret.append(
                max(left, right) - selected)
            prior_scalar = scalar
            prior_persistent = persistent
    elapsed_ms = (
        time.perf_counter() - started) * 1000.0
    switch_reduction = (
        1.0 - persistent_switches
        / float(max(1, scalar_switches)))
    result = {
        "decisions": int(traces) * int(steps),
        "maximum_priority_regret":
            max(selected_regret or (0.0,)),
        "mean_decision_latency_ms":
            elapsed_ms / float(
                max(1, int(traces) * int(steps))),
        "mean_priority_regret":
            sum(selected_regret)
            / float(max(1, len(selected_regret))),
        "persistent_switches":
            persistent_switches,
        "retained_by_dwell_or_hysteresis":
            retained,
        "scalar_switches": scalar_switches,
        "switch_reduction": switch_reduction,
    }
    result["offline_mechanism_gate_pass"] = bool(
        switch_reduction >= 0.50
        and result["maximum_priority_regret"] <= 0.05)
    result["engine_gameplay_gate_pass"] = False
    result["engine_gameplay_gate_reason"] = (
        "paired engine diagnostic has not completed")
    return result


def run_transition_readout_experiment(
        readout_cases=300,
        persistence_traces=64,
        persistence_steps=80):
    """Run CT0–CT4 offline gates and explicitly hold CT5 closed."""
    scalar_verification = run_v2_verification()
    calibration = _calibration_experiment()
    readout = _readout_experiment(readout_cases)
    persistence = _persistence_experiment(
        persistence_traces,
        persistence_steps)
    semantic = {
        "baseline": {
            "frozen_predecessor":
                FROZEN_PREDECESSOR,
            "identity": (
                "scalar-pf-v2+whole-operation-packets"),
            "verification": scalar_verification,
        },
        "ct1_calibrated_scalar":
            calibration,
        "ct2_ct3_candidate_recall":
            readout,
        "ct4_path_persistence":
            persistence,
        "ct5_source_sink_entry": {
            "entry_gate_pass": False,
            "reason": (
                "CT4 paired engine diagnostic and route-allocation "
                "error attribution are still required"),
        },
        "evaluation_scope": (
            "synthetic mechanism and captured-snapshot replay; "
            "claim-ineligible for FreeCiv score or win rate"),
        "schema_version": "1.0",
    }
    semantic["offline_valid"] = bool(
        scalar_verification["valid"]
        and calibration["mechanism_gate_pass"]
        and readout["ct2_mechanism_gate_pass"]
        and readout["ct3_mechanism_gate_pass"]
        and persistence["offline_mechanism_gate_pass"]
        and not semantic[
            "ct5_source_sink_entry"][
                "entry_gate_pass"])
    hash_material = copy.deepcopy(semantic)
    hash_material[
        "ct2_ct3_candidate_recall"].pop(
            "mean_case_latency_ms")
    hash_material[
        "ct4_path_persistence"].pop(
            "mean_decision_latency_ms")
    semantic["semantic_hash"] = structural_hash(
        hash_material)
    return semantic
