"""Shadow-mode lifecycle and induction operations with typed packets."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from .induction import InducedRuleProposal, ReplayValidation
from .lifecycle import CloneManager, CloneState
from .model import CostVector, Operation
from .packets import PacketCost, ResourceKind
from .teleology import TypedAdvantage


def _nonnegative(value, name):
    value = float(value)
    if value < 0.0 or not math.isfinite(value):
        raise ValueError(
            "{} must be finite and non-negative".format(name))
    return value


@dataclass(frozen=True)
class CloneSplitRequest:
    atom_id: str
    parent_clone_id: str
    generation: int
    current_clone_count: int
    predictive_gain: float
    added_parameters: int
    split_score: float
    successor_gate_passed: bool
    lineage_gate_passed: bool
    merge_gate_checked: bool
    trigger_pressure: float

    def __post_init__(self):
        if not self.atom_id or not self.parent_clone_id:
            raise ValueError(
                "clone split request requires stable IDs")
        for value, name, minimum in (
                (self.generation, "clone generation", 1),
                (self.current_clone_count,
                 "current clone count", 1),
                (self.added_parameters,
                 "added parameters", 0)):
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < minimum):
                raise ValueError(
                    "{} must be an integer >= {}".format(
                        name, minimum))
        _nonnegative(
            self.predictive_gain, "predictive gain")
        if not 0.0 <= float(self.split_score) <= 1.0:
            raise ValueError("split score must be in [0,1]")
        _nonnegative(
            self.trigger_pressure, "trigger pressure")
        for value, name in (
                (self.successor_gate_passed, "successor gate"),
                (self.lineage_gate_passed, "lineage gate"),
                (self.merge_gate_checked, "merge gate")):
            if not isinstance(value, bool):
                raise TypeError("{} must be boolean".format(name))

    def to_dict(self):
        return {
            "added_parameters": int(self.added_parameters),
            "atom_id": self.atom_id,
            "current_clone_count": int(
                self.current_clone_count),
            "generation": int(self.generation),
            "lineage_gate_passed": bool(
                self.lineage_gate_passed),
            "merge_gate_checked": bool(
                self.merge_gate_checked),
            "parent_clone_id": self.parent_clone_id,
            "predictive_gain": float(self.predictive_gain),
            "split_score": float(self.split_score),
            "successor_gate_passed": bool(
                self.successor_gate_passed),
            "trigger_pressure": float(self.trigger_pressure),
        }


@dataclass(frozen=True)
class StructuralOperationDecision:
    accepted: bool
    reason: object
    operation: object
    shadow_mode: bool = True

    def __post_init__(self):
        if not isinstance(self.accepted, bool):
            raise TypeError(
                "structural decision accepted must be boolean")
        if self.accepted != (self.operation is not None):
            raise ValueError(
                "accepted structural decision requires operation")
        if not self.accepted and not self.reason:
            raise ValueError(
                "rejected structural decision requires reason")
        if (self.operation is not None
                and not isinstance(self.operation, Operation)):
            raise TypeError(
                "structural decision operation must be Operation")
        if not self.shadow_mode:
            raise ValueError(
                "S2 structural operations must remain shadow-only")

    def to_dict(self):
        return {
            "accepted": bool(self.accepted),
            "operation": (
                None if self.operation is None
                else self.operation.to_dict()),
            "reason": self.reason,
            "shadow_mode": True,
        }


@dataclass(frozen=True)
class StructuralShadowRecord:
    operation_id: str
    structural_kind: str
    selected: bool
    expected_usefulness: float
    realized_usefulness: object
    source_state_hash: str

    def __post_init__(self):
        if not self.operation_id or not self.structural_kind:
            raise ValueError(
                "shadow record requires stable IDs")
        if not isinstance(self.selected, bool):
            raise TypeError(
                "shadow selection must be boolean")
        _nonnegative(
            self.expected_usefulness,
            "expected usefulness")
        if self.realized_usefulness is not None:
            _nonnegative(
                self.realized_usefulness,
                "realized usefulness")
        if (not isinstance(self.source_state_hash, str)
                or len(self.source_state_hash) != 64):
            raise ValueError(
                "shadow source state hash must be SHA-256")

    def to_dict(self):
        return {
            "expected_usefulness": float(
                self.expected_usefulness),
            "operation_id": self.operation_id,
            "realized_usefulness": (
                None if self.realized_usefulness is None else
                float(self.realized_usefulness)),
            "selected": bool(self.selected),
            "source_state_hash": self.source_state_hash,
            "structural_kind": self.structural_kind,
        }


class StructuralShadowLedger:
    """In-memory control evaluation; owns no semantic store."""

    def __init__(self):
        self._records = {}

    @property
    def records(self):
        return tuple(
            self._records[key] for key in sorted(self._records))

    def record(
            self, operation, selected,
            expected_usefulness, source_state_hash):
        if not isinstance(operation, Operation):
            raise TypeError(
                "shadow ledger requires Operation")
        payload = operation.payload
        if (not isinstance(payload, dict)
                or not payload.get("shadow_mode")
                or not payload.get("structural_kind")):
            raise ValueError(
                "shadow ledger accepts only shadow structural operations")
        record = StructuralShadowRecord(
            operation.operation_id,
            payload["structural_kind"],
            selected, expected_usefulness, None,
            source_state_hash)
        existing = self._records.get(operation.operation_id)
        if existing is not None and existing != record:
            raise ValueError(
                "shadow operation identity reused")
        self._records[operation.operation_id] = record
        return record

    def realize(self, operation_id, usefulness):
        record = self._records.get(str(operation_id))
        if record is None:
            raise KeyError("unknown shadow operation")
        updated = StructuralShadowRecord(
            record.operation_id, record.structural_kind,
            record.selected, record.expected_usefulness,
            usefulness, record.source_state_hash)
        self._records[record.operation_id] = updated
        return updated


class StructuralOperationFactory:
    """Build lifecycle/induction work without applying durable mutation."""

    def __init__(self, clone_manager=None):
        self.clone_manager = clone_manager or CloneManager()
        if not isinstance(self.clone_manager, CloneManager):
            raise TypeError(
                "structural factory requires CloneManager")

    @staticmethod
    def _operation(
            operation_id, atom_id, mode, kind,
            packet_costs, payload, success_probability=1.0,
            information_gain=0.0,
            externally_consequential=False,
            typed_advantages=(), causal_kind="diagnostic"):
        material = dict(payload)
        material.update({
            "shadow_mode": True,
            "structural_kind": kind,
        })
        return Operation(
            operation_id, atom_id, mode,
            CostVector(compute=1.0),
            causal_kind=causal_kind,
            success_probability=success_probability,
            information_gain=information_gain,
            payload=material,
            packet_costs=tuple(packet_costs),
            externally_consequential=(
                externally_consequential),
            typed_advantages=tuple(typed_advantages))

    def propose_clone_split(self, request):
        if not isinstance(request, CloneSplitRequest):
            raise TypeError(
                "clone split proposal requires CloneSplitRequest")
        if not request.successor_gate_passed:
            return StructuralOperationDecision(
                False, "successor_gate_failed", None)
        if not request.lineage_gate_passed:
            return StructuralOperationDecision(
                False, "lineage_gate_failed", None)
        if not request.merge_gate_checked:
            return StructuralOperationDecision(
                False, "merge_gate_not_checked", None)
        accepted = self.clone_manager.accept_split(
            request.current_clone_count,
            request.predictive_gain,
            request.added_parameters,
            request.split_score)
        if not accepted:
            return StructuralOperationDecision(
                False, "predictive_complexity_or_cap_gate_failed",
                None)
        operation = self._operation(
            "propose-clone-split-{}".format(
                structural_hash(request.to_dict())[:20]),
            request.atom_id, "expand",
            "propose_clone_split",
            (PacketCost(ResourceKind.EXPANSION, 1),),
            {"request": request.to_dict()},
            information_gain=min(
                1.0, request.predictive_gain))
        return StructuralOperationDecision(
            True, None, operation)

    def evaluate_clone_split(self, proposal):
        if (not isinstance(proposal, StructuralOperationDecision)
                or not proposal.accepted
                or proposal.operation.payload.get(
                    "structural_kind")
                != "propose_clone_split"):
            return StructuralOperationDecision(
                False, "accepted_split_proposal_required", None)
        request = proposal.operation.payload["request"]
        operation = self._operation(
            "evaluate-{}".format(proposal.operation.operation_id),
            proposal.operation.atom_id, "infer",
            "evaluate_clone_split",
            (
                PacketCost(ResourceKind.CPU, 1),
                PacketCost(ResourceKind.SIMULATION, 1),
            ),
            {
                "request": request,
                "source_operation_id": (
                    proposal.operation.operation_id),
            },
            information_gain=float(
                request["predictive_gain"]))
        return StructuralOperationDecision(
            True, None, operation)

    def commit_clone_split(
            self, proposal, evaluated, exact_validation,
            current_generation):
        if not isinstance(exact_validation, bool):
            raise TypeError(
                "exact validation flag must be boolean")
        if (not proposal.accepted or not evaluated.accepted):
            return StructuralOperationDecision(
                False, "proposal_and_evaluation_required", None)
        request = proposal.operation.payload["request"]
        if int(current_generation) != int(request["generation"]):
            return StructuralOperationDecision(
                False, "stale_clone_generation", None)
        if not exact_validation:
            return StructuralOperationDecision(
                False, "exact_validation_required", None)
        operation = self._operation(
            "commit-{}".format(proposal.operation.operation_id),
            proposal.operation.atom_id, "expand",
            "commit_clone_split",
            (
                PacketCost(ResourceKind.DURABLE_MUTATION, 1),
                PacketCost(ResourceKind.EXACT_RULE, 1),
            ),
            {
                "expected_generation": int(
                    request["generation"]),
                "source_evaluation_id": (
                    evaluated.operation.operation_id),
                "source_operation_id": (
                    proposal.operation.operation_id),
                "validator_approved": True,
            },
            externally_consequential=True)
        return StructuralOperationDecision(
            True, None, operation)

    def propose_clone_merge(
            self, atom_id, left, right, generation,
            trigger_pressure):
        if (not isinstance(left, CloneState)
                or not isinstance(right, CloneState)):
            raise TypeError(
                "clone merge requires CloneState inputs")
        if (left.atom_id != str(atom_id)
                or right.atom_id != str(atom_id)
                or left.clone_id == right.clone_id):
            return StructuralOperationDecision(
                False, "invalid_merge_lineage", None)
        if not self.clone_manager.merge_eligible(left, right):
            return StructuralOperationDecision(
                False, "merge_similarity_gate_failed", None)
        material = {
            "atom_id": str(atom_id),
            "generation": int(generation),
            "left_clone_id": left.clone_id,
            "right_clone_id": right.clone_id,
            "trigger_pressure": _nonnegative(
                trigger_pressure, "merge trigger pressure"),
        }
        operation = self._operation(
            "propose-clone-merge-{}".format(
                structural_hash(material)[:20]),
            str(atom_id), "expand", "propose_clone_merge",
            (PacketCost(ResourceKind.EXPANSION, 1),),
            material)
        return StructuralOperationDecision(
            True, None, operation)

    @classmethod
    def commit_clone_merge(
            cls, proposal, exact_validation,
            current_generation):
        if (not isinstance(proposal, StructuralOperationDecision)
                or not proposal.accepted
                or proposal.operation.payload.get(
                    "structural_kind")
                != "propose_clone_merge"):
            return StructuralOperationDecision(
                False, "accepted_merge_proposal_required", None)
        payload = proposal.operation.payload
        if int(current_generation) != int(payload["generation"]):
            return StructuralOperationDecision(
                False, "stale_clone_generation", None)
        if exact_validation is not True:
            return StructuralOperationDecision(
                False, "exact_validation_required", None)
        operation = cls._operation(
            "commit-{}".format(proposal.operation.operation_id),
            proposal.operation.atom_id, "expand",
            "commit_clone_merge",
            (
                PacketCost(ResourceKind.DURABLE_MUTATION, 1),
                PacketCost(ResourceKind.EXACT_RULE, 1),
            ),
            {
                "expected_generation": int(
                    payload["generation"]),
                "left_clone_id": payload["left_clone_id"],
                "right_clone_id": payload["right_clone_id"],
                "source_operation_id": (
                    proposal.operation.operation_id),
                "validator_approved": True,
            },
            externally_consequential=True)
        return StructuralOperationDecision(
            True, None, operation)

    @classmethod
    def clone_action_recommendation(
            cls, clone, action_atom_id, goal_id,
            generation, expected_relief):
        if not isinstance(clone, CloneState):
            raise TypeError(
                "clone action requires CloneState")
        advantage = TypedAdvantage(
            str(goal_id), str(action_atom_id), "act",
            _nonnegative(
                expected_relief, "clone action relief"),
            0.0, 0.0, 0.0, 1.0,
            (("action", 1.0),),
            "clone-specific-action/1.0")
        return cls._operation(
            "clone-action:{}:{}".format(
                clone.clone_id, action_atom_id),
            str(action_atom_id), "act",
            "clone_action_recommendation",
            (PacketCost(ResourceKind.ACTION, 1),),
            {
                "atom_id": clone.atom_id,
                "clone_id": clone.clone_id,
                "generation": int(generation),
            },
            typed_advantages=(advantage,),
            causal_kind="procedural")

    @classmethod
    def mining_operation(cls, frontier_id):
        return cls._operation(
            "mine-patterns:{}".format(frontier_id),
            str(frontier_id), "infer", "mine_patterns",
            (PacketCost(ResourceKind.CPU, 1),),
            {"frontier_id": str(frontier_id)})

    @classmethod
    def induced_proposal_operation(cls, proposal, atom_id):
        if not isinstance(proposal, InducedRuleProposal):
            raise TypeError(
                "induced proposal operation requires proposal")
        return cls._operation(
            "propose:{}".format(proposal.proposal_id),
            str(atom_id), "expand", "propose_induced_rule",
            (PacketCost(ResourceKind.EXPANSION, 1),),
            {"proposal": proposal.to_dict()},
            success_probability=(
                (1.0 - proposal.overfit_risk)
                * (1.0 - proposal.transfer_uncertainty)),
            information_gain=proposal.expected_gain)

    @classmethod
    def heldout_validation_operation(cls, proposal, atom_id):
        if not isinstance(proposal, InducedRuleProposal):
            raise TypeError(
                "heldout validation requires proposal")
        return cls._operation(
            "heldout-replay:{}".format(proposal.proposal_id),
            str(atom_id), "infer", "validate_induced_rule",
            (
                PacketCost(ResourceKind.CPU, 1),
                PacketCost(ResourceKind.SIMULATION, 1),
            ),
            {
                "disjoint_heldout_required": True,
                "proposal_id": proposal.proposal_id,
            })

    @classmethod
    def promote_induced_rule(
            cls, proposal, validation,
            heldout_packets_committed, atom_id):
        if not isinstance(proposal, InducedRuleProposal):
            raise TypeError(
                "promotion requires induced proposal")
        if not heldout_packets_committed:
            return StructuralOperationDecision(
                False, "heldout_validation_packets_required", None)
        if (not isinstance(validation, ReplayValidation)
                or validation.proposal_id != proposal.proposal_id
                or validation.verdict != "promoted"):
            return StructuralOperationDecision(
                False, "promoted_replay_validation_required", None)
        operation = cls._operation(
            "promote:{}".format(proposal.proposal_id),
            str(atom_id), "expand", "promote_induced_rule",
            (
                PacketCost(ResourceKind.DURABLE_MUTATION, 1),
                PacketCost(ResourceKind.EXACT_RULE, 1),
            ),
            {
                "proposal_id": proposal.proposal_id,
                "validation_id": validation.validation_id,
                "validator_approved": True,
            },
            externally_consequential=True)
        return StructuralOperationDecision(
            True, None, operation)

    @classmethod
    def demote_induced_rule(
            cls, proposal, validation, atom_id):
        if not isinstance(proposal, InducedRuleProposal):
            raise TypeError(
                "demotion requires induced proposal")
        if (not isinstance(validation, ReplayValidation)
                or validation.proposal_id != proposal.proposal_id
                or validation.verdict != "demoted"):
            return StructuralOperationDecision(
                False, "demoted_replay_validation_required", None)
        operation = cls._operation(
            "demote:{}".format(proposal.proposal_id),
            str(atom_id), "expand", "demote_induced_rule",
            (PacketCost(ResourceKind.EXACT_RULE, 1),),
            {
                "proposal_id": proposal.proposal_id,
                "reason": validation.reason,
                "validation_id": validation.validation_id,
                "validator_approved": True,
            })
        return StructuralOperationDecision(
            True, None, operation)

    @classmethod
    def analogy_operation(
            cls, proposal, atom_id, goal_id):
        if (not isinstance(proposal, InducedRuleProposal)
                or proposal.source != "analogy"):
            raise TypeError(
                "analogy operation requires analogy proposal")
        advantage = TypedAdvantage(
            goal_id=str(goal_id),
            target_id=str(atom_id),
            mode="expand",
            expected_relief=proposal.expected_gain,
            relief_variance=proposal.transfer_uncertainty,
            information_gain=proposal.expected_gain,
            option_value=proposal.expected_generalization,
            predicted_latency=1.0,
            predicted_resource_use=(
                ("expansion", 1.0),),
            estimator_id="structural-analogy/1.0")
        return cls._operation(
            "analogy:{}".format(proposal.proposal_id),
            str(atom_id), "expand",
            "propose_analogy_transfer",
            (PacketCost(ResourceKind.EXPANSION, 1),),
            {"proposal": proposal.to_dict()},
            success_probability=(
                1.0 - proposal.transfer_uncertainty),
            typed_advantages=(advantage,))
