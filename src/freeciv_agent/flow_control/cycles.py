"""Explicit closure policies for open paths and attentional cycles."""

from dataclasses import dataclass
from enum import Enum

from .model import FlowEdgeKind, FlowProcess, FlowView
from .probes import ProbePath


class ClosurePolicy(str, Enum):
    KNOWN_SPLICE = "known_splice"
    RESERVOIR_RETURN = "reservoir_return"
    SOURCE_SINK_OPEN = "source_sink_open"
    PROJECTION_FALLBACK = "projection_fallback"


@dataclass(frozen=True)
class PathClosure:
    path_id: str
    policy: ClosurePolicy
    path_edge_ids: tuple
    closure_edge_ids: tuple
    boundary_vector: tuple
    resource_accounting_only: bool
    fallback_used: bool
    nonzero_route_preserved: bool

    def __post_init__(self):
        if not isinstance(self.policy, ClosurePolicy):
            object.__setattr__(
                self, "policy", ClosurePolicy(self.policy))
        if abs(sum(
                value for _, value
                in self.boundary_vector)) > 1e-12:
            raise ValueError(
                "path closure boundary must balance")
        if (self.policy == ClosurePolicy.SOURCE_SINK_OPEN
                and self.closure_edge_ids):
            raise ValueError(
                "source-sink paths have no explicit return edge")
        if (self.policy == ClosurePolicy.RESERVOIR_RETURN
                and not self.resource_accounting_only):
            raise ValueError(
                "reservoir closure is accounting only")

    def to_dict(self):
        return {
            "boundary_vector": [
                {"node_id": node_id, "value": float(value)}
                for node_id, value in self.boundary_vector],
            "closure_edge_ids": list(self.closure_edge_ids),
            "fallback_used": self.fallback_used,
            "nonzero_route_preserved": self.nonzero_route_preserved,
            "path_edge_ids": list(self.path_edge_ids),
            "path_id": self.path_id,
            "policy": self.policy.value,
            "resource_accounting_only": (
                self.resource_accounting_only),
        }


class CycleClosurePlanner:
    """Close only through declared edges; preserve open tree paths."""

    def close(self, view, path, policy, closure_edge_id=None):
        if not isinstance(view, FlowView):
            raise TypeError(
                "closure planner requires FlowView")
        if not isinstance(path, ProbePath):
            raise TypeError(
                "closure planner requires ProbePath")
        if path.topology_generation != view.topology_generation:
            raise ValueError(
                "cannot close stale probe path")
        if not isinstance(policy, ClosurePolicy):
            policy = ClosurePolicy(policy)
        start = path.node_ids[0]
        end = path.node_ids[-1]
        boundary = (
            () if start == end else
            tuple(sorted(((start, 1.0), (end, -1.0)))))
        if policy in (
                ClosurePolicy.SOURCE_SINK_OPEN,
                ClosurePolicy.PROJECTION_FALLBACK):
            return PathClosure(
                path.path_id,
                ClosurePolicy.SOURCE_SINK_OPEN,
                path.edge_ids, (), boundary,
                resource_accounting_only=False,
                fallback_used=(
                    policy == ClosurePolicy.PROJECTION_FALLBACK),
                nonzero_route_preserved=bool(path.edge_ids))
        if closure_edge_id is None:
            raise ValueError(
                "explicit closure requires closure edge")
        edge = view.edge(closure_edge_id)
        if (edge.source_node_id != end
                or edge.target_node_id != start):
            raise ValueError(
                "closure edge must return end to start")
        if policy == ClosurePolicy.RESERVOIR_RETURN:
            if (edge.kind != FlowEdgeKind.RESOURCE_RETURN
                    or not edge.legality.allows(
                        FlowProcess.RESOURCE_ACCOUNTING)):
                raise ValueError(
                    "reservoir closure requires resource-return edge")
            return PathClosure(
                path.path_id, policy, path.edge_ids,
                (edge.stable_id,), (),
                resource_accounting_only=True,
                fallback_used=False,
                nonzero_route_preserved=bool(path.edge_ids))
        if (edge.kind != FlowEdgeKind.SPLICE
                or not (
                    edge.legality.probe_forward
                    or edge.legality.probe_backward)):
            raise ValueError(
                "known closure requires legal splice edge")
        return PathClosure(
            path.path_id, policy, path.edge_ids,
            (edge.stable_id,), (),
            resource_accounting_only=False,
            fallback_used=False,
            nonzero_route_preserved=bool(path.edge_ids))
