"""Immutable evidence, uncertain belief, support, and revision artifacts."""

from dataclasses import dataclass, field

from ..events.schema import structural_hash


def _bounded(value, name):
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError("{} must be in [0,1]".format(name))
    return value


@dataclass(frozen=True, order=True)
class BeliefKey:
    predicate: str
    arguments: tuple

    @property
    def atom_id(self):
        return "belief-" + structural_hash({
            "arguments": list(self.arguments), "predicate": self.predicate,
        })[:20]


@dataclass(frozen=True)
class Evidence:
    provenance_id: str
    game_id: str
    turn: int
    location: object
    source_sensor: str
    key: BeliefKey
    strength: float
    confidence: float
    opponent_id: str
    ruleset: str
    model_version: str
    selection_policy: object = None

    def __post_init__(self):
        _bounded(self.strength, "strength")
        _bounded(self.confidence, "confidence")
        if not self.provenance_id or self.turn < 0:
            raise ValueError("evidence requires provenance and nonnegative turn")

    def to_dict(self):
        return {
            "confidence": self.confidence, "game_id": self.game_id,
            "location": self.location, "model_version": self.model_version,
            "observed_atom": {
                "args": list(self.key.arguments), "atom_id": self.key.atom_id,
                "crisp": False, "predicate": self.key.predicate,
                "provenance_ids": [self.provenance_id],
                "tv": {"confidence": self.confidence, "strength": self.strength},
            },
            "opponent_id": self.opponent_id, "provenance_id": self.provenance_id,
            "ruleset": self.ruleset, "source_sensor": self.source_sensor,
            "selection_policy": (
                self.selection_policy.to_dict()
                if hasattr(self.selection_policy, "to_dict")
                else self.selection_policy),
            "strength": self.strength, "turn": self.turn,
        }


@dataclass(frozen=True)
class Contribution:
    provenance_id: str
    strength: float
    confidence: float
    source_turn: int
    derivation_path: tuple = ()
    formula: str = "observation"
    dampening_lambda: float = 0.0


@dataclass(frozen=True)
class Revision:
    revision_id: str
    turn: int
    operation: str
    prior_tv: object
    evidence_tv: dict
    posterior_tv: dict
    provenance_ids: tuple
    formula: dict

    def to_dict(self):
        return {
            "evidence_tv": dict(self.evidence_tv), "formula": dict(self.formula),
            "operation": self.operation, "posterior_tv": dict(self.posterior_tv),
            "prior_tv": None if self.prior_tv is None else dict(self.prior_tv),
            "provenance_ids": list(self.provenance_ids),
            "revision_id": self.revision_id, "turn": self.turn,
        }


@dataclass(frozen=True)
class UncertainBelief:
    key: BeliefKey
    strength: float
    confidence: float
    provenance_ids: tuple
    support_paths: tuple
    last_revised_turn: int
    history: tuple = field(default_factory=tuple)
    crisp: bool = False

    def __post_init__(self):
        if self.crisp:
            raise ValueError("uncertain belief can never be crisp")
        _bounded(self.strength, "strength")
        _bounded(self.confidence, "confidence")

    @property
    def atom_id(self):
        return self.key.atom_id

    @property
    def tv(self):
        return {"strength": self.strength, "confidence": self.confidence}

    def atom(self):
        return {
            "args": list(self.key.arguments), "atom_id": self.atom_id,
            "crisp": False, "predicate": self.key.predicate,
            "provenance_ids": list(self.provenance_ids), "tv": self.tv,
        }

    def to_dict(self):
        return {
            "atom": self.atom(), "history": [row.to_dict() for row in self.history],
            "last_revised_turn": self.last_revised_turn,
            "support_paths": [list(row) for row in self.support_paths],
        }
