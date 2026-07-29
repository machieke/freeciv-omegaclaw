"""Deterministic construction of bounded query-local control graphs."""

from dataclasses import dataclass, replace

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


@dataclass(frozen=True)
class CandidateFactorization:
    operation_node_id: str
    factor_node_ids: tuple
    requirement_roles: tuple
    frontier_roles: tuple
    complete: bool

    def __post_init__(self):
        if (not isinstance(self.operation_node_id, str)
                or not self.operation_node_id):
            raise ValueError(
                "factorization operation node ID is required")
        if len(set(self.factor_node_ids)) != len(
                self.factor_node_ids):
            raise ValueError(
                "factor node IDs must be unique")
        if len(set(self.requirement_roles)) != len(
                self.requirement_roles):
            raise ValueError(
                "requirement roles must be unique")
        if len(set(self.frontier_roles)) != len(
                self.frontier_roles):
            raise ValueError(
                "frontier roles must be unique")
        if not isinstance(self.complete, bool):
            raise TypeError(
                "factorization complete state must be boolean")

    def to_dict(self):
        return {
            "complete": self.complete,
            "factor_node_ids": list(self.factor_node_ids),
            "frontier_roles": list(self.frontier_roles),
            "operation_node_id": self.operation_node_id,
            "requirement_roles": list(
                self.requirement_roles),
        }


@dataclass(frozen=True)
class FreeCivFactorizationResult:
    view: FlowView
    shell: FlowBuildResult
    factorizations: tuple
    factorized_candidate_count: int
    frontier_candidate_count: int
    budget_exhausted: bool

    def __post_init__(self):
        if not isinstance(self.view, FlowView):
            raise TypeError(
                "factorization view must be FlowView")
        if not isinstance(self.shell, FlowBuildResult):
            raise TypeError(
                "factorization shell must be FlowBuildResult")
        if any(not isinstance(row, CandidateFactorization)
               for row in self.factorizations):
            raise TypeError(
                "factorizations must contain CandidateFactorization")

    def to_dict(self):
        material = {
            "budget_exhausted": self.budget_exhausted,
            "factorizations": [
                row.to_dict() for row in self.factorizations],
            "factorized_candidate_count": (
                self.factorized_candidate_count),
            "frontier_candidate_count": (
                self.frontier_candidate_count),
            "schema_version": "1.0",
            "shell": self.shell.to_dict(),
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
                "role": "authoritative_snapshot_boundary",
            }))
        goal_node_ids = dict(
            (goal_id, "flow:backward-boundary:{}".format(
                structural_hash({
                    "goal_id": goal_id,
                    "role": "active_goal_boundary",
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
            "committable": False,
            "evidence_mirror": False,
            "payload_digest": structural_hash(
                snapshot.event_payload()),
            "provenance_ids": (snapshot_id,),
            "semantic_role": "authoritative_snapshot_boundary",
            "source": self.BUILDER_IDENTITY,
            "stable_id": forward_id,
        }]
        node_specs.extend({
            "active": True,
            "kind": FlowNodeKind.BACKWARD_BOUNDARY,
            "committable": False,
            "evidence_mirror": False,
            "payload_digest": structural_hash(goal_id),
            "provenance_ids": (goal_id,),
            "semantic_role": "active_goal_boundary",
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
                "committable": True,
                "evidence_mirror": False,
                "payload_digest": action_digest,
                "provenance_ids": (
                    snapshot_id, action_digest),
                "semantic_role": "authoritative_legal_operation",
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
                    "legal_action_digest": legal_action_digest,
                    "legal_candidate_count": len(legal_rows),
                    "materialized_candidate_count": len(selected),
                    "role": "candidate_materialization_frontier",
                }))
            node_specs.append({
                "active": True,
                "kind": FlowNodeKind.FRONTIER_STUB,
                "committable": False,
                "evidence_mirror": False,
                "payload_digest": None,
                "provenance_ids": (),
                "semantic_role": "candidate_materialization_frontier",
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
                active=row["active"],
                semantic_role=row.get("semantic_role"),
                payload_digest=row.get("payload_digest"),
                evidence_mirror=row.get(
                    "evidence_mirror", False),
                committable=row.get("committable", False))
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


class FreeCivFactorGraphBuilder:
    """Deepen authoritative operations into bounded causal factor routes."""

    BUILDER_IDENTITY = "freeciv-grounded-factor-builder/1.0"

    def __init__(self, budget=None, max_candidates_per_category=64):
        self.budget = (
            budget if budget is not None else FlowBuildBudget(
                max_nodes=1024, max_edges=4096,
                max_candidates=512,
                max_frontier_stubs=64))
        if not isinstance(self.budget, FlowBuildBudget):
            raise TypeError(
                "factor graph budget must be FlowBuildBudget")
        self.max_candidates_per_category = _bounded_integer(
            max_candidates_per_category,
            "maximum candidates per category", 1)

    @staticmethod
    def _node_id(operation_id, role):
        return "flow:factor:{}".format(structural_hash({
            "operation_node_id": operation_id,
            "role": role,
        }))

    @staticmethod
    def _edge_id(kind, source, target, role):
        return "flow:edge:{}".format(structural_hash({
            "kind": kind.value,
            "role": role,
            "source": source,
            "target": target,
        }))

    @staticmethod
    def _actor_is_mirrored(snapshot, action):
        action_type = str(action.get("action_type", ""))
        if action_type.startswith("unit_"):
            actor_id = action.get("actor_id")
            return (
                actor_id is not None
                and snapshot.unit(actor_id) is not None)
        if action_type.startswith("city_"):
            city_id = action.get(
                "city_id", action.get("actor_id"))
            return (
                city_id is not None
                and snapshot.city(city_id) is not None)
        actor_id = action.get("actor_id")
        return (
            actor_id is None
            or actor_id == snapshot.player_id)

    @staticmethod
    def _requirement_roles(snapshot, candidate):
        action = candidate.action
        action_type = str(action.get("action_type", ""))
        projection = candidate.projection or {}
        roles = [
            (
                "legal_action_is_still_advertised",
                FlowNodeKind.PROPOSITION, True,
                structural_hash(action)),
            (
                "actor_exists_and_is_available",
                (FlowNodeKind.PROPOSITION
                 if FreeCivFactorGraphBuilder._actor_is_mirrored(
                     snapshot, action)
                 else FlowNodeKind.FRONTIER_STUB),
                FreeCivFactorGraphBuilder._actor_is_mirrored(
                    snapshot, action),
                structural_hash({
                    "actor_id": action.get(
                        "actor_id", action.get("city_id")),
                    "snapshot_id": snapshot.snapshot_id,
                })),
            (
                "target_or_destination_remains_valid",
                FlowNodeKind.PROPOSITION, True,
                structural_hash({
                    "action": action,
                    "legal_action_digest": (
                        snapshot.legal_actions_digest),
                })),
            (
                "safety_and_provenance_guards",
                FlowNodeKind.PROPOSITION, False,
                structural_hash({
                    "category": candidate.category,
                    "source": "grounded-impact-planner",
                })),
        ]
        if action_type == "unit_move":
            roles.append((
                "path_or_movement_feasibility",
                FlowNodeKind.PROPOSITION, True,
                structural_hash({
                    "legal_action_digest": (
                        snapshot.legal_actions_digest),
                    "target": action.get("target"),
                })))
        if action_type in (
                "city_production", "unit_upgrade",
                "unit_buy", "building_buy"):
            roles.append((
                "resource_gold_or_upkeep_precondition",
                FlowNodeKind.FRONTIER_STUB, False,
                structural_hash({
                    "action_type": action_type,
                    "economy": snapshot.economy.to_dict(),
                })))
        if (action_type == "city_production"
                or projection.get(
                    "founder_route_eta_turns") is not None):
            roles.append((
                "production_or_completion_deadline",
                FlowNodeKind.FRONTIER_STUB, False,
                structural_hash({
                    "eta": projection.get(
                        "founder_route_eta_turns"),
                    "turn": snapshot.turn,
                })))
        if (projection
                and projection.get(
                    "settlement_site_eligible") is None):
            roles.append((
                "required_observation_or_simulation_result",
                FlowNodeKind.FRONTIER_STUB, False,
                structural_hash({
                    "projection": projection,
                    "snapshot_id": snapshot.snapshot_id,
                })))
        if any(
                key in projection for key in (
                    "risk_estimate", "threat",
                    "danger", "enemy_distance")):
            roles.append((
                "threat_or_opportunity_context",
                FlowNodeKind.FRONTIER_STUB, False,
                structural_hash(projection)))
        return tuple(sorted(roles, key=lambda row: row[0]))

    def _factor_specs(
            self, snapshot, candidate, grounding,
            goal_node_id, forward_boundary_id):
        operation_id = grounding.operation_node_id
        factor_roles = (
            ("desired_outcome_factor", FlowNodeKind.RULE_FACTOR),
            ("effect_model_factor", FlowNodeKind.RULE_FACTOR),
            ("operation_requirement_set",
             FlowNodeKind.REQUIREMENT_SET),
        )
        node_specs = []
        role_ids = {}
        for role, kind in factor_roles:
            stable_id = self._node_id(operation_id, role)
            role_ids[role] = stable_id
            node_specs.append({
                "active": True,
                "committable": False,
                "evidence_mirror": False,
                "kind": kind,
                "payload_digest": structural_hash({
                    "candidate": candidate.to_dict(),
                    "role": role,
                }),
                "provenance_ids": (
                    grounding.action_digest,),
                "semantic_role": role,
                "source": self.BUILDER_IDENTITY,
                "stable_id": stable_id,
            })
        requirement_roles = self._requirement_roles(
            snapshot, candidate)
        for role, kind, evidence_mirror, payload_digest in (
                requirement_roles):
            stable_id = self._node_id(operation_id, role)
            role_ids[role] = stable_id
            node_specs.append({
                "active": True,
                "committable": False,
                "evidence_mirror": evidence_mirror,
                "kind": kind,
                "payload_digest": payload_digest,
                "provenance_ids": (
                    grounding.action_digest,
                    snapshot.snapshot_id),
                "semantic_role": role,
                "source": self.BUILDER_IDENTITY,
                "stable_id": stable_id,
            })

        edge_specs = []

        def edge(kind, source, target, role, legality):
            edge_specs.append({
                "kind": kind,
                "legality": legality,
                "provenance_ids": (
                    grounding.action_digest,),
                "source": source,
                "stable_id": self._edge_id(
                    kind, source, target, role),
                "target": target,
            })

        requirement_set_id = role_ids[
            "operation_requirement_set"]
        for role, kind, _, _ in requirement_roles:
            premise_id = role_ids[role]
            if kind == FlowNodeKind.PROPOSITION:
                edge(
                    FlowEdgeKind.PROBE_FORWARD,
                    forward_boundary_id, premise_id,
                    "boundary-to-{}".format(role),
                    FlowLegality(probe_forward=True))
                edge(
                    FlowEdgeKind.FORWARD_TRUTH,
                    premise_id, requirement_set_id,
                    "{}-to-requirement-set".format(role),
                    FlowLegality(
                        forward_truth=True,
                        probe_forward=True,
                        causal_planning=True))
            edge(
                FlowEdgeKind.BACKWARD_DEMAND,
                requirement_set_id, premise_id,
                "requirement-set-to-{}".format(role),
                FlowLegality(
                    backward_demand=True,
                    probe_backward=True,
                    expansion=(
                        kind == FlowNodeKind.FRONTIER_STUB)))

        effect_id = role_ids["effect_model_factor"]
        outcome_id = role_ids["desired_outcome_factor"]
        edge(
            FlowEdgeKind.PROBE_FORWARD,
            requirement_set_id, operation_id,
            "requirements-to-operation",
            FlowLegality(
                probe_forward=True,
                causal_planning=True))
        edge(
            FlowEdgeKind.PROBE_FORWARD,
            operation_id, effect_id,
            "operation-to-effect",
            FlowLegality(
                probe_forward=True,
                causal_planning=True,
                operation_invocation=True))
        edge(
            FlowEdgeKind.PROBE_FORWARD,
            effect_id, outcome_id,
            "effect-to-outcome",
            FlowLegality(
                probe_forward=True,
                causal_planning=True))
        edge(
            FlowEdgeKind.PROBE_FORWARD,
            outcome_id, goal_node_id,
            "outcome-to-goal",
            FlowLegality(probe_forward=True))
        edge(
            FlowEdgeKind.BACKWARD_DEMAND,
            goal_node_id, outcome_id,
            "goal-to-outcome",
            FlowLegality(
                backward_demand=True,
                probe_backward=True))
        edge(
            FlowEdgeKind.BACKWARD_DEMAND,
            outcome_id, effect_id,
            "outcome-to-effect",
            FlowLegality(
                backward_demand=True,
                probe_backward=True))
        edge(
            FlowEdgeKind.BACKWARD_DEMAND,
            effect_id, operation_id,
            "effect-to-operation",
            FlowLegality(
                backward_demand=True,
                probe_backward=True))
        edge(
            FlowEdgeKind.BACKWARD_DEMAND,
            operation_id, requirement_set_id,
            "operation-to-requirements",
            FlowLegality(
                backward_demand=True,
                probe_backward=True))
        return node_specs, edge_specs, requirement_roles

    def build(
            self, query_id, snapshot, candidates,
            goal_ids, goal_by_category,
            semantic_epoch=0, topology_generation=0,
            clone_generation=0, context_digest=None):
        candidates = tuple(candidates)
        shell = QueryLocalFlowBuilder(self.budget).build(
            query_id, snapshot, candidates,
            goal_ids=goal_ids,
            goal_by_category=goal_by_category,
            semantic_epoch=semantic_epoch,
            topology_generation=topology_generation,
            clone_generation=clone_generation,
            context_digest=context_digest)
        view = shell.view
        candidate_by_digest = dict(
            (structural_hash(row.action), row)
            for row in candidates)
        goal_nodes = dict(
            (row.provenance_ids[0], row.stable_id)
            for row in view.nodes
            if row.kind == FlowNodeKind.BACKWARD_BOUNDARY)
        forward_boundary_id = next(
            row.stable_id for row in view.nodes
            if row.kind == FlowNodeKind.FORWARD_BOUNDARY)
        category_counts = {}
        node_specs = []
        edge_specs = []
        records = []
        skipped = []
        used_nodes = len(view.nodes)
        base_edges = tuple(
            row for row in view.edges
            if row.kind != FlowEdgeKind.OPERATION_INVOKE)
        used_edges = len(base_edges)
        category_goal = dict(goal_by_category)
        for grounding in view.candidate_groundings:
            candidate = candidate_by_digest[
                grounding.action_digest]
            goal_id = category_goal.get(candidate.category)
            if goal_id not in goal_nodes:
                skipped.append((grounding, "no_declared_goal"))
                continue
            count = category_counts.get(
                candidate.category, 0)
            proposed_nodes, proposed_edges, roles = (
                self._factor_specs(
                    snapshot, candidate, grounding,
                    goal_nodes[goal_id],
                    forward_boundary_id))
            over_budget = (
                count >= self.max_candidates_per_category
                or used_nodes + len(proposed_nodes)
                > self.budget.max_nodes
                or used_edges + len(proposed_edges)
                > self.budget.max_edges)
            if over_budget:
                skipped.append((
                    grounding, "factorization_budget"))
                continue
            category_counts[candidate.category] = count + 1
            node_specs.extend(proposed_nodes)
            edge_specs.extend(proposed_edges)
            used_nodes += len(proposed_nodes)
            used_edges += len(proposed_edges)
            records.append(CandidateFactorization(
                operation_node_id=(
                    grounding.operation_node_id),
                factor_node_ids=tuple(sorted(
                    row["stable_id"]
                    for row in proposed_nodes)),
                requirement_roles=tuple(
                    row[0] for row in roles),
                frontier_roles=tuple(
                    row[0] for row in roles
                    if row[1] == FlowNodeKind.FRONTIER_STUB),
                complete=True))

        for grounding, reason in skipped:
            factor_node_ids = ()
            if used_nodes < self.budget.max_nodes:
                frontier_id = self._node_id(
                    grounding.operation_node_id,
                    "factorization_frontier:{}".format(reason))
                node_specs.append({
                    "active": True,
                    "committable": False,
                    "evidence_mirror": False,
                    "kind": FlowNodeKind.FRONTIER_STUB,
                    "payload_digest": grounding.action_digest,
                    "provenance_ids": (
                        grounding.action_digest,),
                    "semantic_role": (
                        "candidate_factorization_frontier"),
                    "source": self.BUILDER_IDENTITY,
                    "stable_id": frontier_id,
                })
                used_nodes += 1
                factor_node_ids = (frontier_id,)
            records.append(CandidateFactorization(
                grounding.operation_node_id,
                factor_node_ids,
                (),
                ("candidate_factorization_frontier",),
                False))

        existing_node_specs = []
        for row in view.nodes:
            existing_node_specs.append(row)
        appended_nodes = tuple(
            FlowNode(
                local_id=0,
                stable_id=row["stable_id"],
                kind=row["kind"],
                semantic_generation=semantic_epoch,
                topology_generation=topology_generation,
                context_digest=view.context_digest,
                clone_generation=clone_generation,
                source=row["source"],
                provenance_ids=tuple(row["provenance_ids"]),
                born_generation=topology_generation,
                active=row["active"],
                semantic_role=row["semantic_role"],
                payload_digest=row["payload_digest"],
                evidence_mirror=row["evidence_mirror"],
                committable=row["committable"])
            for row in node_specs)
        nodes = tuple(
            replace(row, local_id=index)
            for index, row in enumerate(sorted(
                tuple(existing_node_specs) + appended_nodes,
                key=lambda item: item.stable_id)))
        appended_edges = tuple(
            FlowEdge(
                local_id=0,
                stable_id=row["stable_id"],
                source_node_id=row["source"],
                target_node_id=row["target"],
                kind=row["kind"],
                legality=row["legality"],
                semantic_generation=semantic_epoch,
                topology_generation=topology_generation,
                context_digest=view.context_digest,
                clone_generation=clone_generation,
                source=self.BUILDER_IDENTITY,
                provenance_ids=tuple(row["provenance_ids"]),
                born_generation=topology_generation)
            for row in edge_specs)
        edges = tuple(
            replace(row, local_id=index)
            for index, row in enumerate(sorted(
                base_edges + appended_edges,
                key=lambda item: item.stable_id)))
        frontier_ids = tuple(sorted(set(
            view.frontier_stub_ids
            + tuple(
                row.stable_id for row in appended_nodes
                if row.kind == FlowNodeKind.FRONTIER_STUB))))
        deep_view = FlowView(
            query_id=view.query_id,
            snapshot_id=view.snapshot_id,
            legal_action_digest=view.legal_action_digest,
            semantic_epoch=view.semantic_epoch,
            topology_generation=view.topology_generation,
            context_digest=view.context_digest,
            clone_generation=view.clone_generation,
            nodes=nodes,
            edges=edges,
            candidate_groundings=view.candidate_groundings,
            frontier_stub_ids=frontier_ids,
            materialization_budget={
                "factorization": {
                    "max_candidates_per_category": (
                        self.max_candidates_per_category),
                },
                "topology": self.budget.to_dict(),
            })
        factorizations = tuple(sorted(
            records,
            key=lambda row: row.operation_node_id))
        complete_count = sum(
            row.complete for row in factorizations)
        return FreeCivFactorizationResult(
            view=deep_view,
            shell=shell,
            factorizations=factorizations,
            factorized_candidate_count=complete_count,
            frontier_candidate_count=(
                len(view.candidate_groundings)
                - complete_count),
            budget_exhausted=bool(
                skipped or shell.budget_exhausted))
