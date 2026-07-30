"""The optional native parity tool stays behind a strict process contract."""

import json
import os
import subprocess
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import freeciv_agent.oracle.native_gameplay as native_module  # noqa: E402
from freeciv_agent.oracle import (  # noqa: E402
    NativeGameplayOracle,
    NativeGameplayOracleError,
    compare_native_gameplay_cases,
)


def test_native_gameplay_oracle_validates_response_identity(monkeypatch):
    def run(command, input, **kwargs):
        request = json.loads(
            input.decode("utf-8"))
        response = {
            "oracle_identity": "native-test",
            "protocol_version":
                request["protocol_version"],
            "request_id": request["request_id"],
            "result": {
                "reachable": True,
            },
        }
        return subprocess.CompletedProcess(
            command, 0,
            stdout=json.dumps(
                response).encode("utf-8"),
            stderr=b"")

    monkeypatch.setattr(
        native_module.subprocess,
        "run", run)
    oracle = NativeGameplayOracle(
        ("native-freeciv-parity",),
        "native-test")

    assert oracle.query(
        "movement", {
            "actor_id": 1,
        }) == {
            "reachable": True,
        }


def test_native_gameplay_oracle_rejects_unbound_response(monkeypatch):
    def run(command, input, **kwargs):
        del input, kwargs
        return subprocess.CompletedProcess(
            command, 0,
            stdout=b'{"result": {}}',
            stderr=b"")

    monkeypatch.setattr(
        native_module.subprocess,
        "run", run)
    oracle = NativeGameplayOracle(
        ("native-freeciv-parity",),
        "native-test")

    with pytest.raises(
            NativeGameplayOracleError,
            match="identity mismatch"):
        oracle.query("combat", {})


def test_native_gameplay_case_comparison_is_stable_and_reports_mismatch(
        monkeypatch):
    def run(command, input, **kwargs):
        del kwargs
        request = json.loads(
            input.decode("utf-8"))
        response = {
            "oracle_identity": "native-test",
            "protocol_version":
                request["protocol_version"],
            "request_id":
                request["request_id"],
            "result": {
                "value": request[
                    "payload"]["value"],
            },
        }
        return subprocess.CompletedProcess(
            command, 0,
            stdout=json.dumps(
                response).encode("utf-8"),
            stderr=b"")

    monkeypatch.setattr(
        native_module.subprocess,
        "run", run)
    oracle = NativeGameplayOracle(
        ("native-freeciv-parity",),
        "native-test")
    cases = (
        {
            "case_id": "movement-2",
            "derived_result": {"value": 3},
            "kind": "movement",
            "payload": {"value": 2},
        },
        {
            "case_id": "movement-1",
            "derived_result": {"value": 1},
            "kind": "movement",
            "payload": {"value": 1},
        },
    )

    first = compare_native_gameplay_cases(
        oracle, cases)
    second = compare_native_gameplay_cases(
        oracle, tuple(reversed(cases)))

    assert first == second
    assert first["case_count"] == 2
    assert first["mismatch_count"] == 1
    assert first["passed"] is False
    assert [
        row["case_id"]
        for row in first["comparisons"]
    ] == ["movement-1", "movement-2"]


def test_native_gameplay_case_comparison_rejects_duplicate_ids():
    oracle = NativeGameplayOracle(
        ("native-freeciv-parity",),
        "native-test")
    row = {
        "case_id": "duplicate",
        "derived_result": {},
        "kind": "combat",
        "payload": {},
    }

    with pytest.raises(
            ValueError,
            match="must be unique"):
        compare_native_gameplay_cases(
            oracle, (row, row))

    with pytest.raises(
            ValueError,
            match="at least one case"):
        compare_native_gameplay_cases(
            oracle, ())
