"""Phase 0 tests for the PLN-FreeCiv execution foundation."""

import copy
import json
import os
import subprocess
import sys
import tempfile


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO_ROOT, "src")
_BENCH = os.path.join(_REPO_ROOT, "benchmarks")
for _path in (_SRC, _BENCH):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from freeciv_agent import config, manifest  # noqa: E402
from freeciv_agent import gates  # noqa: E402
from freeciv import client  # noqa: E402


def _manifest(**overrides):
    values = {
        "condition_id": "a_stock_llm",
        "game_id": "phase0-test",
        "seed": 42,
        "ruleset": "civ2civ3",
        "turn_limit": 3,
        "provider": "Ollama-local",
        "model": "qwen3-coder-next:latest",
        "base_url": "http://localhost:11434/v1",
        "temperature": 0.3,
        "max_tokens": 4000,
        "freeciv_commit": "1" * 40,
        "proxy_commit": "2" * 40,
        "engine_image_digest": "sha256:" + "3" * 64,
    }
    values.update(overrides)
    return manifest.build_manifest(**values)


def test_condition_matrix_has_exact_order_and_capabilities():
    data = config.load_config()
    assert tuple(data["conditions"]) == config.CONDITION_ORDER
    assert not any(config.condition("a_stock_llm")["capabilities"].values())
    assert all(config.condition("e_full_loop")["capabilities"].values())


def test_condition_matrix_is_monotonic():
    previous = set()
    for condition_id in config.CONDITION_ORDER:
        caps = config.condition(condition_id)["capabilities"]
        enabled = {name for name, value in caps.items() if value}
        assert previous.issubset(enabled)
        previous = enabled


def test_config_rejects_missing_dependency():
    data = config.load_config()
    data["conditions"]["c_dependency_scheduler"]["capabilities"]["dependency_oracle"] = False
    try:
        config.validate_config(data)
        assert False, "expected invalid scheduler dependency"
    except config.FreecivConfigError as exc:
        assert "without" in str(exc)


def test_config_returns_defensive_copy():
    first = config.condition("e_full_loop")
    first["capabilities"]["scheduler"] = False
    assert config.condition("e_full_loop")["capabilities"]["scheduler"] is True


def test_runtime_capability_gate_fails_closed():
    assert gates.require("c_dependency_scheduler", "scheduler") is True
    try:
        gates.require("a_stock_llm", "scheduler")
        assert False, "expected disabled capability"
    except gates.CapabilityDisabled as exc:
        assert "a_stock_llm" in str(exc) and "scheduler" in str(exc)


def test_manifest_identity_ignores_run_id_timestamp_and_host():
    first = _manifest()
    second = _manifest()
    assert first["run_id"] != second["run_id"]
    assert first["manifest_identity"] == second["manifest_identity"]
    changed = copy.deepcopy(second)
    changed["created_at"] = "2000-01-01T00:00:00Z"
    changed["runtime"]["platform"] = "another-host"
    changed["run_id"] = "another-run"
    assert manifest.calculate_identity(changed) == first["manifest_identity"]


def test_manifest_identity_changes_for_behavior_input():
    first = _manifest(seed=42)
    second = _manifest(seed=43)
    third = _manifest(model="another-model")
    assert len({first["manifest_identity"], second["manifest_identity"], third["manifest_identity"]}) == 3


def test_manifest_detects_tampering():
    value = _manifest()
    value["game"]["seed"] = 99
    try:
        manifest.validate_manifest(value)
        assert False, "expected identity mismatch"
    except manifest.ManifestError as exc:
        assert "identity" in str(exc)


def test_manifest_atomic_round_trip():
    value = _manifest()
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "nested", "manifest.json")
        assert manifest.write_manifest(path, value) == path
        loaded = json.load(open(path, encoding="utf-8"))
        assert manifest.validate_manifest(loaded) == loaded
        assert not [name for name in os.listdir(os.path.dirname(path)) if ".tmp." in name]


def test_manifest_conforms_to_published_schema_when_jsonschema_available():
    try:
        import jsonschema
    except ImportError:
        return
    schema_path = os.path.join(
        _REPO_ROOT, "schemas", "freeciv-run-manifest", "v1", "manifest.schema.json")
    schema = json.load(open(schema_path, encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(_manifest())


def test_new_domain_modules_contain_no_workstation_path():
    package = os.path.join(_SRC, "freeciv_agent")
    for root, _, files in os.walk(package):
        for name in files:
            if name.endswith(".py"):
                text = open(os.path.join(root, name), encoding="utf-8").read()
                assert "/home/" not in text


def test_proxy_contract_fixture_matches_client_wire_shapes():
    path = os.path.join(_REPO_ROOT, "contracts", "freeciv-proxy", "v1", "contract.json")
    contract = json.load(open(path, encoding="utf-8"))
    freeciv = client.FreecivClient(
        "http://proxy", "ws://proxy/llmsocket/8002", "REDACTED",
        "contract-game", 1, agent_id="contract-agent", civserver_port=6001)
    assert freeciv.connect_message() == contract["websocket"]["connect"]
    assert client.action_message({
        "type": "unit_move", "unit_id": 7, "dest_x": 2, "dest_y": 3,
    }) == contract["websocket"]["action"]
    assert client.end_turn_message() == contract["websocket"]["end_turn"]


def test_baseline_prepare_command_writes_complete_artifacts():
    script = os.path.join(_REPO_ROOT, "scripts", "freeciv", "run_baseline.py")
    with tempfile.TemporaryDirectory() as directory:
        proc = subprocess.run([
            sys.executable, script,
            "--game-id", "prepare-test",
            "--out", directory,
            "--max-turns", "1",
            "--freeciv-commit", "1" * 40,
            "--proxy-commit", "2" * 40,
            "--provider", "Ollama-local",
            "--prepare-only",
        ], cwd=_REPO_ROOT, text=True, capture_output=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        prepared = json.load(open(os.path.join(directory, "manifest.json"), encoding="utf-8"))
        status = json.load(open(os.path.join(directory, "run_status.json"), encoding="utf-8"))
        assert manifest.validate_manifest(prepared)
        assert status["status"] == "prepared"
        assert status["manifest_identity"] == prepared["manifest_identity"]


def test_fixture_smoke_command_advances_a_turn():
    script = os.path.join(_REPO_ROOT, "scripts", "freeciv", "smoke.py")
    proc = subprocess.run(
        [sys.executable, script, "--mode", "fixture"], cwd=_REPO_ROOT,
        text=True, capture_output=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["advanced"] is True
    assert result["turn_after"] > result["turn_before"]
