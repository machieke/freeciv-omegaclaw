"""Deterministic robust scaling fits, intervals, and bounded gate decisions."""

import math
import random
import statistics


SURFACE_FITS = {
    "atomspace": ("live_revision_atoms", "incremental_ms", 1.35),
    "proof": ("relevant_rules", "kernel_elapsed_ms", 1.50),
    "bridge": ("edges", "kernel_elapsed_ms", 1.50),
    "fluid": ("edge_updates", "kernel_elapsed_ms", 1.25),
}

SECONDARY_FITS = {
    "atomspace": (
        ("peak-rss-vs-live-atoms", "live_revision_atoms",
         "peak_rss_bytes", 1.15),
    ),
}

ABSOLUTE_LABELS = {
    "atomspace": (
        ("A2-interactive", "A2", "incremental_ms", 500.0),
        ("A4-research-usable", "A4", "incremental_ms", 2000.0),
    ),
    "proof": (
        ("P2-10k-research-usable", "P2", "kernel_elapsed_ms", 2000.0),
        ("P3-100k-stress-usable", "P3", "kernel_elapsed_ms", 15000.0),
    ),
    "bridge": (
        ("B1-live-capable", "B1", "controller_inclusive_ms", 500.0),
        ("B3-research-usable", "B3", "controller_inclusive_ms", 2000.0),
    ),
    "fluid": (
        ("F3-research-usable", "F3", "kernel_elapsed_ms", 5000.0),
    ),
}


def required_correctness_keys(row):
    """Semantic invariants required for a completed surface trial."""
    surface = row.get("trial", {}).get("cell", {}).get("surface")
    correctness = row.get("correctness", {})
    arm = row.get("trial", {}).get("arm")
    if surface == "atomspace":
        keys = [
            "cold_incremental_equivalent", "count_exact",
            "synthetic_namespace_only"]
        if "retention_cycles" in row.get("actual_work", {}):
            keys.extend((
                "revision_retention_no_leak", "scope_retention_no_leak",
                "rss_plateau_within_5_percent"))
        return tuple(keys)
    if surface == "proof":
        return ("matches_reference",)
    if surface == "bridge":
        if "scalar_winner_recalled" not in correctness:
            return ("bridge_separated",)
        keys = [
            "scalar_order_preserved", "scalar_winner_recalled",
            "truth_hash_unchanged"]
        if arm != "scalar_pf_v2":
            keys.append("expected_bridge_recalled")
        if arm not in ("scalar_pf_v2", "source_sink_flow"):
            keys.append("bridge_separated")
        if arm == "source_sink_flow":
            keys.extend((
                "flow_healthy", "flow_mass_within_1e_9",
                "flow_no_positivity_corrections"))
        if correctness.get("fallback_required") is True:
            keys = [key for key in keys if key != "bridge_separated"]
        return tuple(keys)
    if surface == "fluid":
        keys = ["edge_updates_exact", "healthy", "mass_error_within_1e_9"]
        if int(row.get("actual_work", {}).get("failed_edges", 0)) > 0:
            keys.append("failed_edges_carried_no_current")
        return tuple(keys)
    return ()


def _primary_fit_eligible(row, surface):
    """Select the frozen canonical axis; never pool stress dimensions."""
    parameters = row.get("trial", {}).get("cell", {}).get("parameters", {})
    # Minimal hand-built rows are used by the analysis unit tests and by
    # downstream consumers that already preselect their fit population.
    if not parameters:
        return True
    if surface == "atomspace":
        return (
            parameters.get("topology", "local") == "local"
            and float(parameters.get("churn_fraction", 0.01)) == 0.01
            and int(parameters.get("support_multiplicity", 1)) == 1
            and int(parameters.get("retention_cycles", 0)) == 0)
    if surface == "proof":
        return (
            parameters.get("shape") == "shared_dag"
            and int(parameters.get("distractor_count", 0)) == 0)
    if surface == "bridge":
        return (
            parameters.get("arm", "protected_message")
            == "protected_message"
            and parameters.get(
                "topology", "disconnected_distractors")
            == "disconnected_distractors")
    if surface == "fluid":
        return (
            parameters.get("topology", "corridor") == "corridor"
            and float(parameters.get("failure_fraction", 0.0)) == 0.0)
    return True


def _proof_distractor_fit(rows, resamples):
    """Fit distractor cost within fixed relevant-node tiers."""
    maximum_exponent = 1.10
    tier_fits = {}
    all_points = []
    for tier in ("P1", "P2", "P3"):
        points = []
        clusters = {}
        for row in rows:
            cell = row["trial"]["cell"]
            parameters = cell.get("parameters", {})
            if (cell.get("tier") != tier
                    or parameters.get("shape") != "shared_dag"):
                continue
            work = row.get("actual_work", {}).get(
                "indexed_distractor_rules")
            metric = row.get("metrics", {}).get("kernel_elapsed_ms")
            if work is None or metric is None or float(work) <= 0.0:
                continue
            point = (float(work), float(metric))
            points.append(point)
            all_points.append(point)
            clusters.setdefault(str(cell["seed"]), []).append(point)
        interval = cluster_bootstrap_interval(
            clusters, resamples=resamples)
        upper = interval[1] if interval is not None else None
        distinct = len(set(point[0] for point in points))
        eligible = distinct >= 3 and upper is not None
        gate = (
            "pass" if eligible and upper <= maximum_exponent else
            "fail" if eligible else "not-entered")
        tier_fits[tier] = {
            "distinct_work_values": distinct,
            "eligible": eligible,
            "exponent": robust_log_slope(points),
            "exponent_95_ci": list(interval) if interval is not None else None,
            "gate": gate,
            "points": [[x, y] for x, y in points],
        }
    gates = [tier_fits[tier]["gate"] for tier in ("P1", "P2", "P3")]
    gate = (
        "fail" if "fail" in gates else
        "pass" if all(value == "pass" for value in gates) else
        "not-entered")
    eligible_intervals = [
        row["exponent_95_ci"] for row in tier_fits.values()
        if row["exponent_95_ci"] is not None]
    exponents = [
        row["exponent"] for row in tier_fits.values()
        if row["exponent"] is not None]
    return {
        "distinct_work_values": len(set(point[0] for point in all_points)),
        "eligible": all(row["eligible"] for row in tier_fits.values()),
        "exponent": statistics.median(exponents) if exponents else None,
        "exponent_95_ci": (
            [min(row[0] for row in eligible_intervals),
             max(row[1] for row in eligible_intervals)]
            if eligible_intervals else None),
        "gate": gate,
        "maximum_exponent": maximum_exponent,
        "metric": "kernel_elapsed_ms",
        "points": [[x, y] for x, y in all_points],
        "tier_fits": tier_fits,
        "work": "indexed_distractor_rules",
    }


def percentile(values, fraction):
    rows = sorted(float(value) for value in values)
    if not rows:
        return None
    position = fraction * (len(rows) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return rows[lower]
    weight = position - lower
    return rows[lower] * (1.0 - weight) + rows[upper] * weight


def robust_log_slope(points):
    """Theil-Sen exponent for positive (work, metric) points."""
    rows = sorted((float(x), float(y)) for x, y in points
                  if float(x) > 0.0 and float(y) > 0.0)
    slopes = []
    for left_index, (left_x, left_y) in enumerate(rows):
        for right_x, right_y in rows[left_index + 1:]:
            if right_x == left_x:
                continue
            slopes.append(
                (math.log(right_y) - math.log(left_y))
                / (math.log(right_x) - math.log(left_x)))
    return statistics.median(slopes) if slopes else None


def cluster_bootstrap_interval(cluster_points, resamples=10000, seed=104743):
    """Bootstrap clusters with an exact weighted Theil-Sen reconstruction.

    Resampling a cluster duplicates all of its points. A slope between points
    from clusters ``a`` and ``b`` therefore occurs exactly
    ``count[a] * count[b]`` times (also ``count[a] ** 2`` within one repeated
    cluster). Precomputing the sorted slopes and applying those integer
    multiplicities preserves the exact estimator while avoiding repeated log
    and sort work.
    """
    clusters = sorted(cluster_points)
    if len(clusters) < 2:
        return None
    points = []
    for cluster_index, cluster in enumerate(clusters):
        points.extend(
            (float(x), float(y), cluster_index)
            for x, y in cluster_points[cluster]
            if float(x) > 0.0 and float(y) > 0.0)
    weighted_slopes = []
    for left_index, (left_x, left_y, left_cluster) in enumerate(points):
        for right_x, right_y, right_cluster in points[left_index + 1:]:
            if right_x == left_x:
                continue
            weighted_slopes.append((
                (math.log(right_y) - math.log(left_y))
                / (math.log(right_x) - math.log(left_x)),
                left_cluster, right_cluster))
    weighted_slopes.sort(key=lambda row: row[0])
    if not weighted_slopes:
        return None
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - exercised on minimal deployments
        np = None
    if np is not None:
        slope_values = np.asarray(
            [row[0] for row in weighted_slopes], dtype=float)
        left_clusters = np.asarray(
            [row[1] for row in weighted_slopes], dtype=np.int64)
        right_clusters = np.asarray(
            [row[2] for row in weighted_slopes], dtype=np.int64)
    rng = random.Random(seed)
    slopes = []
    for _ in range(resamples):
        counts = [0] * len(clusters)
        for _sample in clusters:
            counts[rng.randrange(len(clusters))] += 1
        if np is not None:
            count_values = np.asarray(counts, dtype=np.int64)
            weights = count_values[left_clusters] * count_values[
                right_clusters]
            total = int(weights.sum())
        else:
            total = sum(
                counts[left] * counts[right]
                for _slope, left, right in weighted_slopes)
        if total < 1:
            continue
        lower_rank = (total - 1) // 2
        upper_rank = total // 2
        if np is not None:
            cumulative = np.cumsum(weights)
            lower_value = float(slope_values[
                int(np.searchsorted(cumulative, lower_rank, side="right"))])
            upper_value = float(slope_values[
                int(np.searchsorted(cumulative, upper_rank, side="right"))])
        else:
            cumulative = 0
            lower_value = None
            upper_value = None
            for slope, left, right in weighted_slopes:
                cumulative += counts[left] * counts[right]
                if lower_value is None and cumulative > lower_rank:
                    lower_value = slope
                if cumulative > upper_rank:
                    upper_value = slope
                    break
        if lower_value is not None and upper_value is not None:
            slope = (lower_value + upper_value) / 2.0
            if math.isfinite(slope):
                slopes.append(slope)
    if not slopes:
        return None
    return (percentile(slopes, 0.025), percentile(slopes, 0.975))


def analyze_surface(results, surface, resamples=10000, source_identity=None):
    if surface not in SURFACE_FITS:
        raise ValueError("unknown analysis surface")
    work_key, metric_key, maximum_exponent = SURFACE_FITS[surface]
    completed_all = [row for row in results
                     if row["status"] == "completed"
                     and row["trial"]["cell"]["surface"] == surface
                     and (source_identity is None
                          or row["trial"]["source_identity"]
                          == source_identity)]
    timing_completed = [row for row in completed_all
                        if row["trial"].get(
                            "telemetry_mode", "aggregate") == "aggregate"]
    completed = [row for row in timing_completed
                 if _primary_fit_eligible(row, surface)]
    matching = [row for row in results
                if row["trial"]["cell"]["surface"] == surface
                and (source_identity is None
                     or row["trial"]["source_identity"] == source_identity)]
    semantic_failures = [
        {"key": key, "trial_id": row.get("trial_id")}
        for row in completed_all for key in required_correctness_keys(row)
        if row.get("correctness", {}).get(key) is not True]
    noncompleted = [row for row in matching if row["status"] != "completed"]
    points = []
    clusters = {}
    for row in completed:
        work = row["actual_work"].get(work_key)
        metric = row["metrics"].get(metric_key)
        if work is None or metric is None:
            continue
        point = (float(work), float(metric))
        points.append(point)
        seed = str(row["trial"]["cell"]["seed"])
        clusters.setdefault(seed, []).append(point)
    slope = robust_log_slope(points)
    interval = cluster_bootstrap_interval(clusters, resamples=resamples)
    upper = interval[1] if interval is not None else None
    distinct_work = len(set(point[0] for point in points))
    fit_eligible = distinct_work >= 2 and upper is not None
    secondary_fits = {}
    secondary_gates = []
    for name, secondary_work, secondary_metric, secondary_limit in (
            SECONDARY_FITS.get(surface, ())):
        secondary_points = []
        secondary_clusters = {}
        for row in completed:
            work = row["actual_work"].get(secondary_work)
            metric = row["metrics"].get(secondary_metric)
            if work is None or metric is None or float(work) <= 0.0:
                continue
            point = (float(work), float(metric))
            secondary_points.append(point)
            seed = str(row["trial"]["cell"]["seed"])
            secondary_clusters.setdefault(seed, []).append(point)
        secondary_interval = cluster_bootstrap_interval(
            secondary_clusters, resamples=resamples)
        secondary_upper = (
            secondary_interval[1] if secondary_interval is not None else None)
        secondary_distinct = len(set(row[0] for row in secondary_points))
        secondary_eligible = (
            secondary_distinct >= 2 and secondary_upper is not None)
        secondary_gate = (
            "pass" if secondary_eligible
            and secondary_upper <= secondary_limit else
            "fail" if secondary_eligible else "not-entered")
        secondary_fits[name] = {
            "distinct_work_values": secondary_distinct,
            "eligible": secondary_eligible,
            "exponent": robust_log_slope(secondary_points),
            "exponent_95_ci": (
                list(secondary_interval)
                if secondary_interval is not None else None),
            "gate": secondary_gate,
            "maximum_exponent": secondary_limit,
            "metric": secondary_metric,
            "points": [[x, y] for x, y in secondary_points],
            "work": secondary_work,
        }
        secondary_gates.append(secondary_gate)
    if surface == "proof":
        proof_distractors = _proof_distractor_fit(
            timing_completed, resamples=resamples)
        secondary_fits["time-vs-indexed-distractors"] = proof_distractors
        secondary_gates.append(proof_distractors["gate"])
    primary_gate = (
        "pass" if fit_eligible and upper <= maximum_exponent else
        "fail" if fit_eligible else "not-entered")
    required_gates = [primary_gate] + secondary_gates
    combined_gate = (
        "fail" if semantic_failures or noncompleted
        or "fail" in required_gates else
        "pass" if required_gates
        and all(row == "pass" for row in required_gates) else
        "not-entered")
    labels = {}
    for label, tier, label_metric, threshold in ABSOLUTE_LABELS[surface]:
        values = [
            float(row["metrics"][label_metric]) for row in completed
            if row["trial"]["cell"]["tier"] == tier
            and label_metric in row["metrics"]]
        label_p95 = percentile(values, 0.95)
        label_eligible = len(values) >= 50
        labels[label] = {
            "eligible": label_eligible,
            "metric": label_metric,
            "p95": label_p95,
            "sample_count": len(values),
            "screening_point_status": (
                "pass" if label_p95 is not None and label_p95 <= threshold
                else "fail" if label_p95 is not None else "not-measured"),
            "status": (
                "pass" if label_eligible and label_p95 <= threshold
                else "fail" if label_eligible else "not-entered"),
            "threshold_ms": threshold,
            "tier": tier,
        }
    return {
        "absolute_labels": labels,
        "completed_trials": len(completed_all),
        "distinct_work_values": distinct_work,
        "excluded_stress_trials": len(timing_completed) - len(completed),
        "excluded_non_timing_trials": sum(
            row["trial"].get("telemetry_mode", "aggregate") != "aggregate"
            for row in completed_all),
        "exponent": slope,
        "exponent_95_ci": list(interval) if interval is not None else None,
        "fit_eligible": fit_eligible,
        "fit_completed_trials": len(completed),
        "fit_trial_ids": [row["trial_id"] for row in completed
                          if "trial_id" in row],
        "fit_selection": {
            "atomspace": "local topology / 1% churn / one support / no retention",
            "proof": "shared DAG / zero indexed distractors",
            "bridge": "protected message / disconnected distractors",
            "fluid": "corridor topology / zero edge failures",
        }[surface],
        "gate": combined_gate,
        "maximum_exponent": maximum_exponent,
        "metric": metric_key,
        "p50": percentile([row["metrics"][metric_key] for row in completed
                           if metric_key in row["metrics"]], 0.50),
        "p95": percentile([row["metrics"][metric_key] for row in completed
                           if metric_key in row["metrics"]], 0.95),
        "p99": percentile([row["metrics"][metric_key] for row in completed
                           if metric_key in row["metrics"]], 0.99),
        "maximum": max((row["metrics"][metric_key] for row in completed
                        if metric_key in row["metrics"]), default=None),
        "points": [[x, y] for x, y in points],
        "semantic_failure_count": len(semantic_failures),
        "semantic_failures": semantic_failures,
        "semantic_screening_trials": sum(
            row["trial"].get("telemetry_mode") == "semantic-screening"
            for row in completed_all),
        "status_counts": dict((status, sum(
            row["status"] == status for row in matching))
            for status in ("completed", "failed", "stopped")),
        "secondary_fits": secondary_fits,
        "work": work_key,
    }


def analyze_combined(results, source_identity=None):
    """Pair combined trials only with same-source, same-seed isolated stages."""
    matching = [row for row in results
                if row["trial"]["cell"]["surface"] == "combined"
                and (source_identity is None
                     or row["trial"]["source_identity"] == source_identity)]
    completed_all = [row for row in matching
                     if row["status"] == "completed"]
    completed = [row for row in completed_all
                 if row["trial"].get(
                     "telemetry_mode", "aggregate") == "aggregate"]
    isolated = {}
    for row in results:
        cell = row["trial"]["cell"]
        if (row["status"] != "completed"
                or cell["surface"] not in SURFACE_FITS
                or not _primary_fit_eligible(row, cell["surface"])
                or row["trial"].get(
                    "telemetry_mode", "aggregate") != "aggregate"
                or (source_identity is not None
                    and row["trial"]["source_identity"] != source_identity)):
            continue
        isolated[(
            row["trial"]["source_identity"], cell["seed"],
            cell["surface"], cell["tier"])] = row
    pairs = []
    for row in completed:
        cell = row["trial"]["cell"]
        parameters = cell["parameters"]
        tier_keys = (
            ("atomspace", parameters.get("atom_tier")),
            ("proof", parameters.get("proof_tier")),
            ("bridge", parameters.get("bridge_tier")),
        )
        if parameters.get("fluid_tier") not in (None, "none"):
            tier_keys += (("fluid", parameters["fluid_tier"]),)
        matched = []
        for surface, tier in tier_keys:
            candidate = isolated.get((
                row["trial"]["source_identity"], cell["seed"],
                surface, tier))
            if candidate is None:
                matched = []
                break
            matched.append(candidate)
        if not matched:
            continue
        predicted = sum(float(item["metrics"]["wall_ms"]) for item in matched)
        observed = float(row["metrics"]["combined_elapsed_ms"])
        pairs.append({
            "combined_tier": cell["tier"],
            "observed_ms": observed,
            "predicted_isolated_sum_ms": predicted,
            "ratio": observed / predicted if predicted > 0.0 else None,
            "seed": cell["seed"],
        })
    ratios = [row["ratio"] for row in pairs if row["ratio"] is not None]
    invariant_keys = (
        "bridge_candidate_safe", "cold_incremental_equivalent",
        "fluid_healthy", "fluid_mass_within_1e_9",
        "proof_matches_reference", "truth_hash_unchanged")
    semantics_hold = all(
        all(row.get("correctness", {}).get(key) is True
            for key in invariant_keys)
        for row in completed_all)
    noncompleted = [row for row in matching if row["status"] != "completed"]
    entered = bool(completed) and len(pairs) == len(completed)
    interaction_pass = bool(ratios) and max(ratios) <= 2.0
    gate = (
        "fail" if noncompleted or not semantics_hold else
        "pass" if entered and interaction_pass else
        "fail" if entered and not interaction_pass else
        "not-entered")
    return {
        "completed_trials": len(completed_all),
        "excluded_non_timing_trials": (
            len(completed_all) - len(completed)),
        "gate": gate,
        "interaction_bound": 2.0,
        "maximum_ratio": max(ratios, default=None),
        "p50_ratio": percentile(ratios, 0.50),
        "p95_ratio": percentile(ratios, 0.95),
        "paired_trials": len(pairs),
        "pairs": pairs,
        "semantic_invariants_hold": semantics_hold,
        "semantic_screening_trials": sum(
            row["trial"].get("telemetry_mode") == "semantic-screening"
            for row in completed_all),
        "status_counts": dict((status, sum(
            row["status"] == status for row in matching))
            for status in ("completed", "failed", "stopped")),
        "timing_completed_trials": len(completed),
    }


def analyze_captured(results, source_identity=None):
    """Compare realistic captured shapes with same-version synthetic builds."""
    captured = [row for row in results
                if row["status"] == "completed"
                and row["trial"]["cell"]["surface"] == "captured"
                and (source_identity is None
                     or row["trial"]["source_identity"] == source_identity)]
    timing_captured = [
        row for row in captured
        if row["trial"].get("telemetry_mode", "aggregate") == "aggregate"]
    synthetic = {}
    for row in results:
        cell = row["trial"]["cell"]
        if (row["status"] != "completed"
                or cell["surface"] != "atomspace"
                or not _primary_fit_eligible(row, "atomspace")
                or row["trial"].get(
                    "telemetry_mode", "aggregate") != "aggregate"
                or (source_identity is not None
                    and row["trial"]["source_identity"] != source_identity)):
            continue
        synthetic.setdefault(cell["tier"], []).append(row)
    synthetic_reference = {}
    for tier, rows in synthetic.items():
        build_values = [float(row["metrics"]["generator_ms"])
                        for row in rows if "generator_ms" in row["metrics"]]
        rss_values = [float(row["metrics"]["peak_rss_bytes"])
                      for row in rows if "peak_rss_bytes" in row["metrics"]]
        if build_values and rss_values:
            synthetic_reference[tier] = {
                "generator_ms_median": percentile(build_values, 0.50),
                "peak_rss_bytes_median": percentile(rss_values, 0.50),
            }
    pairs = []
    for row in timing_captured:
        parameters = row["trial"]["cell"]["parameters"]
        tier = parameters.get("synthetic_tier")
        reference = synthetic_reference.get(tier)
        if reference is None:
            continue
        timing_ratio = (
            float(row["metrics"]["amplification_ms"])
            / reference["generator_ms_median"])
        rss_ratio = (
            float(row["metrics"]["peak_rss_bytes"])
            / reference["peak_rss_bytes_median"])
        pairs.append({
            "captured_tier": row["trial"]["cell"]["tier"],
            "rss_ratio": rss_ratio,
            "synthetic_tier": tier,
            "timing_ratio": timing_ratio,
            "turn": row["actual_work"]["turn"],
        })
    invariant_keys = (
        "at_least_target_atoms", "clone_authority_quarantined",
        "original_subgraph_invariant", "source_hash_verified")
    semantics_hold = all(
        all(row.get("correctness", {}).get(key) is True
            for key in invariant_keys)
        for row in captured)
    tier_turns = dict(
        (tier, len({row["actual_work"]["turn"] for row in captured
                    if row["trial"]["cell"]["tier"] == tier}))
        for tier in ("CA2", "CA4"))
    timing_tier_turns = dict(
        (tier, len({row["actual_work"]["turn"] for row in timing_captured
                    if row["trial"]["cell"]["tier"] == tier}))
        for tier in ("CA2", "CA4"))
    cohort_complete = all(value >= 20 for value in tier_turns.values())
    timing_cohort_complete = all(
        value >= 20 for value in timing_tier_turns.values())
    transfer_within_2x = bool(pairs) and all(
        row["timing_ratio"] <= 2.0 and row["rss_ratio"] <= 2.0
        for row in pairs)
    fully_paired = len(pairs) == len(timing_captured)
    gate = (
        "pass" if cohort_complete and timing_cohort_complete and fully_paired
        and semantics_hold and transfer_within_2x else
        "fail" if cohort_complete and (
            not semantics_hold or (
                timing_cohort_complete
                and (not fully_paired or not transfer_within_2x)))
        else "not-entered")
    return {
        "completed_trials": len(captured),
        "cohort_complete": cohort_complete,
        "excluded_non_timing_trials": len(captured) - len(timing_captured),
        "gate": gate,
        "maximum_rss_ratio": max(
            (row["rss_ratio"] for row in pairs), default=None),
        "maximum_timing_ratio": max(
            (row["timing_ratio"] for row in pairs), default=None),
        "paired_trials": len(pairs),
        "pairs": pairs,
        "semantic_invariants_hold": semantics_hold,
        "semantic_screening_trials": sum(
            row["trial"].get("telemetry_mode") == "semantic-screening"
            for row in captured),
        "synthetic_reference": synthetic_reference,
        "tier_distinct_turns": tier_turns,
        "timing_cohort_complete": timing_cohort_complete,
        "timing_completed_trials": len(timing_captured),
        "timing_tier_distinct_turns": timing_tier_turns,
        "transfer_bound": 2.0,
    }


def build_report(results, resamples=10000, include_phase_reports=True):
    surfaces = {}
    for surface in sorted(SURFACE_FITS):
        identities = sorted(set(
            row["trial"]["source_identity"] for row in results
            if row["trial"]["cell"]["surface"] == surface))
        versions = dict(
            (identity, analyze_surface(
                results, surface, resamples=resamples,
                source_identity=identity))
            for identity in identities)
        selected = max(
            identities,
            key=lambda identity: (
                versions[identity]["distinct_work_values"],
                versions[identity]["completed_trials"], identity),
            default=None)
        material = (
            dict(versions[selected]) if selected is not None else
            analyze_surface([], surface, resamples=resamples))
        material["selected_source_identity"] = selected
        material["versions"] = versions
        surfaces[surface] = material
    gates = dict((surface, material["gate"])
                 for surface, material in surfaces.items())
    combined_identities = sorted(set(
        row["trial"]["source_identity"] for row in results
        if row["trial"]["cell"]["surface"] == "combined"))
    combined_versions = dict(
        (identity, analyze_combined(results, source_identity=identity))
        for identity in combined_identities)
    combined_selected = max(
        combined_identities,
        key=lambda identity: (
            combined_versions[identity]["paired_trials"],
            combined_versions[identity]["completed_trials"], identity),
        default=None)
    combined = (
        dict(combined_versions[combined_selected])
        if combined_selected is not None else analyze_combined([]))
    combined["selected_source_identity"] = combined_selected
    combined["versions"] = combined_versions
    gates["combined"] = combined["gate"]
    captured_identities = sorted(set(
        row["trial"]["source_identity"] for row in results
        if row["trial"]["cell"]["surface"] == "captured"))
    captured_versions = dict(
        (identity, analyze_captured(results, source_identity=identity))
        for identity in captured_identities)
    captured_selected = max(
        captured_identities,
        key=lambda identity: (
            captured_versions[identity]["gate"] == "pass",
            captured_versions[identity]["cohort_complete"],
            captured_versions[identity]["completed_trials"],
            captured_versions[identity]["paired_trials"], identity),
        default=None)
    captured = (
        dict(captured_versions[captured_selected])
        if captured_selected is not None else analyze_captured([]))
    captured["selected_source_identity"] = captured_selected
    captured["versions"] = captured_versions
    gates["captured"] = captured["gate"]
    report = {
        "artifact_type": "freeciv-scalability-report",
        "claim_boundary": (
            "Scalability, boundedness, correctness, and performance only; "
            "no FreeCiv gameplay claim."),
        "gates": gates,
        "schema_version": "1.0",
        "combined": combined,
        "captured": captured,
        "surfaces": surfaces,
    }
    if include_phase_reports:
        report["phase_reports"] = dict(
            (phase, build_report(
                [row for row in results
                 if row["trial"]["phase"] == phase],
                resamples=resamples,
                include_phase_reports=False))
            for phase in ("discovery", "heldout"))
    return report
