#!/usr/bin/env python3
"""Run the PLN-FreeCiv cross-cutting release invariants and emit evidence."""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for candidate in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv_agent.config import belief_config  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.rulesets.audit import audit as audit_ruleset  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402


PINNED_FREECIV_COMMIT = "26ba7124249f34fd3050ef29bf191bd4d8808018"
PINNED_PROXY_PATCH_SHA256 = "283ff5c5554ac7fc709ec0294e14dab0be47d06f93e8fbdfa74283eb79f24802"
REQUIRED_CONFIDENCE_PARAMETERS = frozenset({
    "actionable_threshold", "minimum_logged_confidence", "dampening_lambda",
    "observation_strength", "observation_confidence", "abduction_strength",
    "abduction_confidence", "induction_default_probability",
    "induction_decision_threshold", "induction_minimum_samples", "decay", "sweep",
})


def _hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical_path(path):
    relative = os.path.relpath(os.path.abspath(path), REPO)
    return relative if relative != os.pardir and not relative.startswith(
        os.pardir + os.sep) else os.path.basename(path)


def _source_files(root, suffixes):
    for directory, names, files in os.walk(root):
        names[:] = [name for name in names if name not in {
            "__pycache__", "coverage", "dist", "node_modules", "proofshot-artifacts"}]
        for name in files:
            if name.endswith(suffixes):
                yield os.path.join(directory, name)


def _ancestry(event_id, parents):
    pending = list(parents.get(event_id, ()))
    found = set()
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(parents.get(current, ()))
    return found


def _trace_check(path, require_cognitive):
    report = validate_file(path, require_action_roots=True)
    details = {
        "events": report.event_count, "game_id": report.game_id,
        "max_bytes_per_turn": max(report.bytes_by_turn.values() or [0]),
        "path": _logical_path(path), "sha256": _hash_file(path),
        "validation_errors": [error.to_dict() for error in report.errors],
        "volume_budget_bytes_per_turn": 5 * 1024 * 1024,
    }
    if not report.valid:
        return False, details
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    declarations = {}
    for row in rows:
        if row["type"] != "metric_sample":
            continue
        payload = row["payload"]
        labels = payload.get("labels", {})
        if labels.get("declaration") != "release_configuration":
            continue
        declarations[(payload["name"], labels.get("predicate"))] = payload["value"]
    configured = belief_config()
    expected_declarations = {
        ("belief_{}".format(key), None): value
        for key, value in configured.items()
        if key not in ("decay", "schema_version", "sweep")}
    expected_declarations.update({
        ("belief_decay_window_turns", predicate): schedule["window_turns"]
        for predicate, schedule in configured["decay"].items()})
    missing_declarations = [
        {"metric": key[0], "predicate": key[1], "expected": value}
        for key, value in sorted(expected_declarations.items(), key=str)
        if declarations.get(key) != value]
    details["confidence_declarations"] = len(declarations)
    details["missing_confidence_declarations"] = missing_declarations
    parents = {row["event_id"]: row["caused_by"] for row in rows}
    types = {row["event_id"]: row["type"] for row in rows}
    results = {row["payload"]["action_id"] for row in rows
               if row["type"] == "action_result"}
    planned = []
    incomplete = []
    for row in rows:
        if row["type"] != "action_sent":
            continue
        payload = row["payload"]
        action_type = payload.get("action", {}).get(
            "action_type", payload.get("action", {}).get("type"))
        if payload.get("plan_id") is None or action_type == "end_turn":
            continue
        planned.append(payload["action_id"])
        ancestors = _ancestry(row["event_id"], parents)
        ancestor_types = {types.get(event_id) for event_id in ancestors}
        absent = sorted({
            "state_snapshot", "verification", "pln_result", "plan_created",
        } - ancestor_types)
        if not {"llm_proposal", "goal_selection"} & ancestor_types:
            absent.append("llm_proposal|goal_selection")
        if absent or payload["action_id"] not in results:
            incomplete.append({
                "action_id": payload["action_id"], "missing_ancestry": absent,
                "missing_result": payload["action_id"] not in results,
            })
    details["planned_cognitive_actions"] = planned
    details["incomplete_planned_actions"] = incomplete
    passed = (not incomplete and not missing_declarations
              and details["max_bytes_per_turn"] <= 5 * 1024 * 1024)
    return passed and (bool(planned) if require_cognitive else True), details


def run(args):
    checks = []

    def record(identifier, passed, details):
        checks.append({"id": identifier, "passed": bool(passed), "details": details})

    metta = []
    handwritten = []
    for root in (os.path.join(REPO, "benchmarks", "freeciv"),
                 os.path.join(REPO, "src", "freeciv_agent"),
                 os.path.join(REPO, "Autotests")):
        for path in _source_files(root, (".metta",)):
            metta.append(_logical_path(path))
            source = open(path, encoding="utf-8").read()
            if any(token in source for token in (
                    "(Implication", "(researchable ", "(has-tech ", "(buildable ")):
                handwritten.append(_logical_path(path))
    record("no-handwritten-game-rules", not handwritten, {
        "metta_sources_in_freeciv_domains": sorted(metta),
        "handwritten_game_rule_files": sorted(handwritten),
        "legacy_rules_absent": not os.path.exists(
            os.path.join(REPO, "benchmarks", "freeciv", "rules.metta")),
    })

    boundary = subprocess.run(
        ["node", "scripts/check-boundaries.mjs"],
        cwd=os.path.join(REPO, "apps", "freeciv-observability"),
        text=True, capture_output=True, timeout=30)
    record("ui-event-only-boundary", boundary.returncode == 0, {
        "stdout": boundary.stdout.strip(), "stderr": boundary.stderr.strip()})

    forbidden_imports = []
    forbidden_symbols = {"ProxyStateDTO", "AuthoritativeSnapshot", "SnapshotStore"}
    llm_root = os.path.join(REPO, "src", "freeciv_agent", "llm")
    for path in _source_files(llm_root, (".py",)):
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if (module.endswith(("state.dto", "state.snapshot", "state.store"))
                        or forbidden_symbols.intersection(item.name for item in node.names)):
                    forbidden_imports.append(
                        "{}:{}".format(_logical_path(path), node.lineno))
            elif isinstance(node, ast.Import) and any(item.name.endswith(
                    ("state.dto", "state.snapshot", "state.store")) for item in node.names):
                forbidden_imports.append("{}:{}".format(_logical_path(path), node.lineno))
    record("llm-query-summary-only", not forbidden_imports,
           {"forbidden_imports": forbidden_imports})

    configured = belief_config()
    missing = sorted(REQUIRED_CONFIDENCE_PARAMETERS - set(configured))
    record("confidence-parameters-declared", not missing, {
        "declared": sorted(configured), "missing": missing,
        "configuration_hash": hashlib.sha256(json.dumps(
            configured, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    })

    compiled = {}
    numeric_conclusions = []
    forbidden_conclusions = {
        "add", "sum", "accumulate", "gold-stockpile", "shield-stockpile",
        "beakers-per-turn", "shields-per-turn",
    }
    for ruleset in ("civ2civ3", "classic"):
        ir = compile_ruleset(args.ruleset_root, ruleset)
        report = audit_ruleset(ir, args.ruleset_root)
        compiled[ruleset] = {
            "audit_passed": report["passed"], "counts": report["counts"],
            "rules": len(ir.rules), "source_hashes": ir.source_hashes,
            "grounded_signatures": [row["name"] for row in ir.grounded_signatures],
        }
        numeric_conclusions.extend(
            "{}:{}".format(ruleset, rule.rule_id) for rule in ir.rules
            if rule.target_predicate in forbidden_conclusions)
    record("compiled-ruleset-independent-audit",
           all(row["audit_passed"] for row in compiled.values()), compiled)
    record("no-numeric-accumulation-in-inference", not numeric_conclusions, {
        "compiled": compiled, "numeric_conclusions": numeric_conclusions})

    absolute_paths = []
    for relative in ("src/freeciv_agent", "benchmarks/freeciv/harness",
                     "scripts/freeciv", "apps/freeciv-observability/src"):
        for path in _source_files(os.path.join(REPO, relative),
                                  (".py", ".ts", ".tsx", ".js", ".mjs", ".sh")):
            for line_number, line in enumerate(open(path, encoding="utf-8"), 1):
                if re.search(r"/(?:home|Users)/[^/\s]+/", line):
                    absolute_paths.append("{}:{}".format(_logical_path(path), line_number))
    record("no-workstation-paths", not absolute_paths,
           {"absolute_path_locations": absolute_paths})

    patch_path = os.path.join(
        REPO, "scripts", "freeciv", "upstream", "0001-pln-authoritative-state.patch")
    external = {
        "pinned_commit": PINNED_FREECIV_COMMIT, "patch": _logical_path(patch_path),
        "patch_sha256": _hash_file(patch_path),
    }
    external_passed = external["patch_sha256"] == PINNED_PROXY_PATCH_SHA256
    if args.freeciv_llm_root:
        commit = subprocess.run(
            ["git", "-C", args.freeciv_llm_root, "rev-parse", "HEAD"],
            text=True, capture_output=True)
        reverse = subprocess.run(
            ["git", "-C", args.freeciv_llm_root, "apply", "--reverse", "--check", patch_path],
            text=True, capture_output=True)
        external.update({"checkout_commit": commit.stdout.strip(),
                         "patch_applied": reverse.returncode == 0})
        external_passed = (commit.returncode == 0
                           and commit.stdout.strip() == PINNED_FREECIV_COMMIT
                           and reverse.returncode == 0)
    record("pinned-external-contract", external_passed, external)

    pf_audit = subprocess.run(
        [sys.executable, os.path.join(
            REPO, "scripts", "freeciv", "audit_pf_pln.py")],
        cwd=REPO, text=True, capture_output=True, timeout=60)
    try:
        pf_report = json.loads(pf_audit.stdout)
    except (TypeError, ValueError):
        pf_report = None
    record("pf-pln-phase-readiness", (
        pf_audit.returncode == 0
        and isinstance(pf_report, dict)
        and pf_report.get("passed") is True
    ), {
        "report": pf_report,
        "stderr": pf_audit.stderr.strip(),
    })

    for path in args.events:
        passed, details = _trace_check(path, args.require_cognitive_trace)
        record("validated-trace:" + _logical_path(path), passed, details)
    return {"schema_version": "1.0", "passed": all(
        check["passed"] for check in checks), "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ruleset-root", default=os.environ.get("FREECIV_RULESET_ROOT"))
    parser.add_argument("--freeciv-llm-root", default=os.environ.get("FREECIV_LLM_ROOT"))
    parser.add_argument("--events", action="append", default=[])
    parser.add_argument("--require-cognitive-trace", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if not args.ruleset_root:
        parser.error("--ruleset-root or FREECIV_RULESET_ROOT is required")
    result = run(args)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        parent = os.path.dirname(os.path.abspath(args.output))
        if parent:
            os.makedirs(parent, exist_ok=True)
        temporary = os.path.abspath(args.output) + ".tmp.{}".format(os.getpid())
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(rendered)
        os.replace(temporary, os.path.abspath(args.output))
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
