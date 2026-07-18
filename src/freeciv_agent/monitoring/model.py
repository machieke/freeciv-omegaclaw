"""Immutable M5 invalidation and local-repair artifacts."""

from dataclasses import dataclass

from ..events.schema import structural_hash


@dataclass(frozen=True)
class AtomRevision:
    atom_id: str
    prior_tv: dict
    posterior_tv: dict
    revision_event_id: str
    turn: int


@dataclass(frozen=True)
class Invalidation:
    invalidation_id: str
    plan_id: str
    turn: int
    broken_assumptions: tuple
    revisions: tuple
    affected_step_ids: tuple
    affected_subtree_hashes: tuple
    reason: str = "assumption_below_threshold"

    @property
    def broken_assumption(self):
        return self.broken_assumptions[0]

    def to_dict(self, reused=(), rederived=()):
        broken = [item.to_dict() for item in self.broken_assumptions]
        return {
            "affected_step_ids": list(self.affected_step_ids),
            "broken_assumption": broken[0], "broken_assumptions": broken,
            "plan_id": self.plan_id,
            "posterior_tv": dict(self.revisions[0].posterior_tv),
            "prior_tv": dict(self.revisions[0].prior_tv),
            "reason": self.reason,
            "rederived_subtree_hashes": list(rederived),
            "reused_subtree_hashes": list(reused),
            "revision_event_ids": [item.revision_event_id for item in self.revisions],
        }

    @classmethod
    def create(cls, plan_id, turn, broken, revisions):
        affected_steps = tuple(sorted(set(
            step for assumption in broken for step in assumption.affected_step_ids)))
        subtrees = tuple(sorted(set(
            assumption.subtree_hash for assumption in broken if assumption.subtree_hash)))
        material = {
            "broken": [item.atom_id for item in broken], "plan_id": plan_id,
            "revisions": [item.revision_event_id for item in revisions], "turn": turn,
        }
        return cls(
            "invalidation-" + structural_hash(material)[:20], str(plan_id), int(turn),
            tuple(sorted(broken, key=lambda item: item.atom_id)),
            tuple(sorted(revisions, key=lambda item: item.revision_event_id)),
            affected_steps, subtrees)


@dataclass(frozen=True)
class RepairResult:
    status: str
    invalidation_id: str
    replacement_plan: object
    reused_subtree_hashes: tuple
    rederived_subtree_hashes: tuple
    latency_ms: float
    reason: object = None

    @property
    def executable(self):
        return self.status == "REPAIRED" and self.replacement_plan is not None
