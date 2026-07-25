#!/usr/bin/env python3
"""Replay every canonical PF-PLN phase gate and audit tracked evidence."""

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402


PHASES = (
    {
        "phase": 0,
        "benchmark": "pf-pln-phase-0-executable-semantics",
        "script": "scripts/freeciv/run_pf_semantics_benchmark.py",
        "evidence": "pf-executable-semantics-phase-0.json",
    },
    {
        "phase": 1,
        "benchmark": None,
        "script": "scripts/freeciv/benchmark_pressure.py",
        "evidence": "pf-pressure-concentration.json",
    },
    {
        "phase": 2,
        "benchmark": "pf-pln-phase-2-provenance-contradiction",
        "script": "scripts/freeciv/run_pf_provenance_benchmark.py",
        "evidence": "pf-provenance-contradiction-phase-2.json",
    },
    {
        "phase": 3,
        "benchmark": "pf-pln-phase-3-exhaustive-voi",
        "script": "scripts/freeciv/run_pf_voi_benchmark.py",
        "evidence": "pf-observation-voi-phase-3.json",
    },
    {
        "phase": 4,
        "benchmark": "pf-pln-phase-4-conductance-learning",
        "script": "scripts/freeciv/run_pf_conductance_benchmark.py",
        "evidence": "pf-conductance-learning-phase-4.json",
    },
    {
        "phase": 5,
        "benchmark": "pf-pln-phase-5-hidden-context",
        "script": "scripts/freeciv/run_pf_clone_benchmark.py",
        "evidence": "pf-clone-lifecycle-phase-5.json",
    },
    {
        "phase": 6,
        "benchmark": "pf-pln-phase-6-contextual-induction",
        "script": "scripts/freeciv/run_pf_induction_benchmark.py",
        "evidence": "pf-induction-analogy-phase-6.json",
    },
    {
        "phase": 7,
        "benchmark": "pf-pln-phase-7-llm-gateway",
        "script": "scripts/freeciv/run_pf_llm_gateway_benchmark.py",
        "evidence": "pf-llm-gateway-phase-7.json",
    },
    {
        "phase": 8,
        "benchmark": "pf-pln-phase-8-differentiable-execution",
        "script": "scripts/freeciv/run_pf_differentiable_benchmark.py",
        "evidence": "pf-differentiable-phase-8.json",
    },
    {
        "phase": 9,
        "benchmark": "pf-pln-phase-9-conflicting-goals",
        "script": "scripts/freeciv/run_pf_multi_goal_benchmark.py",
        "evidence": "pf-multi-goal-phase-9.json",
    },
)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _fingerprint(value):
    return (
        value.get("artifact_hash")
        or value.get("benchmark_hash")
        or value.get("artifact", {}).get("structural_hash")
    )


def _phase_map_check(path):
    rows = {}
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if not line.startswith("| "):
                continue
            columns = [column.strip() for column in line.strip().split("|")]
            if len(columns) < 6:
                continue
            label = columns[1]
            prefix = label.split(" ", 1)[0]
            if not prefix.isdigit():
                continue
            rows[int(prefix)] = {
                "label": label,
                "remaining": columns[4],
                "status": columns[3],
            }
    missing = sorted(set(range(10)) - set(rows))
    extra = sorted(set(rows) - set(range(10)))
    incomplete = [
        phase for phase, row in sorted(rows.items())
        if not row["status"].startswith("Implemented")
        or row["remaining"] != "None"
    ]
    return not missing and not extra and not incomplete, {
        "extra_phases": extra,
        "incomplete_phases": incomplete,
        "missing_phases": missing,
        "phase_rows": rows,
    }


def _replay_phase(spec, evidence_root):
    script_path = os.path.join(REPO, spec["script"])
    evidence_path = os.path.join(evidence_root, spec["evidence"])
    details = {
        "benchmark": spec["benchmark"],
        "evidence": os.path.relpath(evidence_path, REPO),
        "phase": spec["phase"],
        "script": spec["script"],
    }
    if not os.path.isfile(script_path):
        details["error"] = "benchmark script missing"
        return False, details
    if not os.path.isfile(evidence_path):
        details["error"] = "evidence file missing"
        return False, details
    try:
        process = subprocess.run(
            [sys.executable, script_path],
            cwd=REPO,
            text=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        details["error"] = str(exc)
        return False, details
    details["returncode"] = process.returncode
    details["stderr"] = process.stderr.strip()
    try:
        replay = json.loads(process.stdout)
    except (TypeError, ValueError) as exc:
        details["error"] = "invalid benchmark JSON: {}".format(exc)
        return False, details
    try:
        with open(evidence_path, encoding="utf-8") as stream:
            evidence = json.load(stream)
    except (OSError, ValueError) as exc:
        details["error"] = "invalid evidence JSON: {}".format(exc)
        return False, details

    replay_fingerprint = _fingerprint(replay)
    evidence_fingerprint = _fingerprint(evidence)
    acceptance = replay.get("acceptance")
    acceptance_passed = (
        all(acceptance.values())
        if isinstance(acceptance, dict) and acceptance
        else process.returncode == 0
    )
    self_hash_valid = True
    if replay.get("artifact_hash") is not None:
        hash_material = dict(replay)
        artifact_hash = hash_material.pop("artifact_hash")
        self_hash_valid = structural_hash(hash_material) == artifact_hash
    benchmark_matches = (
        spec["benchmark"] is None
        or replay.get("benchmark") == spec["benchmark"]
        and evidence.get("benchmark") == spec["benchmark"]
    )
    details.update({
        "acceptance": acceptance,
        "acceptance_passed": acceptance_passed,
        "benchmark_matches": benchmark_matches,
        "evidence_fingerprint": evidence_fingerprint,
        "evidence_sha256": _sha256(evidence_path),
        "fingerprint_matches": (
            replay_fingerprint is not None
            and replay_fingerprint == evidence_fingerprint),
        "replay_fingerprint": replay_fingerprint,
        "self_hash_valid": self_hash_valid,
    })
    passed = (
        process.returncode == 0
        and acceptance_passed
        and benchmark_matches
        and details["fingerprint_matches"]
        and self_hash_valid
    )
    return passed, details


def run(phase_map, evidence_root, workers=4):
    checks = []

    def record(identifier, passed, details):
        checks.append({
            "details": details,
            "id": identifier,
            "passed": bool(passed),
        })

    map_passed, map_details = _phase_map_check(phase_map)
    map_details.update({
        "path": os.path.relpath(os.path.abspath(phase_map), REPO),
        "sha256": _sha256(phase_map),
    })
    record("pf-pln-phase-map-complete", map_passed, map_details)

    generated = subprocess.run(
        [
            sys.executable,
            os.path.join(REPO, "scripts", "freeciv",
                         "generate_event_types.py"),
            "--check",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
    )
    record("pf-pln-generated-event-types-current",
           generated.returncode == 0, {
               "stderr": generated.stderr.strip(),
               "stdout": generated.stdout.strip(),
           })

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, min(int(workers), len(PHASES)))) as executor:
        futures = {
            spec["phase"]: executor.submit(
                _replay_phase, spec, evidence_root)
            for spec in PHASES
        }
        for phase in range(10):
            passed, details = futures[phase].result()
            record("pf-pln-phase-{}-replay".format(phase), passed, details)

    return {
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
        "schema_version": "1.0",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase-map",
        default=os.path.join(REPO, "docs", "freeciv",
                             "pf-pln-phase-map.md"),
    )
    parser.add_argument(
        "--evidence-root",
        default=os.path.join(REPO, "docs", "freeciv", "evidence"),
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")
    result = run(args.phase_map, args.evidence_root, args.workers)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        parent = os.path.dirname(os.path.abspath(args.output))
        if parent:
            os.makedirs(parent, exist_ok=True)
        temporary = os.path.abspath(args.output) + ".tmp.{}".format(
            os.getpid())
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(rendered)
        os.replace(temporary, os.path.abspath(args.output))
    sys.stdout.write(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
