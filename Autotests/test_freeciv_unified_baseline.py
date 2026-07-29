"""G0 gates for the frozen scalar-v1 and strong scalar baselines."""

import copy
import hashlib
import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_unified.baseline import (  # noqa: E402
    BaselineIdentityError,
    _verify_rows,
    assert_comparable,
    baseline_identity,
    load_baseline_manifest,
    verify_baseline,
)
from freeciv.pf_unified.golden import (  # noqa: E402
    GOLDEN_NAMES,
    capture_golden,
    reproduce_golden,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    ScalarBaselineConfig,
    ScalarRouteBid,
    SmoothedScalarController,
)


def _sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_archived_baseline_identity_fixtures_and_goldens_verify():
    manifest = load_baseline_manifest()
    report = verify_baseline(manifest)

    assert report["valid"]
    assert report["source_matches"]
    assert report["fixture_set_matches"]
    assert report["golden_set_matches"]
    assert manifest["source"] == report["archived_source"]
    assert manifest["solvers"]["scalar_baseline"] == (
        SmoothedScalarController.SOLVER_IDENTITY)
    assert baseline_identity(manifest) == report["baseline_identity"]


def test_baseline_verification_detects_fixture_drift():
    manifest = load_baseline_manifest()
    changed = copy.deepcopy(manifest)
    changed["fixtures"]["files"][0]["sha256"] = "0" * 64

    report = verify_baseline(changed)

    assert not report["valid"]
    assert not report["fixture_set_matches"]
    assert report["fixture_mismatches"][0]["path"] == (
        "benchmarks/freeciv/samples/real_state_turn0.json")


def test_baseline_fixtures_are_read_from_archived_source(
        monkeypatch):
    manifest = load_baseline_manifest()

    monkeypatch.setattr(
        "freeciv.pf_unified.baseline._file_sha256",
        lambda path: (_ for _ in ()).throw(
            AssertionError(
                "archived fixtures must not read mutable working tree")))
    rows, mismatches = _verify_rows(
        manifest["fixtures"]["files"],
        archived_commit=manifest["source"]["commit"])

    assert not mismatches
    assert rows == manifest["fixtures"]["files"]


def test_cross_version_comparison_requires_explicit_flag():
    baseline = load_baseline_manifest()
    changed = copy.deepcopy(baseline)
    changed["solvers"]["live_adapter"] = "grounded-impact-planner/next"

    with pytest.raises(BaselineIdentityError, match="solvers"):
        assert_comparable(baseline, changed)
    report = assert_comparable(
        baseline, changed, allow_cross_version=True)
    assert not report["comparable"]
    assert report["mismatches"] == ["solvers"]
    assert report["allow_cross_version"]


def test_golden_artifacts_reproduce_byte_for_byte(tmp_path):
    manifest = load_baseline_manifest()
    report = reproduce_golden(manifest)
    captured = capture_golden(str(tmp_path), manifest)

    assert report["byte_exact"], report["mismatches"]
    assert tuple(sorted(report["actual"])) == tuple(sorted(GOLDEN_NAMES))
    for row in captured:
        name = os.path.basename(row["path"])
        expected = os.path.join(
            REPO, manifest["golden"]["directory"], name)
        actual = os.path.join(str(tmp_path), name)
        assert open(actual, "rb").read() == open(expected, "rb").read()
        assert _sha256(actual) == report["expected"][name]


def test_every_golden_declares_complete_replay_identity():
    manifest = load_baseline_manifest()
    identity = baseline_identity(manifest)
    rows = manifest["golden"]["artifacts"]

    assert len(rows) == len(GOLDEN_NAMES)
    for row in rows:
        with open(os.path.join(REPO, row["path"]), encoding="utf-8") as stream:
            artifact = json.load(stream)
        assert artifact["schema_version"] == "1.0"
        assert artifact["artifact_type"] in ("semantic", "performance")
        assert artifact["baseline_identity"] == identity
        assert artifact["source_commit"] == manifest["source"]["commit"]
        assert artifact["random_seed"] == manifest["random_seed"]
        assert artifact["payload_hash"] == structural_hash(
            artifact["payload"])
        material = dict(artifact)
        artifact_hash = material.pop("artifact_hash")
        assert artifact_hash == structural_hash(material)


@pytest.mark.parametrize("field,value", (
    ("smoothing", -0.01),
    ("smoothing", 1.01),
    ("route_momentum", -0.01),
    ("minimum_dwell_steps", True),
    ("minimum_dwell_steps", 2.0),
    ("minimum_dwell_steps", 1.5),
    ("dwell_bonus", -0.01),
    ("switch_margin", -0.01),
    ("diversity_floor", 1.01),
))
def test_strong_scalar_configuration_rejects_invalid_values(field, value):
    arguments = {field: value}
    with pytest.raises(ValueError):
        ScalarBaselineConfig(**arguments)


def test_strong_scalar_smooths_and_applies_route_momentum():
    controller = SmoothedScalarController(ScalarBaselineConfig(
        smoothing=0.5, route_momentum=1.0,
        minimum_dwell_steps=0, dwell_bonus=0.0,
        switch_margin=0.0, diversity_floor=0.0))

    first = controller.update_route_score("route", 1.0)
    second = controller.update_route_score("route", 2.0)

    assert first.smoothed_score == 1.0
    assert second.smoothed_score == 1.5
    assert second.momentum == 0.5
    assert second.total_score == 2.0


def test_strong_scalar_minimum_dwell_and_hysteresis_prevent_chatter():
    dwell = SmoothedScalarController(ScalarBaselineConfig(
        smoothing=1.0, route_momentum=0.0,
        minimum_dwell_steps=2, dwell_bonus=0.0,
        switch_margin=0.0, diversity_floor=0.1))
    dwell.rank(
        (ScalarRouteBid("a", 1.0), ScalarRouteBid("b", 0.9)), 0)
    retained = dwell.rank(
        (ScalarRouteBid("a", 0.9), ScalarRouteBid("b", 1.1)), 1)
    switched = dwell.rank(
        (ScalarRouteBid("a", 0.9), ScalarRouteBid("b", 1.1)), 2)

    assert retained.selected_route_id == "a"
    assert retained.retained_by_dwell
    assert switched.selected_route_id == "b"

    hysteresis = SmoothedScalarController(ScalarBaselineConfig(
        smoothing=1.0, route_momentum=0.0,
        minimum_dwell_steps=0, dwell_bonus=0.0,
        switch_margin=0.2, diversity_floor=0.0))
    hysteresis.rank(
        (ScalarRouteBid("a", 1.0), ScalarRouteBid("b", 0.9)), 0)
    retained = hysteresis.rank(
        (ScalarRouteBid("a", 1.0), ScalarRouteBid("b", 1.1)), 1)

    assert retained.selected_route_id == "a"
    assert retained.retained_by_hysteresis


def test_strong_scalar_reserves_one_backup_and_releases_inadmissible_route():
    controller = SmoothedScalarController(ScalarBaselineConfig(
        smoothing=1.0, route_momentum=0.0,
        minimum_dwell_steps=10, dwell_bonus=0.0,
        switch_margin=0.0, diversity_floor=0.15))
    first = controller.rank((
        ScalarRouteBid("economy", 1.0, pf_advantage=0.1),
        ScalarRouteBid("defense", 0.9, bridge_estimate=0.1),
        ScalarRouteBid("science", 0.8),
    ), 0)
    second = controller.rank((
        ScalarRouteBid("economy", 2.0, admissible=False),
        ScalarRouteBid("defense", 0.9),
        ScalarRouteBid("science", 0.8),
    ), 1)

    assert first.selected_route_id == "economy"
    assert first.backup_route_id == "defense"
    assert first.allocations == (
        ("economy", 0.85), ("defense", 0.15))
    assert abs(sum(value for _, value in first.allocations) - 1.0) < 1e-12
    assert second.selected_route_id == "defense"
    assert not second.retained_by_dwell


def test_strong_scalar_is_insertion_order_invariant_and_resettable():
    bids = (
        ScalarRouteBid("b", 1.0, bridge_estimate=0.1),
        ScalarRouteBid("a", 1.0, pf_advantage=0.1),
    )
    first = SmoothedScalarController()
    second = SmoothedScalarController()

    left = first.rank(bids, 0)
    right = second.rank(tuple(reversed(bids)), 0)
    first.reset()
    replayed = first.rank(bids, 0)

    assert left.to_dict() == right.to_dict()
    assert replayed.to_dict() == left.to_dict()
    assert left.artifact_hash == structural_hash({
        key: value for key, value in left.to_dict().items()
        if key != "artifact_hash"
    })


def test_strong_scalar_rejects_step_regression_and_duplicate_routes():
    controller = SmoothedScalarController()
    controller.rank((ScalarRouteBid("a", 1.0),), 2)

    with pytest.raises(ValueError, match="regress"):
        controller.rank((ScalarRouteBid("a", 1.0),), 1)
    with pytest.raises(ValueError, match="unique"):
        SmoothedScalarController().rank((
            ScalarRouteBid("a", 1.0),
            ScalarRouteBid("a", 2.0),
        ), 0)
