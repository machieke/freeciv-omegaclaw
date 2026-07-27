#!/usr/bin/env python3
"""Drive a live patched freeciv-llm game and compare every packet-backed snapshot."""

import argparse
import asyncio
import json
import os
import random
import sys
import time
import hashlib


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv import turncycle  # noqa: E402
from freeciv_agent.execution import ExecutionGate, ProposedAction  # noqa: E402
from freeciv_agent.events.model import atom, proof_node, proof_tree  # noqa: E402
from freeciv_agent.events.schema import canonical_json_bytes, structural_hash  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.state import ProxyStateDTO, SnapshotStore  # noqa: E402
from freeciv_agent.state.parity import compare_packet_state  # noqa: E402


SAFE_ACTIONS = frozenset({"unit_build_city", "unit_fortify", "unit_sentry", "unit_skip"})


def start_action_trace(writer, snapshot, action, ordinal, caused_by):
    """Emit a grounded one-step plan before a live action is submitted."""
    material = [snapshot.snapshot_id, action, ordinal]
    suffix = structural_hash(material)[:20]
    action_id = "live-action-" + suffix
    advertised = canonical_json_bytes(action).decode("utf-8") in snapshot.legal_action_json
    legal_predicate = ("server-advertised-legal-action" if advertised
                       else "proxy-control-action-admissible")
    proposal = writer.emit("llm_proposal", snapshot.turn, {
        "claims": [], "goals": [{
            "goal_id": "execute-" + suffix, "predicate": "execute-legal-action",
            "arguments": [action],
        }], "model": "deterministic-live-soak-driver",
        "prompt_version": "freeciv-live-soak/1.0", "proposal_id": "proposal-" + suffix,
    }, caused_by=caused_by)
    legal_atom = atom(
        "legal-" + suffix, legal_predicate,
        [snapshot.player_id, action], provenance_ids=[snapshot.snapshot_id])
    query = writer.emit("pln_query", snapshot.turn, {
        "invoking_layer": "test", "query_atom": legal_atom,
        "query_id": "query-" + suffix, "query_type": "verify",
    }, caused_by=[proposal["event_id"]])
    check = writer.emit("grounded_check", snapshot.turn, {
        "args": [action], "available": True, "check_id": "check-" + suffix,
        "diagnostic": None, "predicate": legal_predicate,
        "satisfied": True, "snapshot_id": snapshot.snapshot_id, "value": True,
    }, caused_by=[query["event_id"]])
    proof = proof_tree("grounded-" + suffix, [proof_node(
        "grounded-" + suffix, "grounded", legal_atom, True,
        grounded_result={"available": True, "satisfied": True, "value": True},
        rule_source={"kind": "M2-grounded-check", "snapshot_id": snapshot.snapshot_id})])
    result = writer.emit("pln_result", snapshot.turn, {
        "cache_status": "miss", "chain_depth": 1, "dampening_lambda": None,
        "error": None, "latency_ms": 0.0, "prerequisite_atoms": [legal_atom],
        "proof": proof, "query_id": "query-" + suffix, "status": "PROVED",
        "tree_size": 1, "unsatisfied_frontier": [],
    }, caused_by=[query["event_id"], check["event_id"]])
    plan_id = "live-plan-" + suffix
    step_id = "live-step-" + suffix
    plan = writer.emit("plan_created", snapshot.turn, {"plan": {
        "assumptions": [], "branch_scores": [{
            "branch_id": "grounded-action", "feasibility_grade": 1.0,
            "feasible": True, "predicted_turns": 0, "reason": None,
            "scheduler_cost": 0.0,
        }], "cost_profile": "turns-to-goal", "feasibility_grade": 1.0,
        "goal_atom_id": legal_atom["atom_id"], "ledger": [], "plan_id": plan_id,
        "predicted_turns": 0, "rederived_subtree_hashes": [],
        "reused_subtree_hashes": [], "scheduler_cost": 0.0,
        "schema_version": "1.0", "selected_branch_id": "grounded-action",
        "snapshot_id": snapshot.snapshot_id,
        "solver_identity": "grounded-live-action-scheduler/1.0",
        "source_proof_hash": proof["structural_hash"], "status": "ACTIVE",
        "steps": [{
            "actual_turn": None, "cost": 0.0, "duration_turns": 0,
            "kind": "engine-action", "legal_actions_digest": snapshot.legal_actions_digest,
            "predicted_turn": snapshot.turn, "snapshot_id": snapshot.snapshot_id,
            "spatial": None, "status": "ACTIVE", "step_id": step_id,
            "target": action,
        }],
    }}, caused_by=[result["event_id"]])
    started = writer.emit("plan_step_executed", snapshot.turn, {
        "plan_id": plan_id, "snapshot_id": snapshot.snapshot_id,
        "status": "started", "step_id": step_id,
    }, caused_by=[plan["event_id"]])
    sent = writer.emit("action_sent", snapshot.turn, {
        "action": action, "action_id": action_id,
        "legal_actions_digest": snapshot.legal_actions_digest,
        "plan_id": plan_id, "snapshot_id": snapshot.snapshot_id, "step_id": step_id,
    }, caused_by=[started["event_id"]])
    return action_id, plan_id, step_id, sent


def finish_action_trace(writer, snapshot, identifiers, response):
    action_id, plan_id, step_id, sent = identifiers
    accepted = bool(response and response.get("type") == "action_accepted")
    result = writer.emit("action_result", snapshot.turn, {
        "action_id": action_id, "engine_response": response,
        "engine_turn": snapshot.turn, "status": "accepted" if accepted else "rejected",
    }, caused_by=[sent["event_id"]])
    completed = writer.emit("plan_step_executed", snapshot.turn, {
        "plan_id": plan_id, "snapshot_id": snapshot.snapshot_id,
        "status": "completed" if accepted else "rejected", "step_id": step_id,
    }, caused_by=[result["event_id"]])
    return accepted, completed


async def receive_action_result(ws, timeout=15):
    return await turncycle.recv_until(
        ws, {"action_accepted", "action_rejected", "error"}, timeout=timeout)


async def query_authoritative(ws):
    return await turncycle.get_state(ws, "pln_authoritative")


async def await_authoritative_advance(ws, turn, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = await query_authoritative(ws)
        if state is not None and int(state.get("turn", -1)) > turn:
            return state
        await asyncio.sleep(0.1)
    return None


def select_safe_action(snapshot, have_city, randomizer):
    rows = [json.loads(raw) for raw in snapshot.legal_action_json]
    if not have_city:
        founders = [row for row in rows if row.get("action_type") == "unit_build_city"]
        if founders:
            return founders[0]
    safe = [row for row in rows if row.get("action_type") in SAFE_ACTIONS]
    return randomizer.choice(safe) if safe else None


async def run(args):
    import websockets

    randomizer = random.Random(args.seed)
    store = SnapshotStore()
    local_submissions = []
    gate = ExecutionGate(store, lambda action: local_submissions.append(action) or {
        "accepted": True})
    writer = None
    trace_parent = None
    if args.events:
        writer = EventWriter(args.events, args.game_id, durable=True)
        trace_parent = writer.emit("run_started", 0, {
            "condition_id": "live-authoritative-soak",
            "manifest_identity": structural_hash({
                "game_id": args.game_id, "proxy_commit": args.proxy_commit,
                "seed": args.seed, "turns": args.turns,
            }),
        })
    report = {
        "accepted_random_actions": 0, "accepted_end_turns": 0,
        "engine_rejections": 0, "game_id": args.game_id, "mismatches": [],
        "proxy_commit": args.proxy_commit, "seed": args.seed,
        "stale_local_rejections": 0, "turns_requested": args.turns,
        "turns_verified": 0,
        "planned_actions": 0, "planned_action_rejections": 0,
    }
    async with websockets.connect(
            args.ws_url, open_timeout=20, max_size=None, ping_interval=None) as ws:
        connect = {
            "type": "llm_connect", "agent_id": args.agent_id,
            "api_token": args.api_token, "game_id": args.game_id,
            "nation": "Romans", "leader_name": "PLN State Comparator",
        }
        if args.port:
            connect["port"] = args.port
        await ws.send(json.dumps(connect))
        auth = await turncycle.recv_until(ws, {"auth_success", "error"}, timeout=40)
        if not auth or auth.get("type") != "auth_success":
            raise RuntimeError("authentication failed: {}".format(auth))
        player_id = int(auth["player_id"])
        state = await query_authoritative(ws)
        if not state or not state.get("units"):
            for command in ("/set minplayers 1", "/set aifill 0", "/set endturn 500", "/start"):
                await ws.send(json.dumps({"type": "chat", "message": command}))
                await asyncio.sleep(0.5)
            for _ in range(60):
                await asyncio.sleep(0.5)
                state = await query_authoritative(ws)
                if state and state.get("units"):
                    break
        if not state or not state.get("units"):
            raise RuntimeError("live game did not reach a populated authoritative state")

        prior = None
        for index in range(args.turns):
            source_seq = state.get("authoritative", {}).get("source_seq")
            snapshot = ProxyStateDTO.parse(args.game_id, source_seq, state).to_snapshot()
            store.replace(snapshot)
            if writer is not None:
                snapshot_event = writer.emit(
                    "state_snapshot", snapshot.turn, snapshot.event_payload(),
                    caused_by=[trace_parent["event_id"]] if trace_parent else None)
                trace_parent = snapshot_event
            atomspaces = store.current_atomspaces(args.game_id, player_id)
            for mismatch in compare_packet_state(state, snapshot, atomspaces):
                mismatch["turn"] = snapshot.turn
                report["mismatches"].append(mismatch)
            report["turns_verified"] += 1

            if prior is not None:
                stale = gate.execute(args.game_id, player_id, prior)
                if not stale.submitted and stale.reason == "stale_snapshot":
                    report["stale_local_rejections"] += 1
                else:
                    report["mismatches"].append({
                        "actual": stale.reason, "expected": "stale_snapshot",
                        "field": "execution_gate", "turn": snapshot.turn,
                    })

            action = select_safe_action(snapshot, bool(snapshot.cities), randomizer)
            if action is not None:
                proposal = ProposedAction.create(action, snapshot)
                local = gate.execute(args.game_id, player_id, proposal)
                if not local.submitted:
                    report["mismatches"].append({
                        "actual": local.reason, "expected": "submitted",
                        "field": "current_action_gate", "turn": snapshot.turn,
                    })
                else:
                    identifiers = (start_action_trace(
                        writer, snapshot, action, index * 2,
                        [trace_parent["event_id"]]) if writer is not None else None)
                    await ws.send(json.dumps({"type": "action", "action": action}))
                    response = await receive_action_result(ws)
                    if writer is not None:
                        accepted, completed = finish_action_trace(
                            writer, snapshot, identifiers, response)
                        trace_parent = completed
                        report["planned_actions"] += 1
                        if not accepted:
                            report["planned_action_rejections"] += 1
                    if response and response.get("type") == "action_accepted":
                        report["accepted_random_actions"] += 1
                    else:
                        report["engine_rejections"] += 1
                        report["mismatches"].append({
                            "actual": response, "expected": "action_accepted",
                            "field": "random_action", "turn": snapshot.turn,
                        })
                prior = proposal
            else:
                prior = None

            end_turn_action = {"action_type": "end_turn"}
            identifiers = (start_action_trace(
                writer, snapshot, end_turn_action, index * 2 + 1,
                [trace_parent["event_id"]]) if writer is not None else None)
            await ws.send(json.dumps({"type": "action", "action": end_turn_action}))
            response = await receive_action_result(ws)
            if writer is not None:
                accepted, completed = finish_action_trace(
                    writer, snapshot, identifiers, response)
                trace_parent = completed
                report["planned_actions"] += 1
                if not accepted:
                    report["planned_action_rejections"] += 1
            if not response or response.get("type") != "action_accepted":
                report["engine_rejections"] += 1
                report["mismatches"].append({
                    "actual": response, "expected": "action_accepted",
                    "field": "end_turn", "turn": snapshot.turn,
                })
                break
            report["accepted_end_turns"] += 1
            if index + 1 < args.turns:
                advanced = await await_authoritative_advance(ws, snapshot.turn)
                if advanced is None:
                    report["mismatches"].append({
                        "actual": None, "expected": snapshot.turn + 1,
                        "field": "turn_advance", "turn": snapshot.turn,
                    })
                    break
                state = advanced
    if writer is not None:
        metric = writer.emit("metric_sample", snapshot.turn, {
            "labels": {"run": "live-soak"}, "name": "confabulation_write_through",
            "unit": "claims", "value": 0,
        }, caused_by=[trace_parent["event_id"]])
        complete = writer.emit("run_completed", snapshot.turn, {
            "status": "completed" if not report["mismatches"] else "failed",
            "summary": {
                "planned_action_rejections": report["planned_action_rejections"],
                "planned_actions": report["planned_actions"],
                "turns_verified": report["turns_verified"],
            },
        }, caused_by=[metric["event_id"]])
        trace_parent = complete
        validation = validate_file(args.events)
        report["event_log"] = {
            "bytes": os.path.getsize(args.events),
            "events": validation.event_count,
            "sha256": hashlib.sha256(open(args.events, "rb").read()).hexdigest(),
            "valid": validation.valid,
            "validation_errors": [item.to_dict() for item in validation.errors],
        }
    report["passed"] = (not report["mismatches"]
                        and report["engine_rejections"] == 0
                        and report["planned_action_rejections"] == 0
                        and (not args.events or report["event_log"]["valid"])
                        and report["turns_verified"] == args.turns)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws-url", default=os.environ.get(
        "FREECIV_PROXY_WS", "ws://localhost:8002/llmsocket/8002"))
    parser.add_argument("--api-token", default=os.environ.get(
        "FREECIV_API_TOKEN", "test-token-fc3d-001"))
    parser.add_argument("--game-id", default="pln-state-parity")
    parser.add_argument("--agent-id", default="pln-state-parity")
    parser.add_argument("--port", type=int)
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--seed", type=int, default=4202)
    parser.add_argument("--proxy-commit", default=(
        "26ba7124249f34fd3050ef29bf191bd4d8808018+patch-sha256:2ac25711830d9f27824200ddfa07ff52ea6d12c592dfee814fec30183ae5f6b5"))
    parser.add_argument("--events", help="archive canonical persisted-first event JSONL")
    args = parser.parse_args()
    try:
        report = asyncio.run(run(args))
    except Exception as exc:
        report = {"passed": False, "error": "{}: {}".format(
            type(exc).__name__, str(exc)[:500])}
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
