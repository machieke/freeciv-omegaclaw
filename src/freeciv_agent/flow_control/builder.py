"""Deterministic construction of bounded query-local control graphs."""

from dataclasses import dataclass

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


def _bounded_integer(value, name, minimum=0):
    if (isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum):
        raise ValueError(
            "{} must be an integer >= {}".format(
                name, minimum))
    return value


@dataclass(frozen=True)
class FlowBuildBudget:
    max_nodes: int = 512
    max_edges: int = 2048
    max_candidates: int = 256
    max_frontier_stubs: int = 8

    def __post_init__(self):
        _bounded_integer(self.max_nodes, "maximum nodes", 1)
        _bounded_integer(self.max_edges, "maximum edges")
        _bounded_integer(
            self.max_candidates, "maximum candidates")
        _bounded_integer(
            self.max_frontier_stubs,
            "maximum frontier stubs")

    def to_dict(self):
        return {
            "max_candidates": self.max_candidates,
            "max_edges": self.max_edges,
            "max_frontier_stubs": self.max_frontier_stubs,
            "max_nodes": self.max_nodes,
        }


@dataclass(frozen=True)
class FlowBuildRejection:
    action_digest: str
    category: str
    reason: str

    def to_dict(self):
        return {
            "action_digest": self.action_digest,
            "category": self.category,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FlowBuildResult:
    view: FlowView
    rejections: tuple
    legal_candidate_count: int
    materialized_candidate_count: int
    budget_exhausted: bool

    def __post_init__(self):
        if not isinstance(self.view, FlowView):
            raise TypeError("build result view must be FlowView")
        if any(not isinstance(row, FlowBuildRejection)
               for row in self.rejections):
            raise TypeError(
                "build rejections must contain FlowBuildRejection")

    def to_dict(self):
        material = {
            "budget_exhausted": self.budget_exhausted,
            "legal_candidate_count": self.legal_candidate_count,
            "materialized_candidate_count": (
                self.materialized_candidate_count),
            "rejections": [
                row.to_dict() for row in self.rejections],
            "schema_version": "1.0",
            "view": self.view.to_dict(),
        }
        material["artifact_hash"] = structural_hash(material)
        return material


class QueryLocalFlowBuilder:
    """Build the Stage-S3 operation shell from authoritative candidates.

    The builder does not infer legality.  An operation node is committable only
    when its canonical action is present in the snapshot's exact advertised
    legal-action set.  Deeper rule and requirement factors are added by later
    factorization stages.
    """

    BUILDER_IDENTITY = "freeciv-query-local-flow-builder/1.0"

    def __init__(self, budget=None):
        self.budget = (
            budget if budget is not None else FlowBuildBudget())
        if not isinstance(self.budget, FlowBuildBudget):
            raise TypeError(
                "flow build budget must be FlowBuildBudget")

    @staticmethod
    def _candidate_row(candidate):
        action = getattr(candidate, "action", None)
        category = getattr(candidate, "category", None)
        action_key = getattr(candidate, "action_key", None)
        if not isinstance(action, dict):
            raise TypeError(
                "flow candidates must expose an action dictionary")
        if not isinstance(category, str) or not category:
            raise ValueError(
                "flow candidates must expose a category")
        if not isinstance(action_key, str) or not action_key:
            raise ValueError(
                "flow candidates must expose a canonical action key")
        return (
            action_key, category,
            structural_hash(action), candidate)

    @staticmethod
    def _target_digest(action):
        target = action.get("target")
        if target is None:
            target = dict(
                (key, action[key]) for key in sorted(action)
                if key not in ("actor_id", "action_id"))
        return structural_hash(target)

    @staticmethod
    def _actor_id(action):
        return action.get(
            "actor_id", action.get("city_id"))

    def build(
            self, query_id, snapshot, candidates,
            goal_ids=(), goal_by_category=None,
            semantic_epoch=0, topology_generation=0,
            clone_generation=0, context_digest=None):
        if not isinstance(query_id, str) or not query_id:
            raise ValueError("flow query ID is required")
        for name, value in (
                ("semantic epoch", semantic_epoch),
                ("topology generation", topology_generation),
                ("clone generation", clone_generation)):
            _bounded_integer(value, name)
        snapshot_id = getattr(snapshot, "snapshot_id", None)
        legal_action_digest = getattr(
            snapshot, "legal_actions_digest", None)
        legal_action_json = getattr(
            snapshot, "legal_action_json", None)
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise TypeError(
                "flow snapshot must expose snapshot_id")
        if (not isinstance(legal_action_digest, str)
                or not legal_action_digest):
            raise TypeError(
                "flow snapshot must expose legal_actions_digest")
        if not isinstance(legal_action_json, tuple):
            raise TypeError(
                "flow snapshot legal_action_json must be a tuple")
        goals = tuple(sorted(set(str(value) for value in goal_ids)))
        if any(not value for value in goals):
            raise ValueError("flow goal IDs must be nonempty")
        category_goal = dict(goal_by_category or {})
        if any(not isinstance(key, str)
               or not isinstance(value, str)
               or value not in goals
               for key, value in category_goal.items()):
            raise ValueError(
                "category goals must reference declared goal IDs")
        context_digest = (
            str(context_digest)
            if context_digest is not None else structural_hash({
                "clone_generation": clone_generation,
                "goals": list(goals),
                "legal_action_digest": legal_action_digest,
                "query_id": query_id,
                "snapshot_id": snapshot_id,
            }))
        if not context_digest:
            raise ValueError("flow context digest is required")

        legal_keys = frozenset(legal_action_json)
        rows = sorted(
            (self._candidate_row(candidate)
             for candidate in tuple(candidates)),
            key=lambda row: (
                row[0], row[1], row[2]))
        rejections = []
        legal_rows = []
        observed_actions = set()
        for action_key, category, action_digest, candidate in rows:
            if action_key not in legal_keys:
                rejections.append(FlowBuildRejection(
                    action_digest, category,
                    "not_authoritative_legal_action"))
                continue
            if action_digest in observed_actions:
                rejections.append(FlowBuildRejection(
                    action_digest, category,
                    "duplicate_authoritative_action"))
                continue
            observed_actions.add(action_digest)
            legal_rows.append((
                action_key, category,
                action_digest, candidate))

        forward_id = "flow:forward-boundary:{}".format(
            structural_hash({
                "legal_action_digest": legal_action_digest,
                "snapshot_id": snapshot_id,
            }))
        goal_node_ids = dict(
            (goal_id, "flow:backward-boundary:{}".format(
                structural_hash({
                    "goal_id": goal_id,
                    "query_id": query_id,
                    "snapshot_id": snapshot_id,
                })))
            for goal_id in goals)
        base_nodes = 1 + len(goal_node_ids)
        if base_nodes > self.budget.max_nodes:
            raise ValueError(
                "flow budget cannot hold required query boundaries")

        def edge_count(row):
            return (
                1 + int(row[1] in category_goal))

        def choose(reserve_stub):
            node_limit = (
                self.budget.max_nodes - base_nodes
                - int(reserve_stub))
            chosen = []
            used_edges = 0
            for row in legal_rows:
                required_edges = edge_count(row)
                if (len(chosen) >= self.budget.max_candidates
                        or len(chosen) >= node_limit
                        or used_edges + required_edges
                        > self.budget.max_edges):
                    break
                chosen.append(row)
                used_edges += required_edges
            return chosen, used_edges

        selected, selected_edge_count = choose(False)
        truncated = len(selected) < len(legal_rows)
        reserve_stub = (
            truncated and self.budget.max_frontier_stubs > 0
            and base_nodes < self.budget.max_nodes)
        if reserve_stub:
            selected, selected_edge_count = choose(True)
            truncated = len(selected) < len(legal_rows)
        del selected_edge_count
        selected_digests = frozenset(
            row[2] for row in selected)
        for _, category, action_digest, _ in legal_rows:
            if action_digest not in selected_digests:
                rejections.append(FlowBuildRejection(
                    action_digest, category,
                    "materialization_budget"))

        node_specs = [{
            "active": True,
            "kind": FlowNodeKind.FORWARD_BOUNDARY,
            "provenance_ids": (snapshot_id,),
            "source": self.BUILDER_IDENTITY,
            "stable_id": forward_id,
        }]
        node_specs.extend({
            "active": True,
            "kind": FlowNodeKind.BACKWARD_BOUNDARY,
            "provenance_ids": (goal_id,),
            "source": self.BUILDER_IDENTITY,
            "stable_id": stable_id,
        } for goal_id, stable_id in goal_node_ids.items())
        edge_specs = []
        grounding_specs = []
        for _, category, action_digest, candidate in selected:
            action = candidate.action
            operation_id = "flow:operation:{}".format(
                action_digest)
            node_specs.append({
                "active": True,
                "kind": FlowNodeKind.OPERATION,
                "provenance_ids": (
                    snapshot_id, action_digest),
                "source": self.BUILDER_IDENTITY,
                "stable_id": operation_id,
            })
            invoke_id = "flow:edge:{}".format(structural_hash({
                "kind": FlowEdgeKind.OPERATION_INVOKE.value,
                "source": forward_id,
                "target": operation_id,
            }))
            edge_specs.append({
                "kind": FlowEdgeKind.OPERATION_INVOKE,
                "legality": FlowLegality(
                    probe_forward=True,
                    causal_planning=True,
                    operation_invocation=True),
                "provenance_ids": (
                    snapshot_id, action_digest),
                "source": forward_id,
                "stable_id": invoke_id,
                "target": operation_id,
            })
            goal_id = category_goal.get(category)
            if goal_id is not None:
                demand_id = "flow:edge:{}".format(
                    structural_hash({
                        "goal_id": goal_id,
                        "kind": FlowEdgeKind.BACKWARD_DEMAND.value,
                        "source": goal_node_ids[goal_id],
                        "target": operation_id,
                    }))
                edge_specs.append({
                    "kind": FlowEdgeKind.BACKWARD_DEMAND,
                    "legality": FlowLegality(
                        backward_demand=True,
                        probe_backward=True),
                    "provenance_ids": (goal_id,),
                    "source": goal_node_ids[goal_id],
                    "stable_id": demand_id,
                    "target": operation_id,
                })
            grounding_specs.append({
                "action_digest": action_digest,
                "actor_id": self._actor_id(action),
                "category": category,
                "operation_node_id": operation_id,
                "target_digest": self._target_digest(action),
            })

        frontier_stub_ids = ()
        if truncated and reserve_stub:
            frontier_id = "flow:frontier-stub:{}".format(
                structural_hash({
                    "legal_candidate_count": len(legal_rows),
                    "materialized_candidate_count": len(selected),
                    "query_id": query_id,
                }))
            node_specs.append({
                "active": True,
                "kind": FlowNodeKind.FRONTIER_STUB,
                "provenance_ids": (),
                "source": self.BUILDER_IDENTITY,
                "stable_id": frontier_id,
            })
            frontier_stub_ids = (frontier_id,)

        node_specs = sorted(
            node_specs, key=lambda row: row["stable_id"])
        nodes = tuple(
            FlowNode(
                local_id=index,
                stable_id=row["stable_id"],
                kind=row["kind"],
                semantic_generation=semantic_epoch,
                topology_generation=topology_generation,
                context_digest=context_digest,
                clone_generation=clone_generation,
                source=row["source"],
                provenance_ids=tuple(row["provenance_ids"]),
                born_generation=topology_generation,
                active=row["active"])
            for index, row in enumerate(node_specs))
        edge_specs = sorted(
            edge_specs, key=lambda row: row["stable_id"])
        edges = tuple(
            FlowEdge(
                local_id=index,
                stable_id=row["stable_id"],
                source_node_id=row["source"],
                target_node_id=row["target"],
                kind=row["kind"],
                legality=row["legality"],
                semantic_generation=semantic_epoch,
                topology_generation=topology_generation,
                context_digest=context_digest,
                clone_generation=clone_generation,
                source=self.BUILDER_IDENTITY,
                provenance_ids=tuple(row["provenance_ids"]),
                born_generation=topology_generation)
            for index, row in enumerate(edge_specs))
        grounding_specs = sorted(
            grounding_specs,
            key=lambda row: row["operation_node_id"])
        groundings = tuple(
            CandidateGrounding(
                snapshot_id=snapshot_id,
                legal_action_digest=legal_action_digest,
                action_digest=row["action_digest"],
                semantic_epoch=semantic_epoch,
                topology_generation=topology_generation,
                actor_id=row["actor_id"],
                target_digest=row["target_digest"],
                category=row["category"],
                operation_node_id=row["operation_node_id"])
            for row in grounding_specs)
        view = FlowView(
            query_id=query_id,
            snapshot_id=snapshot_id,
            legal_action_digest=legal_action_digest,
            semantic_epoch=semantic_epoch,
            topology_generation=topology_generation,
            context_digest=context_digest,
            clone_generation=clone_generation,
            nodes=nodes,
            edges=edges,
            candidate_groundings=groundings,
            frontier_stub_ids=frontier_stub_ids,
            materialization_budget=self.budget.to_dict())
        return FlowBuildResult(
            view=view,
            rejections=tuple(sorted(
                rejections,
                key=lambda row: (
                    row.action_digest, row.category,
                    row.reason))),
            legal_candidate_count=len(legal_rows),
            materialized_candidate_count=len(groundings),
            budget_exhausted=truncated)
