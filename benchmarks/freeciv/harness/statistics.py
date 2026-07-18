"""Predeclared Wilson and deterministic paired-bootstrap intervals."""

import math
import random


def mean(values):
    return sum(values) / float(len(values)) if values else None


def wilson(successes, samples, z=1.959963984540054):
    if not samples:
        return {"estimate": None, "lower": None, "upper": None, "n": 0,
                "method": "wilson"}
    p = float(successes) / samples
    denominator = 1.0 + z * z / samples
    center = (p + z * z / (2.0 * samples)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * samples)) / samples) / denominator
    return {"estimate": p, "lower": max(0.0, center - margin),
            "upper": min(1.0, center + margin), "n": samples, "method": "wilson"}


def bootstrap_mean(values, samples=2000, seed=7717, confidence=0.95):
    values = tuple(float(value) for value in values)
    if not values:
        return {"estimate": None, "lower": None, "upper": None, "n": 0,
                "method": "bootstrap_mean"}
    randomizer = random.Random(int(seed))
    estimates = []
    for _ in range(int(samples)):
        estimates.append(mean([values[randomizer.randrange(len(values))]
                               for _ in values]))
    estimates.sort()
    alpha = (1.0 - confidence) / 2.0
    lower = estimates[max(0, int(alpha * len(estimates)))]
    upper = estimates[min(len(estimates) - 1, int((1.0 - alpha) * len(estimates)))]
    return {"estimate": mean(values), "lower": lower, "upper": upper,
            "n": len(values), "method": "bootstrap_mean"}


def paired_delta(left_by_seed, right_by_seed, **kwargs):
    shared = sorted(set(left_by_seed) & set(right_by_seed))
    differences = [float(right_by_seed[seed]) - float(left_by_seed[seed]) for seed in shared]
    result = bootstrap_mean(differences, **kwargs)
    result["method"] = "paired_bootstrap_delta"
    result["paired_seeds"] = shared
    return result
