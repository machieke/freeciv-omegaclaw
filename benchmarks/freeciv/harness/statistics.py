"""Predeclared Wilson and deterministic paired-bootstrap intervals."""

import math
import random
from statistics import NormalDist


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


def paired_score_randomization(differences, margin=0.0, maximum_states=1000000,
                               alternative="two_sided"):
    """Exact paired sign-flip test for an integer score effect.

    FreeCiv scores are integers.  Under the sharp null, swapping treatment and
    baseline within every seed pair is equivalent to independently flipping the
    signs of the paired differences.  Dynamic programming evaluates the full
    randomization distribution without enumerating every one of its 2**n
    assignments.  A state bound makes an unexpectedly large score range fail
    closed instead of silently switching to an approximate test.
    """
    margin = float(margin)
    maximum_states = int(maximum_states)
    if alternative not in ("two_sided", "greater"):
        raise ValueError("alternative must be 'two_sided' or 'greater'")
    if maximum_states < 1:
        raise ValueError("maximum_states must be positive")
    adjusted = [float(value) - margin for value in differences]
    result = {
        "alternative": alternative, "exact": True,
        "margin": margin, "maximum_states": maximum_states,
        "method": "exact-paired-sign-flip-randomization",
        "nonzero_pairs": 0, "observed_mean_difference": mean(adjusted),
        "p_value": None, "pairs": len(adjusted), "ready": False,
        "states_evaluated": 0,
    }
    if not adjusted:
        result["reason"] = "at least one paired score difference is required"
        return result
    integral = []
    for value in adjusted:
        rounded = round(value)
        if not math.isclose(value, rounded, rel_tol=0.0, abs_tol=1e-9):
            result["reason"] = (
                "exact score randomization requires integer score differences "
                "after applying the declared margin")
            return result
        integral.append(int(rounded))
    weights = [abs(value) for value in integral if value]
    result["nonzero_pairs"] = len(weights)
    if not weights:
        result.update({"p_value": 1.0, "ready": True, "states_evaluated": 1,
                       "reason": None})
        return result

    divisor = weights[0]
    for value in weights[1:]:
        divisor = math.gcd(divisor, value)
    weights = [value // divisor for value in weights]
    observed_signed = sum(integral) // divisor
    distribution = {0: 1}
    for weight in weights:
        updated = {}
        for total, count in distribution.items():
            updated[total + weight] = updated.get(total + weight, 0) + count
            updated[total - weight] = updated.get(total - weight, 0) + count
        if len(updated) > maximum_states:
            result.update({
                "reason": (
                    "exact score randomization exceeded the predeclared "
                    "{}-state bound".format(maximum_states)),
                "states_evaluated": len(updated),
            })
            return result
        distribution = updated
    if alternative == "greater":
        extreme = sum(count for total, count in distribution.items()
                      if total >= observed_signed)
    else:
        observed = abs(observed_signed)
        extreme = sum(count for total, count in distribution.items()
                      if abs(total) >= observed)
    result.update({
        "p_value": extreme / float(2 ** len(weights)), "ready": True,
        "reason": None, "states_evaluated": len(distribution),
    })
    return result


def paired_power(differences, alpha=0.05, target_power=0.8,
                 minimum_detectable_delta=2.0, minimum_pairs=30):
    """Normal-approximation planning values from observed paired differences."""
    values = tuple(float(value) for value in differences)
    result = {
        "achieved_pairs": len(values), "achieved_power": None,
        "alpha": float(alpha), "minimum_detectable_delta": float(
            minimum_detectable_delta),
        "observed_paired_sd": None, "required_pairs": None,
        "target_power": float(target_power), "detectable_delta_at_achieved_n": None,
        "method": "paired-normal-approximation", "minimum_variance_pairs": int(
            minimum_pairs), "ready": False,
    }
    if len(values) < int(minimum_pairs):
        result["reason"] = (
            "variance and achieved-power reporting require at least {} completed pairs".format(
                int(minimum_pairs)))
        return result
    average = mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    deviation = math.sqrt(variance)
    result["observed_paired_sd"] = deviation
    if deviation == 0:
        result.update({
            "achieved_power": 1.0, "required_pairs": int(minimum_pairs),
            "detectable_delta_at_achieved_n": 0.0,
            "ready": True, "reason": None,
        })
        return result
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1.0 - float(alpha) / 2.0)
    z_power = normal.inv_cdf(float(target_power))
    required = ((z_alpha + z_power) * deviation
                / float(minimum_detectable_delta)) ** 2
    signal = math.sqrt(len(values)) * float(minimum_detectable_delta) / deviation
    achieved = normal.cdf(signal - z_alpha) + normal.cdf(-signal - z_alpha)
    result.update({
        "achieved_power": min(1.0, achieved),
        "required_pairs": max(int(minimum_pairs), int(math.ceil(required))),
        "detectable_delta_at_achieved_n": (
            (z_alpha + z_power) * deviation / math.sqrt(len(values))),
        "ready": True, "reason": None,
    })
    return result


def paired_binary_effect(left_by_seed, right_by_seed, **kwargs):
    """Paired absolute risk difference with a seed-pair bootstrap interval."""
    shared = sorted(set(left_by_seed) & set(right_by_seed))
    differences = [int(bool(right_by_seed[seed])) - int(bool(left_by_seed[seed]))
                   for seed in shared]
    result = bootstrap_mean(differences, **kwargs)
    result["method"] = "paired-bootstrap-risk-difference"
    result["paired_seeds"] = shared
    return result


def _binomial_probabilities(samples, probability):
    if probability <= 0:
        return [1.0] + [0.0] * samples
    if probability >= 1:
        return [0.0] * samples + [1.0]
    logs = [
        math.lgamma(samples + 1) - math.lgamma(successes + 1)
        - math.lgamma(samples - successes + 1)
        + successes * math.log(probability)
        + (samples - successes) * math.log1p(-probability)
        for successes in range(samples + 1)
    ]
    peak = max(logs)
    weights = [math.exp(value - peak) for value in logs]
    total = sum(weights)
    return [value / total for value in weights]


def paired_win_design_power(pairs, minimum_detectable_delta, discordance,
                            alpha=0.05, target_power=0.8):
    """Exact two-sided McNemar power under a predeclared paired alternative."""
    pairs = int(pairs)
    delta = float(minimum_detectable_delta)
    discordance = float(discordance)
    if pairs < 1 or not 0 < delta <= discordance <= 1:
        raise ValueError("invalid paired win power design")
    conditional_treatment = (discordance + delta) / (2.0 * discordance)
    conditional_power = []
    for discordant in range(pairs + 1):
        null = _binomial_probabilities(discordant, 0.5)
        cumulative = 0.0
        critical = -1
        for successes in range(discordant // 2 + 1):
            cumulative += null[successes]
            if min(1.0, 2.0 * cumulative) <= float(alpha) + 1e-15:
                critical = successes
        if critical < 0:
            conditional_power.append(0.0)
            continue
        alternative = _binomial_probabilities(discordant, conditional_treatment)
        conditional_power.append(
            sum(alternative[:critical + 1])
            + sum(alternative[discordant - critical:]))
    discordant_probabilities = _binomial_probabilities(pairs, discordance)
    power = sum(probability * conditional_power[count]
                for count, probability in enumerate(discordant_probabilities))
    return {
        "alpha": float(alpha), "method": "exact-two-sided-mcnemar-design-power",
        "minimum_detectable_delta": delta, "planned_discordance": discordance,
        "planned_pairs": pairs, "planned_power": power,
        "target_power": float(target_power), "target_met": power >= float(target_power),
    }


def paired_binary_discordance(left_by_seed, right_by_seed):
    """Retain all paired binary outcomes and exact two-sided McNemar evidence."""
    shared = sorted(set(left_by_seed) & set(right_by_seed))
    counts = {"both_lose": 0, "both_win": 0,
              "baseline_only_win": 0, "treatment_only_win": 0}
    for seed in shared:
        left = bool(left_by_seed[seed])
        right = bool(right_by_seed[seed])
        if left and right:
            counts["both_win"] += 1
        elif left:
            counts["baseline_only_win"] += 1
        elif right:
            counts["treatment_only_win"] += 1
        else:
            counts["both_lose"] += 1
    discordant = counts["baseline_only_win"] + counts["treatment_only_win"]
    if discordant:
        smaller = min(counts["baseline_only_win"], counts["treatment_only_win"])
        probability = min(1.0, 2.0 * sum(
            math.comb(discordant, index) for index in range(smaller + 1))
                          / float(2 ** discordant))
    else:
        probability = 1.0
    return dict(
        counts, discordant_pairs=discordant, exact_mcnemar_p=probability,
        method="exact-two-sided-mcnemar", paired_seeds=shared,
        pairs=len(shared))
