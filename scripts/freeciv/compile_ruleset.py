#!/usr/bin/env python3
"""Compile and independently audit one pinned FreeCiv ruleset."""

import argparse
import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.rulesets.audit import audit  # noqa: E402
from freeciv_agent.rulesets.compiler import (  # noqa: E402
    COMPILER_VERSION, canonical_json, compile_ruleset, render_metta,
)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _write(path, data):
    with open(path, "wb") as handle:
        handle.write(data)


def compile_to_directory(ruleset_root, ruleset, out, event_log=None):
    ir = compile_ruleset(ruleset_root, ruleset)
    report = audit(ir, ruleset_root)
    if not report["passed"]:
        raise RuntimeError("independent ruleset audit failed")
    os.makedirs(out, exist_ok=True)
    ir_bytes = canonical_json(ir.to_dict())
    metta_bytes = render_metta(ir).encode("utf-8")
    audit_bytes = canonical_json(report)
    signature_bytes = canonical_json({"schema_version": "1.0",
                                      "signatures": list(ir.grounded_signatures)})
    markdown = (
        "# Generated ruleset audit: {ruleset}\n\n"
        "Compiler: `{compiler}`\n\n"
        "- Target rules: {target_rules}\n"
        "- Tech rules: {tech_rules}\n"
        "- Unit rules: {unit_rules}\n"
        "- Building rules: {building_rules}\n"
        "- Prerequisite edges: {prerequisite_edges}\n"
        "- Independent audit: PASS\n"
        "- Sample seed: {seed}\n"
        "- Tech samples: {tech_samples}\n"
        "- Unit samples: {unit_samples}\n"
    ).format(
        ruleset=ruleset, compiler=COMPILER_VERSION, seed=report["sample_seed"],
        tech_samples=", ".join(report["samples"]["tech"]),
        unit_samples=", ".join(report["samples"]["unit"]), **report["counts"]
    ).encode("utf-8")
    outputs = {
        "audit.json": audit_bytes,
        "audit.md": markdown,
        "grounded-signatures.json": signature_bytes,
        "ruleset.ir.json": ir_bytes,
        "ruleset.metta": metta_bytes,
    }
    output_hashes = {name: _hash(data) for name, data in sorted(outputs.items())}
    combined_source = canonical_json(ir.source_hashes)
    manifest = {
        "compiler_version": COMPILER_VERSION,
        "output_hashes": output_hashes,
        "ruleset": ruleset,
        "schema_version": "1.0",
        "source_hash": _hash(combined_source),
        "source_hashes": ir.source_hashes,
    }
    outputs["manifest.json"] = canonical_json(manifest)
    for name, data in sorted(outputs.items()):
        _write(os.path.join(out, name), data)
    if event_log:
        writer = EventWriter(event_log, "ruleset-compile-{}".format(ruleset))
        writer.emit("ruleset_compiled", 0, {
            "atomese_hash": output_hashes["ruleset.metta"],
            "counts": report["counts"],
            "ir_hash": output_hashes["ruleset.ir.json"],
            "ruleset": ruleset,
            "source_hash": manifest["source_hash"],
        })
    return manifest, report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--ruleset-root", default=os.environ.get("FREECIV_RULESET_ROOT"),
                        help="directory containing civ2civ3/ and classic/")
    parser.add_argument("--ruleset", required=True, choices=("civ2civ3", "classic"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--event-log")
    args = parser.parse_args(argv)
    if not args.ruleset_root:
        parser.error("--ruleset-root or FREECIV_RULESET_ROOT is required")
    manifest, report = compile_to_directory(args.ruleset_root, args.ruleset,
                                            args.out, args.event_log)
    print(json.dumps({"manifest": manifest, "audit": report}, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
