"""Strong, stateful scalar control baseline for bridge and flow ablations.

This module is deliberately separate from the live PF-v1 scheduler.  It gives
later controllers a cheap but non-trivial comparator without changing current
planner behavior.
"""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash


def _finite(name, value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("{} must be finite".format(name))
    return value


def _unit_interval(name, value):
    value = _finite(name, value)
    if value < 0.0 or value > 1.0:
        raise ValueError("{} must be between zero and one".format(name))
    return value


def _nonnegative(name, value):
    value = _finite(name, value)
    if value < 0.0:
        raise ValueError("{} must be non-negative".format(name))
    return value


@dataclass(frozen=True)
class ScalarBaselineConfig:
    """Configuration for the strong scalar comparator."""

    smoothing: float = 0.35
    route_momentum: float = 0.15
    minimum_dwell_steps: int = 2
    dwell_bonus: float = 0.05
    switch_margin: float = 0.01
    diversity_floor: float = 0.10

    def __post_init__(self):
        object.__setattr__(
            self, "smoothing", _unit_interval("smoothing", self.smoothing))
        object.__setattr__(
            self, "route_momentum",
            _nonnegative("route_momentum", self.route_momentum))
        object.__setattr__(
            self, "dwell_bonus",
            _nonnegative("dwell_bonus", self.dwell_bonus))
        object.__setattr__(
            self, "switch_margin",
            _nonnegative("switch_margin", self.switch_margin))
        object.__setattr__(
            self, "diversity_floor",
            _unit_interval("diversity_floor", self.diversity_floor))
        if (isinstance(self.minimum_dwell_steps, bool)
                or not isinstance(self.minimum_dwell_steps, int)):
            raise ValueError("minimum_dwell_steps must be a non-negative integer")
        steps = int(self.minimum_dwell_steps)
        if steps < 0:
            raise ValueError("minimum_dwell_steps must be a non-negative integer")
        object.__setattr__(self, "minimum_dwell_steps", steps)

    def to_dict(self):
        return {
            "diversity_floor": float(self.diversity_floor),
            "dwell_bonus": float(self.dwell_bonus),
            "minimum_dwell_steps": int(self.minimum_dwell_steps),
            "route_momentum": float(self.route_momentum),
            "smoothing": float(self.smoothing),
            "switch_margin": float(self.switch_margin),
        }


@dataclass(frozen=True)
class ScalarRouteBid:
    """One route's common scalar features and admissibility."""

    route_id: str
    instantaneous_score: float
    pf_advantage: float = 0.0
    bridge_estimate: float = 0.0
    admissible: bool = True

    def __post_init__(self):
        if not isinstance(self.route_id, str) or not self.route_id:
            raise ValueError("route_id must be a non-empty string")
        for name in (
                "instantaneous_score", "pf_advantage", "bridge_estimate"):
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        object.__setattr__(self, "admissible", bool(self.admissible))

    @property
    def combined_score(self):
        return (
            self.instantaneous_score + self.pf_advantage
            + self.bridge_estimate)

    def to_dict(self):
        return {
            "admissible": bool(self.admissible),
            "bridge_estimate": float(self.bridge_estimate),
            "instantaneous_score": float(self.instantaneous_score),
            "pf_advantage": float(self.pf_advantage),
            "route_id": self.route_id,
        }


@dataclass(frozen=True)
class SmoothedRouteScore:
    route_id: str
    instantaneous_score: float
    smoothed_score: float
    momentum: float
    dwell_bonus: float
    total_score: float
    admissible: bool

    def to_dict(self):
        return {
            "admissible": bool(self.admissible),
            "dwell_bonus": float(self.dwell_bonus),
            "instantaneous_score": float(self.instantaneous_score),
            "momentum": float(self.momentum),
            "route_id": self.route_id,
            "smoothed_score": float(self.smoothed_score),
            "total_score": float(self.total_score),
        }


@dataclass(frozen=True)
class SmoothedScalarDecision:
    step: int
    selected_route_id: object
    backup_route_id: object
    allocations: tuple
    scores: tuple
    retained_by_dwell: bool
    retained_by_hysteresis: bool
    controller_identity: str
    config: dict

    def to_dict(self):
        value = {
            "allocations": [
                {"fraction": float(fraction), "route_id": route_id}
                for route_id, fraction in self.allocations
            ],
            "backup_route_id": self.backup_route_id,
            "config": dict(self.config),
            "controller_identity": self.controller_identity,
            "retained_by_dwell": bool(self.retained_by_dwell),
            "retained_by_hysteresis": bool(self.retained_by_hysteresis),
            "scores": [score.to_dict() for score in self.scores],
            "selected_route_id": self.selected_route_id,
            "step": int(self.step),
        }
        value["artifact_hash"] = structural_hash(value)
        return value

    @property
    def artifact_hash(self):
        return self.to_dict()["artifact_hash"]


class SmoothedScalarController:
    """Strong cheap baseline for bridge and flow ablations."""

    SOLVER_IDENTITY = "pf-pln-smoothed-scalar/1.0"

    def __init__(self, config=None):
        self.config = config or ScalarBaselineConfig()
        if not isinstance(self.config, ScalarBaselineConfig):
            raise TypeError("config must be ScalarBaselineConfig")
        self.reset()

    def reset(self):
        self._smoothed = {}
        self._selected_route_id = None
        self._selected_since = None
        self._last_step = None

    def update_route_score(
            self, route_id, instantaneous_score, route_momentum=None,
            dwell_bonus=0.0, diversity_floor=None):
        """Update and return one route score.

        ``diversity_floor`` is accepted here to keep the stable baseline API
        shared with allocation-aware controllers; it is validated and applied
        by :meth:`rank`, not folded into route utility.
        """
        if not isinstance(route_id, str) or not route_id:
            raise ValueError("route_id must be a non-empty string")
        instantaneous_score = _finite(
            "instantaneous_score", instantaneous_score)
        momentum_weight = (
            self.config.route_momentum
            if route_momentum is None
            else _nonnegative("route_momentum", route_momentum))
        dwell_bonus = _nonnegative("dwell_bonus", dwell_bonus)
        if diversity_floor is not None:
            _unit_interval("diversity_floor", diversity_floor)
        previous = self._smoothed.get(route_id, instantaneous_score)
        smoothed = (
            self.config.smoothing * instantaneous_score
            + (1.0 - self.config.smoothing) * previous)
        momentum = momentum_weight * (smoothed - previous)
        total = smoothed + momentum + dwell_bonus
        self._smoothed[route_id] = smoothed
        return SmoothedRouteScore(
            route_id, instantaneous_score, smoothed, momentum,
            dwell_bonus, total, True)

    def rank(self, bids, step):
        """Rank admissible bids and reserve diversity for one backup route."""
        bids = tuple(bids)
        for bid in bids:
            if not isinstance(bid, ScalarRouteBid):
                raise TypeError("bids must contain ScalarRouteBid")
        route_ids = tuple(bid.route_id for bid in bids)
        if len(set(route_ids)) != len(route_ids):
            raise ValueError("route IDs must be unique")
        step = int(step)
        if step < 0:
            raise ValueError("step must be non-negative")
        if self._last_step is not None and step < self._last_step:
            raise ValueError("step must not regress")

        scores = []
        for bid in sorted(bids, key=lambda row: row.route_id):
            dwell = (
                self.config.dwell_bonus
                if bid.route_id == self._selected_route_id else 0.0)
            score = self.update_route_score(
                bid.route_id, bid.combined_score,
                route_momentum=self.config.route_momentum,
                dwell_bonus=dwell,
                diversity_floor=self.config.diversity_floor)
            scores.append(SmoothedRouteScore(
                score.route_id, score.instantaneous_score,
                score.smoothed_score, score.momentum, score.dwell_bonus,
                score.total_score, bid.admissible))

        admissible = sorted(
            (score for score in scores if score.admissible),
            key=lambda row: (-row.total_score, row.route_id))
        selected = admissible[0] if admissible else None
        current = next((
            score for score in admissible
            if score.route_id == self._selected_route_id), None)
        retained_by_dwell = False
        retained_by_hysteresis = False
        if selected is not None and current is not None:
            age = step - int(self._selected_since)
            if (selected.route_id != current.route_id
                    and age < self.config.minimum_dwell_steps):
                selected = current
                retained_by_dwell = True
            elif (selected.route_id != current.route_id
                  and selected.total_score
                  < current.total_score + self.config.switch_margin):
                selected = current
                retained_by_hysteresis = True

        selected_id = None if selected is None else selected.route_id
        if selected_id != self._selected_route_id:
            self._selected_route_id = selected_id
            self._selected_since = None if selected_id is None else step
        self._last_step = step

        backup = next((
            score for score in admissible
            if score.route_id != selected_id), None)
        allocations = ()
        if selected is not None:
            if backup is None or self.config.diversity_floor == 0.0:
                allocations = ((selected_id, 1.0),)
            else:
                allocations = (
                    (selected_id, 1.0 - self.config.diversity_floor),
                    (backup.route_id, self.config.diversity_floor),
                )
        return SmoothedScalarDecision(
            step, selected_id, None if backup is None else backup.route_id,
            allocations, tuple(sorted(
                scores, key=lambda row: (-row.total_score, row.route_id))),
            retained_by_dwell, retained_by_hysteresis,
            self.SOLVER_IDENTITY, self.config.to_dict())

    @staticmethod
    def schedule_packets(
            operations, scores, budgets, **kwargs):
        """Use the same whole-packet scheduler as scalar PF-v2."""
        from .packets import PacketScheduler
        return PacketScheduler().schedule(
            operations, scores, budgets, **kwargs)
