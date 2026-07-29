"""Bridge-scalar controller with health-gated scalar-v2 fallback."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from ..pressure.packets import (
    PacketBudget,
    PacketScheduler,
    ResourceKind,
)
from ..pressure.scalar_baseline import (
    ScalarRouteBid,
    SmoothedScalarController,
)
from .builder import (
    FlowBuildBudget,
    FreeCivFactorGraphBuilder,
)
from .candidate_selector import (
    BridgeCandidateSelector,
    DecisionSafeCandidateSelector,
)
from .model import FlowNodeKind
from .potentials import (
    DeterministicMessagePotentialEstimator,
    PotentialBudget,
)
from .probes import (
    CorrectedProbeEstimator,
    ProbeConfig,
    ProbeNodeFeatures,
)


@dataclass(frozen=True)
class BridgeScalarConfig:
    maximum_regions_per_goal: int = 8
    probe_path_count: int = 128
    probe_max_steps: int = 32
    probe_reference_fraction: float = 0.2
    probe_temperature: float = 1.0
    probe_maximum_importance_weight: float = 20.0
    probe_minimum_ess_fraction: float = 0.2
    probe_maximum_clipped_fraction: float = 0.25
    probe_minimum_path_diversity: float = 0.01
    probe_current_following_gain: float = 0.0
    probe_estimator_mode: str = "two_stream"
    seed: int = 1729
    allow_unvalidated_reordering: bool = False
    readout_policy: str = "corrected-probe-overlap"
    protected_scalar_top_k: int = 3
    force_fallback_reason: object = None

    def __post_init__(self):
        for name in (
                "maximum_regions_per_goal",
                "probe_path_count", "probe_max_steps",
                "protected_scalar_top_k"):
            value = getattr(self, name)
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 1):
                raise ValueError(
                    "{} must be a positive integer".format(name))
        for name in (
                "probe_reference_fraction",
                "probe_minimum_ess_fraction",
                "probe_maximum_clipped_fraction",
                "probe_minimum_path_diversity"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(
                    "{} must be in [0,1]".format(name))
        if self.probe_reference_fraction <= 0.0:
            raise ValueError(
                "bridge probes require reference stream")
        if self.probe_estimator_mode not in (
                "importance", "two_stream"):
            raise ValueError(
                "bridge probe estimator mode is invalid")
        if self.readout_policy not in (
                "corrected-probe-overlap",
                "protected-message-union",
                "corrected-probe-union"):
            raise ValueError(
                "bridge readout policy is invalid")
        for name, minimum in (
                ("probe_temperature", 0.0),
                ("probe_maximum_importance_weight", 1.0),
                ("probe_current_following_gain", 0.0)):
            value = float(getattr(self, name))
            if (not math.isfinite(value)
                    or value < minimum
                    or (name == "probe_temperature"
                        and value == 0.0)):
                raise ValueError(
                    "{} is outside its valid range".format(
                        name))
        if (isinstance(self.seed, bool)
                or not isinstance(self.seed, int)):
            raise ValueError(
                "bridge seed must be an integer")
        if not isinstance(
                self.allow_unvalidated_reordering, bool):
            raise TypeError(
                "bridge reordering policy must be boolean")
        if (self.force_fallback_reason is not None
                and (not isinstance(
                    self.force_fallback_reason, str)
                     or not self.force_fallback_reason)):
            raise ValueError(
                "forced fallback reason must be nonempty")

    def to_dict(self):
        return {
            "allow_unvalidated_reordering": (
                self.allow_unvalidated_reordering),
            "force_fallback_reason": (
                self.force_fallback_reason),
            "maximum_regions_per_goal": (
                self.maximum_regions_per_goal),
            "probe_max_steps": self.probe_max_steps,
            "probe_maximum_clipped_fraction": (
                self.probe_maximum_clipped_fraction),
            "probe_maximum_importance_weight": (
                self.probe_maximum_importance_weight),
            "probe_current_following_gain": (
                self.probe_current_following_gain),
            "probe_estimator_mode": (
                self.probe_estimator_mode),
            "probe_minimum_ess_fraction": (
                self.probe_minimum_ess_fraction),
            "probe_minimum_path_diversity": (
                self.probe_minimum_path_diversity),
            "probe_path_count": self.probe_path_count,
            "probe_reference_fraction": (
                self.probe_reference_fraction),
            "probe_temperature": (
                self.probe_temperature),
            "protected_scalar_top_k": (
                self.protected_scalar_top_k),
            "readout_policy": self.readout_policy,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class BridgeScalarDecision:
    selected_operation_id: object
    ranked_operation_ids: tuple
    fallback_required: bool
    fallback_reason: object
    controller_identity: str
    config: dict
    flow_summary: object
    potential_summary: object
    goal_selections: tuple
    scalar_decision: object
    packet_schedule: object

    def __post_init__(self):
        if not isinstance(self.fallback_required, bool):
            raise TypeError(
                "bridge fallback state must be boolean")
        if self.fallback_required != (
                self.fallback_reason is not None):
            raise ValueError(
                "bridge fallback reason must match state")
        if self.fallback_required and (
                self.selected_operation_id is not None
                or self.ranked_operation_ids):
            raise ValueError(
                "fallback decision cannot rank bridge operations")
        if not self.fallback_required and (
                self.selected_operation_id is None
                or not self.ranked_operation_ids
                or self.ranked_operation_ids[0]
                != self.selected_operation_id):
            raise ValueError(
                "healthy bridge decision requires selected first route")

    def to_dict(self):
        material = {
            "config": dict(self.config),
            "controller_identity": self.controller_identity,
            "fallback_reason": self.fallback_reason,
            "fallback_required": self.fallback_required,
            "flow_summary": self.flow_summary,
            "goal_selections": list(self.goal_selections),
            "packet_schedule": self.packet_schedule,
            "potential_summary": self.potential_summary,
            "ranked_operation_ids": list(
                self.ranked_operation_ids),
            "scalar_decision": self.scalar_decision,
            "schema_version": "1.0",
            "selected_operation_id": (
                self.selected_operation_id),
        }
        material["artifact_hash"] = structural_hash(material)
        return material


class BridgeScalarController:
    """Bridge region selection plus unchanged scalar-v2 operation scores."""

    CONTROLLER_IDENTITY = "pf-pln-bridge-scalar/1.0"

    def __init__(self, config=None):
        self.config = (
            config if config is not None else BridgeScalarConfig())
        if not isinstance(self.config, BridgeScalarConfig):
            raise TypeError(
                "bridge scalar config must be BridgeScalarConfig")
        self.factor_builder = FreeCivFactorGraphBuilder(
            FlowBuildBudget(
                max_nodes=1024, max_edges=4096,
                max_candidates=512,
                max_frontier_stubs=64))
        self.potential_estimator = (
            DeterministicMessagePotentialEstimator())
        self.probe_estimator = CorrectedProbeEstimator(
            ProbeConfig(
                mode=self.config.probe_estimator_mode,
                path_count=self.config.probe_path_count,
                max_steps=self.config.probe_max_steps,
                reference_fraction=(
                    self.config.probe_reference_fraction),
                temperature=(
                    self.config.probe_temperature),
                current_following_gain=(
                    self.config
                    .probe_current_following_gain),
                maximum_importance_weight=(
                    self.config
                    .probe_maximum_importance_weight),
                minimum_ess_fraction=(
                    self.config.probe_minimum_ess_fraction),
                maximum_clipped_fraction=(
                    self.config.probe_maximum_clipped_fraction),
                minimum_path_diversity=(
                    self.config.probe_minimum_path_diversity),
                seed=self.config.seed))
        self.selector = BridgeCandidateSelector()
        self.protected_selector = (
            DecisionSafeCandidateSelector())

    def _fallback(
            self, reason, flow_summary=None,
            potential_summary=None, goal_selections=()):
        return BridgeScalarDecision(
            selected_operation_id=None,
            ranked_operation_ids=(),
            fallback_required=True,
            fallback_reason=str(reason),
            controller_identity=self.CONTROLLER_IDENTITY,
            config=self.config.to_dict(),
            flow_summary=flow_summary,
            potential_summary=potential_summary,
            goal_selections=tuple(goal_selections),
            scalar_decision=None,
            packet_schedule=None)

    @staticmethod
    def _standardized_features(
            view, estimates, flow_to_score):
        heights = tuple(
            row.bridge_height for row in estimates)
        mean = sum(heights) / len(heights)
        variance = sum(
            (value - mean) ** 2
            for value in heights) / len(heights)
        scale = math.sqrt(variance) or 1.0
        score_costs = tuple(
            row.scalar_cost for row in flow_to_score.values())
        score_risks = tuple(
            row.risk_penalty for row in flow_to_score.values())
        maximum_cost = max(score_costs or (1.0,)) or 1.0
        maximum_risk = max(score_risks or (1.0,)) or 1.0
        estimate_by_node = dict(
            (row.node_id, row) for row in estimates)
        rows = []
        for node in view.nodes:
            estimate = estimate_by_node[node.stable_id]
            standardized = max(
                -4.0, min(
                    4.0,
                    (estimate.bridge_height - mean) / scale))
            score = flow_to_score.get(node.stable_id)
            rows.append(ProbeNodeFeatures(
                node_id=node.stable_id,
                local_advantage=standardized,
                cost=(
                    0.0 if score is None
                    else score.scalar_cost / maximum_cost),
                risk=(
                    0.0 if score is None
                    else score.risk_penalty / maximum_risk)))
        return tuple(rows)

    def rank(
            self, snapshot, candidate_by_operation,
            operations, scores, goal_by_category,
            semantic_epoch=0, topology_generation=0,
            clone_generation=0):
        candidate_by_operation = dict(
            candidate_by_operation)
        operations = tuple(operations)
        scores = tuple(scores)
        goal_by_category = dict(goal_by_category)
        if set(candidate_by_operation) != {
                row.operation_id for row in operations}:
            raise ValueError(
                "bridge candidates and operations must align")
        if set(candidate_by_operation) != {
                row.operation_id for row in scores}:
            raise ValueError(
                "bridge candidates and scores must align")
        if self.config.force_fallback_reason is not None:
            return self._fallback(
                self.config.force_fallback_reason)
        candidates = tuple(
            candidate_by_operation[key]
            for key in sorted(candidate_by_operation))
        active_goals = tuple(sorted(set(
            goal_by_category[candidate.category]
            for candidate in candidates
            if candidate.category in goal_by_category)))
        if not active_goals:
            return self._fallback(
                "no_bridge_goal_routes")
        try:
            factorization = self.factor_builder.build(
                "bridge-scalar:{}".format(snapshot.snapshot_id),
                snapshot, candidates,
                goal_ids=active_goals,
                goal_by_category=goal_by_category,
                semantic_epoch=semantic_epoch,
                topology_generation=topology_generation,
                clone_generation=clone_generation)
            view = factorization.view
            flow_summary = {
                "candidate_count": len(
                    view.candidate_groundings),
                "edge_count": len(view.edges),
                "factorized_candidate_count": (
                    factorization.factorized_candidate_count),
                "frontier_candidate_count": (
                    factorization.frontier_candidate_count),
                "node_count": len(view.nodes),
                "topology_generation": (
                    view.topology_generation),
                "view_hash": view.to_dict()["view_hash"],
            }
            potentials = self.potential_estimator.estimate(
                view, active_goals,
                PotentialBudget(max_iterations=64))
            potential_summary = {
                "estimate_count": len(potentials),
                "estimator_id": (
                    self.potential_estimator.ESTIMATOR_ID),
                "potential_hash": structural_hash([
                    row.to_dict() for row in potentials]),
                "process_semantics": (
                    self.potential_estimator.process_semantics),
            }
            grounding_by_digest = dict(
                (row.action_digest, row)
                for row in view.candidate_groundings)
            flow_by_pressure = {}
            pressure_by_flow = {}
            for operation_id, candidate in (
                    candidate_by_operation.items()):
                grounding = grounding_by_digest[
                    structural_hash(candidate.action)]
                flow_by_pressure[operation_id] = (
                    grounding.operation_node_id)
                pressure_by_flow[
                    grounding.operation_node_id] = operation_id
            score_by_pressure = dict(
                (row.operation_id, row) for row in scores)
            flow_to_score = dict(
                (flow_by_pressure[operation_id],
                 score_by_pressure[operation_id])
                for operation_id in flow_by_pressure)
            forward_starts = tuple(
                row.stable_id for row in view.nodes
                if row.kind == FlowNodeKind.FORWARD_BOUNDARY)
            goal_nodes = dict(
                (row.provenance_ids[0], row.stable_id)
                for row in view.nodes
                if (row.kind == FlowNodeKind.BACKWARD_BOUNDARY
                    and row.provenance_ids))
            all_flow_operations = tuple(sorted(
                pressure_by_flow))
            selected_flow_operations = set()
            goal_selections = []
            for goal_id in active_goals:
                goal_estimates = tuple(
                    row for row in potentials
                    if row.goal_id == goal_id)
                features = self._standardized_features(
                    view, goal_estimates, flow_to_score)
                relevant_pressure_ids = tuple(
                    operation_id
                    for operation_id, candidate
                    in sorted(candidate_by_operation.items())
                    if goal_by_category.get(candidate.category)
                    == goal_id)
                relevant_flow_ids = tuple(
                    flow_by_pressure[value]
                    for value in relevant_pressure_ids)
                if self.config.readout_policy == (
                        "protected-message-union"):
                    estimate_by_node = dict(
                        (row.node_id, row)
                        for row in goal_estimates)
                    selected_messages = tuple(sorted(
                        relevant_flow_ids,
                        key=lambda value: (
                            -estimate_by_node[
                                value].bridge_factor,
                            value)
                    )[:min(
                        self.config
                        .maximum_regions_per_goal,
                        len(relevant_flow_ids))])
                    selected_flow_operations.update(
                        selected_messages)
                    goal_selections.append({
                        "backward_probe": None,
                        "forward_probe": None,
                        "goal_id": goal_id,
                        "selection": {
                            "estimator_id":
                                self.potential_estimator
                                .ESTIMATOR_ID,
                            "readout_policy":
                                self.config
                                .readout_policy,
                            "selected_operation_node_ids":
                                list(
                                    selected_messages),
                            "signal_authority":
                                "candidate-union-only",
                        },
                    })
                    continue
                forward_batch = self.probe_estimator.run(
                    view, "forward", forward_starts,
                    all_flow_operations, features)
                backward_batch = self.probe_estimator.run(
                    view, "backward",
                    (goal_nodes[goal_id],),
                    all_flow_operations, features)
                selection = self.selector.select(
                    view, goal_id, relevant_flow_ids,
                    forward_batch, backward_batch,
                    maximum_regions=min(
                        self.config.maximum_regions_per_goal,
                        len(relevant_flow_ids)))
                goal_selections.append({
                    "backward_probe": {
                        "artifact_hash": backward_batch.to_dict()[
                            "artifact_hash"],
                        "health": backward_batch.health.to_dict(),
                        "meet_count": sum(
                            row.met_opposite_frontier
                            for row in backward_batch.paths),
                        "path_count": len(
                            backward_batch.paths),
                    },
                    "forward_probe": {
                        "artifact_hash": forward_batch.to_dict()[
                            "artifact_hash"],
                        "health": forward_batch.health.to_dict(),
                        "meet_count": sum(
                            row.met_opposite_frontier
                            for row in forward_batch.paths),
                        "path_count": len(
                            forward_batch.paths),
                    },
                    "goal_id": goal_id,
                    "selection": selection.to_dict(),
                })
                if selection.fallback_required:
                    return self._fallback(
                        "unhealthy_bridge_estimator:{}".format(
                            selection.fallback_reason),
                        flow_summary, potential_summary,
                        goal_selections)
                selected_flow_operations.update(
                    selection.selected_operation_node_ids)
            protected_union = None
            if self.config.readout_policy in (
                    "protected-message-union",
                    "corrected-probe-union"):
                bridge_pressure_ids = tuple(
                    pressure_by_flow[value]
                    for value in sorted(
                        selected_flow_operations))
                scalar_ranked_ids = tuple(
                    row.operation_id for row in scores
                    if row.admissible)
                terminal_ids = tuple(
                    operation_id
                    for operation_id, candidate
                    in sorted(
                        candidate_by_operation.items())
                    if candidate.terminal_on_accept)
                safety_active = any(
                    row.admissible
                    and not row.operation
                    .safety_compatible
                    for row in scores)
                safety_ids = (
                    tuple(
                        row.operation_id
                        for row in scores
                        if (
                            row.admissible
                            and row.operation
                            .safety_compatible))
                    if safety_active else ())
                protected_union = (
                    self.protected_selector.select(
                        scalar_ranked_ids,
                        tuple(sorted(
                            candidate_by_operation)),
                        bridge_operation_ids=(
                            bridge_pressure_ids),
                        terminal_operation_ids=(
                            terminal_ids),
                        safety_operation_ids=(
                            safety_ids),
                        scalar_top_k=(
                            self.config
                            .protected_scalar_top_k),
                        readout_policy=(
                            self.config
                            .readout_policy)))
                selected_pressure_ids = frozenset(
                    protected_union.operation_ids)
            else:
                selected_pressure_ids = frozenset(
                    pressure_by_flow[value]
                    for value in selected_flow_operations)
            selected_scores = tuple(
                row for row in scores
                if (row.operation_id in selected_pressure_ids
                    and row.admissible))
            if not selected_scores:
                return self._fallback(
                    "no_admissible_bridge_region",
                    flow_summary, potential_summary,
                    goal_selections)
            scalar = SmoothedScalarController()
            scalar_decision = scalar.rank(tuple(
                ScalarRouteBid(
                    row.operation_id,
                    row.priority,
                    admissible=row.admissible)
                for row in selected_scores), step=0)
            selected_id = scalar_decision.selected_route_id
            if selected_id is None:
                return self._fallback(
                    "strong_scalar_abstained",
                    flow_summary, potential_summary,
                    goal_selections)
            scalar_v2_selected = next(
                (row.operation_id for row in scores
                 if row.admissible), None)
            if (selected_id != scalar_v2_selected
                    and not self.config
                    .allow_unvalidated_reordering):
                return self._fallback(
                    "unvalidated_bridge_reordering",
                    flow_summary, potential_summary,
                    goal_selections)
            selected_operation = next(
                row for row in operations
                if row.operation_id == selected_id)
            selected_score = score_by_pressure[selected_id]
            packet_schedule = PacketScheduler().schedule(
                (selected_operation,), (selected_score,), (
                    PacketBudget(ResourceKind.ACTION, 1),
                    PacketBudget(ResourceKind.CPU, 1),
                ))
            if packet_schedule.committed_operation_ids != (
                    selected_id,):
                return self._fallback(
                    "incomplete_packet_reservation",
                    flow_summary, potential_summary,
                    goal_selections)
            scalar_order = tuple(
                row.route_id for row in scalar_decision.scores
                if row.admissible)
            if protected_union is not None:
                # Candidate-union membership is a recall/readout signal only.
                # With no separately calibrated final value, preserve the
                # complete scalar ordering byte-for-byte.
                ranked = tuple(
                    row.operation_id for row in scores)
            else:
                remaining = tuple(
                    row.operation_id for row in scores
                    if row.operation_id not in scalar_order)
                ranked = scalar_order + remaining
            return BridgeScalarDecision(
                selected_operation_id=selected_id,
                ranked_operation_ids=ranked,
                fallback_required=False,
                fallback_reason=None,
                controller_identity=self.CONTROLLER_IDENTITY,
                config=self.config.to_dict(),
                flow_summary=flow_summary,
                potential_summary=potential_summary,
                goal_selections=tuple(
                    goal_selections)
                + (
                    ({
                        "protected_candidate_union":
                            protected_union.to_dict(),
                    },)
                    if protected_union is not None
                    else ()),
                scalar_decision=scalar_decision.to_dict(),
                packet_schedule=packet_schedule.to_dict())
        except (
                ArithmeticError, KeyError, RuntimeError,
                TypeError, ValueError) as error:
            return self._fallback(
                "bridge_exception:{}".format(
                    type(error).__name__))
