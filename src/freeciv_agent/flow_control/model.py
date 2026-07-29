"""Immutable query-local graph contracts for bridge and flow control.

The graph in this package is a control view.  Its nodes, edges, potentials,
and local handles are never evidence and cannot authorize an external action.
Durable identity is always semantic and generation-tagged; dense local IDs
exist only to support bounded numerical work inside one topology generation.
"""

import math
from dataclasses import dataclass
from enum import Enum

from ..events.schema import structural_hash


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _generation(value, name):
    if (isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0):
        raise ValueError(
            "{} must be a non-negative integer".format(name))
    return value


def _local_id(value, name):
    return _generation(value, name)


def _finite_nonnegative(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(
            "{} must be finite and non-negative".format(name))
    return value


class FlowNodeKind(str, Enum):
    PROPOSITION = "proposition"
    RULE_FACTOR = "rule_factor"
    REQUIREMENT_SET = "requirement_set"
    OPERATION = "operation"
    LIFECYCLE = "lifecycle"
    FORWARD_BOUNDARY = "forward_boundary"
    BACKWARD_BOUNDARY = "backward_boundary"
    RESERVOIR = "reservoir"
    FRONTIER_STUB = "frontier_stub"
    SHARD_PORTAL = "shard_portal"


class FlowEdgeKind(str, Enum):
    FORWARD_TRUTH = "forward_truth"
    BACKWARD_DEMAND = "backward_demand"
    PROBE_FORWARD = "probe_forward"
    PROBE_BACKWARD = "probe_backward"
    ASSOCIATIVE = "associative"
    OPERATION_INVOKE = "operation_invoke"
    LIFECYCLE = "lifecycle"
    RESOURCE_RETURN = "resource_return"
    SHARD_TRANSFER = "shard_transfer"
    SPLICE = "splice"
    EXPANSION = "expansion"


class FlowProcess(str, Enum):
    """Transition sets that must remain independent on a shared graph."""

    FORWARD_TRUTH = "forward_truth"
    BACKWARD_DEMAND = "backward_demand"
    PROBE_FORWARD = "probe_forward"
    PROBE_BACKWARD = "probe_backward"
    CAUSAL_PLANNING = "causal_planning"
    ASSOCIATIVE_TRAVERSAL = "associative_traversal"
    OPERATION_INVOCATION = "operation_invocation"
    LIFECYCLE_TRANSITION = "lifecycle_transition"
    RESOURCE_ACCOUNTING = "resource_accounting"
    EXPANSION = "expansion"


@dataclass(frozen=True)
class FlowLegality:
    """Explicit process-specific edge legality.

    Backward legality has no inferred default.  A caller must opt each process
    in, which prevents reverse probes and resource-return edges from silently
    becoming proof or causal transitions.
    """

    forward_truth: bool = False
    backward_demand: bool = False
    probe_forward: bool = False
    probe_backward: bool = False
    causal_planning: bool = False
    associative_traversal: bool = False
    operation_invocation: bool = False
    lifecycle_transition: bool = False
    resource_accounting: bool = False
    expansion: bool = False

    def __post_init__(self):
        for name in (
                "forward_truth", "backward_demand",
                "probe_forward", "probe_backward",
                "causal_planning", "associative_traversal",
                "operation_invocation", "lifecycle_transition",
                "resource_accounting", "expansion"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(
                    "{} legality must be boolean".format(name))

    def allows(self, process):
        if not isinstance(process, FlowProcess):
            process = FlowProcess(process)
        return bool(getattr(self, process.value))

    @property
    def enabled_processes(self):
        return tuple(
            process.value for process in FlowProcess
            if self.allows(process))

    def to_dict(self):
        return dict(
            (process.value, self.allows(process))
            for process in FlowProcess)


@dataclass(frozen=True)
class FlowNode:
    local_id: int
    stable_id: str
    kind: FlowNodeKind
    semantic_generation: int
    topology_generation: int
    context_digest: str
    clone_generation: int
    source: str
    provenance_ids: tuple = ()
    born_generation: int = 0
    retired_generation: object = None
    active: bool = True

    def __post_init__(self):
        _local_id(self.local_id, "node local ID")
        _required_text(self.stable_id, "node stable ID")
        if not isinstance(self.kind, FlowNodeKind):
            object.__setattr__(self, "kind", FlowNodeKind(self.kind))
        _generation(
            self.semantic_generation, "node semantic generation")
        _generation(
            self.topology_generation, "node topology generation")
        _required_text(self.context_digest, "node context digest")
        _generation(self.clone_generation, "node clone generation")
        _required_text(self.source, "node source")
        if (not isinstance(self.provenance_ids, tuple)
                or any(not isinstance(value, str) or not value
                       for value in self.provenance_ids)
                or len(set(self.provenance_ids))
                != len(self.provenance_ids)):
            raise ValueError(
                "node provenance IDs must be a unique tuple")
        _generation(self.born_generation, "node born generation")
        if self.retired_generation is not None:
            _generation(
                self.retired_generation,
                "node retired generation")
            if self.retired_generation < self.born_generation:
                raise ValueError(
                    "node cannot retire before it is born")
        if not isinstance(self.active, bool):
            raise TypeError("node active state must be boolean")
        if (self.kind in (
                FlowNodeKind.RESERVOIR,
                FlowNodeKind.SHARD_PORTAL)
                and self.active):
            raise ValueError(
                "{} nodes are inactive in Stage S3".format(
                    self.kind.value))

    def to_dict(self):
        """Return durable fields only; local_id is intentionally omitted."""
        return {
            "active": self.active,
            "born_generation": self.born_generation,
            "clone_generation": self.clone_generation,
            "context_digest": self.context_digest,
            "kind": self.kind.value,
            "provenance_ids": list(self.provenance_ids),
            "retired_generation": self.retired_generation,
            "semantic_generation": self.semantic_generation,
            "source": self.source,
            "stable_id": self.stable_id,
            "topology_generation": self.topology_generation,
        }


@dataclass(frozen=True)
class FlowEdge:
    local_id: int
    stable_id: str
    source_node_id: str
    target_node_id: str
    kind: FlowEdgeKind
    legality: FlowLegality
    semantic_generation: int
    topology_generation: int
    context_digest: str
    clone_generation: int
    source: str
    provenance_ids: tuple = ()
    born_generation: int = 0
    retired_generation: object = None
    control_weight: float = 1.0

    def __post_init__(self):
        _local_id(self.local_id, "edge local ID")
        _required_text(self.stable_id, "edge stable ID")
        _required_text(self.source_node_id, "edge source node ID")
        _required_text(self.target_node_id, "edge target node ID")
        if self.source_node_id == self.target_node_id:
            raise ValueError("flow self edges require an explicit factor node")
        if not isinstance(self.kind, FlowEdgeKind):
            object.__setattr__(self, "kind", FlowEdgeKind(self.kind))
        if not isinstance(self.legality, FlowLegality):
            raise TypeError("edge legality must be FlowLegality")
        _generation(
            self.semantic_generation, "edge semantic generation")
        _generation(
            self.topology_generation, "edge topology generation")
        _required_text(self.context_digest, "edge context digest")
        _generation(self.clone_generation, "edge clone generation")
        _required_text(self.source, "edge source")
        if (not isinstance(self.provenance_ids, tuple)
                or any(not isinstance(value, str) or not value
                       for value in self.provenance_ids)
                or len(set(self.provenance_ids))
                != len(self.provenance_ids)):
            raise ValueError(
                "edge provenance IDs must be a unique tuple")
        _generation(self.born_generation, "edge born generation")
        if self.retired_generation is not None:
            _generation(
                self.retired_generation,
                "edge retired generation")
            if self.retired_generation < self.born_generation:
                raise ValueError(
                    "edge cannot retire before it is born")
        _finite_nonnegative(
            self.control_weight, "edge control weight")
        if (self.kind == FlowEdgeKind.RESOURCE_RETURN
                and any((
                    self.legality.forward_truth,
                    self.legality.backward_demand,
                    self.legality.probe_forward,
                    self.legality.probe_backward,
                    self.legality.causal_planning,
                    self.legality.associative_traversal,
                    self.legality.operation_invocation,
                    self.legality.lifecycle_transition,
                    self.legality.expansion,
                ))):
            raise ValueError(
                "resource-return edges may only carry resource accounting")

    def to_dict(self):
        """Return durable fields only; local_id is intentionally omitted."""
        return {
            "born_generation": self.born_generation,
            "clone_generation": self.clone_generation,
            "context_digest": self.context_digest,
            "control_weight": float(self.control_weight),
            "kind": self.kind.value,
            "legality": self.legality.to_dict(),
            "provenance_ids": list(self.provenance_ids),
            "retired_generation": self.retired_generation,
            "semantic_generation": self.semantic_generation,
            "source": self.source,
            "source_node_id": self.source_node_id,
            "stable_id": self.stable_id,
            "target_node_id": self.target_node_id,
            "topology_generation": self.topology_generation,
        }


@dataclass(frozen=True)
class LocalNodeHandle:
    """Ephemeral node address, valid in exactly one topology generation."""

    local_id: int
    stable_id: str
    topology_generation: int

    def __post_init__(self):
        _local_id(self.local_id, "handle local ID")
        _required_text(self.stable_id, "handle stable ID")
        _generation(
            self.topology_generation,
            "handle topology generation")


@dataclass(frozen=True)
class CandidateGrounding:
    """Durable binding from an operation node to authoritative legality."""

    snapshot_id: str
    legal_action_digest: str
    action_digest: str
    semantic_epoch: int
    topology_generation: int
    actor_id: object
    target_digest: str
    category: str
    operation_node_id: str
    committable: bool = True

    def __post_init__(self):
        _required_text(self.snapshot_id, "candidate snapshot ID")
        _required_text(
            self.legal_action_digest,
            "candidate legal-action digest")
        _required_text(self.action_digest, "candidate action digest")
        _generation(self.semantic_epoch, "candidate semantic epoch")
        _generation(
            self.topology_generation,
            "candidate topology generation")
        _required_text(self.target_digest, "candidate target digest")
        _required_text(self.category, "candidate category")
        _required_text(
            self.operation_node_id,
            "candidate operation node ID")
        if not isinstance(self.committable, bool):
            raise TypeError("candidate committable must be boolean")

    @property
    def grounding_id(self):
        return "candidate-grounding:{}".format(
            structural_hash(self.to_dict()))

    def to_dict(self):
        return {
            "action_digest": self.action_digest,
            "actor_id": self.actor_id,
            "category": self.category,
            "committable": self.committable,
            "legal_action_digest": self.legal_action_digest,
            "operation_node_id": self.operation_node_id,
            "semantic_epoch": self.semantic_epoch,
            "snapshot_id": self.snapshot_id,
            "target_digest": self.target_digest,
            "topology_generation": self.topology_generation,
        }


@dataclass(frozen=True)
class FlowView:
    """One immutable, bounded topology generation for a single query."""

    query_id: str
    snapshot_id: str
    legal_action_digest: str
    semantic_epoch: int
    topology_generation: int
    context_digest: str
    clone_generation: int
    nodes: tuple
    edges: tuple
    candidate_groundings: tuple = ()
    frontier_stub_ids: tuple = ()
    materialization_budget: object = None

    def __post_init__(self):
        _required_text(self.query_id, "flow query ID")
        _required_text(self.snapshot_id, "flow snapshot ID")
        _required_text(
            self.legal_action_digest,
            "flow legal-action digest")
        _generation(self.semantic_epoch, "flow semantic epoch")
        _generation(
            self.topology_generation,
            "flow topology generation")
        _required_text(self.context_digest, "flow context digest")
        _generation(self.clone_generation, "flow clone generation")
        if any(not isinstance(row, FlowNode) for row in self.nodes):
            raise TypeError("flow nodes must contain FlowNode")
        if any(not isinstance(row, FlowEdge) for row in self.edges):
            raise TypeError("flow edges must contain FlowEdge")
        if any(not isinstance(row, CandidateGrounding)
               for row in self.candidate_groundings):
            raise TypeError(
                "candidate groundings must contain CandidateGrounding")
        node_ids = [row.stable_id for row in self.nodes]
        node_locals = [row.local_id for row in self.nodes]
        edge_ids = [row.stable_id for row in self.edges]
        edge_locals = [row.local_id for row in self.edges]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("flow node stable IDs must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("flow edge stable IDs must be unique")
        if sorted(node_locals) != list(range(len(self.nodes))):
            raise ValueError(
                "flow node local IDs must be dense for one generation")
        if sorted(edge_locals) != list(range(len(self.edges))):
            raise ValueError(
                "flow edge local IDs must be dense for one generation")
        node_set = frozenset(node_ids)
        if any(row.source_node_id not in node_set
               or row.target_node_id not in node_set
               for row in self.edges):
            raise ValueError("flow edge references unknown node")
        if any(row.topology_generation != self.topology_generation
               for row in self.nodes + self.edges):
            raise ValueError(
                "all flow rows must match topology generation")
        if any(row.semantic_generation != self.semantic_epoch
               for row in self.nodes + self.edges):
            raise ValueError(
                "all flow rows must match semantic epoch")
        grounding_nodes = [
            row.operation_node_id for row in self.candidate_groundings]
        if (len(grounding_nodes) != len(set(grounding_nodes))
                or any(value not in node_set
                       for value in grounding_nodes)):
            raise ValueError(
                "candidate groundings must uniquely reference flow nodes")
        if any(value not in node_set
               for value in self.frontier_stub_ids):
            raise ValueError("frontier stub references unknown node")
        if any(self.node(value).kind != FlowNodeKind.FRONTIER_STUB
               for value in self.frontier_stub_ids):
            raise ValueError(
                "frontier stub IDs must reference frontier nodes")

    def node(self, stable_id):
        stable_id = str(stable_id)
        try:
            return next(
                row for row in self.nodes
                if row.stable_id == stable_id)
        except StopIteration:
            raise KeyError(stable_id)

    def edge(self, stable_id):
        stable_id = str(stable_id)
        try:
            return next(
                row for row in self.edges
                if row.stable_id == stable_id)
        except StopIteration:
            raise KeyError(stable_id)

    def local_handle(self, stable_id):
        node = self.node(stable_id)
        return LocalNodeHandle(
            node.local_id, node.stable_id,
            self.topology_generation)

    def resolve(self, handle):
        if not isinstance(handle, LocalNodeHandle):
            raise TypeError(
                "flow resolution requires LocalNodeHandle")
        if handle.topology_generation != self.topology_generation:
            raise ValueError(
                "stale local handle topology generation")
        if not 0 <= handle.local_id < len(self.nodes):
            raise ValueError("local handle is outside this view")
        node = self.nodes[handle.local_id]
        if node.stable_id != handle.stable_id:
            raise ValueError(
                "local handle stable identity mismatch")
        return node

    def legal_edges(self, process):
        if not isinstance(process, FlowProcess):
            process = FlowProcess(process)
        return tuple(
            row for row in self.edges
            if row.legality.allows(process))

    def to_dict(self):
        material = {
            "candidate_groundings": [
                row.to_dict()
                for row in self.candidate_groundings],
            "clone_generation": self.clone_generation,
            "context_digest": self.context_digest,
            "edges": [row.to_dict() for row in self.edges],
            "frontier_stub_ids": list(self.frontier_stub_ids),
            "legal_action_digest": self.legal_action_digest,
            "materialization_budget": self.materialization_budget,
            "nodes": [row.to_dict() for row in self.nodes],
            "query_id": self.query_id,
            "schema_version": "1.0",
            "semantic_epoch": self.semantic_epoch,
            "snapshot_id": self.snapshot_id,
            "topology_generation": self.topology_generation,
        }
        material["view_hash"] = structural_hash(material)
        return material
