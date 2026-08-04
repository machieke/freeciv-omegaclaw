#!/usr/bin/env python3
"""Run the frozen PR86 replacement-intention pairs on isolated ports."""

import argparse
import concurrent.futures
import datetime
import fcntl
import json
import os
import subprocess
import sys
import traceback


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness import HarnessRunner  # noqa: E402
from freeciv.harness.config import load  # noqa: E402
from freeciv.harness.fdas_replacement_intention_live import (  # noqa: E402
    ISOLATED_EXPERIMENT_ID,
    ISOLATED_FIXED_SEEDS,
    _expected_diagnostic,
    expected_arm_order,
)


DEFAULT_CONTROL_PROFILE = os.path.join(
    REPO, "profile",
    "freeciv_harness_fdas_pr86_replacement_intention_isolated_control_160_turn.yaml")
DEFAULT_TREATMENT_PROFILE = os.path.join(
    REPO, "profile",
    "freeciv_harness_fdas_pr86_replacement_intention_isolated_treatment_160_turn.yaml")
EXPECTED_COHORT = {
    "claim_eligible": False,
    "cohort_id": ISOLATED_EXPERIMENT_ID,
    "paired_arms": ["control", "treatment"],
    "purpose": "descriptive-isolated-launch-paired-pilot",
    "required_unique_seeds": 16,
}


def _utc_now():
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path, value):
    temporary = path + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, path)


def parse_server_ports(value, workers):
    """Return exactly one supported and unique engine port per worker."""
    if isinstance(workers, bool) or not 1 <= int(workers) <= 9:
        raise ValueError("workers must be within 1-9")
    workers = int(workers)
    if value is None:
        ports = tuple(range(6001, 6001 + workers))
    elif isinstance(value, str):
        try:
            ports = tuple(
                int(item.strip()) for item in value.split(",")
                if item.strip())
        except ValueError:
            raise ValueError("server ports must be comma-separated integers")
    else:
        ports = tuple(value)
    if (len(ports) != workers
            or any(isinstance(port, bool) or not isinstance(port, int)
                   or not 6001 <= port <= 6009 for port in ports)
            or len(set(ports)) != len(ports)):
        raise ValueError(
            "workers require distinct dedicated ports within 6001-6009")
    return ports


def build_pair_buckets(seeds, workers, experiment_id=ISOLATED_EXPERIMENT_ID):
    """Keep each pair serial while distributing seed pairs deterministically."""
    if isinstance(workers, bool) or not 1 <= int(workers) <= 9:
        raise ValueError("workers must be within 1-9")
    buckets = [[] for _ in range(int(workers))]
    for seed_offset, seed in enumerate(tuple(seeds)):
        buckets[seed_offset % int(workers)].append({
            "arm_order": list(expected_arm_order(seed, experiment_id)),
            "seed": int(seed),
            "seed_offset": seed_offset,
        })
    return buckets


def _source_identity(repo):
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo,
        stderr=subprocess.DEVNULL, text=True).strip()
    dirty = bool(subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo, stderr=subprocess.DEVNULL, text=True).strip())
    return {"commit": commit, "dirty": dirty}


def validate_launch_preflight(
        out, control_profile, treatment_profile, workers, server_ports,
        require_clean_source=True, repo=REPO):
    """Fail before creating artifacts or starting an engine on any mismatch."""
    out = os.path.abspath(out)
    profiles = {
        "control": os.path.abspath(control_profile),
        "treatment": os.path.abspath(treatment_profile),
    }
    ports = parse_server_ports(server_ports, workers)
    if os.path.lexists(out):
        raise ValueError("output root must not exist: {}".format(out))
    configs = dict((arm, load(path)) for arm, path in profiles.items())
    for arm, config in configs.items():
        if tuple(config.get("seeds", ())) != ISOLATED_FIXED_SEEDS:
            raise ValueError("{} profile seed cohort differs".format(arm))
        if config.get("diagnostic_seed_cohort") != EXPECTED_COHORT:
            raise ValueError("{} profile diagnostic cohort differs".format(arm))
        declaration = config.get("dependent_atomspace", {}).get(
            "manifest", {})
        diagnostic = declaration.get(
            "coordinated_replacement_intention_outcome_diagnostic")
        if diagnostic != _expected_diagnostic(
                arm, ISOLATED_EXPERIMENT_ID):
            raise ValueError("{} profile arm lock differs".format(arm))
    if configs["control"]["configuration_hash"] == configs[
            "treatment"]["configuration_hash"]:
        raise ValueError("paired arm configurations must be distinct")
    source = _source_identity(repo)
    if require_clean_source and source["dirty"]:
        raise ValueError("PR86 launch requires a clean source tree")
    return {
        "arm_profiles": profiles,
        "experiment_id": ISOLATED_EXPERIMENT_ID,
        "fixed_seeds": list(ISOLATED_FIXED_SEEDS),
        "output_root": out,
        "pair_buckets": build_pair_buckets(ISOLATED_FIXED_SEEDS, workers),
        "server_ports": list(ports),
        "source": source,
        "worker_count": int(workers),
    }


def _run_worker(spec):
    results = []
    for pair in spec["pairs"]:
        for arm in pair["arm_order"]:
            started_at = _utc_now()
            try:
                arm_root = os.path.join(
                    spec["out"], "worker-{}".format(spec["worker"]), arm)
                runner = HarnessRunner(
                    arm_root,
                    config_path=spec["profiles"][arm],
                    backend="engine-live",
                    workers=1,
                    seed_limit=1,
                    seed_offset=pair["seed_offset"],
                    conditions=("e_full_loop",),
                    server_ports=(spec["port"],))
                summary = runner.run(
                    resume=False, include_induction=False,
                    include_grading=False)
                result = {
                    "arm": arm,
                    "ended_at": _utc_now(),
                    "output_root": arm_root,
                    "port": spec["port"],
                    "runner_summary": summary,
                    "seed": pair["seed"],
                    "seed_offset": pair["seed_offset"],
                    "started_at": started_at,
                    "status": (
                        "completed" if summary["completed"] == 1
                        else "infrastructure_failure"),
                    "worker": spec["worker"],
                }
            except Exception as exc:
                result = {
                    "arm": arm,
                    "ended_at": _utc_now(),
                    "error": "{}: {}".format(type(exc).__name__, exc),
                    "port": spec["port"],
                    "seed": pair["seed"],
                    "seed_offset": pair["seed_offset"],
                    "started_at": started_at,
                    "status": "launcher_failure",
                    "traceback": traceback.format_exc()[-8000:],
                    "worker": spec["worker"],
                }
            results.append(result)
            print(json.dumps({
                "arm": result["arm"],
                "port": result["port"],
                "seed": result["seed"],
                "status": result["status"],
                "worker": result["worker"],
            }, sort_keys=True), flush=True)
    return results


def run_cohort(preflight):
    os.makedirs(preflight["output_root"])
    launch_manifest = {
        "arm_profiles": preflight["arm_profiles"],
        "experiment_id": preflight["experiment_id"],
        "fixed_seeds": preflight["fixed_seeds"],
        "launch_isolation_policy": (
            "explicit-dedicated-server-port-per-worker-v1"),
        "launch_preflight_policy": (
            "unique-port-empty-output-root-clean-source-v1"),
        "schema_version": "1.0",
        "server_ports": preflight["server_ports"],
        "source": preflight["source"],
        "started_at": _utc_now(),
        "worker_count": preflight["worker_count"],
    }
    _atomic_json(os.path.join(
        preflight["output_root"], "launch-manifest.json"), launch_manifest)
    specs = [{
        "out": preflight["output_root"],
        "pairs": preflight["pair_buckets"][worker],
        "port": preflight["server_ports"][worker],
        "profiles": preflight["arm_profiles"],
        "worker": worker,
    } for worker in range(preflight["worker_count"])]
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=preflight["worker_count"]) as pool:
        grouped = list(pool.map(_run_worker, specs))
    results = [row for group in grouped for row in group]
    results.sort(key=lambda row: (row["seed_offset"], row["started_at"]))
    summary = {
        "attempted_arms": len(results),
        "completed_arms": sum(
            row["status"] == "completed" for row in results),
        "ended_at": _utc_now(),
        "experiment_id": preflight["experiment_id"],
        "fixed_arm_count": len(preflight["fixed_seeds"]) * 2,
        "infrastructure_failures": sum(
            row["status"] == "infrastructure_failure" for row in results),
        "launcher_failures": sum(
            row["status"] == "launcher_failure" for row in results),
        "results": results,
        "schema_version": "1.0",
        "server_ports": preflight["server_ports"],
        "source": preflight["source"],
        "started_at": launch_manifest["started_at"],
        "worker_count": preflight["worker_count"],
    }
    _atomic_json(os.path.join(
        preflight["output_root"], "launch-summary.json"), summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--server-ports",
        help="dedicated ports, one per worker (default: 6001 upward)")
    parser.add_argument("--control-profile", default=DEFAULT_CONTROL_PROFILE)
    parser.add_argument(
        "--treatment-profile", default=DEFAULT_TREATMENT_PROFILE)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        preflight = validate_launch_preflight(
            arguments.out, arguments.control_profile,
            arguments.treatment_profile, arguments.workers,
            arguments.server_ports)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        parser.error(str(exc))
    if arguments.preflight_only:
        print(json.dumps(preflight, sort_keys=True))
        return 0

    # Bind the lock to the shared artifact parent, including when this script
    # runs from a detached frozen worktree with an output root in the primary
    # repository's artifact tree.
    lock_path = os.path.join(
        os.path.dirname(preflight["output_root"]), ".engine-live.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock_stream:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_stream.seek(0)
            owner = lock_stream.read().strip() or "unknown owner"
            print("engine-live harness is already active: {}".format(
                owner), file=sys.stderr)
            return 2
        lock_stream.seek(0)
        lock_stream.truncate()
        lock_stream.write(
            "pid={} out={} track=fdas-pr86-paired\n".format(
                os.getpid(), preflight["output_root"]))
        lock_stream.flush()
        summary = run_cohort(preflight)
    print(json.dumps({
        "completed_arms": summary["completed_arms"],
        "fixed_arm_count": summary["fixed_arm_count"],
        "infrastructure_failures": summary["infrastructure_failures"],
        "launcher_failures": summary["launcher_failures"],
        "output_root": preflight["output_root"],
    }, sort_keys=True))
    return 0 if summary["attempted_arms"] == summary["fixed_arm_count"] else 1


if __name__ == "__main__":
    sys.exit(main())
