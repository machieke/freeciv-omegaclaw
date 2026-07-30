#!/usr/bin/env python3
"""Run generated movement/combat cases against an external native oracle."""

import argparse
import json
import os
import shlex
import sys


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.oracle import (  # noqa: E402
    NativeGameplayOracle,
    compare_native_gameplay_cases,
)


def _load_corpus(path):
    with open(path, encoding="utf-8") as stream:
        value = json.load(stream)
    if (not isinstance(value, dict)
            or value.get(
                "schema_version") != "1.0"
            or not isinstance(
                value.get("cases"), list)
            or not value["cases"]):
        raise ValueError(
            "parity corpus must be a 1.0 object with a non-empty cases array")
    return value


def _command(value):
    value = value or os.environ.get(
        "FREECIV_GAMEPLAY_PARITY_COMMAND")
    if not value:
        raise ValueError(
            "set --oracle-command or "
            "FREECIV_GAMEPLAY_PARITY_COMMAND")
    command = tuple(shlex.split(
        value))
    if not command:
        raise ValueError(
            "native gameplay parity command is empty")
    return command


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--input", required=True,
        help="generated parity corpus JSON")
    parser.add_argument(
        "--oracle-command",
        help="external executable command; shell quoting is parsed, "
             "but no shell is invoked")
    parser.add_argument(
        "--oracle-identity",
        required=True,
        help="versioned native binary/image identity")
    parser.add_argument(
        "--output", required=True)
    parser.add_argument(
        "--timeout-seconds",
        default=5.0, type=float)
    args = parser.parse_args(argv)

    corpus = _load_corpus(
        args.input)
    report = compare_native_gameplay_cases(
        NativeGameplayOracle(
            _command(
                args.oracle_command),
            args.oracle_identity,
            timeout_seconds=(
                args.timeout_seconds)),
        corpus["cases"])
    report["corpus_id"] = corpus.get(
        "corpus_id")
    report["generator_identity"] = (
        corpus.get("generator_identity"))
    report["ruleset_digest"] = corpus.get(
        "ruleset_digest")
    report["report_hash"] = structural_hash({
        key: value
        for key, value in report.items()
        if key != "report_hash"
    })
    with open(
            args.output, "wb") as stream:
        stream.write(
            canonical_json_bytes(
                report))
        stream.write(b"\n")
    print(json.dumps(
        {
            "case_count":
                report["case_count"],
            "mismatch_count":
                report[
                    "mismatch_count"],
            "output": args.output,
            "passed": report["passed"],
            "report_hash":
                report["report_hash"],
        },
        sort_keys=True))
    return 0 if report[
        "passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
