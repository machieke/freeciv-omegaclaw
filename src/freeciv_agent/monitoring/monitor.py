"""Atomic assumption monitor and fail-closed plan execution guard."""

import threading

from .model import Invalidation


class PlanMonitor(object):
    def __init__(self):
        self._lock = threading.RLock()
        self._plans = {}
        self._status = {}
        self._atom_index = {}
        self._last_revisions = {}
        self._invalidations = {}

    def register(self, plan):
        if plan.status != "ACTIVE":
            raise ValueError("only active plans can be monitored")
        with self._lock:
            if plan.plan_id in self._plans:
                raise ValueError("plan already registered")
            self._plans[plan.plan_id] = plan
            self._status[plan.plan_id] = "ACTIVE"
            for assumption in plan.assumptions:
                self._atom_index.setdefault(assumption.atom_id, set()).add(plan.plan_id)
        return plan

    def evaluate_batch(self, revisions):
        """Apply simultaneous revisions as one deterministic transaction."""
        revisions = tuple(sorted(revisions, key=lambda item: (
            item.turn, item.atom_id, item.revision_event_id)))
        if not revisions:
            return tuple()
        turns = {item.turn for item in revisions}
        if len(turns) != 1:
            raise ValueError("revision batch must be turn-atomic")
        with self._lock:
            affected = {}
            relevant_revisions = {}
            for revision in revisions:
                self._last_revisions[revision.atom_id] = revision.revision_event_id
                for plan_id in sorted(self._atom_index.get(revision.atom_id, ())):
                    if self._status.get(plan_id) != "ACTIVE":
                        continue
                    plan = self._plans[plan_id]
                    for assumption in plan.assumptions:
                        if (assumption.atom_id == revision.atom_id
                                and revision.posterior_tv["confidence"] < assumption.threshold
                                and revision.prior_tv["confidence"] >= assumption.threshold):
                            affected.setdefault(plan_id, []).append(assumption)
                            relevant_revisions.setdefault(plan_id, []).append(revision)
            invalidations = []
            for plan_id in sorted(affected):
                invalidation = Invalidation.create(
                    plan_id, revisions[0].turn, affected[plan_id], relevant_revisions[plan_id])
                self._status[plan_id] = "INVALID"
                self._invalidations[plan_id] = invalidation
                invalidations.append(invalidation)
            return tuple(invalidations)

    def evaluate(self, revision):
        return self.evaluate_batch((revision,))

    def guard_execution(self, plan_id, required_revision_ids=None):
        with self._lock:
            if plan_id not in self._plans:
                return False, "unregistered_plan"
            if self._status[plan_id] != "ACTIVE":
                return False, "plan_invalid"
            required = dict(required_revision_ids or {})
            plan = self._plans[plan_id]
            for assumption in plan.assumptions:
                current = self._last_revisions.get(assumption.atom_id)
                if assumption.atom_id in required and current != required[assumption.atom_id]:
                    return False, "stale_assumption_revision"
            return True, None

    def invalidation(self, plan_id):
        with self._lock:
            return self._invalidations.get(plan_id)

    def status(self, plan_id):
        with self._lock:
            return self._status.get(plan_id)

    def emit_batch(self, revisions, writer, caused_by=None):
        invalidations = self.evaluate_batch(revisions)
        events = []
        for invalidation in invalidations:
            trigger_events = []
            revisions_by_atom = {item.atom_id: item for item in invalidation.revisions}
            for assumption in invalidation.broken_assumptions:
                revision = revisions_by_atom[assumption.atom_id]
                trigger_events.append(writer.emit("monitor_trigger", invalidation.turn, {
                    "affected_plan_ids": [invalidation.plan_id],
                    "atom_id": assumption.atom_id,
                    "posterior_tv": revision.posterior_tv,
                    "prior_tv": revision.prior_tv,
                    "threshold": assumption.threshold,
                    "trigger_id": "trigger-" + invalidation.invalidation_id,
                }, caused_by=caused_by))
            event = writer.emit(
                "plan_invalidated", invalidation.turn, invalidation.to_dict(),
                caused_by=[item["event_id"] for item in trigger_events])
            events.append((invalidation, event))
        return tuple(events)
