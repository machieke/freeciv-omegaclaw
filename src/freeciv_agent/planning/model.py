"""Immutable versioned plan, branch, assumption, and resource artifacts."""

from dataclasses import dataclass, field

from ..events.schema import structural_hash


@dataclass(frozen=True)
class PlanningSnapshot:
    snapshot_id: str
    turn: int
    beakers_per_turn: int
    gold: int
    current_research: object = None
    current_progress: int = 0
    tech_costs: tuple = ()
    build_costs: tuple = ()
    city_shields_per_turn: tuple = ()
    city_shield_stockpiles: tuple = ()
    legal_actions_digest: object = None

    def _lookup(self, rows, key):
        return dict(rows).get(key)

    def tech_cost(self, tech):
        return self._lookup(self.tech_costs, str(tech))

    def build_cost(self, target):
        return self._lookup(self.build_costs, str(target))

    def city_rate(self, city):
        return self._lookup(self.city_shields_per_turn, str(city))

    def city_stockpile(self, city):
        return self._lookup(self.city_shield_stockpiles, str(city))

    def to_dict(self):
        return {
            "beakers_per_turn": self.beakers_per_turn,
            "build_costs": [list(row) for row in self.build_costs],
            "city_shield_stockpiles": [list(row) for row in self.city_shield_stockpiles],
            "city_shields_per_turn": [list(row) for row in self.city_shields_per_turn],
            "current_progress": self.current_progress,
            "current_research": self.current_research, "gold": self.gold,
            "legal_actions_digest": self.legal_actions_digest,
            "snapshot_id": self.snapshot_id, "tech_costs": [list(row) for row in self.tech_costs],
            "turn": self.turn,
        }


@dataclass(frozen=True)
class ResourceLedgerEntry:
    resource: str
    available: float
    allocated: float
    remaining: float
    step_id: str

    def to_dict(self):
        return {
            "allocated": self.allocated, "available": self.available,
            "remaining": self.remaining, "resource": self.resource,
            "step_id": self.step_id,
        }


@dataclass(frozen=True)
class ResourceLedger:
    entries: tuple = ()

    def validate(self):
        remaining = {}
        for entry in self.entries:
            if entry.allocated < 0:
                raise ValueError("negative allocation")
            previous = remaining.get(entry.resource, entry.available)
            if abs(previous - entry.available) > 1e-9:
                raise ValueError("resource available value does not chain")
            expected = previous - entry.allocated
            if expected < -1e-9 or abs(expected - entry.remaining) > 1e-9:
                raise ValueError("resource double-spend or inconsistent remaining value")
            remaining[entry.resource] = entry.remaining
        return True

    def to_list(self):
        self.validate()
        return [entry.to_dict() for entry in self.entries]


@dataclass(frozen=True)
class PlanAssumption:
    atom_id: str
    threshold: float
    accepted_tv: dict
    affected_step_ids: tuple
    proof_node_id: object = None
    subtree_hash: object = None
    provenance_ids: tuple = ()

    def to_dict(self):
        return {
            "accepted_tv": dict(self.accepted_tv), "affected_step_ids": list(self.affected_step_ids),
            "atom_id": self.atom_id, "proof_node_id": self.proof_node_id,
            "provenance_ids": list(self.provenance_ids), "subtree_hash": self.subtree_hash,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class BranchScore:
    branch_id: str
    feasibility_grade: float
    scheduler_cost: float
    predicted_turns: int
    feasible: bool
    reason: object = None

    def to_dict(self):
        return {
            "branch_id": self.branch_id, "feasibility_grade": self.feasibility_grade,
            "feasible": self.feasible, "predicted_turns": self.predicted_turns,
            "reason": self.reason, "scheduler_cost": self.scheduler_cost,
        }


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    kind: str
    target: dict
    predicted_turn: int
    duration_turns: int
    cost: float
    status: str = "PENDING"
    actual_turn: object = None
    spatial: object = None
    snapshot_id: object = None
    legal_actions_digest: object = None

    def to_dict(self):
        return {
            "actual_turn": self.actual_turn, "cost": self.cost,
            "duration_turns": self.duration_turns, "kind": self.kind,
            "legal_actions_digest": self.legal_actions_digest,
            "predicted_turn": self.predicted_turn, "snapshot_id": self.snapshot_id,
            "spatial": self.spatial, "status": self.status,
            "step_id": self.step_id, "target": dict(self.target),
        }


@dataclass(frozen=True)
class Plan:
    plan_id: str
    goal_atom_id: str
    source_proof_hash: str
    snapshot_id: str
    steps: tuple
    ledger: ResourceLedger
    branch_scores: tuple
    selected_branch_id: str
    cost_profile: str
    scheduler_cost: float
    feasibility_grade: float
    predicted_turns: int
    solver_identity: str
    assumptions: tuple = ()
    status: str = "ACTIVE"
    reused_subtree_hashes: tuple = ()
    rederived_subtree_hashes: tuple = ()
    schema_version: str = "1.0"

    def to_dict(self):
        value = {
            "assumptions": [item.to_dict() for item in self.assumptions],
            "branch_scores": [item.to_dict() for item in self.branch_scores],
            "cost_profile": self.cost_profile, "feasibility_grade": self.feasibility_grade,
            "goal_atom_id": self.goal_atom_id, "ledger": self.ledger.to_list(),
            "plan_id": self.plan_id, "predicted_turns": self.predicted_turns,
            "rederived_subtree_hashes": list(self.rederived_subtree_hashes),
            "reused_subtree_hashes": list(self.reused_subtree_hashes),
            "scheduler_cost": self.scheduler_cost, "schema_version": self.schema_version,
            "selected_branch_id": self.selected_branch_id,
            "snapshot_id": self.snapshot_id, "solver_identity": self.solver_identity,
            "source_proof_hash": self.source_proof_hash, "status": self.status,
            "steps": [step.to_dict() for step in self.steps],
        }
        return value

    @property
    def artifact_hash(self):
        return structural_hash(self.to_dict())


@dataclass(frozen=True)
class NonPlan:
    status: str
    reason: str
    snapshot_id: str
    source_proof_hash: str
    solver_identity: str
    diagnostic: object = None

    @property
    def executable(self):
        return False

    def to_dict(self):
        return {
            "diagnostic": self.diagnostic, "reason": self.reason,
            "snapshot_id": self.snapshot_id, "solver_identity": self.solver_identity,
            "source_proof_hash": self.source_proof_hash, "status": self.status,
        }
