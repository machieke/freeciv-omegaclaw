#!/usr/bin/env python3
"""Run and aggregate the predeclared paired FreeCiv impact-policy experiment."""

import argparse
import fcntl
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness import (HarnessRunner, aggregate_impact_pairs,  # noqa: E402
                             write_impact_report)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--config", default=os.path.join(
        REPO, "profile", "freeciv_harness.yaml"))
    parser.add_argument("--backend", default="representative",
                        choices=("representative", "engine-live"))
    parser.add_argument("--workers", type=int, default=1,
                        help="pair workers; both arms of a seed remain serial on one worker")
    parser.add_argument("--server-ports",
                        help="comma-separated dedicated engine ports, one per worker")
    parser.add_argument("--cohort", default=None,
                        help="paired cohort (default: configuration default_cohort)")
    parser.add_argument("--limit-pairs", type=int,
                        help="development/pilot smoke prefix; forbidden for confirmatory cohorts")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args(argv)
    server_ports = None
    if args.server_ports:
        try:
            server_ports = tuple(int(value.strip())
                                 for value in args.server_ports.split(",") if value.strip())
        except ValueError:
            parser.error("--server-ports must be comma-separated integers")
        if len(server_ports) != args.workers:
            parser.error("--server-ports must provide exactly --workers ports")

    lock_stream = None
    if args.backend == "engine-live" and not args.aggregate_only:
        lock_path = os.path.join(REPO, "artifacts", "freeciv", ".engine-live.lock")
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        lock_stream = open(lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("engine-live harness is already active", file=sys.stderr)
            return 2
        lock_stream.seek(0)
        lock_stream.truncate()
        lock_stream.write("pid={} out={} track=impact_pair\n".format(
            os.getpid(), os.path.abspath(args.out)))
        lock_stream.flush()

    runner_summary = None
    if not args.aggregate_only:
        runner = HarnessRunner(
            args.out, args.config, args.backend, workers=args.workers,
            seed_limit=args.limit_pairs,
            conditions=("e_full_loop",), impact_cohort=args.cohort,
            server_ports=server_ports)
        runner_summary = runner.run_impact_pairs(resume=not args.no_resume)
    aggregate = aggregate_impact_pairs(args.out, args.config, cohort=args.cohort)
    write_impact_report(args.out, aggregate)
    print(json.dumps({
        "aggregate": os.path.abspath(os.path.join(args.out, "impact-aggregate.json")),
        "complete_pairs": aggregate["complete_pairs"],
        "cohort": aggregate["design"]["cohort"],
        "claim_status": aggregate["claim_evaluation"]["status"],
        "failures": len(aggregate["failures"]), "runner": runner_summary,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
