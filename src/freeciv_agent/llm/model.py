"""Typed LLM proposals, claims, verification sinks, and candidate grades."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateGoal:
    goal_id: str
    target_id: str
    predicate: str
    arguments: tuple

    def to_dict(self):
        return {"arguments": list(self.arguments), "goal_id": self.goal_id,
                "predicate": self.predicate, "target_id": self.target_id}


@dataclass(frozen=True)
class FactualClaim:
    claim_id: str
    text: str
    predicate: str
    arguments: tuple
    asserted: bool

    def to_dict(self):
        return {"arguments": list(self.arguments), "asserted": self.asserted,
                "claim_id": self.claim_id, "predicate": self.predicate,
                "text": self.text}


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    goals: tuple
    claims: tuple
    rationale: str
    selection: object = None
    schema_version: str = "1.0"

    def to_dict(self):
        return {"claims": [row.to_dict() for row in self.claims],
                "goals": [row.to_dict() for row in self.goals],
                "proposal_id": self.proposal_id, "rationale": self.rationale,
                "schema_version": self.schema_version, "selection": self.selection}


@dataclass(frozen=True)
class VerifiedClaim:
    claim: FactualClaim
    proposal_id: str
    verdict: str
    check: str
    evidence_atoms: tuple

    @property
    def usable(self):
        return self.verdict == "believe"


@dataclass(frozen=True)
class QuarantineEntry:
    quarantine_id: str
    proposal_id: str
    claim: FactualClaim
    failed_check: str
    evidence_atoms: tuple
    model: str
    model_config: tuple
    quarantined_at: str

    def to_dict(self):
        return {
            "claim": self.claim.text, "claim_id": self.claim.claim_id,
            "evidence_atoms": [dict(value) for value in self.evidence_atoms],
            "failed_check": self.failed_check, "model": self.model,
            "model_config": dict(self.model_config), "proposal_id": self.proposal_id,
            "quarantine_id": self.quarantine_id,
            "quarantined_at": self.quarantined_at,
        }


@dataclass(frozen=True)
class CandidateGrade:
    goal: CandidateGoal
    valid: bool
    feasibility_grade: object
    scheduler_cost: object
    status: str
    proof_hash: object = None
    plan_id: object = None
    reason: object = None

    def to_dict(self):
        return {
            "feasibility_grade": self.feasibility_grade, "goal": self.goal.to_dict(),
            "plan_id": self.plan_id, "proof_hash": self.proof_hash,
            "reason": self.reason, "scheduler_cost": self.scheduler_cost,
            "status": self.status, "valid": self.valid,
        }


@dataclass(frozen=True)
class TurnDecision:
    status: str
    proposal: object
    selected: object
    grades: tuple
    verifications: tuple
    elapsed_ms: float
    fallback_action: object = None
    error: object = None
