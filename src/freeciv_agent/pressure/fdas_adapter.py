"""Shadow PF-v2 pressure graphs over FDAS local goals and operations."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from .engine import PressureEngineV2, PressureGraph, PressureV2Policy
from .model import (
    AtomState,
    CostVector,
    Operation,
    PressureConfig,
    PressureRule,
    Resolvability,
    TruthState,
)
from .scheduler import PressureScheduler


@dataclass(frozen=True)
class MaterializationBudget:
    maximum_atoms: int = 25000
    maximum_rules: int = 2000
    maximum_operations: int = 1000

    def __post_init__(self):
        for value, name in (
                (self.maximum_atoms, "maximum atoms"),
                (self.maximum_rules, "maximum rules"),
                (self.maximum_operations, "maximum operations")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("{} must be positive".format(name))


@dataclass(frozen=True)
class DependentAtomPressureContext:
    graph: PressureGraph
    goals: tuple
    operations: tuple
    candidate_atom_ids: tuple
    gap_atom_ids: tuple
    revision_id: str
    snapshot_id: str
    truncated: bool
    diagnostics: tuple
    policy_authority: bool
    artifact_hash: str

    def __post_init__(self):
        if self.policy_authority:
            raise ValueError("FDAS pressure context is shadow-only")

    def to_dict(self):
        return {
            "artifact_hash": self.artifact_hash,
            "candidate_atom_ids": [list(value)
                                   for value in self.candidate_atom_ids],
            "diagnostics": list(self.diagnostics),
            "gap_atom_ids": [list(value) for value in self.gap_atom_ids],
            "goals": [value.to_dict() for value in self.goals],
            "graph_hash": self.graph.artifact_hash,
            "operations": [value.to_dict() for value in self.operations],
            "policy_authority": False,
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class DependentAtomPressureEvaluation:
    context: DependentAtomPressureContext
    pressure_result: object
    schedule: object
    status: str
    reason: object
    evaluation_hash: str

    def __post_init__(self):
        if self.status not in ("complete", "not-applicable", "unknown"):
            raise ValueError("invalid FDAS pressure evaluation status")
        if self.status == "complete":
            if self.pressure_result is None or self.reason is not None:
                raise ValueError("complete pressure evaluation is inconsistent")
        elif self.reason is None:
            raise ValueError("non-complete pressure evaluation requires reason")

    def to_dict(self):
        return {
            "context": self.context.to_dict(),
            "evaluation_hash": self.evaluation_hash,
            "pressure": (
                None if self.pressure_result is None
                else self.pressure_result.to_dict()),
            "reason": self.reason,
            "schedule": self.schedule,
            "status": self.status,
        }


class DependentAtomPressureAdapter(object):
    """Map FDAS causal routes to PF-v2 without mutating epistemic truth."""

    def __init__(self, config=None, v2_policy=None):
        self.config = config or PressureConfig()
        self.v2_policy = v2_policy or PressureV2Policy()
        self.engine = PressureEngineV2(self.config, self.v2_policy)
        self.scheduler = PressureScheduler(self.config)

    @staticmethod
    def _truth(record):
        truth = record.truth or {}
        return TruthState(
            float(truth.get("strength", 0.0)),
            float(truth.get("confidence", 0.0)),
            tuple(record.provenance_ids),
            bool(truth.get("crisp", False)),
        )

    @staticmethod
    def _target_atom(goal):
        return AtomState(
            goal.target_key.atom_id,
            TruthState(0.0, 1.0, (goal.deficit_atom_id,), crisp=True),
            expression=goal.target_key.to_dict(),
            context=(("scope_id", goal.scope_id),
                     ("snapshot_id", goal.snapshot_id)),
            lifecycle="unsatisfied",
        )

    @staticmethod
    def _candidate_atom_id(candidate):
        return "fdas-pressure-operation:" + candidate.operation.operation_id

    @staticmethod
    def _gap_atom_id(goal):
        return "fdas-pressure-gap:" + goal.goal.goal_id

    @staticmethod
    def _operation(candidate, atom_id, goals):
        blocked = bool(candidate.blockers)
        effects = tuple(
            (goal.goal.goal_id,
             1.0 if goal.goal.goal_id in candidate.operation.goal_ids else 0.0)
            for goal in goals)
        return Operation(
            candidate.operation.operation_id,
            atom_id,
            "expand" if blocked else "act",
            CostVector(
                compute=1.0,
                resource=float(max(1, len(candidate.resource_keys))),
                risk=0.25 if blocked else 0.0,
            ),
            causal_kind="diagnostic" if blocked else "procedural",
            success_probability=0.0 if blocked else 1.0,
            relief_scale=0.0 if blocked else 1.0,
            feasibility=1.0 if candidate.legal_bound else 0.0,
            goal_effects=effects,
            safety_compatible=True,
            payload={
                "action": candidate.action,
                "action_key": candidate.action_key,
                "authority_eligible": False,
                "blockers": list(candidate.blockers),
                "candidate_hash": candidate.candidate_hash,
                "operation_spec_digest": candidate.operation.spec_digest,
                "resource_keys": list(candidate.resource_keys),
                "shadow_only": True,
            },
            reversible=True,
            externally_consequential=not blocked,
            requirement_set_id=(
                candidate.operation.steps[0].requirement_set_id),
        )

    @staticmethod
    def _gap_operation(goal, atom_id, goals):
        effects = tuple(
            (row.goal.goal_id,
             1.0 if row.goal.goal_id == goal.goal.goal_id else 0.0)
            for row in goals)
        return Operation(
            "fdas-expand-gap:" + goal.goal.goal_id,
            atom_id,
            "expand",
            CostVector(compute=1.0),
            causal_kind="diagnostic",
            success_probability=1.0,
            relief_scale=1.0,
            feasibility=1.0,
            information_gain=0.25,
            goal_effects=effects,
            payload={
                "authority_eligible": False,
                "deficit_atom_id": goal.deficit_atom_id,
                "reason": "no-current-legal-causal-route",
                "shadow_only": True,
            },
        )

    def build_context(self, revision, goals, candidate_operations,
                      materialization_budget=None):
        budget = materialization_budget or MaterializationBudget()
        goals = tuple(sorted(goals, key=lambda value: value.goal.goal_id))
        candidates = tuple(sorted(
            candidate_operations,
            key=lambda value: value.operation.operation_id))
        if any(goal.snapshot_id != revision.snapshot_id for goal in goals):
            raise ValueError("FDAS pressure goal references a stale snapshot")
        if any(candidate.action_key != candidate.action_key.strip()
               for candidate in candidates):
            raise ValueError("candidate action identity is malformed")
        graph = PressureGraph()
        diagnostics = []
        truncated = False
        atom_count = 0
        rule_count = 0
        operations = []
        candidate_atom_ids = []
        gap_atom_ids = []
        active_goal_contexts = []

        def add_atom(atom, resolvability):
            nonlocal atom_count, truncated
            if atom_count >= budget.maximum_atoms:
                truncated = True
                diagnostics.append("atom-budget-exhausted")
                return False
            graph.add_atom(atom, resolvability)
            atom_count += 1
            return True

        def add_rule(rule):
            nonlocal rule_count, truncated
            if rule_count >= budget.maximum_rules:
                truncated = True
                diagnostics.append("rule-budget-exhausted")
                return False
            graph.add_rule(rule)
            rule_count += 1
            return True

        for goal in goals:
            # A goal is useful only when both its desired target and factual
            # deficit boundary fit.  Do not leave a crisp orphan target behind
            # when the bounded materialization cannot represent the witness.
            if atom_count + 2 > budget.maximum_atoms:
                truncated = True
                diagnostics.append("atom-budget-exhausted")
                break
            target = self._target_atom(goal)
            if not add_atom(target, Resolvability(retain=0.1)):
                break
            deficit = revision.record(goal.deficit_atom_id)
            if deficit is None:
                raise ValueError("local goal deficit atom is absent")
            if not add_atom(AtomState(
                deficit.atom_id,
                self._truth(deficit),
                expression=deficit.key.to_dict(),
                context=(("scope_id", deficit.key.scope_id),),
                lifecycle="active-deficit",
            ), Resolvability(retain=0.5)):
                break
            active_goal_contexts.append(goal)

        goals = tuple(active_goal_contexts)
        goal_by_id = dict((value.goal.goal_id, value) for value in goals)

        candidates_by_goal = dict((goal.goal.goal_id, []) for goal in goals)
        for candidate in (candidates if goals else ()):
            matching = tuple(
                goal_id for goal_id in candidate.operation.goal_ids
                if goal_id in goal_by_id)
            if not matching:
                diagnostics.append(
                    "candidate-without-active-goal:{}".format(
                        candidate.operation.operation_id))
                continue
            if len(operations) >= budget.maximum_operations:
                truncated = True
                diagnostics.append("operation-budget-exhausted")
                break
            atom_id = self._candidate_atom_id(candidate)
            blocked = bool(candidate.blockers)
            if not add_atom(AtomState(
                    atom_id,
                    TruthState(
                        0.0, 1.0,
                        (candidate.candidate_hash,), crisp=True),
                    expression={
                        "action_key": candidate.action_key,
                        "blockers": list(candidate.blockers),
                        "operation_id": candidate.operation.operation_id,
                    },
                    context=(("snapshot_id", revision.snapshot_id),),
                    lifecycle="blocked" if blocked else "legal-bound",
            ), Resolvability(
                infer=0.25 if blocked else 0.0,
                act=0.0 if blocked else 1.0,
                expand=1.0 if blocked else 0.0,
                retain=0.1)):
                break
            operation = self._operation(candidate, atom_id, goals)
            connected = False
            for goal_id in matching:
                goal = goal_by_id[goal_id]
                added = add_rule(PressureRule(
                    "fdas-pressure-rule:" + structural_hash({
                        "candidate": candidate.candidate_hash,
                        "goal_id": goal_id,
                        "revision_id": revision.revision_id,
                    })[:28],
                    (atom_id,),
                    goal.target_key.atom_id,
                    kind="or",
                    causal_kind=(
                        "diagnostic" if blocked else "procedural"),
                    conductance=1.0,
                    compatibility=1.0,
                    residual=1.0,
                    success_probability=0.0 if blocked else 1.0,
                    route_cost=1.0,
                    source={
                        "candidate_hash": candidate.candidate_hash,
                        "deficit_atom_id": goal.deficit_atom_id,
                        "explanation_hash": goal.explanation_hash,
                        "operation_spec_digest": (
                            candidate.operation.spec_digest),
                        "revision_id": revision.revision_id,
                    },
                ))
                if added:
                    candidates_by_goal[goal_id].append(candidate)
                    connected = True
            if connected:
                candidate_atom_ids.append((
                    candidate.operation.operation_id, atom_id))
                operations.append(operation)

        for goal in goals:
            if candidates_by_goal[goal.goal.goal_id]:
                continue
            if len(operations) >= budget.maximum_operations:
                truncated = True
                diagnostics.append("operation-budget-exhausted")
                break
            atom_id = self._gap_atom_id(goal)
            if not add_atom(AtomState(
                    atom_id,
                    TruthState(0.0, 1.0, (), crisp=True),
                    expression={
                        "deficit_atom_id": goal.deficit_atom_id,
                        "reason": "no-current-legal-causal-route",
                    },
                    lifecycle="unknown-route",
            ), Resolvability(infer=0.25, expand=1.0)):
                break
            gap_atom_ids.append((goal.goal.goal_id, atom_id))
            added = add_rule(PressureRule(
                "fdas-gap-rule:" + goal.goal.goal_id,
                (atom_id,),
                goal.target_key.atom_id,
                kind="or",
                causal_kind="diagnostic",
                source={
                    "deficit_atom_id": goal.deficit_atom_id,
                    "explanation_hash": goal.explanation_hash,
                    "reason": "no-current-legal-causal-route",
                    "revision_id": revision.revision_id,
                },
            ))
            if added:
                operations.append(self._gap_operation(goal, atom_id, goals))

        semantic = {
            "candidate_atom_ids": candidate_atom_ids,
            "diagnostics": sorted(set(diagnostics)),
            "gap_atom_ids": gap_atom_ids,
            "goals": [value.goal.to_dict() for value in goals],
            "graph_hash": graph.artifact_hash,
            "operation_hashes": [value.artifact_hash for value in operations],
            "policy_authority": False,
            "revision_id": revision.revision_id,
            "snapshot_id": revision.snapshot_id,
            "truncated": truncated,
        }
        return DependentAtomPressureContext(
            graph,
            tuple(value.goal for value in goals),
            tuple(sorted(operations, key=lambda value: value.operation_id)),
            tuple(candidate_atom_ids),
            tuple(gap_atom_ids),
            revision.revision_id,
            revision.snapshot_id,
            truncated,
            tuple(sorted(set(diagnostics))),
            False,
            structural_hash(semantic),
        )

    def evaluate(self, revision, goals, candidate_operations,
                 materialization_budget=None):
        context = self.build_context(
            revision, goals, candidate_operations, materialization_budget)
        if not context.goals:
            status = "unknown" if context.truncated else "not-applicable"
            reason = (
                "materialization-budget-exhausted"
                if context.truncated else "no-active-local-goals")
            schedule = {
                "allocations": [],
                "pressure_hash": None,
                "reason": reason,
                "scores": [],
                "selected_operation_id": None,
                "solver_identity": self.scheduler.SOLVER_IDENTITY,
                "status": status,
            }
            schedule["structural_hash"] = structural_hash(schedule)
            semantic = {
                "context_hash": context.artifact_hash,
                "pressure_hash": None,
                "reason": reason,
                "schedule_hash": schedule["structural_hash"],
                "status": status,
            }
            return DependentAtomPressureEvaluation(
                context, None, schedule, status, reason,
                structural_hash(semantic))
        pressure = self.engine.propagate(context.graph, context.goals)
        schedule = self.scheduler.decision_artifact(
            context.operations, pressure)
        semantic = {
            "context_hash": context.artifact_hash,
            "pressure_hash": pressure.artifact_hash,
            "schedule_hash": schedule["structural_hash"],
            "status": "complete",
        }
        return DependentAtomPressureEvaluation(
            context, pressure, schedule, "complete", None,
            structural_hash(semantic))
