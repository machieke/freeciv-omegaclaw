"""Typed resource and packet scheduling for FDAS shadow operations."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from .packets import PacketBudget, PacketScheduler
from .resource_claims import (
    ClaimHardness,
    GameResourceKind,
    ResourceCapacity,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
)
from .resource_scheduler import (
    BoundedExactScheduler,
    OperationResourceRequest,
)
from .scheduler import PressureScheduler


@dataclass(frozen=True)
class DependentAtomSchedulingResult:
    resource_schedule: object
    packet_schedule: object
    joint_selected_operation_ids: tuple
    diagnostics: tuple
    policy_authority: bool
    artifact_hash: str

    def __post_init__(self):
        if self.policy_authority:
            raise ValueError("FDAS scheduling bridge is shadow-only")
        object.__setattr__(
            self, "joint_selected_operation_ids",
            tuple(sorted(set(self.joint_selected_operation_ids))))
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics))))

    def to_dict(self, include_latency=True):
        return {
            "artifact_hash": self.artifact_hash,
            "diagnostics": list(self.diagnostics),
            "joint_selected_operation_ids": list(
                self.joint_selected_operation_ids),
            "packet_schedule": (
                None if self.packet_schedule is None
                else self.packet_schedule.to_dict()),
            "policy_authority": False,
            "resource_schedule": self.resource_schedule.to_dict(
                include_latency=include_latency),
        }


class DependentAtomSchedulingBridge(object):
    """Fail-closed scheduling over exact identities without reserving them."""

    BRIDGE_IDENTITY = "fdas-resource-packet-shadow/1.0"

    def __init__(self, node_budget=100000, time_budget_ms=None):
        self.resource_scheduler = BoundedExactScheduler(
            node_budget=node_budget, time_budget_ms=time_budget_ms)
        self.packet_scheduler = PacketScheduler()

    @staticmethod
    def _resource_ref(resource_key, player_id):
        prefix, separator, owner_id = str(resource_key).partition(":")
        if not separator or not owner_id:
            return None
        player_scope = "player:{}".format(player_id)
        mapping = {
            "action-budget": (
                GameResourceKind.ACTION_BUDGET,
                player_scope,
                None),
            "city-governor-slot": (
                GameResourceKind.CITY_WORKER_ASSIGNMENT,
                "city:{}".format(owner_id),
                "governor"),
            "city-production-slot": (
                GameResourceKind.CITY_PRODUCTION_SLOT,
                "city:{}".format(owner_id),
                None),
            "player-rate-action": (
                GameResourceKind.ACTION_BUDGET,
                player_scope,
                "player-rates"),
            "research-choice": (
                GameResourceKind.RESEARCH_SLOT,
                player_scope,
                None),
            "unit-action": (
                GameResourceKind.ACTOR,
                "unit:{}".format(owner_id),
                "current-action"),
        }
        row = mapping.get(prefix)
        if row is None:
            return None
        kind, scope, subresource = row
        return ResourceRef(
            kind=kind,
            owner_id=owner_id,
            subresource=subresource,
            scope=scope,
        )

    def schedule(self, evaluation, candidate_operations, snapshot,
                 packet_budgets=None):
        candidate_operations = tuple(candidate_operations)
        candidates = dict(
            (value.operation.operation_id, value)
            for value in candidate_operations)
        if len(candidates) != len(candidate_operations):
            raise ValueError("FDAS scheduling candidates must be unique")
        if evaluation.context.snapshot_id != snapshot.snapshot_id:
            raise ValueError("FDAS scheduling context references stale snapshot")
        if evaluation.context.policy_authority:
            raise ValueError("authoritative FDAS scheduling is unavailable")
        diagnostics = []
        scores = ()
        if evaluation.pressure_result is not None:
            scores = PressureScheduler(
                evaluation.pressure_result.config).score_all(
                    evaluation.context.operations,
                    evaluation.pressure_result)
        score_by_id = dict((value.operation_id, value) for value in scores)
        operation_by_id = dict(
            (value.operation_id, value)
            for value in evaluation.context.operations)
        requests = []
        capacities = {}
        scheduled_operations = []
        window = TurnWindow(snapshot.turn, snapshot.turn + 1)
        for operation in evaluation.context.operations:
            if operation.mode != "act":
                continue
            candidate = candidates.get(operation.operation_id)
            if candidate is None:
                diagnostics.append(
                    "operation-candidate-unavailable:{}".format(
                        operation.operation_id))
                continue
            refs = tuple(
                self._resource_ref(value, snapshot.player_id)
                for value in candidate.resource_keys)
            if not refs or any(value is None for value in refs):
                diagnostics.append(
                    "unmapped-resource-identity:{}".format(
                        operation.operation_id))
                continue
            step_id = candidate.operation.steps[0].step_id
            claims = tuple(ResourceClaim(
                resource=value,
                quantity=1,
                window=window,
                hardness=ClaimHardness.HARD_CURRENT,
                exclusive=True,
                source_operation_id=operation.operation_id,
                source_step_id=step_id,
            ) for value in refs)
            score = score_by_id[operation.operation_id]
            requests.append(OperationResourceRequest(
                operation.operation_id,
                max(0.0, float(score.priority)),
                claims,
                requirement_set_id=None,
            ))
            scheduled_operations.append(operation)
            for resource in refs:
                capacities[resource] = ResourceCapacity(
                    resource=resource,
                    quantity=1,
                    window=window,
                    snapshot_id=snapshot.snapshot_id,
                    authority="server-legal-action-identity",
                )
        resource_schedule = self.resource_scheduler.schedule(
            tuple(requests),
            tuple(capacities[key] for key in sorted(
                capacities, key=lambda value: value.sort_key)),
        )
        if packet_budgets is None:
            packet_schedule = None
            diagnostics.append("packet-budgets-not-provided")
            packet_selected = frozenset(operation_by_id)
        else:
            packet_budgets = tuple(packet_budgets)
            if any(not isinstance(value, PacketBudget)
                   for value in packet_budgets):
                raise TypeError("FDAS packet budgets must be PacketBudget")
            selected_ids = {value.operation_id for value in scheduled_operations}
            selected_scores = tuple(
                value for value in scores if value.operation_id in selected_ids)
            packet_schedule = self.packet_scheduler.schedule(
                tuple(scheduled_operations),
                selected_scores,
                packet_budgets,
            )
            packet_selected = frozenset(
                packet_schedule.committed_operation_ids)
        joint = tuple(sorted(
            set(resource_schedule.selected_operation_ids).intersection(
                packet_selected)))
        semantic = {
            "bridge_identity": self.BRIDGE_IDENTITY,
            "diagnostics": sorted(set(diagnostics)),
            "joint_selected_operation_ids": list(joint),
            "packet_schedule": (
                None if packet_schedule is None
                else packet_schedule.to_dict()),
            "policy_authority": False,
            "resource_schedule_digest": resource_schedule.decision_digest,
            "snapshot_id": snapshot.snapshot_id,
        }
        return DependentAtomSchedulingResult(
            resource_schedule,
            packet_schedule,
            joint,
            tuple(diagnostics),
            False,
            structural_hash(semantic),
        )
