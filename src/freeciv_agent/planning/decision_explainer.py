"""Type-separated belief, attention, and action explanations.

The products in this module deliberately have different schemas.  In
particular, a belief explanation is fail-closed against controller telemetry so
that a probe, flow, packet, or score can never be presented as evidence.
"""

from dataclasses import dataclass

from ..events.schema import structural_hash
from .commit_validator import ValidationResult
from .impact_flow_adapter import ControlDecision, ControlQuery


_CONTROL_ONLY_TERMS = frozenset((
    "attention",
    "bridge",
    "congestion",
    "controller",
    "current",
    "flow",
    "packet",
    "probe",
    "requested_current",
    "resource_return",
    "scheduler",
    "score",
    "typed_advantage",
))
_NON_EPISTEMIC_EDGE_KINDS = frozenset((
    "attention_transport",
    "probe_forward",
    "probe_backward",
    "resource_return",
    "shard_portal",
))


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _contains_control_only_material(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(term in lowered for term in _CONTROL_ONLY_TERMS):
                return path + (str(key),)
            if (lowered in ("edge_kind", "transition_kind")
                    and str(child).lower()
                    in _NON_EPISTEMIC_EDGE_KINDS):
                return path + (str(key),)
            found = _contains_control_only_material(
                child, path + (str(key),))
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _contains_control_only_material(
                child, path + (str(index),))
            if found:
                return found
    return ()


@dataclass(frozen=True)
class BeliefExplanation:
    semantic_id: str
    evidence_tokens: tuple
    truth_formula: object
    committed_proof_path: tuple
    assumptions: tuple
    contexts: tuple
    confidence: object
    uncertainty: object
    overlap_handling: object
    conflict_handling: object
    epistemic_authority: bool = True
    schema_version: str = "belief-explanation/1.0"

    def __post_init__(self):
        _required_text(self.semantic_id, "belief semantic ID")
        if not self.epistemic_authority:
            raise ValueError(
                "belief explanation must describe epistemic material")
        material = self.to_dict()
        material.pop("explanation_type", None)
        material.pop("schema_version", None)
        material.pop("epistemic_authority", None)
        leaked_path = _contains_control_only_material(material)
        if leaked_path:
            raise ValueError(
                "belief explanation contains control-only material at "
                "{}".format(".".join(leaked_path)))

    @property
    def explanation_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "assumptions": list(self.assumptions),
            "committed_proof_path": list(
                self.committed_proof_path),
            "confidence": self.confidence,
            "conflict_handling": self.conflict_handling,
            "contexts": list(self.contexts),
            "epistemic_authority": self.epistemic_authority,
            "evidence_tokens": list(self.evidence_tokens),
            "explanation_type": "belief",
            "overlap_handling": self.overlap_handling,
            "schema_version": self.schema_version,
            "semantic_id": self.semantic_id,
            "truth_formula": self.truth_formula,
            "uncertainty": self.uncertainty,
        }


@dataclass(frozen=True)
class AttentionExplanation:
    decision_id: str
    active_goals: tuple
    cost_to_go: object
    immediate_loss: object
    teleological_demand_path: tuple
    bridge_factors: object
    bridge_health: object
    probe_support: object
    path_diversity: object
    attention_summary: object
    congestion_summary: object
    expected_information_or_relief: object
    evidential_authority: bool = False
    schema_version: str = "attention-explanation/1.0"

    def __post_init__(self):
        _required_text(self.decision_id, "attention decision ID")
        if self.evidential_authority:
            raise ValueError(
                "attention telemetry cannot be epistemic evidence")

    @property
    def explanation_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "active_goals": list(self.active_goals),
            "attention_summary": self.attention_summary,
            "bridge_factors": self.bridge_factors,
            "bridge_health": self.bridge_health,
            "congestion_summary": self.congestion_summary,
            "cost_to_go": self.cost_to_go,
            "decision_id": self.decision_id,
            "evidential_authority": self.evidential_authority,
            "expected_information_or_relief":
                self.expected_information_or_relief,
            "explanation_type": "attention",
            "immediate_loss": self.immediate_loss,
            "path_diversity": self.path_diversity,
            "probe_support": self.probe_support,
            "schema_version": self.schema_version,
            "teleological_demand_path": list(
                self.teleological_demand_path),
        }


@dataclass(frozen=True)
class ActionExplanation:
    decision_id: str
    candidate_key: object
    authoritative_grounding: object
    per_goal_expected_effects: object
    risk: object
    deadline: object
    costs: object
    packet_use: object
    resource_conflicts: object
    rejected_alternatives: tuple
    safety_gates: object
    provenance_gates: object
    commit_revalidation: object
    fallback_chain: tuple
    execution_authority: bool = False
    schema_version: str = "action-explanation/1.0"

    def __post_init__(self):
        _required_text(self.decision_id, "action decision ID")
        if self.execution_authority:
            raise ValueError(
                "an explanation cannot authorize execution")

    @property
    def explanation_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "authoritative_grounding":
                self.authoritative_grounding,
            "candidate_key": self.candidate_key,
            "commit_revalidation": self.commit_revalidation,
            "costs": self.costs,
            "deadline": self.deadline,
            "decision_id": self.decision_id,
            "execution_authority": self.execution_authority,
            "explanation_type": "action",
            "fallback_chain": list(self.fallback_chain),
            "packet_use": self.packet_use,
            "per_goal_expected_effects":
                self.per_goal_expected_effects,
            "provenance_gates": self.provenance_gates,
            "rejected_alternatives": list(
                self.rejected_alternatives),
            "resource_conflicts": self.resource_conflicts,
            "risk": self.risk,
            "safety_gates": self.safety_gates,
            "schema_version": self.schema_version,
        }


class DecisionExplainer:
    """Separate indexed ledgers for epistemic, attentional, and action facts."""

    EXPLAINER_IDENTITY = "impact-decision-explainer/1.0"

    def __init__(self):
        self._belief = {}
        self._attention = {}
        self._action = {}

    @staticmethod
    def decision_id(query, decision):
        if not isinstance(query, ControlQuery):
            raise TypeError(
                "explanation query has wrong type")
        if not isinstance(decision, ControlDecision):
            raise TypeError(
                "explanation decision has wrong type")
        return "control-decision:{}".format(
            structural_hash({
                "decision_hash": decision.decision_hash,
                "query_id": query.query_id,
            }))

    def register_belief(self, explanation):
        if not isinstance(explanation, BeliefExplanation):
            raise TypeError(
                "belief ledger requires BeliefExplanation")
        existing = self._belief.get(
            explanation.semantic_id)
        if (existing is not None
                and existing.explanation_hash
                != explanation.explanation_hash):
            raise ValueError(
                "belief explanation ID is immutable")
        self._belief[explanation.semantic_id] = explanation
        return explanation

    def register_decision(
            self, query, decision, *,
            attention_fields=None, action_fields=None,
            validation=None):
        if not isinstance(query, ControlQuery):
            raise TypeError(
                "explanation query has wrong type")
        if not isinstance(decision, ControlDecision):
            raise TypeError(
                "explanation decision has wrong type")
        if (validation is not None
                and not isinstance(
                    validation, ValidationResult)):
            raise TypeError(
                "explanation validation has wrong type")
        attention_fields = dict(attention_fields or {})
        action_fields = dict(action_fields or {})
        decision_id = self.decision_id(query, decision)
        candidate = next((
            row for row in query.grounded_candidates
            if row.action_key
            == decision.selected_candidate_key
        ), None)
        artifact = decision.artifact
        attention = AttentionExplanation(
            decision_id=decision_id,
            active_goals=query.active_goals,
            cost_to_go=attention_fields.get(
                "cost_to_go"),
            immediate_loss=attention_fields.get(
                "immediate_loss"),
            teleological_demand_path=tuple(
                attention_fields.get(
                    "teleological_demand_path", ())),
            bridge_factors=attention_fields.get(
                "bridge_factors",
                artifact.get("bridge")),
            bridge_health=attention_fields.get(
                "bridge_health", decision.health),
            probe_support=attention_fields.get(
                "probe_support"),
            path_diversity=attention_fields.get(
                "path_diversity"),
            attention_summary=attention_fields.get(
                "attention_summary"),
            congestion_summary=attention_fields.get(
                "congestion_summary"),
            expected_information_or_relief=(
                attention_fields.get(
                    "expected_information_or_relief")))
        action = ActionExplanation(
            decision_id=decision_id,
            candidate_key=decision.selected_candidate_key,
            authoritative_grounding=(
                candidate.to_dict()
                if candidate is not None else None),
            per_goal_expected_effects=action_fields.get(
                "per_goal_expected_effects"),
            risk=action_fields.get("risk"),
            deadline=action_fields.get("deadline"),
            costs=action_fields.get("costs"),
            packet_use=(
                decision.packet_schedule.to_dict()
                if decision.packet_schedule is not None
                else None),
            resource_conflicts=action_fields.get(
                "resource_conflicts"),
            rejected_alternatives=tuple(
                action_fields.get(
                    "rejected_alternatives",
                    decision.ordered_candidate_keys[1:])),
            safety_gates=action_fields.get(
                "safety_gates"),
            provenance_gates=action_fields.get(
                "provenance_gates"),
            commit_revalidation=(
                validation.to_dict()
                if validation is not None else None),
            fallback_chain=decision.fallback_chain)
        for ledger, value in (
                (self._attention, attention),
                (self._action, action)):
            existing = ledger.get(decision_id)
            if (existing is not None
                    and existing.explanation_hash
                    != value.explanation_hash):
                raise ValueError(
                    "decision explanation ID is immutable")
            ledger[decision_id] = value
        return decision_id

    def belief_explanation(self, semantic_id):
        _required_text(semantic_id, "belief semantic ID")
        return self._belief.get(semantic_id)

    def attention_explanation(self, decision_id):
        _required_text(decision_id, "attention decision ID")
        return self._attention.get(decision_id)

    def action_explanation(self, decision_id):
        _required_text(decision_id, "action decision ID")
        return self._action.get(decision_id)
