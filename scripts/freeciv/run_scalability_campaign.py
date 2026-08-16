#!/usr/bin/env python3
"""Run the staged larger-AtomSpace/deep-proof/bridge/fluid campaign."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for candidate in (REPO, os.path.join(REPO, "src")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from benchmarks.freeciv.scaling.runner import (  # noqa: E402
    TIER_TABLES,
    environment_identity,
    freeze_campaign,
    initialize_campaign,
    payload_identity,
    run_cells,
    smoke_payloads,
    tier_payload,
)
from benchmarks.freeciv.scaling.design import (  # noqa: E402
    design_variants,
    timing_variant,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402


def _csv(value, convert=str):
    if value is None:
        return None
    rows = tuple(convert(row.strip()) for row in value.split(",") if row.strip())
    if not rows:
        raise SystemExit("comma-separated selections cannot be empty")
    return rows


def _parser():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in (
            "baseline", "smoke", "plan", "discovery", "freeze", "heldout"):
        command = commands.add_parser(name)
        command.add_argument(
            "--out", default="artifacts/freeciv/scalability-v1")
        if name in ("plan", "discovery", "freeze", "heldout"):
            command.add_argument(
                "--surface", choices=tuple(TIER_TABLES) + ("all",),
                default="all")
            command.add_argument(
                "--tiers", help="comma-separated explicit tiers")
            command.add_argument(
                "--design", choices=("tier", "primary"), default="tier",
                help=("tier runs one default variant; primary expands the "
                      "fixed preregistered screening matrix"))
            command.add_argument(
                "--seeds", type=int,
                default=(10 if name in ("plan", "discovery") else 40))
            command.add_argument(
                "--seed-offset", type=int,
                default=(
                    0 if name in ("plan", "discovery") else 100000))
            command.add_argument(
                "--timing-samples", type=int,
                default=(50 if name in ("freeze", "heldout") else None),
                help=("canonical isolated samples per tier; defaults to the "
                      "semantic seed count except for freeze/heldout (50)"))
            command.add_argument("--workers", type=int, default=1)
            command.add_argument(
                "--atom-topologies",
                help=("comma-separated atom topologies: local,chain,hub,"
                      "balanced_tree,shared_dag,distractor_shards,mixed"))
            command.add_argument(
                "--churn-fractions",
                help="comma-separated AtomSpace churn fractions in (0,1]")
            command.add_argument(
                "--support-multiplicities",
                help="comma-separated AtomSpace support multiplicities")
            command.add_argument(
                "--proof-shapes",
                help=("comma-separated proof shapes: chain,and_tree,"
                      "shared_dag,diamond_50,diamond_90,or_one_success,"
                      "or_several_success,or_unreachable,cycle_alternate,"
                      "cycle_only,grounded_blocker,binding_heavy"))
            command.add_argument(
                "--distractor-counts",
                help="comma-separated explicit proof distractor counts")
            command.add_argument(
                "--arms",
                help=("comma-separated bridge arms: scalar_pf_v2,"
                      "protected_message,corrected_probe,path_persistence,"
                      "source_sink_flow"))
            command.add_argument(
                "--topologies",
                help=("comma-separated bridge topologies: sparse_dag,"
                      "shared_dag,cyclic,disconnected_distractors,"
                      "asymmetric_legality,bottleneck,dynamic_failure"))
            command.add_argument(
                "--failure-fractions",
                help="comma-separated fluid edge-failure fractions in [0,1]")
            command.add_argument(
                "--captured-events",
                help="full-AtomRecord events.jsonl for captured trials")
            command.add_argument(
                "--captured-sha256",
                help="required SHA-256 of --captured-events")
            command.add_argument(
                "--turns",
                help="comma-separated captured turns (one trial per tier/turn)")
    return parser


def _selected_payloads(arguments):
    surfaces = tuple(TIER_TABLES) if arguments.surface == "all" else (arguments.surface,)
    if arguments.surface == "all" and not arguments.captured_events:
        surfaces = tuple(row for row in surfaces if row != "captured")
    explicit = set(arguments.tiers.split(",")) if arguments.tiers else None
    payloads = []
    for surface in surfaces:
        tiers = list(TIER_TABLES[surface])
        # Stretch tiers require separate explicit approval/selection.
        tiers = [tier for tier in tiers if tier not in ("A5", "P4", "B5", "F4")]
        if explicit is not None:
            tiers = [tier for tier in tiers if tier in explicit]
        if surface == "captured":
            if not (arguments.captured_events
                    and arguments.captured_sha256 and arguments.turns):
                raise SystemExit(
                    "captured trials require --captured-events, "
                    "--captured-sha256, and --turns")
            for tier in tiers:
                for turn in (
                        int(value) for value in arguments.turns.split(",")):
                    payloads.append(tier_payload(
                        surface, tier, turn,
                        overrides={
                            "events_path": arguments.captured_events,
                            "events_sha256": arguments.captured_sha256,
                            "turn": turn,
                        }))
            continue
        for tier in tiers:
            timing_samples = (
                arguments.timing_samples
                if arguments.timing_samples is not None else arguments.seeds)
            sample_count = (
                max(arguments.seeds, timing_samples)
                if surface in ("atomspace", "proof", "bridge", "fluid")
                else arguments.seeds)
            for index in range(sample_count):
                selections = {}
                if surface == "atomspace":
                    selections = {
                        "atom_topologies": _csv(arguments.atom_topologies),
                        "churn_fractions": _csv(
                            arguments.churn_fractions, float),
                        "support_multiplicities": _csv(
                            arguments.support_multiplicities, int),
                    }
                elif surface == "proof":
                    selections = {
                        "proof_shapes": _csv(arguments.proof_shapes),
                        "distractor_counts": _csv(
                            arguments.distractor_counts, int),
                    }
                elif surface == "bridge":
                    selections = {
                        "arms": _csv(arguments.arms),
                        "bridge_topologies": _csv(arguments.topologies),
                    }
                elif surface == "fluid":
                    selections = {
                        "failure_fractions": _csv(
                            arguments.failure_fractions, float),
                    }
                variants = design_variants(
                    surface, tier, design=arguments.design,
                    seed_index=index, **selections)
                if index >= arguments.seeds:
                    if arguments.design != "primary" or any(
                            value is not None for value in selections.values()):
                        variants = variants[:1]
                    else:
                        variants = (timing_variant(surface),)
                canonical = (
                    timing_variant(surface)
                    if arguments.design == "primary"
                    and surface in ("atomspace", "proof", "bridge", "fluid")
                    and not any(value is not None
                                for value in selections.values())
                    else None)
                for overrides in variants:
                    overrides = dict(overrides)
                    if (canonical is not None and all(
                            overrides.get(key) == value
                            for key, value in canonical.items())):
                        overrides["timing_block"] = index % 3
                        overrides["timing_sample"] = True
                    payloads.append(tier_payload(
                        surface, tier, arguments.seed_offset + index,
                        overrides=overrides))
    return payloads


def main(argv=None):
    arguments = _parser().parse_args(argv)
    if arguments.command == "baseline":
        result = initialize_campaign(arguments.out)
    elif arguments.command == "smoke":
        initialize_campaign(arguments.out)
        result = {"results": run_cells(
            arguments.out, smoke_payloads(), phase="discovery")}
    elif arguments.command == "plan":
        payloads = _selected_payloads(arguments)
        payload_ids = tuple(payload_identity(row) for row in payloads)
        if len(payload_ids) != len(set(payload_ids)):
            raise SystemExit("selected campaign contains duplicate cells")
        environment = environment_identity()
        result = {
            "artifact_type": "freeciv-scalability-selection-plan",
            "design": arguments.design,
            "payload_count": len(payloads),
            "payload_ids": list(payload_ids),
            "schema_version": "1.0",
            "semantic_seed_count": arguments.seeds,
            "selection_hash": structural_hash(list(payloads)),
            "source_identity": "{}:{}:{}".format(
                environment["git_commit"], environment["code_digest"],
                environment["measurement_contract_hash"]),
            "surface_counts": dict(
                (surface, sum(
                    row["surface"] == surface for row in payloads))
                for surface in sorted(set(
                    row["surface"] for row in payloads))),
            "timing_sample_count": (
                arguments.timing_samples
                if arguments.timing_samples is not None else arguments.seeds),
        }
    elif arguments.command == "discovery":
        if os.path.isfile(os.path.join(
                arguments.out, "frozen-preregistration.json")):
            raise SystemExit(
                "campaign is frozen; discovery tuning requires a new root")
        initialize_campaign(arguments.out)
        result = {"results": run_cells(
            arguments.out, _selected_payloads(arguments),
            phase=arguments.command, workers=arguments.workers)}
    elif arguments.command == "heldout":
        if arguments.workers != 1:
            raise SystemExit(
                "claim-eligible runner currently requires --workers 1")
        result = {"results": run_cells(
            arguments.out, _selected_payloads(arguments),
            phase=arguments.command, workers=arguments.workers)}
    else:
        result = freeze_campaign(
            arguments.out, _selected_payloads(arguments))
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
