"""Bounded latent-clone projection and lifecycle representation controls."""

import math
from dataclasses import dataclass

from .model import PressureVector, TruthState


@dataclass(frozen=True)
class CloneState:
    clone_id: str
    atom_id: str
    posterior: float
    truth: TruthState
    lifecycle: str = "active"
    successor_distribution: tuple = ()
    pressure: tuple = ()

    def __post_init__(self):
        if not self.clone_id or not self.atom_id:
            raise ValueError("clone and atom IDs are required")
        if not 0 <= float(self.posterior) <= 1:
            raise ValueError("clone posterior must be in [0,1]")
        if len(dict(self.successor_distribution)) != len(self.successor_distribution):
            raise ValueError("successor labels must be unique")
        if any(float(value) < 0 for _, value in self.successor_distribution):
            raise ValueError("successor probabilities must be nonnegative")
        if len(dict(self.pressure)) != len(self.pressure):
            raise ValueError("clone goal pressure IDs must be unique")
        if any(not isinstance(value, PressureVector) for _, value in self.pressure):
            raise TypeError("clone pressure values must be PressureVector")


class CloneManager(object):
    """Bayes updates and projections under a hard per-atom clone cap."""

    def __init__(self, maximum_clones=8, split_threshold=0.5,
                 merge_truth_tolerance=0.05, merge_pressure_tolerance=0.05,
                 complexity_penalty=0.5, confidence_k=1.0):
        if isinstance(maximum_clones, bool) or not 1 <= int(maximum_clones) <= 128:
            raise ValueError("maximum clones must be in 1..128")
        for value, name in (
                (split_threshold, "split threshold"),
                (merge_truth_tolerance, "merge truth tolerance"),
                (merge_pressure_tolerance, "merge pressure tolerance")):
            if not 0 <= float(value) <= 1:
                raise ValueError("{} must be in [0,1]".format(name))
        if float(complexity_penalty) < 0 or float(confidence_k) <= 0:
            raise ValueError("complexity penalty and confidence k are invalid")
        self.maximum_clones = int(maximum_clones)
        self.split_threshold = float(split_threshold)
        self.merge_truth_tolerance = float(merge_truth_tolerance)
        self.merge_pressure_tolerance = float(merge_pressure_tolerance)
        self.complexity_penalty = float(complexity_penalty)
        self.confidence_k = float(confidence_k)

    @staticmethod
    def normalize(clones):
        clones = tuple(clones)
        total = sum(float(clone.posterior) for clone in clones)
        if not clones or total <= 0:
            raise ValueError("clone posterior mass must be positive")
        return tuple(CloneState(
            clone.clone_id, clone.atom_id, clone.posterior / total, clone.truth,
            clone.lifecycle, clone.successor_distribution, clone.pressure)
            for clone in clones)

    def bayes_update(self, clones, likelihoods):
        likelihoods = dict(likelihoods)
        rows = []
        for clone in clones:
            likelihood = float(likelihoods.get(clone.clone_id, 0.0))
            if not 0 <= likelihood <= 1:
                raise ValueError("clone likelihood must be in [0,1]")
            rows.append(CloneState(
                clone.clone_id, clone.atom_id,
                clone.posterior * likelihood, clone.truth, clone.lifecycle,
                clone.successor_distribution, clone.pressure))
        normalized = sorted(
            self.normalize(rows), key=lambda row: (-row.posterior, row.clone_id))
        normalized = normalized[:self.maximum_clones]
        return self.normalize(normalized)

    def visible_truth(self, clones):
        clones = self.normalize(clones)
        mean = sum(clone.posterior * clone.truth.strength for clone in clones)
        variance = 0.0
        evidence = set()
        for clone in clones:
            confidence = min(float(clone.truth.confidence), 1.0 - 1e-12)
            weight = self.confidence_k * confidence / (1.0 - confidence)
            within = (
                clone.truth.strength * (1.0 - clone.truth.strength)
                / (weight + 1.0))
            variance += clone.posterior * (
                within + (clone.truth.strength - mean) ** 2)
            evidence.update(clone.truth.evidence_ids)
        maximum_variance = mean * (1.0 - mean)
        if variance <= 0:
            equivalent_weight = 1e12
        elif maximum_variance <= variance:
            equivalent_weight = 0.0
        else:
            equivalent_weight = max(0.0, maximum_variance / variance - 1.0)
        confidence = equivalent_weight / (
            equivalent_weight + self.confidence_k)
        return TruthState(mean, confidence, tuple(sorted(evidence)))

    def visible_pressure(self, clones, goal_id):
        clones = self.normalize(clones)
        result = PressureVector()
        for clone in clones:
            value = dict(clone.pressure).get(goal_id, PressureVector())
            result = result.plus(value.scaled(clone.posterior))
        return result

    def split_score(self, successor_divergence, conflict_severity,
                    action_outcome_gap, pressure_divergence):
        values = (
            float(successor_divergence), float(conflict_severity),
            float(action_outcome_gap), float(pressure_divergence))
        if any(not 0 <= value <= 1 for value in values):
            raise ValueError("split score components must be in [0,1]")
        return sum(values) / len(values)

    def accept_split(self, current_count, predictive_gain, added_parameters,
                     split_score):
        if int(current_count) >= self.maximum_clones:
            return False
        if float(split_score) < self.split_threshold:
            return False
        return float(predictive_gain) > (
            self.complexity_penalty * max(0, int(added_parameters)))

    def merge_eligible(self, left, right):
        truth_close = abs(left.truth.strength - right.truth.strength)
        goals = set(dict(left.pressure)) | set(dict(right.pressure))
        pressure_distance = 0.0
        for goal_id in goals:
            a = dict(left.pressure).get(goal_id, PressureVector())
            b = dict(right.pressure).get(goal_id, PressureVector())
            pressure_distance = max(
                pressure_distance,
                max(abs(a.value(channel) - b.value(channel))
                    for channel in ("infer", "observe", "act", "expand", "retain")))
        return (
            truth_close <= self.merge_truth_tolerance
            and pressure_distance <= self.merge_pressure_tolerance)
