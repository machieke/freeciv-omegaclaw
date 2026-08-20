"""Conservative held-out-only claim and planned-cell accounting manifest."""

from collections import defaultdict

from freeciv_agent.events.schema import structural_hash


_CORRECTNESS_KEYS = {
    "atomspace": (
        "cold_incremental_equivalent", "count_exact",
        "synthetic_namespace_only"),
    "proof": ("matches_reference",),
    "bridge": (
        "expected_bridge_recalled", "scalar_order_preserved",
        "scalar_winner_recalled", "truth_hash_unchanged"),
    "fluid": (
        "edge_updates_exact", "healthy", "mass_error_within_1e_9"),
    "combined": (
        "bridge_candidate_safe", "cold_incremental_equivalent",
        "fluid_healthy", "fluid_mass_within_1e_9",
        "proof_matches_reference", "truth_hash_unchanged"),
    "captured": (
        "at_least_target_atoms", "clone_authority_quarantined",
        "original_subgraph_invariant", "source_hash_verified"),
}


def _payload_key(row):
    return structural_hash({
        "parameters": row["parameters"],
        "seed": int(row["seed"]),
        "surface": row["surface"],
        "tier": row["tier"],
    })


def _result_payload(result):
    cell = result["trial"]["cell"]
    return {
        "parameters": cell["parameters"],
        "seed": cell["seed"],
        "surface": cell["surface"],
        "tier": cell["tier"],
    }


def _semantic_cell(row):
    parameters = row["parameters"]
    return structural_hash({
        "arm": parameters.get("arm", "kernel"),
        "topology": parameters.get("topology", "default"),
        "tier": row["tier"],
    })


def _tier_sort(value):
    digits = "".join(character for character in str(value)
                     if character.isdigit())
    return (int(digits) if digits else -1, str(value))


def build_claim_manifest(results, audit, frozen=None):
    """Authorize only claims backed by complete preregistered held-out cells."""
    heldout = [row for row in results if row["trial"]["phase"] == "heldout"]
    result_by_key = dict(
        (_payload_key(_result_payload(row)), row) for row in heldout)
    planned = [] if frozen is None else list(frozen.get("payloads", ()))
    accounting = []
    planned_by_surface_tier = defaultdict(list)
    for payload in planned:
        key = _payload_key(payload)
        result = result_by_key.get(key)
        status = "not-entered" if result is None else result["status"]
        accounting.append({
            "payload_id": payload.get("payload_id"),
            "status": status,
            "surface": payload["surface"],
            "tier": payload["tier"],
            "trial_id": None if result is None else result["trial_id"],
        })
        planned_by_surface_tier[(
            payload["surface"], payload["tier"])].append((payload, result))
    heldout_report = audit["report"]["phase_reports"]["heldout"]
    surface_claims = {}
    for surface in _CORRECTNESS_KEYS:
        tier_claims = []
        for (candidate_surface, tier), rows in sorted(
                planned_by_surface_tier.items(),
                key=lambda item: (item[0][0], _tier_sort(item[0][1]))):
            if candidate_surface != surface:
                continue
            results_for_tier = [row for _payload, row in rows
                                if row is not None]
            all_completed = (
                len(results_for_tier) == len(rows)
                and all(row["status"] == "completed"
                        for row in results_for_tier))
            semantics_hold = all(
                all(row.get("correctness", {}).get(key) is True
                    for key in _CORRECTNESS_KEYS[surface])
                for row in results_for_tier)
            by_semantic_cell = defaultdict(set)
            for payload, result in rows:
                if result is not None and result["status"] == "completed":
                    by_semantic_cell[_semantic_cell(payload)].add(
                        int(payload["seed"]))
            minimum = 20 if surface == "captured" else 40
            sample_complete = bool(by_semantic_cell) and all(
                len(seeds) >= minimum
                for seeds in by_semantic_cell.values())
            if all_completed and semantics_hold and sample_complete:
                tier_claims.append(tier)
        fit = heldout_report.get("surfaces", {}).get(surface, {})
        absolute = fit.get("absolute_labels", {})
        surface_claims[surface] = {
            "correct_at_scale_tiers": tier_claims,
            "live_capable_labels": sorted(
                name for name, row in absolute.items()
                if row.get("status") == "pass" and "live-capable" in name),
            "research_usable_labels": sorted(
                name for name, row in absolute.items()
                if row.get("status") == "pass"
                and "research-usable" in name),
            "scales_predictably": bool(
                tier_claims and fit.get("gate") == "pass"),
        }
    special_gates = {
        "G6-combined": heldout_report.get(
            "combined", {}).get("gate", "not-entered"),
        "G7-captured": heldout_report.get(
            "captured", {}).get("gate", "not-entered"),
        "G8-engine": audit["report"].get(
            "engine_shadow", {}).get("gate", "not-entered"),
    }
    all_accounted = bool(accounting) and all(
        row["status"] != "not-entered" for row in accounting)
    required_gate_decisions = tuple(
        heldout_report.get("gates", {}).get(
            surface, "not-entered")
        for surface in ("atomspace", "proof", "bridge", "fluid")) + (
        special_gates["G6-combined"],
        special_gates["G7-captured"],
        special_gates["G8-engine"],
    )
    all_gates_decided = all(
        value in ("pass", "fail") for value in required_gate_decisions)
    material = {
        "artifact_type": "freeciv-scalability-claim-manifest",
        "cell_accounting": accounting,
        "claim_boundary": (
            "Scalability, boundedness, correctness, and performance only; "
            "no FreeCiv gameplay, score, or win-rate claim."),
        "frozen": frozen is not None,
        "frozen_source_identity": (
            None if frozen is None else frozen.get("source_identity")),
        "g9_complete": bool(
            audit.get("valid") and all_accounted and all_gates_decided),
        "required_gate_decisions": list(required_gate_decisions),
        "heldout_result_count": len(heldout),
        "negative_and_null_results_retained": True,
        "schema_version": "1.0",
        "special_gates": special_gates,
        "surface_claims": surface_claims,
    }
    material["claim_manifest_hash"] = structural_hash(material)
    return material
