"""Deterministic proof-DAG scheduler; no logical deductions occur here."""

import itertools
import math
import time

from ..events.schema import structural_hash
from .model import (BranchScore, NonPlan, Plan, PlanStep, ResourceLedger,
                    ResourceLedgerEntry)


SOLVER_IDENTITY = "proof-dag-scheduler/1.0"


def research_duration_turns(cost, progress, beakers_per_turn):
    """The declared M3 duration function used by plans and live ETA audits."""
    rate = int(beakers_per_turn)
    if rate <= 0:
        raise ValueError("beakers_per_turn must be positive")
    remaining = max(0, int(cost) - int(progress))
    return int(math.ceil(float(remaining) / rate))


def _deduplicate(sequence):
    result = []
    for item in sequence:
        if item not in result:
            result.append(item)
    return tuple(result)


class _ProofAlternatives(object):
    def __init__(self, proof):
        self.proof = proof
        self.nodes = {node["node_id"]: node for node in proof["nodes"]}

    def _combine(self, groups):
        if not groups:
            return [()]
        return [_deduplicate(itertools.chain.from_iterable(items))
                for items in itertools.product(*groups)]

    def expand(self, node_id, active=None):
        active = set() if active is None else set(active)
        if node_id in active:
            return []
        active.add(node_id)
        node = self.nodes[node_id]
        children = node.get("premise_node_refs", [])
        if node["kind"] == "or":
            result = []
            for child in children:
                result.extend(self.expand(child, active))
            return result
        groups = [self.expand(child, active) for child in children]
        if any(not group for group in groups):
            return []
        combined = self._combine(groups)
        atom = node["atom"]
        if (atom["predicate"] == "has-tech" and not node["satisfied"]
                and node["kind"] in ("goal", "premise")):
            tech = str(atom["args"][-1])
            combined = [_deduplicate(tuple(items) + (tech,)) for items in combined]
        return combined

    def alternatives(self, target):
        rows = self.expand(self.proof["root_node_id"])
        return tuple(sorted({_deduplicate(tuple(row) + (str(target),)) for row in rows}))


class ProofScheduler(object):
    def __init__(self, cost_profile="turns-to-goal", gold_weight=0.0,
                 timeout_ms=500.0):
        if cost_profile not in ("turns-to-goal", "gold-weighted"):
            raise ValueError("unknown cost profile")
        self.cost_profile = cost_profile
        self.gold_weight = float(gold_weight)
        self.timeout_ms = float(timeout_ms)

    def _score(self, branch_id, steps, gold):
        turns = sum(step.duration_turns for step in steps)
        scheduler_cost = float(turns)
        if self.cost_profile == "gold-weighted":
            scheduler_cost += self.gold_weight * max(0.0, -float(gold))
        return BranchScore(branch_id, 1.0, scheduler_cost, turns, True)

    def schedule(self, query_result, numeric_snapshot):
        proof = query_result.proof
        proof_hash = proof["structural_hash"]
        if (not query_result.executable or query_result.status == "ERROR"):
            return NonPlan("NO_PLAN", "PROOF_NOT_EXECUTABLE", numeric_snapshot.snapshot_id,
                           proof_hash, SOLVER_IDENTITY, query_result.error)
        if numeric_snapshot.beakers_per_turn <= 0:
            return NonPlan("NO_PLAN", "BEAKERS_PER_TURN_UNAVAILABLE",
                           numeric_snapshot.snapshot_id, proof_hash, SOLVER_IDENTITY)
        started = time.perf_counter()
        target = str(query_result.goal.arguments[-1])
        alternatives = _ProofAlternatives(proof).alternatives(target)
        if not alternatives and query_result.status == "PROVED":
            alternatives = ((),)
        if not alternatives:
            return NonPlan("NO_PLAN", "NO_FEASIBLE_PROOF_BRANCH",
                           numeric_snapshot.snapshot_id, proof_hash, SOLVER_IDENTITY)
        candidates = []
        rejected = []
        for index, technologies in enumerate(alternatives):
            if (time.perf_counter() - started) * 1000.0 > self.timeout_ms:
                return NonPlan("NO_PLAN", "SCHEDULER_TIMEOUT", numeric_snapshot.snapshot_id,
                               proof_hash, SOLVER_IDENTITY)
            steps = []
            current_turn = numeric_snapshot.turn
            missing_cost = None
            for position, tech in enumerate(technologies):
                cost = numeric_snapshot.tech_cost(tech)
                if cost is None:
                    missing_cost = tech
                    break
                progress = (numeric_snapshot.current_progress
                            if tech == numeric_snapshot.current_research else 0)
                duration = research_duration_turns(
                    cost, progress, numeric_snapshot.beakers_per_turn)
                current_turn += duration
                step_id = "step-{:02d}-{}".format(position, structural_hash(tech)[:10])
                steps.append(PlanStep(
                    step_id, "research", {"tech": tech}, current_turn, duration,
                    float(cost), snapshot_id=numeric_snapshot.snapshot_id,
                    legal_actions_digest=numeric_snapshot.legal_actions_digest))
            branch_id = "branch-" + structural_hash(list(technologies))[:16]
            if missing_cost is not None:
                rejected.append(BranchScore(branch_id, 1.0, 1e30, 0, False,
                                            "missing research cost for {}".format(missing_cost)))
                continue
            score = self._score(branch_id, steps, numeric_snapshot.gold)
            candidates.append((score, tuple(steps), technologies))
        if not candidates:
            return NonPlan("NO_PLAN", "MISSING_GROUNDED_COST",
                           numeric_snapshot.snapshot_id, proof_hash, SOLVER_IDENTITY,
                           [item.to_dict() for item in rejected])
        candidates.sort(key=lambda item: (
            item[0].scheduler_cost, item[0].predicted_turns,
            tuple(step.target["tech"] for step in item[1]), item[0].branch_id))
        selected, steps, _ = candidates[0]
        all_scores = tuple(sorted([item[0] for item in candidates] + rejected,
                                  key=lambda item: item.branch_id))
        entries = []
        available = float(numeric_snapshot.beakers_per_turn)
        for step in steps:
            entries.append(ResourceLedgerEntry(
                "research-slot", available, available, 0.0, step.step_id))
            # The sequential slot becomes available again only after the step; model each
            # allocation as a separate time-scoped resource to avoid false double-spend.
            available = float(numeric_snapshot.beakers_per_turn)
            entries[-1] = ResourceLedgerEntry(
                "research-slot@{}".format(step.step_id), available, available, 0.0,
                step.step_id)
        ledger = ResourceLedger(tuple(entries))
        plan_material = {
            "cost_profile": self.cost_profile, "proof": proof_hash,
            "selected": selected.branch_id, "snapshot": numeric_snapshot.snapshot_id,
            "steps": [step.to_dict() for step in steps],
        }
        plan_id = "plan-" + structural_hash(plan_material)[:20]
        root_atom_id = {node["node_id"]: node for node in proof["nodes"]}[
            proof["root_node_id"]]["atom"]["atom_id"]
        return Plan(
            plan_id, root_atom_id, proof_hash,
            numeric_snapshot.snapshot_id, steps, ledger, all_scores,
            selected.branch_id, self.cost_profile, selected.scheduler_cost,
            selected.feasibility_grade, selected.predicted_turns, SOLVER_IDENTITY)

    def emit_plan(self, query_result, numeric_snapshot, writer, turn, caused_by=None):
        result = self.schedule(query_result, numeric_snapshot)
        if isinstance(result, NonPlan):
            event = writer.emit("logging_gap", turn, {
                "component": "proof-scheduler", "missing": result.reason,
                "detail": str(result.diagnostic or result.reason),
            }, caused_by=caused_by)
        else:
            event = writer.emit("plan_created", turn, {"plan": result.to_dict()},
                                caused_by=caused_by)
        return result, event


def validate_next_step(plan, current_snapshot_id, grounded_checks=()):
    if plan.status != "ACTIVE":
        return False, "plan_not_active"
    if plan.snapshot_id != current_snapshot_id:
        return False, "stale_snapshot"
    if not plan.steps:
        return False, "plan_has_no_steps"
    for check in grounded_checks:
        if check.snapshot_id != current_snapshot_id or not check.executable:
            return False, "grounded_precondition_failed"
    return True, None
