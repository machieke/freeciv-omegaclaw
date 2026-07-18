#!/usr/bin/env python3
"""Report byte savings from structural proof-subtree deduplication."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events import model  # noqa: E402
from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402


def report(repetitions=40):
    leaf_atom = model.atom("known-alphabet", "has-tech", ["player", "Alphabet"])
    leaves = [model.proof_node("leaf-{:03d}".format(index), "premise", leaf_atom, True)
              for index in range(repetitions)]
    goal = model.atom("research-writing", "researchable", ["player", "Writing"])
    root = model.proof_node(
        "root", "and", goal, True, rule_applied="compiled:tech:Writing",
        premise_node_refs=[node["node_id"] for node in leaves],
    )
    expanded = model.proof_tree("root", leaves + [root])
    compact = model.deduplicate_proof_tree(expanded)
    expanded_bytes = len(canonical_json_bytes(expanded))
    compact_bytes = len(canonical_json_bytes(compact))
    return {
        "compact_bytes": compact_bytes,
        "compact_nodes": len(compact["nodes"]),
        "expanded_bytes": expanded_bytes,
        "expanded_nodes": len(expanded["nodes"]),
        "repetitions": repetitions,
        "saved_bytes": expanded_bytes - compact_bytes,
        "savings_percent": round(100.0 * (expanded_bytes - compact_bytes) / expanded_bytes, 2),
        "structural_hash_stable": expanded["structural_hash"] == compact["structural_hash"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=40)
    args = parser.parse_args(argv)
    if args.repetitions < 2:
        parser.error("--repetitions must be at least 2")
    print(json.dumps(report(args.repetitions), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
