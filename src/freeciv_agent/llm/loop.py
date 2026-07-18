"""Bounded proposer/verify/grade/select loop with safe timeout fallback."""

import time

from .model import TurnDecision


class ConstrainedTurnLoop(object):
    def __init__(self, proposer, router, grader, timeout_seconds=30.0):
        self.proposer = proposer
        self.router = router
        self.grader = grader
        self.timeout_seconds = float(timeout_seconds)

    def _timed_out(self, started):
        return time.perf_counter() - started > self.timeout_seconds

    def run(self, state_summary, crisp_state, numeric_snapshot,
            plan_status=None, invalidations=None, budgets=None):
        started = time.perf_counter()
        try:
            proposal, _ = self.proposer.propose(
                state_summary, plan_status, invalidations, budgets)
            if self._timed_out(started):
                raise TimeoutError("proposer_timeout")
            verifications = self.router.route_proposal(proposal)
            if self._timed_out(started):
                raise TimeoutError("verification_timeout")
            grades = self.grader.grade_all(proposal, crisp_state, numeric_snapshot)
            if self._timed_out(started):
                raise TimeoutError("grading_timeout")
            selected = self.grader.select(proposal, grades)
            elapsed = (time.perf_counter() - started) * 1000.0
            status = "SELECTED" if selected is not None else "NO_PLAN"
            return TurnDecision(status, proposal, selected, grades, verifications, elapsed,
                                fallback_action={"type": "end_turn"} if selected is None else None)
        except Exception as exc:
            return TurnDecision(
                "SAFE_FALLBACK", None, None, (), (),
                (time.perf_counter() - started) * 1000.0,
                fallback_action={"type": "end_turn"},
                error="{}: {}".format(type(exc).__name__, exc))
