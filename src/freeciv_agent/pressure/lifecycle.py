"""Bounded latent-clone projection and lifecycle representation controls."""

import json
import math
import os
import threading
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes, structural_hash
from .model import (
    PressureMagnitude,
    PressureVector,
    SignedPressureVector,
    TruthState,
)


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
        if any(not isinstance(
                value, (PressureVector, SignedPressureVector))
                for _, value in self.pressure):
            raise TypeError(
                "clone pressure values must be pressure vectors")
        pressure_types = set(
            type(value) for _, value in self.pressure)
        if len(pressure_types) > 1:
            raise TypeError(
                "one clone cannot mix v1 and v2 pressure values")

    def to_dict(self):
        value = {
            "atom_id": self.atom_id,
            "clone_id": self.clone_id,
            "lifecycle": self.lifecycle,
            "posterior": float(self.posterior),
            "pressure": dict(
                (goal_id, value.to_dict()) for goal_id, value in self.pressure),
            "successor_distribution": dict(
                (str(key), float(value))
                for key, value in self.successor_distribution),
            "truth": self.truth.to_dict(),
        }
        if any(isinstance(
                pressure, SignedPressureVector)
                for _, pressure in self.pressure):
            value["pressure_schema_version"] = "2.0"
        return value

    @classmethod
    def from_dict(cls, value):
        truth = value["truth"]
        pressure_schema = value.get("pressure_schema_version", "1.0")
        if pressure_schema not in ("1.0", "2.0"):
            raise ValueError("unsupported clone pressure schema")

        def pressure_value(row):
            if pressure_schema == "2.0":
                if set(row) != {"negative", "positive"}:
                    raise ValueError(
                        "signed clone pressure requires both rails")
                return SignedPressureVector(
                    positive=PressureMagnitude(**row["positive"]),
                    negative=PressureMagnitude(**row["negative"]))
            return PressureVector(**row)

        return cls(
            clone_id=value["clone_id"],
            atom_id=value["atom_id"],
            posterior=float(value["posterior"]),
            truth=TruthState(
                truth["strength"], truth["confidence"],
                tuple(truth.get("evidence_ids", ())),
                bool(truth.get("crisp", False))),
            lifecycle=value.get("lifecycle", "active"),
            successor_distribution=tuple(sorted(
                (str(key), float(probability))
                for key, probability in
                value.get("successor_distribution", {}).items())),
            pressure=tuple(sorted(
                (str(goal_id), pressure_value(pressure))
                for goal_id, pressure in value.get("pressure", {}).items())),
        )


class CloneManager(object):
    """Bayes updates and projections under a hard per-atom clone cap."""

    def __init__(self, maximum_clones=8, split_threshold=0.5,
                 merge_truth_tolerance=0.05, merge_pressure_tolerance=0.05,
                 merge_successor_tolerance=0.05,
                 complexity_penalty=0.5, confidence_k=1.0):
        if isinstance(maximum_clones, bool) or not 1 <= int(maximum_clones) <= 128:
            raise ValueError("maximum clones must be in 1..128")
        for value, name in (
                (split_threshold, "split threshold"),
                (merge_truth_tolerance, "merge truth tolerance"),
                (merge_pressure_tolerance, "merge pressure tolerance"),
                (merge_successor_tolerance, "merge successor tolerance")):
            if not 0 <= float(value) <= 1:
                raise ValueError("{} must be in [0,1]".format(name))
        if float(complexity_penalty) < 0 or float(confidence_k) <= 0:
            raise ValueError("complexity penalty and confidence k are invalid")
        self.maximum_clones = int(maximum_clones)
        self.split_threshold = float(split_threshold)
        self.merge_truth_tolerance = float(merge_truth_tolerance)
        self.merge_pressure_tolerance = float(merge_pressure_tolerance)
        self.merge_successor_tolerance = float(merge_successor_tolerance)
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

    def visible_pressure(self, clones, goal_id, risk_alpha=None):
        clones = self.normalize(clones)
        present = tuple(
            dict(clone.pressure)[goal_id]
            for clone in clones if goal_id in dict(clone.pressure))
        pressure_types = set(type(value) for value in present)
        if len(pressure_types) > 1:
            raise TypeError(
                "clone projection cannot mix v1 and v2 pressure")
        signed = bool(
            present and isinstance(present[0], SignedPressureVector))
        empty = (
            SignedPressureVector() if signed else PressureVector())
        if risk_alpha is not None:
            risk_alpha = float(risk_alpha)
            if not 0.0 < risk_alpha <= 1.0:
                raise ValueError("risk alpha must be in (0,1]")
            def tail_mean(extract):
                remaining = risk_alpha
                total = 0.0
                ordered = sorted(
                    clones,
                    key=lambda row: extract(
                        dict(row.pressure).get(goal_id, empty)),
                    reverse=True)
                for clone in ordered:
                    mass = min(remaining, clone.posterior)
                    total += mass * extract(
                        dict(clone.pressure).get(goal_id, empty))
                    remaining -= mass
                    if remaining <= 1e-15:
                        break
                return total / risk_alpha

            if signed:
                positive = {}
                negative = {}
                for channel in (
                        "infer", "observe", "act", "expand", "retain"):
                    positive[channel] = tail_mean(
                        lambda value, name=channel:
                        value.positive.value(name))
                    negative[channel] = tail_mean(
                        lambda value, name=channel:
                        value.negative.value(name))
                return SignedPressureVector(
                    positive=PressureMagnitude(**positive),
                    negative=PressureMagnitude(**negative))
            values = {}
            for channel in (
                    "infer", "observe", "act", "expand", "retain"):
                values[channel] = tail_mean(
                    lambda value, name=channel: value.value(name))
            return PressureVector(**values)
        result = empty
        for clone in clones:
            value = dict(clone.pressure).get(goal_id, empty)
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
        successor_labels = (
            set(dict(left.successor_distribution))
            | set(dict(right.successor_distribution)))
        successor_distance = max((
            abs(
                float(dict(left.successor_distribution).get(label, 0.0))
                - float(dict(right.successor_distribution).get(label, 0.0)))
            for label in successor_labels), default=0.0)
        goals = set(dict(left.pressure)) | set(dict(right.pressure))
        pressure_distance = 0.0
        for goal_id in goals:
            a = dict(left.pressure).get(goal_id)
            b = dict(right.pressure).get(goal_id)
            if a is None:
                a = (
                    SignedPressureVector()
                    if isinstance(b, SignedPressureVector)
                    else PressureVector())
            if b is None:
                b = (
                    SignedPressureVector()
                    if isinstance(a, SignedPressureVector)
                    else PressureVector())
            if type(a) is not type(b):
                return False
            if isinstance(a, SignedPressureVector):
                distances = tuple(
                    abs(getattr(a, rail).value(channel)
                        - getattr(b, rail).value(channel))
                    for rail in ("positive", "negative")
                    for channel in (
                        "infer", "observe", "act", "expand", "retain"))
            else:
                distances = tuple(
                    abs(a.value(channel) - b.value(channel))
                    for channel in (
                        "infer", "observe", "act", "expand", "retain"))
            pressure_distance = max(
                pressure_distance, max(distances, default=0.0))
        return (
            truth_close <= self.merge_truth_tolerance
            and successor_distance <= self.merge_successor_tolerance
            and pressure_distance <= self.merge_pressure_tolerance)


class CloneTransactionError(RuntimeError):
    pass


class CloneLifecycleStore(object):
    """Atomic persistent clone sets with lineage forwarding and hard caps."""

    SCHEMA_VERSION = "1.0"

    def __init__(self, path, manager=None):
        self.path = os.path.abspath(path)
        self.manager = manager or CloneManager()
        self._lock = threading.RLock()
        self._state = {
            "schema_version": self.SCHEMA_VERSION,
            "atoms": {},
            "forwarding": {},
            "applied_events": [],
            "history": [],
        }
        if os.path.exists(self.path):
            self._load()

    def _load(self):
        with open(self.path, encoding="utf-8") as stream:
            value = json.load(stream)
        if value.get("schema_version") != self.SCHEMA_VERSION:
            raise CloneTransactionError("unsupported clone lifecycle schema")
        self._state = value
        for atom_id, row in self._state["atoms"].items():
            clones = tuple(CloneState.from_dict(item) for item in row["clones"])
            self._validate_set(atom_id, clones)

    def _validate_set(self, atom_id, clones):
        clones = tuple(clones)
        if not clones or len(clones) > self.manager.maximum_clones:
            raise CloneTransactionError("clone set violates per-atom cap")
        if any(clone.atom_id != atom_id for clone in clones):
            raise CloneTransactionError("clone stored under the wrong visible atom")
        ids = [clone.clone_id for clone in clones]
        if len(ids) != len(set(ids)):
            raise CloneTransactionError("active clone IDs must be unique")
        if abs(sum(clone.posterior for clone in clones) - 1.0) > 1e-9:
            raise CloneTransactionError("active clone posterior must sum to one")

    def _persist(self):
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        temporary = "{}.tmp.{}.{}".format(
            self.path, os.getpid(), threading.get_ident())
        payload = canonical_json_bytes(self._state) + b"\n"
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            written = os.write(fd, payload)
            if written != len(payload):
                raise CloneTransactionError("short clone lifecycle write")
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, self.path)

    def _set(self, atom_id, clones):
        clones = tuple(sorted(
            self.manager.normalize(clones), key=lambda row: row.clone_id))
        self._validate_set(atom_id, clones)
        prior = self._state["atoms"].get(atom_id, {})
        self._state["atoms"][atom_id] = {
            "clones": [clone.to_dict() for clone in clones],
            "version": int(prior.get("version", 0)) + 1,
        }
        return clones

    def initialize(self, atom_id, clones):
        with self._lock:
            if atom_id in self._state["atoms"]:
                raise CloneTransactionError(
                    "clone set already initialized for {}".format(atom_id))
            clones = self._set(str(atom_id), clones)
            self._persist()
            return clones

    def clones(self, atom_id):
        with self._lock:
            row = self._state["atoms"].get(str(atom_id))
            if row is None:
                return ()
            return tuple(CloneState.from_dict(item) for item in row["clones"])

    def _begin(self, event_id, atom_id, operation):
        event_id = str(event_id)
        if not event_id:
            raise CloneTransactionError("clone transaction event ID is required")
        if event_id in self._state["applied_events"]:
            return False
        if str(atom_id) not in self._state["atoms"]:
            raise CloneTransactionError("unknown clone atom {}".format(atom_id))
        return True

    def _finish(self, event_id, atom_id, operation, detail):
        self._state["applied_events"].append(str(event_id))
        self._state["applied_events"].sort()
        self._state["history"].append({
            "atom_id": str(atom_id),
            "detail": detail,
            "event_id": str(event_id),
            "operation": str(operation),
            "state_hash": self.state_hash,
        })
        self._persist()

    def bayes_update(self, atom_id, likelihoods, event_id):
        with self._lock:
            if not self._begin(event_id, atom_id, "bayes_update"):
                return self.clones(atom_id)
            before = self.clones(atom_id)
            updated = self.manager.bayes_update(before, likelihoods)
            truncated = max(0, len(before) - len(updated))
            result = self._set(str(atom_id), updated)
            self._finish(event_id, atom_id, "bayes_update", {
                "likelihoods": dict(sorted(
                    (str(key), float(value))
                    for key, value in dict(likelihoods).items())),
                "truncated_clones": truncated,
            })
            return result

    def split(self, atom_id, parent_id, children, predictive_gain,
              added_parameters, split_score, event_id):
        with self._lock:
            if not self._begin(event_id, atom_id, "split"):
                return self.clones(atom_id)
            current = self.clones(atom_id)
            parent = next(
                (row for row in current if row.clone_id == str(parent_id)), None)
            if parent is None:
                raise CloneTransactionError("split parent is not active")
            children = tuple(children)
            if not children or any(
                    child.atom_id != str(atom_id) for child in children):
                raise CloneTransactionError("split children have invalid atom")
            if abs(
                    sum(child.posterior for child in children)
                    - parent.posterior) > 1e-9:
                raise CloneTransactionError(
                    "split children must preserve parent posterior mass")
            new_count = len(current) - 1 + len(children)
            if (new_count > self.manager.maximum_clones
                    or not self.manager.accept_split(
                        len(current), predictive_gain, added_parameters,
                        split_score)):
                raise CloneTransactionError("split rejected by lifecycle gates")
            result = self._set(
                str(atom_id),
                tuple(row for row in current if row.clone_id != parent.clone_id)
                + children)
            self._state["forwarding"][parent.clone_id] = sorted(
                child.clone_id for child in children)
            self._finish(event_id, atom_id, "split", {
                "children": sorted(child.clone_id for child in children),
                "parent": parent.clone_id,
            })
            return result

    def merge(self, atom_id, left_id, right_id, merged, event_id):
        with self._lock:
            if not self._begin(event_id, atom_id, "merge"):
                return self.clones(atom_id)
            current = self.clones(atom_id)
            by_id = dict((row.clone_id, row) for row in current)
            left = by_id.get(str(left_id))
            right = by_id.get(str(right_id))
            if left is None or right is None or left.clone_id == right.clone_id:
                raise CloneTransactionError("merge inputs must be active and distinct")
            if not self.manager.merge_eligible(left, right):
                raise CloneTransactionError("merge rejected by similarity gates")
            if (merged.atom_id != str(atom_id)
                    or abs(
                        merged.posterior
                        - left.posterior - right.posterior) > 1e-9):
                raise CloneTransactionError(
                    "merged clone must preserve atom and posterior mass")
            result = self._set(
                str(atom_id),
                tuple(
                    row for row in current
                    if row.clone_id not in (left.clone_id, right.clone_id))
                + (merged,))
            self._state["forwarding"][left.clone_id] = [merged.clone_id]
            self._state["forwarding"][right.clone_id] = [merged.clone_id]
            self._finish(event_id, atom_id, "merge", {
                "merged": merged.clone_id,
                "parents": sorted((left.clone_id, right.clone_id)),
            })
            return result

    def resolve(self, clone_id):
        """Resolve retired references through split/merge forwarding."""
        with self._lock:
            memo = {}

            def visit(current, active):
                if current in memo:
                    return memo[current]
                if current in active:
                    raise CloneTransactionError("clone forwarding cycle")
                successors = self._state["forwarding"].get(current)
                if successors is None:
                    result = frozenset((current,))
                else:
                    result = frozenset().union(*(
                        visit(successor, active | {current})
                        for successor in successors))
                memo[current] = result
                return result

            return tuple(sorted(visit(str(clone_id), set())))

    @property
    def state_hash(self):
        value = dict(self._state)
        # History stores the hash before its own append to avoid recursion.
        value["history"] = [
            dict((key, item) for key, item in row.items()
                 if key != "state_hash")
            for row in self._state["history"]]
        return structural_hash(value)

    @property
    def artifact(self):
        with self._lock:
            result = json.loads(canonical_json_bytes(self._state).decode("utf-8"))
            result["state_hash"] = self.state_hash
            return result
