"""FDAS projection adapter for persistent founder/ferry operations."""

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure.coalitions import RequirementSet
from .fdas_defense import (
    FdasDefenseActionBinding,
    FdasDefenseRequirementContext,
)
from .operations import OperationState
from .transport_lifecycle import FounderTransportOperationLifecycle
from .transport_operations import FounderTransportOperationAssembler


class FdasFounderTransportProjectionAdapter(object):
    """Expose current transport lifecycle bindings without adding authority."""

    ADAPTER_IDENTITY = "fdas-founder-transport-projection/1.0"

    def __init__(self, lifecycle, ruleset_digest):
        if not isinstance(lifecycle, FounderTransportOperationLifecycle):
            raise TypeError(
                "FDAS transport projection requires transport lifecycle")
        if not isinstance(ruleset_digest, str) or not ruleset_digest:
            raise ValueError(
                "FDAS transport projection requires ruleset digest")
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
    def _participant_ids(assembly):
        return {
            "founder": assembly.intent.founder_unit_id,
            "ferry": assembly.intent.ferry_unit_id,
        }

    @staticmethod
    def _premise_for_reason(premises, reason):
        reason = str(reason or "")
        if "founder" in reason:
            return premises[0]
        if any(value in reason for value in (
                "ferry", "carrier", "transport-participant")):
            return premises[1]
        if "deadline" in reason or "expired" in reason:
            return premises[2]
        if any(value in reason for value in (
                "resource", "capacity", "conflict", "budget")):
            return premises[5]
        if any(value in reason for value in (
                "action", "advertised", "legal")):
            return premises[4]
        return premises[3]

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
            record.spec.operation_id,
            record.spec.operation_id,
            snapshot.snapshot_id,
            snapshot.legal_actions_digest,
            action,
            action_key,
            True,
            structural_hash(semantic),
        )

    @classmethod
    def _context(cls, record, assembly, snapshot, readout, request,
                 exact_reservation):
        step = record.spec.steps[record.progress.current_step_index]
        participants = cls._participant_ids(assembly)
        phase = readout.phase
        premises = (
            "participant:founder:unit:{}:current".format(
                participants["founder"]),
            "participant:ferry:unit:{}:current".format(
                participants["ferry"]),
            "deadline:turn:{}<=operation:{}".format(
                snapshot.turn, record.spec.expiry_turn),
            "phase:{}:current-precondition".format(phase),
            "phase:{}:current-byte-identical-legal-action".format(phase),
            "phase:{}:current-resource-capacity".format(phase),
        )
        roles = (
            "founder", "ferry", "deadline", "phase-precondition",
            "legal-binding", "resource-capacity",
        )
        requirement_set = RequirementSet(
            step.requirement_set_id,
            "{}:{}".format(cls.ADAPTER_IDENTITY, phase),
            premises,
            roles,
            structural_hash({
                "operation_id": record.spec.operation_id,
                "phase": phase,
                "snapshot_id": snapshot.snapshot_id,
                "step_id": step.step_id,
            }),
        )
        blocked = ()
        reason = record.progress.blocked_reason
        awaiting_effect = bool(
            record.progress.state == OperationState.ACTIVE
            and record.progress.last_snapshot_id == snapshot.snapshot_id
            and not exact_reservation)
        if awaiting_effect:
            reason = "awaiting-authoritative-step-effect"
        elif readout.disposition != "reservable":
            reason = reason or readout.reason
        elif request is None:
            reason = reason or "current-transport-resource-claims-unavailable"
        elif not exact_reservation:
            reason = reason or "current-transport-resource-capacity-unreserved"
        if reason:
            blocked = ((cls._premise_for_reason(premises, reason), reason),)
        claims = () if request is None or awaiting_effect else request.claims
        material = {
            "blocked_premises": dict(blocked),
            "operation_id": record.spec.operation_id,
            "requirement_set": requirement_set.to_dict(),
            "resource_claims": [value.to_dict() for value in claims],
            "snapshot_id": snapshot.snapshot_id,
        }
        return FdasDefenseRequirementContext(
            record.spec.operation_id,
            snapshot.snapshot_id,
            requirement_set,
            claims,
            blocked,
            structural_hash(material),
        )

    def refresh(self, snapshot):
        """Rebuild projection-only bindings from the current lifecycle state."""
        bindings = {}
        contexts = {}
        for record in self.lifecycle.store.nonterminal_records():
            if record.spec.operation_type != (
                    FounderTransportOperationAssembler.OPERATION_TYPE):
                continue
            if record.spec.ruleset_digest != self.ruleset_digest:
                raise ValueError("transport operation ruleset changed")
            assembly = self.lifecycle.assembly(record.spec.operation_id)
            if assembly is None:
                raise ValueError(
                    "transport lifecycle operation lacks its assembly")
            step_index = record.progress.current_step_index
            readout, request = (
                FounderTransportOperationAssembler.current_step_resource_request(
                    assembly, snapshot, step_index))
            reservation = self.lifecycle.ledger.reservation(
                record.spec.operation_id)
            exact_reservation = bool(
                request is not None
                and reservation is not None
                and reservation.active
                and reservation.snapshot_id == snapshot.snapshot_id
                and reservation.claims == request.claims)
            context = self._context(
                record, assembly, snapshot, readout, request,
                exact_reservation)
            contexts[record.spec.operation_id] = context
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

    def register(self, assembly, snapshot):
        updates = self.lifecycle.register(assembly, snapshot)
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
