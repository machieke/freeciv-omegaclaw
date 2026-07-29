"""Ordered bounded-staleness updates for immutable flow views."""

from dataclasses import dataclass, replace
import threading

from ..events.schema import structural_hash
from .model import (
    CandidateGrounding,
    FlowEdge,
    FlowEdgeKind,
    FlowLegality,
    FlowNode,
    FlowNodeKind,
    FlowView,
)


STRUCTURAL_PATCHES = frozenset((
    "AddNode",
    "AddEdge",
    "RetireNode",
    "RetireEdge",
))
SCALAR_PATCHES = frozenset((
    "UpdateTruthSummary",
    "UpdateCompatibility",
    "UpdateCost",
    "UpdateConductance",
    "UpdateCapacity",
))
INVALIDATION_PATCHES = frozenset((
    "GoalChanged",
    "ContextInvalidated",
    "CloneGenerationChanged",
))
SUPPORTED_PATCHES = (
    STRUCTURAL_PATCHES
    | SCALAR_PATCHES
    | INVALIDATION_PATCHES)
_FORBIDDEN_COMMIT_KEYS = frozenset((
    "commit",
    "execute",
    "execution_authority",
    "materialize_plan",
    "send_action",
    "truth_mutation",
    "write_evidence",
))


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _nonnegative_int(value, name):
    if (isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0):
        raise ValueError(
            "{} must be a non-negative integer".format(name))
    return value


def _find_forbidden_key(value):
    if isinstance(value, dict):
        for key, child in value.items():
            key = str(key).lower()
            if key in _FORBIDDEN_COMMIT_KEYS:
                return key
            nested = _find_forbidden_key(child)
            if nested:
                return nested
    elif isinstance(value, (tuple, list)):
        for child in value:
            nested = _find_forbidden_key(child)
            if nested:
                return nested
    return None


@dataclass(frozen=True)
class FlowPatch:
    sequence_number: int
    semantic_epoch: int
    operation: str
    stable_ids: tuple
    payload: dict
    schema_version: str = "flow-patch/1.0"

    def __post_init__(self):
        _nonnegative_int(
            self.sequence_number, "patch sequence")
        _nonnegative_int(
            self.semantic_epoch, "patch semantic epoch")
        if self.operation not in SUPPORTED_PATCHES:
            raise ValueError(
                "unsupported flow patch operation")
        if (not isinstance(self.stable_ids, tuple)
                or not self.stable_ids
                or len(set(self.stable_ids))
                != len(self.stable_ids)
                or any(not isinstance(value, str) or not value
                       for value in self.stable_ids)):
            raise ValueError(
                "patch stable IDs must be a unique nonempty tuple")
        if not isinstance(self.payload, dict):
            raise TypeError(
                "patch payload must be an object")
        forbidden = _find_forbidden_key(self.payload)
        if forbidden:
            raise ValueError(
                "flow patch cannot perform semantic commit: "
                "{}".format(forbidden))

    @property
    def patch_hash(self):
        return structural_hash(self.to_dict())

    @property
    def structural(self):
        return self.operation in STRUCTURAL_PATCHES

    @property
    def coalescible(self):
        return self.operation in SCALAR_PATCHES

    def to_dict(self):
        return {
            "operation": self.operation,
            "payload": dict(self.payload),
            "schema_version": self.schema_version,
            "semantic_epoch": self.semantic_epoch,
            "sequence_number": self.sequence_number,
            "stable_ids": list(self.stable_ids),
        }


@dataclass(frozen=True)
class FlowSafePointResult:
    applied_sequence_numbers: tuple
    duplicate_sequence_numbers: tuple
    coalesced_sequence_numbers: tuple
    deferred_structural_count: int
    structural_applied: int
    scalar_applied: int
    semantic_epoch: int
    topology_generation: int
    truth_mutations: int = 0
    semantic_commits: int = 0

    def __post_init__(self):
        if self.truth_mutations or self.semantic_commits:
            raise ValueError(
                "flow safe point cannot commit semantics")

    def to_dict(self):
        return {
            "applied_sequence_numbers": list(
                self.applied_sequence_numbers),
            "coalesced_sequence_numbers": list(
                self.coalesced_sequence_numbers),
            "deferred_structural_count":
                self.deferred_structural_count,
            "duplicate_sequence_numbers": list(
                self.duplicate_sequence_numbers),
            "scalar_applied": self.scalar_applied,
            "semantic_commits": self.semantic_commits,
            "semantic_epoch": self.semantic_epoch,
            "structural_applied": self.structural_applied,
            "topology_generation":
                self.topology_generation,
            "truth_mutations": self.truth_mutations,
        }


class BoundedFlowViewOwner:
    """Single-writer overlay and deterministic-rebuild owner."""

    OWNER_IDENTITY = "bounded-flow-view-owner/1.0"

    def __init__(self, base_view):
        if not isinstance(base_view, FlowView):
            raise TypeError(
                "flow patch owner requires FlowView")
        self._base = base_view
        self._base_hash = base_view.to_dict()["view_hash"]
        self._writer_thread = threading.get_ident()
        self._accepted_hashes = {}
        self._next_sequence = 0
        self._pending = []
        self._added_nodes = {}
        self._added_edges = {}
        self._retired_nodes = set()
        self._retired_edges = set()
        self._scalar_overlay = {}
        self._semantic_epoch = base_view.semantic_epoch
        self._topology_generation = (
            base_view.topology_generation)
        self._context_digest = base_view.context_digest
        self._clone_generation = base_view.clone_generation

    @property
    def immutable_base_hash(self):
        return self._base_hash

    @property
    def pending_count(self):
        return len(self._pending)

    @property
    def scalar_overlay(self):
        return dict(self._scalar_overlay)

    def _assert_writer(self):
        if threading.get_ident() != self._writer_thread:
            raise RuntimeError(
                "flow patches require single-writer ownership")

    def submit(self, patches):
        """Accept an exact ordered prefix; identical retries are idempotent."""
        self._assert_writer()
        patches = tuple(patches)
        duplicates = []
        accepted_hashes = dict(self._accepted_hashes)
        next_sequence = self._next_sequence
        pending = []
        for patch in patches:
            if not isinstance(patch, FlowPatch):
                raise TypeError(
                    "flow patch queue requires FlowPatch")
            known = accepted_hashes.get(
                patch.sequence_number)
            if known is not None:
                if known != patch.patch_hash:
                    raise ValueError(
                        "patch sequence replay conflicts with "
                        "accepted content")
                duplicates.append(
                    patch.sequence_number)
                continue
            if patch.sequence_number != next_sequence:
                raise ValueError(
                    "flow patch sequence gap: expected {}, got {}".format(
                        next_sequence,
                        patch.sequence_number))
            accepted_hashes[
                patch.sequence_number] = patch.patch_hash
            next_sequence += 1
            pending.append(patch)
        self._accepted_hashes = accepted_hashes
        self._next_sequence = next_sequence
        self._pending.extend(pending)
        return tuple(duplicates)

    @staticmethod
    def _node_from_patch(patch):
        payload = dict(patch.payload)
        node = FlowNode(
            local_id=0,
            stable_id=patch.stable_ids[0],
            kind=FlowNodeKind(payload.pop("kind")),
            semantic_generation=patch.semantic_epoch,
            topology_generation=0,
            context_digest=_required_text(
                payload.pop("context_digest"),
                "added node context"),
            clone_generation=int(
                payload.pop("clone_generation", 0)),
            source=_required_text(
                payload.pop("source"),
                "added node source"),
            provenance_ids=tuple(
                payload.pop("provenance_ids", ())),
            born_generation=0,
            retired_generation=None,
            active=bool(payload.pop("active", True)),
            semantic_role=payload.pop(
                "semantic_role", None),
            payload_digest=payload.pop(
                "payload_digest", None),
            evidence_mirror=bool(
                payload.pop("evidence_mirror", False)),
            committable=bool(
                payload.pop("committable", False)))
        if node.committable:
            raise ValueError(
                "patch-added nodes cannot be committable")
        if payload:
            raise ValueError(
                "unknown added-node patch fields: {}".format(
                    ", ".join(sorted(payload))))
        return node

    @staticmethod
    def _edge_from_patch(patch):
        payload = dict(patch.payload)
        legality = payload.pop("legality")
        if isinstance(legality, dict):
            legality = FlowLegality(**legality)
        edge = FlowEdge(
            local_id=0,
            stable_id=patch.stable_ids[0],
            source_node_id=_required_text(
                payload.pop("source_node_id"),
                "added edge source node"),
            target_node_id=_required_text(
                payload.pop("target_node_id"),
                "added edge target node"),
            kind=FlowEdgeKind(payload.pop("kind")),
            legality=legality,
            semantic_generation=patch.semantic_epoch,
            topology_generation=0,
            context_digest=_required_text(
                payload.pop("context_digest"),
                "added edge context"),
            clone_generation=int(
                payload.pop("clone_generation", 0)),
            source=_required_text(
                payload.pop("source"),
                "added edge source"),
            provenance_ids=tuple(
                payload.pop("provenance_ids", ())),
            born_generation=0,
            retired_generation=None,
            control_weight=float(
                payload.pop("control_weight", 1.0)))
        if payload:
            raise ValueError(
                "unknown added-edge patch fields: {}".format(
                    ", ".join(sorted(payload))))
        return edge

    def _apply_structural(self, patch):
        stable_id = patch.stable_ids[0]
        if patch.operation == "AddNode":
            known = {
                row.stable_id for row in self._base.nodes
            } | set(self._added_nodes)
            if (stable_id in known
                    and stable_id not in self._retired_nodes):
                raise ValueError(
                    "cannot add duplicate flow node")
            self._added_nodes[stable_id] = (
                self._node_from_patch(patch))
            self._retired_nodes.discard(stable_id)
        elif patch.operation == "AddEdge":
            known = {
                row.stable_id for row in self._base.edges
            } | set(self._added_edges)
            if (stable_id in known
                    and stable_id not in self._retired_edges):
                raise ValueError(
                    "cannot add duplicate flow edge")
            self._added_edges[stable_id] = (
                self._edge_from_patch(patch))
            self._retired_edges.discard(stable_id)
        elif patch.operation == "RetireNode":
            self._retired_nodes.add(stable_id)
            self._added_nodes.pop(stable_id, None)
        elif patch.operation == "RetireEdge":
            self._retired_edges.add(stable_id)
            self._added_edges.pop(stable_id, None)
        self._topology_generation += 1

    def _apply_scalar_or_invalidation(self, patch):
        if patch.operation in SCALAR_PATCHES:
            for stable_id in patch.stable_ids:
                self._scalar_overlay[(
                    patch.operation, stable_id)] = dict(
                        patch.payload)
        elif patch.operation == "GoalChanged":
            self._scalar_overlay[(
                patch.operation, patch.stable_ids[0])] = dict(
                    patch.payload)
        elif patch.operation == "ContextInvalidated":
            context = patch.payload.get("context_digest")
            if context is not None:
                self._context_digest = _required_text(
                    context, "updated context digest")
            self._scalar_overlay[(
                patch.operation, patch.stable_ids[0])] = dict(
                    patch.payload)
        elif patch.operation == "CloneGenerationChanged":
            generation = patch.payload.get(
                "clone_generation")
            self._clone_generation = _nonnegative_int(
                generation, "updated clone generation")
        self._semantic_epoch = max(
            self._semantic_epoch,
            patch.semantic_epoch)

    def apply_safe_point(
            self, patches=(),
            maximum_structural_patches=8):
        """Apply scalar coalescing and a bounded structural prefix."""
        self._assert_writer()
        maximum_structural_patches = _nonnegative_int(
            maximum_structural_patches,
            "safe-point structural bound")
        duplicates = self.submit(patches)
        coalesced = []
        latest_scalar = {}
        for patch in self._pending:
            if patch.coalescible:
                for stable_id in patch.stable_ids:
                    key = (patch.operation, stable_id)
                    previous = latest_scalar.get(key)
                    if previous is not None:
                        coalesced.append(
                            previous.sequence_number)
                    latest_scalar[key] = patch
        keep_scalars = frozenset(
            patch.sequence_number
            for patch in latest_scalar.values())
        retained = []
        applied = []
        structural_applied = 0
        scalar_applied = 0
        for patch in self._pending:
            if patch.coalescible:
                if patch.sequence_number in keep_scalars:
                    self._apply_scalar_or_invalidation(patch)
                    scalar_applied += 1
                applied.append(patch.sequence_number)
            elif patch.structural:
                if structural_applied < maximum_structural_patches:
                    self._apply_structural(patch)
                    self._semantic_epoch = max(
                        self._semantic_epoch,
                        patch.semantic_epoch)
                    structural_applied += 1
                    applied.append(patch.sequence_number)
                else:
                    retained.append(patch)
            else:
                self._apply_scalar_or_invalidation(patch)
                scalar_applied += 1
                applied.append(patch.sequence_number)
        self._pending = retained
        return FlowSafePointResult(
            applied_sequence_numbers=tuple(applied),
            duplicate_sequence_numbers=duplicates,
            coalesced_sequence_numbers=tuple(sorted(
                set(coalesced))),
            deferred_structural_count=len(retained),
            structural_applied=structural_applied,
            scalar_applied=scalar_applied,
            semantic_epoch=self._semantic_epoch,
            topology_generation=self._topology_generation)

    def materialize(self):
        """Return a generation-consistent immutable view of the overlays."""
        self._assert_writer()
        retired_nodes = frozenset(
            self._retired_nodes)
        nodes_by_id = dict(
            (row.stable_id, row)
            for row in self._base.nodes
            if row.stable_id not in retired_nodes)
        nodes_by_id.update(self._added_nodes)
        nodes = tuple(
            replace(
                row,
                local_id=index,
                semantic_generation=self._semantic_epoch,
                topology_generation=self._topology_generation,
                context_digest=self._context_digest,
                clone_generation=self._clone_generation,
                born_generation=min(
                    row.born_generation,
                    self._topology_generation))
            for index, row in enumerate(sorted(
                nodes_by_id.values(),
                key=lambda item: item.stable_id)))
        node_ids = frozenset(
            row.stable_id for row in nodes)
        edges_by_id = dict(
            (row.stable_id, row)
            for row in self._base.edges
            if (row.stable_id not in self._retired_edges
                and row.source_node_id in node_ids
                and row.target_node_id in node_ids))
        edges_by_id.update(dict(
            (stable_id, row)
            for stable_id, row
            in self._added_edges.items()
            if (row.source_node_id in node_ids
                and row.target_node_id in node_ids)))
        edges = tuple(
            replace(
                row,
                local_id=index,
                semantic_generation=self._semantic_epoch,
                topology_generation=self._topology_generation,
                context_digest=self._context_digest,
                clone_generation=self._clone_generation,
                born_generation=min(
                    row.born_generation,
                    self._topology_generation))
            for index, row in enumerate(sorted(
                edges_by_id.values(),
                key=lambda item: item.stable_id)))
        groundings = tuple(
            replace(
                row,
                semantic_epoch=self._semantic_epoch,
                topology_generation=self._topology_generation)
            for row in self._base.candidate_groundings
            if row.operation_node_id in node_ids)
        frontier = tuple(sorted(
            row.stable_id for row in nodes
            if row.kind == FlowNodeKind.FRONTIER_STUB))
        return FlowView(
            query_id=self._base.query_id,
            snapshot_id=self._base.snapshot_id,
            legal_action_digest=(
                self._base.legal_action_digest),
            semantic_epoch=self._semantic_epoch,
            topology_generation=self._topology_generation,
            context_digest=self._context_digest,
            clone_generation=self._clone_generation,
            nodes=nodes,
            edges=edges,
            candidate_groundings=groundings,
            frontier_stub_ids=frontier,
            materialization_budget=(
                self._base.materialization_budget))

    def rebuild(self):
        """Compact overlays into a new immutable base deterministically."""
        self._assert_writer()
        rebuilt = self.materialize()
        self._base = rebuilt
        self._base_hash = rebuilt.to_dict()["view_hash"]
        self._added_nodes.clear()
        self._added_edges.clear()
        self._retired_nodes.clear()
        self._retired_edges.clear()
        return rebuilt
