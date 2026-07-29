"""Conservative two-dye attention transport on asymmetric legal graphs."""

import math
import time
from dataclasses import dataclass

from ..events.schema import structural_hash
from .model import FlowProcess, FlowView
from .projection import ProjectionResult


def _finite_nonnegative(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(
            "{} must be finite and non-negative".format(name))
    return value


@dataclass(frozen=True)
class ReservationMass:
    reservation_id: str
    mass: float
    operation_id: object = None
    requirement_set_id: object = None

    def __post_init__(self):
        if not isinstance(self.reservation_id, str) or not self.reservation_id:
            raise ValueError(
                "reservation mass requires an ID")
        _finite_nonnegative(
            self.mass, "reservation mass")
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.requirement_set_id, "requirement-set ID")):
            if value is not None and (
                    not isinstance(value, str) or not value):
                raise ValueError(
                    "{} must be nonempty when present".format(name))

    def to_dict(self):
        return {
            "mass": float(self.mass),
            "operation_id": self.operation_id,
            "requirement_set_id": self.requirement_set_id,
            "reservation_id": self.reservation_id,
        }


@dataclass(frozen=True)
class PacketReservationLedger:
    entries: tuple = ()

    def __post_init__(self):
        if any(not isinstance(row, ReservationMass)
               for row in self.entries):
            raise TypeError(
                "reservation ledger requires ReservationMass")
        identities = [row.reservation_id for row in self.entries]
        if len(identities) != len(set(identities)):
            raise ValueError(
                "reservation mass IDs must be unique")

    @property
    def total_mass(self):
        return sum(float(row.mass) for row in self.entries)

    def to_dict(self):
        return {
            "entries": [
                row.to_dict() for row in self.entries],
            "total_mass": float(self.total_mass),
        }


@dataclass(frozen=True)
class AttentionState:
    node_ids: tuple
    forward_mass: tuple
    backward_mass: tuple
    reservoir_mass: dict
    inflight_mass: dict
    reservations: PacketReservationLedger

    def __post_init__(self):
        if (len(self.node_ids) != len(self.forward_mass)
                or len(self.node_ids) != len(self.backward_mass)):
            raise ValueError(
                "attention node and dye arrays must align")
        if (len(set(self.node_ids)) != len(self.node_ids)
                or any(not isinstance(value, str) or not value
                       for value in self.node_ids)):
            raise ValueError(
                "attention node IDs must be unique")
        for values, name in (
                (self.forward_mass, "forward attention"),
                (self.backward_mass, "backward attention")):
            for value in values:
                _finite_nonnegative(value, name)
        for values, name in (
                (self.reservoir_mass, "reservoir mass"),
                (self.inflight_mass, "in-flight mass")):
            if not isinstance(values, dict):
                raise TypeError(
                    "{} must be a dictionary".format(name))
            copied = {}
            for key, value in values.items():
                if not isinstance(key, str) or not key:
                    raise ValueError(
                        "{} IDs must be nonempty".format(name))
                copied[key] = _finite_nonnegative(value, name)
            object.__setattr__(self, (
                "reservoir_mass"
                if name == "reservoir mass"
                else "inflight_mass"), copied)
        if not isinstance(
                self.reservations, PacketReservationLedger):
            raise TypeError(
                "attention reservations require ledger")

    @property
    def forward_total(self):
        return sum(float(value) for value in self.forward_mass)

    @property
    def backward_total(self):
        return sum(float(value) for value in self.backward_mass)

    @property
    def accounted_total(self):
        return (
            self.forward_total + self.backward_total
            + sum(self.reservoir_mass.values())
            + sum(self.inflight_mass.values())
            + self.reservations.total_mass)

    @property
    def state_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "accounted_total": float(self.accounted_total),
            "backward_mass": [
                float(value) for value in self.backward_mass],
            "backward_total": float(self.backward_total),
            "forward_mass": [
                float(value) for value in self.forward_mass],
            "forward_total": float(self.forward_total),
            "inflight_mass": dict(sorted(
                (key, float(value))
                for key, value in self.inflight_mass.items())),
            "node_ids": list(self.node_ids),
            "reservations": self.reservations.to_dict(),
            "reservoir_mass": dict(sorted(
                (key, float(value))
                for key, value in self.reservoir_mass.items())),
        }


@dataclass(frozen=True)
class AdvectionStepResult:
    state: AttentionState
    overlap: tuple
    overlap_peak_node_id: object
    total_mass_before: float
    total_mass_after: float
    mass_error: float
    raw_local_cfl: float
    applied_velocity_scale: float
    cfl_rescaled: bool
    positivity_corrections: int
    correction_mass: float
    forward_edges_used: tuple
    backward_edges_used: tuple
    edge_updates: int
    elapsed_ms: float
    health: str

    def __post_init__(self):
        if len(self.overlap) != len(self.state.node_ids):
            raise ValueError(
                "overlap must align with attention nodes")
        for value, name in (
                (self.total_mass_before, "mass before"),
                (self.total_mass_after, "mass after"),
                (self.raw_local_cfl, "local CFL"),
                (self.applied_velocity_scale,
                 "velocity scale"),
                (self.correction_mass, "correction mass"),
                (self.elapsed_ms, "elapsed time")):
            _finite_nonnegative(value, name)
        if not math.isfinite(float(self.mass_error)):
            raise ValueError("mass error must be finite")
        if self.applied_velocity_scale > 1.0:
            raise ValueError(
                "advection may only scale velocity down")
        if self.positivity_corrections < 0 or self.edge_updates < 0:
            raise ValueError(
                "advection counts must be non-negative")

    @property
    def healthy(self):
        return self.health == "healthy"

    @property
    def result_hash(self):
        # Timing is deliberately excluded from scientific replay identity.
        material = self.to_dict()
        material.pop("elapsed_ms")
        return structural_hash(material)

    def to_dict(self):
        return {
            "applied_velocity_scale": float(
                self.applied_velocity_scale),
            "backward_edges_used": list(
                self.backward_edges_used),
            "cfl_rescaled": self.cfl_rescaled,
            "correction_mass": float(
                self.correction_mass),
            "edge_updates": self.edge_updates,
            "elapsed_ms": float(self.elapsed_ms),
            "forward_edges_used": list(
                self.forward_edges_used),
            "health": self.health,
            "mass_error": float(self.mass_error),
            "overlap": [
                float(value) for value in self.overlap],
            "overlap_peak_node_id": (
                self.overlap_peak_node_id),
            "positivity_corrections": (
                self.positivity_corrections),
            "raw_local_cfl": float(self.raw_local_cfl),
            "state": self.state.to_dict(),
            "total_mass_after": float(
                self.total_mass_after),
            "total_mass_before": float(
                self.total_mass_before),
        }


@dataclass(frozen=True)
class TransportRun:
    final_state: AttentionState
    steps: tuple
    microsteps: int
    corridor_length: int
    edge_updates: int
    wall_ms: float

    @property
    def microseconds_per_edge_update(self):
        if self.edge_updates <= 0:
            return 0.0
        return 1000.0 * self.wall_ms / self.edge_updates

    def to_dict(self):
        return {
            "corridor_length": self.corridor_length,
            "edge_updates": self.edge_updates,
            "final_state": self.final_state.to_dict(),
            "microseconds_per_edge_update": float(
                self.microseconds_per_edge_update),
            "microsteps": self.microsteps,
            "wall_ms": float(self.wall_ms),
        }


class TwoDyeAdvectionKernel:
    """Explicit conservative donor-cell transport with a graph CFL gate."""

    KERNEL_IDENTITY = "pf-two-dye-advection/1.0"

    def __init__(
            self, cfl_limit=0.9, alpha=0.5,
            epsilon=1e-12, correction_tolerance=1e-12,
            maximum_corrections=2):
        self.cfl_limit = float(cfl_limit)
        if not 0.0 < self.cfl_limit <= 1.0:
            raise ValueError(
                "CFL limit must be in (0, 1]")
        self.alpha = float(alpha)
        if not math.isfinite(self.alpha) or self.alpha <= 0.0:
            raise ValueError(
                "overlap alpha must be positive")
        self.epsilon = _finite_nonnegative(
            epsilon, "overlap epsilon")
        self.correction_tolerance = _finite_nonnegative(
            correction_tolerance,
            "positivity correction tolerance")
        if (isinstance(maximum_corrections, bool)
                or not isinstance(maximum_corrections, int)
                or maximum_corrections < 0):
            raise ValueError(
                "maximum corrections must be non-negative")
        self.maximum_corrections = maximum_corrections

    @staticmethod
    def _field(view, values):
        edge_ids = tuple(row.stable_id for row in view.edges)
        if isinstance(values, ProjectionResult):
            if values.edge_ids != edge_ids:
                raise ValueError(
                    "projected field is not aligned with view")
            values = values.feasible_current
        elif isinstance(values, dict):
            unknown = set(values) - set(edge_ids)
            if unknown:
                raise ValueError(
                    "advection field references unknown edge")
            values = tuple(
                float(values.get(edge_id, 0.0))
                for edge_id in edge_ids)
        else:
            values = tuple(float(value) for value in values)
            if len(values) != len(edge_ids):
                raise ValueError(
                    "advection field must align with edges")
        if any(not math.isfinite(value) or value < 0.0
               for value in values):
            raise ValueError(
                "directed advection velocity must be "
                "finite and non-negative")
        return tuple(values)

    @staticmethod
    def _node_order(view, state):
        node_ids = tuple(
            row.stable_id
            for row in sorted(
                view.nodes, key=lambda row: row.local_id))
        if state.node_ids != node_ids:
            raise ValueError(
                "attention state is not aligned with flow view")
        return dict(
            (value, index)
            for index, value in enumerate(node_ids))

    @staticmethod
    def _legal_field(view, values, process):
        return tuple(
            value if edge.legality.allows(process) else 0.0
            for edge, value in zip(view.edges, values))

    @staticmethod
    def _local_cfl(
            view, values, legality, diffusion, delta_time,
            node_index):
        outgoing = [0.0] * len(node_index)
        degree = [0] * len(node_index)
        for edge, value, legal in zip(
                view.edges, values, legality):
            if not legal:
                continue
            if value <= 0.0 and diffusion <= 0.0:
                continue
            source = node_index[edge.source_node_id]
            target = node_index[edge.target_node_id]
            outgoing[source] += value
            if diffusion > 0.0:
                degree[source] += 1
                degree[target] += 1
        return max((
            delta_time * (
                outgoing[index]
                + diffusion * degree[index])
            for index in range(len(node_index))),
            default=0.0)

    @staticmethod
    def _transport(
            view, mass, values, legality, diffusion,
            delta_time, scale, node_index):
        updated = [float(value) for value in mass]
        edge_updates = 0
        used = []
        for edge, raw_velocity, legal in zip(
                view.edges, values, legality):
            if not legal:
                continue
            velocity = raw_velocity * scale
            if velocity <= 0.0 and diffusion <= 0.0:
                continue
            source = node_index[edge.source_node_id]
            target = node_index[edge.target_node_id]
            flux = delta_time * (
                velocity * mass[source]
                + diffusion * scale
                * (mass[source] - mass[target]))
            updated[source] -= flux
            updated[target] += flux
            edge_updates += 1
            used.append(edge.stable_id)
        return updated, tuple(used), edge_updates

    def _correct(self, values):
        corrections = 0
        correction_mass = 0.0
        result = []
        unhealthy = False
        for value in values:
            if value < 0.0:
                if abs(value) > self.correction_tolerance:
                    unhealthy = True
                corrections += 1
                correction_mass += abs(value)
                value = 0.0
            result.append(value)
        if corrections > self.maximum_corrections:
            unhealthy = True
        return tuple(result), corrections, correction_mass, unhealthy

    def overlap(self, state):
        if not isinstance(state, AttentionState):
            raise TypeError(
                "overlap requires AttentionState")
        return tuple(
            (float(forward) + self.epsilon) ** self.alpha
            * (float(backward) + self.epsilon) ** self.alpha
            for forward, backward in zip(
                state.forward_mass, state.backward_mass))

    def step(
            self, view, state,
            forward_field, backward_field,
            delta_time=1.0, diffusion=0.0):
        started = time.perf_counter()
        if not isinstance(view, FlowView):
            raise TypeError(
                "advection requires FlowView")
        if not isinstance(state, AttentionState):
            raise TypeError(
                "advection requires AttentionState")
        delta_time = float(delta_time)
        if not math.isfinite(delta_time) or delta_time <= 0.0:
            raise ValueError(
                "advection delta time must be positive")
        diffusion = _finite_nonnegative(
            diffusion, "advection diffusion")
        node_index = self._node_order(view, state)
        forward = self._legal_field(
            view, self._field(view, forward_field),
            FlowProcess.PROBE_FORWARD)
        backward = self._legal_field(
            view, self._field(view, backward_field),
            FlowProcess.PROBE_BACKWARD)
        forward_legality = tuple(
            edge.legality.allows(
                FlowProcess.PROBE_FORWARD)
            for edge in view.edges)
        backward_legality = tuple(
            edge.legality.allows(
                FlowProcess.PROBE_BACKWARD)
            for edge in view.edges)
        raw_cfl = max(
            self._local_cfl(
                view, forward, forward_legality, diffusion,
                delta_time, node_index),
            self._local_cfl(
                view, backward, backward_legality, diffusion,
                delta_time, node_index))
        scale = (
            min(1.0, self.cfl_limit / raw_cfl)
            if raw_cfl > 0.0 else 1.0)
        forward_mass, forward_used, forward_updates = (
            self._transport(
                view, state.forward_mass, forward,
                forward_legality,
                diffusion, delta_time, scale, node_index))
        backward_mass, backward_used, backward_updates = (
            self._transport(
                view, state.backward_mass, backward,
                backward_legality,
                diffusion, delta_time, scale, node_index))
        (
            forward_mass, forward_corrections,
            forward_correction_mass, forward_unhealthy
        ) = self._correct(forward_mass)
        (
            backward_mass, backward_corrections,
            backward_correction_mass, backward_unhealthy
        ) = self._correct(backward_mass)
        next_state = AttentionState(
            node_ids=state.node_ids,
            forward_mass=forward_mass,
            backward_mass=backward_mass,
            reservoir_mass=state.reservoir_mass,
            inflight_mass=state.inflight_mass,
            reservations=state.reservations)
        before = state.accounted_total
        after = next_state.accounted_total
        error = after - before
        corrections = (
            forward_corrections + backward_corrections)
        correction_mass = (
            forward_correction_mass
            + backward_correction_mass)
        mass_tolerance = self.correction_tolerance * max(
            1.0, before)
        unhealthy = (
            forward_unhealthy or backward_unhealthy
            or abs(error) > mass_tolerance)
        overlap = self.overlap(next_state)
        peak = (
            next_state.node_ids[max(
                range(len(overlap)),
                key=lambda index: (
                    overlap[index], -index))]
            if overlap else None)
        return AdvectionStepResult(
            state=next_state,
            overlap=overlap,
            overlap_peak_node_id=peak,
            total_mass_before=before,
            total_mass_after=after,
            mass_error=error,
            raw_local_cfl=raw_cfl,
            applied_velocity_scale=scale,
            cfl_rescaled=scale < 1.0,
            positivity_corrections=corrections,
            correction_mass=correction_mass,
            forward_edges_used=forward_used,
            backward_edges_used=backward_used,
            edge_updates=(
                forward_updates + backward_updates),
            elapsed_ms=(
                (time.perf_counter() - started) * 1000.0),
            health=(
                "unhealthy:mass-or-positivity"
                if unhealthy else "healthy"))

    def run(
            self, view, state,
            forward_field, backward_field,
            microsteps, delta_time=1.0, diffusion=0.0):
        if (isinstance(microsteps, bool)
                or not isinstance(microsteps, int)
                or microsteps < 1):
            raise ValueError(
                "transport microsteps must be positive")
        started = time.perf_counter()
        steps = []
        current = state
        for _ in range(microsteps):
            result = self.step(
                view, current,
                forward_field, backward_field,
                delta_time=delta_time,
                diffusion=diffusion)
            steps.append(result)
            current = result.state
            if not result.healthy:
                break
        wall_ms = (
            time.perf_counter() - started) * 1000.0
        return TransportRun(
            final_state=current,
            steps=tuple(steps),
            microsteps=len(steps),
            corridor_length=max(0, len(view.nodes) - 1),
            edge_updates=sum(
                row.edge_updates for row in steps),
            wall_ms=wall_ms)
