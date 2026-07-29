"""Corrected bridge readout and single-use signal enforcement."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from .model import FlowNodeKind, FlowView
from .probes import ProbeBatch


def _unit_interval(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(
            "{} must be in [0,1]".format(name))
    return value


@dataclass(frozen=True)
class SignalUse:
    signal_name: str
    stage: str
    transformation: str
    used_in_final_score: bool
    residualized: bool
    model_id: object = None

    def __post_init__(self):
        for name in (
                "signal_name", "stage", "transformation"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "{} is required".format(
                        name.replace("_", " ")))
        if not isinstance(self.used_in_final_score, bool):
            raise TypeError(
                "signal final-score state must be boolean")
        if not isinstance(self.residualized, bool):
            raise TypeError(
                "signal residualization state must be boolean")
        if (self.model_id is not None
                and (not isinstance(self.model_id, str)
                     or not self.model_id)):
            raise ValueError(
                "signal model ID must be nonempty")
        if self.residualized and self.model_id is None:
            raise ValueError(
                "residualized signal requires model ID")

    def to_dict(self):
        return {
            "model_id": self.model_id,
            "residualized": self.residualized,
            "signal_name": self.signal_name,
            "stage": self.stage,
            "transformation": self.transformation,
            "used_in_final_score": (
                self.used_in_final_score),
        }


@dataclass(frozen=True)
class SignalUseLedger:
    uses: tuple
    contract_version: str = "single-use-bridge-signals/1.0"

    def __post_init__(self):
        if any(not isinstance(row, SignalUse)
               for row in self.uses):
            raise TypeError(
                "signal ledger must contain SignalUse")
        keys = [
            (
                row.signal_name, row.stage,
                row.transformation)
            for row in self.uses]
        if len(keys) != len(set(keys)):
            raise ValueError(
                "duplicate signal-use declaration")
        if (not isinstance(self.contract_version, str)
                or not self.contract_version):
            raise ValueError(
                "signal-use contract version is required")
        self._validate_single_use()

    def _validate_single_use(self):
        final_by_signal = {}
        for row in self.uses:
            if (row.signal_name == "raw_probe_count"
                    and (
                        row.used_in_final_score
                        or "amplitude" in row.transformation
                        or "scale_current" in row.transformation)):
                raise ValueError(
                    "raw probe count cannot scale current or score")
            if (row.signal_name in (
                    "bridge_height",
                    "raw_route_momentum")
                    and row.used_in_final_score
                    and not row.residualized):
                raise ValueError(
                    "{} cannot be reapplied to final score".format(
                        row.signal_name))
            if (row.residualized
                    and (row.model_id is None
                         or not row.model_id.startswith(
                             "heldout:"))):
                raise ValueError(
                    "residualized signal requires held-out model ID")
            if row.used_in_final_score:
                final_by_signal.setdefault(
                    row.signal_name, []).append(row)
        duplicate = tuple(
            signal for signal, rows in final_by_signal.items()
            if len(rows) > 1
            and not all(row.residualized for row in rows))
        if duplicate:
            raise ValueError(
                "uncalibrated signal reused in final score: {}".format(
                    ", ".join(sorted(duplicate))))
        raw_final = frozenset(final_by_signal)
        if ("corrected_bridge_overlap" in raw_final
                and "bridge_height" in raw_final):
            raise ValueError(
                "bridge height cannot be scored after overlap readout")

    def to_dict(self):
        material = {
            "contract_version": self.contract_version,
            "uses": [
                row.to_dict() for row in self.uses],
        }
        material["ledger_hash"] = structural_hash(material)
        return material


@dataclass(frozen=True)
class BridgeReadout:
    goal_id: str
    operation_node_id: str
    forward_support: float
    backward_support: float
    corrected_overlap: float
    compatibility: float
    location_eligibility: float
    uncertainty: float
    estimator_id: str

    def __post_init__(self):
        if not isinstance(self.goal_id, str) or not self.goal_id:
            raise ValueError(
                "bridge readout goal ID is required")
        if (not isinstance(self.operation_node_id, str)
                or not self.operation_node_id):
            raise ValueError(
                "bridge readout operation node ID is required")
        for name in (
                "forward_support", "backward_support",
                "corrected_overlap", "compatibility",
                "location_eligibility", "uncertainty"):
            _unit_interval(
                getattr(self, name),
                "bridge {}".format(
                    name.replace("_", " ")))
        if abs(
                self.corrected_overlap
                - _geometric_overlap(
                    self.forward_support,
                    self.backward_support)) > 1e-12:
            raise ValueError(
                "corrected overlap must be geometric support meet")
        if abs(
                self.location_eligibility
                - self.corrected_overlap
                * self.compatibility) > 1e-12:
            raise ValueError(
                "location eligibility must be overlap times compatibility")
        if not isinstance(self.estimator_id, str) or not self.estimator_id:
            raise ValueError(
                "bridge readout estimator ID is required")

    def to_dict(self):
        return {
            "backward_support": float(self.backward_support),
            "compatibility": float(self.compatibility),
            "corrected_overlap": float(
                self.corrected_overlap),
            "estimator_id": self.estimator_id,
            "forward_support": float(self.forward_support),
            "goal_id": self.goal_id,
            "location_eligibility": float(
                self.location_eligibility),
            "operation_node_id": self.operation_node_id,
            "uncertainty": float(self.uncertainty),
        }


def _geometric_overlap(left, right):
    return math.sqrt(float(left) * float(right))


@dataclass(frozen=True)
class BridgeRegionSelection:
    goal_id: str
    readouts: tuple
    selected_operation_node_ids: tuple
    signal_ledger: SignalUseLedger
    fallback_required: bool
    fallback_reason: object

    def __post_init__(self):
        if any(not isinstance(row, BridgeReadout)
               for row in self.readouts):
            raise TypeError(
                "bridge selection readouts must contain BridgeReadout")
        if not isinstance(self.signal_ledger, SignalUseLedger):
            raise TypeError(
                "bridge selection requires SignalUseLedger")
        available = frozenset(
            row.operation_node_id for row in self.readouts)
        if any(value not in available
               for value in self.selected_operation_node_ids):
            raise ValueError(
                "bridge selection references missing readout")
        if not isinstance(self.fallback_required, bool):
            raise TypeError(
                "bridge fallback state must be boolean")
        if self.fallback_required != (
                self.fallback_reason is not None):
            raise ValueError(
                "bridge fallback reason must match state")

    def to_dict(self):
        material = {
            "fallback_reason": self.fallback_reason,
            "fallback_required": self.fallback_required,
            "goal_id": self.goal_id,
            "readouts": [
                row.to_dict() for row in self.readouts],
            "schema_version": "1.0",
            "selected_operation_node_ids": list(
                self.selected_operation_node_ids),
            "signal_ledger": self.signal_ledger.to_dict(),
        }
        material["artifact_hash"] = structural_hash(material)
        return material


def default_signal_use_ledger():
    return SignalUseLedger((
        SignalUse(
            "bridge_height", "probe_steering",
            "temperature_scaled_direction",
            False, False),
        SignalUse(
            "corrected_probe_weight", "route_current",
            "importance_corrected_deposit",
            False, False),
        SignalUse(
            "raw_probe_count", "diagnostics",
            "count_only",
            False, False),
        SignalUse(
            "corrected_bridge_overlap",
            "candidate_region_selection",
            "multiply_compatibility",
            False, False),
        SignalUse(
            "typed_advantage", "operation_scoring",
            "add_pre_cost_value_once",
            True, False),
        SignalUse(
            "operation_cost", "operation_scoring",
            "subtract_once",
            True, False),
        SignalUse(
            "distributional_risk", "operation_scoring",
            "subtract_scheduler_penalty_once",
            True, False),
    ))


class BridgeCandidateSelector:
    """Read corrected route overlap without reusing raw bridge signals."""

    ESTIMATOR_ID = "corrected-bridge-readout/1.0"

    @staticmethod
    def _deposits(batch):
        values = {}
        for path in batch.paths:
            unique_nodes = tuple(dict.fromkeys(path.node_ids))
            amount = (
                path.importance_weight
                * path.reliability
                / len(unique_nodes))
            for node_id in unique_nodes:
                values[node_id] = (
                    values.get(node_id, 0.0) + amount)
        maximum = max(values.values() or (1.0,))
        if maximum <= 0.0:
            return dict((key, 0.0) for key in values)
        return dict(
            (key, min(1.0, value / maximum))
            for key, value in values.items())

    def select(
            self, view, goal_id, operation_node_ids,
            forward_batch, backward_batch,
            compatibilities=None, maximum_regions=8):
        if not isinstance(view, FlowView):
            raise TypeError(
                "bridge selector requires FlowView")
        if not isinstance(forward_batch, ProbeBatch):
            raise TypeError(
                "forward probes must be ProbeBatch")
        if not isinstance(backward_batch, ProbeBatch):
            raise TypeError(
                "backward probes must be ProbeBatch")
        if (forward_batch.side != "forward"
                or backward_batch.side != "backward"):
            raise ValueError(
                "bridge selector probe sides are reversed")
        if (forward_batch.topology_generation
                != view.topology_generation
                or backward_batch.topology_generation
                != view.topology_generation):
            raise ValueError(
                "bridge selector received stale probes")
        if (isinstance(maximum_regions, bool)
                or not isinstance(maximum_regions, int)
                or maximum_regions < 1):
            raise ValueError(
                "maximum bridge regions must be positive")
        operation_ids = tuple(sorted(set(
            str(value) for value in operation_node_ids)))
        for operation_id in operation_ids:
            if view.node(operation_id).kind != FlowNodeKind.OPERATION:
                raise ValueError(
                    "bridge readout requires operation nodes")
        compatibility = dict(compatibilities or {})
        if any(value not in operation_ids
               for value in compatibility):
            raise ValueError(
                "bridge compatibility references unknown operation")
        for operation_id in operation_ids:
            _unit_interval(
                compatibility.get(operation_id, 1.0),
                "bridge compatibility")
        forward = self._deposits(forward_batch)
        backward = self._deposits(backward_batch)
        health_fraction = min(
            forward_batch.health.effective_sample_fraction,
            backward_batch.health.effective_sample_fraction)
        uncertainty = 1.0 - health_fraction
        readouts = []
        for operation_id in operation_ids:
            f = forward.get(operation_id, 0.0)
            g = backward.get(operation_id, 0.0)
            overlap = math.sqrt(f * g)
            compatible = float(
                compatibility.get(operation_id, 1.0))
            readouts.append(BridgeReadout(
                goal_id=str(goal_id),
                operation_node_id=operation_id,
                forward_support=f,
                backward_support=g,
                corrected_overlap=overlap,
                compatibility=compatible,
                location_eligibility=(
                    overlap * compatible),
                uncertainty=uncertainty,
                estimator_id=self.ESTIMATOR_ID))
        readouts = tuple(sorted(
            readouts,
            key=lambda row: (
                -row.location_eligibility,
                row.operation_node_id)))
        healthy = (
            forward_batch.health.healthy
            and backward_batch.health.healthy)
        selected = (
            tuple(
                row.operation_node_id
                for row in readouts[:maximum_regions])
            if healthy else ())
        reasons = tuple(sorted(set(
            forward_batch.health.reasons
            + backward_batch.health.reasons)))
        return BridgeRegionSelection(
            goal_id=str(goal_id),
            readouts=readouts,
            selected_operation_node_ids=selected,
            signal_ledger=default_signal_use_ledger(),
            fallback_required=not healthy,
            fallback_reason=(
                None if healthy
                else ",".join(reasons)))
