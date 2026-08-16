"""Strict, hash-addressed contracts shared by scaling campaign runners."""

import math
from dataclasses import dataclass, field

from freeciv_agent.events.schema import structural_hash


SURFACES = frozenset((
    "atomspace", "proof", "bridge", "fluid", "combined", "captured"))
PHASES = frozenset(("discovery", "heldout", "audit"))
STATUSES = frozenset(("completed", "failed", "stopped"))


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _pairs(value, name):
    rows = tuple((str(key), item) for key, item in value)
    if any(not key for key, _ in rows):
        raise ValueError("{} keys must be nonempty".format(name))
    if len(rows) != len(dict(rows)):
        raise ValueError("{} keys must be unique".format(name))
    return tuple(sorted(rows, key=lambda row: row[0]))


def _json_value(value, path="value"):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("{} must be finite".format(path))
        return value
    if isinstance(value, (tuple, list)):
        return [_json_value(item, path) for item in value]
    if isinstance(value, dict):
        return dict(
            (str(key), _json_value(item, "{}.{}".format(path, key)))
            for key, item in sorted(value.items()))
    raise TypeError("{} is not JSON-serializable".format(path))


@dataclass(frozen=True)
class ScaleCell:
    surface: str
    tier: str
    seed: int
    parameters: tuple
    budgets: tuple

    def __post_init__(self):
        if self.surface not in SURFACES:
            raise ValueError("unknown scaling surface")
        _required_text(self.tier, "scale tier")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("scale seed must be an integer")
        object.__setattr__(
            self, "parameters", _pairs(self.parameters, "parameters"))
        object.__setattr__(self, "budgets", _pairs(self.budgets, "budgets"))
        _json_value(dict(self.parameters), "parameters")
        _json_value(dict(self.budgets), "budgets")

    def to_dict(self):
        return {
            "budgets": _json_value(dict(self.budgets)),
            "parameters": _json_value(dict(self.parameters)),
            "seed": self.seed,
            "surface": self.surface,
            "tier": self.tier,
        }

    @property
    def cell_id(self):
        return "scale-cell-" + structural_hash(self.to_dict())[:24]


@dataclass(frozen=True)
class TrialSpec:
    experiment_id: str
    phase: str
    cell: ScaleCell
    arm: str
    telemetry_mode: str
    source_identity: str

    def __post_init__(self):
        _required_text(self.experiment_id, "experiment ID")
        if self.phase not in PHASES:
            raise ValueError("unknown experiment phase")
        if not isinstance(self.cell, ScaleCell):
            raise TypeError("trial requires ScaleCell")
        for value, name in (
                (self.arm, "trial arm"),
                (self.telemetry_mode, "telemetry mode"),
                (self.source_identity, "source identity")):
            _required_text(value, name)

    def to_dict(self):
        return {
            "arm": self.arm,
            "cell": self.cell.to_dict(),
            "experiment_id": self.experiment_id,
            "phase": self.phase,
            "source_identity": self.source_identity,
            "telemetry_mode": self.telemetry_mode,
        }

    @property
    def trial_id(self):
        return "scale-trial-" + structural_hash(self.to_dict())[:24]


@dataclass(frozen=True)
class TrialResult:
    trial: TrialSpec
    status: str
    actual_work: tuple
    metrics: tuple
    correctness: tuple
    errors: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.trial, TrialSpec):
            raise TypeError("result requires TrialSpec")
        if self.status not in STATUSES:
            raise ValueError("unknown trial status")
        for name in ("actual_work", "metrics", "correctness"):
            object.__setattr__(
                self, name, _pairs(getattr(self, name), name))
            _json_value(dict(getattr(self, name)), name)
        object.__setattr__(self, "errors", tuple(str(row) for row in self.errors))
        if self.status == "completed" and self.errors:
            raise ValueError("completed results cannot contain errors")

    def to_dict(self):
        material = {
            "actual_work": _json_value(dict(self.actual_work)),
            "correctness": _json_value(dict(self.correctness)),
            "errors": list(self.errors),
            "metrics": _json_value(dict(self.metrics)),
            "schema_version": "1.0",
            "status": self.status,
            "trial": self.trial.to_dict(),
            "trial_id": self.trial.trial_id,
        }
        material["result_hash"] = structural_hash(material)
        return material
