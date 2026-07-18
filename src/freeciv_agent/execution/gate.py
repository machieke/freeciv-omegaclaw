"""Fail-closed local action gate preventing stale or unverified submissions."""

import json
import uuid
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes


@dataclass(frozen=True)
class ProposedAction:
    action_id: str
    action: dict
    snapshot_id: str
    legal_actions_digest: str
    plan_id: object = None
    step_id: object = None
    grounded_preconditions: tuple = ()

    @classmethod
    def create(cls, action, snapshot, plan_id=None, step_id=None,
               grounded_preconditions=()):
        return cls("action-" + uuid.uuid4().hex, dict(action), snapshot.snapshot_id,
                   snapshot.legal_actions_digest, plan_id, step_id,
                   tuple(grounded_preconditions))


@dataclass(frozen=True)
class ActionOutcome:
    action_id: str
    status: str
    reason: object
    submitted: bool
    engine_response: object = None
    result_event_id: object = None


def _legal_form(action):
    normalized = dict(action)
    normalized.pop("reason", None)
    normalized.pop("is_valid", None)
    return canonical_json_bytes(normalized).decode("utf-8")


class ExecutionGate(object):
    def __init__(self, snapshot_store, transport, writer=None, plan_monitor=None):
        self.snapshot_store = snapshot_store
        self.transport = transport
        self.writer = writer
        self.plan_monitor = plan_monitor

    def _reject(self, proposed, snapshot, reason, caused_by=None):
        result_event = None
        if self.writer is not None:
            verification = self.writer.emit("verification", snapshot.turn, {
                "verification_id": "verify-" + proposed.action_id,
                "proposal_id": proposed.plan_id or proposed.action_id,
                "claim_id": proposed.step_id or proposed.action_id,
                "verdict": "disbelieve", "check": reason, "evidence_atom_ids": [],
            }, caused_by=caused_by)
            if proposed.plan_id is not None and proposed.step_id is not None:
                result_event = self.writer.emit("plan_step_executed", snapshot.turn, {
                    "plan_id": proposed.plan_id, "step_id": proposed.step_id,
                    "snapshot_id": proposed.snapshot_id, "status": "rejected",
                }, caused_by=[verification["event_id"]])
            else:
                result_event = verification
        return ActionOutcome(
            proposed.action_id, "rejected", reason, False,
            result_event_id=None if result_event is None else result_event["event_id"])

    def _preflight(self, game_id, player_id, proposed):
        current = self.snapshot_store.current(game_id, player_id)
        if current is None:
            return None, "missing_snapshot"
        if proposed.snapshot_id != current.snapshot_id:
            return current, "stale_snapshot"
        if proposed.legal_actions_digest != current.legal_actions_digest:
            return current, "stale_legal_actions"
        if proposed.plan_id is not None and self.plan_monitor is not None:
            valid, reason = self.plan_monitor.guard_execution(proposed.plan_id)
            if not valid:
                return current, reason
        if not current.ruleset_ready:
            return current, "ruleset_unavailable"
        legal = _legal_form(proposed.action)
        if legal not in current.legal_action_json:
            return current, "action_not_in_server_legal_set"
        if str(proposed.action.get("action_type", proposed.action.get("type", ""))).startswith(
                ("city_production", "city_change_production")):
            city_id = proposed.action.get("city_id", proposed.action.get("actor_id"))
            city = current.city(city_id) if city_id is not None else None
            if city is None or not city.buildability_available:
                return current, "buildability_unavailable"
        for check in proposed.grounded_preconditions:
            if check.snapshot_id != current.snapshot_id or not check.executable:
                return current, "grounded_precondition_failed"
        return current, None

    def _emit_sent(self, current, proposed, caused_by):
        if self.writer is None:
            return None
        return self.writer.emit("action_sent", current.turn, {
            "action": proposed.action, "action_id": proposed.action_id,
            "legal_actions_digest": proposed.legal_actions_digest,
            "plan_id": proposed.plan_id, "snapshot_id": proposed.snapshot_id,
            "step_id": proposed.step_id,
        }, caused_by=caused_by)

    def _complete(self, current, proposed, response, sent_event):
        accepted = not (isinstance(response, dict) and response.get("accepted") is False)
        status = "accepted" if accepted else "rejected"
        result_event = None
        if self.writer is not None:
            result_event = self.writer.emit("action_result", current.turn, {
                "action_id": proposed.action_id, "engine_response": response,
                "engine_turn": current.turn, "status": status,
            }, caused_by=[sent_event["event_id"]])
            if proposed.plan_id is not None and proposed.step_id is not None:
                result_event = self.writer.emit("plan_step_executed", current.turn, {
                    "plan_id": proposed.plan_id, "step_id": proposed.step_id,
                    "snapshot_id": proposed.snapshot_id,
                    "status": "completed" if accepted else "rejected",
                }, caused_by=[result_event["event_id"]])
        return ActionOutcome(
            proposed.action_id, status, None if accepted else "engine_rejected",
            True, response, None if result_event is None else result_event["event_id"])

    def execute(self, game_id, player_id, proposed, caused_by=None):
        current, reason = self._preflight(game_id, player_id, proposed)
        if current is None:
            return ActionOutcome(proposed.action_id, "rejected", "missing_snapshot", False)
        if reason is not None:
            return self._reject(proposed, current, reason, caused_by)
        sent_event = self._emit_sent(current, proposed, caused_by)
        response = self.transport(dict(proposed.action))
        return self._complete(current, proposed, response, sent_event)

    async def execute_async(self, game_id, player_id, proposed, caused_by=None):
        """Async transport variant with exactly the same fail-closed preflight."""
        current, reason = self._preflight(game_id, player_id, proposed)
        if current is None:
            return ActionOutcome(proposed.action_id, "rejected", "missing_snapshot", False)
        if reason is not None:
            return self._reject(proposed, current, reason, caused_by)
        sent_event = self._emit_sent(current, proposed, caused_by)
        response = await self.transport(dict(proposed.action))
        return self._complete(current, proposed, response, sent_event)
