#!/usr/bin/env python3
"""One-command M7 runner and deterministic aggregator."""

import argparse
import fcntl
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness import HarnessRunner, aggregate_runs, write_report  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--config")
    parser.add_argument("--backend", default="representative",
                        choices=("representative", "engine-live"))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--base-port", type=int, default=6001)
    parser.add_argument("--limit-seeds", type=int,
                        help="smoke-only prefix of the pinned seed list")
    parser.add_argument("--condition", action="append", choices=(
        "a_stock_llm", "b_state_oracle", "c_dependency_scheduler",
        "d_uncertain_monitor", "e_full_loop"),
        help="smoke-only condition subset; repeat for more than one")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--main-only", action="store_true")
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args(argv)
    lock_stream = None
    if args.backend == "engine-live" and not args.aggregate_only:
        lock_path = os.path.join(REPO, "artifacts", "freeciv", ".engine-live.lock")
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        lock_stream = open(lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_stream.seek(0)
            owner = lock_stream.read().strip() or "unknown owner"
            print("engine-live harness is already active: {}".format(owner), file=sys.stderr)
            return 2
        lock_stream.seek(0)
        lock_stream.truncate()
        lock_stream.write("pid={} out={}\n".format(os.getpid(), os.path.abspath(args.out)))
        lock_stream.flush()
    runner_summary = None
    if not args.aggregate_only:
        runner_summary = HarnessRunner(
            args.out, args.config, args.backend, args.workers, args.base_port,
            args.limit_seeds, args.condition).run(
                resume=not args.no_resume,
                include_induction=not args.main_only,
                include_grading=not args.main_only)
    aggregate = aggregate_runs(args.out, args.config)
    write_report(args.out, aggregate)
    print(json.dumps({
        "aggregate": os.path.abspath(os.path.join(args.out, "aggregate.json")),
        "conditions": {key: row["completed_games"]
                       for key, row in aggregate["conditions"].items()},
        "failures": len(aggregate["failures"]), "runner": runner_summary,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
