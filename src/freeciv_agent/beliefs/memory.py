"""Version-scoped repeated-opponent evidence memory and post-game audit."""

import json
import os
import threading

from ..events.schema import structural_hash


class OpponentMemory(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self._lock = threading.RLock()
        self._rows = {}
        if os.path.isfile(self.path):
            with open(self.path, encoding="utf-8") as stream:
                value = json.load(stream)
            if value.get("schema_version") != "1.0":
                raise ValueError("unsupported opponent memory schema")
            self._rows = dict(value.get("populations", {}))

    @staticmethod
    def population_id(opponent_id, ruleset, model_version):
        return "population-" + structural_hash([
            str(opponent_id), str(ruleset), str(model_version)])[:20]

    def record(self, opponent_id, ruleset, model_version, predicate, predicted, true):
        population = self.population_id(opponent_id, ruleset, model_version)
        key = "{}:{}".format(predicate, "positive" if predicted else "negative")
        with self._lock:
            row = self._rows.setdefault(population, {
                "model_version": str(model_version), "opponent_id": str(opponent_id),
                "ruleset": str(ruleset), "counts": {},
            })
            counts = row["counts"].setdefault(key, {"samples": 0, "true": 0})
            counts["samples"] += 1
            counts["true"] += int(bool(true))

    def predict(self, opponent_id, ruleset, model_version, predicate,
                default_probability, decision_threshold, minimum_samples):
        """Return the scoped empirical prediction available before a game."""
        population = self.population_id(opponent_id, ruleset, model_version)
        with self._lock:
            row = self._rows.get(population, {})
            counts = row.get("counts", {})
            samples = true = 0
            prefix = str(predicate) + ":"
            for key, value in counts.items():
                if not str(key).startswith(prefix):
                    continue
                samples += int(value.get("samples", 0))
                true += int(value.get("true", 0))
        probability = (float(true) / samples
                       if samples >= int(minimum_samples) and samples > 0
                       else float(default_probability))
        return {"predicted": probability >= float(decision_threshold),
                "probability": probability, "samples": samples}

    def estimate(self, opponent_id, ruleset, model_version, predicate, predicted=True):
        """Return a population-scoped empirical prediction from prior games only.

        The caller decides when to record the current game's outcome, which keeps
        post-game omniscient truth from leaking into the live decision path.
        """
        population = self.population_id(opponent_id, ruleset, model_version)
        key = "{}:{}".format(predicate, "positive" if predicted else "negative")
        with self._lock:
            row = self._rows.get(population)
            counts = None if row is None else row.get("counts", {}).get(key)
            if not counts or not counts.get("samples"):
                return None
            samples = int(counts["samples"])
            true = int(counts["true"])
            return {
                "population_id": population, "predicate": str(predicate),
                "predicted": bool(predicted), "samples": samples, "true": true,
                "empirical_frequency": float(true) / samples,
            }

    def save(self):
        with self._lock:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            temporary = self.path + ".tmp.{}".format(os.getpid())
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump({"schema_version": "1.0", "populations": self._rows},
                          stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary, self.path)

    def to_dict(self):
        with self._lock:
            return {"schema_version": "1.0", "populations": self._rows}


def post_game_calibration(predictions, truth, post_game=False):
    """Compare beliefs to omniscient truth only after the game has ended."""
    if not post_game:
        raise PermissionError("omniscient truth is unavailable to the live agent")
    buckets = {}
    for belief in predictions:
        lower = int(min(9, belief.strength * 10)) / 10.0
        row = buckets.setdefault("{:.1f}".format(lower), {
            "bucket_strength": lower + 0.05, "samples": 0, "true": 0})
        row["samples"] += 1
        row["true"] += int(bool(truth.get(belief.atom_id, False)))
    result = []
    for name in sorted(buckets):
        row = buckets[name]
        empirical = float(row["true"]) / row["samples"]
        result.append(dict(row, bucket=name, empirical_frequency=empirical,
                           absolute_error=abs(empirical - row["bucket_strength"]),
                           sufficient_sample=row["samples"] >= 10))
    return {"buckets": result, "samples": sum(row["samples"] for row in result)}
