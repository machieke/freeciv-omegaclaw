"""Deterministic V0 good, adversarial, and performance traces."""

import argparse
import copy
import json
import os
import sys

from .model import atom, plan, plan_step, proof_node, proof_tree, truth_value
from .schema import canonical_json_bytes, structural_hash
from .validator import validate_file
from .writer import EventWriter


GOOD_SCENARIOS = (
    "normal-crisp",
    "unreachable",
    "invalidation-repair",
    "decay-rescout",
    "provenance-multipath",
    "quarantine-40",
)
BAD_SCENARIOS = (
    "bad-orphan-action",
    "bad-crisp-drift",
    "bad-duplicate-provenance",
    "bad-write-through",
    "bad-seq-gap",
)
ALL_SCENARIOS = GOOD_SCENARIOS + BAD_SCENARIOS


class DeterministicIds(object):
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 1
        return "event-{:06d}".format(self.value)


def fixed_clock():
    return "2026-01-01T00:00:00Z"


def _writer(path, game_id):
    return EventWriter(
        path, game_id, clock=fixed_clock, id_factory=DeterministicIds(), durable=False)


def _run_started(writer, condition="e_full_loop"):
    return writer.emit("run_started", 0, {
        "manifest_identity": "0" * 64,
        "condition_id": condition,
    })


def _snapshot(writer, turn, parent, snapshot_id=None, uncertain_atoms=None, own_state=None):
    sid = snapshot_id or "snapshot-{}".format(turn)
    payload = {
        "snapshot_id": sid,
        "player_id": 1,
        "state_hash": structural_hash(own_state or {"turn": turn}),
        "own_state": own_state or {"turn": turn, "techs": ["Alphabet"], "gold": 20},
        "uncertain_atoms": list(uncertain_atoms or []),
        "map": {"width": 10, "height": 10, "visible": [[1, 1]]},
    }
    return writer.emit("state_snapshot", turn, payload, caused_by=[parent["event_id"]])


def _simple_proof(goal, satisfied=True, uncertain=False, multi_path=False):
    leaf_tv = truth_value(0.8, 0.7) if uncertain else truth_value()
    premise = proof_node(
        "node-premise", "premise",
        atom("atom-premise", "has-tech", ["player-1", "Alphabet"],
             tv=leaf_tv, crisp=not uncertain, provenance_ids=(["prov-1"] if uncertain else [])),
        satisfied, tv=leaf_tv, crisp=not uncertain)
    nodes = [premise]
    refs = [premise["node_id"]]
    if multi_path:
        alternative = proof_node(
            "node-alternative", "premise",
            atom("atom-alternative", "observed-unit", ["enemy-1", "Phalanx"],
                 tv=leaf_tv, crisp=False, provenance_ids=["prov-1"]),
            True, tv=leaf_tv, crisp=False)
        nodes.append(alternative)
        branch = proof_node(
            "node-or", "or",
            atom("atom-or", "has-tech", ["enemy-1", "Bronze Working"],
                 tv=leaf_tv, crisp=False, provenance_ids=["prov-1"]),
            True, rule_applied="abduction", premise_node_refs=[premise["node_id"], alternative["node_id"]],
            tv=leaf_tv, crisp=False, formula={"name": "provenance-union", "inputs": {"paths": 2}},
            dampening_lambda=0.1)
        nodes.append(branch)
        refs = [branch["node_id"]]
    root = proof_node(
        "node-goal", "goal", goal, satisfied,
        rule_applied="compiled:goal", premise_node_refs=refs,
        tv=(leaf_tv if uncertain else truth_value()), crisp=not uncertain,
        formula=({"name": "deduction", "inputs": {"lambda": 0.1}} if uncertain else None),
        dampening_lambda=(0.1 if uncertain else None))
    nodes.append(root)
    return proof_tree(root["node_id"], nodes)


def _proposal(writer, turn, snapshot, goal, claims=None):
    return writer.emit("llm_proposal", turn, {
        "proposal_id": "proposal-{}".format(turn),
        "model": "synthetic-model",
        "prompt_version": "v1",
        "goals": [{"goal_atom_id": goal["atom_id"], "predicate": goal["predicate"], "args": goal["args"]}],
        "claims": list(claims or []),
    }, caused_by=[snapshot["event_id"]])


def _query_result(writer, turn, parent, goal, proof, status="PROVED", frontier=None,
                  invoking_layer="planner", query_id=None, latency=1.0, depth=2, dampening=None):
    qid = query_id or "query-{}-{}".format(turn, parent["seq"])
    query = writer.emit("pln_query", turn, {
        "query_id": qid, "query_atom": goal, "query_type": "deps",
        "invoking_layer": invoking_layer,
    }, caused_by=[parent["event_id"]])
    result = writer.emit("pln_result", turn, {
        "query_id": qid, "status": status, "proof": proof,
        "unsatisfied_frontier": list(frontier or []), "latency_ms": float(latency),
        "chain_depth": int(depth), "dampening_lambda": dampening,
    }, caused_by=[query["event_id"]])
    return query, result


def generate_normal(path):
    writer = _writer(path, "synthetic-normal-crisp")
    started = _run_started(writer)
    snapshot = _snapshot(writer, 1, started)
    goal = atom("goal-pottery", "researchable", ["player-1", "Pottery"])
    proposal = _proposal(writer, 1, snapshot, goal, [{
        "claim_id": "claim-1", "text": "Alphabet is known",
        "atom": atom("known-alphabet", "has-tech", ["player-1", "Alphabet"]),
    }])
    verification = writer.emit("verification", 1, {
        "verification_id": "verification-1", "proposal_id": "proposal-1",
        "claim_id": "claim-1", "verdict": "believe", "check": "authoritative-state",
        "evidence_atom_ids": ["known-alphabet"],
    }, caused_by=[proposal["event_id"], snapshot["event_id"]])
    _, result = _query_result(writer, 1, verification, goal, _simple_proof(goal))
    step = plan_step("step-1", "research", {"tech": "Pottery"}, 2, status="ACTIVE", cost=1)
    p = plan("plan-1", goal["atom_id"], result["payload"]["proof"]["structural_hash"],
             "snapshot-1", [step], scheduler_cost=1)
    created = writer.emit("plan_created", 1, {"plan": p}, caused_by=[result["event_id"]])
    executed = writer.emit("plan_step_executed", 1, {
        "plan_id": "plan-1", "step_id": "step-1", "snapshot_id": "snapshot-1", "status": "started",
    }, caused_by=[created["event_id"]])
    sent = writer.emit("action_sent", 1, {
        "action_id": "action-1", "action": {"type": "tech_research", "tech_name": "Pottery"},
        "snapshot_id": "snapshot-1", "legal_actions_digest": "1" * 64,
        "plan_id": "plan-1", "step_id": "step-1",
    }, caused_by=[executed["event_id"]])
    action_result = writer.emit("action_result", 1, {
        "action_id": "action-1", "status": "accepted", "engine_response": {"ok": True}, "engine_turn": 1,
    }, caused_by=[sent["event_id"]])
    metric = writer.emit("metric_sample", 1, {
        "name": "loop_latency_ms", "value": 10.0, "unit": "ms", "labels": {"condition": "e"},
    }, caused_by=[action_result["event_id"]])
    writer.emit("run_completed", 2, {"status": "completed", "summary": {"actions": 1}},
                caused_by=[metric["event_id"]])


def generate_unreachable(path):
    writer = _writer(path, "synthetic-unreachable")
    started = _run_started(writer)
    snapshot = _snapshot(writer, 1, started)
    goal = atom("goal-disabled", "researchable", ["player-1", "Disabled Tech"])
    proposal = _proposal(writer, 1, snapshot, goal)
    blocker = proof_node("node-disabled", "unreachable", goal, False)
    proof = proof_tree("node-disabled", [blocker])
    frontier = [{"node_id": "node-disabled", "blocker_type": "disabled-goal",
                 "atom_id": goal["atom_id"], "detail": "ruleset marks goal Never"}]
    _, result = _query_result(writer, 1, proposal, goal, proof, status="UNREACHABLE", frontier=frontier, depth=0)
    writer.emit("run_completed", 1, {"status": "completed", "summary": {"unreachable": 1}},
                caused_by=[result["event_id"]])


def generate_invalidation(path):
    writer = _writer(path, "synthetic-invalidation")
    started = _run_started(writer)
    uncertain = atom("chokepoint-clear", "tile-clear", [4, 4],
                     tv=truth_value(0.8, 0.7), crisp=False, provenance_ids=["prov-scout"])
    snapshot = _snapshot(writer, 1, started, uncertain_atoms=[uncertain])
    goal = atom("goal-expand", "buildable", ["city-1", "Settlers"])
    proposal = _proposal(writer, 1, snapshot, goal)
    _, result = _query_result(writer, 1, proposal, goal, _simple_proof(goal))
    assumption = {"atom_id": "chokepoint-clear", "threshold": 0.6,
                  "accepted_tv": truth_value(0.8, 0.7), "affected_step_ids": ["step-cross"]}
    p = plan("plan-expand", goal["atom_id"], result["payload"]["proof"]["structural_hash"],
             "snapshot-1", [plan_step("step-cross", "move", {"tile": [4, 4]}, 3, status="ACTIVE",
                                      cost=2, spatial={"x": 4, "y": 4})],
             scheduler_cost=2, assumptions=[assumption])
    created = writer.emit("plan_created", 1, {"plan": p}, caused_by=[result["event_id"]])
    observed_atom = atom("enemy-at-choke", "at", ["enemy-7", 4, 4],
                         tv=truth_value(1.0, 0.9), crisp=False, provenance_ids=["prov-enemy"])
    observation = writer.emit("observation", 2, {
        "observation_id": "obs-enemy", "provenance_id": "prov-enemy", "atom": observed_atom,
        "source": "visible-map", "age_turns": 0,
    }, caused_by=[created["event_id"]])
    revised_atom = copy.deepcopy(uncertain)
    revised_atom["tv"] = truth_value(0.1, 0.9)
    revision = writer.emit("revision", 2, {
        "target_atom": revised_atom, "prior_tv": truth_value(0.8, 0.7),
        "evidence_tv": truth_value(0.0, 0.9), "posterior_tv": truth_value(0.1, 0.9),
        "provenance_id": "prov-enemy", "operation": "apply",
        "formula": {"name": "revision", "inputs": {"conflict": True}},
    }, caused_by=[observation["event_id"]])
    trigger = writer.emit("monitor_trigger", 2, {
        "trigger_id": "trigger-1", "atom_id": "chokepoint-clear",
        "prior_tv": truth_value(0.8, 0.7), "posterior_tv": truth_value(0.1, 0.9),
        "threshold": 0.6, "affected_plan_ids": ["plan-expand"],
    }, caused_by=[revision["event_id"]])
    invalidated = writer.emit("plan_invalidated", 2, {
        "plan_id": "plan-expand", "reason": "assumption_below_threshold",
        "broken_assumption": assumption, "affected_step_ids": ["step-cross"],
        "reused_subtree_hashes": ["2" * 64], "rederived_subtree_hashes": ["3" * 64],
    }, caused_by=[trigger["event_id"]])
    repair_goal = atom("goal-repair", "buildable", ["city-1", "Warriors"])
    _, repaired_result = _query_result(
        writer, 2, invalidated, repair_goal, _simple_proof(repair_goal), invoking_layer="monitor",
        query_id="repair-query")
    replacement = plan(
        "plan-repair", repair_goal["atom_id"], repaired_result["payload"]["proof"]["structural_hash"],
        "snapshot-1", [plan_step("step-defend", "produce", {"unit": "Warriors"}, 4, cost=2)],
        scheduler_cost=2, reused=["2" * 64], rederived=["3" * 64])
    writer.emit("plan_created", 2, {"plan": replacement},
                caused_by=[invalidated["event_id"], repaired_result["event_id"]])


def generate_decay(path):
    writer = _writer(path, "synthetic-decay")
    started = _run_started(writer)
    enemy = atom("enemy-at-3-3", "at", ["enemy-1", 3, 3],
                 tv=truth_value(1.0, 0.8), crisp=False, provenance_ids=["prov-seen"])
    snapshot = _snapshot(writer, 1, started, uncertain_atoms=[enemy])
    observation = writer.emit("observation", 1, {
        "observation_id": "obs-seen", "provenance_id": "prov-seen", "atom": enemy,
        "source": "visible-map", "age_turns": 0,
    }, caused_by=[snapshot["event_id"]])
    applied = writer.emit("revision", 1, {
        "target_atom": enemy, "prior_tv": None, "evidence_tv": truth_value(1.0, 0.8),
        "posterior_tv": truth_value(1.0, 0.8), "provenance_id": "prov-seen", "operation": "apply",
        "formula": {"name": "revision", "inputs": {"new": True}},
    }, caused_by=[observation["event_id"]])
    decayed = copy.deepcopy(enemy)
    decayed["tv"] = truth_value(1.0, 0.3)
    decay = writer.emit("revision", 5, {
        "target_atom": decayed, "prior_tv": truth_value(1.0, 0.8),
        "evidence_tv": truth_value(1.0, 0.3), "posterior_tv": truth_value(1.0, 0.3),
        "provenance_id": "prov-seen", "operation": "decay",
        "formula": {"name": "exponential-decay", "inputs": {"age": 4, "window": 4}},
    }, caused_by=[applied["event_id"]])
    scout_goal = atom("goal-rescout", "usable-action", ["unit-scout", "move", 3, 3])
    _proposal(writer, 5, {"event_id": decay["event_id"]}, scout_goal)


def generate_provenance(path):
    writer = _writer(path, "synthetic-provenance")
    started = _run_started(writer)
    seen = atom("seen-phalanx", "observed-unit", ["enemy-1", "Phalanx"],
                tv=truth_value(1.0, 0.8), crisp=False, provenance_ids=["prov-1"])
    snapshot = _snapshot(writer, 1, started, uncertain_atoms=[seen])
    observation = writer.emit("observation", 1, {
        "observation_id": "obs-1", "provenance_id": "prov-1", "atom": seen,
        "source": "visible-map", "age_turns": 0,
    }, caused_by=[snapshot["event_id"]])
    inferred = atom("enemy-bronze", "has-tech", ["enemy-1", "Bronze Working"],
                    tv=truth_value(0.8, 0.7), crisp=False, provenance_ids=["prov-1"])
    revision = writer.emit("revision", 1, {
        "target_atom": inferred, "prior_tv": None, "evidence_tv": truth_value(0.8, 0.7),
        "posterior_tv": truth_value(0.8, 0.7), "provenance_id": "prov-1", "operation": "apply",
        "formula": {"name": "abduction", "inputs": {"paths": 3, "unique_provenance": 1}},
    }, caused_by=[observation["event_id"]])
    _query_result(writer, 1, revision, inferred, _simple_proof(inferred, uncertain=True, multi_path=True),
                  invoking_layer="test", dampening=0.1)


def generate_quarantine(path):
    writer = _writer(path, "synthetic-quarantine")
    started = _run_started(writer)
    snapshot = _snapshot(writer, 1, started)
    claims = [{"claim_id": "false-{:02d}".format(index),
               "text": "Known-false claim {}".format(index), "atom": None}
              for index in range(40)]
    goal = atom("goal-safe", "researchable", ["player-1", "Pottery"])
    proposal = _proposal(writer, 1, snapshot, goal, claims)
    last = proposal
    for index, claim in enumerate(claims):
        verification = writer.emit("verification", 1, {
            "verification_id": "verify-{:02d}".format(index), "proposal_id": "proposal-1",
            "claim_id": claim["claim_id"], "verdict": "quarantine",
            "check": "unknown-or-false", "evidence_atom_ids": [],
        }, caused_by=[proposal["event_id"]])
        last = writer.emit("quarantine", 1, {
            "quarantine_id": "quarantine-{:02d}".format(index), "proposal_id": "proposal-1",
            "claim_id": claim["claim_id"], "claim": claim["text"],
            "failed_check": "unknown-or-false", "evidence_atoms": [],
        }, caused_by=[verification["event_id"]])
    writer.emit("metric_sample", 1, {
        "name": "confabulation_write_through", "value": 0.0, "unit": "claims",
        "labels": {"fixture": "quarantine-40"},
    }, caused_by=[last["event_id"]])


def generate_bad_orphan(path):
    writer = _writer(path, "synthetic-bad-orphan")
    writer.emit("action_sent", 1, {
        "action_id": "orphan", "action": {"type": "end_turn"}, "snapshot_id": "missing",
        "legal_actions_digest": "0" * 64, "plan_id": None, "step_id": None,
    })


def generate_bad_crisp(path):
    writer = _writer(path, "synthetic-bad-crisp")
    started = _run_started(writer)
    snapshot = _snapshot(writer, 1, started)
    goal = atom("goal-drift", "researchable", ["player-1", "Pottery"], tv=truth_value(0.8, 0.99))
    proposal = _proposal(writer, 1, snapshot, goal)
    proof = _simple_proof(goal)
    _query_result(writer, 1, proposal, goal, proof)


def generate_bad_duplicate_provenance(path):
    writer = _writer(path, "synthetic-bad-provenance")
    started = _run_started(writer)
    target = atom("belief-1", "at", ["enemy", 1, 1],
                  tv=truth_value(1, 0.6), crisp=False, provenance_ids=["prov-dup"])
    parent = started
    for index in range(2):
        parent = writer.emit("revision", 1, {
            "target_atom": target, "prior_tv": (None if index == 0 else truth_value(1, 0.6)),
            "evidence_tv": truth_value(1, 0.6), "posterior_tv": truth_value(1, 0.6),
            "provenance_id": "prov-dup", "operation": "apply",
            "formula": {"name": "revision", "inputs": {"index": index}},
        }, caused_by=[parent["event_id"]])


def generate_bad_write_through(path):
    writer = _writer(path, "synthetic-bad-write-through")
    started = _run_started(writer)
    writer.emit("metric_sample", 1, {
        "name": "confabulation_write_through", "value": 1.0, "unit": "claims", "labels": {},
    }, caused_by=[started["event_id"]])


def generate_bad_seq(path):
    writer = _writer(path, "synthetic-bad-seq")
    started = _run_started(writer)
    _snapshot(writer, 1, started)
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    rows[-1]["seq"] = 3
    with open(path, "wb") as stream:
        for row in rows:
            stream.write(canonical_json_bytes(row) + b"\n")


GENERATORS = {
    "normal-crisp": generate_normal,
    "unreachable": generate_unreachable,
    "invalidation-repair": generate_invalidation,
    "decay-rescout": generate_decay,
    "provenance-multipath": generate_provenance,
    "quarantine-40": generate_quarantine,
    "bad-orphan-action": generate_bad_orphan,
    "bad-crisp-drift": generate_bad_crisp,
    "bad-duplicate-provenance": generate_bad_duplicate_provenance,
    "bad-write-through": generate_bad_write_through,
    "bad-seq-gap": generate_bad_seq,
}


def generate_performance(path, turns=200, atoms_per_turn=250):
    writer = _writer(path, "synthetic-performance")
    parent = _run_started(writer)
    for turn in range(1, turns + 1):
        atoms = [atom(
            "perf-{}-{}".format(turn, index), "estimated-at",
            ["enemy-{}".format(index), index % 80, (index * 3) % 50],
            tv=truth_value(0.5 + ((index % 5) * 0.1), 0.6), crisp=False,
            provenance_ids=["perf-prov-{}-{}".format(turn, index)])
                 for index in range(atoms_per_turn)]
        snapshot = _snapshot(writer, turn, parent, uncertain_atoms=atoms,
                             own_state={"turn": turn, "gold": turn, "units": index_summary(atoms_per_turn)})
        goal = atom("perf-goal-{}".format(turn), "researchable", ["player-1", "Tech-{}".format(turn)])
        proposal = _proposal(writer, turn, snapshot, goal)
        _, result = _query_result(writer, turn, proposal, goal, _simple_proof(goal), latency=2.0)
        metric = writer.emit("metric_sample", turn, {
            "name": "loop_latency_ms", "value": 15.0, "unit": "ms",
            "labels": {"condition": "e"},
        }, caused_by=[result["event_id"]])
        parent = metric


def index_summary(count):
    return {"count": count, "ids": [0, max(0, count - 1)]}


def _prepare_output(path, overwrite=False):
    if overwrite and os.path.isfile(path):
        os.unlink(path)


def generate(name, path, overwrite=False):
    if name not in GENERATORS:
        raise ValueError("unknown synthetic scenario: {}".format(name))
    _prepare_output(path, overwrite=overwrite)
    GENERATORS[name](path)
    return path


def generate_all(directory, include_performance=True, overwrite=False):
    os.makedirs(directory, exist_ok=True)
    outputs = []
    for name in ALL_SCENARIOS:
        path = os.path.join(directory, name + ".jsonl")
        generate(name, path, overwrite=overwrite)
        outputs.append(path)
    if include_performance:
        path = os.path.join(directory, "performance-200-turns.jsonl")
        _prepare_output(path, overwrite=overwrite)
        generate_performance(path)
        outputs.append(path)
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description="generate deterministic PLN-FreeCiv V0 logs")
    parser.add_argument("--out", required=True)
    parser.add_argument("--scenario", choices=ALL_SCENARIOS)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--no-performance", action="store_true")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace only the selected deterministic output files")
    args = parser.parse_args(argv)
    if not args.all and not args.scenario:
        parser.error("choose --scenario or --all")
    if args.all:
        paths = generate_all(args.out, include_performance=not args.no_performance,
                             overwrite=args.overwrite)
    else:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, args.scenario + ".jsonl")
        paths = [generate(args.scenario, path, overwrite=args.overwrite)]
    result = []
    for path in paths:
        report = validate_file(path)
        result.append({"path": path, "valid": report.valid,
                       "events": report.event_count,
                       "errors": [item.code for item in report.errors]})
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
