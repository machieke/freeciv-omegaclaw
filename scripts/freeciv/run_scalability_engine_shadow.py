#!/usr/bin/env python3
"""Run the preregistered high-entity G8 paired engine-shadow cohort."""

import argparse
import json
import os
import subprocess
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEED_COUNT = 20


def _profile(arm, index):
    if arm == "control":
        name = "freeciv_scalability_engine_shadow_control.yaml"
    elif index == 0:
        name = "freeciv_scalability_engine_shadow_detail.yaml"
    else:
        name = "freeciv_scalability_engine_shadow_shadow.yaml"
    return os.path.join(REPO, "profile", name)


def _run_command(root, arm, index):
    return [
        sys.executable,
        os.path.join(REPO, "scripts", "freeciv", "run_harness.py"),
        "--out", os.path.join(root, arm),
        "--config", _profile(arm, index),
        "--backend", "engine-live",
        "--workers", "1",
        "--limit-seeds", "1",
        "--seed-offset", str(index),
        "--main-only",
        "--condition", "e_full_loop",
    ]


def _audit_command(root, output):
    return [
        sys.executable,
        os.path.join(
            REPO, "scripts", "freeciv",
            "audit_fdas_engine_shadow_cohort.py"),
        "--control", os.path.join(root, "control"),
        "--shadow", os.path.join(root, "shadow"),
        "--minimum-pairs", str(SEED_COUNT),
        "--output", output,
    ]


def _clean_source_identity():
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO, text=True).strip()
    if dirty:
        raise RuntimeError(
            "G8 requires a committed clean source tree before execution")
    return commit


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "--arm", choices=("both", "control", "shadow"), default="both")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--stop-index", type=int, default=SEED_COUNT)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    output = os.path.abspath(
        args.output or os.path.join(root, "report.json"))
    if not 0 <= args.start_index <= args.stop_index <= SEED_COUNT:
        parser.error("indices must satisfy 0 <= start <= stop <= 20")
    commit = _clean_source_identity()
    if not args.audit_only:
        arms = ("control", "shadow") if args.arm == "both" else (args.arm,)
        for index in range(args.start_index, args.stop_index):
            for arm in arms:
                print(json.dumps({
                    "arm": arm, "commit": commit, "index": index,
                    "phase": "engine-shadow-run",
                }, sort_keys=True), flush=True)
                subprocess.run(
                    _run_command(root, arm, index), cwd=REPO, check=True)
                if _clean_source_identity() != commit:
                    raise RuntimeError("source identity changed during G8 cohort")
    if args.audit_only or (
            args.arm == "both" and args.start_index == 0
            and args.stop_index == SEED_COUNT):
        subprocess.run(_audit_command(root, output), cwd=REPO, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
