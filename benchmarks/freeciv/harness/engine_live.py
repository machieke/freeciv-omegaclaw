"""Release backend that drives completed games through the real FreeCiv proxy.

The global observer is queried only for navigation by the test driver and for
post-game scoring/calibration.  Agent beliefs are created exclusively from the
player connection's packet-visible foreign units.
"""

import asyncio
from datetime import datetime
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
from freeciv_agent.llm import GoalGrader, ProposalParser, SymbolCatalog
from freeciv_agent.monitoring import AtomRevision, LocalRepairer, PlanMonitor
from freeciv_agent.oracle import CrispStateView, DependencyOracle, Goal
from freeciv_agent.pf_runtime import (
    emit_runtime_activation,
    validate_runtime_activation,
)
from freeciv_agent.pressure import (
    pressure_dependency_view,
)
from freeciv_agent.planning import (BranchScore, NonPlan, Plan, PlanAssumption,
                                    PlanStep, PlanningSnapshot, ProofScheduler,
                                    ResourceLedger, GroundedImpactPlanner,
                                    DeferredImpactOutcomeLedger,
                                    ImpactTurnBudget,
                                    ControlEventEmitter)
from freeciv_agent.rulesets.compiler import compile_ruleset
from freeciv_agent.state import ProxyStateDTO, SnapshotStore, StateSummaryService
from .domain_observability import DomainObservabilityEmitter


_IR = None
_STACK = None
_MODEL_JSON_CACHE = {}
_MODEL_CACHE_LOCK = threading.RLock()
_MODEL_READINESS_LOCK = threading.Lock()
_MODEL_READINESS_VERIFIED = set()
_STACK_LOCK = threading.RLock()
_LAST_CLEAN_SERVER_PIDS = {}
SELECTION_CALL_POLICY = "canonical-singleton-bypass-v1"
READINESS_POLICY = "chat-once-expiry-aware-resident-v2"


def _websocket_compression():
    """Disable costly loopback deflate unless a remote harness opts in."""
    return (
        "deflate"
        if os.environ.get(
            "FREECIV_PROXY_WEBSOCKET_COMPRESSION", "").lower()
        in {"1", "true", "yes", "on"}
        else None)


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
                _STACK = (
                    _IR, catalog, ProposalParser(catalog), oracle,
                    ProofScheduler())
    return _STACK


def _metric(writer, turn, parent, name, value, manifest, **labels):
    values = {"condition": manifest["condition_id"], "track": manifest["track"]}
    values.update({key: str(value) for key, value in labels.items()})
    event = writer.emit("metric_sample", turn, {
        "labels": values, "name": name,
        "unit": (
            "ms" if name.endswith("_ms")
            else "turns" if name.endswith("_turns")
            else "bytes" if name.endswith("_bytes")
            else "ratio"),
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


def _ollama_model_residency(native_endpoint, model, timeout):
    """Return the exact resident model row, or ``None`` when it is unavailable."""
    request = urllib.request.Request(native_endpoint + "/api/ps")
    try:
        with urllib.request.urlopen(request, timeout=min(5.0, timeout)) as response:
            body = json.load(response)
    except Exception:
        return None
    models = body.get("models") if isinstance(body, dict) else None
    if not isinstance(models, list):
        return None
    return next((
        row for row in models
        if (isinstance(row, dict)
            and model in (row.get("name"), row.get("model")))), None)


def _ollama_residency_remaining_seconds(row, now=None):
    """Parse Ollama's nanosecond ISO expiry conservatively."""
    value = row.get("expires_at") if isinstance(row, dict) else None
    if not isinstance(value, str) or not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    # Python 3.8 accepts microseconds; Ollama emits nanoseconds.
    normalized = re.sub(
        r"(\.\d{6})\d+(?=[+-]\d\d:\d\d$)", r"\1", normalized)
    try:
        expires_at = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if expires_at.tzinfo is None:
        return None
    return expires_at.timestamp() - (
        time.time() if now is None else float(now))


def _ollama_refresh_resident_model(native_endpoint, model, keep_alive, timeout):
    """Refresh a verified resident model without generating completion tokens."""
    request = urllib.request.Request(
        native_endpoint + "/api/generate",
        data=json.dumps({
            "model": model, "prompt": "", "stream": False,
            "keep_alive": keep_alive,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=min(10.0, timeout)) as response:
        body = json.load(response)
    if (not isinstance(body, dict) or body.get("error")
            or body.get("done") is not True):
        raise RuntimeError("resident model keep-alive refresh was not completed")
    result = dict(body)
    result.update({
        "readiness_method": "resident_keep_alive_refresh",
        "readiness_reused": True,
    })
    return result


def _validate_readiness_chat(body):
    if not isinstance(body, dict) or body.get("error"):
        raise RuntimeError(
            "configured Ollama model readiness returned an error: {}".format(
                body.get("error") if isinstance(body, dict) else body))
    if body.get("done") is False:
        raise RuntimeError("configured Ollama model readiness did not complete")
    try:
        ready = json.loads(body["message"]["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "configured Ollama model readiness returned invalid JSON: {}".format(exc))
    if ready != {"ready": True}:
        raise RuntimeError(
            "configured Ollama model readiness returned unexpected JSON: {}".format(
                ready))


def _ollama_readiness(manifest):
    """Load and keep the configured model resident before an engine arm.

    The verified-response cache can make a long arm appear model-idle.  Ollama
    may unload the model during that idle period, turning the next real request
    into a cold load that exceeds the bounded turn budget. The first preflight
    for each endpoint/model/think tuple performs a complete native chat request.
    Later arms check residency under the same process lock. An exact model row
    whose reported expiry exceeds the configured safety floor is reused without
    another model request. Missing, malformed, or near-expiry residency is
    refreshed without generating completion tokens; a failed refresh falls back
    to the complete chat validation.
    """
    model_config = manifest.get("model_config", {})
    timeout = float(model_config.get("readiness_timeout_seconds", 90))
    residency_floor = float(model_config.get(
        "readiness_residency_floor_seconds", 300))
    if timeout <= 0:
        raise ValueError("model readiness timeout must be positive")
    if residency_floor <= 0:
        raise ValueError("model readiness residency floor must be positive")
    if model_config.get("readiness_policy") != READINESS_POLICY:
        raise ValueError("unsupported Ollama readiness policy")
    native_endpoint = _ollama_native_endpoint()
    keep_alive = str(model_config.get("keep_alive", "30m"))
    readiness_key = (
        native_endpoint, manifest["model"], bool(model_config.get("think", False)))
    payload = {
        "model": manifest["model"],
        "stream": False,
        "think": bool(model_config.get("think", False)),
        "keep_alive": keep_alive,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 16},
        "messages": [
            {"role": "system", "content": "Return one JSON object only; no markdown."},
            {"role": "user", "content": "Return exactly {\"ready\":true}."},
        ],
    }
    request = urllib.request.Request(
        native_endpoint + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    # Multiple engine workers may begin at once. Serialize readiness calls so a
    # cold model load is never duplicated or CPU-contended.
    if not _MODEL_READINESS_LOCK.acquire(timeout=timeout):
        raise RuntimeError("model readiness budget exhausted waiting for local model")
    try:
        if readiness_key in _MODEL_READINESS_VERIFIED:
            resident = _ollama_model_residency(
                native_endpoint, manifest["model"], timeout)
            if resident is not None:
                remaining = _ollama_residency_remaining_seconds(resident)
                if (remaining is not None
                        and remaining >= residency_floor):
                    return {
                        "done": True,
                        "model": manifest["model"],
                        "readiness_method": "resident_expiry_reuse",
                        "readiness_remaining_seconds": remaining,
                        "readiness_reused": True,
                    }
                try:
                    result = _ollama_refresh_resident_model(
                        native_endpoint, manifest["model"], keep_alive, timeout)
                    result["readiness_remaining_seconds"] = None
                    return result
                except Exception:
                    # A failed optional fast path must recover through the
                    # original full chat contract rather than weaken readiness.
                    pass
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.load(response)
        except Exception as exc:
            raise RuntimeError(
                "configured Ollama model readiness failed: {}".format(exc))
        _validate_readiness_chat(body)
        _MODEL_READINESS_VERIFIED.add(readiness_key)
        result = dict(body)
        result.update({
            "readiness_method": "complete_chat",
            "readiness_remaining_seconds": None,
            "readiness_reused": False,
        })
        return result
    finally:
        _MODEL_READINESS_LOCK.release()


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


def _parse_constrained_proposal(raw, summary, catalog, parser=None):
    """Parse one proposal through the reusable production schema/catalog gate."""
    if not hasattr(summary, "to_dict"):
        raise TypeError("LLM state input must be a query summary DTO")
    return (parser or ProposalParser(catalog)).parse(raw)


def _constrained_proposal(manifest, summary, catalog, targets, parser=None):
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
    proposal = _parse_constrained_proposal(
        raw, summary, catalog, parser=parser)
    return proposal, value, latency, corrections


def _canonical_singleton_proposal(
        manifest, summary, catalog, targets, parser=None):
    """Build the only legal canonical proposal without asking the model to echo it."""
    if len(targets) != 1:
        raise ValueError("canonical singleton selection requires exactly one target")
    target = targets[0]
    goal = {
        "goal_id": "goal-live-1", "target_id": target.rule_id,
        "predicate": target.target_predicate,
        "arguments": ["player", target.rule_name],
    }
    expanded = {
        "schema_version": "1.0",
        "proposal_id": "proposal-canonical-" + structural_hash([
            SELECTION_CALL_POLICY, target.rule_id, summary.to_dict()])[:20],
        "goals": [goal], "claims": [],
        "rationale": "single canonical live goal; model selection is unnecessary",
        "selection": goal["goal_id"],
    }
    raw = json.dumps(expanded, sort_keys=True, separators=(",", ":"))
    # Keep the same production parser and symbol-catalog gates as model output.
    return _parse_constrained_proposal(
        raw, summary, catalog, parser=parser)


def _decision_state_fingerprint(snapshot):
    """Hash authoritative decision inputs without transport/cadence identity."""
    return structural_hash({
        "map": snapshot.map_dict(),
        "own_state": snapshot.own_state_dict(),
        "phase": snapshot.phase,
        "player_id": snapshot.player_id,
        # A packet burst can change executability without changing units,
        # cities, or map facts. Stability therefore covers the exact canonical
        # legal set consumed by ExecutionGate as well as state projections.
        "legal_actions_digest": snapshot.legal_actions_digest,
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
    if not (snapshot.player_alive is True
            and snapshot.ruleset_ready and snapshot.economy.available
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


def _player_eliminated(snapshot):
    """Return the exact packet-backed terminal player state.

    Asset collections are not a safe death signal: a living player may own cities
    but no units, while an eliminated connection may retain stale city packets.
    Missing player status therefore fails closed instead of being inferred.
    """
    return snapshot.player_alive is False


def _game_terminal(snapshot):
    """Return packet/session-backed terminal state without inferring from assets."""
    return snapshot.game_over or _player_eliminated(snapshot)


async def _state(ws, game_id, minimum_turn=1, minimum_source_seq=None, timeout=20.0,
                 require_decision_ready=False, require_own_units=False,
                 stable_samples=1, poll_interval=0.05, diagnostics=None,
                 settle_first_projection=False,
                 include_movement_routes=False,
                 include_combat_probabilities=False):
    if (isinstance(stable_samples, bool) or not isinstance(stable_samples, int)
            or not 1 <= stable_samples <= 5):
        raise ValueError("stable_samples must be in 1..5")
    if not 0.05 <= float(poll_interval) <= 1.0:
        raise ValueError("poll_interval must be in [0.05,1]")
    call_started = time.perf_counter()

    def record(name, value):
        if diagnostics is not None:
            diagnostics[name] = diagnostics.get(name, 0.0) + value

    def finish(success):
        record("calls", 1)
        record("successful_calls", int(success))
        record("latency_ms", (time.perf_counter() - call_started) * 1000.0)

    deadline = time.monotonic() + timeout
    stable_fingerprint = None
    stable_count = 0
    stable_raw = None
    stable_snapshot = None
    observed_source_seq = None
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        query_options = {}
        if (stable_count > 0 and observed_source_seq is not None
                and remaining > 0.001):
            # The first full projection is built under the proxy's packet-state
            # lock. Confirm later samples with a bounded conditional wait: an
            # unchanged packet revision proves the deterministic projection and
            # exact legal set remain identical without retransmitting them.
            wait_ms = min(
                5000,
                int(max(0.001, min(float(poll_interval), remaining)) * 1000))
            if wait_ms >= 1:
                query_options = {
                    "after_source_seq": int(observed_source_seq),
                    "wait_timeout_ms": wait_ms,
                    "accept_unchanged": True,
                }
                record("settle_wait_requested_ms", float(wait_ms))
        # Do not spend a request/sleep cycle rediscovering a revision the
        # caller has already consumed. Once a ready candidate is observed,
        # a conditional wait above supplies the independent stability check.
        elif stable_count == 0 and remaining > 0.05:
            wait_after = observed_source_seq
            if minimum_source_seq is not None and minimum_source_seq > 0:
                wait_after = max(
                    minimum_source_seq - 1,
                    -1 if wait_after is None else wait_after)
            if wait_after is not None and wait_after >= 0:
                wait_ms = min(5000, int(max(0.001, remaining - 0.05) * 1000))
                if wait_ms >= 1:
                    settle_ms = min(
                        wait_ms,
                        int(float(poll_interval) * 1000))
                    query_options = {
                        "after_source_seq": int(wait_after),
                        "wait_timeout_ms": wait_ms,
                    }
                    # A caller that consumes the complete action result may
                    # request the same packet-lock plus quiet-interval proof
                    # used at turn boundaries. Candidate-specific effect
                    # predicates still run after this response, so the marker
                    # removes a duplicate full transfer without weakening
                    # action attribution.
                    if require_decision_ready or settle_first_projection:
                        query_options["settle_quiet_ms"] = settle_ms
                        record("settle_wait_requested_ms", float(settle_ms))
        query_started = time.perf_counter()
        query_diagnostics = {}
        state_query_options = dict(query_options)
        if include_movement_routes:
            state_query_options[
                "include_movement_routes"] = True
        if include_combat_probabilities:
            state_query_options[
                "include_combat_probabilities"] = True
        if diagnostics is not None:
            state_query_options["diagnostics"] = query_diagnostics
        try:
            raw = await asyncio.wait_for(
                turncycle.get_state(
                    ws, "pln_authoritative",
                    **state_query_options),
                timeout=max(0.05, remaining))
        except asyncio.TimeoutError:
            record("queries", 1)
            record("query_latency_ms", (
                time.perf_counter() - query_started) * 1000.0)
            break
        record("queries", 1)
        record("query_latency_ms", (
            time.perf_counter() - query_started) * 1000.0)
        for name, value in query_diagnostics.items():
            prefix = (
                "client_"
                if name in {"json_decode_ms", "wire_bytes"}
                else "server_")
            record(prefix + name, value)
        if raw and raw.get("type") == "state_unchanged":
            unchanged_seq = raw.get("source_seq")
            unchanged_turn = raw.get("turn")
            if (stable_count > 0 and stable_raw is not None
                    and stable_snapshot is not None
                    and unchanged_seq == observed_source_seq
                    and unchanged_turn is not None
                    and int(unchanged_turn) >= minimum_turn):
                stable_count += 1
                if stable_count >= stable_samples:
                    finish(True)
                    return stable_raw, stable_snapshot
                continue
            stable_fingerprint = None
            stable_count = 0
            stable_raw = None
            stable_snapshot = None
            continue
        source_seq = raw.get("authoritative", {}).get("source_seq") if raw else None
        if source_seq is not None:
            try:
                observed_source_seq = int(source_seq)
            except (TypeError, ValueError):
                observed_source_seq = None
        raw_game = (
            raw.get("game")
            if raw and isinstance(raw.get("game"), dict) else {})
        raw_game_over = raw_game.get("is_over") is True
        source_ready = (
            raw_game_over
            or
            minimum_source_seq is None
            or (source_seq is not None and int(source_seq) >= minimum_source_seq))
        if raw and source_ready:
            stability = raw.get("authoritative", {}).get("stability", {})
            if isinstance(stability, dict) and stability:
                record("settled_markers", 1)
            parse_started = time.perf_counter()
            snapshot = ProxyStateDTO.parse(game_id, source_seq, raw).to_snapshot()
            record("parse_latency_ms", (
                time.perf_counter() - parse_started) * 1000.0)
            # A dead player receives no next begin-turn packet. Accept the exact
            # terminal player packet at its current turn even when the caller is
            # waiting for ``minimum_turn = current + 1``.
            if _game_terminal(snapshot):
                finish(True)
                return raw, snapshot
            turn_ready = int(raw.get("turn", 0)) >= minimum_turn
            ready = (snapshot.player_alive is not None and turn_ready
                     and (not require_decision_ready or _decision_state_ready(
                         snapshot, require_own_units=require_own_units)))
            if ready:
                fingerprint = _decision_state_fingerprint(snapshot)
                if fingerprint == stable_fingerprint:
                    stable_count += 1
                else:
                    stable_fingerprint = fingerprint
                    stable_count = 1
                if (isinstance(stability, dict)
                        and stability.get("policy") == "source-seq-quiet-v1"
                        and stability.get("source_seq") == source_seq
                        and isinstance(
                            stability.get("quiet_interval_ms"), int)
                        and not isinstance(
                            stability.get("quiet_interval_ms"), bool)
                        and stability["quiet_interval_ms"]
                            >= int(float(poll_interval) * 1000)):
                    # The proxy built this exact packet revision under the
                    # packet/projection lock and verified it was unchanged
                    # after the requested quiet interval. It is
                    # therefore the same two-sample proof as one full response
                    # followed by an exact state_unchanged acknowledgement.
                    stable_count = max(stable_count, 2)
                    record("settled_responses", 1)
                stable_raw = raw
                stable_snapshot = snapshot
                if stable_count >= stable_samples:
                    finish(True)
                    return raw, snapshot
            else:
                stable_fingerprint = None
                stable_count = 0
                stable_raw = None
                stable_snapshot = None
        if stable_count > 0 and observed_source_seq is not None:
            continue
        settle_wait = min(float(poll_interval), max(0.0, remaining))
        record("settle_wait_requested_ms", settle_wait * 1000.0)
        await asyncio.sleep(settle_wait)
    finish(False)
    raise TimeoutError("authoritative state did not reach turn {}".format(minimum_turn))


async def _next_turn_state(ws, game_id, api_token, agent_id, minimum_turn,
                           minimum_source_seq, diagnostics=None,
                           timeout=20.0, include_movement_routes=False,
                           include_combat_probabilities=False):
    """Wait for one turn boundary, recovering one lost phase-done signal.

    A submitted ``end_turn`` can be acknowledged before the civserver consumes
    its phase-done packet.  If no authoritative next-turn revision arrives
    within the normal bounded wait, use the proxy's authenticated REST fallback
    once and prove recovery by waiting for the same minimum turn and source
    revision.  A second timeout still fails the run, so recovery cannot turn a
    persistently wedged engine into claim-eligible evidence.
    """

    def record(name):
        if diagnostics is not None:
            diagnostics[name] = diagnostics.get(name, 0.0) + 1.0

    state_options = {
        "minimum_turn": minimum_turn,
        "minimum_source_seq": minimum_source_seq,
        "require_decision_ready": True,
        "stable_samples": 2,
        "diagnostics": diagnostics,
        "timeout": timeout,
    }
    if include_movement_routes:
        state_options[
            "include_movement_routes"] = True
    if include_combat_probabilities:
        state_options[
            "include_combat_probabilities"] = True
    try:
        return await _state(ws, game_id, **state_options)
    except TimeoutError:
        record("force_end_turn_recovery_attempts")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, _force_end_turn_proxy, game_id, api_token, agent_id)
        try:
            result = await _state(ws, game_id, **state_options)
        except TimeoutError:
            record("force_end_turn_recovery_failures")
            raise
        record("force_end_turn_recovery_successes")
        return result


def _global_state_ready(state, player_id=None, minimum_turn=None):
    if not (state.get("units") and state.get("players") and state.get("techs")):
        return False
    if minimum_turn is not None:
        turn = state.get("turn")
        if (isinstance(turn, bool) or not isinstance(turn, (int, float))
                or not math.isfinite(float(turn))
                or int(turn) != float(turn)
                or int(turn) < int(minimum_turn)):
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


async def _global_state(ws, timeout=15.0, player_id=None, minimum_turn=None,
                        poll_interval=0.05):
    if not 0.05 <= float(poll_interval) <= 1.0:
        raise ValueError("poll_interval must be in [0.05,1]")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await ws.send(json.dumps({"type": "global_state_query"}))
        remaining = deadline - time.monotonic()
        response = await turncycle.recv_until(
            ws, {"global_state_response", "error"},
            timeout=min(10.0, max(0.05, remaining)))
        if response and response.get("type") == "global_state_response":
            state = response.get("data", {})
            if _global_state_ready(
                    state, player_id=player_id, minimum_turn=minimum_turn):
                return state
        await asyncio.sleep(min(float(poll_interval), max(
            0.0, deadline - time.monotonic())))
    raise TimeoutError("observer global state was not populated")


def _needs_turn_global_state(impact_planner):
    # Plain conditions navigate with the observer-backed scout driver.
    # Scheduler conditions route through packet-visible GroundedImpactPlanner
    # candidates and need observer state only for initial identity/fidelity and
    # final fixed-horizon scoring.
    return impact_planner is None


def _target_rule(ir, known):
    candidates = [rule for rule in ir.rules if rule.target_kind == "tech" and not rule.disabled
                  and rule.rule_name != "None"]
    return next((rule for rule in candidates if rule.rule_name not in known), candidates[0])


def _rule_numeric(rule, field, default=0.0):
    value = getattr(rule, "quantitative", {}).get(field, default)
    if isinstance(value, dict):
        value = value.get("value", default)
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else float(default))


def _rule_trait_values(rule, name):
    trait = getattr(rule, "traits", {}).get(name, {})
    values = trait.get("values", ()) if isinstance(trait, dict) else ()
    return {
        str(value).strip().lower().replace("_", " ")
        for value in values
    }


def _strategic_unlock_value(ir, technology, known):
    """Score immediate ruleset unlocks without inventing future legality."""
    known_after = set(map(str, known)) | {str(technology.rule_name)}
    value = 0.0
    for rule in ir.rules:
        if rule.disabled or rule.target_kind not in (
                "unit", "building", "improvement"):
            continue
        required = {
            str(requirement.name)
            for requirement in rule.antecedents
            if requirement.kind == "Tech" and requirement.present}
        if technology.rule_name not in required or required - known_after:
            continue
        if rule.target_kind == "unit":
            unit_classes = _rule_trait_values(rule, "class")
            unit_flags = _rule_trait_values(rule, "flags")
            if ("missile" in unit_classes
                    or unit_flags.intersection(
                        {"nuclear", "oneattack", "one attack"})):
                continue
            attack = _rule_numeric(rule, "attack")
            defense = _rule_numeric(rule, "defense")
            hitpoints = max(1.0, _rule_numeric(rule, "hitpoints", 10.0))
            firepower = max(1.0, _rule_numeric(rule, "firepower", 1.0))
            transport = _rule_numeric(rule, "transport_cap")
            value += (
                (attack * 1.15 + defense) * hitpoints * firepower / 10.0
                + transport * 2.0)
        else:
            name = str(rule.rule_name).lower()
            value += (
                18.0 if any(token in name for token in (
                    "factory", "manufacturing", "power plant",
                    "offshore platform")) else
                16.0 if any(token in name for token in (
                    "university", "research lab", "library")) else
                14.0 if any(token in name for token in (
                    "bank", "stock exchange", "marketplace")) else
                10.0)
    return value


def _target_rules(ir, known, count=2, available_names=()):
    available = {str(name) for name in available_names}
    candidates = [rule for rule in ir.rules if rule.target_kind == "tech"
                  and not rule.disabled and rule.rule_name != "None"
                  and rule.rule_name not in known
                  and (not available or rule.rule_name in available)]
    if not available:
        # Choose from the exact current research frontier. A future technology
        # may directly unlock a powerful unit but still hide a long prerequisite
        # chain; ranking it as an "immediate" unlock caused the proof planner to
        # spend hundreds of turns on the chain while a stronger current unlock
        # (for example Armor) was already researchable.
        known_names = set(map(str, known))
        frontier = [
            rule for rule in candidates
            if all(
                str(requirement.name) in known_names
                for requirement in rule.antecedents
                if requirement.kind == "Tech" and requirement.present)
        ]
        if frontier:
            candidates = frontier
    candidates.sort(key=lambda rule: (_tech_cost(rule), rule.rule_name, rule.rule_id))
    if not candidates:
        return (_target_rule(ir, known),)
    if len(candidates) == 1 or count == 1:
        return (candidates[0],)
    cheapest = candidates[0]
    strategic = max(candidates, key=lambda rule: (
        _strategic_unlock_value(ir, rule, known),
        -_tech_cost(rule), rule.rule_name, rule.rule_id))
    # A positive compiled unlock is already a complete deterministic decision.
    # Sending both "cheapest" and "strategic" through the model allowed the
    # cheaper branch to win despite the declared objective and consumed a model
    # call. Keep the cheapest fallback only when no frontier node has grounded
    # strategic value.
    return (
        (strategic,)
        if _strategic_unlock_value(ir, strategic, known) > 0
        else (cheapest,))


def _selection_target_rules(ir, snapshot, available_names):
    """Return the only relevant active goal when no new choice is executable."""
    if not available_names and snapshot.research.target_name:
        active = next((
            rule for rule in ir.rules
            if (rule.target_kind == "tech" and not rule.disabled
                and rule.rule_name == snapshot.research.target_name)), None)
        if active is not None:
            return (active,)
    return _target_rules(
        ir, snapshot.research.known_techs,
        available_names=available_names)


def _active_research_continuation(snapshot, available_names, targets):
    """Whether the exact catalog proves research is already in progress."""
    return bool(
        not available_names
        and snapshot.research.target_name
        and len(targets) == 1
        and targets[0].rule_name == snapshot.research.target_name)


def _live_tech_costs(ir, snapshot):
    costs = {rule.rule_name: _tech_cost(rule) for rule in ir.rules
             if rule.target_kind == "tech" and not rule.disabled}
    for option in snapshot.research_options:
        if option.tech_cost is None:
            continue
        costs[option.tech_name] = int(option.tech_cost)
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
                          ordinal, plan=None, diagnostics=None):
    action_id = "engine-action-" + structural_hash([
        snapshot.snapshot_id, action, ordinal])[:20]
    proposed = ProposedAction(
        action_id, dict(action), snapshot.snapshot_id, snapshot.legal_actions_digest,
        None if plan is None else plan.plan_id,
        None if plan is None or not plan.steps else plan.steps[0].step_id)
    outcome = await gate.execute_async(
        game_id, player_id, proposed, caused_by=[parent],
        diagnostics=diagnostics)
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


def _impact_refresh_timeout(planner, candidate):
    """Use a stronger barrier for accepted actions that can consume an actor."""
    if candidate.terminal_on_accept:
        return planner.terminal_refresh_timeout_seconds
    return planner.refresh_timeout_seconds


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


def _retain_terminal_predictions(predictions, revisions):
    """Retain the latest post-game calibration prediction for each atom."""
    predictions.update((belief.atom_id, belief) for belief in revisions)


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
                    ir, catalog, proposal_parser, oracle, scheduler, writer,
                    parent, diagnostics=None):
    """Run proposal, verification/grading, dependency, and planning for one turn."""
    def record_stage(name, started):
        if diagnostics is not None:
            diagnostics[name] = diagnostics.get(name, 0.0) + (
                time.perf_counter() - started) * 1000.0

    stage_started = time.perf_counter()
    if context.capabilities["authoritative_state"]:
        context.use("authoritative_state")
        summary = StateSummaryService(store).query(manifest["game_id"], player_id)
    else:
        summary = _plain_state_summary(raw)
    record_stage("summary_ms", stage_started)
    stage_started = time.perf_counter()
    available_research = _available_research_names(raw)
    targets = ()
    target = None
    if _needs_cognitive_stack(context):
        targets = _selection_target_rules(
            ir, snapshot, available_research)
        target = targets[0]
    active_research_continuation = bool(
        context.capabilities["constrained_llm"]
        and manifest.get("model_config", {}).get(
            "selection_call_policy") == SELECTION_CALL_POLICY
        and _active_research_continuation(
            snapshot, available_research, targets))
    record_stage("setup_ms", stage_started)

    stage_started = time.perf_counter()
    proposal = None
    plain_selection = "end_turn"
    model_started = time.perf_counter()
    model_error = None
    model_called = True
    model_call_avoided = False
    event_type = "llm_proposal"
    if (context.capabilities["constrained_llm"] and len(targets) == 1
            and manifest.get("model_config", {}).get(
                "selection_call_policy") == SELECTION_CALL_POLICY):
        context.use("constrained_llm")
        proposal = _canonical_singleton_proposal(
            manifest, summary, catalog, targets, parser=proposal_parser)
        latency = 0.0
        corrections = 0
        model_called = False
        model_call_avoided = True
        event_type = "goal_selection"
        payload = {
            "candidate_count": 1,
            "goal": proposal.goals[0].to_dict(),
            "model_call_avoided": True,
            "policy": SELECTION_CALL_POLICY,
            "proposal_id": proposal.proposal_id,
            "selection_id": proposal.selection,
            "source": "canonical_catalog",
        }
    else:
        try:
            if context.capabilities["constrained_llm"]:
                context.use("constrained_llm")
                proposal, _, latency, corrections = _constrained_proposal(
                    manifest, summary, catalog, targets,
                    parser=proposal_parser)
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
        event_type, snapshot.turn, payload, caused_by=[parent])
    parent = proposal_event["event_id"]
    record_stage("proposal_ms", stage_started)
    stage_started = time.perf_counter()
    if active_research_continuation and model_error is None:
        verification = writer.emit("verification", snapshot.turn, {
            "verification_id": "verify-continuation-" + proposal.proposal_id,
            "proposal_id": proposal.proposal_id,
            "claim_id": proposal.selection,
            "verdict": "believe",
            "check": "active_research_has_no_new_selection_action",
            "evidence_atom_ids": [],
        }, caused_by=[parent])
        record_stage("finalization_ms", stage_started)
        return (
            None, "end_turn", verification["event_id"], latency, corrections,
            False, model_called, model_call_avoided)
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
        record_stage("finalization_ms", stage_started)
        if _claim_eligible_manifest(manifest):
            raise RuntimeError(
                "claim-eligible arm cannot use model fallback: {}".format(
                    type(model_error).__name__))
        return (None, "end_turn", gap["event_id"], latency, corrections, True,
                model_called, model_call_avoided)

    crisp = (CrispStateView(
        snapshot.snapshot_id, known_techs=snapshot.research.known_techs,
        player="player") if context.capabilities["dependency_oracle"] else None)
    numeric = (PlanningSnapshot(
        snapshot.snapshot_id, snapshot.turn,
        int(snapshot.research.beakers_per_turn or 0),
        int(snapshot.economy.gold or 0),
        current_research=snapshot.research.target_name,
        current_progress=int(snapshot.research.progress or 0),
        tech_costs=_live_tech_costs(ir, snapshot),
        legal_actions_digest=snapshot.legal_actions_digest)
               if context.capabilities["scheduler"] else None)
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
    record_stage("finalization_ms", stage_started)
    return (active_plan, plain_selection, parent, latency, corrections, False,
            model_called, model_call_avoided)


async def _play(run_dir, manifest, context):
    import websockets

    pf_runtime = validate_runtime_activation(
        manifest["pf_pln_runtime"],
        "engine-live",
        context.capabilities,
        manifest["impact_policy"],
    )
    movement_routes_enabled = bool(
        manifest["impact_policy"].get(
            "pressure_native_movement_routes_enabled", False))
    combat_probabilities_enabled = bool(
        manifest["impact_policy"].get(
            "pressure_native_combat_probabilities_enabled",
            False))
    combat_operations_enabled = bool(
        manifest["impact_policy"].get(
            "pressure_combat_operations_enabled",
            False))
    combat_operation_authority_enabled = bool(
        manifest["impact_policy"].get(
            "pressure_combat_operation_authority_enabled",
            False))
    city_defense_operation_authority_enabled = bool(
        manifest["impact_policy"].get(
            "pressure_city_defense_operation_authority_enabled",
            False))
    combat_operation_action_budget = (
        int(manifest["impact_policy"][
            "max_actions_per_turn"])
        if combat_operations_enabled
        else None)
    if _needs_cognitive_stack(context):
        ir, catalog, proposal_parser, oracle, scheduler = _cognitive_stack()
    else:
        ir = catalog = proposal_parser = oracle = scheduler = None
    observability_ir = ir or compile_ruleset(_ruleset_root(), "civ2civ3")
    combat_ruleset_digest = (
        structural_hash(
            observability_ir.to_dict())
        if combat_operations_enabled
        else None)
    events_path = manifest["events_path"]
    if not os.path.isabs(events_path):
        events_path = os.path.join(run_dir, events_path)
    writer = EventWriter(
        events_path, manifest["game_id"], durable=True, sync_mode="turn")
    domain_observability = DomainObservabilityEmitter(
        writer, observability_ir)
    root = writer.emit("run_started", 0, {
        "condition_id": manifest["condition_id"],
        "manifest_identity": manifest["manifest_identity"]})
    parent, _ = emit_runtime_activation(
        writer,
        0,
        root["event_id"],
        pf_runtime,
        manifest["condition_id"],
        manifest["track"],
    )
    parent = _emit_belief_configuration(writer, parent, manifest)
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
        "sciencebox": 100,
        "foodbox": manifest["impact_policy"].get("foodbox_percent", 100),
        "techlevel": 50, "map_size": "tiny",
        # Founder + mobile diplomat + stationary defender: the defender gives
        # fog-of-war calibration a repeatable visible opponent unit while the
        # diplomat drives the real scouting path.
        "startunits": "csd", "startcity": True,
        "startpos": "all", "dispersion": 0, "fogofwar": False,
        # Preserve spaceship construction/arrival dynamics while preventing
        # optional victory conditions from truncating a fixed-horizon cohort.
        # Conquest remains a genuine absorbing terminal state.
        "victories": "SPACERACE", "endspaceship": False,
        "max_turns": manifest.get("engine_max_turns", manifest["turn_limit"]),
        "ai_skill_level": manifest["opponent"].get("difficulty", "experimental"),
    }
    config.update(
        manifest.get(
            "release_game_config",
            {}))
    store = SnapshotStore()
    belief_store = (BeliefStore(manifest["beliefs"])
                    if context.capabilities["uncertain_beliefs"] else None)
    inference = (UncertainInference(ir, belief_store)
                 if context.capabilities["uncertain_beliefs"] else None)
    execution_monitor = (PlanMonitor()
                         if context.capabilities["scheduler"] else None)
    pressure_state_identity = structural_hash([
        manifest["manifest_identity"], manifest["attempt_id"],
        manifest["ruleset"], manifest["impact_policy"],
        "pf-impact-conductance/1.0",
    ])
    impact_planner = (GroundedImpactPlanner(
        manifest["impact_policy"], ruleset_ir=ir,
        pressure_state_path=os.path.join(
            run_dir, "pressure-conductance.json"),
        pressure_state_identity=pressure_state_identity)
        if context.capabilities["scheduler"] else None)
    control_event_emitter = ControlEventEmitter()
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
    # A belief atom can be revised after many independent unit sightings.  The
    # post-game calibration population is one terminal prediction per atom,
    # not one copy of every intermediate revision.  Keeping the latest value
    # also prevents a large late-game army from creating an unbounded terminal
    # telemetry burst.
    predictions = {}
    monitor_belief = None
    seen = set()
    blocked_moves = set()
    prior_scout = None
    action_count = attempted_count = rejected = zombie_blocked = 0
    decision_stats = {
        "impact_actions": 0, "meaningful_actions": 0,
        "production_changes": 0, "founder_production_changes": 0,
        "production_repurpose_changes": 0,
        "production_preexpansion_growth_changes": 0,
        "production_preexpansion_founder_changes": 0,
        "production_military_score_changes": 0,
        "settlement_attempts": 0, "settlement_completions": 0,
        "tactical_actions": 0,
        "effect_observed": 0, "no_effect": 0, "safe_model_fallbacks": 0,
        "model_selection_calls": 0, "model_selection_calls_avoided": 0,
        "failover_attempts": 0, "failover_recoveries": 0,
        "effect_confirmation_timeouts": 0,
        "effect_confirmation_deferred": 0,
        "effect_confirmation_recovered": 0,
        "effect_confirmation_expired": 0,
        "stale_terminal_followups_blocked": 0,
        "operation_authority_opportunities": 0,
        "operation_authority_actions": 0,
        "operation_authority_winner_changes": 0,
    }
    pending_impact_outcomes = DeferredImpactOutcomeLedger()
    action_type_counts = {}
    impact_turns = set()
    capability_pruned_worker_moves = set()
    nonprogress_moves = set()
    unreachable_founder_moves = set()
    founder_cycle_moves = set()
    founder_attrition_moves = set()

    def observe_impact_snapshot(current):
        if impact_planner is None:
            return
        impact_planner.observe(current)
        pruning = impact_planner.pruning_move_keys(current)
        capability_pruned_worker_moves.update(
            pruning["capability_pruned_worker_moves"])
        nonprogress_moves.update(pruning["nonprogress_moves"])
        unreachable_founder_moves.update(
            pruning["unreachable_founder_moves"])
        founder_cycle_moves.update(pruning["founder_cycle_moves"])
        founder_attrition_moves.update(pruning["founder_attrition_moves"])

    replan_latencies = []
    model_latencies = []
    full_loop_latencies = []
    turn_cognitive_latencies = []
    cognitive_diagnostics = {}
    turn_action_phase_latencies = []
    impact_planning_latency_ms = 0.0
    impact_planning_calls = 0
    impact_planning_diagnostics = {}
    impact_decision_event_latency_ms = 0.0
    impact_execution_latency_ms = 0.0
    impact_execution_calls = 0
    impact_execution_diagnostics = {}
    impact_preconfirmation_latency_ms = 0.0
    impact_confirmation_nonstate_latency_ms = 0.0
    impact_postconfirmation_latency_ms = 0.0
    impact_postconfirmation_effect_latency_ms = 0.0
    impact_postconfirmation_budget_latency_ms = 0.0
    impact_postconfirmation_resolution_latency_ms = 0.0
    impact_postconfirmation_reconcile_latency_ms = 0.0
    impact_resolution_diagnostics = {}
    impact_learning_diagnostics = {}
    action_refresh_observer_latency_ms = 0.0
    action_refresh_event_latency_ms = 0.0
    turn_end_submit_latencies = []
    turn_boundary_latencies = []
    turn_checkpoint_sync_latencies = []
    transition_state_diagnostics = {}
    action_state_diagnostics = {}
    effect_confirmation_latencies = []
    production_projection_etas = []
    production_projection_values = []
    production_projection_unit_completions = []
    production_projection_unit_score_progress = []
    production_projection_guaranteed_unit_score = []
    production_batch_incremental_unit_completions = []
    production_batch_guaranteed_unit_score = []
    production_projection_costs = []
    production_projection_shields = []
    production_projection_pop_costs = []
    production_projection_ruleset_sources = []
    production_projection_population_etas = []
    production_projection_settlement_etas = []
    production_projection_settlement_runways = []
    production_projection_route_etas = []
    production_projection_route_eta_sources = []
    production_projection_growth_ruleset_sources = []
    production_founder_deficits = []
    production_repurpose_avoided_population = []
    production_repurpose_discarded_shields = []
    production_repurpose_target_completions = []
    production_preexpansion_settlement_etas = []
    production_preexpansion_settlement_runways = []
    corrections = 0
    final_global = None
    observer_global_state_queries = 0
    # Engine-live runs the proxy on the same host. The proxy's level-9
    # per-message deflate costs more CPU/scheduling than loopback bytes save;
    # remote harnesses can explicitly restore compression.
    async with websockets.connect(
            ws_url, open_timeout=30, max_size=None, ping_interval=None,
            compression=_websocket_compression()) as ws:
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
            require_own_units=True, stable_samples=5,
            include_movement_routes=movement_routes_enabled,
            include_combat_probabilities=(
                combat_probabilities_enabled))
        store.replace(snapshot)
        state_event = writer.emit("state_snapshot", snapshot.turn, snapshot.event_payload(),
                                  caused_by=[parent])
        domain_observability.emit_snapshot(
            snapshot, state_event["event_id"], raw=raw)
        parent = state_event["event_id"]
        if combat_operations_enabled:
            combat_events = (
                control_event_emitter
                .emit_combat_operation_shadow(
                    writer,
                    snapshot,
                    combat_ruleset_digest,
                    caused_by=(parent,),
                    action_budget=(
                        combat_operation_action_budget)))
            if combat_events:
                parent = combat_events[
                    -1]["event_id"]
        global_state = await _global_state(
            ws, player_id=player_id, minimum_turn=snapshot.turn)
        observer_global_state_queries += 1
        opponent_rows = sorted(
            (row for row in global_state["players"].values()
             if row.get("id") != player_id and row.get("score", -1) >= 0),
            key=lambda row: (row.get("id", 2147483647), row.get("name", "")))
        opponent = opponent_rows[0] if opponent_rows else {"id": 1, "name": "builtin-ai"}
        observe_impact_snapshot(snapshot)
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
                if category == "production_repurpose":
                    decision_stats["production_repurpose_changes"] += 1
                if category == "production_preexpansion_growth":
                    decision_stats["production_preexpansion_growth_changes"] += 1
                if category == "production_preexpansion_founder":
                    decision_stats["production_preexpansion_founder_changes"] += 1
                if category == "production_military_score":
                    decision_stats["production_military_score_changes"] += 1
            if action_type == "unit_build_city":
                decision_stats["settlement_attempts"] += 1
            if category in ("tactical_attack", "tactical_move"):
                decision_stats["tactical_actions"] += 1

        def record_impact_resolution(candidate, before, after, effect_observed,
                                     deferred=False, feedback_id=None):
            """Commit one candidate-specific authoritative outcome exactly once."""
            nonlocal parent
            learning_started = time.perf_counter()
            conductance_update = impact_planner.record_outcome(
                candidate, before, effect_observed, after_snapshot=after,
                feedback_id=feedback_id,
                diagnostics=impact_learning_diagnostics)
            if (impact_planner.last_control_outcome_record
                    is not None
                    and impact_planner
                    .last_control_outcome_query is not None
                    and impact_planner
                    .last_control_outcome_decision is not None):
                outcome_event = (
                    control_event_emitter.emit_outcome(
                        writer, int(after.turn),
                        impact_planner
                        .last_control_outcome_query,
                        impact_planner
                        .last_control_outcome_decision,
                        impact_planner
                        .last_control_outcome_record,
                        caused_by=(parent,)))
                parent = outcome_event["event_id"]
                if (impact_planner
                        .last_transition_value_update
                        is not None):
                    transition_event = (
                        control_event_emitter
                        .emit_transition_value_update(
                            writer, int(after.turn),
                            impact_planner
                            .last_control_outcome_query,
                            impact_planner
                            .last_control_outcome_decision,
                            impact_planner
                            .last_transition_value_update,
                            caused_by=(parent,)))
                    parent = transition_event[
                        "event_id"]
            conductance_updates = (
                (() if conductance_update is None else (conductance_update,))
                + impact_planner.drain_conductance_updates())
            impact_resolution_diagnostics["learning_latency_ms"] = (
                impact_resolution_diagnostics.get(
                    "learning_latency_ms", 0.0)
                + (time.perf_counter() - learning_started) * 1000.0)
            event_started = time.perf_counter()
            for conductance_update in conductance_updates:
                event = writer.emit(
                    "conductance_updated", int(after.turn),
                    conductance_update.to_dict(), caused_by=[parent])
                parent = event["event_id"]
            impact_resolution_diagnostics["event_latency_ms"] = (
                impact_resolution_diagnostics.get("event_latency_ms", 0.0)
                + (time.perf_counter() - event_started) * 1000.0)
            stats_started = time.perf_counter()
            if effect_observed:
                decision_stats["effect_observed"] += 1
                if candidate.action.get("action_type") == "unit_build_city":
                    decision_stats["settlement_completions"] += 1
                if deferred:
                    decision_stats["effect_confirmation_recovered"] += 1
            else:
                decision_stats["no_effect"] += 1
                if deferred:
                    decision_stats["effect_confirmation_expired"] += 1
            impact_resolution_diagnostics["stats_latency_ms"] = (
                impact_resolution_diagnostics.get("stats_latency_ms", 0.0)
                + (time.perf_counter() - stats_started) * 1000.0)
            impact_resolution_diagnostics["calls"] = (
                impact_resolution_diagnostics.get("calls", 0) + 1)

        def reconcile_deferred_impact_outcomes(current):
            if impact_planner is None:
                return
            for resolution in pending_impact_outcomes.resolve(
                    impact_planner, current):
                record_impact_resolution(
                    resolution.candidate, resolution.before_snapshot,
                    resolution.after_snapshot, resolution.effect_observed,
                    deferred=True, feedback_id=resolution.feedback_id)

        distance = _enemy_distance(
            raw, global_state, player_id, snapshot.map_width, snapshot.map_height)
        if distance is not None:
            parent = _metric(
                writer, snapshot.turn, parent, "initial_enemy_distance", distance, manifest)

        if context.capabilities["uncertain_beliefs"]:
            monitor_belief, parent = _emit_opponent_presence(
                raw, snapshot, manifest, belief_store, writer, parent, player_id)

        async def refresh_after_action(current, cause, predicate=None, timeout=15.0):
            nonlocal action_refresh_event_latency_ms
            nonlocal action_refresh_observer_latency_ms
            minimum_seq = current.identity.source_seq + 1
            deadline = time.monotonic() + float(timeout)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("accepted action produced no authoritative state update")
                next_raw, next_snapshot = await _state(
                    ws, manifest["game_id"], minimum_turn=current.turn,
                    minimum_source_seq=minimum_seq, timeout=remaining,
                    stable_samples=2,
                    settle_first_projection=True,
                    poll_interval=(
                        impact_planner.refresh_stability_interval_seconds
                        if impact_planner is not None else 0.2),
                    diagnostics=action_state_diagnostics,
                    include_movement_routes=movement_routes_enabled,
                    include_combat_probabilities=(
                        combat_probabilities_enabled))
                if predicate is not None and not predicate(next_snapshot):
                    minimum_seq = next_snapshot.identity.source_seq + 1
                    await asyncio.sleep(0.05)
                    continue
                store.replace(next_snapshot)
                observer_started = time.perf_counter()
                observe_impact_snapshot(next_snapshot)
                action_refresh_observer_latency_ms += (
                    time.perf_counter() - observer_started) * 1000.0
                event_started = time.perf_counter()
                event = writer.emit(
                    "state_snapshot", next_snapshot.turn, next_snapshot.event_payload(),
                    caused_by=[cause])
                domain_observability.emit_snapshot(
                    next_snapshot, event["event_id"], raw=next_raw)
                operation_events = (
                    control_event_emitter
                    .resolve_city_defense_operations(
                        writer,
                        next_snapshot,
                        caused_by=(
                            event[
                                "event_id"],)))
                combat_parent = (
                    operation_events[
                        -1]["event_id"]
                    if operation_events
                    else event["event_id"])
                combat_lifecycle_events = (
                    control_event_emitter
                    .resolve_combat_operations(
                        writer,
                        next_snapshot,
                        caused_by=(
                            combat_parent,))
                    if combat_operations_enabled
                    else ())
                combat_parent = (
                    combat_lifecycle_events[
                        -1]["event_id"]
                    if combat_lifecycle_events
                    else combat_parent)
                combat_events = (
                    control_event_emitter
                    .emit_combat_operation_shadow(
                        writer,
                        next_snapshot,
                        combat_ruleset_digest,
                        caused_by=(
                            combat_parent,),
                        action_budget=(
                            combat_operation_action_budget))
                    if combat_operations_enabled
                    else ())
                action_refresh_event_latency_ms += (
                    time.perf_counter() - event_started) * 1000.0
                return (
                    next_raw,
                    next_snapshot,
                    (
                        combat_events[
                            -1]["event_id"]
                        if combat_events
                        else combat_parent))

        turn_started = time.perf_counter()
        final_turn = snapshot.turn
        turns_executed = 0
        planned_actions = 0
        terminal_player_elimination = False
        terminal_game_over = False
        turn_boundary_started = None
        for turn_index in range(1, manifest["turn_limit"] + 1):
            if turn_index > 1:
                raw, snapshot = await _next_turn_state(
                    ws, manifest["game_id"], api_token, agent_id,
                    minimum_turn=snapshot.turn + 1,
                    minimum_source_seq=snapshot.identity.source_seq + 1,
                    diagnostics=transition_state_diagnostics,
                    include_movement_routes=movement_routes_enabled,
                    include_combat_probabilities=(
                        combat_probabilities_enabled))
                store.replace(snapshot)
                state_event = writer.emit(
                    "state_snapshot", snapshot.turn, snapshot.event_payload(),
                    caused_by=[parent])
                domain_observability.emit_snapshot(
                    snapshot, state_event["event_id"], raw=raw)
                operation_events = (
                    control_event_emitter
                    .resolve_city_defense_operations(
                        writer, snapshot,
                        caused_by=(
                            state_event[
                                "event_id"],)))
                operation_parent = (
                    operation_events[
                        -1]["event_id"]
                    if operation_events
                    else state_event[
                        "event_id"])
                combat_lifecycle_events = (
                    control_event_emitter
                    .resolve_combat_operations(
                        writer, snapshot,
                        caused_by=(
                            operation_parent,))
                    if combat_operations_enabled
                    else ())
                operation_parent = (
                    combat_lifecycle_events[
                        -1]["event_id"]
                    if combat_lifecycle_events
                    else operation_parent)
                combat_events = (
                    control_event_emitter
                    .emit_combat_operation_shadow(
                        writer,
                        snapshot,
                        combat_ruleset_digest,
                        caused_by=(
                            operation_parent,),
                        action_budget=(
                            combat_operation_action_budget))
                    if combat_operations_enabled
                    else ())
                parent = (
                    combat_events[
                        -1]["event_id"]
                    if combat_events
                    else operation_parent)
                if _needs_turn_global_state(impact_planner):
                    global_state = await _global_state(
                        ws, player_id=player_id, minimum_turn=snapshot.turn)
                    observer_global_state_queries += 1
                observe_impact_snapshot(snapshot)
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
            reconcile_deferred_impact_outcomes(snapshot)
            if context.capabilities["uncertain_beliefs"]:
                context.use("uncertain_beliefs")
                rows, parent = _emit_observations(
                    snapshot, manifest, belief_store, inference, writer, parent, seen)
                _retain_terminal_predictions(predictions, rows)
            if _game_terminal(snapshot):
                terminal_game_over = snapshot.game_over
                terminal_player_elimination = _player_eliminated(snapshot)
                break

            if turn_boundary_started is not None:
                turn_boundary_latencies.append(
                    (time.perf_counter() - turn_boundary_started) * 1000.0)
            full_turn_started = time.perf_counter()
            cognitive_started = time.perf_counter()
            (active_plan, plain_selection, parent, turn_model_latency,
             turn_corrections, safe_model_fallback, model_called,
             model_call_avoided) = _cognitive_turn(
                manifest, context, store, player_id, raw, snapshot,
                ir, catalog, proposal_parser, oracle, scheduler, writer, parent,
                diagnostics=cognitive_diagnostics)
            turn_cognitive_latencies.append(
                (time.perf_counter() - cognitive_started) * 1000.0)
            action_phase_started = time.perf_counter()
            model_latencies.append(turn_model_latency)
            corrections += turn_corrections
            decision_stats["safe_model_fallbacks"] += int(safe_model_fallback)
            decision_stats["model_selection_calls"] += int(model_called)
            decision_stats["model_selection_calls_avoided"] += int(
                model_call_avoided)
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
                    impact_planning_started = time.perf_counter()
                    operation_authority = (
                        control_event_emitter
                        .operation_authority_readout(
                            writer,
                            snapshot,
                            city_defense_enabled=(
                                city_defense_operation_authority_enabled),
                            combat_enabled=(
                                combat_operation_authority_enabled))
                        if (
                            city_defense_operation_authority_enabled
                            or combat_operation_authority_enabled)
                        else None)
                    decision_stats[
                        "operation_authority_opportunities"
                    ] += int(
                        operation_authority
                        is not None)
                    decision = impact_planner.plan(
                        snapshot, excluded=excluded_impact_actions,
                        excluded_scopes=impact_budget.excluded_scopes,
                        diagnostics=impact_planning_diagnostics,
                        operation_authority=(
                            operation_authority))
                    impact_planning_latency_ms += (
                        time.perf_counter() - impact_planning_started) * 1000.0
                    impact_planning_calls += 1
                    # Identity-resource scheduling is observational in GDO-3.
                    # Dispatch it only after the complete live planning
                    # boundary has stopped its latency clock.
                    impact_planner.dispatch_resource_schedules()
                    if decision is None:
                        stranded = (
                            impact_planner.last_stranded_pressure_artifact)
                        if stranded is not None:
                            pressure_value = stranded["pressure"]
                            schedule_value = stranded["schedule"]
                            pressure_hash = schedule_value["pressure_hash"]
                            pressure_id = (
                                "pressure-" + pressure_hash[:20])
                            pressure_event = writer.emit(
                                "pressure_propagated", snapshot.turn, {
                                    "conductance_state": stranded[
                                        "conductance_state"],
                                    "config": pressure_value["config"],
                                    "dependency":
                                        pressure_dependency_view(
                                            pressure_value),
                                    "goals": pressure_value["goals"],
                                    "graph_hash": pressure_value[
                                        "graph_hash"],
                                    "operational_pressure": pressure_value[
                                        "pressure"],
                                    "pressure_id": pressure_id,
                                    "result_hash": pressure_hash,
                                    "traces": pressure_value["traces"],
                                }, caused_by=[parent])
                            parent = pressure_event["event_id"]
                            impact_planning_diagnostics[
                                "stranded_pressure_events"] = (
                                    impact_planning_diagnostics.get(
                                        "stranded_pressure_events", 0) + 1)
                        break
                    impact_action = decision.candidate.action
                    action_snapshot = snapshot
                    decision_event_started = time.perf_counter()
                    if decision.pressure_artifact is not None:
                        pressure_value = decision.pressure_artifact["pressure"]
                        schedule_value = decision.pressure_artifact["schedule"]
                        # Scheduling already binds the exact materialized
                        # pressure artifact to this decision. Reuse that
                        # identity instead of serializing and hashing the
                        # artifact a second time during event emission.
                        pressure_hash = schedule_value["pressure_hash"]
                        pressure_id = "pressure-" + pressure_hash[:20]
                        pressure_event = writer.emit(
                            "pressure_propagated", snapshot.turn, {
                                "conductance_state": decision.pressure_artifact[
                                    "conductance_state"],
                                "config": pressure_value["config"],
                                "dependency":
                                    pressure_dependency_view(
                                        pressure_value),
                                "goals": pressure_value["goals"],
                                "graph_hash": pressure_value["graph_hash"],
                                "operational_pressure": pressure_value["pressure"],
                                "pressure_id": pressure_id,
                                "result_hash": pressure_hash,
                                "traces": pressure_value["traces"],
                            }, caused_by=[parent])
                        decision_id = "pressure-decision-" + schedule_value[
                            "structural_hash"][:20]
                        scored_event = writer.emit(
                            "operation_scored", snapshot.turn, {
                                "allocations": schedule_value["allocations"],
                                "decision_id": decision_id,
                                "pressure_id": pressure_id,
                                "scores": schedule_value["scores"],
                                "selected_operation_id": schedule_value[
                                    "selected_operation_id"],
                                "solver_identity": schedule_value[
                                    "solver_identity"],
                                "structural_hash": schedule_value[
                                    "structural_hash"],
                            }, caused_by=[pressure_event["event_id"]])
                        parent = scored_event["event_id"]
                    if (impact_planner.last_control_query
                            is not None
                            and impact_planner
                            .last_control_decision is not None):
                        control_events = (
                            control_event_emitter
                            .emit_decision(
                                writer, snapshot.turn,
                                impact_planner
                                .last_control_query,
                                impact_planner
                                .last_control_decision,
                                caused_by=(parent,)))
                        if control_events:
                            parent = control_events[
                                -1]["event_id"]
                    if (
                            isinstance(
                                decision
                                .operation_authority,
                                dict)
                            and decision
                            .operation_authority
                            .get("applied")
                    ):
                        authority_events = (
                            control_event_emitter
                            .emit_operation_authority_selection(
                                writer,
                                snapshot.turn,
                                decision
                                .operation_authority[
                                    "readout"],
                                decision
                                .operation_authority
                                .get(
                                    "baseline_candidate_key"),
                                caused_by=(
                                    parent,)))
                        parent = (
                            authority_events[
                                -1]["event_id"])
                        decision_stats[
                            "operation_authority_actions"
                        ] += 1
                        decision_stats[
                            "operation_authority_winner_changes"
                        ] += int(
                            decision
                            .operation_authority
                            .get(
                                "changed_winner",
                                False))
                    plan_event = writer.emit(
                        "plan_created", snapshot.turn,
                        {"plan": decision.plan.to_dict()}, caused_by=[parent])
                    parent = plan_event["event_id"]
                    execution_monitor.register(decision.plan)
                    impact_decision_event_latency_ms += (
                        time.perf_counter() - decision_event_started) * 1000.0
                    execution_started = time.perf_counter()
                    outcome, parent = await _execute_action(
                        gate, manifest["game_id"], player_id, snapshot,
                        impact_action, parent, attempted_count, decision.plan,
                        diagnostics=impact_execution_diagnostics)
                    impact_execution_latency_ms += (
                        time.perf_counter() - execution_started) * 1000.0
                    impact_execution_calls += 1
                    preconfirmation_started = time.perf_counter()
                    impact_feedback_id = outcome.result_event_id or parent
                    attempted_count += 1
                    action_count += int(outcome.submitted)
                    rejected += int(outcome.submitted and outcome.status != "accepted")
                    operation_events = (
                        control_event_emitter
                        .emit_city_defense_action_outcome(
                            writer,
                            action_snapshot.turn,
                            action_snapshot,
                            impact_action,
                            outcome,
                            caused_by=(
                                parent,)))
                    if operation_events:
                        parent = (
                            operation_events[
                                -1][
                                    "event_id"])
                    combat_operation_events = (
                        control_event_emitter
                        .emit_combat_action_outcome(
                            writer,
                            action_snapshot,
                            impact_action,
                            outcome,
                            caused_by=(
                                parent,))
                        if combat_operations_enabled
                        else ())
                    if combat_operation_events:
                        parent = (
                            combat_operation_events[
                                -1][
                                    "event_id"])
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
                        if projection.get("projected_unit_completions") is not None:
                            production_projection_unit_completions.append(float(
                                projection["projected_unit_completions"]))
                        if projection.get("projected_unit_score_progress") is not None:
                            production_projection_unit_score_progress.append(float(
                                projection["projected_unit_score_progress"]))
                        if projection.get("guaranteed_unit_score_points") is not None:
                            production_projection_guaranteed_unit_score.append(float(
                                projection["guaranteed_unit_score_points"]))
                        if projection.get("batch_incremental_unit_completions") is not None:
                            production_batch_incremental_unit_completions.append(float(
                                projection["batch_incremental_unit_completions"]))
                        if projection.get("batch_guaranteed_unit_score_points") is not None:
                            production_batch_guaranteed_unit_score.append(float(
                                projection["batch_guaranteed_unit_score_points"]))
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
                        if projection.get("population_ready_eta_turns") is not None:
                            production_projection_population_etas.append(float(
                                projection["population_ready_eta_turns"]))
                        if projection.get("settlement_eta_turns") is not None:
                            production_projection_settlement_etas.append(float(
                                projection["settlement_eta_turns"]))
                        if projection.get("settlement_runway_turns") is not None:
                            production_projection_settlement_runways.append(float(
                                projection["settlement_runway_turns"]))
                        if projection.get("founder_route_eta_turns") is not None:
                            production_projection_route_etas.append(float(
                                projection["founder_route_eta_turns"]))
                        if projection.get("founder_route_eta_source") is not None:
                            production_projection_route_eta_sources.append(int(
                                projection["founder_route_eta_source"]
                                == "observed_route_effects"))
                        if projection.get("growth_cost_source") is not None:
                            production_projection_growth_ruleset_sources.append(int(
                                projection["growth_cost_source"] == "ruleset_ir"))
                        if projection.get("founder_deficit_before") is not None:
                            production_founder_deficits.append(float(
                                projection["founder_deficit_before"]))
                        if projection.get("avoided_population_cost") is not None:
                            production_repurpose_avoided_population.append(float(
                                projection["avoided_population_cost"]))
                        if projection.get("repurpose_discarded_shield_stock") is not None:
                            production_repurpose_discarded_shields.append(float(
                                projection["repurpose_discarded_shield_stock"]))
                        if projection.get(
                                "repurpose_target_completes_by_horizon") is not None:
                            production_repurpose_target_completions.append(int(
                                projection["repurpose_target_completes_by_horizon"]))
                        if projection.get(
                                "preexpansion_sequence_settlement_eta_turns") is not None:
                            production_preexpansion_settlement_etas.append(float(
                                projection[
                                    "preexpansion_sequence_settlement_eta_turns"]))
                        if projection.get(
                                "preexpansion_sequence_settlement_runway_turns") is not None:
                            production_preexpansion_settlement_runways.append(float(
                                projection[
                                    "preexpansion_sequence_settlement_runway_turns"]))
                    excluded_impact_actions.add(decision.candidate.action_key)
                    impact_preconfirmation_latency_ms += (
                        time.perf_counter() - preconfirmation_started) * 1000.0
                    confirmation_started = time.perf_counter()
                    confirmation_state_before = action_state_diagnostics.get(
                        "latency_ms", 0.0)
                    raw, snapshot, parent, authoritative_refresh = (
                        await _refresh_accepted_impact_action(
                            refresh_after_action, raw, snapshot, parent,
                            decision.candidate,
                            refresh_timeout=_impact_refresh_timeout(
                                impact_planner, decision.candidate),
                            effect_predicate=(
                                (lambda value: impact_planner.candidate_effect_observed(
                                    decision.candidate, action_snapshot, value))
                                if impact_action.get("action_type") in (
                                    "city_production", "unit_build_city",
                                    "unit_join_city")
                                else None)))
                    confirmation_latency_ms = (
                        time.perf_counter() - confirmation_started) * 1000.0
                    effect_confirmation_latencies.append(confirmation_latency_ms)
                    impact_confirmation_nonstate_latency_ms += max(
                        0.0,
                        confirmation_latency_ms
                        - (action_state_diagnostics.get("latency_ms", 0.0)
                           - confirmation_state_before))
                    postconfirmation_started = time.perf_counter()
                    effect_started = time.perf_counter()
                    decision_stats["effect_confirmation_timeouts"] += int(
                        not authoritative_refresh)
                    effect_observed = (authoritative_refresh
                                       and impact_planner.candidate_effect_observed(
                                           decision.candidate, action_snapshot, snapshot))
                    impact_postconfirmation_effect_latency_ms += (
                        time.perf_counter() - effect_started) * 1000.0
                    budget_started = time.perf_counter()
                    impact_budget.record(
                        decision.candidate, effect_observed,
                        authoritative_refresh=authoritative_refresh)
                    impact_postconfirmation_budget_latency_ms += (
                        time.perf_counter() - budget_started) * 1000.0
                    resolution_started = time.perf_counter()
                    if effect_observed:
                        record_impact_resolution(
                            decision.candidate, action_snapshot, snapshot, True,
                            feedback_id=impact_feedback_id)
                    elif (authoritative_refresh
                          and snapshot.turn > action_snapshot.turn):
                        record_impact_resolution(
                            decision.candidate, action_snapshot, snapshot, False,
                            feedback_id=impact_feedback_id)
                    else:
                        pending_impact_outcomes.defer(
                            decision.candidate, action_snapshot,
                            feedback_id=impact_feedback_id)
                        decision_stats["effect_confirmation_deferred"] += 1
                    impact_postconfirmation_resolution_latency_ms += (
                        time.perf_counter() - resolution_started) * 1000.0
                    reconcile_started = time.perf_counter()
                    if authoritative_refresh:
                        # A fresh packet may also reveal effects from older
                        # accepted actions that exceeded their bounded wait.
                        reconcile_deferred_impact_outcomes(snapshot)
                    impact_postconfirmation_reconcile_latency_ms += (
                        time.perf_counter() - reconcile_started) * 1000.0
                    impact_postconfirmation_latency_ms += (
                        time.perf_counter() - postconfirmation_started) * 1000.0
                    if (not authoritative_refresh
                            and decision.candidate.terminal_on_accept):
                        # The actor may already be gone even though the proxy
                        # has not projected the effect. Never plan a follow-up
                        # from the unchanged pre-action snapshot.
                        decision_stats[
                            "stale_terminal_followups_blocked"] += 1
                        break
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
            turn_action_phase_latencies.append(
                (time.perf_counter() - action_phase_started) * 1000.0)
            end_turn = _first_legal_action(snapshot, "end_turn")
            if end_turn is None:
                raise RuntimeError("server did not advertise end_turn")
            end_submit_started = time.perf_counter()
            outcome, parent = await _execute_action(
                gate, manifest["game_id"], player_id, snapshot, end_turn,
                parent, attempted_count, control_plan)
            turn_end_submit_latencies.append(
                (time.perf_counter() - end_submit_started) * 1000.0)
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
            checkpoint_started = time.perf_counter()
            writer.sync()
            turn_checkpoint_sync_latencies.append(
                (time.perf_counter() - checkpoint_started) * 1000.0)
            turn_boundary_started = time.perf_counter()

        # Bind final scoring to the post-horizon observer revision rather than
        # assuming a fixed sleep is long enough for endgame packets to settle.
        final_global_started = time.perf_counter()
        observer_global_state_queries += 1
        final_global = await _global_state(
            ws, timeout=5, player_id=player_id,
            minimum_turn=(
                final_turn
                if terminal_game_over or terminal_player_elimination
                else final_turn + 1))
        final_global_settle_latency = (
            time.perf_counter() - final_global_started) * 1000.0

    loop_latency = (time.perf_counter() - turn_started) * 1000.0 / max(1, turns_executed)
    model_latency = (sum(model_latencies) / len(model_latencies)
                     if model_latencies else 0.0)
    full_loop_under_30 = (sum(value <= 30000 for value in full_loop_latencies)
                          / max(1, len(full_loop_latencies)))
    transition_calls = max(1.0, transition_state_diagnostics.get("calls", 0.0))
    action_state_calls = max(
        1.0, action_state_diagnostics.get("calls", 0.0))
    mean_boundary_latency = (
        sum(turn_boundary_latencies) / max(1, len(turn_boundary_latencies)))
    mean_transition_state_latency = (
        transition_state_diagnostics.get("latency_ms", 0.0) / transition_calls)

    def mean_state_diagnostic(diagnostics, name, calls):
        return diagnostics.get(name, 0.0) / calls

    def mean_state_delivery_latency(diagnostics, calls):
        return max(
            0.0,
            mean_state_diagnostic(diagnostics, "query_latency_ms", calls)
            - mean_state_diagnostic(
                diagnostics, "server_elapsed_before_serialize_ms", calls))

    def mean_state_delivery_excluding_decode(diagnostics, calls):
        return max(
            0.0,
            mean_state_delivery_latency(diagnostics, calls)
            - mean_state_diagnostic(
                diagnostics, "client_json_decode_ms", calls))

    truth_techs = set((final_global or {}).get("techs", {}).get(
        "player{}".format(opponent.get("id", 1)), []))
    correct = []
    for belief in predictions.values():
        tech = str(belief.key.arguments[-1])
        is_true = tech in truth_techs
        correct.append(is_true)
        parent = _metric(
            writer, final_turn, parent, "belief_calibration_sample",
            belief.strength, manifest, truth=int(is_true),
            opponent=manifest["opponent"].get("id", "builtin-ai-experimental"),
            atom_id=belief.atom_id)
    calibration_error = (sum(abs(belief.strength - int(value))
                             for belief, value in zip(
                                 predictions.values(), correct)) / len(correct)
                         if correct else 0.0)
    player_row = _player_row(final_global or {}, player_id)
    opponent_row = _player_row(final_global or {}, opponent.get("id", 1))
    if "score" not in player_row or "score" not in opponent_row:
        raise RuntimeError("final paired scores were not authoritative")
    player_score = float(player_row["score"])
    opponent_score = float(opponent_row["score"])
    score_margin = player_score - opponent_score
    score_lead = player_score > opponent_score
    horizon_reached = final_turn >= manifest["turn_limit"]
    score_observation_semantics = (
        "terminal_absorbing_score_carried_to_horizon"
        if terminal_game_over or terminal_player_elimination
        else "observed_at_fixed_horizon")
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
        ("turn_cognitive_latency_ms",
         sum(turn_cognitive_latencies) / max(1, len(turn_cognitive_latencies))),
        ("turn_cognitive_summary_latency_ms",
         cognitive_diagnostics.get("summary_ms", 0.0)
         / max(1, len(turn_cognitive_latencies))),
        ("turn_cognitive_setup_latency_ms",
         cognitive_diagnostics.get("setup_ms", 0.0)
         / max(1, len(turn_cognitive_latencies))),
        ("turn_cognitive_proposal_latency_ms",
         cognitive_diagnostics.get("proposal_ms", 0.0)
         / max(1, len(turn_cognitive_latencies))),
        ("turn_cognitive_finalization_latency_ms",
         cognitive_diagnostics.get("finalization_ms", 0.0)
         / max(1, len(turn_cognitive_latencies))),
        ("turn_action_phase_latency_ms",
         sum(turn_action_phase_latencies)
         / max(1, len(turn_action_phase_latencies))),
        ("turn_action_refresh_state_latency_ms",
         action_state_diagnostics.get("latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_action_nonrefresh_latency_ms", max(
            0.0,
            sum(turn_action_phase_latencies)
            / max(1, len(turn_action_phase_latencies))
            - action_state_diagnostics.get("latency_ms", 0.0)
            / max(1, turns_executed))),
        ("action_refresh_state_calls_per_turn",
         action_state_diagnostics.get("calls", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_planning_latency_ms",
         impact_planning_latency_ms / max(1, turns_executed)),
        ("impact_planning_decision_latency_ms",
         impact_planning_latency_ms / max(1, impact_planning_calls)),
        ("impact_planning_decision_calls_per_turn",
         float(impact_planning_calls) / max(1, turns_executed)),
        ("impact_planning_candidate_latency_ms",
         impact_planning_diagnostics.get("candidate_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_pressure_latency_ms",
         impact_planning_diagnostics.get("pressure_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_materialization_latency_ms",
         impact_planning_diagnostics.get("materialization_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_candidate_count",
         float(impact_planning_diagnostics.get("candidate_count", 0))
         / max(1, impact_planning_calls)),
        ("impact_planning_stranded_pressure_events_per_turn",
         float(impact_planning_diagnostics.get(
             "stranded_pressure_events", 0))
         / max(1, turns_executed)),
        ("impact_planning_stranded_goals_per_decision",
         float(impact_planning_diagnostics.get(
             "stranded_goal_count", 0))
         / max(1, impact_planning_calls)),
        ("impact_planning_legal_action_count",
         float(impact_planning_diagnostics.get("legal_action_count", 0))
         / max(1, impact_planning_calls)),
        ("impact_planning_catalog_latency_ms",
         impact_planning_diagnostics.get("catalog_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_candidate_setup_latency_ms",
         impact_planning_diagnostics.get(
             "candidate_setup_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_candidate_production_latency_ms",
         impact_planning_diagnostics.get(
             "candidate_production_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_candidate_movement_latency_ms",
         impact_planning_diagnostics.get(
             "candidate_movement_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_candidate_other_latency_ms",
         impact_planning_diagnostics.get(
             "candidate_other_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_candidate_finalize_latency_ms",
         impact_planning_diagnostics.get(
             "candidate_finalize_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_pressure_graph_latency_ms",
         impact_planning_diagnostics.get(
             "pressure_graph_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_pressure_propagation_latency_ms",
         impact_planning_diagnostics.get(
             "pressure_propagation_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_pressure_operation_latency_ms",
         impact_planning_diagnostics.get(
             "pressure_operation_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_pressure_schedule_latency_ms",
         impact_planning_diagnostics.get(
             "pressure_schedule_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_pressure_artifact_latency_ms",
         impact_planning_diagnostics.get(
             "pressure_artifact_latency_ms", 0.0)
         / max(1, impact_planning_calls)),
        ("impact_planning_pressure_score_alignment_guard_rejections_per_decision",
         float(impact_planning_diagnostics.get(
             "pressure_score_alignment_guard_rejections", 0))
         / max(1, impact_planning_calls)),
        ("impact_planning_pressure_score_alignment_deadline_rejections_per_decision",
         float(impact_planning_diagnostics.get(
             "pressure_score_alignment_deadline_rejections", 0))
         / max(1, impact_planning_calls)),
        ("turn_impact_decision_event_latency_ms",
         impact_decision_event_latency_ms / max(1, turns_executed)),
        ("turn_impact_execution_latency_ms",
         impact_execution_latency_ms / max(1, turns_executed)),
        ("impact_execution_latency_ms",
         impact_execution_latency_ms / max(1, impact_execution_calls)),
        ("impact_execution_preflight_latency_ms",
         impact_execution_diagnostics.get("preflight_latency_ms", 0.0)
         / max(1, impact_execution_calls)),
        ("impact_execution_sent_event_latency_ms",
         impact_execution_diagnostics.get("sent_event_latency_ms", 0.0)
         / max(1, impact_execution_calls)),
        ("impact_execution_transport_latency_ms",
         impact_execution_diagnostics.get("transport_latency_ms", 0.0)
         / max(1, impact_execution_calls)),
        ("impact_execution_completion_event_latency_ms",
         impact_execution_diagnostics.get(
             "completion_event_latency_ms", 0.0)
         / max(1, impact_execution_calls)),
        ("turn_impact_preconfirmation_latency_ms",
         impact_preconfirmation_latency_ms / max(1, turns_executed)),
        ("turn_impact_confirmation_nonstate_latency_ms",
         impact_confirmation_nonstate_latency_ms / max(1, turns_executed)),
        ("turn_impact_postconfirmation_latency_ms",
         impact_postconfirmation_latency_ms / max(1, turns_executed)),
        ("turn_impact_postconfirmation_effect_latency_ms",
         impact_postconfirmation_effect_latency_ms
         / max(1, turns_executed)),
        ("turn_impact_postconfirmation_budget_latency_ms",
         impact_postconfirmation_budget_latency_ms
         / max(1, turns_executed)),
        ("turn_impact_postconfirmation_resolution_latency_ms",
         impact_postconfirmation_resolution_latency_ms
         / max(1, turns_executed)),
        ("turn_impact_postconfirmation_reconcile_latency_ms",
         impact_postconfirmation_reconcile_latency_ms
         / max(1, turns_executed)),
        ("impact_resolution_calls_per_turn",
         impact_resolution_diagnostics.get("calls", 0)
         / max(1, turns_executed)),
        ("turn_impact_resolution_learning_latency_ms",
         impact_resolution_diagnostics.get("learning_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_resolution_event_latency_ms",
         impact_resolution_diagnostics.get("event_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_resolution_stats_latency_ms",
         impact_resolution_diagnostics.get("stats_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_learning_bookkeeping_latency_ms",
         impact_learning_diagnostics.get("bookkeeping_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_learning_grounding_latency_ms",
         impact_learning_diagnostics.get("grounding_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_learning_feedback_latency_ms",
         impact_learning_diagnostics.get("feedback_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_learning_goal_relief_latency_ms",
         impact_learning_diagnostics.get("goal_relief_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_learning_conductance_latency_ms",
         impact_learning_diagnostics.get("conductance_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_learning_conductance_update_latency_ms",
         impact_learning_diagnostics.get(
             "conductance_update_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_learning_conductance_save_latency_ms",
         impact_learning_diagnostics.get("conductance_save_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_learning_conductance_hash_latency_ms",
         impact_learning_diagnostics.get("conductance_hash_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_impact_learning_downstream_latency_ms",
         impact_learning_diagnostics.get("downstream_latency_ms", 0.0)
         / max(1, turns_executed)),
        ("turn_action_refresh_observer_latency_ms",
         action_refresh_observer_latency_ms / max(1, turns_executed)),
        ("turn_action_refresh_event_latency_ms",
         action_refresh_event_latency_ms / max(1, turns_executed)),
        ("turn_end_submit_latency_ms",
         sum(turn_end_submit_latencies)
         / max(1, len(turn_end_submit_latencies))),
        ("turn_boundary_latency_ms", mean_boundary_latency),
        ("turn_boundary_state_latency_ms", mean_transition_state_latency),
        ("turn_boundary_nonstate_latency_ms", max(
            0.0, mean_boundary_latency - mean_transition_state_latency)),
        ("turn_boundary_state_query_latency_ms",
         transition_state_diagnostics.get("query_latency_ms", 0.0)
         / transition_calls),
        ("turn_boundary_state_query_count",
         transition_state_diagnostics.get("queries", 0.0) / transition_calls),
        ("turn_boundary_state_settled_response_rate",
         transition_state_diagnostics.get("settled_responses", 0.0)
         / transition_calls),
        ("turn_boundary_state_settled_marker_rate",
         transition_state_diagnostics.get("settled_markers", 0.0)
         / transition_calls),
        ("turn_boundary_state_server_source_wait_ms",
         mean_state_diagnostic(
             transition_state_diagnostics, "server_source_wait_ms",
             transition_calls)),
        ("turn_boundary_state_server_projection_ms",
         mean_state_diagnostic(
             transition_state_diagnostics, "server_projection_ms",
             transition_calls)),
        ("turn_boundary_state_server_quiet_wait_ms",
         mean_state_diagnostic(
             transition_state_diagnostics, "server_quiet_wait_ms",
             transition_calls)),
        ("turn_boundary_state_server_movement_route_wait_ms",
         mean_state_diagnostic(
             transition_state_diagnostics,
             "server_movement_route_wait_ms", transition_calls)),
        ("turn_boundary_state_server_movement_route_responses",
         mean_state_diagnostic(
             transition_state_diagnostics,
             "server_movement_route_responses", transition_calls)),
        ("turn_boundary_state_server_prepare_ms",
         mean_state_diagnostic(
             transition_state_diagnostics,
             "server_elapsed_before_serialize_ms", transition_calls)),
        ("turn_boundary_state_delivery_ms",
         mean_state_delivery_latency(
             transition_state_diagnostics, transition_calls)),
        ("turn_boundary_state_json_decode_ms",
         mean_state_diagnostic(
             transition_state_diagnostics, "client_json_decode_ms",
             transition_calls)),
        ("turn_boundary_state_delivery_excluding_decode_ms",
         mean_state_delivery_excluding_decode(
             transition_state_diagnostics, transition_calls)),
        ("turn_boundary_state_wire_bytes",
         mean_state_diagnostic(
             transition_state_diagnostics, "client_wire_bytes",
             transition_calls)),
        ("turn_boundary_state_projection_count",
         mean_state_diagnostic(
             transition_state_diagnostics, "server_projection_attempts",
             transition_calls)),
        ("turn_boundary_force_end_turn_recovery_attempts",
         transition_state_diagnostics.get(
             "force_end_turn_recovery_attempts", 0.0)),
        ("turn_boundary_force_end_turn_recovery_successes",
         transition_state_diagnostics.get(
             "force_end_turn_recovery_successes", 0.0)),
        ("turn_boundary_force_end_turn_recovery_failures",
         transition_state_diagnostics.get(
             "force_end_turn_recovery_failures", 0.0)),
        ("action_refresh_state_latency_ms",
         action_state_diagnostics.get("latency_ms", 0.0) / action_state_calls),
        ("action_refresh_state_query_latency_ms",
         action_state_diagnostics.get("query_latency_ms", 0.0)
         / action_state_calls),
        ("action_refresh_state_query_count",
         action_state_diagnostics.get("queries", 0.0) / action_state_calls),
        ("action_refresh_state_settled_response_rate",
         action_state_diagnostics.get("settled_responses", 0.0)
         / action_state_calls),
        ("action_refresh_state_settled_marker_rate",
         action_state_diagnostics.get("settled_markers", 0.0)
         / action_state_calls),
        ("action_refresh_state_server_source_wait_ms",
         mean_state_diagnostic(
             action_state_diagnostics, "server_source_wait_ms",
             action_state_calls)),
        ("action_refresh_state_server_projection_ms",
         mean_state_diagnostic(
             action_state_diagnostics, "server_projection_ms",
             action_state_calls)),
        ("action_refresh_state_server_quiet_wait_ms",
         mean_state_diagnostic(
             action_state_diagnostics, "server_quiet_wait_ms",
             action_state_calls)),
        ("action_refresh_state_server_movement_route_wait_ms",
         mean_state_diagnostic(
             action_state_diagnostics,
             "server_movement_route_wait_ms", action_state_calls)),
        ("action_refresh_state_server_movement_route_responses",
         mean_state_diagnostic(
             action_state_diagnostics,
             "server_movement_route_responses", action_state_calls)),
        ("action_refresh_state_server_prepare_ms",
         mean_state_diagnostic(
             action_state_diagnostics,
             "server_elapsed_before_serialize_ms", action_state_calls)),
        ("action_refresh_state_delivery_ms",
         mean_state_delivery_latency(
             action_state_diagnostics, action_state_calls)),
        ("action_refresh_state_json_decode_ms",
         mean_state_diagnostic(
             action_state_diagnostics, "client_json_decode_ms",
             action_state_calls)),
        ("action_refresh_state_delivery_excluding_decode_ms",
         mean_state_delivery_excluding_decode(
             action_state_diagnostics, action_state_calls)),
        ("action_refresh_state_wire_bytes",
         mean_state_diagnostic(
             action_state_diagnostics, "client_wire_bytes",
             action_state_calls)),
        ("action_refresh_state_projection_count",
         mean_state_diagnostic(
             action_state_diagnostics, "server_projection_attempts",
             action_state_calls)),
        ("action_refresh_state_parse_latency_ms",
         action_state_diagnostics.get("parse_latency_ms", 0.0)
         / action_state_calls),
        ("action_refresh_state_settle_wait_ms",
         action_state_diagnostics.get("settle_wait_requested_ms", 0.0)
         / action_state_calls),
        ("turn_boundary_state_parse_latency_ms",
         transition_state_diagnostics.get("parse_latency_ms", 0.0)
         / transition_calls),
        ("turn_boundary_state_settle_wait_ms",
         transition_state_diagnostics.get("settle_wait_requested_ms", 0.0)
         / transition_calls),
        ("turn_checkpoint_sync_latency_ms",
         sum(turn_checkpoint_sync_latencies)
         / max(1, len(turn_checkpoint_sync_latencies))),
        ("final_global_settle_latency_ms", final_global_settle_latency),
        ("observer_global_state_queries", observer_global_state_queries),
        ("full_loop_under_30s_rate", full_loop_under_30),
        ("zombie_action_attempt_blocked", zombie_blocked),
        ("planned_engine_actions", planned_actions),
        ("meaningful_actions_per_turn", meaningful_per_turn),
        ("decision_impact_actions", decision_stats["impact_actions"]),
        ("decision_impact_turn_rate", impact_turn_rate),
        ("operation_authority_opportunities",
         decision_stats["operation_authority_opportunities"]),
        ("operation_authority_actions",
         decision_stats["operation_authority_actions"]),
        ("operation_authority_winner_changes",
         decision_stats["operation_authority_winner_changes"]),
        ("decision_effect_observed_rate", effect_observed_rate),
        ("decision_effect_confirmation_latency_ms",
         sum(effect_confirmation_latencies) / max(1, len(effect_confirmation_latencies))),
        ("decision_effect_confirmation_timeouts",
         decision_stats["effect_confirmation_timeouts"]),
        ("decision_effect_confirmation_deferred",
         decision_stats["effect_confirmation_deferred"]),
        ("decision_effect_confirmation_recovered",
         decision_stats["effect_confirmation_recovered"]),
        ("decision_effect_confirmation_expired",
         decision_stats["effect_confirmation_expired"]),
        ("decision_effect_confirmation_pending", len(pending_impact_outcomes)),
        ("decision_stale_terminal_followups_blocked",
         decision_stats["stale_terminal_followups_blocked"]),
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
        ("model_selection_call_rate",
         float(decision_stats["model_selection_calls"]) / max(1, turns_executed)),
        ("model_selection_call_avoided_rate",
         float(decision_stats["model_selection_calls_avoided"])
         / max(1, turns_executed)),
        ("action_type_diversity", len(action_type_counts)),
        ("cities_gained", city_gain),
        ("cities_founded", decision_stats["settlement_completions"]),
        ("technologies_acquired", technology_gain),
        ("positions_explored", explored_positions),
        ("production_changes", decision_stats["production_changes"]),
        ("founder_production_changes",
         decision_stats["founder_production_changes"]),
        ("production_repurpose_changes",
         decision_stats["production_repurpose_changes"]),
        ("production_preexpansion_growth_changes",
         decision_stats["production_preexpansion_growth_changes"]),
        ("production_preexpansion_founder_changes",
         decision_stats["production_preexpansion_founder_changes"]),
        ("production_military_score_changes",
         decision_stats["production_military_score_changes"]),
        ("settlement_attempts", decision_stats["settlement_attempts"]),
        ("settlement_completions", decision_stats["settlement_completions"]),
        ("planner_capability_pruned_worker_moves",
         len(capability_pruned_worker_moves)),
        ("planner_nonprogress_moves_pruned", len(nonprogress_moves)),
        ("planner_repeated_failed_destination_moves_pruned",
         impact_planner.repeated_failed_destination_moves_pruned
         if impact_planner is not None else 0),
        ("planner_founder_unreachable_moves_pruned",
         len(unreachable_founder_moves)),
        ("planner_founder_cycle_moves_pruned", len(founder_cycle_moves)),
        ("planner_founder_attrition_moves_pruned", len(founder_attrition_moves)),
        ("planner_failed_settlement_sites_pruned",
         impact_planner.failed_settlement_sites_pruned
         if impact_planner is not None else 0),
        ("planner_founder_route_successes",
         impact_planner.founder_route_successes if impact_planner is not None else 0),
        ("planner_founder_route_failures",
         impact_planner.founder_route_failures if impact_planner is not None else 0),
        ("planner_founder_route_success_rate",
         (float(impact_planner.founder_route_successes)
          / max(1, impact_planner.founder_route_successes
                + impact_planner.founder_route_failures))
         if impact_planner is not None else 0.0),
        ("planner_founder_cardinal_corridor_attempts",
         impact_planner.founder_cardinal_corridor_attempts
         if impact_planner is not None else 0),
        ("planner_founder_cardinal_corridor_successes",
         impact_planner.founder_cardinal_corridor_successes
         if impact_planner is not None else 0),
        ("planner_founder_cardinal_corridor_success_rate",
         (float(impact_planner.founder_cardinal_corridor_successes)
          / max(1, impact_planner.founder_cardinal_corridor_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_settlement_site_preference_attempts",
         impact_planner.founder_settlement_site_preference_attempts
         if impact_planner is not None else 0),
        ("planner_founder_settlement_site_preference_successes",
         impact_planner.founder_settlement_site_preference_successes
         if impact_planner is not None else 0),
        ("planner_founder_settlement_site_preference_success_rate",
         (float(
             impact_planner.founder_settlement_site_preference_successes)
          / max(
              1,
              impact_planner.founder_settlement_site_preference_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_escort_deferral_snapshots",
         impact_planner.founder_escort_deferral_snapshots
         if impact_planner is not None else 0),
        ("planner_founder_escort_threat_deferral_snapshots",
         impact_planner.founder_escort_threat_deferral_snapshots
         if impact_planner is not None else 0),
        ("planner_founder_escort_persisted_threat_deferral_snapshots",
         impact_planner.founder_escort_persisted_threat_deferral_snapshots
         if impact_planner is not None else 0),
        ("planner_founder_route_threat_observations",
         impact_planner.founder_route_threat_observations
         if impact_planner is not None else 0),
        ("planner_founder_final_escort_deferral_snapshots",
         impact_planner.founder_final_escort_deferral_snapshots
         if impact_planner is not None else 0),
        ("planner_founder_final_escort_rendezvous_hold_snapshots",
         impact_planner.founder_final_escort_rendezvous_hold_snapshots
         if impact_planner is not None else 0),
        ("planner_founder_final_escort_rendezvous_no_progress_snapshots",
         impact_planner.founder_final_escort_rendezvous_no_progress_snapshots
         if impact_planner is not None else 0),
        ("planner_founder_final_escort_unprepared_route_bypass_snapshots",
         impact_planner
         .founder_final_escort_unprepared_route_bypass_snapshots
         if impact_planner is not None else 0),
        ("planner_founder_final_escort_unthreatened_route_bypass_snapshots",
         impact_planner
         .founder_final_escort_unthreatened_route_bypass_snapshots
         if impact_planner is not None else 0),
        ("planner_founder_escort_defense_production_attempts",
         impact_planner.founder_escort_defense_production_attempts
         if impact_planner is not None else 0),
        ("planner_founder_escort_defense_production_successes",
         impact_planner.founder_escort_defense_production_successes
         if impact_planner is not None else 0),
        ("planner_founder_escort_defense_production_success_rate",
         (float(impact_planner.founder_escort_defense_production_successes)
         / max(
             1,
             impact_planner.founder_escort_defense_production_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_final_escort_preparation_production_attempts",
         impact_planner.founder_final_escort_preparation_production_attempts
         if impact_planner is not None else 0),
        ("planner_founder_final_escort_preparation_production_successes",
         impact_planner.founder_final_escort_preparation_production_successes
         if impact_planner is not None else 0),
        ("planner_founder_final_escort_preparation_production_success_rate",
         (float(
             impact_planner
             .founder_final_escort_preparation_production_successes)
          / max(
              1,
              impact_planner
              .founder_final_escort_preparation_production_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_escort_move_attempts",
         impact_planner.founder_escort_move_attempts
         if impact_planner is not None else 0),
        ("planner_founder_escort_move_successes",
         impact_planner.founder_escort_move_successes
         if impact_planner is not None else 0),
        ("planner_founder_escort_move_success_rate",
         (float(impact_planner.founder_escort_move_successes)
         / max(1, impact_planner.founder_escort_move_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_final_escort_move_attempts",
         impact_planner.founder_final_escort_move_attempts
         if impact_planner is not None else 0),
        ("planner_founder_final_escort_move_successes",
         impact_planner.founder_final_escort_move_successes
         if impact_planner is not None else 0),
        ("planner_founder_final_escort_move_success_rate",
         (float(impact_planner.founder_final_escort_move_successes)
          / max(1, impact_planner.founder_final_escort_move_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_threat_avoidance_move_attempts",
         impact_planner.founder_threat_avoidance_move_attempts
         if impact_planner is not None else 0),
        ("planner_founder_threat_avoidance_move_successes",
         impact_planner.founder_threat_avoidance_move_successes
         if impact_planner is not None else 0),
        ("planner_founder_threat_avoidance_move_success_rate",
         (float(impact_planner.founder_threat_avoidance_move_successes)
          / max(
              1, impact_planner.founder_threat_avoidance_move_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_escorted_settlement_attempts",
         impact_planner.founder_escorted_settlement_attempts
         if impact_planner is not None else 0),
        ("planner_founder_escorted_settlement_completions",
         impact_planner.founder_escorted_settlement_completions
         if impact_planner is not None else 0),
        ("planner_founder_escorted_settlement_completion_rate",
         (float(impact_planner.founder_escorted_settlement_completions)
          / max(1, impact_planner.founder_escorted_settlement_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_final_escorted_settlement_attempts",
         impact_planner.founder_final_escorted_settlement_attempts
         if impact_planner is not None else 0),
        ("planner_founder_final_escorted_settlement_completions",
         impact_planner.founder_final_escorted_settlement_completions
         if impact_planner is not None else 0),
        ("planner_founder_final_escorted_settlement_completion_rate",
         (float(
             impact_planner.founder_final_escorted_settlement_completions)
          / max(
              1,
              impact_planner.founder_final_escorted_settlement_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_unescorted_safe_settlement_attempts",
         impact_planner.founder_unescorted_safe_settlement_attempts
         if impact_planner is not None else 0),
        ("planner_founder_unescorted_safe_settlement_completions",
         impact_planner.founder_unescorted_safe_settlement_completions
         if impact_planner is not None else 0),
        ("planner_founder_unescorted_safe_settlement_completion_rate",
         (float(
             impact_planner.founder_unescorted_safe_settlement_completions)
          / max(
              1,
              impact_planner.founder_unescorted_safe_settlement_attempts))
         if impact_planner is not None else 0.0),
        ("planner_founder_capable_unit_types",
         len(impact_planner.founder_capable_types)
         if impact_planner is not None else 0),
        ("population_recovery_route_attempts",
         impact_planner.population_recovery_route_attempts
         if impact_planner is not None else 0),
        ("population_recovery_route_successes",
         impact_planner.population_recovery_route_successes
         if impact_planner is not None else 0),
        ("population_recovery_route_success_rate",
         (float(impact_planner.population_recovery_route_successes)
          / max(1, impact_planner.population_recovery_route_attempts))
         if impact_planner is not None else 0.0),
        ("population_recovery_attempts",
         impact_planner.population_recovery_attempts
         if impact_planner is not None else 0),
        ("population_recovery_completions",
         impact_planner.population_recovery_completions
         if impact_planner is not None else 0),
        ("population_recovered",
         impact_planner.population_recovered if impact_planner is not None else 0),
        ("tactical_actions", decision_stats["tactical_actions"]),
        ("production_projected_completion_eta_turns",
         sum(production_projection_etas) / max(1, len(production_projection_etas))),
        ("production_projected_score_value",
         sum(production_projection_values) / max(1, len(production_projection_values))),
        ("production_projected_unit_completions",
         sum(production_projection_unit_completions)
         / max(1, len(production_projection_unit_completions))),
        ("production_projected_unit_score_progress",
         sum(production_projection_unit_score_progress)
         / max(1, len(production_projection_unit_score_progress))),
        ("production_guaranteed_unit_score_points",
         sum(production_projection_guaranteed_unit_score)
         / max(1, len(production_projection_guaranteed_unit_score))),
        ("production_batch_incremental_unit_completions",
         sum(production_batch_incremental_unit_completions)
         / max(1, len(production_batch_incremental_unit_completions))),
        ("production_batch_guaranteed_unit_score_points",
         sum(production_batch_guaranteed_unit_score)
         / max(1, len(production_batch_guaranteed_unit_score))),
        ("production_projected_build_cost",
         sum(production_projection_costs) / max(1, len(production_projection_costs))),
        ("production_projected_shield_surplus",
         sum(production_projection_shields) / max(1, len(production_projection_shields))),
        ("production_projected_pop_cost",
         sum(production_projection_pop_costs) / max(1, len(production_projection_pop_costs))),
        ("production_projection_ruleset_source_rate",
         sum(production_projection_ruleset_sources)
         / float(max(1, len(production_projection_ruleset_sources)))),
        ("production_projected_population_ready_eta_turns",
         sum(production_projection_population_etas)
         / float(max(1, len(production_projection_population_etas)))),
        ("production_projected_settlement_eta_turns",
         sum(production_projection_settlement_etas)
         / float(max(1, len(production_projection_settlement_etas)))),
        ("production_projected_settlement_runway_turns",
         sum(production_projection_settlement_runways)
         / float(max(1, len(production_projection_settlement_runways)))),
        ("production_projected_founder_route_eta_turns",
         sum(production_projection_route_etas)
         / float(max(1, len(production_projection_route_etas)))),
        ("production_projection_route_observed_source_rate",
         sum(production_projection_route_eta_sources)
         / float(max(1, len(production_projection_route_eta_sources)))),
        ("production_projection_growth_ruleset_source_rate",
         sum(production_projection_growth_ruleset_sources)
         / float(max(1, len(production_projection_growth_ruleset_sources)))),
        ("production_founder_deficit_before",
         sum(production_founder_deficits)
         / float(max(1, len(production_founder_deficits)))),
        ("production_repurpose_avoided_population_cost",
         sum(production_repurpose_avoided_population)),
        ("production_repurpose_discarded_shield_stock",
         sum(production_repurpose_discarded_shields)),
        ("production_repurpose_target_completion_rate",
         sum(production_repurpose_target_completions)
         / float(max(1, len(production_repurpose_target_completions)))),
        ("production_preexpansion_sequence_settlement_eta_turns",
         sum(production_preexpansion_settlement_etas)
         / float(max(1, len(production_preexpansion_settlement_etas)))),
        ("production_preexpansion_sequence_settlement_runway_turns",
         sum(production_preexpansion_settlement_runways)
         / float(max(1, len(production_preexpansion_settlement_runways)))),
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
    drained_domain_estimates = ()
    final_domain_estimate_events = ()
    drained_resource_schedules = ()
    final_resource_schedule_events = ()
    if impact_planner is not None:
        drained_domain_estimates = (
            impact_planner.flush_domain_estimates(
                timeout=5.0))
        final_domain_estimate_events = (
            control_event_emitter
            .emit_domain_estimate_artifacts(
                writer, final_turn,
                drained_domain_estimates,
                caused_by=(parent,)))
        if final_domain_estimate_events:
            parent = final_domain_estimate_events[
                -1]["event_id"]
        drained_resource_schedules = (
            impact_planner
            .flush_resource_schedules(
                timeout=5.0))
        final_resource_schedule_events = (
            control_event_emitter
            .emit_resource_schedule_results(
                writer, final_turn,
                drained_resource_schedules,
                caused_by=(parent,)))
        if final_resource_schedule_events:
            parent = (
                final_resource_schedule_events[
                    -1]["event_id"])
        impact_planner.close_domain_estimates()
        metrics.extend((
            ("domain_estimate_final_drain_batches",
             len(drained_domain_estimates)),
            ("domain_estimate_final_drain_events",
             len(final_domain_estimate_events)),
            ("resource_schedule_final_drain_batches",
             len(drained_resource_schedules)),
            ("resource_schedule_final_drain_events",
             len(final_resource_schedule_events)),
        ))
    for name, value in metrics:
        parent = _metric(writer, final_turn, parent, name, value, manifest,
                         seed=manifest["seed"], sequence=manifest.get("sequence", 0))
    writer.emit("run_completed", final_turn, {
        "status": "completed", "summary": {
            "actions": action_count, "calibration_samples": len(predictions),
            "model_corrections": corrections, "opponent": opponent.get("name"),
            "model_selection_calls": decision_stats["model_selection_calls"],
            "model_selection_calls_avoided": (
                decision_stats["model_selection_calls_avoided"]),
            "decision_impact_actions": decision_stats["impact_actions"],
            "operation_authority_opportunities": (
                decision_stats[
                    "operation_authority_opportunities"]),
            "operation_authority_actions": (
                decision_stats[
                    "operation_authority_actions"]),
            "operation_authority_winner_changes": (
                decision_stats[
                    "operation_authority_winner_changes"]),
            "decision_no_effect_retries_blocked": (
                impact_planner.no_effect_retries_blocked
                if impact_planner is not None else 0),
            "decision_no_effect_failover_attempts": decision_stats["failover_attempts"],
            "decision_no_effect_failover_recoveries": (
                decision_stats["failover_recoveries"]),
            "decision_effect_confirmation_timeouts": (
                decision_stats["effect_confirmation_timeouts"]),
            "decision_effect_confirmation_deferred": (
                decision_stats["effect_confirmation_deferred"]),
            "decision_effect_confirmation_recovered": (
                decision_stats["effect_confirmation_recovered"]),
            "decision_effect_confirmation_expired": (
                decision_stats["effect_confirmation_expired"]),
            "decision_effect_confirmation_pending": len(pending_impact_outcomes),
            "domain_estimate_final_drain_batches":
                len(drained_domain_estimates),
            "domain_estimate_final_drain_events":
                len(final_domain_estimate_events),
            "decision_stale_terminal_followups_blocked": (
                decision_stats["stale_terminal_followups_blocked"]),
            "meaningful_actions": decision_stats["meaningful_actions"],
            "founder_production_changes": (
                decision_stats["founder_production_changes"]),
            "production_repurpose_changes": (
                decision_stats["production_repurpose_changes"]),
            "production_preexpansion_growth_changes": (
                decision_stats["production_preexpansion_growth_changes"]),
            "production_preexpansion_founder_changes": (
                decision_stats["production_preexpansion_founder_changes"]),
            "production_military_score_changes": (
                decision_stats["production_military_score_changes"]),
            "settlement_attempts": decision_stats["settlement_attempts"],
            "cities_gained": city_gain,
            "settlement_completions": decision_stats["settlement_completions"],
            "planner_capability_pruned_worker_moves": (
                len(capability_pruned_worker_moves)),
            "planner_nonprogress_moves_pruned": len(nonprogress_moves),
            "planner_repeated_failed_destination_moves_pruned": (
                impact_planner.repeated_failed_destination_moves_pruned
                if impact_planner is not None else 0),
            "planner_founder_unreachable_moves_pruned": (
                len(unreachable_founder_moves)),
            "planner_founder_cycle_moves_pruned": len(founder_cycle_moves),
            "planner_founder_attrition_moves_pruned": (
                len(founder_attrition_moves)),
            "planner_failed_settlement_sites_pruned": (
                impact_planner.failed_settlement_sites_pruned
                if impact_planner is not None else 0),
            "planner_founder_route_successes": (
                impact_planner.founder_route_successes
                if impact_planner is not None else 0),
            "planner_founder_route_failures": (
                impact_planner.founder_route_failures
                if impact_planner is not None else 0),
            "planner_founder_cardinal_corridor_attempts": (
                impact_planner.founder_cardinal_corridor_attempts
                if impact_planner is not None else 0),
            "planner_founder_cardinal_corridor_successes": (
                impact_planner.founder_cardinal_corridor_successes
                if impact_planner is not None else 0),
            "planner_founder_settlement_site_preference_attempts": (
                impact_planner.founder_settlement_site_preference_attempts
                if impact_planner is not None else 0),
            "planner_founder_settlement_site_preference_successes": (
                impact_planner.founder_settlement_site_preference_successes
                if impact_planner is not None else 0),
            "planner_founder_escort_deferral_snapshots": (
                impact_planner.founder_escort_deferral_snapshots
                if impact_planner is not None else 0),
            "planner_founder_escort_threat_deferral_snapshots": (
                impact_planner.founder_escort_threat_deferral_snapshots
                if impact_planner is not None else 0),
            "planner_founder_escort_persisted_threat_deferral_snapshots": (
                impact_planner
                .founder_escort_persisted_threat_deferral_snapshots
                if impact_planner is not None else 0),
            "planner_founder_route_threat_observations": (
                impact_planner.founder_route_threat_observations
                if impact_planner is not None else 0),
            "planner_founder_final_escort_deferral_snapshots": (
                impact_planner.founder_final_escort_deferral_snapshots
                if impact_planner is not None else 0),
            "planner_founder_final_escort_rendezvous_hold_snapshots": (
                impact_planner
                .founder_final_escort_rendezvous_hold_snapshots
                if impact_planner is not None else 0),
            "planner_founder_final_escort_rendezvous_no_progress_snapshots": (
                impact_planner
                .founder_final_escort_rendezvous_no_progress_snapshots
                if impact_planner is not None else 0),
            "planner_founder_final_escort_unprepared_route_bypass_snapshots": (
                impact_planner
                .founder_final_escort_unprepared_route_bypass_snapshots
                if impact_planner is not None else 0),
            "planner_founder_final_escort_unthreatened_route_bypass_snapshots": (
                impact_planner
                .founder_final_escort_unthreatened_route_bypass_snapshots
                if impact_planner is not None else 0),
            "planner_founder_escort_defense_production_attempts": (
                impact_planner.founder_escort_defense_production_attempts
                if impact_planner is not None else 0),
            "planner_founder_escort_defense_production_successes": (
                impact_planner.founder_escort_defense_production_successes
                if impact_planner is not None else 0),
            "planner_founder_final_escort_preparation_production_attempts": (
                impact_planner
                .founder_final_escort_preparation_production_attempts
                if impact_planner is not None else 0),
            "planner_founder_final_escort_preparation_production_successes": (
                impact_planner
                .founder_final_escort_preparation_production_successes
                if impact_planner is not None else 0),
            "planner_founder_escort_move_attempts": (
                impact_planner.founder_escort_move_attempts
                if impact_planner is not None else 0),
            "planner_founder_escort_move_successes": (
                impact_planner.founder_escort_move_successes
                if impact_planner is not None else 0),
            "planner_founder_final_escort_move_attempts": (
                impact_planner.founder_final_escort_move_attempts
                if impact_planner is not None else 0),
            "planner_founder_final_escort_move_successes": (
                impact_planner.founder_final_escort_move_successes
                if impact_planner is not None else 0),
            "planner_founder_threat_avoidance_move_attempts": (
                impact_planner.founder_threat_avoidance_move_attempts
                if impact_planner is not None else 0),
            "planner_founder_threat_avoidance_move_successes": (
                impact_planner.founder_threat_avoidance_move_successes
                if impact_planner is not None else 0),
            "planner_founder_escorted_settlement_attempts": (
                impact_planner.founder_escorted_settlement_attempts
                if impact_planner is not None else 0),
            "planner_founder_escorted_settlement_completions": (
                impact_planner.founder_escorted_settlement_completions
                if impact_planner is not None else 0),
            "planner_founder_final_escorted_settlement_attempts": (
                impact_planner.founder_final_escorted_settlement_attempts
                if impact_planner is not None else 0),
            "planner_founder_final_escorted_settlement_completions": (
                impact_planner.founder_final_escorted_settlement_completions
                if impact_planner is not None else 0),
            "planner_founder_unescorted_safe_settlement_attempts": (
                impact_planner.founder_unescorted_safe_settlement_attempts
                if impact_planner is not None else 0),
            "planner_founder_unescorted_safe_settlement_completions": (
                impact_planner.founder_unescorted_safe_settlement_completions
                if impact_planner is not None else 0),
            "planner_founder_capable_unit_types": (
                len(impact_planner.founder_capable_types)
                if impact_planner is not None else 0),
            "population_recovery_route_attempts": (
                impact_planner.population_recovery_route_attempts
                if impact_planner is not None else 0),
            "population_recovery_route_successes": (
                impact_planner.population_recovery_route_successes
                if impact_planner is not None else 0),
            "population_recovery_attempts": (
                impact_planner.population_recovery_attempts
                if impact_planner is not None else 0),
            "population_recovery_completions": (
                impact_planner.population_recovery_completions
                if impact_planner is not None else 0),
            "population_recovered": (
                impact_planner.population_recovered
                if impact_planner is not None else 0),
            "planned_engine_actions": planned_actions,
            "turn_boundary_force_end_turn_recovery_attempts": (
                transition_state_diagnostics.get(
                    "force_end_turn_recovery_attempts", 0.0)),
            "turn_boundary_force_end_turn_recovery_successes": (
                transition_state_diagnostics.get(
                    "force_end_turn_recovery_successes", 0.0)),
            "turn_boundary_force_end_turn_recovery_failures": (
                transition_state_diagnostics.get(
                    "force_end_turn_recovery_failures", 0.0)),
            "opponent_score": opponent_score,
            "outcome_definition": "fixed_horizon_score_lead",
            "horizon_reached": horizon_reached,
            "score_observation_semantics": score_observation_semantics,
            "score_observation_turn": final_turn,
            "score": player_score, "score_lead": score_lead,
            "score_margin": score_margin, "won": won,
            "terminal_game_over": terminal_game_over,
            "terminal_player_elimination": terminal_player_elimination,
            "zombie_attempts_blocked": zombie_blocked,
        }}, caused_by=[parent])
    return {
        "capability_audit": context.audit(), "calibration_samples": len(predictions),
        "completed": True, "engine_actions": action_count,
        "infrastructure_failure": False, "loss": not won,
        "horizon_reached": horizon_reached,
        "score_observation_semantics": score_observation_semantics,
        "score_observation_turn": final_turn,
        "terminal_game_over": terminal_game_over,
        "terminal_player_elimination": terminal_player_elimination,
        "model_latency_ms": model_latency, "rejected_actions": rejected,
        "model_selection_calls": decision_stats["model_selection_calls"],
        "model_selection_calls_avoided": (
            decision_stats["model_selection_calls_avoided"]),
        "decision_impact_actions": decision_stats["impact_actions"],
        "operation_authority_opportunities": (
            decision_stats[
                "operation_authority_opportunities"]),
        "operation_authority_actions": (
            decision_stats[
                "operation_authority_actions"]),
        "operation_authority_winner_changes": (
            decision_stats[
                "operation_authority_winner_changes"]),
        "decision_no_effect_retries_blocked": (
            impact_planner.no_effect_retries_blocked
            if impact_planner is not None else 0),
        "decision_no_effect_failover_attempts": decision_stats["failover_attempts"],
        "decision_no_effect_failover_recoveries": decision_stats["failover_recoveries"],
        "decision_effect_confirmation_deferred": (
            decision_stats["effect_confirmation_deferred"]),
        "decision_effect_confirmation_recovered": (
            decision_stats["effect_confirmation_recovered"]),
        "decision_effect_confirmation_expired": (
            decision_stats["effect_confirmation_expired"]),
        "decision_effect_confirmation_pending": len(pending_impact_outcomes),
        "decision_stale_terminal_followups_blocked": (
            decision_stats["stale_terminal_followups_blocked"]),
        "initial_legal_action_families": initial_legal_action_families,
        "initial_state_fingerprint": initial_state_fingerprint,
        "meaningful_actions": decision_stats["meaningful_actions"],
        "turn_boundary_force_end_turn_recovery_attempts": (
            transition_state_diagnostics.get(
                "force_end_turn_recovery_attempts", 0.0)),
        "turn_boundary_force_end_turn_recovery_successes": (
            transition_state_diagnostics.get(
                "force_end_turn_recovery_successes", 0.0)),
        "turn_boundary_force_end_turn_recovery_failures": (
            transition_state_diagnostics.get(
                "force_end_turn_recovery_failures", 0.0)),
        "founder_production_changes": decision_stats["founder_production_changes"],
        "production_repurpose_changes": decision_stats["production_repurpose_changes"],
        "production_preexpansion_growth_changes": (
            decision_stats["production_preexpansion_growth_changes"]),
        "production_preexpansion_founder_changes": (
            decision_stats["production_preexpansion_founder_changes"]),
        "production_military_score_changes": (
            decision_stats["production_military_score_changes"]),
        "settlement_attempts": decision_stats["settlement_attempts"],
        "cities_gained": city_gain,
        "settlement_completions": decision_stats["settlement_completions"],
        "planner_capability_pruned_worker_moves": (
            len(capability_pruned_worker_moves)),
        "planner_nonprogress_moves_pruned": len(nonprogress_moves),
        "planner_repeated_failed_destination_moves_pruned": (
            impact_planner.repeated_failed_destination_moves_pruned
            if impact_planner is not None else 0),
        "planner_founder_unreachable_moves_pruned": len(unreachable_founder_moves),
        "planner_founder_cycle_moves_pruned": len(founder_cycle_moves),
        "planner_founder_attrition_moves_pruned": len(founder_attrition_moves),
        "planner_failed_settlement_sites_pruned": (
            impact_planner.failed_settlement_sites_pruned
            if impact_planner is not None else 0),
        "planner_founder_route_successes": (
            impact_planner.founder_route_successes
            if impact_planner is not None else 0),
        "planner_founder_route_failures": (
            impact_planner.founder_route_failures
            if impact_planner is not None else 0),
        "planner_founder_cardinal_corridor_attempts": (
            impact_planner.founder_cardinal_corridor_attempts
            if impact_planner is not None else 0),
        "planner_founder_cardinal_corridor_successes": (
            impact_planner.founder_cardinal_corridor_successes
            if impact_planner is not None else 0),
        "planner_founder_settlement_site_preference_attempts": (
            impact_planner.founder_settlement_site_preference_attempts
            if impact_planner is not None else 0),
        "planner_founder_settlement_site_preference_successes": (
            impact_planner.founder_settlement_site_preference_successes
            if impact_planner is not None else 0),
        "planner_founder_escort_deferral_snapshots": (
            impact_planner.founder_escort_deferral_snapshots
            if impact_planner is not None else 0),
        "planner_founder_escort_threat_deferral_snapshots": (
            impact_planner.founder_escort_threat_deferral_snapshots
            if impact_planner is not None else 0),
        "planner_founder_escort_persisted_threat_deferral_snapshots": (
            impact_planner.founder_escort_persisted_threat_deferral_snapshots
            if impact_planner is not None else 0),
        "planner_founder_route_threat_observations": (
            impact_planner.founder_route_threat_observations
            if impact_planner is not None else 0),
        "planner_founder_final_escort_deferral_snapshots": (
            impact_planner.founder_final_escort_deferral_snapshots
            if impact_planner is not None else 0),
        "planner_founder_final_escort_rendezvous_hold_snapshots": (
            impact_planner.founder_final_escort_rendezvous_hold_snapshots
            if impact_planner is not None else 0),
        "planner_founder_final_escort_rendezvous_no_progress_snapshots": (
            impact_planner
            .founder_final_escort_rendezvous_no_progress_snapshots
            if impact_planner is not None else 0),
        "planner_founder_final_escort_unprepared_route_bypass_snapshots": (
            impact_planner
            .founder_final_escort_unprepared_route_bypass_snapshots
            if impact_planner is not None else 0),
        "planner_founder_final_escort_unthreatened_route_bypass_snapshots": (
            impact_planner
            .founder_final_escort_unthreatened_route_bypass_snapshots
            if impact_planner is not None else 0),
        "planner_founder_escort_defense_production_attempts": (
            impact_planner.founder_escort_defense_production_attempts
            if impact_planner is not None else 0),
        "planner_founder_escort_defense_production_successes": (
            impact_planner.founder_escort_defense_production_successes
            if impact_planner is not None else 0),
        "planner_founder_final_escort_preparation_production_attempts": (
            impact_planner
            .founder_final_escort_preparation_production_attempts
            if impact_planner is not None else 0),
        "planner_founder_final_escort_preparation_production_successes": (
            impact_planner
            .founder_final_escort_preparation_production_successes
            if impact_planner is not None else 0),
        "planner_founder_escort_move_attempts": (
            impact_planner.founder_escort_move_attempts
            if impact_planner is not None else 0),
        "planner_founder_escort_move_successes": (
            impact_planner.founder_escort_move_successes
            if impact_planner is not None else 0),
        "planner_founder_final_escort_move_attempts": (
            impact_planner.founder_final_escort_move_attempts
            if impact_planner is not None else 0),
        "planner_founder_final_escort_move_successes": (
            impact_planner.founder_final_escort_move_successes
            if impact_planner is not None else 0),
        "planner_founder_threat_avoidance_move_attempts": (
            impact_planner.founder_threat_avoidance_move_attempts
            if impact_planner is not None else 0),
        "planner_founder_threat_avoidance_move_successes": (
            impact_planner.founder_threat_avoidance_move_successes
            if impact_planner is not None else 0),
        "planner_founder_escorted_settlement_attempts": (
            impact_planner.founder_escorted_settlement_attempts
            if impact_planner is not None else 0),
        "planner_founder_escorted_settlement_completions": (
            impact_planner.founder_escorted_settlement_completions
            if impact_planner is not None else 0),
        "planner_founder_final_escorted_settlement_attempts": (
            impact_planner.founder_final_escorted_settlement_attempts
            if impact_planner is not None else 0),
        "planner_founder_final_escorted_settlement_completions": (
            impact_planner.founder_final_escorted_settlement_completions
            if impact_planner is not None else 0),
        "planner_founder_unescorted_safe_settlement_attempts": (
            impact_planner.founder_unescorted_safe_settlement_attempts
            if impact_planner is not None else 0),
        "planner_founder_unescorted_safe_settlement_completions": (
            impact_planner.founder_unescorted_safe_settlement_completions
            if impact_planner is not None else 0),
        "planner_founder_capable_unit_types": (
            len(impact_planner.founder_capable_types)
            if impact_planner is not None else 0),
        "population_recovery_route_attempts": (
            impact_planner.population_recovery_route_attempts
            if impact_planner is not None else 0),
        "population_recovery_route_successes": (
            impact_planner.population_recovery_route_successes
            if impact_planner is not None else 0),
        "population_recovery_attempts": (
            impact_planner.population_recovery_attempts
            if impact_planner is not None else 0),
        "population_recovery_completions": (
            impact_planner.population_recovery_completions
            if impact_planner is not None else 0),
        "population_recovered": (
            impact_planner.population_recovered
            if impact_planner is not None else 0),
        "planned_engine_actions": planned_actions,
        "zombie_attempts_blocked": zombie_blocked,
    }


def _force_end_turn_proxy(game_id, token, agent_id):
    request = urllib.request.Request(
        "http://127.0.0.1:8002/api/game/{}/force_end_turn".format(game_id),
        data=json.dumps({"agent_id": agent_id}).encode("utf-8"), method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.load(response)
    except Exception as error:
        detail = ""
        if isinstance(error, urllib.error.HTTPError):
            try:
                detail = ": " + error.read().decode("utf-8", "replace")
            except Exception:
                detail = ""
        raise RuntimeError(
            "proxy force-end-turn failed for {}{}".format(game_id, detail))
    result = (
        body.get("results", {}).get(agent_id)
        if isinstance(body, dict) else None)
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RuntimeError(
            "proxy force-end-turn did not confirm agent {} for {}: {}".format(
                agent_id, game_id, body))
    return result


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


def _recycle_server(port, previous_clean_pid=None):
    container = os.environ.get("FREECIV_SERVER_CONTAINER", "fciv-net")

    def inspect_server():
        # Capture process identity and listener readiness in one container
        # execution. Opening a Freeciv connection would allocate a transient
        # client slot and mutate game state.
        probe = (
            "import json,os,sys\n"
            "port=str(int(sys.argv[1]))\n"
            "pid=None\n"
            "names=sorted((n for n in os.listdir('/proc') if n.isdigit()),key=int)\n"
            "for name in names:\n"
            " try:\n"
            "  raw=open('/proc/'+name+'/cmdline','rb').read().split(b'\\0')\n"
            "  args=[v.decode('utf-8','replace') for v in raw if v]\n"
            " except (IOError,OSError):\n"
            "  continue\n"
            " if not args or os.path.basename(args[0])!='freeciv-web':\n"
            "  continue\n"
            " if any(args[i]=='--port' and args[i+1]==port "
            "for i in range(len(args)-1)):\n"
            "  pid=name\n"
            "  break\n"
            "p='%04X'%int(port)\n"
            "rows=open('/proc/net/tcp').read().splitlines()[1:]"
            "+open('/proc/net/tcp6').read().splitlines()[1:]\n"
            "listening=any(len(r.split())>3 "
            "and r.split()[1].rsplit(':',1)[-1]==p "
            "and r.split()[3]=='0A' for r in rows)\n"
            "print(json.dumps({'pid':pid,'listening':bool(pid and listening)},"
            "sort_keys=True))\n"
        )
        output = subprocess.check_output(
            ["docker", "exec", container, "python3", "-c", probe, str(port)],
            text=True)
        try:
            snapshot = json.loads(output)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "invalid civserver inspection response: {}".format(exc))
        if not isinstance(snapshot, dict):
            raise RuntimeError("invalid civserver inspection response")
        pid = snapshot.get("pid")
        if ((pid is not None
                and (not isinstance(pid, str) or not pid.isdigit()))
                or not isinstance(snapshot.get("listening"), bool)):
            raise RuntimeError("invalid civserver inspection response")
        return snapshot

    old_snapshot = inspect_server()
    old_pid = old_snapshot["pid"]
    deadline = time.monotonic() + 20
    if previous_clean_pid is not None and old_pid != previous_clean_pid:
        # A successfully completed game exits its civserver with status zero.
        # Publite2 then supplies a new process. That successor is already the
        # required clean isolation boundary, so do not kill it and trigger the
        # process manager's failure backoff.
        current = old_snapshot
        while time.monotonic() < deadline:
            if (current["pid"] is not None
                    and current["pid"] != previous_clean_pid
                    and current["listening"]):
                return {
                    "method": "clean-successor-listener",
                    "pid": current["pid"],
                }
            time.sleep(0.1)
            current = inspect_server()
        raise RuntimeError(
            "clean civserver successor on port {} did not become ready".format(port))
    if old_pid is not None:
        subprocess.run(["docker", "exec", container, "kill", old_pid], check=False,
                       stdout=subprocess.DEVNULL)
    while time.monotonic() < deadline:
        time.sleep(0.1)
        current = inspect_server()
        if (current["pid"] is not None and current["pid"] != old_pid
                and current["listening"]):
            return {
                "method": "kill-then-listener",
                "pid": current["pid"],
            }
    raise RuntimeError("civserver port {} did not recycle".format(port))


def run_game(run_dir, manifest, context):
    if not 6001 <= int(manifest["port"]) <= 6009:
        raise ValueError("engine-live requires a dedicated multiplayer port")
    backend_started = time.perf_counter()
    token = os.environ.get("FREECIV_API_TOKEN", "test-token-fc3d-001")
    # An interrupted attempt can leave proxy-side game/session metadata after its
    # civserver has gone away. Clear that metadata before recycling the dedicated
    # server; otherwise the proxy may report the old configuration as already
    # applied and skip configuring the fresh process.
    proxy_clear_started = time.perf_counter()
    _terminate_proxy(manifest["game_id"], token, required=True)
    proxy_clear_latency = (
        time.perf_counter() - proxy_clear_started) * 1000.0
    # Every job starts from a newly spawned process so no autosave/session state can
    # leak across seeds or conditions.
    port = int(manifest["port"])
    previous_clean_pid = _LAST_CLEAN_SERVER_PIDS.pop(port, None)
    server_recycle_started = time.perf_counter()
    server_recycle = _recycle_server(
        port, previous_clean_pid=previous_clean_pid)
    server_recycle_latency = (
        time.perf_counter() - server_recycle_started) * 1000.0
    active_server_pid = server_recycle["pid"]
    preflight_latency = (time.perf_counter() - backend_started) * 1000.0
    result = None
    cleanup_latency = None
    try:
        readiness_started = time.perf_counter()
        readiness = _ollama_readiness(manifest)
        readiness_latency = (time.perf_counter() - readiness_started) * 1000.0
        gameplay_started = time.perf_counter()
        result = asyncio.run(_play(run_dir, manifest, context))
        gameplay_latency = (time.perf_counter() - gameplay_started) * 1000.0
    finally:
        cleanup_started = time.perf_counter()
        _terminate_proxy(manifest["game_id"], token)
        cleanup_latency = (time.perf_counter() - cleanup_started) * 1000.0
        # The next arm always performs a hard pre-arm recycle before connecting.
        # Recycling here as well duplicated the same isolation boundary and added
        # roughly six seconds to every arm. Proxy termination is sufficient to
        # close the completed session; the following pre-arm reset remains the
        # authoritative clean-process guarantee, including after a failed arm.
    result.update({
        "engine_backend_latency_ms": (
            (time.perf_counter() - backend_started) * 1000.0),
        "engine_cleanup_latency_ms": cleanup_latency,
        "engine_gameplay_latency_ms": gameplay_latency,
        "engine_preflight_latency_ms": preflight_latency,
        "engine_proxy_clear_latency_ms": proxy_clear_latency,
        "engine_server_recycle_latency_ms": server_recycle_latency,
        "engine_server_pid": active_server_pid,
        "engine_server_recycle_method": server_recycle["method"],
        "model_readiness_latency_ms": readiness_latency,
        "model_readiness_method": readiness["readiness_method"],
        "model_readiness_remaining_seconds": readiness.get(
            "readiness_remaining_seconds"),
        "model_readiness_reused": readiness["readiness_reused"],
    })
    # Publish a reusable predecessor only after the game and its cleanup have
    # both completed successfully. A failed arm leaves no successor shortcut,
    # so its next attempt retains the unconditional kill/recycle path.
    _LAST_CLEAN_SERVER_PIDS[port] = active_server_pid
    return result
