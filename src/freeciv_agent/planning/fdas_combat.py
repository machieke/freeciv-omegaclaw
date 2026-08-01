"""FDAS projection adapter for the persistent atomic combat lifecycle."""

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure.coalitions import RequirementSet
from .combat_lifecycle import CombatOperationLifecycle
from .combat_operations import CombatOperationAssembler
from .fdas_defense import (
    FdasDefenseActionBinding,
    FdasDefenseRequirementContext,
)
from .operations import OperationState


class FdasCombatProjectionAdapter(object):
    """Expose combat lifecycle state to generic FDAS operation scopes."""

    ADAPTER_IDENTITY = "fdas-combat-operation-projection/1.0"

    def __init__(self, lifecycle, ruleset_digest):
        if not isinstance(lifecycle, CombatOperationLifecycle):
            raise TypeError("FDAS combat projection requires combat lifecycle")
        if not isinstance(ruleset_digest, str) or not ruleset_digest:
            raise ValueError("FDAS combat projection requires ruleset digest")
        self.lifecycle = lifecycle
        self.ruleset_digest = ruleset_digest
        self._bindings = {}
        self._contexts = {}

    @property
    def store(self):
        return self.lifecycle.store

    def binding(self, operation_id):
        return self._bindings.get(str(operation_id))

    def bindings(self):
        return tuple(self._bindings[key] for key in sorted(self._bindings))

    def requirement_context(self, operation_id):
        return self._contexts.get(str(operation_id))

    def requirement_contexts(self):
        return tuple(self._contexts[key] for key in sorted(self._contexts))

    @staticmethod
    def _binding(record, snapshot, action):
        action_key = canonical_json_bytes(action).decode("utf-8")
        if action_key not in snapshot.legal_action_json:
            return None
        semantic = {
            "action": action,
            "action_key": action_key,
            "domain_operation_id": record.spec.operation_id,
            "legal_actions_digest": snapshot.legal_actions_digest,
            "legal_bound": True,
            "operation_id": record.spec.operation_id,
            "snapshot_id": snapshot.snapshot_id,
        }
        return FdasDefenseActionBinding(
            record.spec.operation_id, record.spec.operation_id,
            snapshot.snapshot_id, snapshot.legal_actions_digest,
            action, action_key, True, structural_hash(semantic))

    @staticmethod
    def _premise_for_reason(premises, reason):
        reason = str(reason or "")
        if "participant" in reason or "actor" in reason:
            return premises[0]
        if "target" in reason or "visible" in reason:
            return premises[1]
        if "deadline" in reason or "expired" in reason:
            return premises[2]
        if "material" in reason or "probability" in reason:
            return premises[3]
        if "action" in reason or "legal" in reason:
            return premises[4]
        if any(value in reason for value in (
                "resource", "capacity", "conflict", "budget")):
            return premises[5]
        return premises[3]

    @classmethod
    def _context(cls, record, assembly, snapshot, readout, claims,
                 exact_reservation):
        step = record.spec.steps[record.progress.current_step_index]
        premises = (
            "combat:step:{}:participants-current".format(step.step_id),
            "combat:target:unit:{}:packet-visible".format(
                assembly.target_unit_id),
            "deadline:turn:{}<=operation:{}".format(
                snapshot.turn, record.spec.expiry_turn),
            "combat:step:{}:conservative-interval-and-material-positive".format(
                step.step_id),
            "combat:step:{}:current-byte-identical-legal-action".format(
                step.step_id),
            "combat:step:{}:current-resource-capacity".format(step.step_id),
        )
        requirement_set = RequirementSet(
            step.requirement_set_id,
            "{}:step:{}".format(cls.ADAPTER_IDENTITY, step.step_id),
            premises,
            ("participants", "target", "deadline", "transition-value",
             "legal-binding", "resource-capacity"),
            structural_hash({
                "operation_id": record.spec.operation_id,
                "snapshot_id": snapshot.snapshot_id,
                "step_id": step.step_id,
            }))
        awaiting_effect = bool(
            record.progress.state == OperationState.ACTIVE
            and record.progress.last_snapshot_id == snapshot.snapshot_id
            and not exact_reservation)
        reason = record.progress.blocked_reason
        if awaiting_effect:
            reason = "awaiting-authoritative-combat-effect"
        elif readout.disposition != "reservable":
            reason = reason or readout.reason
        elif not claims:
            reason = reason or "current-combat-resource-claims-unavailable"
        elif not exact_reservation:
            reason = reason or "current-combat-resource-capacity-unreserved"
        blocked = () if not reason else ((
            cls._premise_for_reason(premises, reason), reason),)
        claims = () if awaiting_effect else tuple(claims)
        material = {
            "blocked_premises": dict(blocked),
            "operation_id": record.spec.operation_id,
            "requirement_set": requirement_set.to_dict(),
            "resource_claims": [value.to_dict() for value in claims],
            "snapshot_id": snapshot.snapshot_id,
        }
        return FdasDefenseRequirementContext(
            record.spec.operation_id, snapshot.snapshot_id,
            requirement_set, claims, blocked, structural_hash(material))

    @staticmethod
    def _current_claims(record, assembly, snapshot):
        if record.progress.current_step_index == 0:
            return assembly.resource_request.claims
        request = CombatOperationAssembler.step_resource_request(
            assembly, snapshot, record.progress.current_step_index)
        return () if request is None else request.claims

    def refresh(self, snapshot):
        bindings = {}
        contexts = {}
        for record in self.lifecycle.store.nonterminal_records():
            if record.spec.operation_type != CombatOperationAssembler.OPERATION_TYPE:
                continue
            if record.spec.ruleset_digest != self.ruleset_digest:
                raise ValueError("combat operation ruleset changed")
            assembly = self.lifecycle.assembly(record.spec.operation_id)
            if assembly is None:
                raise ValueError("combat lifecycle operation lacks assembly")
            readout = CombatOperationAssembler.readout(
                assembly, snapshot, record.progress.current_step_index)
            claims = self._current_claims(
                record, assembly, snapshot)
            reservation = self.lifecycle.ledger.reservation(
                record.spec.operation_id)
            exact_reservation = bool(
                claims and reservation is not None and reservation.active
                and reservation.snapshot_id == snapshot.snapshot_id
                and reservation.claims == tuple(claims))
            contexts[record.spec.operation_id] = self._context(
                record, assembly, snapshot, readout, claims,
                exact_reservation)
            if (readout.disposition == "reservable"
                    and exact_reservation
                    and record.progress.state in (
                        OperationState.RESERVED, OperationState.ACTIVE)):
                binding = self._binding(
                    record, snapshot, readout.next_action)
                if binding is not None:
                    bindings[record.spec.operation_id] = binding
        self._bindings = bindings
        self._contexts = contexts
        return self

    def register_schedule(self, assemblies, schedule, snapshot):
        updates = self.lifecycle.register_schedule(
            assemblies, schedule, snapshot)
        self.refresh(snapshot)
        return updates

    def observe(self, snapshot):
        updates = self.lifecycle.observe(snapshot)
        self.refresh(snapshot)
        return updates

    def commit_matching_action(self, snapshot, action, accepted, reason=None):
        updates = self.lifecycle.commit_matching_action(
            snapshot, action, accepted, reason=reason)
        self.refresh(snapshot)
        return updates
