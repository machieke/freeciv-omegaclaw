"""Independent, inspectable Stage-0 flow-control reference model.

This module deliberately does not import the live flow-control package.  It
models the scientific risks in small deterministic fixtures where every route
attribute and intermediate score can be inspected.
"""

import math
import random
import time
from dataclasses import dataclass, replace


SYNTHETIC_FAMILIES = (
    "two_corridor_positive_feedback",
    "long_path_stable",
    "long_path_changing",
    "or_packet_thresholds",
    "and_zero_gradient_blocker",
    "tree",
    "dag",
    "cyclic",
    "disconnected_distractors",
    "asymmetric_backward_legality",
    "measured_service_bottleneck",
    "allocated_shaping_capacities",
    "dynamic_edge_failures",
    "stale_topology",
    "evidence_acquisition_selection_bias",
    "resource_conversion_reservation_fragmentation",
)

BASELINE_NAMES = (
    "uniform_random_expansion",
    "forward_only_best_first",
    "backward_only_best_first",
    "tuned_bidirectional_heuristic",
    "strong_smoothed_scalar",
    "diffusion_only_attention",
    "scalar_probe_pheromone",
    "bridge_scoring_without_flow",
    "electrical_flow_routing",
    "aco_style_reinforcement",
    "gflownet_trajectory_balance",
    "exact_integer_packet_oracle",
)

ABLATION_NAMES = (
    "scalar_pf_v1",
    "scalar_pf_v2",
    "scalar_pf_v2_plus_packets",
    "explicit_bridge_without_probes",
    "corrected_probes",
    "uncorrected_probes",
    "scalar_pheromone",
    "path_currents_without_pf_typing",
    "pf_bridge_scalar_packet_scheduler",
    "source_sink_projection_without_advection",
    "continuous_advection_without_packet_gates",
    "advection_plus_packet_gates",
    "capacities_without_provenance",
    "capacities_with_provenance",
    "full_multi_goal_controller",
)


@dataclass(frozen=True)
class ReferenceRoute:
    route_id: str
    typed_value: float
    generic_conductance: float
    estimated_forward: float
    corrected_forward: float
    current_forward: float
    backward_relevance: float
    packet_cost: int
    allocated_capacity: int
    capacity_kind: str
    requirement_complete: bool
    legal_forward: bool
    legal_backward: bool
    dynamic_alive: bool
    cross_goal_harm: float
    corridor_length: int

    @property
    def actual_complete(self):
        capacity = (
            self.allocated_capacity
            if self.capacity_kind in (
                "measured", "allocated")
            else 10 ** 9)
        return bool(
            self.legal_forward
            and self.legal_backward
            and self.dynamic_alive
            and self.requirement_complete
            and self.current_forward >= 0.5
            and self.backward_relevance >= 0.5
            and self.packet_cost <= capacity)

    @property
    def realized_value(self):
        if not self.actual_complete:
            return 0.0
        return max(
            0.0,
            self.typed_value - 0.10
            - self.cross_goal_harm)


@dataclass(frozen=True)
class ReferenceCase:
    case_id: str
    family: str
    seed: int
    split: str
    routes: tuple


def _bounded(value):
    return max(0.0, min(1.0, float(value)))


def _route(
        route_id, typed, estimated, corrected, current,
        backward, packet_cost=1, capacity=1,
        capacity_kind="allocated", requirement=True,
        legal_forward=True, legal_backward=True,
        dynamic_alive=True, harm=0.0, corridor=6,
        conductance=None):
    return ReferenceRoute(
        route_id=route_id,
        typed_value=float(typed),
        generic_conductance=_bounded(
            estimated if conductance is None
            else conductance),
        estimated_forward=_bounded(estimated),
        corrected_forward=_bounded(corrected),
        current_forward=_bounded(current),
        backward_relevance=_bounded(backward),
        packet_cost=int(packet_cost),
        allocated_capacity=int(capacity),
        capacity_kind=str(capacity_kind),
        requirement_complete=bool(requirement),
        legal_forward=bool(legal_forward),
        legal_backward=bool(legal_backward),
        dynamic_alive=bool(dynamic_alive),
        cross_goal_harm=_bounded(harm),
        corridor_length=int(corridor))


def _case(family, seed, split):
    rng = random.Random(seed)
    jitter = lambda width: rng.uniform(-width, width)
    good = _route(
        "good", 1.00 + jitter(0.04),
        0.88 + jitter(0.03),
        0.90 + jitter(0.02),
        0.92 + jitter(0.02),
        0.90 + jitter(0.02),
        corridor=(
            24 if family.startswith("long_path")
            else 8))
    lure = _route(
        "lure", 1.18 + jitter(0.04),
        0.22 + jitter(0.04),
        0.10 + jitter(0.02),
        0.06 + jitter(0.02),
        0.90 + jitter(0.02),
        conductance=0.92 + jitter(0.03))
    alternate = _route(
        "alternate", 0.78 + jitter(0.03),
        0.72 + jitter(0.04),
        0.76 + jitter(0.03),
        0.78 + jitter(0.03),
        0.72 + jitter(0.03),
        corridor=5)

    if family == "two_corridor_positive_feedback":
        lure = _route(
            "lure", 1.20 + jitter(0.03),
            0.80, 0.12, 0.08, 0.90,
            conductance=0.98)
    elif family == "long_path_changing":
        lure = _route(
            "lure", 1.24, 0.95, 0.88, 0.04, 0.92,
            dynamic_alive=False, corridor=20,
            conductance=0.96)
    elif family == "or_packet_thresholds":
        good = _route(
            "good", 1.22, 0.94, 0.94, 0.94, 0.93,
            packet_cost=2, capacity=1)
    elif family == "and_zero_gradient_blocker":
        lure = _route(
            "lure", 1.26, 0.94, 0.94, 0.94, 0.94,
            requirement=False, conductance=0.95)
    elif family == "tree":
        lure = _route(
            "lure", 1.16, 0.15, 0.08, 0.05, 0.88,
            legal_forward=False)
    elif family == "dag":
        alternate = _route(
            "alternate", 0.86, 0.82, 0.84, 0.85, 0.82)
    elif family == "cyclic":
        lure = _route(
            "lure", 1.19, 0.75, 0.10, 0.05, 0.90,
            conductance=0.99)
    elif family == "disconnected_distractors":
        lure = _route(
            "lure", 1.30, 0.10, 0.04, 0.0, 0.95,
            legal_forward=False, conductance=0.97)
    elif family == "asymmetric_backward_legality":
        lure = _route(
            "lure", 1.24, 0.94, 0.94, 0.94, 0.05,
            legal_backward=False)
    elif family == "measured_service_bottleneck":
        good = _route(
            "good", 1.25, 0.95, 0.95, 0.95, 0.94,
            packet_cost=2, capacity=1,
            capacity_kind="measured")
    elif family == "allocated_shaping_capacities":
        good = _route(
            "good", 1.10, 0.94, 0.94, 0.94, 0.94,
            packet_cost=1, capacity=0,
            capacity_kind="shaping")
        alternate = _route(
            "alternate", 0.76, 0.78, 0.78, 0.78, 0.78,
            capacity_kind="allocated")
    elif family == "dynamic_edge_failures":
        lure = _route(
            "lure", 1.28, 0.97, 0.92, 0.03, 0.94,
            dynamic_alive=False, conductance=0.98)
    elif family == "stale_topology":
        lure = _route(
            "lure", 1.27, 0.96, 0.90, 0.02, 0.93,
            legal_forward=False, conductance=0.98)
    elif family == "evidence_acquisition_selection_bias":
        lure = _route(
            "lure", 1.23, 0.96, 0.08, 0.05, 0.92,
            conductance=0.96)
    elif family == (
            "resource_conversion_reservation_fragmentation"):
        good = _route(
            "good", 1.24, 0.94, 0.94, 0.94, 0.93,
            packet_cost=2, capacity=1, harm=0.15)
        alternate = _route(
            "alternate", 0.88, 0.82, 0.82, 0.82, 0.82,
            packet_cost=1, capacity=1, harm=0.0)

    # Preserve nontrivial outcome variance. Some held-out seeds make the
    # scalar-preferred route genuinely useful, while a disjoint stratum has
    # no completable route for any controller or oracle.
    if (seed % 5 == 0
            and family not in (
                "long_path_changing",
                "dynamic_edge_failures",
                "stale_topology")):
        lure = replace(
            lure,
            estimated_forward=0.90,
            corrected_forward=0.88,
            current_forward=0.88,
            packet_cost=1,
            allocated_capacity=1,
            capacity_kind="allocated",
            requirement_complete=True,
            legal_forward=True,
            legal_backward=True,
            dynamic_alive=True)
    if seed % 11 == 0:
        good = replace(good, dynamic_alive=False)
        lure = replace(lure, dynamic_alive=False)
        alternate = replace(
            alternate, dynamic_alive=False)

    routes = [good, lure, alternate]
    rng.shuffle(routes)
    routes = tuple(
        ReferenceRoute(
            route_id="{}:{}:{}".format(
                family, seed, row.route_id),
            typed_value=row.typed_value,
            generic_conductance=row.generic_conductance,
            estimated_forward=row.estimated_forward,
            corrected_forward=row.corrected_forward,
            current_forward=row.current_forward,
            backward_relevance=row.backward_relevance,
            packet_cost=row.packet_cost,
            allocated_capacity=row.allocated_capacity,
            capacity_kind=row.capacity_kind,
            requirement_complete=row.requirement_complete,
            legal_forward=row.legal_forward,
            legal_backward=row.legal_backward,
            dynamic_alive=row.dynamic_alive,
            cross_goal_harm=row.cross_goal_harm,
            corridor_length=row.corridor_length)
        for row in routes)
    return ReferenceCase(
        case_id="{}:{}:{}".format(
            family, split, seed),
        family=family,
        seed=seed,
        split=split,
        routes=routes)


def build_cohort(split, seeds_per_family):
    if split not in ("train", "heldout"):
        raise ValueError("reference split must be train or heldout")
    seeds_per_family = int(seeds_per_family)
    if seeds_per_family < 1:
        raise ValueError("seeds per family must be positive")
    offset = 200000 if split == "heldout" else 0
    return tuple(
        _case(
            family,
            offset + family_index * 1000 + index,
            split)
        for family_index, family in enumerate(
            SYNTHETIC_FAMILIES)
        for index in range(seeds_per_family))


def _select(case, score, gate=lambda row: True):
    admissible = [
        row for row in case.routes if gate(row)]
    if not admissible:
        admissible = list(case.routes)
    return max(
        admissible,
        key=lambda row: (
            float(score(row)), row.route_id))


def _packet_gate(row, provenance=True):
    capacity = (
        row.allocated_capacity
        if (row.capacity_kind in (
            "measured", "allocated")
            or not provenance)
        else 10 ** 9)
    return bool(
        row.requirement_complete
        and row.packet_cost <= capacity)


def selector_registry(seed=991):
    randomizer = random.Random(seed)

    def random_selection(case):
        return case.routes[
            randomizer.randrange(len(case.routes))]

    def flow_score(row):
        return (
            row.typed_value - row.cross_goal_harm
            + 2.0 * row.current_forward
            * row.backward_relevance
            - 0.01 * row.corridor_length)

    return {
        "uniform_random_expansion": random_selection,
        "forward_only_best_first": lambda case: _select(
            case, lambda row: row.estimated_forward),
        "backward_only_best_first": lambda case: _select(
            case, lambda row: row.backward_relevance),
        "tuned_bidirectional_heuristic": lambda case: _select(
            case, lambda row: (
                row.estimated_forward
                * row.backward_relevance)),
        "strong_smoothed_scalar": lambda case: _select(
            case, lambda row: row.typed_value),
        "diffusion_only_attention": lambda case: _select(
            case, lambda row: (
                row.corrected_forward
                + row.backward_relevance)),
        "scalar_probe_pheromone": lambda case: _select(
            case, lambda row: (
                row.typed_value
                + row.generic_conductance)),
        "bridge_scoring_without_flow": lambda case: _select(
            case, lambda row: (
                row.typed_value
                + 2.0 * row.corrected_forward
                * row.backward_relevance)),
        "electrical_flow_routing": lambda case: _select(
            case, lambda row: min(
                row.corrected_forward,
                row.backward_relevance)),
        "aco_style_reinforcement": lambda case: _select(
            case, lambda row: (
                row.generic_conductance ** 2
                * max(0.01, row.estimated_forward))),
        "gflownet_trajectory_balance": lambda case: _select(
            case, lambda row: (
                math.exp(row.typed_value)
                * row.corrected_forward
                * row.backward_relevance)),
        "exact_integer_packet_oracle": lambda case: _select(
            case, lambda row: row.realized_value,
            gate=lambda row: row.actual_complete),
        "scalar_pf_v1": lambda case: _select(
            case, lambda row: (
                row.typed_value
                + row.generic_conductance)),
        "scalar_pf_v2": lambda case: _select(
            case, lambda row: row.typed_value),
        "scalar_pf_v2_plus_packets": lambda case: _select(
            case, lambda row: row.typed_value,
            gate=lambda row: _packet_gate(row)),
        "explicit_bridge_without_probes": lambda case: _select(
            case, lambda row: (
                row.typed_value
                + row.estimated_forward
                * row.backward_relevance)),
        "corrected_probes": lambda case: _select(
            case, lambda row: (
                row.typed_value
                + 2.0 * row.corrected_forward
                * row.backward_relevance)),
        "uncorrected_probes": lambda case: _select(
            case, lambda row: (
                row.typed_value
                + 2.0 * row.estimated_forward
                * row.backward_relevance)),
        "scalar_pheromone": lambda case: _select(
            case, lambda row: (
                row.typed_value
                + row.generic_conductance)),
        "path_currents_without_pf_typing": lambda case: _select(
            case, lambda row: (
                row.current_forward
                * row.backward_relevance)),
        "pf_bridge_scalar_packet_scheduler": lambda case: _select(
            case, lambda row: (
                row.typed_value
                + 2.0 * row.corrected_forward
                * row.backward_relevance),
            gate=lambda row: _packet_gate(row)),
        "source_sink_projection_without_advection": lambda case: _select(
            case, lambda row: (
                row.typed_value
                + row.current_forward
                * row.backward_relevance)),
        "continuous_advection_without_packet_gates": (
            lambda case: _select(case, flow_score)),
        "advection_plus_packet_gates": lambda case: _select(
            case, flow_score,
            gate=lambda row: _packet_gate(row)),
        "capacities_without_provenance": lambda case: _select(
            case, flow_score,
            gate=lambda row: _packet_gate(
                row, provenance=False)),
        "capacities_with_provenance": lambda case: _select(
            case, flow_score,
            gate=lambda row: _packet_gate(
                row, provenance=True)),
        "full_multi_goal_controller": lambda case: _select(
            case, flow_score,
            gate=lambda row: (
                _packet_gate(row, provenance=True)
                and row.legal_forward
                and row.legal_backward
                and row.dynamic_alive
                and row.current_forward >= 0.5
                and row.backward_relevance >= 0.5)),
    }


def evaluate_selector(cases, selector):
    selections = tuple(selector(case) for case in cases)
    completions = tuple(
        int(row.actual_complete) for row in selections)
    return {
        "case_count": len(cases),
        "complete_packets": sum(completions),
        "completion_rate": (
            sum(completions) / float(len(cases))
            if cases else 0.0),
        "false_corridor_allocations": sum(
            1 - value for value in completions),
        "mean_realized_value": (
            sum(row.realized_value for row in selections)
            / float(len(cases))
            if cases else 0.0),
        "mean_relaxed_mass": (
            sum(
                row.corrected_forward
                * row.backward_relevance
                for row in selections)
            / float(len(cases))
            if cases else 0.0),
        "selected_route_ids": tuple(
            row.route_id for row in selections),
    }


def reference_invariants():
    projection_cases = []
    for length in (2, 4, 16, 64):
        current = [1.0] * (length - 1)
        divergence = [0.0] * length
        for index, value in enumerate(current):
            divergence[index] += value
            divergence[index + 1] -= value
        projection_cases.append({
            "length": length,
            "maximum_balance_error": max(
                abs(value - target)
                for value, target in zip(
                    divergence,
                    (1.0,) + (0.0,) * (length - 2)
                    + (-1.0,))),
            "nonzero_tree_route": any(current),
        })
    transport_cases = []
    for length in (4, 8, 32):
        masses = [0.0] * length
        masses[0] = 1.0
        before = sum(masses)
        for _ in range(length):
            prior = list(masses)
            fluxes = [
                0.5 * prior[index]
                for index in range(length - 1)]
            for index, flux in enumerate(fluxes):
                masses[index] -= flux
                masses[index + 1] += flux
        transport_cases.append({
            "length": length,
            "mass_error": sum(masses) - before,
            "minimum_mass": min(masses),
        })
    valid = all(
        row["maximum_balance_error"] <= 1e-12
        and row["nonzero_tree_route"]
        for row in projection_cases) and all(
            abs(row["mass_error"]) <= 1e-12
            and row["minimum_mass"] >= 0.0
            for row in transport_cases)
    return {
        "mass_cases": transport_cases,
        "projection_cases": projection_cases,
        "valid": valid,
    }


def _recovery(parameters):
    false_mass = 0.80
    correct_mass = 0.20
    failure_turn = 2
    recovered = None
    threshold = (
        0.50 + 0.04
        * (parameters["packet_quantum"] - 1))
    for turn in range(24):
        false_stimulus = 1.0 if turn < failure_turn else 0.0
        correct_stimulus = (
            parameters["turnover"]
            / (1.0 + parameters["corridor_length"] / 12.0))
        false_next = (
            parameters["decay"] * false_mass
            + parameters["deposit_gain"]
            * false_stimulus * false_mass
            + parameters["current_following_gain"]
            * false_mass * 0.20)
        correct_next = (
            parameters["decay"] * correct_mass
            + correct_stimulus
            + parameters["diffusion"]
            + 0.04 * parameters["temperature"])
        denominator = max(
            1e-12, false_next + correct_next)
        false_mass = false_next / denominator
        correct_mass = correct_next / denominator
        if (turn >= failure_turn
                and correct_mass >= threshold
                and recovered is None):
            recovered = turn - failure_turn
    return {
        "false_corridor_fixed_point": (
            recovered is None),
        "recovered": recovered is not None,
        "recovery_turns": recovered,
        "terminal_correct_mass": correct_mass,
    }


def stability_map():
    grid = {
        "deposit_gain": (0.2, 1.2),
        "current_following_gain": (0.1, 0.9),
        "decay": (0.5, 0.95),
        "temperature": (0.1, 1.0),
        "diffusion": (0.0, 0.2),
        "turnover": (0.1, 0.8),
        "packet_quantum": (1, 3),
        "corridor_length": (4, 24),
    }
    names = tuple(grid)
    rows = []

    def visit(index, values):
        if index == len(names):
            parameters = dict(zip(names, values))
            result = _recovery(parameters)
            rows.append(dict(parameters, **result))
            return
        for value in grid[names[index]]:
            visit(index + 1, values + (value,))

    visit(0, ())
    stable = [row for row in rows if row["recovered"]]
    unstable = [row for row in rows if not row["recovered"]]
    selected = min(
        stable,
        key=lambda row: (
            row["recovery_turns"],
            row["deposit_gain"],
            row["current_following_gain"],
            -row["diffusion"],
            -row["turnover"],
            row["corridor_length"]))
    return {
        "grid": dict(
            (name, list(values))
            for name, values in grid.items()),
        "rows": rows,
        "selected_region": dict(
            (name, selected[name]) for name in names),
        "stable_count": len(stable),
        "unstable_count": len(unstable),
    }


def transport_latency(repetitions=10):
    repetitions = max(1, int(repetitions))
    rows = []
    checksum = 0.0
    for length in (4, 8, 16, 32, 64, 128):
        started = time.perf_counter()
        edge_updates = 0
        for _ in range(repetitions):
            mass = [0.0] * length
            mass[0] = 1.0
            for _ in range(length):
                prior = list(mass)
                for index in range(length - 1):
                    flux = 0.25 * prior[index]
                    mass[index] -= flux
                    mass[index + 1] += flux
                    edge_updates += 1
            checksum += sum(mass)
        elapsed = time.perf_counter() - started
        rows.append({
            "corridor_length": length,
            "edge_updates": edge_updates,
            "mean_microseconds_per_run": (
                elapsed * 1000000.0 / repetitions),
            "microseconds_per_edge_update": (
                elapsed * 1000000.0 / edge_updates),
            "total_seconds": elapsed,
        })
    return {
        "checksum": checksum,
        "repetitions": repetitions,
        "rows": rows,
    }
