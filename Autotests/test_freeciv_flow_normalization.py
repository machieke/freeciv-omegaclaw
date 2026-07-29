"""Stage-S4 normalization, units, and turnover contracts."""

import os
import sys
from dataclasses import replace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    RobustNormalizer,
    default_normalization_contract,
)


def test_raw_probe_count_does_not_change_requested_current_amplitude():
    normalizer = RobustNormalizer()
    semantic = normalizer.normalize(
        (1.0, -0.5, 0.25),
        "typed_advantage", "semantic")
    paths = (
        (1.0, 0.0, -1.0),
        (0.0, 1.0, -1.0),
    )
    first_probe = normalizer.mean_probe_direction(paths)
    duplicated_probe = normalizer.mean_probe_direction(
        paths * 50)

    first = normalizer.mix(
        semantic, first_probe, 0.5, 0.5)
    duplicated = normalizer.mix(
        semantic, duplicated_probe, 0.5, 0.5)

    assert first_probe == duplicated_probe
    assert first.velocity == duplicated.velocity
    assert first.turnover_rate == duplicated.turnover_rate


def test_normalization_contract_hash_changes_on_scientific_identity():
    contract = default_normalization_contract()

    changed_scale = replace(
        contract,
        robust_scale_policy="interquartile-range")
    changed_turnover = replace(
        contract, turnover_fraction=0.20)
    changed_packet = replace(
        contract,
        packet_quanta=(("action", 1), ("cpu", 2)))
    changed_sign = replace(
        contract,
        sign_convention="positive-sink-to-source")

    assert len({
        contract.contract_hash,
        changed_scale.contract_hash,
        changed_turnover.contract_hash,
        changed_packet.contract_hash,
        changed_sign.contract_hash,
    }) == 5


def test_missing_or_degenerate_scale_uses_declared_fallback():
    normalizer = RobustNormalizer()

    sparse = normalizer.robust_scale(
        "edge_cost", (2.0,))
    degenerate = normalizer.robust_scale(
        "risk", (0.5, 0.5, 0.5))

    assert sparse.fallback_used
    assert sparse.value == 1.0
    assert degenerate.fallback_used
    assert degenerate.value == 1.0
    with pytest.raises(ValueError, match="fallback"):
        normalizer.robust_scale(
            "undeclared-field", (1.0, 2.0, 3.0))


def test_semantic_and_probe_directions_are_unit_normalized_before_mixing():
    normalizer = RobustNormalizer()
    semantic = normalizer.normalize(
        (20.0, -10.0, 5.0),
        "typed_advantage", "teleological-semantic")
    probe = normalizer.mean_probe_direction((
        (3.0, 4.0, 0.0),
        (3.0, 4.0, 0.0),
    ))

    mixed = normalizer.mix(
        semantic, probe, 0.7, 0.3)

    assert semantic.norm == pytest.approx(1.0)
    assert probe.norm == pytest.approx(1.0)
    assert dict(mixed.input_norms) == pytest.approx({
        "probe": 1.0, "semantic": 1.0})
    assert sum(
        value * value
        for value in mixed.unit_values) == pytest.approx(1.0)
    assert mixed.normalization_contract_hash == (
        normalizer.contract.contract_hash)


def test_turnover_fraction_bounds_local_raw_cfl():
    contract = replace(
        default_normalization_contract(),
        turnover_fraction=0.25)
    normalizer = RobustNormalizer(contract)
    semantic = normalizer.normalize(
        (1.0, 0.0, 0.0),
        "typed_advantage", "semantic")
    probe = normalizer.mean_probe_direction((
        (0.0, 1.0, 0.0),))

    full = normalizer.mix(
        semantic, probe, 0.5, 0.5,
        outer_packet_allocation=1.0)
    half = normalizer.mix(
        semantic, probe, 0.5, 0.5,
        outer_packet_allocation=0.5)

    assert full.turnover_rate == 0.25
    assert full.raw_cfl_bound <= 0.25
    assert half.turnover_rate == 0.125
    assert half.raw_cfl_bound <= 0.125


def test_bridge_height_and_hydraulic_dual_have_distinct_scales():
    contract = default_normalization_contract()
    fields = dict(contract.fallback_scales)

    assert "bridge_height_difference" in fields
    assert "congestion_dual" in fields
    assert "bridge_height_difference" != "congestion_dual"
