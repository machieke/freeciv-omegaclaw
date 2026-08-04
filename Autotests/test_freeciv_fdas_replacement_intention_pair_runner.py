import os
import sys
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SCRIPTS, os.path.join(REPO, "src"),
             os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from run_fdas_replacement_intention_pairs import (  # noqa: E402
    DEFAULT_CONTROL_PROFILE,
    DEFAULT_TREATMENT_PROFILE,
    ISOLATED_EXPERIMENT_ID,
    ISOLATED_FIXED_SEEDS,
    build_pair_buckets,
    parse_server_ports,
    validate_engine_environment,
    validate_launch_preflight,
)
from freeciv.harness.config import load  # noqa: E402


def _configs():
    return {
        "control": load(DEFAULT_CONTROL_PROFILE),
        "treatment": load(DEFAULT_TREATMENT_PROFILE),
    }


def test_pair_buckets_preserve_serial_order_and_assign_each_seed_once():
    buckets = build_pair_buckets(ISOLATED_FIXED_SEEDS, 4)
    pairs = [pair for bucket in buckets for pair in bucket]

    assert [len(bucket) for bucket in buckets] == [4, 4, 4, 4]
    assert sorted(pair["seed"] for pair in pairs) == sorted(
        ISOLATED_FIXED_SEEDS)
    assert sorted(pair["seed_offset"] for pair in pairs) == list(range(16))
    assert all(set(pair["arm_order"]) == {"control", "treatment"}
               for pair in pairs)


@pytest.mark.parametrize("value,workers", (
    ("6001,6001", 2),
    ("6001", 2),
    ("6010", 1),
))
def test_server_ports_fail_closed_on_shared_missing_or_unsupported_port(
        value, workers):
    with pytest.raises(ValueError, match="distinct dedicated ports"):
        parse_server_ports(value, workers)


def test_preflight_binds_v3_profiles_ports_and_empty_output(tmp_path):
    out = tmp_path / "fresh-pr86-root"

    preflight = validate_launch_preflight(
        str(out), DEFAULT_CONTROL_PROFILE, DEFAULT_TREATMENT_PROFILE,
        workers=4, server_ports="6001,6003,6005,6007",
        require_clean_source=False,
        environment_validator=lambda _configs: {"validated": True})

    assert not out.exists()
    assert preflight["experiment_id"] == ISOLATED_EXPERIMENT_ID
    assert preflight["server_ports"] == [6001, 6003, 6005, 6007]
    assert preflight["fixed_seeds"] == list(ISOLATED_FIXED_SEEDS)
    assert [len(bucket) for bucket in preflight["pair_buckets"]] == [4] * 4
    assert preflight["runtime_environment"] == {"validated": True}


def test_preflight_rejects_even_an_empty_existing_output_root(tmp_path):
    with pytest.raises(ValueError, match="output root must not exist"):
        validate_launch_preflight(
            str(tmp_path), DEFAULT_CONTROL_PROFILE, DEFAULT_TREATMENT_PROFILE,
            workers=1, server_ports=(6001,), require_clean_source=False)


def test_engine_environment_rejects_missing_ruleset_before_dependencies():
    with pytest.raises(ValueError, match="FREECIV_RULESET_ROOT"):
        validate_engine_environment(
            _configs(), environ={},
            dependency_probe=lambda *_args: pytest.fail(
                "dependencies must not be probed without a ruleset"))


def test_engine_environment_compiles_ruleset_and_freezes_safe_dependencies(
        tmp_path):
    ruleset = tmp_path / "data" / "civ2civ3"
    ruleset.mkdir(parents=True)
    (ruleset / "techs.ruleset").write_text("proof", encoding="utf-8")
    compiled = SimpleNamespace(
        compiler_version="compiler-proof",
        to_dict=lambda: {"ruleset": "compiled-proof"})

    result = validate_engine_environment(
        _configs(),
        environ={"FREECIV_RULESET_ROOT": str(tmp_path / "data")},
        ruleset_compiler=lambda root, name: (
            compiled
            if root == str(tmp_path / "data") and name == "civ2civ3"
            else pytest.fail("ruleset compiler inputs differ")),
        dependency_probe=lambda container, ws_url, ollama_url, model: {
            "freeciv_server_container": container,
            "ollama_endpoint": ollama_url,
            "ollama_model": model,
            "proxy_endpoint": ws_url,
        })

    assert result["ruleset_compiler_version"] == "compiler-proof"
    assert result["ruleset_root"] == str(tmp_path / "data")
    assert result["ollama_model"] == "qwen3-coder-next:latest"
