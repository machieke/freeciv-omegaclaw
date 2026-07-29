"""Unified flow health diagnostics and truth-preserving fallback policy."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from .advection import AdvectionStepResult
from .capacities import MultiCommodityResult
from .eligibility import FlowPacketDecision
from .probes import ProbeBatch
from .projection import ProjectionResult


DIAGNOSTIC_NAMES = (
    "mass_conservation",
    "balance_residual",
    "local_cfl",
    "bridge_overlap",
    "probe_meet_rate",
    "probe_correction",
    "path_diversity",
    "feedback_ratio",
    "pressure_peak",
    "dual_health",
    "integrality_gap",
    "packet_starvation",
    "stale_view_lag",
    "relief_calibration",
    "normalization_drift",
    "controller_overhead",
)


RESPONSES = {
    "mass_conservation": "stop-flow-repair-or-fallback",
    "balance_residual": "regional-resolve-or-scalar-fallback",
    "local_cfl": "rescale-velocity-or-reduce-step",
    "bridge_overlap": "expand-diffuse-or-fallback",
    "probe_meet_rate": "increase-exploration-or-use-messages",
    "probe_correction": "more-reference-probes-or-holdout",
    "path_diversity": "increase-temperature-or-diffusion",
    "feedback_ratio": "lower-deposit-or-current-following-gain",
    "pressure_peak": "inspect-capacity-provenance",
    "dual_health": "suppress-economic-interpretation",
    "integrality_gap": "concentrate-routes-or-change-packets",
    "packet_starvation": "return-or-reallocate-reservations",
    "stale_view_lag": "patch-rebuild-or-fallback",
    "relief_calibration": "update-or-disable-estimator",
    "normalization_drift": "invalidate-calibration",
    "controller_overhead": "compare-or-fallback-to-scalar",
}


@dataclass(frozen=True)
class FlowDiagnosticsConfig:
    mass_tolerance: float = 1e-9
    balance_tolerance: float = 1e-8
    cfl_limit: float = 0.9
    minimum_bridge_overlap: float = 1e-12
    minimum_probe_meet_rate: float = 0.05
    minimum_ess_fraction: float = 0.20
    maximum_clipped_fraction: float = 0.25
    minimum_path_diversity: float = 0.01
    maximum_feedback_ratio: float = 0.50
    maximum_pressure_peak: float = 10.0
    maximum_integrality_ratio: float = 0.50
    maximum_packet_starvation: int = 0
    maximum_stale_view_lag: int = 0
    maximum_relief_mae: float = 0.50
    controller_budget_ms: float = 500.0

    def __post_init__(self):
        for name in (
                "mass_tolerance", "balance_tolerance",
                "minimum_bridge_overlap",
                "minimum_probe_meet_rate",
                "minimum_ess_fraction",
                "maximum_clipped_fraction",
                "minimum_path_diversity",
                "maximum_feedback_ratio",
                "maximum_pressure_peak",
                "maximum_integrality_ratio",
                "maximum_relief_mae",
                "controller_budget_ms"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(
                    "{} must be finite and non-negative".format(name))
        if not 0.0 < self.cfl_limit <= 1.0:
            raise ValueError(
                "diagnostic CFL limit must be in (0, 1]")
        for name in (
                "minimum_probe_meet_rate",
                "minimum_ess_fraction",
                "maximum_clipped_fraction",
                "minimum_path_diversity",
                "maximum_feedback_ratio",
                "maximum_integrality_ratio"):
            if float(getattr(self, name)) > 1.0:
                raise ValueError(
                    "{} must be at most one".format(name))
        for name in (
                "maximum_packet_starvation",
                "maximum_stale_view_lag"):
            value = getattr(self, name)
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))


@dataclass(frozen=True)
class FlowHealthSample:
    forward_total_mass: object = None
    backward_total_mass: object = None
    mass_error: object = None
    balance_residual: object = None
    projection_healthy: object = None
    local_cfl: object = None
    cfl_rescaled: object = None
    advection_healthy: object = None
    bridge_overlap: object = None
    probe_meet_rate: object = None
    ess_fraction: object = None
    clipped_fraction: object = None
    path_diversity: object = None
    probes_healthy: object = None
    feedback_ratio: object = None
    pressure_peak: object = None
    dual_converged: object = None
    integrality_gap: object = None
    relaxed_value: object = None
    packet_starvation_count: object = None
    stale_view_lag: object = None
    relief_mae: object = None
    expected_normalization_hash: object = None
    observed_normalization_hash: object = None
    controller_overhead_ms: object = None

    @classmethod
    def from_components(
            cls, advection_steps=(), projections=(),
            probe_batches=(), capacity_result=None,
            packet_decision=None, feedback_ratio=None,
            stale_view_lag=None, predicted_relief=(),
            realized_relief=(),
            expected_normalization_hash=None,
            observed_normalization_hash=None,
            controller_overhead_ms=None):
        advection_steps = tuple(advection_steps)
        projections = tuple(projections)
        probe_batches = tuple(probe_batches)
        if any(not isinstance(row, AdvectionStepResult)
               for row in advection_steps):
            raise TypeError(
                "diagnostic advection rows have wrong type")
        if any(not isinstance(row, ProjectionResult)
               for row in projections):
            raise TypeError(
                "diagnostic projections have wrong type")
        if any(not isinstance(row, ProbeBatch)
               for row in probe_batches):
            raise TypeError(
                "diagnostic probe batches have wrong type")
        if (capacity_result is not None
                and not isinstance(
                    capacity_result, MultiCommodityResult)):
            raise TypeError(
                "diagnostic capacity result has wrong type")
        if (packet_decision is not None
                and not isinstance(
                    packet_decision, FlowPacketDecision)):
            raise TypeError(
                "diagnostic packet decision has wrong type")
        final_state = (
            advection_steps[-1].state
            if advection_steps else None)
        paths = tuple(
            path for batch in probe_batches
            for path in batch.paths)
        predicted_relief = tuple(
            float(value) for value in predicted_relief)
        realized_relief = tuple(
            float(value) for value in realized_relief)
        if len(predicted_relief) != len(realized_relief):
            raise ValueError(
                "predicted and realized relief must align")
        relief_mae = (
            sum(abs(left - right)
                for left, right in zip(
                    predicted_relief, realized_relief))
            / len(predicted_relief)
            if predicted_relief else None)
        return cls(
            forward_total_mass=(
                final_state.forward_total
                if final_state is not None else None),
            backward_total_mass=(
                final_state.backward_total
                if final_state is not None else None),
            mass_error=(
                max(abs(row.mass_error)
                    for row in advection_steps)
                if advection_steps else None),
            balance_residual=(
                max(row.balance_residual
                    for row in projections)
                if projections else None),
            projection_healthy=(
                all(row.healthy for row in projections)
                if projections else None),
            local_cfl=(
                max(row.raw_local_cfl
                    for row in advection_steps)
                if advection_steps else None),
            cfl_rescaled=(
                any(row.cfl_rescaled
                    for row in advection_steps)
                if advection_steps else None),
            advection_healthy=(
                all(row.healthy for row in advection_steps)
                if advection_steps else None),
            bridge_overlap=(
                max(
                    (max(row.overlap)
                     if row.overlap else 0.0)
                    for row in advection_steps)
                if advection_steps else None),
            probe_meet_rate=(
                sum(1 for row in paths
                    if row.met_opposite_frontier)
                / float(len(paths))
                if paths else None),
            ess_fraction=(
                min(row.health.effective_sample_fraction
                    for row in probe_batches)
                if probe_batches else None),
            clipped_fraction=(
                max(row.health.clipped_weight_fraction
                    for row in probe_batches)
                if probe_batches else None),
            path_diversity=(
                min(row.health.path_diversity
                    for row in probe_batches)
                if probe_batches else None),
            probes_healthy=(
                all(row.health.healthy
                    for row in probe_batches)
                if probe_batches else None),
            feedback_ratio=feedback_ratio,
            pressure_peak=(
                max((row.value for row
                     in capacity_result.capacity_duals),
                    default=0.0)
                if capacity_result is not None else None),
            dual_converged=(
                capacity_result.converged
                if capacity_result is not None else None),
            integrality_gap=(
                packet_decision.diagnostics.integrality_gap
                if packet_decision is not None else None),
            relaxed_value=(
                packet_decision.diagnostics
                .relaxed_continuous_value
                if packet_decision is not None else None),
            packet_starvation_count=(
                len(packet_decision.diagnostics.packet_starvation)
                if packet_decision is not None else None),
            stale_view_lag=stale_view_lag,
            relief_mae=relief_mae,
            expected_normalization_hash=(
                expected_normalization_hash),
            observed_normalization_hash=(
                observed_normalization_hash),
            controller_overhead_ms=controller_overhead_ms)


@dataclass(frozen=True)
class DiagnosticReading:
    name: str
    status: str
    value: object
    reason: str
    recommended_response: str

    def __post_init__(self):
        if self.name not in DIAGNOSTIC_NAMES:
            raise ValueError(
                "unknown flow diagnostic")
        if self.status not in (
                "healthy", "repaired",
                "unhealthy", "unknown"):
            raise ValueError(
                "unknown diagnostic status")
        if self.recommended_response != RESPONSES[self.name]:
            raise ValueError(
                "diagnostic response disagrees with contract")

    @property
    def acceptable(self):
        return self.status in ("healthy", "repaired")

    def to_dict(self):
        return {
            "name": self.name,
            "reason": self.reason,
            "recommended_response": (
                self.recommended_response),
            "status": self.status,
            "value": self.value,
        }


@dataclass(frozen=True)
class FlowHealthReport:
    readings: tuple
    require_complete: bool
    monitor_identity: str

    def __post_init__(self):
        if (tuple(row.name for row in self.readings)
                != DIAGNOSTIC_NAMES):
            raise ValueError(
                "health report must contain ordered diagnostics")
        if not isinstance(self.require_complete, bool):
            raise TypeError(
                "complete-health policy must be boolean")

    @property
    def complete(self):
        return all(
            row.status != "unknown"
            for row in self.readings)

    @property
    def unhealthy_names(self):
        return tuple(
            row.name for row in self.readings
            if row.status == "unhealthy"
            or (self.require_complete
                and row.status == "unknown"))

    @property
    def healthy(self):
        return not self.unhealthy_names

    @property
    def report_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "complete": self.complete,
            "healthy": self.healthy,
            "monitor_identity": self.monitor_identity,
            "readings": [
                row.to_dict() for row in self.readings],
            "require_complete": self.require_complete,
            "unhealthy_names": list(
                self.unhealthy_names),
        }


class FlowHealthMonitor:
    """Evaluate all preregistered flow health dimensions."""

    MONITOR_IDENTITY = "pf-flow-health/1.0"

    def __init__(self, config=None):
        self.config = (
            config if config is not None
            else FlowDiagnosticsConfig())
        if not isinstance(
                self.config, FlowDiagnosticsConfig):
            raise TypeError(
                "flow health config has wrong type")

    @staticmethod
    def _unknown(name):
        return DiagnosticReading(
            name, "unknown", None,
            "diagnostic-input-unavailable",
            RESPONSES[name])

    @staticmethod
    def _reading(name, value, healthy, reason):
        return DiagnosticReading(
            name,
            "healthy" if healthy else "unhealthy",
            value, reason, RESPONSES[name])

    def evaluate(self, sample, require_complete=False):
        if not isinstance(sample, FlowHealthSample):
            raise TypeError(
                "health monitor requires FlowHealthSample")
        config = self.config
        readings = []
        if (sample.mass_error is None
                or sample.forward_total_mass is None
                or sample.backward_total_mass is None
                or sample.advection_healthy is None):
            readings.append(self._unknown(
                "mass_conservation"))
        else:
            healthy = (
                sample.advection_healthy
                and abs(float(sample.mass_error))
                <= config.mass_tolerance)
            readings.append(self._reading(
                "mass_conservation", {
                    "backward_total": float(
                        sample.backward_total_mass),
                    "forward_total": float(
                        sample.forward_total_mass),
                    "mass_error": float(sample.mass_error),
                }, healthy,
                ("conserved" if healthy
                 else "mass-or-positivity-failure")))
        if (sample.balance_residual is None
                or sample.projection_healthy is None):
            readings.append(self._unknown(
                "balance_residual"))
        else:
            healthy = (
                sample.projection_healthy
                and float(sample.balance_residual)
                <= config.balance_tolerance)
            readings.append(self._reading(
                "balance_residual",
                float(sample.balance_residual),
                healthy,
                ("balanced" if healthy
                 else "projection-unhealthy")))
        if (sample.local_cfl is None
                or sample.cfl_rescaled is None
                or sample.advection_healthy is None):
            readings.append(self._unknown("local_cfl"))
        else:
            raw = float(sample.local_cfl)
            if (raw > config.cfl_limit
                    and sample.cfl_rescaled
                    and sample.advection_healthy):
                readings.append(DiagnosticReading(
                    "local_cfl", "repaired", raw,
                    "velocity-rescaled-before-step",
                    RESPONSES["local_cfl"]))
            else:
                healthy = (
                    raw <= config.cfl_limit
                    and sample.advection_healthy)
                readings.append(self._reading(
                    "local_cfl", raw, healthy,
                    ("within-cfl" if healthy
                     else "unrepaired-cfl-violation")))
        scalar_checks = (
            (
                "bridge_overlap", sample.bridge_overlap,
                lambda value: value
                >= config.minimum_bridge_overlap,
                "meeting-corridor-present",
                "no-meeting-corridor"),
            (
                "probe_meet_rate", sample.probe_meet_rate,
                lambda value: value
                >= config.minimum_probe_meet_rate,
                "probe-meet-rate-adequate",
                "probe-meet-rate-low"),
            (
                "path_diversity", sample.path_diversity,
                lambda value: value
                >= config.minimum_path_diversity,
                "path-diversity-adequate",
                "path-lock-in"),
            (
                "feedback_ratio", sample.feedback_ratio,
                lambda value: value
                <= config.maximum_feedback_ratio,
                "feedback-bounded",
                "self-reinforcement-high"),
            (
                "pressure_peak", sample.pressure_peak,
                lambda value: value
                <= config.maximum_pressure_peak,
                "pressure-bounded",
                "capacity-pressure-peak"),
            (
                "stale_view_lag", sample.stale_view_lag,
                lambda value: value
                <= config.maximum_stale_view_lag,
                "view-current",
                "stale-view"),
            (
                "relief_calibration", sample.relief_mae,
                lambda value: value
                <= config.maximum_relief_mae,
                "relief-calibrated",
                "relief-miscalibrated"),
            (
                "controller_overhead",
                sample.controller_overhead_ms,
                lambda value: value
                <= config.controller_budget_ms,
                "controller-within-budget",
                "controller-over-budget"),
        )
        # Add bridge and meet before the composite correction diagnostic.
        for name, value, predicate, passed, failed in scalar_checks[:2]:
            if value is None:
                readings.append(self._unknown(name))
            else:
                healthy = predicate(float(value))
                readings.append(self._reading(
                    name, float(value), healthy,
                    passed if healthy else failed))
        if (sample.ess_fraction is None
                or sample.clipped_fraction is None
                or sample.probes_healthy is None):
            readings.append(self._unknown(
                "probe_correction"))
        else:
            healthy = (
                sample.probes_healthy
                and float(sample.ess_fraction)
                >= config.minimum_ess_fraction
                and float(sample.clipped_fraction)
                <= config.maximum_clipped_fraction)
            readings.append(self._reading(
                "probe_correction", {
                    "clipped_fraction": float(
                        sample.clipped_fraction),
                    "ess_fraction": float(
                        sample.ess_fraction),
                }, healthy,
                ("probe-correction-healthy" if healthy
                 else "probe-correction-unhealthy")))
        for name, value, predicate, passed, failed in scalar_checks[2:5]:
            if value is None:
                readings.append(self._unknown(name))
            else:
                healthy = predicate(float(value))
                readings.append(self._reading(
                    name, float(value), healthy,
                    passed if healthy else failed))
        if sample.dual_converged is None:
            readings.append(self._unknown("dual_health"))
        else:
            readings.append(self._reading(
                "dual_health",
                bool(sample.dual_converged),
                bool(sample.dual_converged),
                ("dual-converged"
                 if sample.dual_converged
                 else "dual-nonconverged")))
        if (sample.integrality_gap is None
                or sample.relaxed_value is None):
            readings.append(self._unknown(
                "integrality_gap"))
        else:
            ratio = (
                float(sample.integrality_gap)
                / max(1e-12, float(sample.relaxed_value))
                if float(sample.relaxed_value) > 0.0
                else 0.0)
            healthy = (
                ratio <= config.maximum_integrality_ratio)
            readings.append(self._reading(
                "integrality_gap", {
                    "gap": float(sample.integrality_gap),
                    "ratio": ratio,
                    "relaxed_value": float(
                        sample.relaxed_value),
                }, healthy,
                ("integrality-gap-bounded" if healthy
                 else "integrality-gap-high")))
        if sample.packet_starvation_count is None:
            readings.append(self._unknown(
                "packet_starvation"))
        else:
            count = int(sample.packet_starvation_count)
            healthy = (
                count <= config.maximum_packet_starvation)
            readings.append(self._reading(
                "packet_starvation", count, healthy,
                ("no-packet-starvation" if healthy
                 else "incomplete-packet-reservations")))
        for name, value, predicate, passed, failed in scalar_checks[5:7]:
            if value is None:
                readings.append(self._unknown(name))
            else:
                healthy = predicate(float(value))
                readings.append(self._reading(
                    name, float(value), healthy,
                    passed if healthy else failed))
        if (sample.expected_normalization_hash is None
                or sample.observed_normalization_hash is None):
            readings.append(self._unknown(
                "normalization_drift"))
        else:
            healthy = (
                sample.expected_normalization_hash
                == sample.observed_normalization_hash)
            readings.append(self._reading(
                "normalization_drift", {
                    "expected": (
                        sample.expected_normalization_hash),
                    "observed": (
                        sample.observed_normalization_hash),
                }, healthy,
                ("normalization-stable" if healthy
                 else "normalization-contract-changed")))
        name, value, predicate, passed, failed = scalar_checks[7]
        if value is None:
            readings.append(self._unknown(name))
        else:
            healthy = predicate(float(value))
            readings.append(self._reading(
                name, float(value), healthy,
                passed if healthy else failed))
        by_name = dict((row.name, row) for row in readings)
        ordered = tuple(by_name[name] for name in DIAGNOSTIC_NAMES)
        return FlowHealthReport(
            readings=ordered,
            require_complete=bool(require_complete),
            monitor_identity=self.MONITOR_IDENTITY)


REPAIR_ORDER = (
    "local_numerical_repair",
    "adjust_exploration_or_feedback",
    "apply_pending_topology_patches",
    "rebuild_affected_view",
    "fallback_bridge_scalar",
    "fallback_scalar_v2",
    "fallback_legacy_scalar",
    "fallback_canonical_impact",
)


@dataclass(frozen=True)
class FlowRepairDecision:
    selected_action: object
    fallback_mode: object
    unhealthy_diagnostics: tuple
    attempted_actions: tuple
    truth_mutation_allowed: bool
    candidate_authority: bool
    planner_identity: str

    def __post_init__(self):
        if (self.selected_action is not None
                and self.selected_action not in REPAIR_ORDER):
            raise ValueError(
                "unknown flow repair action")
        if self.truth_mutation_allowed:
            raise ValueError(
                "flow repair may never alter truth")
        if self.candidate_authority:
            raise ValueError(
                "flow repair is not candidate authority")

    def to_dict(self):
        return {
            "attempted_actions": list(
                self.attempted_actions),
            "candidate_authority": self.candidate_authority,
            "fallback_mode": self.fallback_mode,
            "planner_identity": self.planner_identity,
            "selected_action": self.selected_action,
            "truth_mutation_allowed": (
                self.truth_mutation_allowed),
            "unhealthy_diagnostics": list(
                self.unhealthy_diagnostics),
        }


class FlowRepairPlanner:
    """Select the next relevant repair without modifying truth."""

    PLANNER_IDENTITY = "pf-flow-repair-ladder/1.0"
    LOCAL = frozenset((
        "mass_conservation", "balance_residual",
        "local_cfl", "dual_health"))
    EXPLORATION = frozenset((
        "bridge_overlap", "probe_meet_rate",
        "probe_correction", "path_diversity",
        "feedback_ratio"))
    TOPOLOGY = frozenset(("stale_view_lag",))

    def decide(self, report, attempted_actions=()):
        if not isinstance(report, FlowHealthReport):
            raise TypeError(
                "repair planner requires health report")
        attempted = tuple(attempted_actions)
        if (len(set(attempted)) != len(attempted)
                or any(value not in REPAIR_ORDER
                       for value in attempted)):
            raise ValueError(
                "attempted repairs must be unique known actions")
        unhealthy = frozenset(report.unhealthy_names)
        selected = None
        if unhealthy:
            relevant = []
            if unhealthy & self.LOCAL:
                relevant.append("local_numerical_repair")
            if unhealthy & self.EXPLORATION:
                relevant.append(
                    "adjust_exploration_or_feedback")
            if unhealthy & self.TOPOLOGY:
                relevant.append(
                    "apply_pending_topology_patches")
            relevant.append("rebuild_affected_view")
            relevant.extend(REPAIR_ORDER[4:])
            selected = next((
                value for value in relevant
                if value not in attempted), None)
        fallback_modes = {
            "fallback_bridge_scalar": "bridge_scalar",
            "fallback_scalar_v2": "scalar_v2",
            "fallback_legacy_scalar": "legacy_scalar",
            "fallback_canonical_impact": "canonical_impact",
        }
        return FlowRepairDecision(
            selected_action=selected,
            fallback_mode=fallback_modes.get(selected),
            unhealthy_diagnostics=tuple(sorted(unhealthy)),
            attempted_actions=attempted,
            truth_mutation_allowed=False,
            candidate_authority=False,
            planner_identity=self.PLANNER_IDENTITY)
