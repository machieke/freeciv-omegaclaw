#!/usr/bin/env python3
"""Audit M3 research ETA predictions against uninterrupted live engine intervals."""

import argparse
import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.planning import research_duration_turns  # noqa: E402


def analyze(paths, minimum=30):
    trials = []
    logs = []
    for raw_path in paths:
        path = os.path.abspath(raw_path)
        relative = os.path.relpath(path, REPO)
        logical_path = (os.path.basename(path) if relative == os.pardir
                        or relative.startswith(os.pardir + os.sep) else relative)
        validation = validate_file(path)
        if not validation.valid:
            raise ValueError("invalid event log {}: {}".format(path, validation.to_dict()))
        snapshots = []
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if event["type"] == "state_snapshot":
                    snapshots.append(event)
        logs.append({
            "events": validation.event_count, "path": logical_path,
            "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
            "snapshots": len(snapshots),
        })
        index = 0
        while index < len(snapshots):
            research = snapshots[index]["payload"]["own_state"]["research"]
            target = research.get("target_name")
            cost = research.get("cost")
            progress = research.get("progress")
            rate = research.get("beakers_per_turn")
            if not target or not cost or not rate or progress is None:
                index += 1
                continue
            start = index
            predicted = research_duration_turns(cost, progress, rate)
            index += 1
            while (index < len(snapshots)
                   and snapshots[index]["payload"]["own_state"]["research"].get(
                       "target_name") == target):
                index += 1
            if index == len(snapshots):
                # Right-censored interval: never count it as a completion.
                continue
            actual = snapshots[index]["turn"] - snapshots[start]["turn"]
            trials.append({
                "absolute_error_turns": abs(actual - predicted),
                "actual_turns": actual, "beakers_per_turn": rate, "cost": cost,
                "end_turn": snapshots[index]["turn"], "event_log": logical_path,
                "predicted_turns": predicted, "progress": progress,
                "start_turn": snapshots[start]["turn"], "target": target,
            })
    within = sum(row["absolute_error_turns"] <= 1 for row in trials)
    count = len(trials)
    report = {
        "criterion": "P6.A1", "duration_function": "research_duration_turns/1.0",
        "live_engine": True, "logs": logs, "minimum_trials": int(minimum),
        "passed": count >= minimum and (float(within) / count if count else 0) >= 0.95,
        "trials": trials, "trials_completed": count,
        "within_one_turn": within,
        "within_one_turn_rate": float(within) / count if count else 0.0,
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("events", nargs="+")
    parser.add_argument("--minimum", type=int, default=30)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = analyze(args.events, args.minimum)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as stream:
            stream.write(serialized)
    print(serialized, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
