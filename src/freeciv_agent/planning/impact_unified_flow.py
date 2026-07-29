"""Production-shaped Python unified flow controller for grounded Impact."""

from dataclasses import dataclass, replace
import time

from ..events.schema import canonical_json_bytes, structural_hash
from ..flow_control import (
    AttentionState,
    CorrectedProbeEstimator,
    DeterministicMessagePotentialEstimator,
    FlowCandidateFactory,
    FlowHealthMonitor,
    FlowHealthSample,
    FlowNodeKind,
    FlowPacketIntegrator,
    FlowProcess,
    FreeCivFactorGraphBuilder,
    PacketReservationLedger,
    PotentialBudget,
    ProbeConfig,
    ProbeNodeFeatures,
    ProjectionSolver,
    RequestedCurrentBuilder,
    TwoDyeAdvectionKernel,
    default_normalization_contract,
)
from ..pressure import (
    CostVector,
    Operation,
    PacketBudget,
    PacketCost,
    ResourceKind,
    TypedAdvantage,
)
from ..pressure.scheduler import (
    GoalEffect,
    OperationScore,
)
from .impact_flow_adapter import (
    ControlDecision,
    ControlQuery,
)


@dataclass(frozen=True)
class UnifiedImpactFlowConfig:
    probe_path_count: int = 8
    probe_max_steps: int = 16
    probe_reference_fraction: float = 0.25
    potential_iterations: int = 64
    transport_microsteps: int = 8
    transport_time_step: float = 1.0
    diffusion: float = 0.03
    controller_budget_ms: float = 500.0
    seed: int = 4401

    def __post_init__(self):
        for name in (
                "probe_path_count", "probe_max_steps",
                "potential_iterations",
                "transport_microsteps"):
            value = getattr(self, name)
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 1):
                raise ValueError(
                    "{} must be a positive integer".format(name))
        for name in (
                "probe_reference_fraction",):
            value = float(getattr(self, name))
            if not 0.0 < value <= 1.0:
                raise ValueError(
                    "{} must be in (0, 1]".format(name))
        for name in (
                "transport_time_step",
                "controller_budget_ms"):
            if float(getattr(self, name)) <= 0.0:
                raise ValueError(
                    "{} must be positive".format(name))
        if not 0.0 <= float(self.diffusion) <= 1.0:
            raise ValueError(
                "flow diffusion must be in [0, 1]")
        if (isinstance(self.seed, bool)
                or not isinstance(self.seed, int)):
            raise ValueError(
                "flow seed must be an integer")


def _cost(value):
    return CostVector(**dict(value))


def _advantage(value):
    predicted = value.get(
        "predicted_resource_use", ())
    if isinstance(predicted, dict):
        predicted = tuple(sorted(
            (str(key), float(item))
            for key, item in predicted.items()))
    else:
        predicted = tuple(
            (str(row[0]), float(row[1]))
            for row in predicted)
    return TypedAdvantage(
        goal_id=str(value["goal_id"]),
        target_id=str(value["target_id"]),
        mode=str(value["mode"]),
        expected_relief=float(
            value["expected_relief"]),
        relief_variance=float(
            value["relief_variance"]),
        information_gain=float(
            value["information_gain"]),
        option_value=float(value["option_value"]),
        predicted_latency=float(
            value["predicted_latency"]),
        predicted_resource_use=predicted,
        estimator_id=str(value["estimator_id"]))


def _operation(value):
    packet_costs = tuple(
        PacketCost(
            ResourceKind(row["resource"]),
            int(row["quanta"]))
        for row in value.get("packet_costs", ()))
    return Operation(
        operation_id=str(value["operation_id"]),
        atom_id=str(value["atom_id"]),
        mode=str(value["mode"]),
        cost=_cost(value["cost"]),
        causal_kind=str(value.get(
            "causal_kind", "associative")),
        success_probability=float(value.get(
            "success_probability", 1.0)),
        relief_scale=float(value.get(
            "relief_scale", 1.0)),
        feasibility=float(value.get(
            "feasibility", 1.0)),
        deadline_fit=float(value.get(
            "deadline_fit", 1.0)),
        information_gain=float(value.get(
            "information_gain", 0.0)),
        coherence_gain=float(value.get(
            "coherence_gain", 0.0)),
        future_option_value=float(value.get(
            "future_option_value", 0.0)),
        redundancy=float(value.get(
            "redundancy", 0.0)),
        contradiction_risk=float(value.get(
            "contradiction_risk", 0.0)),
        goal_effects=tuple(
            (str(row[0]), float(row[1]))
            for row in value.get("goal_effects", ())),
        safety_compatible=bool(value.get(
            "safety_compatible", True)),
        payload=value.get("payload"),
        reversible=bool(value.get(
            "reversible", True)),
        externally_consequential=bool(value.get(
            "externally_consequential", False)),
        packet_costs=packet_costs,
        packet_threshold=int(value.get(
            "packet_threshold", 1)),
        reservation_policy=str(value.get(
            "reservation_policy", "atomic")),
        requirement_set_id=value.get(
            "requirement_set_id"),
        typed_advantages=tuple(
            _advantage(row)
            for row in value.get(
                "typed_advantages", ())))


def _score(value):
    operation = _operation(value["operation"])
    effects = tuple(
        GoalEffect(
            goal_id=str(row["goal_id"]),
            pressure=float(row["pressure"]),
            normalized_relief=float(
                row["normalized_relief"]),
            effect=float(row["effect"]),
            weighted_effect=float(
                row["weighted_effect"]),
            conflict_pressure=float(
                row.get("conflict_pressure", 0.0)))
        for row in value.get("goal_effects", ()))
    return OperationScore(
        operation=operation,
        admissible=bool(value["admissible"]),
        reason=value.get("reason"),
        priority=float(value["priority"]),
        value=float(value["value"]),
        scalar_cost=float(value["scalar_cost"]),
        conflict_penalty=float(
            value["conflict_penalty"]),
        goal_effects=effects,
        risk_penalty=float(
            value.get("risk_penalty", 0.0)))


class UnifiedImpactFlowEngine:
    """Compose bridge, flow, and packet components behind one safe adapter."""

    ENGINE_IDENTITY = "grounded-impact-unified-flow/1.0"

    def __init__(self, scalar_v2_ranker, config=None):
        if not hasattr(scalar_v2_ranker, "rank"):
            raise TypeError(
                "unified flow requires scalar-v2 ranker")
        self.scalar_v2_ranker = scalar_v2_ranker
        self.config = (
            config if config is not None
            else UnifiedImpactFlowConfig())
        if not isinstance(
                self.config, UnifiedImpactFlowConfig):
            raise TypeError(
                "unified flow config has wrong type")
        self.factor_builder = FreeCivFactorGraphBuilder()
        self.potentials = (
            DeterministicMessagePotentialEstimator())
        self.probes = CorrectedProbeEstimator(
            ProbeConfig(
                mode="two_stream",
                path_count=self.config.probe_path_count,
                max_steps=self.config.probe_max_steps,
                reference_fraction=(
                    self.config.probe_reference_fraction),
                minimum_ess_fraction=0.10,
                maximum_clipped_fraction=0.50,
                minimum_path_diversity=0.0,
                seed=self.config.seed))
        self.current_builder = RequestedCurrentBuilder()
        self.projector = ProjectionSolver()
        self.transport = TwoDyeAdvectionKernel(
            cfl_limit=0.9)
        self.candidate_factory = FlowCandidateFactory()
        self.packet_integrator = FlowPacketIntegrator()
        self.health_monitor = FlowHealthMonitor()

    @staticmethod
    def _serialized_pressure(artifact):
        value = dict(artifact)
        value.pop("_packet_schedule_object", None)
        return value

    @staticmethod
    def _semantic_transport(transport):
        value = transport.to_dict()
        value.pop("wall_ms", None)
        value.pop(
            "microseconds_per_edge_update", None)
        return value

    @staticmethod
    def _semantic_health(health):
        value = health.to_dict()
        for reading in value["readings"]:
            if reading["name"] == (
                    "controller_overhead"):
                reading["value"] = {
                    "within_budget":
                        reading["status"]
                        in ("healthy", "repaired"),
                }
        return value

    @staticmethod
    def _candidate_key_from_operation(operation):
        payload = operation.payload or {}
        action = payload.get("action")
        if not isinstance(action, dict):
            raise ValueError(
                "typed operation lacks grounded action")
        return canonical_json_bytes(
            action).decode("utf-8")

    @staticmethod
    def _goal_by_category(
            candidate_by_operation, score_by_operation):
        result = {}
        for operation_id, candidate in (
                candidate_by_operation.items()):
            operation = score_by_operation[
                operation_id].operation
            if not operation.typed_advantages:
                continue
            result[candidate.category] = (
                operation.typed_advantages[0].goal_id)
        return result

    @staticmethod
    def _fields_for_goal(
            view, estimate_by_node, process):
        result = {}
        for edge in view.edges:
            if not edge.legality.allows(process):
                result[edge.stable_id] = 0.0
                continue
            source = estimate_by_node[
                edge.source_node_id].bridge_height
            target = estimate_by_node[
                edge.target_node_id].bridge_height
            result[edge.stable_id] = max(
                0.0, float(target) - float(source))
        return result

    @staticmethod
    def _accumulate(target, projection, divisor):
        for edge_id, value in zip(
                projection.edge_ids,
                projection.feasible_current):
            if value < -1e-9:
                raise ValueError(
                    "projected flow opposes directed legality: "
                    "{}={}".format(edge_id, value))
            target[edge_id] = (
                target.get(edge_id, 0.0)
                + max(0.0, float(value))
                / float(divisor))

    def _project_directed(self, view, requested):
        """Project a bridge-steered prior without reversing legal edges.

        The generic Hodge projection is intentionally orientation-neutral.
        For the production factor DAG, the bridge/probe mixture therefore
        acts as positive mobility rather than raw current. A zero raw current
        plus the explicit source/sink boundary yields a minimum-energy flow
        whose route preference still follows the mixed prior.
        """
        zero_request = replace(
            requested,
            velocity=tuple(
                0.0 for _ in requested.velocity),
            source_components=(
                tuple(requested.source_components)
                + ("directed-zero-current-projection",)))
        mobility = tuple(
            (
                1e-6 + max(0.0, float(value))
                if legal else 0.0)
            for value, legal in zip(
                requested.velocity,
                requested.legality_mask))
        return self.projector.solve(
            view, zero_request, mobility=mobility)

    @staticmethod
    def _fallback(
            query, ordered, pressure_artifact,
            packet_schedule, reason, started,
            details=None):
        keys = tuple(
            row.action_key for row in ordered)
        return ControlDecision(
            ordered_candidate_keys=keys,
            selected_candidate_key=(
                keys[0] if keys else None),
            packet_schedule=packet_schedule,
            controller_mode="unified_flow",
            artifact={
                "admissible_candidate_keys": [],
                "calibrated": False,
                "confidence": 0.0,
                "controller_identity":
                    UnifiedImpactFlowEngine.ENGINE_IDENTITY,
                "controller_telemetry": {
                    "total_latency_ms": (
                        time.perf_counter() - started
                    ) * 1000.0,
                },
                "evidence_overlap_valid": True,
                "fallback_reason": str(reason),
                "flow": details,
                "pressure_artifact": pressure_artifact,
                "quarantined": False,
                "query_hash": query.query_hash,
                "safety_conflict": False,
            },
            health="unhealthy",
            fallback_chain=(
                "unified_flow", "scalar_v2"))

    def __call__(self, query, snapshot):
        if not isinstance(query, ControlQuery):
            raise TypeError(
                "unified flow requires ControlQuery")
        started = time.perf_counter()
        ordered, raw_artifact = self.scalar_v2_ranker.rank(
            snapshot,
            query.grounded_candidates,
            query.expansion_city_target,
            query.horizon_turn,
            query.survival_threat_radius,
            _goal_facts=query.goal_facts)
        scalar_schedule = raw_artifact.get(
            "_packet_schedule_object")
        pressure_artifact = self._serialized_pressure(
            raw_artifact)
        try:
            score_rows = tuple(
                _score(row) for row in pressure_artifact[
                    "schedule"]["scores"])
            score_by_operation = dict(
                (row.operation_id, row)
                for row in score_rows)
            candidate_by_key = dict(
                (row.action_key, row)
                for row in query.grounded_candidates)
            candidate_by_operation = dict(
                (row.operation_id,
                 candidate_by_key[
                     self._candidate_key_from_operation(
                         row.operation)])
                for row in score_rows)
            goal_by_category = self._goal_by_category(
                candidate_by_operation,
                score_by_operation)
            active_goals = tuple(sorted(set(
                goal_by_category.values())))
            if not active_goals:
                raise ValueError(
                    "no typed flow goals")
            factorization = self.factor_builder.build(
                query.query_id, snapshot,
                query.grounded_candidates,
                active_goals, goal_by_category,
                semantic_epoch=query.semantic_epoch,
                topology_generation=int(
                    snapshot.identity.source_seq),
                clone_generation=(
                    query.lifecycle_clone_generation),
                context_digest=query.context_digest)
            view = factorization.view
            estimates = self.potentials.estimate(
                view, active_goals,
                PotentialBudget(
                    max_iterations=(
                        self.config.potential_iterations)))
            estimates_by_goal = {}
            for estimate in estimates:
                estimates_by_goal.setdefault(
                    estimate.goal_id, {})[
                        estimate.node_id] = estimate
            grounding_by_digest = dict(
                (row.action_digest, row)
                for row in view.candidate_groundings)
            flow_node_by_operation = {}
            for operation_id, candidate in (
                    candidate_by_operation.items()):
                grounding = grounding_by_digest[
                    structural_hash(candidate.action)]
                flow_node_by_operation[operation_id] = (
                    grounding.operation_node_id)
            forward_starts = tuple(
                row.stable_id for row in view.nodes
                if row.kind
                == FlowNodeKind.FORWARD_BOUNDARY)
            goal_nodes = dict(
                (row.provenance_ids[0], row.stable_id)
                for row in view.nodes
                if (row.kind
                    == FlowNodeKind.BACKWARD_BOUNDARY
                    and row.provenance_ids))
            forward_field = dict(
                (row.stable_id, 0.0)
                for row in view.edges)
            backward_field = dict(forward_field)
            projections = []
            batches = []
            processed_goals = []
            for goal_id in active_goals:
                relevant_operations = tuple(sorted(
                    operation_id
                    for operation_id, candidate
                    in candidate_by_operation.items()
                    if goal_by_category.get(
                        candidate.category) == goal_id))
                relevant_nodes = tuple(
                    flow_node_by_operation[value]
                    for value in relevant_operations)
                if (not relevant_nodes
                        or goal_id not in goal_nodes):
                    continue
                goal_estimates = estimates_by_goal[
                    goal_id]
                features = tuple(
                    ProbeNodeFeatures(
                        node_id=row.stable_id,
                        local_advantage=max(
                            0.0,
                            goal_estimates[
                                row.stable_id]
                            .bridge_factor))
                    for row in view.nodes)
                forward_batch = self.probes.run(
                    view, "forward", forward_starts,
                    relevant_nodes, features)
                backward_batch = self.probes.run(
                    view, "backward",
                    (goal_nodes[goal_id],),
                    relevant_nodes, features)
                batches.extend((
                    forward_batch, backward_batch))
                forward_paths = tuple(
                    row for row in forward_batch.paths
                    if row.met_opposite_frontier)
                backward_paths = tuple(
                    row for row in backward_batch.paths
                    if row.met_opposite_frontier)
                semantic_forward = self._fields_for_goal(
                    view, goal_estimates,
                    FlowProcess.PROBE_FORWARD)
                semantic_backward = self._fields_for_goal(
                    view, goal_estimates,
                    FlowProcess.PROBE_BACKWARD)
                # Projection spans the complete causal corridor. Operations
                # are observation/readout nodes, not artificial sinks: using
                # them as sinks reverses the operation-to-effect leg and
                # violates directed flow legality.
                forward_boundary = {
                    forward_starts[0]: 1.0,
                    goal_nodes[goal_id]: -1.0,
                }
                sinks = -1.0 / len(relevant_nodes)
                backward_boundary = dict(
                    (value, sinks)
                    for value in relevant_nodes)
                backward_boundary[
                    goal_nodes[goal_id]] = 1.0
                use_forward_probes = (
                    forward_paths
                    if forward_batch.health.healthy else ())
                use_backward_probes = (
                    backward_paths
                    if backward_batch.health.healthy else ())
                forward_request = (
                    self.current_builder.build(
                        view,
                        "{}:forward:cpu".format(goal_id),
                        semantic_forward,
                        use_forward_probes,
                        forward_boundary,
                        FlowProcess.PROBE_FORWARD,
                        semantic_weight=(
                            0.7 if use_forward_probes else 1.0),
                        probe_weight=(
                            0.3 if use_forward_probes else 0.0)))
                backward_request = (
                    self.current_builder.build(
                        view,
                        "{}:backward:cpu".format(goal_id),
                        semantic_backward,
                        use_backward_probes,
                        backward_boundary,
                        FlowProcess.PROBE_BACKWARD,
                        semantic_weight=(
                            0.7 if use_backward_probes else 1.0),
                        probe_weight=(
                            0.3 if use_backward_probes else 0.0)))
                forward_projection = self._project_directed(
                    view, forward_request)
                backward_projection = self._project_directed(
                    view, backward_request)
                if (not forward_projection.healthy
                        or not backward_projection.healthy):
                    continue
                projections.extend((
                    forward_projection,
                    backward_projection))
                processed_goals.append(goal_id)
                self._accumulate(
                    forward_field,
                    forward_projection, 1)
                self._accumulate(
                    backward_field,
                    backward_projection, 1)
            if not processed_goals:
                raise ValueError(
                    "no healthy source-sink goal projection")
            divisor = float(len(processed_goals))
            forward_field = dict(
                (key, value / divisor)
                for key, value in forward_field.items())
            backward_field = dict(
                (key, value / divisor)
                for key, value in backward_field.items())
            node_ids = tuple(
                row.stable_id for row in view.nodes)
            node_index = dict(
                (value, index)
                for index, value in enumerate(node_ids))
            forward_mass = [0.0] * len(node_ids)
            backward_mass = [0.0] * len(node_ids)
            forward_mass[
                node_index[forward_starts[0]]] = 1.0
            for goal_id in processed_goals:
                backward_mass[
                    node_index[goal_nodes[goal_id]]
                ] += 1.0 / len(processed_goals)
            state = AttentionState(
                node_ids=node_ids,
                forward_mass=tuple(forward_mass),
                backward_mass=tuple(backward_mass),
                reservoir_mass={},
                inflight_mass={},
                reservations=PacketReservationLedger())
            transport = self.transport.run(
                view, state,
                forward_field, backward_field,
                microsteps=(
                    self.config.transport_microsteps),
                delta_time=(
                    self.config.transport_time_step),
                diffusion=self.config.diffusion)
            if (not transport.steps
                    or not all(
                        row.healthy
                        for row in transport.steps)):
                raise ValueError(
                    "unhealthy conservative attention transport")
            overlap = tuple(
                max(
                    step.overlap[index]
                    for step in transport.steps)
                for index in range(len(node_ids)))
            eligible_overlaps = []
            for operation_id, node_id in (
                    flow_node_by_operation.items()):
                value = overlap[node_index[node_id]]
                if value <= 1e-12:
                    continue
                eligible_overlaps.append((
                    operation_id, node_id, value))
            eligible_overlaps.sort(key=lambda row: (
                not score_by_operation[row[0]].admissible,
                -score_by_operation[
                    row[0]].priority,
                row[0]))
            if not eligible_overlaps:
                raise ValueError(
                    "flow emitted no eligible operation")
            operation_id, node_id, value = (
                eligible_overlaps[0])
            score = score_by_operation[operation_id]
            # Overlap is an eligibility/readout signal. Select by the typed
            # PF score first, then build only the single whole-packet
            # candidate; hashing the entire FlowView per discarded
            # alternative is both semantically pointless and expensive.
            flow_candidates = (
                self.candidate_factory.build(
                    view, node_id,
                    score.operation, value,
                    bridge_diagnostics=(
                        ("bridge_factor",
                         estimates_by_goal[
                             score.operation
                             .typed_advantages[0].goal_id][
                                 node_id]
                         .bridge_factor),
                        ("transport_overlap", value))),)

            def revalidate(operation, grounding):
                candidate = candidate_by_operation.get(
                    operation.operation_id)
                return bool(
                    candidate is not None
                    and grounding.snapshot_id
                    == query.snapshot_id
                    and grounding.legal_action_digest
                    == query.legal_actions_digest
                    and grounding.action_digest
                    == structural_hash(candidate.action)
                    and candidate.action_key
                    in query.candidate_keys)

            packet = self.packet_integrator.integrate(
                view, flow_candidates,
                score_rows, (
                    PacketBudget(
                        ResourceKind.ACTION, 1),
                    PacketBudget(
                        ResourceKind.CPU, 1),
                ), revalidate=revalidate)
            if not packet.packet_schedule\
                    .committed_operation_ids:
                raise ValueError(
                    "flow could not complete a whole operation packet")
            selected_operation_id = (
                packet.packet_schedule
                .committed_operation_ids[0])
            selected_key = (
                candidate_by_operation[
                    selected_operation_id].action_key)
            scalar_keys = tuple(
                row.action_key for row in ordered)
            ordered_keys = (
                (selected_key,)
                + tuple(
                    key for key in scalar_keys
                    if key != selected_key))
            elapsed_ms = (
                time.perf_counter() - started
            ) * 1000.0
            healthy_batches = tuple(
                row for row in batches
                if row.health.healthy)
            sample = FlowHealthSample.from_components(
                advection_steps=transport.steps,
                projections=projections,
                probe_batches=healthy_batches,
                packet_decision=packet,
                stale_view_lag=0,
                expected_normalization_hash=(
                    default_normalization_contract()
                    .contract_hash),
                observed_normalization_hash=(
                    default_normalization_contract()
                    .contract_hash),
                controller_overhead_ms=elapsed_ms)
            health = self.health_monitor.evaluate(
                sample, require_complete=False)
            if not health.healthy:
                return self._fallback(
                    query, ordered,
                    pressure_artifact,
                    scalar_schedule,
                    "flow-health-unacceptable",
                    started,
                    self._semantic_health(health))
            selected_score = score_by_operation[
                selected_operation_id]
            semantic_health = self._semantic_health(
                health)
            semantic_transport = (
                self._semantic_transport(transport))
            confidence = min(
                (row.health.effective_sample_fraction
                 for row in healthy_batches),
                default=0.5)
            return ControlDecision(
                ordered_candidate_keys=ordered_keys,
                selected_candidate_key=selected_key,
                packet_schedule=(
                    packet.packet_schedule),
                controller_mode="unified_flow",
                artifact={
                    "admissible_candidate_keys": [
                        row.action_key for row
                        in query.grounded_candidates
                        if row.action_key == selected_key],
                    "calibrated": False,
                    "confidence": float(confidence),
                    "controller_identity":
                        self.ENGINE_IDENTITY,
                    "controller_telemetry": {
                        "factor_edge_count": len(
                            view.edges),
                        "factor_node_count": len(
                            view.nodes),
                        "projection_count": len(
                            projections),
                        "total_latency_ms": elapsed_ms,
                        "transport_microseconds_per_edge_update":
                            transport
                            .microseconds_per_edge_update,
                        "transport_microsteps":
                            transport.microsteps,
                        "transport_wall_ms":
                            transport.wall_ms,
                    },
                    "evidence_overlap_valid": True,
                    "expected_resource_use": {
                        row.resource.value: row.quanta
                        for row in selected_score
                        .operation.packet_costs},
                    "flow": {
                        "factorization":
                            factorization.to_dict(),
                        "health": semantic_health,
                        "packet_decision":
                            packet.to_dict(),
                        "probe_batches": [
                            row.to_dict()
                            for row in batches],
                        "projection_results": [
                            row.to_dict()
                            for row in projections],
                        "transport":
                            semantic_transport,
                    },
                    "pressure_artifact":
                        pressure_artifact,
                    "quarantined": False,
                    "query_hash": query.query_hash,
                    "risk": {
                        "penalty": float(
                            selected_score.risk_penalty)},
                    "safety_conflict": False,
                    "typed_advantage": [
                        row.to_dict()
                        for row in selected_score
                        .operation.typed_advantages],
                },
                health="healthy",
                fallback_chain=())
        except (
                ArithmeticError, KeyError,
                RuntimeError, TypeError,
                ValueError) as error:
            return self._fallback(
                query, ordered,
                pressure_artifact,
                scalar_schedule,
                "flow-exception:{}".format(
                    type(error).__name__),
                started, {
                    "exception_message": str(error),
                    "exception_type":
                        type(error).__name__,
                })
