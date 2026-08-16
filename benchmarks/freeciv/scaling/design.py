"""Preregistered, bounded campaign matrices for the scalability surfaces."""

import itertools
import math


DESIGNS = frozenset(("tier", "primary"))

ATOMSPACE_PRIMARY_TOPOLOGIES = (
    "local", "chain", "hub", "balanced_tree", "shared_dag",
    "distractor_shards", "mixed")
ATOMSPACE_PRIMARY_CHURN = (0.001, 0.01, 0.05, 0.20, 1.0)
ATOMSPACE_PRIMARY_SUPPORTS = (1, 2, 4)
PROOF_PRIMARY_SHAPES = (
    "chain", "and_tree", "shared_dag", "diamond_50", "diamond_90",
    "or_one_success", "or_several_success", "or_unreachable",
    "cycle_alternate", "cycle_only", "grounded_blocker", "binding_heavy")
PROOF_DISTRACTOR_ENVELOPES = {
    "P0": 0,
    "P1": 10000,
    "P2": 25000,
    "P3": 100000,
    "P4": 250000,
}
BRIDGE_PRIMARY_ARMS = (
    "scalar_pf_v2", "protected_message", "corrected_probe",
    "path_persistence", "source_sink_flow")
BRIDGE_PRIMARY_TOPOLOGIES = (
    "sparse_dag", "shared_dag", "cyclic",
    "disconnected_distractors", "asymmetric_legality", "bottleneck",
    "dynamic_failure")
FLUID_PRIMARY_FAILURE_FRACTIONS = (0.0, 0.01, 0.10)


def _require_subset(values, allowed, name):
    unknown = sorted(set(values).difference(allowed))
    if unknown:
        raise ValueError("unknown {}: {}".format(name, unknown[0]))


def _require_fraction(values, name, include_zero):
    for value in values:
        number = float(value)
        if (not math.isfinite(number) or number > 1.0 or number < 0.0
                or (not include_zero and number == 0.0)):
            raise ValueError("{} must be in {}".format(
                name, "[0,1]" if include_zero else "(0,1]"))


def _deduplicate(rows):
    result = []
    seen = set()
    for row in rows:
        identity = tuple(sorted(row.items()))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(dict(row))
    return tuple(result)


def primary_variants(surface, tier, seed_index=0):
    """Return the fixed non-Cartesian discovery variants for one tier.

    The primary design varies one AtomSpace stress dimension at a time. This
    avoids treating a very large Cartesian product as the preregistered sweep.
    Proof, bridge, and fluid variants are the explicit semantic families or
    mechanism arms required by their gates.
    """
    if surface == "atomspace":
        rows = [{
            "churn_fraction": 0.01,
            "support_multiplicity": 1,
            "topology": "local",
        }]
        if tier in ("A2", "A4"):
            rows.extend({
                "churn_fraction": churn,
                "support_multiplicity": 1,
                "topology": "local",
            } for churn in ATOMSPACE_PRIMARY_CHURN if churn != 0.01)
            rows.extend({
                "churn_fraction": 0.01,
                "support_multiplicity": multiplicity,
                "topology": "local",
            } for multiplicity in ATOMSPACE_PRIMARY_SUPPORTS if multiplicity != 1)
            rows.extend({
                "churn_fraction": 0.01,
                "support_multiplicity": 1,
                "topology": topology,
            } for topology in ATOMSPACE_PRIMARY_TOPOLOGIES if topology != "local")
        if tier == "A0" and seed_index == 0:
            rows.append({
                "churn_fraction": 0.01,
                "retention_cycles": 100,
                "revision_retention": 4,
                "support_multiplicity": 1,
                "topology": "local",
            })
        return _deduplicate(rows)
    if surface == "proof":
        rows = [{"shape": shape} for shape in PROOF_PRIMARY_SHAPES]
        # Fixed relevant work crossed with four distractor levels identifies
        # the H2 distractor effect without confounding it with proof size.
        envelope = PROOF_DISTRACTOR_ENVELOPES.get(tier, 0)
        if envelope:
            rows.extend({
                "shape": "shared_dag",
                "distractor_count": int(round(envelope * fraction)),
            } for fraction in (0.0, 0.25, 0.50))
        return _deduplicate(rows)
    if surface == "bridge":
        arms = (
            ("scalar_pf_v2", "protected_message", "path_persistence")
            if tier == "B4" else BRIDGE_PRIMARY_ARMS)
        return tuple({"arm": arm, "topology": topology}
                     for arm, topology in itertools.product(
                         arms,
                         BRIDGE_PRIMARY_TOPOLOGIES))
    if surface == "fluid":
        rows = [{"failure_fraction": value, "topology": "corridor"}
                for value in FLUID_PRIMARY_FAILURE_FRACTIONS]
        rows.extend({
            "average_degree": degree,
            "failure_fraction": 0.0,
            "topology": "sparse_dag",
        } for degree in (2, 4, 8))
        rows.extend({
            "average_degree": 4,
            "failure_fraction": value,
            "topology": "sparse_dag",
        } for value in (0.01, 0.10))
        return _deduplicate(rows)
    if surface in ("combined", "captured"):
        return ({},)
    raise ValueError("unknown scaling surface")


def timing_variant(surface):
    """Canonical aggregate-telemetry variant used by absolute p95 labels."""
    if surface == "atomspace":
        return {"churn_fraction": 0.01, "support_multiplicity": 1,
                "topology": "local"}
    if surface == "proof":
        return {"distractor_count": 0, "shape": "shared_dag"}
    if surface == "bridge":
        return {"arm": "protected_message",
                "topology": "disconnected_distractors"}
    if surface == "fluid":
        return {"failure_fraction": 0.0, "topology": "corridor"}
    raise ValueError("surface has no isolated timing variant")


def explicit_variants(surface, **selections):
    """Build a user-requested matrix with strict surface-specific fields."""
    if surface == "atomspace":
        topologies = selections.get("atom_topologies") or ("local",)
        churn = selections.get("churn_fractions") or (0.01,)
        supports = selections.get("support_multiplicities") or (1,)
        _require_subset(
            topologies, ATOMSPACE_PRIMARY_TOPOLOGIES, "atom topology")
        _require_fraction(churn, "churn fraction", include_zero=False)
        if any(isinstance(value, bool) or not isinstance(value, int)
               or value < 1 for value in supports):
            raise ValueError("support multiplicity must be positive")
        return tuple({
            "churn_fraction": churn,
            "support_multiplicity": support,
            "topology": topology,
        } for topology, churn, support in itertools.product(
            topologies, churn, supports))
    if surface == "proof":
        shapes = selections.get("proof_shapes") or ("and_tree",)
        distractor_counts = selections.get("distractor_counts") or (None,)
        _require_subset(shapes, PROOF_PRIMARY_SHAPES, "proof shape")
        if any(value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
                or value < 0)
                for value in distractor_counts):
            raise ValueError("distractor count must be nonnegative")
        return tuple({"shape": shape, **(
            {"distractor_count": distractors}
            if distractors is not None else {})}
            for shape, distractors in itertools.product(
                shapes, distractor_counts))
    if surface == "bridge":
        arms = selections.get("arms") or ("protected_message",)
        topologies = (selections.get("bridge_topologies")
                      or ("disconnected_distractors",))
        _require_subset(arms, BRIDGE_PRIMARY_ARMS, "bridge arm")
        _require_subset(
            topologies, BRIDGE_PRIMARY_TOPOLOGIES, "bridge topology")
        return tuple({"arm": arm, "topology": topology}
                     for arm, topology in itertools.product(
                         arms, topologies))
    if surface == "fluid":
        fractions = selections.get("failure_fractions") or (0.0,)
        _require_fraction(
            fractions, "failure fraction", include_zero=True)
        return tuple({"failure_fraction": value, "topology": "corridor"}
                     for value in fractions)
    if surface in ("combined", "captured"):
        return ({},)
    raise ValueError("unknown scaling surface")


def design_variants(surface, tier, design="tier", seed_index=0, **selections):
    if design not in DESIGNS:
        raise ValueError("unknown campaign design")
    explicitly_selected = any(value is not None for value in selections.values())
    if explicitly_selected:
        return explicit_variants(surface, **selections)
    if design == "primary":
        return primary_variants(surface, tier, seed_index=seed_index)
    return explicit_variants(surface)
