"""Adapter for the native FreeCiv `research_goal_*` parity executable."""

import json
import os
import random
import subprocess

from .service import CrispStateView, Goal


class NativeOracleError(RuntimeError):
    pass


class NativeResearchOracle:
    def __init__(self, image=None, timeout=120):
        self.image = image or os.environ.get(
            "FREECIV_PARITY_IMAGE", "freeciv-research-parity:local")
        self.timeout = timeout

    def query_states(self, ruleset, states):
        lines = []
        for state_id, known in states:
            lines.append("{}\t{}\n".format(state_id, "|".join(sorted(known))))
        command = ["docker", "run", "--rm", "-i", self.image, ruleset]
        try:
            process = subprocess.run(command, input="".join(lines), text=True,
                                     capture_output=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NativeOracleError("native FreeCiv oracle failed: {}".format(exc))
        if process.returncode != 0:
            raise NativeOracleError("native FreeCiv oracle exit {}: {}".format(
                process.returncode, process.stderr.strip()))
        grouped = {}
        for line_number, line in enumerate(process.stdout.splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise NativeOracleError("invalid native JSON at line {}: {}".format(
                    line_number, exc))
            grouped.setdefault(row["state_id"], {})[row["goal"]] = row
        expected_ids = {state_id for state_id, _ in states}
        if set(grouped) != expected_ids:
            raise NativeOracleError("native output state IDs do not match input")
        return grouped

    def image_identity(self):
        process = subprocess.run(
            ["docker", "image", "inspect", self.image, "--format", "{{.Id}}"],
            text=True, capture_output=True, timeout=30)
        if process.returncode != 0:
            raise NativeOracleError("native image is unavailable: {}".format(self.image))
        return process.stdout.strip()


def randomized_states(tech_names, count=50, seed=20260717):
    names = sorted(tech_names)
    rng = random.Random(seed)
    states = [("state-000", frozenset())]
    if count > 1:
        states.append(("state-001", frozenset(names)))
    for index in range(len(states), count):
        probability = rng.uniform(0.02, 0.92)
        known = frozenset(name for name in names if rng.random() < probability)
        states.append(("state-{:03d}".format(index), known))
    return states


def compare_all(ir, dependency_oracle, native_oracle, state_count=50,
                seed=20260717, player="parity-player"):
    tech_names = [rule.rule_name for rule in ir.rules if rule.target_kind == "tech"]
    states = randomized_states(tech_names, state_count, seed)
    native = native_oracle.query_states(ir.ruleset, states)
    mismatches = []
    comparisons = 0
    for state_id, known in states:
        state = CrispStateView(state_id, known_techs=known, player=player)
        for tech in sorted(tech_names):
            result = dependency_oracle.deps(Goal.researchable(player, tech), state)
            expected = tuple(sorted(native[state_id][tech]["required"]))
            actual = result.prerequisite_names
            comparisons += 1
            if expected != actual:
                mismatches.append({
                    "actual": list(actual), "expected": list(expected),
                    "goal": tech, "known": sorted(known), "state_id": state_id,
                    "status": result.status,
                })
    return {
        "comparisons": comparisons,
        "mismatches": mismatches,
        "passed": not mismatches,
        "ruleset": ir.ruleset,
        "seed": seed,
        "state_count": state_count,
        "tech_count": len(tech_names),
    }


def check_leaf_properties(ir, dependency_oracle, native_oracle, pair_count=100,
                          seed=20260717, player="property-player"):
    """Check the amended A1.2 semantics against engine-owned state transitions.

    A frontier tech must be researchable in the original state. Filling the full
    reported prerequisite set must make the target immediately researchable, and
    removing any compiled direct predecessor from that filled state must block it.
    """
    tech_rules = {rule.rule_name: rule for rule in ir.rules if rule.target_kind == "tech"}
    tech_names = sorted(tech_rules)
    base_states = randomized_states(tech_names, pair_count + 2, seed)[2:]
    rng = random.Random(seed + 1)
    selected = []
    for index, (_, known) in enumerate(base_states):
        unknown = [tech for tech in tech_names if tech not in known]
        goal = rng.choice(unknown or tech_names)
        selected.append(("pair-{:03d}".format(index), known, goal))
    native_base = native_oracle.query_states(
        ir.ruleset, [(state_id, known) for state_id, known, _ in selected])
    variants = []
    cases = []
    failures = []
    for index, (state_id, known, goal) in enumerate(selected):
        state = CrispStateView(state_id, known_techs=known, player=player)
        result = dependency_oracle.deps(Goal.researchable(player, goal), state)
        # Use atom IDs to recover frontier names losslessly from the proof.
        atom_by_id = {node["atom"]["atom_id"]: node["atom"] for node in result.proof["nodes"]}
        frontier_names = sorted({atom_by_id[item["atom_id"]]["args"][-1]
                                 for item in result.frontier
                                 if item["blocker_type"] == "missing-tech"})
        for leaf in frontier_names:
            if native_base[state_id][leaf]["goal_state"] != 1:
                failures.append({"case": index, "goal": goal, "leaf": leaf,
                                 "reason": "frontier leaf is not engine-researchable"})
        filled = frozenset(set(known) | set(result.prerequisite_names))
        filled_id = "filled-{:03d}".format(index)
        variants.append((filled_id, filled))
        direct = sorted({str(req.name) for req in tech_rules[goal].antecedents
                         if req.kind == "Tech" and req.present})
        omitted_ids = []
        for direct_index, predecessor in enumerate(direct):
            omitted_id = "omit-{:03d}-{:02d}".format(index, direct_index)
            variants.append((omitted_id, frozenset(set(filled) - {predecessor})))
            omitted_ids.append((omitted_id, predecessor))
        cases.append((index, goal, filled_id, omitted_ids))
    native_variants = native_oracle.query_states(ir.ruleset, variants)
    checks = 0
    for index, goal, filled_id, omitted_ids in cases:
        checks += 1
        if native_variants[filled_id][goal]["goal_state"] != 1:
            failures.append({"case": index, "goal": goal,
                             "reason": "full prerequisite set does not unlock goal"})
        for omitted_id, predecessor in omitted_ids:
            checks += 1
            if native_variants[omitted_id][goal]["goal_state"] == 1:
                failures.append({"case": index, "goal": goal,
                                 "omitted": predecessor,
                                 "reason": "omitted direct predecessor did not block goal"})
    return {"checks": checks, "failures": failures, "pair_count": pair_count,
            "passed": not failures, "ruleset": ir.ruleset, "seed": seed}
