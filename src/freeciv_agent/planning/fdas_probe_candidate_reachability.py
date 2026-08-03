"""Decision-safe probe reachability layered over the calibrated FDAS union."""

from dataclasses import dataclass
import math

from ..events.schema import structural_hash
from ..flow_control import (
    BridgeCandidateSelector,
    CorrectedProbeEstimator,
    FlowNodeKind,
    FreeCivFactorGraphBuilder,
    ProbeConfig,
    SignalUse,
    SignalUseLedger,
)
from .fdas import ShadowOperationCandidate
from .fdas_calibrated_candidate_union import (
    FdasCalibratedCandidateUnion,
)


PROBE_CANDIDATE_REACHABILITY_IDENTITY = (
    "fdas-probe-candidate-reachability/1.0")


def _unit_interval(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("{} must be in [0,1]".format(name))
    return value


def _positive_integer(value, name):
    if (isinstance(value, bool) or not isinstance(value, int)
            or value < 1):
        raise ValueError("{} must be positive".format(name))
    return value


@dataclass(frozen=True)
class _ProbeFlowCandidate:
    """Minimal adapter into the generic authoritative factor builder."""

    candidate: ShadowOperationCandidate

    @property
    def action(self):
        return self.candidate.action

    @property
    def action_key(self):
        return self.candidate.action_key

    @property
    def category(self):
        return self.candidate.operation.operation_type

    @property
    def projection(self):
        # No heuristic projection values are invented for probe steering.
        return {}

    def to_dict(self):
        return {
            "action": self.action,
            "action_key": self.action_key,
            "category": self.category,
            "candidate_hash": self.candidate.candidate_hash,
            "operation_id": self.candidate.operation.operation_id,
            "projection": self.projection,
        }


def _probe_signal_ledger():
    return SignalUseLedger((
        SignalUse(
            "calibrated_transition_estimate", "baseline_candidate_union",
            "protected_membership_only", False, False),
        SignalUse(
            "corrected_probe_weight", "candidate_union",
            "importance_corrected_membership_only", False, False),
        SignalUse(
            "corrected_bridge_overlap", "candidate_union",
            "top_k_membership_only", False, False),
        SignalUse(
            "raw_probe_count", "diagnostics",
            "count_only", False, False),
        SignalUse(
            "typed_advantage", "operation_scoring",
            "add_pre_cost_value_once", True, False),
        SignalUse(
            "operation_cost", "operation_scoring",
            "subtract_once", True, False),
        SignalUse(
            "distributional_risk", "operation_scoring",
            "subtract_scheduler_penalty_once", True, False),
    ))


@dataclass(frozen=True)
class FdasProbeReachabilityReadout:
    operation_id: str
    action_key: str
    operation_type: str
    baseline_rank: int
    operation_node_id: str
    forward_support: float
    backward_support: float
    corrected_overlap: float
    location_eligibility: float
    uncertainty: float
    selected_for_probe_recall: bool

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.action_key, "action key"),
                (self.operation_type, "operation type"),
                (self.operation_node_id, "operation node ID")):
            if not isinstance(value, str) or not value:
                raise ValueError("probe readout {} is required".format(name))
        _positive_integer(self.baseline_rank, "probe baseline rank")
        for name in (
                "forward_support", "backward_support",
                "corrected_overlap", "location_eligibility",
                "uncertainty"):
            object.__setattr__(
                self, name,
                _unit_interval(getattr(self, name), "probe " + name))
        expected_overlap = math.sqrt(
            self.forward_support * self.backward_support)
        if abs(self.corrected_overlap - expected_overlap) > 1e-12:
            raise ValueError("probe overlap is not the corrected support meet")
        if abs(self.location_eligibility - self.corrected_overlap) > 1e-12:
            raise ValueError("probe eligibility introduced undeclared scaling")
        if not isinstance(self.selected_for_probe_recall, bool):
            raise TypeError("probe recall selection must be boolean")
        if self.selected_for_probe_recall and self.location_eligibility <= 0.0:
            raise ValueError("probe recall requires positive reachability")

    def to_dict(self):
        return {
            "action_key": self.action_key,
            "backward_support": self.backward_support,
            "baseline_rank": self.baseline_rank,
            "corrected_overlap": self.corrected_overlap,
            "forward_support": self.forward_support,
            "location_eligibility": self.location_eligibility,
            "operation_id": self.operation_id,
            "operation_node_id": self.operation_node_id,
            "operation_type": self.operation_type,
            "selected_for_probe_recall": self.selected_for_probe_recall,
            "uncertainty": self.uncertainty,
        }


@dataclass(frozen=True)
class FdasProbeCandidateMember:
    operation_id: str
    reasons: tuple

    def __post_init__(self):
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValueError("probe union member requires operation ID")
        reasons = tuple(sorted(str(value) for value in self.reasons))
        if (not reasons or any(not value for value in reasons)
                or len(reasons) != len(set(reasons))
                or set(reasons) - {
                    "calibrated-transition-recall",
                    "probe-informed-reachability",
                    "scalar-top-k",
                    "scalar-winner",
                }):
            raise ValueError("probe union member reasons are invalid")
        object.__setattr__(self, "reasons", reasons)

    def to_dict(self):
        return {
            "operation_id": self.operation_id,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class FdasProbeCandidateUnion:
    snapshot_id: str
    revision_id: str
    goal_id: str
    calibrated_union_result_hash: str
    baseline_selected_operation_id: str
    base_calibrated_operation_ids: tuple
    maximum_probe_regions: int
    probe_per_action: int
    probe_config: ProbeConfig
    graph_artifact_hash: str
    graph_probe_semantic_hash: str
    forward_probe_batch_hash: str
    backward_probe_batch_hash: str
    bridge_selection_hash: str
    graph_complete: bool
    probe_healthy: bool
    fallback_required: bool
    fallback_reason: object
    members: tuple
    readouts: tuple
    probe_selected_operation_ids: tuple
    probe_added_operation_ids: tuple
    signal_ledger: SignalUseLedger
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.goal_id, "goal ID"),
                (self.calibrated_union_result_hash, "calibrated union hash"),
                (self.baseline_selected_operation_id, "baseline selection"),
                (self.graph_artifact_hash, "graph artifact hash"),
                (self.graph_probe_semantic_hash, "graph semantic hash"),
                (self.forward_probe_batch_hash, "forward probe hash"),
                (self.backward_probe_batch_hash, "backward probe hash"),
                (self.bridge_selection_hash, "bridge selection hash"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("probe union {} is required".format(name))
        _positive_integer(self.maximum_probe_regions, "maximum probe regions")
        _positive_integer(self.probe_per_action, "probe per action")
        if not isinstance(self.probe_config, ProbeConfig):
            raise TypeError("probe union requires typed probe config")
        for name in ("graph_complete", "probe_healthy", "fallback_required"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError("probe union {} must be boolean".format(name))
        if (self.fallback_required != (self.fallback_reason is not None)
                or self.fallback_required != (
                    not self.graph_complete or not self.probe_healthy)):
            raise ValueError("probe union fallback state is inconsistent")
        if (self.fallback_reason is not None
                and (not isinstance(self.fallback_reason, str)
                     or not self.fallback_reason)):
            raise ValueError("probe union fallback reason is invalid")
        if (not isinstance(self.signal_ledger, SignalUseLedger)
                or any(row.used_in_final_score for row in
                       self.signal_ledger.uses if row.signal_name in (
                           "calibrated_transition_estimate",
                           "corrected_bridge_overlap",
                           "corrected_probe_weight",
                           "raw_probe_count"))):
            raise ValueError("probe union signal ledger grants score authority")
        if (not self.members or any(
                not isinstance(value, FdasProbeCandidateMember)
                for value in self.members)):
            raise TypeError("probe union requires typed members")
        if (not self.readouts or any(
                not isinstance(value, FdasProbeReachabilityReadout)
                for value in self.readouts)):
            raise TypeError("probe union requires typed readouts")
        member_ids = tuple(value.operation_id for value in self.members)
        readout_ids = tuple(value.operation_id for value in self.readouts)
        base_ids = tuple(self.base_calibrated_operation_ids)
        selected_ids = tuple(self.probe_selected_operation_ids)
        addition_ids = tuple(self.probe_added_operation_ids)
        if any(len(values) != len(set(values)) for values in (
                member_ids, readout_ids, base_ids, selected_ids,
                addition_ids)):
            raise ValueError("probe union IDs must be unique")
        if (not base_ids or set(base_ids) - set(member_ids)
                or set(member_ids) - set(readout_ids)
                or set(selected_ids) - set(member_ids)
                or set(addition_ids) - set(selected_ids)
                or set(addition_ids).intersection(base_ids)
                or self.baseline_selected_operation_id != base_ids[0]
                or self.baseline_selected_operation_id not in member_ids):
            raise ValueError("probe union membership is inconsistent")
        readout_by_id = dict((value.operation_id, value)
                             for value in self.readouts)
        member_by_id = dict((value.operation_id, value)
                            for value in self.members)
        if (tuple(sorted(member_ids,
                         key=lambda value: readout_by_id[value].baseline_rank))
                != member_ids
                or tuple(sorted(readout_ids,
                                key=lambda value:
                                readout_by_id[value].baseline_rank))
                != readout_ids
                or any(readout_by_id[value].selected_for_probe_recall
                       != (value in selected_ids) for value in readout_ids)
                or any("probe-informed-reachability" not in
                       member_by_id[value].reasons for value in selected_ids)
                or any("probe-informed-reachability" in value.reasons
                       and value.operation_id not in selected_ids
                       for value in self.members)):
            raise ValueError("probe union ordering or recall reasons differ")
        if self.fallback_required and (selected_ids or addition_ids):
            raise ValueError("probe fallback cannot add candidate membership")
        action_counts = {}
        for operation_id in addition_ids:
            operation_type = readout_by_id[operation_id].operation_type
            action_counts[operation_type] = action_counts.get(
                operation_type, 0) + 1
        if (any(value > self.probe_per_action
                for value in action_counts.values())
                or len(selected_ids) > self.maximum_probe_regions
                or len(member_ids) > len(base_ids) + len(action_counts)
                * self.probe_per_action):
            raise ValueError("probe union recall bound differs")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("probe union result hash differs")

    @property
    def operation_ids(self):
        return tuple(value.operation_id for value in self.members)

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "backward_probe_batch_hash": self.backward_probe_batch_hash,
            "base_calibrated_operation_ids": list(
                self.base_calibrated_operation_ids),
            "baseline_selected_operation_id": (
                self.baseline_selected_operation_id),
            "bridge_selection_hash": self.bridge_selection_hash,
            "calibrated_union_result_hash": (
                self.calibrated_union_result_hash),
            "capacity_solver_enabled": False,
            "fallback_reason": self.fallback_reason,
            "fallback_required": self.fallback_required,
            "flow_advection_enabled": False,
            "forward_probe_batch_hash": self.forward_probe_batch_hash,
            "goal_id": self.goal_id,
            "graph_artifact_hash": self.graph_artifact_hash,
            "graph_complete": self.graph_complete,
            "graph_probe_semantic_hash": self.graph_probe_semantic_hash,
            "identity": PROBE_CANDIDATE_REACHABILITY_IDENTITY,
            "maximum_probe_regions": self.maximum_probe_regions,
            "members": [value.to_dict() for value in self.members],
            "policy_authority": False,
            "probe_added_operation_ids": list(
                self.probe_added_operation_ids),
            "probe_config": self.probe_config.to_dict(),
            "probe_healthy": self.probe_healthy,
            "probe_per_action": self.probe_per_action,
            "probe_selected_operation_ids": list(
                self.probe_selected_operation_ids),
            "readout_authority": False,
            "readouts": [value.to_dict() for value in self.readouts],
            "revision_id": self.revision_id,
            "scalar_final_score_authority": True,
            "signal_ledger": self.signal_ledger.to_dict(),
            "snapshot_id": self.snapshot_id,
            "truth_mutated": False,
        }

    def to_dict(self):
        value = self._semantic()
        value["result_hash"] = self.result_hash
        return value


def build_probe_candidate_union(
        calibrated_union, candidates, snapshot, revision_id, goal_id,
        probe_config=None, maximum_probe_regions=4, probe_per_action=1):
    """Add bounded corrected-probe recall without ranking or authority."""
    if not isinstance(calibrated_union, FdasCalibratedCandidateUnion):
        raise TypeError("probe reachability requires calibrated union")
    candidates = tuple(candidates)
    if (not candidates or any(
            not isinstance(value, ShadowOperationCandidate)
            for value in candidates)):
        raise TypeError("probe reachability requires shadow candidates")
    if any(not value.legal_bound for value in candidates):
        raise ValueError("probe reachability candidate is not legal-bound")
    if (calibrated_union.snapshot_id != snapshot.snapshot_id
            or calibrated_union.revision_id != str(revision_id)):
        raise ValueError("probe reachability baseline is not revision-current")
    if not isinstance(goal_id, str) or not goal_id:
        raise ValueError("probe reachability goal ID is required")
    _positive_integer(maximum_probe_regions, "maximum probe regions")
    _positive_integer(probe_per_action, "probe per action")
    probe_config = probe_config or ProbeConfig()
    if not isinstance(probe_config, ProbeConfig):
        raise TypeError("probe reachability requires typed probe config")
    candidate_by_id = dict(
        (value.operation.operation_id, value) for value in candidates)
    readout_by_id = dict(
        (value.operation_id, value) for value in calibrated_union.readouts)
    if (len(candidate_by_id) != len(candidates)
            or set(candidate_by_id) != set(readout_by_id)):
        raise ValueError("probe reachability candidate surface differs")

    adapters = tuple(_ProbeFlowCandidate(value) for value in candidates)
    operation_types = tuple(sorted(set(
        value.category for value in adapters)))
    context_digest = structural_hash({
        "calibrated_union_result_hash": calibrated_union.result_hash,
        "goal_id": goal_id,
        "identity": PROBE_CANDIDATE_REACHABILITY_IDENTITY,
        "probe_config": probe_config.to_dict(),
        "revision_id": str(revision_id),
    })
    query_id = "fdas-probe-reachability:" + context_digest[:32]
    generation = int(snapshot.turn)
    factorization = FreeCivFactorGraphBuilder().build(
        query_id, snapshot, adapters, (goal_id,),
        dict((value, goal_id) for value in operation_types),
        semantic_epoch=generation, topology_generation=generation,
        context_digest=context_digest)
    graph_details = factorization.to_dict()
    view = factorization.view
    grounding_by_digest = dict(
        (value.action_digest, value) for value in view.candidate_groundings)
    operation_node_by_id = {}
    for operation_id, candidate in candidate_by_id.items():
        digest = structural_hash(candidate.action)
        grounding = grounding_by_digest.get(digest)
        if grounding is not None:
            operation_node_by_id[operation_id] = grounding.operation_node_id
    graph_complete = bool(
        not factorization.budget_exhausted
        and factorization.factorized_candidate_count == len(candidates)
        and len(operation_node_by_id) == len(candidates))
    forward_boundary_ids = tuple(
        value.stable_id for value in view.nodes
        if value.kind == FlowNodeKind.FORWARD_BOUNDARY)
    backward_boundary_ids = tuple(
        value.stable_id for value in view.nodes
        if (value.kind == FlowNodeKind.BACKWARD_BOUNDARY
            and goal_id in value.provenance_ids))
    if len(forward_boundary_ids) != 1 or len(backward_boundary_ids) != 1:
        raise RuntimeError("probe reachability graph boundaries are invalid")
    operation_node_ids = tuple(sorted(operation_node_by_id.values()))
    estimator = CorrectedProbeEstimator(probe_config)
    forward_batch = estimator.run(
        view, "forward", forward_boundary_ids, operation_node_ids)
    backward_batch = estimator.run(
        view, "backward", backward_boundary_ids, operation_node_ids)
    selection = BridgeCandidateSelector().select(
        view, goal_id, operation_node_ids, forward_batch, backward_batch,
        maximum_regions=maximum_probe_regions)
    probe_healthy = bool(
        forward_batch.health.healthy
        and backward_batch.health.healthy
        and not selection.fallback_required)
    fallback_required = not graph_complete or not probe_healthy
    fallback_reasons = []
    if not graph_complete:
        fallback_reasons.append("incomplete_factor_graph")
    if selection.fallback_reason:
        fallback_reasons.extend(selection.fallback_reason.split(","))
    fallback_reason = (
        None if not fallback_required else
        ",".join(sorted(set(fallback_reasons or ("unhealthy_probes",)))))

    operation_by_node = dict(
        (node_id, operation_id)
        for operation_id, node_id in operation_node_by_id.items())
    selected_nodes = frozenset(selection.selected_operation_node_ids)
    base_ids = calibrated_union.operation_ids
    chosen_ids = []
    additions = []
    addition_counts = {}
    if not fallback_required:
        for bridge_readout in selection.readouts:
            operation_id = operation_by_node[
                bridge_readout.operation_node_id]
            if (bridge_readout.operation_node_id not in selected_nodes
                    or bridge_readout.location_eligibility <= 0.0):
                continue
            if operation_id not in base_ids:
                operation_type = readout_by_id[operation_id].operation_type
                count = addition_counts.get(operation_type, 0)
                if count >= probe_per_action:
                    continue
                addition_counts[operation_type] = count + 1
                additions.append(operation_id)
            chosen_ids.append(operation_id)
    chosen_set = frozenset(chosen_ids)

    bridge_by_node = dict(
        (value.operation_node_id, value) for value in selection.readouts)
    readouts = []
    for calibrated_readout in calibrated_union.readouts:
        operation_id = calibrated_readout.operation_id
        operation_node_id = operation_node_by_id[operation_id]
        bridge_readout = bridge_by_node[operation_node_id]
        readouts.append(FdasProbeReachabilityReadout(
            operation_id=operation_id,
            action_key=calibrated_readout.action_key,
            operation_type=calibrated_readout.operation_type,
            baseline_rank=calibrated_readout.baseline_rank,
            operation_node_id=operation_node_id,
            forward_support=bridge_readout.forward_support,
            backward_support=bridge_readout.backward_support,
            corrected_overlap=bridge_readout.corrected_overlap,
            location_eligibility=bridge_readout.location_eligibility,
            uncertainty=bridge_readout.uncertainty,
            selected_for_probe_recall=operation_id in chosen_set))
    readouts = tuple(sorted(readouts, key=lambda value: value.baseline_rank))

    base_member_by_id = dict(
        (value.operation_id, value) for value in calibrated_union.members)
    member_ids = frozenset(base_ids).union(additions)
    members = []
    for readout in readouts:
        if readout.operation_id not in member_ids:
            continue
        reasons = set(
            base_member_by_id[readout.operation_id].reasons
            if readout.operation_id in base_member_by_id else ())
        if readout.operation_id in chosen_set:
            reasons.add("probe-informed-reachability")
        members.append(FdasProbeCandidateMember(
            readout.operation_id, tuple(reasons)))
    members = tuple(members)
    selected_ids = tuple(
        value.operation_id for value in readouts
        if value.operation_id in chosen_set)
    additions = tuple(
        value.operation_id for value in readouts
        if value.operation_id in additions)
    ledger = _probe_signal_ledger()
    forward_details = forward_batch.to_dict()
    backward_details = backward_batch.to_dict()
    selection_details = selection.to_dict()
    semantic = {
        "action_selection_changed": False,
        "backward_probe_batch_hash": backward_details["artifact_hash"],
        "base_calibrated_operation_ids": list(base_ids),
        "baseline_selected_operation_id": (
            calibrated_union.baseline_selected_operation_id),
        "bridge_selection_hash": selection_details["artifact_hash"],
        "calibrated_union_result_hash": calibrated_union.result_hash,
        "capacity_solver_enabled": False,
        "fallback_reason": fallback_reason,
        "fallback_required": fallback_required,
        "flow_advection_enabled": False,
        "forward_probe_batch_hash": forward_details["artifact_hash"],
        "goal_id": goal_id,
        "graph_artifact_hash": graph_details["artifact_hash"],
        "graph_complete": graph_complete,
        "graph_probe_semantic_hash": view.probe_semantic_hash,
        "identity": PROBE_CANDIDATE_REACHABILITY_IDENTITY,
        "maximum_probe_regions": maximum_probe_regions,
        "members": [value.to_dict() for value in members],
        "policy_authority": False,
        "probe_added_operation_ids": list(additions),
        "probe_config": probe_config.to_dict(),
        "probe_healthy": probe_healthy,
        "probe_per_action": probe_per_action,
        "probe_selected_operation_ids": list(selected_ids),
        "readout_authority": False,
        "readouts": [value.to_dict() for value in readouts],
        "revision_id": str(revision_id),
        "scalar_final_score_authority": True,
        "signal_ledger": ledger.to_dict(),
        "snapshot_id": snapshot.snapshot_id,
        "truth_mutated": False,
    }
    return FdasProbeCandidateUnion(
        snapshot_id=snapshot.snapshot_id,
        revision_id=str(revision_id),
        goal_id=goal_id,
        calibrated_union_result_hash=calibrated_union.result_hash,
        baseline_selected_operation_id=(
            calibrated_union.baseline_selected_operation_id),
        base_calibrated_operation_ids=base_ids,
        maximum_probe_regions=maximum_probe_regions,
        probe_per_action=probe_per_action,
        probe_config=probe_config,
        graph_artifact_hash=graph_details["artifact_hash"],
        graph_probe_semantic_hash=view.probe_semantic_hash,
        forward_probe_batch_hash=forward_details["artifact_hash"],
        backward_probe_batch_hash=backward_details["artifact_hash"],
        bridge_selection_hash=selection_details["artifact_hash"],
        graph_complete=graph_complete,
        probe_healthy=probe_healthy,
        fallback_required=fallback_required,
        fallback_reason=fallback_reason,
        members=members,
        readouts=readouts,
        probe_selected_operation_ids=selected_ids,
        probe_added_operation_ids=additions,
        signal_ledger=ledger,
        result_hash=structural_hash(semantic))
