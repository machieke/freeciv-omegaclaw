"""Immutable evidence, uncertain belief, support, and revision artifacts."""

from dataclasses import dataclass, field

from ..events.schema import structural_hash


@dataclass(frozen=True)
class ModelProvenance:
    """Identity and confidence boundary for a non-authoritative model."""

    source_kind: str
    model_id: str
    model_version: str
    model_hash: str
    exact: bool
    confidence_cap: float
    validity_scope: tuple = ()

    def __post_init__(self):
        if self.source_kind != "simulator":
            raise ValueError("model provenance source_kind must be simulator")
        if not self.model_id or not self.model_version:
            raise ValueError("model provenance requires model identity and version")
        if (len(self.model_hash) != 64
                or any(value not in "0123456789abcdef" for value in self.model_hash)):
            raise ValueError("model provenance hash must be lowercase SHA-256")
        _bounded(self.confidence_cap, "confidence_cap")
        if not self.exact and self.confidence_cap >= 1.0:
            raise ValueError("an inexact simulator requires a finite confidence cap")
        if any(not isinstance(value, str) or not value
               for value in self.validity_scope):
            raise ValueError(
                "model validity scope must contain non-empty strings")

    def to_dict(self):
        value = {
            "confidence_cap": float(self.confidence_cap),
            "exact": bool(self.exact),
            "model_hash": self.model_hash,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "source_kind": self.source_kind,
        }
        if self.validity_scope:
            value["validity_scope"] = list(self.validity_scope)
        return value


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
    model_provenance: object = None

    def __post_init__(self):
        _bounded(self.strength, "strength")
        _bounded(self.confidence, "confidence")
        if not self.provenance_id or self.turn < 0:
            raise ValueError("evidence requires provenance and nonnegative turn")
        if (self.model_provenance is not None
                and not isinstance(self.model_provenance, ModelProvenance)):
            raise TypeError("model_provenance must be ModelProvenance")
        if ((self.source_sensor == "simulator")
                != (self.model_provenance is not None)):
            raise ValueError(
                "simulator evidence and model provenance must appear together")
        if (self.model_provenance is not None
                and not self.model_provenance.exact
                and self.confidence > self.model_provenance.confidence_cap):
            raise ValueError(
                "simulator evidence exceeds its declared confidence cap")

    @property
    def context_id(self):
        """Stable context identity used to contain mutually incompatible evidence."""
        return "context-" + structural_hash({
            "game_id": self.game_id,
            "location": self.location,
            "model_version": self.model_version,
            "opponent_id": self.opponent_id,
            "ruleset": self.ruleset,
        })[:20]

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
            "model_provenance": (
                None if self.model_provenance is None
                else self.model_provenance.to_dict()),
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


@dataclass(frozen=True)
class ConflictAtom:
    """A materialized disagreement between independent evidence lineages."""

    conflict_id: str
    key: BeliefKey
    left_provenance_ids: tuple
    right_provenance_ids: tuple
    left_tv: dict
    right_tv: dict
    overlap: float
    severity: float
    context_ids: tuple
    detected_turn: int

    def __post_init__(self):
        left = set(self.left_provenance_ids)
        right = set(self.right_provenance_ids)
        if not self.conflict_id or not left or not right:
            raise ValueError("conflict requires an ID and two nonempty lineages")
        if left & right:
            raise ValueError("conflict lineages must be provenance-distinct")
        _bounded(self.overlap, "overlap")
        _bounded(self.severity, "severity")
        if int(self.detected_turn) < 0:
            raise ValueError("conflict turn must be nonnegative")

    @property
    def provenance_ids(self):
        return tuple(sorted(set(self.left_provenance_ids) | set(self.right_provenance_ids)))

    def atom(self):
        confidence = min(
            float(self.left_tv["confidence"]), float(self.right_tv["confidence"]))
        return {
            "args": [
                self.key.atom_id,
                list(self.left_provenance_ids),
                list(self.right_provenance_ids),
            ],
            "atom_id": self.conflict_id,
            "crisp": False,
            "predicate": "Conflict",
            "provenance_ids": list(self.provenance_ids),
            "tv": {"confidence": confidence, "strength": float(self.severity)},
        }

    def to_dict(self):
        return {
            "conflict_atom": self.atom(),
            "conflict_id": self.conflict_id,
            "context_ids": list(self.context_ids),
            "detected_turn": int(self.detected_turn),
            "left_provenance_ids": list(self.left_provenance_ids),
            "left_tv": dict(self.left_tv),
            "overlap": float(self.overlap),
            "right_provenance_ids": list(self.right_provenance_ids),
            "right_tv": dict(self.right_tv),
            "severity": float(self.severity),
            "target_atom_id": self.key.atom_id,
        }


@dataclass(frozen=True)
class ContextQuarantineOperation:
    """Exclude one conflicting lineage only while reasoning in one context."""

    operation_id: str
    conflict_id: str
    target_atom_id: str
    context_id: str
    excluded_provenance_ids: tuple
    retained_provenance_ids: tuple
    reason: str
    turn: int

    def __post_init__(self):
        excluded = set(self.excluded_provenance_ids)
        retained = set(self.retained_provenance_ids)
        if not all((
                self.operation_id, self.conflict_id, self.target_atom_id,
                self.context_id, self.reason)):
            raise ValueError("context quarantine fields must be nonempty")
        if not excluded or not retained or excluded & retained:
            raise ValueError(
                "context quarantine requires disjoint excluded and retained lineages")
        if int(self.turn) < 0:
            raise ValueError("context quarantine turn must be nonnegative")

    def to_dict(self):
        return {
            "conflict_id": self.conflict_id,
            "context_id": self.context_id,
            "excluded_provenance_ids": list(self.excluded_provenance_ids),
            "operation_id": self.operation_id,
            "reason": self.reason,
            "retained_provenance_ids": list(self.retained_provenance_ids),
            "target_atom_id": self.target_atom_id,
            "turn": int(self.turn),
        }
