"""PLN feasibility and scheduler cost kept as separate candidate fields."""

from ..oracle import Goal
from ..planning import NonPlan
from .model import CandidateGrade


class GoalGrader(object):
    def __init__(self, oracle, scheduler):
        self.oracle = oracle
        self.scheduler = scheduler

    def grade(self, candidate, crisp_state, numeric_snapshot):
        if candidate.predicate == "researchable":
            goal = Goal(candidate.predicate, tuple(candidate.arguments))
        else:
            goal = Goal(candidate.predicate, tuple(candidate.arguments))
        result = self.oracle.deps(goal, crisp_state)
        if not result.executable:
            return CandidateGrade(
                candidate, False, 0.0, None, result.status,
                proof_hash=result.proof["structural_hash"], reason=result.error)
        plan = self.scheduler.schedule(result, numeric_snapshot)
        if isinstance(plan, NonPlan):
            return CandidateGrade(
                candidate, False, 1.0, None, plan.status,
                proof_hash=result.proof["structural_hash"], reason=plan.reason)
        return CandidateGrade(
            candidate, True, plan.feasibility_grade, plan.scheduler_cost, "GRADED",
            proof_hash=result.proof["structural_hash"], plan_id=plan.plan_id)

    def grade_all(self, proposal, crisp_state, numeric_snapshot):
        return tuple(self.grade(candidate, crisp_state, numeric_snapshot)
                     for candidate in proposal.goals)

    @staticmethod
    def select(proposal, grades):
        feasible = {row.goal.goal_id: row for row in grades if row.valid}
        if proposal.selection in feasible:
            return feasible[proposal.selection]
        if not feasible:
            return None
        return min(feasible.values(), key=lambda row: (
            row.scheduler_cost, -row.feasibility_grade, row.goal.goal_id))

    @staticmethod
    def select_best(grades):
        """Select the lowest-cost feasible candidate for the graded A/B policy."""
        feasible = [row for row in grades if row.valid]
        if not feasible:
            return None
        return min(feasible, key=lambda row: (
            row.scheduler_cost, -row.feasibility_grade, row.goal.goal_id))
