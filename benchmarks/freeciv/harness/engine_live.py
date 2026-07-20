"""Release backend that drives completed games through the real FreeCiv proxy.

The global observer is queried only for navigation by the test driver and for
post-game scoring/calibration.  Agent beliefs are created exclusively from the
player connection's packet-visible foreign units.
"""

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

from freeciv import turncycle
from freeciv_agent.beliefs import (BeliefKey, BeliefStore, Evidence,
                                   OpponentMemory, UncertainInference)
from freeciv_agent.execution import ExecutionGate, ProposedAction
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.writer import EventWriter
from freeciv_agent.llm import ConstrainedProposer, GoalGrader, SymbolCatalog
from freeciv_agent.monitoring import AtomRevision, LocalRepairer, PlanMonitor
from freeciv_agent.oracle import CrispStateView, DependencyOracle, Goal
from freeciv_agent.planning import (BranchScore, NonPlan, Plan, PlanAssumption,
                                    PlanStep, PlanningSnapshot, ProofScheduler,
                                    ResourceLedger, GroundedImpactPlanner,
                                    ImpactTurnBudget)
from freeciv_agent.rulesets.compiler import compile_ruleset
from freeciv_agent.state import ProxyStateDTO, SnapshotStore, StateSummaryService


_IR = None
_STACK = None
_MODEL_JSON_CACHE = {}
_MODEL_CACHE_LOCK = threading.RLock()
_MODEL_READINESS_LOCK = threading.Lock()
_STACK_LOCK = threading.RLock()


def _opponent_memory_path(run_dir, condition_id):
    """Keep sequential induction populations isolated between M7 conditions."""
    return os.path.abspath(os.path.join(
        run_dir, "..", "..", "..", "opponent-memory",
        "{}.json".format(condition_id)))


def _ruleset_root():
    root = os.environ.get("FREECIV_RULESET_ROOT")
    if not root or not os.path.isfile(os.path.join(root, "civ2civ3", "techs.ruleset")):
        raise RuntimeError("engine-live requires FREECIV_RULESET_ROOT")
    return root


def _cognitive_stack():
    global _IR, _STACK
    if _STACK is None:
        with _STACK_LOCK:
            if _STACK is None:
                _IR = compile_ruleset(_ruleset_root(), "civ2civ3")
                catalog = SymbolCatalog(_IR)
                oracle = DependencyOracle(_IR)
                _STACK = (_IR, catalog, oracle, ProofScheduler())
    return _STACK


def _metric(writer, turn, parent, name, value, manifest, **labels):
    values = {"condition": manifest["condition_id"], "track": manifest["track"]}
    values.update({key: str(value) for key, value in labels.items()})
    event = writer.emit("metric_sample", turn, {
        "labels": values, "name": name,
        "unit": "ms" if name.endswith("_ms") else "turns" if name.endswith("_turns") else "ratio",
        "value": float(value),
    }, caused_by=[parent])
    return event["event_id"]


def _emit_belief_configuration(writer, parent, manifest):
    """Put every confidence-affecting release parameter in the event stream."""
    beliefs = manifest["beliefs"]
    for key, value in sorted(beliefs.items()):
        if key in ("decay", "schema_version", "sweep"):
            continue
        parent = _metric(
            writer, 0, parent, "belief_{}".format(key), value, manifest,
            declaration="release_configuration")
    for predicate, schedule in sorted(beliefs["decay"].items()):
        parent = _metric(
            writer, 0, parent, "belief_decay_window_turns",
            schedule["window_turns"], manifest,
            declaration="release_configuration", predicate=predicate,
            formula=schedule["formula"])
    return parent


def _ollama_json(manifest, prompt, expected_keys, attempts=2, validator=None):
    # Ollama runs one configured evaluation model on this machine. Serializing
    # cold misses avoids duplicate generations and CPU oversubscription; every
    # worker shares the deterministic verified-response cache below. Queue time
    # is part of the whole-turn model budget; contention must reach the verified
    # safe fallback before it can consume the execution reserve.
    turn_timeout = float(manifest.get("model_config", {}).get(
        "turn_timeout_seconds", 30))
    model_budget = max(1.0, turn_timeout - 2.0)
    turn_started = time.perf_counter()
    if not _MODEL_CACHE_LOCK.acquire(timeout=model_budget):
        raise RuntimeError("model turn budget exhausted waiting for local model")
    try:
        return _ollama_json_locked(
            manifest, prompt, expected_keys, attempts=attempts, validator=validator,
            turn_started=turn_started)
    finally:
        _MODEL_CACHE_LOCK.release()


def _ollama_native_endpoint():
    """Return the native Ollama API root for the configured OpenAI-compatible URL."""
    endpoint = os.environ.get(
        "OLLAMA_OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    native_endpoint = endpoint.rstrip("/")
    if native_endpoint.endswith("/v1"):
        native_endpoint = native_endpoint[:-3]
    return native_endpoint


def _ollama_readiness(manifest):
    """Load and keep the configured model resident before an engine arm.

    The verified-response cache can make a long arm appear model-idle.  Ollama
    may unload the model during that idle period, turning the next real request
    into a cold load that exceeds the bounded turn budget.  A tiny native API
    request is operational-only: it does not enter the event stream or affect
    outcome metrics, but it establishes that the declared model is loaded and
    keeps it resident for the duration of the arm.
    """
    model_config = manifest.get("model_config", {})
    timeout = float(model_config.get("readiness_timeout_seconds", 90))
    if timeout <= 0:
        raise ValueError("model readiness timeout must be positive")
    payload = {
        "model": manifest["model"],
        "prompt": "{}",
        "stream": False,
        "think": bool(model_config.get("think", False)),
        "keep_alive": str(model_config.get("keep_alive", "30m")),
        "options": {"temperature": 0, "num_predict": 1},
    }
    request = urllib.request.Request(
        _ollama_native_endpoint() + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    # Multiple engine workers may begin at once. Serialize readiness calls so a
    # cold model load is never duplicated or CPU-contended.
    if not _MODEL_READINESS_LOCK.acquire(timeout=timeout):
        raise RuntimeError("model readiness budget exhausted waiting for local model")
    try:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.load(response)
        except Exception as exc:
            raise RuntimeError(
                "configured Ollama model readiness failed: {}".format(exc))
    finally:
        _MODEL_READINESS_LOCK.release()
    if not isinstance(body, dict) or body.get("error"):
        raise RuntimeError(
            "configured Ollama model readiness returned an error: {}".format(
                body.get("error") if isinstance(body, dict) else body))
    if body.get("done") is False:
        raise RuntimeError("configured Ollama model readiness did not complete")
    return body


def _claim_eligible_manifest(manifest):
    """Return whether this arm is allowed to contribute to a formal claim."""
    return bool(manifest.get("claim_eligible") or manifest.get(
        "impact_pair", {}).get("claim_eligible"))


def _ollama_json_locked(manifest, prompt, expected_keys, attempts=2, validator=None,
                        turn_started=None):
    native_endpoint = _ollama_native_endpoint()
    cache_key = structural_hash([
        manifest["model"], prompt, sorted(expected_keys),
        manifest.get("model_config", {}).get("temperature", 0)])
    with _MODEL_CACHE_LOCK:
        cached = _MODEL_JSON_CACHE.get(cache_key)
    if cached is not None:
        value, raw = cached
        if validator is not None:
            validator(value)
        return json.loads(json.dumps(value)), raw, 0.0, 0
    turn_timeout = float(manifest.get("model_config", {}).get("turn_timeout_seconds", 30))
    # The configured 80B CPU model needs roughly 23-27 seconds for the compact
    # two-goal schema. Keep a bounded 2-second reserve for grading, planning,
    # gate checks, and the end-turn transport.
    model_budget = max(1.0, turn_timeout - 2.0)
    error = None
    turn_started = turn_started or time.perf_counter()
    for attempt in range(attempts):
        request_timeout = model_budget - (time.perf_counter() - turn_started)
        if request_timeout <= 0:
            break
        payload = {
            "model": manifest["model"], "stream": False,
            "keep_alive": str(manifest.get("model_config", {}).get(
                "keep_alive", "30m")),
            # The release prompt asks for a bounded JSON object, not a reasoning
            # trace. Ollama enables thinking by default for Qwen 3 models, so
            # pin this explicitly and retain the setting in every manifest.
            "think": bool(manifest.get("model_config", {}).get("think", False)),
            "options": {
                "temperature": 0,
                "num_predict": int(manifest.get(
                    "model_config", {}).get("max_tokens", 400)),
            },
            "messages": [
                {"role": "system", "content": "Return one JSON object only; no markdown."},
                {"role": "user", "content": prompt + (
                    "\nYour previous response was invalid. Copy the requested JSON exactly."
                    if attempt else "")},
            ],
        }
        request = urllib.request.Request(
            native_endpoint + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                body = json.load(response)
            raw = body["message"]["content"].strip()
            value = json.loads(raw)
            if not set(expected_keys).issubset(value):
                raise ValueError("missing keys")
            if validator is not None:
                validator(value)
            with _MODEL_CACHE_LOCK:
                _MODEL_JSON_CACHE[cache_key] = (json.loads(json.dumps(value)), raw)
            return value, raw, (time.perf_counter() - turn_started) * 1000.0, attempt
        except Exception as exc:
            error = exc
    raise RuntimeError("configured Ollama model returned no valid JSON: {}".format(error))


def _plain_proposal(manifest, summary, research_targets=()):
    document = summary if isinstance(summary, dict) else summary.to_dict()
    selection = str(research_targets[0]) if research_targets else "end_turn"
    state_context = _plain_prompt_state(document)
    prompt = (
        "FreeCiv state oracle context is {state_context}. Legal action kinds are "
        "{actions}; currently selectable "
        "research targets are {targets}. Return exactly "
        "{{\"selection\":{selection},\"rationale\":\"advertised safe choice\"}}."
    ).format(state_context=state_context, actions=document["legal_action_kinds"],
             targets=list(research_targets), selection=json.dumps(selection))
    value, raw, latency, corrections = _ollama_json(
        manifest, prompt, ("selection", "rationale"))
    return value, raw, latency, corrections


def _validate_compact_goal_proposal(value, target_count):
    indices = value.get("goal_indices")
    selection = value.get("selection")
    if (not isinstance(indices, list) or not indices
            or any(isinstance(index, bool) or not isinstance(index, int)
                   for index in indices)
            or len(indices) != len(set(indices))
            or any(index < 0 or index >= target_count for index in indices)):
        raise ValueError("goal_indices must be unique allowed integer references")
    if selection not in indices:
        raise ValueError("selection must reference a proposed goal index")
    if value.get("claims") != []:
        raise ValueError("live release proposal admits no unverified factual claims")


def _constrained_proposal(manifest, summary, catalog, targets):
    goals = [{
        "goal_id": "goal-live-{}".format(index + 1), "target_id": target.rule_id,
        "predicate": target.target_predicate,
        "arguments": ["player", target.rule_name],
    } for index, target in enumerate(targets)]
    # Integer references keep the model response bounded while still making the
    # model choose candidate goals from a mechanically generated canonical catalog.
    # The host expands the references and sends the v1 proposal through the
    # production ProposalParser before any goal can reach the oracle.
    exact = {"claims": [], "goal_indices": list(range(len(goals))),
             "selection": len(goals) - 1}
    prompt = (
        "Allowed canonical FreeCiv goal references are {choices}. Return exactly this "
        "compact v1 JSON: {exact}"
    ).format(
        choices=[{"index": index, "name": target.rule_name,
                  "target_id": target.rule_id} for index, target in enumerate(targets)],
        exact=json.dumps(exact, sort_keys=True, separators=(",", ":")))
    value, raw_model, latency, corrections = _ollama_json(
        manifest, prompt, ("goal_indices", "claims", "selection"),
        validator=lambda row: _validate_compact_goal_proposal(row, len(goals)))
    expanded = {
        "schema_version": "1.0", "proposal_id": "proposal-" + structural_hash([
            manifest["model"], [target.rule_id for target in targets], raw_model])[:20],
        "goals": [goals[index] for index in value["goal_indices"]],
        "claims": [], "rationale": "model-selected canonical live goal references",
        "selection": goals[value["selection"]]["goal_id"],
    }
    raw = json.dumps(expanded, sort_keys=True, separators=(",", ":"))
    # Exercise the production constrained parser and its catalog gates on model output.
    proposal = ConstrainedProposer(lambda _request: raw, catalog, manifest["model"]).propose(summary)[0]
    return proposal, value, latency, corrections


def _decision_state_fingerprint(snapshot):
    """Hash authoritative decision inputs without transport/cadence identity."""
    return structural_hash({
        "map": snapshot.map_dict(),
        "own_state": snapshot.own_state_dict(),
        "phase": snapshot.phase,
        "player_id": snapshot.player_id,
        "visible_enemy_units": [row.to_dict() for row in snapshot.visible_enemy_units],
    })


def _legal_action_family_fingerprints(snapshot):
    families = {}
    for encoded in snapshot.legal_action_json:
        action_type = str(json.loads(encoded).get("action_type", "unknown"))
        families.setdefault(action_type, []).append(encoded)
    return {key: structural_hash(sorted(values))
            for key, values in sorted(families.items())}


def _decision_state_ready(snapshot, require_own_units=False):
    """Reject partial packet assemblies before they can drive a paired arm."""
    if not (snapshot.ruleset_ready and snapshot.economy.available
            and snapshot.research.available):
        return False
    if require_own_units and not snapshot.units:
        return False
    if any(not city.buildability_available for city in snapshot.cities):
        return False
    if snapshot.units:
        if any(unit.moves_left is None for unit in snapshot.units):
            return False
        if not any(int(unit.moves_left) > 0 for unit in snapshot.units):
            return False
        if _first_legal_action(snapshot, "end_turn") is None:
            return False
    return True


async def _state(ws, game_id, minimum_turn=1, minimum_source_seq=None, timeout=20.0,
                 require_decision_ready=False, require_own_units=False,
                 stable_samples=1):
    if (isinstance(stable_samples, bool) or not isinstance(stable_samples, int)
            or not 1 <= stable_samples <= 5):
        raise ValueError("stable_samples must be in 1..5")
    deadline = time.monotonic() + timeout
    stable_fingerprint = None
    stable_count = 0
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            raw = await asyncio.wait_for(
                turncycle.get_state(ws, "pln_authoritative"),
                timeout=max(0.05, remaining))
        except asyncio.TimeoutError:
            break
        source_seq = raw.get("authoritative", {}).get("source_seq") if raw else None
        if (raw and raw.get("units") and int(raw.get("turn", 0)) >= minimum_turn
                and (minimum_source_seq is None
                     or (source_seq is not None and int(source_seq) >= minimum_source_seq))):
            snapshot = ProxyStateDTO.parse(game_id, source_seq, raw).to_snapshot()
            ready = (not require_decision_ready or _decision_state_ready(
                snapshot, require_own_units=require_own_units))
            if ready:
                fingerprint = _decision_state_fingerprint(snapshot)
                if fingerprint == stable_fingerprint:
                    stable_count += 1
                else:
                    stable_fingerprint = fingerprint
                    stable_count = 1
                if stable_count >= stable_samples:
                    return raw, snapshot
            else:
                stable_fingerprint = None
                stable_count = 0
        await asyncio.sleep(0.1)
    raise TimeoutError("authoritative state did not reach turn {}".format(minimum_turn))


def _global_state_ready(state, player_id=None):
    if not (state.get("units") and state.get("players") and state.get("techs")):
        return False
    scored = []
    for row in state["players"].values():
        score = row.get("score") if isinstance(row, dict) else None
        if (isinstance(score, (int, float)) and not isinstance(score, bool)
                and math.isfinite(float(score)) and float(score) >= 0):
            scored.append(row)
    if player_id is None:
        return bool(scored)
    return (any(row.get("id") == player_id for row in scored)
            and any(row.get("id") != player_id for row in scored))


def _player_row(state, player_id):
    return next((row for row in state.get("players", {}).values()
                 if isinstance(row, dict) and row.get("id") == player_id), {})


async def _global_state(ws, timeout=15.0, player_id=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await ws.send(json.dumps({"type": "global_state_query"}))
        response = await turncycle.recv_until(
            ws, {"global_state_response", "error"}, timeout=10)
        if response and response.get("type") == "global_state_response":
            state = response.get("data", {})
            if _global_state_ready(state, player_id=player_id):
                return state
        await asyncio.sleep(0.25)
    raise TimeoutError("observer global state was not populated")


def _target_rule(ir, known):
    candidates = [rule for rule in ir.rules if rule.target_kind == "tech" and not rule.disabled
                  and rule.rule_name != "None"]
    return next((rule for rule in candidates if rule.rule_name not in known), candidates[0])


def _target_rules(ir, known, count=2, available_names=()):
    available = {str(name) for name in available_names}
    candidates = [rule for rule in ir.rules if rule.target_kind == "tech"
                  and not rule.disabled and rule.rule_name != "None"
                  and rule.rule_name not in known
                  and (not available or rule.rule_name in available)]
    candidates.sort(key=lambda rule: (_tech_cost(rule), rule.rule_name, rule.rule_id))
    if not candidates:
        return (_target_rule(ir, known),)
    if len(candidates) == 1 or count == 1:
        return (candidates[0],)
    # Maximize the likelihood that grading has a measurable policy choice while
    # keeping the prompt bounded to two canonical goals.
    return (candidates[0], candidates[-1])


def _live_tech_costs(ir, raw):
    costs = {rule.rule_name: _tech_cost(rule) for rule in ir.rules
             if rule.target_kind == "tech" and not rule.disabled}
    for row in raw.get("legal_actions", []):
        if row.get("type") != "tech_research" or row.get("tech_name") is None:
            continue
        value = row.get("tech_cost")
        if isinstance(value, (int, float)) and value >= 0:
            costs[str(row["tech_name"])] = int(value)
    return tuple(sorted(costs.items()))


def _available_research_names(raw):
    """Return only research choices the authoritative proxy marks executable."""
    return sorted({
        str(row["tech_name"])
        for row in raw.get("legal_actions", [])
        if (row.get("type") == "tech_research"
            and row.get("is_valid") is True
            and row.get("tech_name"))
    })


def _plain_state_summary(raw):
    """Expose only the legacy action surface when the M2 oracle is disabled."""
    return {
        "legal_action_kinds": sorted({
            str(row.get("type")) for row in raw.get("legal_actions", [])
            if row.get("is_valid") is True and row.get("type")
        }),
    }


def _plain_prompt_state(document):
    """Bound the M2 query summary while keeping the stock input visibly distinct."""
    if set(document) == {"legal_action_kinds"}:
        return "disabled"
    research = document.get("research", {})
    return {
        "city_count": len(document.get("cities", ())),
        "known_techs": list(document.get("known_techs", ())),
        "research": {
            "beakers_per_turn": research.get("beakers_per_turn"),
            "target": research.get("target"),
        },
        "unit_types": sorted({
            str(row.get("type")) for row in document.get("units", ())
            if row.get("type")
        }),
        "visible_enemy_types": sorted({
            str(row.get("type")) for row in document.get("visible_enemy_units", ())
            if row.get("type")
        }),
    }


def _needs_cognitive_stack(context):
    """Return whether this condition is permitted to construct M1+ services."""
    return bool(context.capabilities["dependency_oracle"])


def _release_configuration_active(auth, expected):
    """Accept newly applied or pre-existing configuration only when exact."""
    return bool(auth.get("game_config") == expected)


def _first_legal_action(snapshot, action_type):
    return next((json.loads(row) for row in snapshot.legal_action_json
                 if json.loads(row).get("action_type") == action_type), None)


def _rule_for_unit(ir, unit_type):
    normalized = str(unit_type).lower().replace("_", " ")
    return next((rule for rule in ir.rules if rule.target_kind == "unit" and not rule.disabled
                 and rule.rule_name.lower() == normalized), None)


def _distance(x, y, tx, ty, width, height):
    dx = min((x - tx) % width, (tx - x) % width)
    dy = min((y - ty) % height, (ty - y) % height)
    return max(dx, dy)


def _scout_action(raw, global_state, player_id, width, height, blocked=()):
    enemies = [row for row in global_state.get("units", {}).values()
               if row.get("owner") != player_id and row.get("owner", 255) < 32]
    moves = [row for row in raw.get("legal_actions", [])
             if row.get("type") == "unit_move" and row.get("is_valid") is True
             and 0 <= int(row.get("params", {}).get("target", {}).get("x", -1)) < width
             and 0 <= int(row.get("params", {}).get("target", {}).get("y", -1)) < height]
    movable_ids = {row.get("unit_id") for row in moves}
    own = [row for row in raw.get("units", {}).values()
           if row.get("owner") == player_id and row.get("id") in movable_ids
           and str(row.get("type", "")).lower() in ("spy", "diplomat")]
    if not own or not enemies:
        return None
    scout = min(own, key=lambda row: int(row.get("id", 0)))
    target = min(enemies, key=lambda row: _distance(
        scout["x"], scout["y"], row["x"], row["y"], width, height))
    choices = [row for row in moves if row.get("unit_id") == scout.get("id")]
    if not choices:
        return None
    unblocked = [row for row in choices if (
        scout["id"], scout["x"], scout["y"],
        row["params"]["target"]["x"], row["params"]["target"]["y"]) not in blocked]
    if unblocked:
        choices = unblocked
    best = min(choices, key=lambda row: _distance(
        row["params"]["target"]["x"], row["params"]["target"]["y"],
        target["x"], target["y"], width, height))
    destination = best["params"]["target"]
    return {"action_type": "unit_move", "actor_id": scout["id"],
            "target": {"x": destination["x"], "y": destination["y"]}}


def _enemy_distance(raw, global_state, player_id, width, height):
    own = [row for row in raw.get("units", {}).values()
           if row.get("owner") == player_id]
    enemies = [row for row in global_state.get("units", {}).values()
               if row.get("owner") != player_id and row.get("owner", 255) < 32]
    if not own or not enemies:
        return None
    return min(_distance(unit["x"], unit["y"], enemy["x"], enemy["y"], width, height)
               for unit in own for enemy in enemies)


def _action_for_plan(raw, snapshot, plan):
    """Resolve the next scheduled step to an exact server-advertised action."""
    if not isinstance(plan, Plan) or not plan.steps:
        return None
    step = plan.steps[0]
    if step.snapshot_id != snapshot.snapshot_id:
        return None
    if step.kind == "engine-action":
        candidate = dict(step.target)
    elif step.kind == "research":
        target = str(step.target.get("tech"))
        candidate = next((json.loads(encoded) for encoded in snapshot.legal_action_json
                          if json.loads(encoded).get("action_type") == "tech_research"
                          and json.loads(encoded).get("target", {}).get("tech_name") == target),
                         None)
        if candidate is None:
            return None
    else:
        return None
    encoded = json.dumps(candidate, sort_keys=True, separators=(",", ":"))
    return candidate if encoded in snapshot.legal_action_json else None


def _research_action(snapshot, tech_name):
    return next((json.loads(encoded) for encoded in snapshot.legal_action_json
                 if json.loads(encoded).get("action_type") == "tech_research"
                 and json.loads(encoded).get("target", {}).get("tech_name") == tech_name),
                None)


async def _refresh_state(ws, store, writer, manifest, snapshot, parent, timeout=10.0):
    raw, current = await _state(
        ws, manifest["game_id"], minimum_turn=snapshot.turn,
        minimum_source_seq=snapshot.identity.source_seq + 1, timeout=timeout)
    store.replace(current)
    event = writer.emit("state_snapshot", current.turn, current.event_payload(),
                        caused_by=[parent])
    return raw, current, event["event_id"]


async def _execute_action(gate, game_id, player_id, snapshot, action, parent,
                          ordinal, plan=None):
    action_id = "engine-action-" + structural_hash([
        snapshot.snapshot_id, action, ordinal])[:20]
    proposed = ProposedAction(
        action_id, dict(action), snapshot.snapshot_id, snapshot.legal_actions_digest,
        None if plan is None else plan.plan_id,
        None if plan is None or not plan.steps else plan.steps[0].step_id)
    outcome = await gate.execute_async(
        game_id, player_id, proposed, caused_by=[parent])
    return outcome, outcome.result_event_id or parent


async def _refresh_accepted_impact_action(
        refresh, raw, snapshot, parent, candidate, refresh_timeout=None,
        effect_predicate=None):
    """Refresh an accepted impact action, preserving bounded no-effect outcomes.

    The proxy acknowledges transport acceptance before civserver necessarily
    emits a new authoritative packet.  A unit order can therefore be accepted
    while producing no source-sequence change (for example, a mechanically
    legal move that the server cannot execute).  Those outcomes must reach the
    planner's no-effect accounting so the accepted actor scope is closed. An
    accepted production order can likewise produce no source-sequence update.
    After the bounded wait, return a no-refresh outcome so the turn budget can
    close that ambiguous scope without sending a stale same-scope failover.
    """
    try:
        if refresh_timeout is None:
            if effect_predicate is None:
                next_raw, next_snapshot, next_parent = await refresh(snapshot, parent)
            else:
                next_raw, next_snapshot, next_parent = await refresh(
                    snapshot, parent, predicate=effect_predicate)
        else:
            kwargs = {"timeout": refresh_timeout}
            if effect_predicate is not None:
                kwargs["predicate"] = effect_predicate
            next_raw, next_snapshot, next_parent = await refresh(
                snapshot, parent, **kwargs)
    except TimeoutError:
        return raw, snapshot, parent, False
    return next_raw, next_snapshot, next_parent, True


def _control_plan(snapshot, assumption=None):
    action = {"action_type": "end_turn"}
    suffix = structural_hash([snapshot.snapshot_id, "control", assumption.atom_id if assumption else None])
    step = PlanStep(
        "step-" + suffix[:16], "engine-action", action, snapshot.turn, 0, 0.0,
        status="ACTIVE", snapshot_id=snapshot.snapshot_id,
        legal_actions_digest=snapshot.legal_actions_digest)
    assumptions = () if assumption is None else (assumption,)
    return Plan(
        "plan-" + suffix[:20], "goal-legal-end-turn", suffix,
        snapshot.snapshot_id, (step,), ResourceLedger(),
        (BranchScore("grounded-control", 1.0, 0.0, 0, True),),
        "grounded-control", "turns-to-goal", 0.0, 1.0, 0,
        "engine-live-control/1.0", assumptions=assumptions)


def _emit_observations(snapshot, manifest, store, inference, writer, parent, seen):
    predictions = []
    beliefs = manifest["beliefs"]
    for unit in snapshot.visible_enemy_units:
        if unit.unit_id in seen:
            continue
        seen.add(unit.unit_id)
        rule = _rule_for_unit(_IR, unit.unit_type)
        if rule is None:
            continue
        provenance = "visible-unit-" + structural_hash([
            manifest["game_id"], snapshot.turn, unit.unit_id, unit.unit_type])[:20]
        evidence = Evidence(
            provenance, manifest["game_id"], snapshot.turn,
            {"x": unit.x, "y": unit.y}, "player-visible-unit-packet",
            BeliefKey("observed-unit", (str(unit.owner), rule.rule_name)),
            beliefs["observation_strength"], beliefs["observation_confidence"],
            str(unit.owner), manifest["ruleset"], manifest["model"])
        _, observation, revision = store.emit_observation(
            evidence, writer, caused_by=[parent])
        parent = (revision or observation)["event_id"]
        derived = inference.abduce_prerequisites(
            "unit", rule.rule_name, str(unit.owner), (provenance,), snapshot.turn,
            strength=beliefs["abduction_strength"],
            confidence=beliefs["abduction_confidence"])
        for belief, belief_revision in derived:
            if belief_revision is None:
                continue
            event = writer.emit("revision", snapshot.turn, {
                "target_atom": belief.atom(), "prior_tv": belief_revision.prior_tv,
                "evidence_tv": belief_revision.evidence_tv,
                "posterior_tv": belief_revision.posterior_tv,
                "provenance_id": provenance, "operation": belief_revision.operation,
                "formula": belief_revision.formula,
            }, caused_by=[parent])
            parent = event["event_id"]
            predictions.append(belief)
    return predictions, parent


def _emit_opponent_presence(raw, snapshot, manifest, store, writer, parent, player_id):
    """Ground a monitor assumption in player-visible roster packets.

    Unit sightings remain the only source used for prerequisite abduction and
    calibration.  The public player roster gives the adversarial monitor a
    guaranteed, non-omniscient assumption to invalidate in every d/e game.
    """
    rows = [row for row in raw.get("players", {}).values()
            if int(row.get("id", player_id)) != player_id]
    if not rows:
        return None, parent
    opponent_id = str(rows[0]["id"])
    provenance = "visible-player-" + structural_hash([
        manifest["game_id"], opponent_id])[:20]
    evidence = Evidence(
        provenance, manifest["game_id"], snapshot.turn, None,
        "player-visible-roster-packet",
        BeliefKey("opponent-present", (opponent_id,)),
        manifest["beliefs"]["observation_strength"],
        manifest["beliefs"]["observation_confidence"],
        opponent_id, manifest["ruleset"], manifest["model"])
    belief, observation, revision = store.emit_observation(
        evidence, writer, caused_by=[parent])
    return belief, (revision or observation)["event_id"]


def _tech_cost(rule):
    row = rule.quantitative.get("cost")
    if isinstance(row, dict):
        row = row.get("value")
    return int(row or 1)


def _adversarial_monitor(snapshot, belief, writer, parent, monitor, beliefs):
    threshold = beliefs["actionable_threshold"]
    posterior_confidence = beliefs["minimum_logged_confidence"]
    evidence_confidence = beliefs["observation_confidence"]
    assumption = PlanAssumption(
        belief.atom_id, threshold, belief.tv, (), proof_node_id="observed-belief",
        subtree_hash=structural_hash(belief.to_dict()), provenance_ids=belief.provenance_ids)
    provisional = _control_plan(snapshot, assumption)
    affected_step = provisional.steps[0].step_id
    assumption = PlanAssumption(
        belief.atom_id, threshold, belief.tv, (affected_step,),
        proof_node_id="observed-belief", subtree_hash=assumption.subtree_hash,
        provenance_ids=belief.provenance_ids)
    provisional = _control_plan(snapshot, assumption)
    plan_event = writer.emit("plan_created", snapshot.turn, {"plan": provisional.to_dict()},
                             caused_by=[parent])
    revision_event = writer.emit("revision", snapshot.turn, {
        "target_atom": dict(belief.atom(), tv={
            "strength": belief.strength, "confidence": posterior_confidence}),
        "prior_tv": belief.tv, "evidence_tv": {
            "strength": 0.0, "confidence": evidence_confidence},
        "posterior_tv": {
            "strength": belief.strength, "confidence": posterior_confidence},
        "provenance_id": belief.provenance_ids[0], "operation": "retract",
        "formula": {"name": "adversarial-contradiction", "inputs": {"release_test": True}},
    }, caused_by=[plan_event["event_id"]])
    monitor.register(provisional)
    revision = AtomRevision(
        belief.atom_id, belief.tv, {
            "strength": belief.strength, "confidence": posterior_confidence},
        revision_event["event_id"], snapshot.turn)
    rows = monitor.emit_batch((revision,), writer, caused_by=[revision_event["event_id"]])
    invalidation, invalidation_event = rows[0]
    allowed, reason = monitor.guard_execution(provisional.plan_id)
    if allowed or reason != "plan_invalid":
        raise RuntimeError("invalid plan was not blocked")
    replacement = _control_plan(snapshot)
    repair = LocalRepairer(lambda _hash, _invalidation: (
        structural_hash(replacement.to_dict()), replacement)).repair(
            invalidation, (assumption.subtree_hash, structural_hash("unaffected")))
    if not repair.executable or repair.latency_ms >= 2000:
        raise RuntimeError("local repair failed release gate")
    repaired_event = writer.emit("plan_created", snapshot.turn, {
        "plan": repair.replacement_plan.to_dict()},
        caused_by=[invalidation_event["event_id"]])
    monitor.register(repair.replacement_plan)
    return (provisional, repair.replacement_plan,
            repaired_event["event_id"], repair.latency_ms)


def _cognitive_turn(manifest, context, store, player_id, raw, snapshot,
                    ir, catalog, oracle, scheduler, writer, parent):
    """Run proposal, verification/grading, dependency, and planning for one turn."""
    if context.capabilities["authoritative_state"]:
        context.use("authoritative_state")
        summary = StateSummaryService(store).query(manifest["game_id"], player_id)
    else:
        summary = _plain_state_summary(raw)
    available_research = _available_research_names(raw)
    targets = ()
    target = None
    if _needs_cognitive_stack(context):
        targets = _target_rules(
            ir, snapshot.research.known_techs, available_names=available_research)
        target = targets[0]
    crisp = (CrispStateView(
        snapshot.snapshot_id, known_techs=snapshot.research.known_techs,
        player="player") if context.capabilities["dependency_oracle"] else None)
    numeric = (PlanningSnapshot(
        snapshot.snapshot_id, snapshot.turn,
        int(snapshot.research.beakers_per_turn or 0),
        int(snapshot.economy.gold or 0),
        current_research=snapshot.research.target_name,
        current_progress=int(snapshot.research.progress or 0),
        tech_costs=_live_tech_costs(ir, raw),
        legal_actions_digest=snapshot.legal_actions_digest)
               if context.capabilities["scheduler"] else None)

    proposal = None
    plain_selection = "end_turn"
    model_started = time.perf_counter()
    model_error = None
    try:
        if context.capabilities["constrained_llm"]:
            context.use("constrained_llm")
            proposal, _, latency, corrections = _constrained_proposal(
                manifest, summary, catalog, targets)
            payload = {
                "claims": [], "goals": [row.to_dict() for row in proposal.goals],
                "model": manifest["model"],
                "prompt_version": "engine-live-constrained/1.0",
                "proposal_id": proposal.proposal_id,
            }
        else:
            selection, raw_model, latency, corrections = _plain_proposal(
                manifest, summary, available_research)
            allowed = set(available_research + ["end_turn"])
            plain_selection = (str(selection["selection"])
                               if str(selection["selection"]) in allowed else "end_turn")
            selected_rule = next(
                (rule for rule in targets if rule.rule_name == plain_selection), None)
            if selected_rule is not None:
                target = selected_rule
            payload = {
                "claims": [], "goals": [{"predicate": plain_selection}],
                "model": manifest["model"],
                "prompt_version": "engine-live-plain/1.0",
                "proposal_id": "proposal-" + structural_hash([
                    raw_model, snapshot.snapshot_id])[:20],
            }
    except Exception as exc:
        model_error = exc
        latency = (time.perf_counter() - model_started) * 1000.0
        corrections = int(manifest.get(
            "model_config", {}).get("corrective_attempts", 2)) - 1
        payload = {
            "claims": [], "goals": [{"predicate": "safe-fallback"}],
            "model": manifest["model"],
            "prompt_version": "engine-live-timeout-fallback/1.0",
            "proposal_id": "proposal-fallback-" + structural_hash([
                snapshot.snapshot_id, type(exc).__name__])[:20],
        }
    proposal_event = writer.emit(
        "llm_proposal", snapshot.turn, payload, caused_by=[parent])
    parent = proposal_event["event_id"]
    if model_error is not None:
        verification = writer.emit("verification", snapshot.turn, {
            "verification_id": "verify-fallback-" + payload["proposal_id"],
            "proposal_id": payload["proposal_id"], "claim_id": "safe-end-turn",
            "verdict": "believe", "check": "model_failure_safe_end_turn",
            "evidence_atom_ids": [],
        }, caused_by=[parent])
        gap = writer.emit("logging_gap", snapshot.turn, {
            "component": "configured-llm", "missing": "valid_model_proposal",
            "detail": "{}; bounded safe end-turn fallback".format(
                type(model_error).__name__),
        }, caused_by=[verification["event_id"]])
        if _claim_eligible_manifest(manifest):
            raise RuntimeError(
                "claim-eligible arm cannot use model fallback: {}".format(
                    type(model_error).__name__))
        return None, "end_turn", gap["event_id"], latency, corrections, True

    if proposal is not None:
        grades = GoalGrader(oracle, scheduler).grade_all(proposal, crisp, numeric)
        if manifest["track"] == "grading_ungraded":
            selected = next((row for row in grades
                             if row.goal.goal_id == proposal.selection and row.valid), None)
        else:
            selected = GoalGrader.select_best(grades)
        if selected is not None:
            target = next(rule for rule in targets
                          if rule.rule_id == selected.goal.target_id)
        verification = writer.emit("verification", snapshot.turn, {
            "verification_id": "verify-selection-" + proposal.proposal_id,
            "proposal_id": proposal.proposal_id,
            "claim_id": proposal.selection or "no-selection",
            "verdict": "believe" if selected is not None else "disbelieve",
            "check": ("graded_candidate_feasible" if selected is not None
                      else "no_feasible_candidate"),
            "evidence_atom_ids": ([] if selected is None or selected.proof_hash is None
                                  else [selected.proof_hash]),
        }, caused_by=[parent])
        parent = verification["event_id"]
        parent = _metric(
            writer, snapshot.turn, parent, "selection_changed_by_grading",
            int(selected is not None and selected.goal.goal_id != proposal.selection),
            manifest)
        for grade in grades:
            parent = _metric(
                writer, snapshot.turn, parent, "candidate_feasibility_grade",
                float(grade.feasibility_grade or 0.0), manifest,
                goal_id=grade.goal.goal_id, valid=int(grade.valid))
            if grade.scheduler_cost is not None:
                parent = _metric(
                    writer, snapshot.turn, parent, "candidate_scheduler_cost",
                    float(grade.scheduler_cost), manifest, goal_id=grade.goal.goal_id)

    # Plain conditions honor an explicit end-turn selection. Constrained goals
    # always proceed through the dependency and scheduling stages.
    should_plan = proposal is not None or plain_selection != "end_turn"
    query_result = None
    if should_plan and context.capabilities["dependency_oracle"]:
        context.use("dependency_oracle")
        query_result, _, result_event = oracle.emit_deps(
            Goal.researchable("player", target.rule_name), crisp, writer,
            snapshot.turn, [parent], invoking_layer="planner")
        parent = result_event["event_id"]
    active_plan = None
    if should_plan and context.capabilities["scheduler"]:
        context.use("scheduler")
        active_plan, plan_event = scheduler.emit_plan(
            query_result, numeric, writer, snapshot.turn, [parent])
        parent = plan_event["event_id"]
    return active_plan, plain_selection, parent, latency, corrections, False


async def _play(run_dir, manifest, context):
    import websockets

    if _needs_cognitive_stack(context):
        ir, catalog, oracle, scheduler = _cognitive_stack()
    else:
        ir = catalog = oracle = scheduler = None
    events_path = manifest["events_path"]
    if not os.path.isabs(events_path):
        events_path = os.path.join(run_dir, events_path)
    writer = EventWriter(events_path, manifest["game_id"], durable=True)
    root = writer.emit("run_started", 0, {
        "condition_id": manifest["condition_id"],
        "manifest_identity": manifest["manifest_identity"]})
    parent = _emit_belief_configuration(writer, root["event_id"], manifest)
    api_token = os.environ.get("FREECIV_API_TOKEN", "test-token-fc3d-001")
    ws_url = os.environ.get("FREECIV_PROXY_WS", "ws://127.0.0.1:8002/llmsocket/8002")
    # A behavioral game can be retried after an interrupted/expired proxy
    # session. Include the recorded attempt identity so the proxy never resumes
    # a suspended session from an earlier source identity or retry.
    agent_id = "rel_{}_{}".format(
        re.sub(r"[^A-Za-z0-9_]", "_", manifest["game_id"])[-27:],
        manifest["attempt_id"][:12])
    config = {
        "ruleset": manifest["ruleset"], "minplayers": 1, "aifill": 2,
        "mapseed": manifest["seed"], "gameseed": manifest["seed"],
        "sciencebox": 100, "techlevel": 50, "map_size": "tiny",
        # Founder + mobile diplomat + stationary defender: the defender gives
        # fog-of-war calibration a repeatable visible opponent unit while the
        # diplomat drives the real scouting path.
        "startunits": "csd", "startcity": True,
        "startpos": "all", "dispersion": 0, "fogofwar": False,
        "max_turns": manifest.get("engine_max_turns", manifest["turn_limit"]),
        "ai_skill_level": manifest["opponent"].get("difficulty", "experimental"),
    }
    store = SnapshotStore()
    belief_store = (BeliefStore(manifest["beliefs"])
                    if context.capabilities["uncertain_beliefs"] else None)
    inference = (UncertainInference(ir, belief_store)
                 if context.capabilities["uncertain_beliefs"] else None)
    execution_monitor = (PlanMonitor()
                         if context.capabilities["scheduler"] else None)
    impact_planner = (GroundedImpactPlanner(manifest["impact_policy"], ruleset_ir=ir)
                      if context.capabilities["scheduler"] else None)
    memory = None
    induction_prediction = None
    induction_estimate = None
    if manifest["track"] == "induction":
        memory_path = _opponent_memory_path(run_dir, manifest["condition_id"])
        memory = OpponentMemory(memory_path)
        induction_estimate = memory.predict(
            manifest["opponent"].get("id"), manifest["ruleset"], manifest["model"],
            "has-tech:Espionage",
            manifest["beliefs"]["induction_default_probability"],
            manifest["beliefs"]["induction_decision_threshold"],
            manifest["beliefs"]["induction_minimum_samples"])
        # A declared neutral prior is used for game one. Later predictions are
        # read from persisted prior games before current-game truth is available.
        induction_prediction = induction_estimate["predicted"]
    predictions = []
    monitor_belief = None
    seen = set()
    blocked_moves = set()
    prior_scout = None
    action_count = attempted_count = rejected = zombie_blocked = 0
    decision_stats = {
        "impact_actions": 0, "meaningful_actions": 0,
        "production_changes": 0, "founder_production_changes": 0,
        "settlement_attempts": 0, "tactical_actions": 0,
        "effect_observed": 0, "no_effect": 0, "safe_model_fallbacks": 0,
        "failover_attempts": 0, "failover_recoveries": 0,
        "effect_confirmation_timeouts": 0,
    }
    action_type_counts = {}
    impact_turns = set()
    capability_pruned_worker_moves = set()
    nonprogress_moves = set()
    replan_latencies = []
    model_latencies = []
    full_loop_latencies = []
    effect_confirmation_latencies = []
    production_projection_etas = []
    production_projection_values = []
    production_projection_costs = []
    production_projection_shields = []
    production_projection_pop_costs = []
    production_projection_ruleset_sources = []
    corrections = 0
    final_global = None
    async with websockets.connect(
            ws_url, open_timeout=30, max_size=None, ping_interval=None) as ws:
        await ws.send(json.dumps({
            "type": "llm_connect", "agent_id": agent_id, "api_token": api_token,
            "game_id": manifest["game_id"], "port": manifest["port"],
            "nation": "Romans", "leader_name": "PLN Release Agent",
            "auto_ready": True, "game_config": config,
        }))
        auth = await turncycle.recv_until(ws, {"auth_success", "error"}, timeout=45)
        if not auth or auth.get("type") != "auth_success":
            raise RuntimeError("live auth failed: {}".format(auth))
        # On a retry the proxy may retain the GameSession after its civserver was
        # recycled. In that case this connection did not apply the configuration,
        # but the auth response still proves that the exact requested dictionary is
        # active. Reject absent or different configuration in all cases.
        if not _release_configuration_active(auth, config):
            raise RuntimeError("release game configuration was not applied exactly")
        ready = await turncycle.recv_until(ws, {"game_ready", "error"}, timeout=30)
        if not ready or ready.get("type") != "game_ready":
            raise RuntimeError("game_ready not received: {}".format(ready))
        player_id = int(auth["player_id"])

        async def submit(action):
            await ws.send(json.dumps({"type": "action", "action": action}))
            response = await turncycle.recv_until(
                ws, {"action_accepted", "action_rejected", "error"}, timeout=15)
            return {
                "accepted": bool(response and response.get("type") == "action_accepted"),
                "proxy_response": response,
            }

        gate = ExecutionGate(store, submit, writer, execution_monitor)
        # ``game_ready`` can precede the final burst of unit-action packets.
        # Require a short quiet period plus five identical canonical samples so
        # paired arms do not latch different stable-looking legal action sets.
        await asyncio.sleep(0.5)
        raw, snapshot = await _state(
            ws, manifest["game_id"], require_decision_ready=True,
            require_own_units=True, stable_samples=5)
        store.replace(snapshot)
        state_event = writer.emit("state_snapshot", snapshot.turn, snapshot.event_payload(),
                                  caused_by=[parent])
        parent = state_event["event_id"]
        global_state = await _global_state(ws, player_id=player_id)
        opponent_rows = sorted(
            (row for row in global_state["players"].values()
             if row.get("id") != player_id and row.get("score", -1) >= 0),
            key=lambda row: (row.get("id", 2147483647), row.get("name", "")))
        opponent = opponent_rows[0] if opponent_rows else {"id": 1, "name": "builtin-ai"}
        if impact_planner is not None:
            impact_planner.observe(snapshot)
            capability_pruned_worker_moves.update(
                impact_planner.capability_pruned_worker_move_keys(snapshot))
            nonprogress_moves.update(impact_planner.nonprogress_move_keys(snapshot))
        initial_city_count = len(snapshot.cities)
        initial_citizens = sum(max(0, int(city.size or 0)) for city in snapshot.cities)
        initial_tech_count = len(snapshot.research.known_techs)
        initial_position_count = (len(impact_planner.visited_positions)
                                  if impact_planner is not None else 0)
        initial_player_row = _player_row(global_state, player_id)
        initial_opponent_row = _player_row(global_state, opponent.get("id", 1))
        if "score" not in initial_player_row or "score" not in initial_opponent_row:
            raise RuntimeError("initial paired scores were not authoritative")
        initial_score = float(initial_player_row["score"])
        initial_state_fingerprint = structural_hash({
            "decision_state": _decision_state_fingerprint(snapshot),
            "opponent_score": float(initial_opponent_row["score"]),
            "player_score": initial_score,
        })
        initial_legal_action_families = _legal_action_family_fingerprints(snapshot)

        def record_meaningful_action(action, impact=False, category=None):
            action_type = str(action.get("action_type", "unknown"))
            if action_type == "end_turn":
                return
            decision_stats["meaningful_actions"] += 1
            action_type_counts[action_type] = action_type_counts.get(action_type, 0) + 1
            if impact:
                decision_stats["impact_actions"] += 1
                impact_turns.add(snapshot.turn)
            if action_type == "city_production":
                decision_stats["production_changes"] += 1
                if category == "production_expansion":
                    decision_stats["founder_production_changes"] += 1
            if action_type == "unit_build_city":
                decision_stats["settlement_attempts"] += 1
            if category in ("tactical_attack", "tactical_move"):
                decision_stats["tactical_actions"] += 1

        distance = _enemy_distance(
            raw, global_state, player_id, snapshot.map_width, snapshot.map_height)
        if distance is not None:
            parent = _metric(
                writer, snapshot.turn, parent, "initial_enemy_distance", distance, manifest)

        if context.capabilities["uncertain_beliefs"]:
            monitor_belief, parent = _emit_opponent_presence(
                raw, snapshot, manifest, belief_store, writer, parent, player_id)

        async def refresh_after_action(current, cause, predicate=None, timeout=15.0):
            minimum_seq = current.identity.source_seq + 1
            deadline = time.monotonic() + float(timeout)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("accepted action produced no authoritative state update")
                next_raw, next_snapshot = await _state(
                    ws, manifest["game_id"], minimum_turn=current.turn,
                    minimum_source_seq=minimum_seq, timeout=remaining,
                    stable_samples=2)
                if predicate is not None and not predicate(next_snapshot):
                    minimum_seq = next_snapshot.identity.source_seq + 1
                    await asyncio.sleep(0.05)
                    continue
                store.replace(next_snapshot)
                if impact_planner is not None:
                    impact_planner.observe(next_snapshot)
                    capability_pruned_worker_moves.update(
                        impact_planner.capability_pruned_worker_move_keys(next_snapshot))
                    nonprogress_moves.update(
                        impact_planner.nonprogress_move_keys(next_snapshot))
                event = writer.emit(
                    "state_snapshot", next_snapshot.turn, next_snapshot.event_payload(),
                    caused_by=[cause])
                return next_raw, next_snapshot, event["event_id"]

        turn_started = time.perf_counter()
        final_turn = snapshot.turn
        turns_executed = 0
        planned_actions = 0
        for turn_index in range(1, manifest["turn_limit"] + 1):
            if turn_index > 1:
                raw, snapshot = await _state(
                    ws, manifest["game_id"], minimum_turn=snapshot.turn + 1,
                    require_decision_ready=True, stable_samples=2)
                store.replace(snapshot)
                state_event = writer.emit(
                    "state_snapshot", snapshot.turn, snapshot.event_payload(),
                    caused_by=[parent])
                parent = state_event["event_id"]
                global_state = await _global_state(ws, player_id=player_id)
                if impact_planner is not None:
                    impact_planner.observe(snapshot)
                    capability_pruned_worker_moves.update(
                        impact_planner.capability_pruned_worker_move_keys(snapshot))
                    nonprogress_moves.update(
                        impact_planner.nonprogress_move_keys(snapshot))
                if prior_scout is not None:
                    actor_id, source_x, source_y, target_x, target_y = prior_scout
                    row = next((unit for unit in raw.get("units", {}).values()
                                if unit.get("id") == actor_id), None)
                    if row is not None and (row.get("x"), row.get("y")) == (source_x, source_y):
                        blocked_moves.add(prior_scout)
                    else:
                        blocked_moves = {move for move in blocked_moves if move[0] != actor_id}
                    prior_scout = None
            final_turn = snapshot.turn
            turns_executed += 1
            final_global = global_state
            if context.capabilities["uncertain_beliefs"]:
                context.use("uncertain_beliefs")
                rows, parent = _emit_observations(
                    snapshot, manifest, belief_store, inference, writer, parent, seen)
                predictions.extend(rows)
            # Elimination is a valid game loss, not infrastructure failure. The
            # player stream may still contain visible foreign units, so test the
            # typed authoritative own-unit collection rather than raw truthiness.
            if not snapshot.units:
                break

            full_turn_started = time.perf_counter()
            (active_plan, plain_selection, parent, turn_model_latency,
             turn_corrections, safe_model_fallback) = _cognitive_turn(
                manifest, context, store, player_id, raw, snapshot,
                ir, catalog, oracle, scheduler, writer, parent)
            model_latencies.append(turn_model_latency)
            corrections += turn_corrections
            decision_stats["safe_model_fallbacks"] += int(safe_model_fallback)
            if isinstance(active_plan, Plan):
                execution_monitor.register(active_plan)

            # Establish an authoritative city/economy source before numeric
            # scheduling. The canonical action comes from this exact snapshot.
            found_city = (_first_legal_action(snapshot, "unit_build_city")
                          if not snapshot.cities else None)
            if found_city is not None and not safe_model_fallback:
                outcome, parent = await _execute_action(
                    gate, manifest["game_id"], player_id, snapshot, found_city,
                    parent, attempted_count)
                attempted_count += 1
                action_count += int(outcome.submitted)
                rejected += int(outcome.submitted and outcome.status != "accepted")
                if outcome.status != "accepted":
                    raise RuntimeError("found-city action failed: {}".format(outcome.reason))
                record_meaningful_action(found_city)
                raw, snapshot, parent = await refresh_after_action(
                    snapshot, parent, predicate=lambda value: bool(value.cities))

            planned_action = _action_for_plan(raw, snapshot, active_plan)
            if planned_action is not None:
                outcome, parent = await _execute_action(
                    gate, manifest["game_id"], player_id, snapshot,
                    planned_action, parent, attempted_count, active_plan)
                attempted_count += 1
                action_count += int(outcome.submitted)
                rejected += int(outcome.submitted and outcome.status != "accepted")
                if outcome.status != "accepted":
                    raise RuntimeError("planned action failed: {}".format(outcome.reason))
                planned_actions += 1
                record_meaningful_action(planned_action)
                raw, snapshot, parent = await refresh_after_action(
                    snapshot, parent,
                    predicate=lambda value: value.research.target_name is not None)
                active_plan = None
            elif (not context.capabilities["scheduler"]
                  and plain_selection != "end_turn"):
                direct_action = _research_action(snapshot, plain_selection)
                if direct_action is not None:
                    outcome, parent = await _execute_action(
                        gate, manifest["game_id"], player_id, snapshot,
                        direct_action, parent, attempted_count)
                    attempted_count += 1
                    action_count += int(outcome.submitted)
                    rejected += int(outcome.submitted and outcome.status != "accepted")
                    if outcome.status != "accepted":
                        raise RuntimeError(
                            "model-selected action failed: {}".format(outcome.reason))
                    record_meaningful_action(direct_action)
                    raw, snapshot, parent = await refresh_after_action(
                        snapshot, parent,
                        predicate=lambda value: value.research.target_name is not None)

            # Scheduler-enabled conditions convert exact, current legal actions
            # into short strategic plans.  Refresh after every action so the
            # next candidate is grounded in a new snapshot and legal digest.
            excluded_impact_actions = set()
            impact_budget = (ImpactTurnBudget(
                impact_planner.max_no_effect_failovers_per_scope)
                if impact_planner is not None else None)
            if impact_planner is not None and not safe_model_fallback:
                context.use("scheduler")
                for _ in range(impact_planner.max_actions_per_turn):
                    turn_timeout = float(manifest.get(
                        "model_config", {}).get("turn_timeout_seconds", 30))
                    if (time.perf_counter() - full_turn_started
                            >= turn_timeout - impact_planner.refresh_timeout_seconds - 0.5):
                        break
                    decision = impact_planner.plan(
                        snapshot, excluded=excluded_impact_actions,
                        excluded_scopes=impact_budget.excluded_scopes)
                    if decision is None:
                        break
                    impact_action = decision.candidate.action
                    action_snapshot = snapshot
                    plan_event = writer.emit(
                        "plan_created", snapshot.turn,
                        {"plan": decision.plan.to_dict()}, caused_by=[parent])
                    parent = plan_event["event_id"]
                    execution_monitor.register(decision.plan)
                    outcome, parent = await _execute_action(
                        gate, manifest["game_id"], player_id, snapshot,
                        impact_action, parent, attempted_count, decision.plan)
                    attempted_count += 1
                    action_count += int(outcome.submitted)
                    rejected += int(outcome.submitted and outcome.status != "accepted")
                    if outcome.status != "accepted":
                        raise RuntimeError(
                            "impact plan action failed: {}".format(outcome.reason))
                    planned_actions += 1
                    record_meaningful_action(
                        impact_action, impact=True,
                        category=decision.candidate.category)
                    projection = decision.candidate.projection or {}
                    if impact_action.get("action_type") == "city_production":
                        if projection.get("completion_eta_turns") is not None:
                            production_projection_etas.append(float(
                                projection["completion_eta_turns"]))
                        if projection.get("score_value") is not None:
                            production_projection_values.append(float(
                                projection["score_value"]))
                        if projection.get("build_cost") is not None:
                            production_projection_costs.append(float(
                                projection["build_cost"]))
                        if projection.get("shield_surplus") is not None:
                            production_projection_shields.append(float(
                                projection["shield_surplus"]))
                        if projection.get("pop_cost") is not None:
                            production_projection_pop_costs.append(float(
                                projection["pop_cost"]))
                        production_projection_ruleset_sources.append(int(
                            projection.get("cost_source") == "ruleset_ir"))
                    excluded_impact_actions.add(decision.candidate.action_key)
                    confirmation_started = time.perf_counter()
                    raw, snapshot, parent, authoritative_refresh = (
                        await _refresh_accepted_impact_action(
                            refresh_after_action, raw, snapshot, parent,
                            decision.candidate,
                            refresh_timeout=impact_planner.refresh_timeout_seconds,
                            effect_predicate=(
                                (lambda value: impact_planner.candidate_effect_observed(
                                    decision.candidate, action_snapshot, value))
                                if impact_action.get("action_type") == "city_production"
                                else None)))
                    effect_confirmation_latencies.append(
                        (time.perf_counter() - confirmation_started) * 1000.0)
                    decision_stats["effect_confirmation_timeouts"] += int(
                        not authoritative_refresh)
                    effect_observed = (authoritative_refresh
                                       and impact_planner.candidate_effect_observed(
                                           decision.candidate, action_snapshot, snapshot))
                    impact_planner.record_outcome(
                        decision.candidate, action_snapshot, effect_observed)
                    impact_budget.record(
                        decision.candidate, effect_observed,
                        authoritative_refresh=authoritative_refresh)
                    if effect_observed:
                        decision_stats["effect_observed"] += 1
                    else:
                        decision_stats["no_effect"] += 1
                decision_stats["failover_attempts"] += impact_budget.failover_attempts
                decision_stats["failover_recoveries"] += impact_budget.recoveries

            action = (None if (safe_model_fallback or impact_planner is not None)
                      else _scout_action(
                raw, global_state, player_id,
                snapshot.map_width, snapshot.map_height, blocked_moves))
            if action is not None:
                source = next(unit for unit in raw.get("units", {}).values()
                              if unit.get("id") == action["actor_id"])
                prior_scout = (
                    action["actor_id"], source["x"], source["y"],
                    action["target"]["x"], action["target"]["y"])
                outcome, parent = await _execute_action(
                    gate, manifest["game_id"], player_id, snapshot, action,
                    parent, attempted_count)
                attempted_count += 1
                action_count += int(outcome.submitted)
                rejected += int(outcome.submitted and outcome.status != "accepted")
                if outcome.status != "accepted":
                    raise RuntimeError("scout action failed: {}".format(outcome.reason))
                record_meaningful_action(action)
                raw, snapshot, parent = await refresh_after_action(snapshot, parent)
            control_plan = None
            if (context.capabilities["assumption_monitor"] and monitor_belief
                    and zombie_blocked == 0):
                context.use("assumption_monitor")
                invalid_plan, control_plan, parent, repair_ms = _adversarial_monitor(
                    snapshot, monitor_belief, writer, parent, execution_monitor,
                    manifest["beliefs"])
                replan_latencies.append(repair_ms)
                invalid_action = _action_for_plan(raw, snapshot, invalid_plan)
                if invalid_action is None:
                    raise RuntimeError("invalid-plan test action was not server-advertised")
                blocked, parent = await _execute_action(
                    gate, manifest["game_id"], player_id, snapshot, invalid_action,
                    parent, attempted_count, invalid_plan)
                attempted_count += 1
                if blocked.submitted or blocked.reason != "plan_invalid":
                    raise RuntimeError("invalid plan reached the execution transport")
                zombie_blocked += 1
            elif context.capabilities["scheduler"]:
                control_plan = _control_plan(snapshot)
                plan_event = writer.emit(
                    "plan_created", snapshot.turn, {"plan": control_plan.to_dict()},
                    caused_by=[parent])
                parent = plan_event["event_id"]
                execution_monitor.register(control_plan)
            end_turn = _first_legal_action(snapshot, "end_turn")
            if end_turn is None:
                raise RuntimeError("server did not advertise end_turn")
            outcome, parent = await _execute_action(
                gate, manifest["game_id"], player_id, snapshot, end_turn,
                parent, attempted_count, control_plan)
            attempted_count += 1
            action_count += int(outcome.submitted)
            rejected += int(outcome.submitted and outcome.status != "accepted")
            if outcome.status != "accepted":
                raise RuntimeError("engine rejected release action: {}".format(outcome.reason))
            full_loop_latency = (time.perf_counter() - full_turn_started) * 1000.0
            full_loop_latencies.append(full_loop_latency)
            parent = _metric(
                writer, snapshot.turn, parent, "turn_full_loop_latency_ms",
                full_loop_latency, manifest, engine_turn=snapshot.turn)

        # Allow endgame packets and observer totals to settle before audit.
        await asyncio.sleep(0.25)
        try:
            final_global = await _global_state(ws, timeout=5, player_id=player_id)
        except TimeoutError:
            pass

    loop_latency = (time.perf_counter() - turn_started) * 1000.0 / max(1, turns_executed)
    model_latency = (sum(model_latencies) / len(model_latencies)
                     if model_latencies else 0.0)
    full_loop_under_30 = (sum(value <= 30000 for value in full_loop_latencies)
                          / max(1, len(full_loop_latencies)))
    truth_techs = set((final_global or {}).get("techs", {}).get(
        "player{}".format(opponent.get("id", 1)), []))
    correct = []
    for belief in predictions:
        tech = str(belief.key.arguments[-1])
        is_true = tech in truth_techs
        correct.append(is_true)
        parent = _metric(
            writer, final_turn, parent, "belief_calibration_sample",
            belief.strength, manifest, truth=int(is_true),
            opponent=manifest["opponent"].get("id", "builtin-ai-experimental"),
            atom_id=belief.atom_id)
    calibration_error = (sum(abs(belief.strength - int(value))
                             for belief, value in zip(predictions, correct)) / len(correct)
                         if correct else 0.0)
    player_row = _player_row(final_global or {}, player_id)
    opponent_row = _player_row(final_global or {}, opponent.get("id", 1))
    if "score" not in player_row or "score" not in opponent_row:
        raise RuntimeError("final paired scores were not authoritative")
    player_score = float(player_row["score"])
    opponent_score = float(opponent_row["score"])
    score_margin = player_score - opponent_score
    score_lead = player_score > opponent_score
    # ``game_win`` is retained for the original M7 aggregate contract. Paired
    # impact claims use the explicitly named fixed-horizon score-lead endpoint.
    won = score_lead
    city_gain = max(0, len(snapshot.cities) - initial_city_count)
    final_citizens = sum(max(0, int(city.size or 0)) for city in snapshot.cities)
    technology_gain = max(0, len(snapshot.research.known_techs) - initial_tech_count)
    score_citizen_component = float(final_citizens)
    score_technology_component = float(len(snapshot.research.known_techs) * 2)
    score_residual_component = (
        player_score - score_citizen_component - score_technology_component)
    explored_positions = (max(0, len(impact_planner.visited_positions) - initial_position_count)
                          if impact_planner is not None else 0)
    meaningful_per_turn = float(decision_stats["meaningful_actions"]) / max(1, turns_executed)
    impact_turn_rate = float(len(impact_turns)) / max(1, turns_executed)
    effect_observed_rate = (float(decision_stats["effect_observed"])
                            / max(1, decision_stats["impact_actions"]))
    failover_recovery_rate = (float(decision_stats["failover_recoveries"])
                              / max(1, decision_stats["failover_attempts"]))
    metrics = [
        ("game_win", int(won)), ("score_lead_turn_n", int(score_lead)),
        ("score_turn_n", player_score),
        ("opponent_score_turn_n", opponent_score),
        ("score_margin_turn_n", score_margin),
        ("engine_rejected_action_rate", float(rejected) / max(1, action_count)),
        ("confabulation_write_through", 0.0),
        ("calibration_absolute_error", calibration_error),
        ("loop_latency_ms", loop_latency),
        ("model_latency_ms", model_latency),
        ("full_loop_under_30s_rate", full_loop_under_30),
        ("zombie_action_attempt_blocked", zombie_blocked),
        ("planned_engine_actions", planned_actions),
        ("meaningful_actions_per_turn", meaningful_per_turn),
        ("decision_impact_actions", decision_stats["impact_actions"]),
        ("decision_impact_turn_rate", impact_turn_rate),
        ("decision_effect_observed_rate", effect_observed_rate),
        ("decision_effect_confirmation_latency_ms",
         sum(effect_confirmation_latencies) / max(1, len(effect_confirmation_latencies))),
        ("decision_effect_confirmation_timeouts",
         decision_stats["effect_confirmation_timeouts"]),
        ("decision_no_effect_actions", decision_stats["no_effect"]),
        ("decision_no_effect_retries_blocked",
         impact_planner.no_effect_retries_blocked if impact_planner is not None else 0),
        ("decision_no_effect_failover_attempts", decision_stats["failover_attempts"]),
        ("decision_no_effect_failover_recoveries",
         decision_stats["failover_recoveries"]),
        ("decision_no_effect_failover_recovery_rate", failover_recovery_rate),
        ("model_safe_fallback_rate",
         float(decision_stats["safe_model_fallbacks"]) / max(1, turns_executed)),
        ("model_corrections_per_turn", float(corrections) / max(1, turns_executed)),
        ("action_type_diversity", len(action_type_counts)),
        ("cities_founded", city_gain),
        ("technologies_acquired", technology_gain),
        ("positions_explored", explored_positions),
        ("production_changes", decision_stats["production_changes"]),
        ("founder_production_changes",
         decision_stats["founder_production_changes"]),
        ("settlement_attempts", decision_stats["settlement_attempts"]),
        ("settlement_completions", city_gain),
        ("planner_capability_pruned_worker_moves",
         len(capability_pruned_worker_moves)),
        ("planner_nonprogress_moves_pruned", len(nonprogress_moves)),
        ("planner_founder_capable_unit_types",
         len(impact_planner.founder_capable_types)
         if impact_planner is not None else 0),
        ("tactical_actions", decision_stats["tactical_actions"]),
        ("production_projected_completion_eta_turns",
         sum(production_projection_etas) / max(1, len(production_projection_etas))),
        ("production_projected_score_value",
         sum(production_projection_values) / max(1, len(production_projection_values))),
        ("production_projected_build_cost",
         sum(production_projection_costs) / max(1, len(production_projection_costs))),
        ("production_projected_shield_surplus",
         sum(production_projection_shields) / max(1, len(production_projection_shields))),
        ("production_projected_pop_cost",
         sum(production_projection_pop_costs) / max(1, len(production_projection_pop_costs))),
        ("production_projection_ruleset_source_rate",
         sum(production_projection_ruleset_sources)
         / float(max(1, len(production_projection_ruleset_sources)))),
        ("score_component_citizens_turn_n", score_citizen_component),
        ("score_component_technology_turn_n", score_technology_component),
        ("score_component_residual_turn_n", score_residual_component),
        ("score_component_citizen_delta", final_citizens - initial_citizens),
        ("score_component_technology_delta", technology_gain * 2),
        ("score_gain", player_score - initial_score),
        ("abduction_truth_accuracy", (sum(correct) / len(correct)) if correct else 0.0),
    ]
    if replan_latencies:
        metrics.append(("replan_latency_ms", sum(replan_latencies) / len(replan_latencies)))
    if manifest["track"] == "induction":
        # Persist only in the memory-enabled conditions and scope by fixed opponent,
        # ruleset, and model version exactly as M4 requires.
        actual = "Espionage" in truth_techs
        memory.record(manifest["opponent"].get("id"), manifest["ruleset"],
                      manifest["model"], "has-tech:Espionage",
                      induction_prediction, actual)
        memory.save()
        metrics.append(("induction_prediction_accuracy",
                        int(induction_prediction == actual)))
        metrics.append(("induction_prior_samples",
                        induction_estimate["samples"]))
    for name, value in metrics:
        parent = _metric(writer, final_turn, parent, name, value, manifest,
                         seed=manifest["seed"], sequence=manifest.get("sequence", 0))
    writer.emit("run_completed", final_turn, {
        "status": "completed", "summary": {
            "actions": action_count, "calibration_samples": len(predictions),
            "model_corrections": corrections, "opponent": opponent.get("name"),
            "decision_impact_actions": decision_stats["impact_actions"],
            "decision_no_effect_retries_blocked": (
                impact_planner.no_effect_retries_blocked
                if impact_planner is not None else 0),
            "decision_no_effect_failover_attempts": decision_stats["failover_attempts"],
            "decision_no_effect_failover_recoveries": (
                decision_stats["failover_recoveries"]),
            "decision_effect_confirmation_timeouts": (
                decision_stats["effect_confirmation_timeouts"]),
            "meaningful_actions": decision_stats["meaningful_actions"],
            "founder_production_changes": (
                decision_stats["founder_production_changes"]),
            "settlement_attempts": decision_stats["settlement_attempts"],
            "settlement_completions": city_gain,
            "planner_capability_pruned_worker_moves": (
                len(capability_pruned_worker_moves)),
            "planner_nonprogress_moves_pruned": len(nonprogress_moves),
            "planner_founder_capable_unit_types": (
                len(impact_planner.founder_capable_types)
                if impact_planner is not None else 0),
            "planned_engine_actions": planned_actions,
            "opponent_score": opponent_score,
            "outcome_definition": "fixed_horizon_score_lead",
            "score": player_score, "score_lead": score_lead,
            "score_margin": score_margin, "won": won,
            "zombie_attempts_blocked": zombie_blocked,
        }}, caused_by=[parent])
    return {
        "capability_audit": context.audit(), "calibration_samples": len(predictions),
        "completed": True, "engine_actions": action_count,
        "infrastructure_failure": False, "loss": not won,
        "model_latency_ms": model_latency, "rejected_actions": rejected,
        "decision_impact_actions": decision_stats["impact_actions"],
        "decision_no_effect_retries_blocked": (
            impact_planner.no_effect_retries_blocked
            if impact_planner is not None else 0),
        "decision_no_effect_failover_attempts": decision_stats["failover_attempts"],
        "decision_no_effect_failover_recoveries": decision_stats["failover_recoveries"],
        "initial_legal_action_families": initial_legal_action_families,
        "initial_state_fingerprint": initial_state_fingerprint,
        "meaningful_actions": decision_stats["meaningful_actions"],
        "founder_production_changes": decision_stats["founder_production_changes"],
        "settlement_attempts": decision_stats["settlement_attempts"],
        "settlement_completions": city_gain,
        "planner_capability_pruned_worker_moves": (
            len(capability_pruned_worker_moves)),
        "planner_nonprogress_moves_pruned": len(nonprogress_moves),
        "planner_founder_capable_unit_types": (
            len(impact_planner.founder_capable_types)
            if impact_planner is not None else 0),
        "planned_engine_actions": planned_actions,
        "zombie_attempts_blocked": zombie_blocked,
    }


def _terminate_proxy(game_id, token, required=False):
    request = urllib.request.Request(
        "http://127.0.0.1:8002/api/game/{}/terminate".format(game_id),
        data=b'{"mode":"hard"}', method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except Exception as error:
        if required:
            detail = ""
            if isinstance(error, urllib.error.HTTPError):
                try:
                    detail = ": " + error.read().decode("utf-8", "replace")
                except Exception:
                    detail = ""
            raise RuntimeError(
                "proxy hard termination failed for {}{}".format(game_id, detail))


def _recycle_server(port):
    container = os.environ.get("FREECIV_SERVER_CONTAINER", "fciv-net")
    def find_pid():
        output = subprocess.check_output(
            ["docker", "exec", container, "ps", "-eo", "pid,args"], text=True)
        for line in output.splitlines():
            if "freeciv-web" not in line or "--port {}".format(port) not in line:
                continue
            match = re.match(
                r"\s*(\d+)\s+.*freeciv-web .*--port {}(?:\s|$)".format(port), line)
            if match is not None:
                return match.group(1)
        return None

    old_pid = find_pid()
    if old_pid is not None:
        subprocess.run(["docker", "exec", container, "kill", old_pid], check=False,
                       stdout=subprocess.DEVNULL)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        time.sleep(0.25)
        current_pid = find_pid()
        if current_pid is not None and current_pid != old_pid:
            time.sleep(0.5)
            return
    raise RuntimeError("civserver port {} did not recycle".format(port))


def run_game(run_dir, manifest, context):
    if not 6001 <= int(manifest["port"]) <= 6009:
        raise ValueError("engine-live requires a dedicated multiplayer port")
    token = os.environ.get("FREECIV_API_TOKEN", "test-token-fc3d-001")
    # An interrupted attempt can leave proxy-side game/session metadata after its
    # civserver has gone away. Clear that metadata before recycling the dedicated
    # server; otherwise the proxy may report the old configuration as already
    # applied and skip configuring the fresh process.
    _terminate_proxy(manifest["game_id"], token, required=True)
    # Every job starts from a newly spawned process so no autosave/session state can
    # leak across seeds or conditions.
    _recycle_server(int(manifest["port"]))
    try:
        _ollama_readiness(manifest)
        return asyncio.run(_play(run_dir, manifest, context))
    finally:
        _terminate_proxy(manifest["game_id"], token)
        _recycle_server(int(manifest["port"]))
