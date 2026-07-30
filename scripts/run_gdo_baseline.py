#!/usr/bin/env python3
"""Capture a deterministic GDO-0 baseline environment and optional test run."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT = os.path.join(
    REPO, "benchmarks", "gdo", "baseline_manifest.local.json")
TARGETED_TESTS = (
    "Autotests/test_freeciv_transitions.py",
    "Autotests/test_freeciv_teleology.py",
    "Autotests/test_freeciv_pf_runtime.py",
    "Autotests/test_freeciv_adapter.py",
)


def _run(arguments, check=True):
    result = subprocess.run(
        arguments, cwd=REPO, check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True)
    return result.returncode, result.stdout.strip()


def _git(*arguments):
    return _run(("git",) + arguments)[1]


def _file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _structural_hash(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _test_result(full_suite):
    tests = ("Autotests",) if full_suite else TARGETED_TESTS
    command = (
        sys.executable, "-m", "pytest", "-q") + tests
    started = time.perf_counter()
    returncode, output = _run(command, check=False)
    return {
        "command": list(command),
        "duration_seconds": round(
            time.perf_counter() - started, 6),
        "output": output,
        "passed": returncode == 0,
        "returncode": int(returncode),
        "scope": "full" if full_suite else "targeted",
    }


def build_manifest(run_tests=False, full_suite=False):
    requirement_path = os.path.join(REPO, "requirements.txt")
    status = _git("status", "--porcelain")
    manifest = {
        "baseline_status": "captured",
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "comparators": {
            "B0": "canonical Impact",
            "B1": "scalar PF-v2 plus v1 packet scheduler",
        },
        "dependency_locks": {
            "requirements.txt": _file_digest(
                requirement_path),
        },
        "dirty_worktree": bool(status),
        "git_status": status.splitlines(),
        "python": {
            "executable": sys.executable,
            "version": ".".join(
                str(value) for value
                in sys.version_info[:3]),
        },
        "schema_version": "1.0",
        "source_commit": _git("rev-parse", "HEAD"),
    }
    if run_tests:
        manifest["test_result"] = _test_result(
            full_suite)
        if not manifest["test_result"]["passed"]:
            manifest["baseline_status"] = "test_failed"
    else:
        manifest["test_result"] = {
            "scope": "not_run",
        }
    identity_material = dict(manifest)
    identity_material.pop("git_status", None)
    manifest["manifest_identity"] = (
        _structural_hash(identity_material))
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--run-tests", action="store_true")
    parser.add_argument(
        "--full-suite", action="store_true")
    arguments = parser.parse_args()
    if arguments.full_suite:
        arguments.run_tests = True
    manifest = build_manifest(
        run_tests=arguments.run_tests,
        full_suite=arguments.full_suite)
    output = os.path.abspath(arguments.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as stream:
        json.dump(
            manifest, stream, indent=2,
            sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "baseline_status":
            manifest["baseline_status"],
        "manifest_identity":
            manifest["manifest_identity"],
        "output": output,
    }, sort_keys=True))
    return 0 if manifest[
        "baseline_status"] != "test_failed" else 1


if __name__ == "__main__":
    sys.exit(main())
