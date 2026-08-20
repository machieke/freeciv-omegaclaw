"""Audit paired legacy/FDAS-shadow engine traces without making outcome claims."""

from collections import defaultdict
import copy
import glob
import json
import os
import statistics

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.validator import validate_file


FDAS_TURN_P95_TARGET_MS = 150.0
CONTROLLER_P95_TARGET_MS = 500.0


def _percentile(values, fraction):
    values = sorted(float(value) for value in values)
    if not values:
        return None
    index = min(
        len(values) - 1,
        max(0, int(round((len(values) - 1) * fraction))))
    return values[index]


def _latency_summary(values):
    values = tuple(float(value) for value in values)
    if not values:
        return {
            "count": 0, "maximum_ms": None, "mean_ms": None,
            "p50_ms": None, "p95_ms": None,
        }
    return {
        "count": len(values),
        "maximum_ms": max(values),
        "mean_ms": statistics.mean(values),
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
    }


def _byte_summary(values):
    values = tuple(int(value) for value in values if int(value) > 0)
    if not values:
        return {
            "count": 0, "maximum_bytes": None, "mean_bytes": None,
            "p50_bytes": None, "p95_bytes": None,
        }
    return {
        "count": len(values),
        "maximum_bytes": max(values),
        "mean_bytes": statistics.mean(values),
        "p50_bytes": int(_percentile(values, 0.50)),
        "p95_bytes": int(_percentile(values, 0.95)),
    }


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _read_events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(
            json.loads(line) for line in stream if line.strip())


def _discover(root):
    result = {}
    pattern = os.path.join(
        os.path.abspath(root), "games", "main", "e_full_loop", "*",
        "manifest.json")
    for path in sorted(glob.glob(pattern)):
        manifest = _read_json(path)
        seed = int(manifest["seed"])
        if seed in result:
            raise ValueError("duplicate main/e_full_loop seed {}".format(seed))
        run_dir = os.path.dirname(path)
        result[seed] = {
            "events_path": os.path.join(
                run_dir, manifest.get("events_path", "events.jsonl")),
            "manifest": manifest,
            "manifest_path": path,
            "status": _read_json(os.path.join(run_dir, "status.json")),
        }
    return result


def _fdas_flags(manifest):
    declaration = manifest.get("dependent_atomspace", {})
    config = declaration.get("config", {})
    domain_authority = config.get("domain_authority", {})
    return {
        "authority_enabled": config.get("authority_enabled"),
        "domain_authority_enabled": sorted(
            name for name, enabled in domain_authority.items() if enabled),
        "enabled": config.get("enabled"),
        "policy_authority": declaration.get(
            "manifest", {}).get("policy_authority"),
        "shadow_enabled": config.get("shadow_enabled"),
    }


def _behavioral_manifest(manifest):
    """Return fields that must be equal outside the FDAS treatment."""
    keys = (
        "backend", "beliefs", "capabilities", "condition_id",
        "controller_workers", "controller_worker_execution", "engine",
        "engine_finalization_turns", "engine_max_turns", "impact_policy",
        "machine_profile", "model", "model_config", "opponent",
        "pf_pln_controller", "pf_pln_runtime", "release_game_config",
        "rulebase", "ruleset", "seed", "sequence", "track", "turn_limit",
        "engine_shadow_scenario",
    )
    return dict((key, copy.deepcopy(manifest.get(key))) for key in keys)


def _metric_rows(events, name):
    return tuple(
        event for event in events
        if event["type"] == "metric_sample"
        and event["payload"]["name"] == name)


def _metric_values(events, name):
    return tuple(
        float(event["payload"]["value"])
        for event in _metric_rows(events, name))


def _turn_contribution(events):
    values = defaultdict(float)
    for name in (
            "fdas_projection_latency_ms",
            "fdas_shadow_evaluation_latency_ms"):
        for event in _metric_rows(events, name):
            values[int(event["turn"])] += float(event["payload"]["value"])
    return tuple(values[key] for key in sorted(values))


def _action_trace(events):
    return tuple({
        "action": event["payload"]["action"],
        "turn": int(event["turn"]),
    } for event in events if event["type"] == "action_sent")


def _result_trace(events):
    return tuple({
        "status": event["payload"]["status"],
        "turn": int(event["turn"]),
    } for event in events if event["type"] == "action_result")


def _completion(events):
    rows = tuple(event for event in events if event["type"] == "run_completed")
    if len(rows) != 1:
        return None
    summary = rows[0]["payload"]["summary"]
    keys = (
        "actions", "decision_impact_actions", "horizon_reached",
        "meaningful_actions", "opponent_score", "score", "score_lead",
        "score_margin", "terminal_game_over", "terminal_player_elimination",
        "won",
    )
    return dict((key, summary.get(key)) for key in keys)


def _shadow_diagnostics(events):
    decisions = tuple(
        event["payload"]["details"] for event in events
        if event["type"] == "atomspace_shadow_decision")
    comparisons = tuple(
        value["comparison"] for value in decisions
        if value.get("comparison") is not None)
    stage_values = defaultdict(list)
    for decision in decisions:
        for name, value in decision.get("stage_latency_ms", {}).items():
            stage_values[name].append(float(value))
    return {
        "authority_eligible_count": sum(
            bool(value.get("authority_eligible")) for value in decisions),
        "authority_violation_count": sum(
            len(value.get("authority_violations", ()))
            for value in comparisons),
        "decision_count": len(decisions),
        "detail_omission_count": sum(
            int(value.get("omitted_detail_event_count", 0))
            for value in decisions),
        "explained_legacy_count": sum(
            int(value.get("explained_legacy_count", 0))
            for value in comparisons),
        "extra_fdas_count": sum(
            int(value.get("extra_fdas_count", 0)) for value in comparisons),
        "legal_binding_failure_count": sum(
            len(value.get("legal_binding_failures", ()))
            for value in comparisons),
        "missing_legacy_count": sum(
            int(value.get("missing_legacy_count", 0))
            for value in comparisons),
        "safety_downgrade_count": sum(
            len(value.get("safety_downgrades", ()))
            for value in comparisons),
        "stage_latency_ms": dict(
            (name, _latency_summary(values))
            for name, values in sorted(stage_values.items())),
    }


def _mechanism_diagnostics(events):
    bridge = tuple(event for event in events
                   if event["type"] == "bridge_estimated")
    flow = tuple(event for event in events
                 if event["type"] == "flow_projected")
    bridge_nodes = []
    flow_iterations = []
    unhealthy = 0
    fallbacks = tuple(event for event in events
                      if event["type"] == "controller_fallback")
    unexplained_fallbacks = 0
    for event in bridge:
        for row in event["payload"].get(
                "summary", {}).get("goal_summaries", ()):
            bridge_nodes.append(int(row.get("node_count", 0)))
    for event in flow:
        for row in event["payload"].get(
                "summary", {}).get("projections", ()):
            flow_iterations.append(int(row.get("iterations", 0)))
            unhealthy += row.get("health") != "healthy"
    for event in fallbacks:
        summary = event["payload"].get("summary", {})
        reasons = summary.get("gate_reasons", ())
        if not summary.get("reason") and not reasons:
            unexplained_fallbacks += 1
    return {
        "bridge_event_count": len(bridge),
        "controller_fallback_count": len(fallbacks),
        "flow_event_count": len(flow),
        "flow_projection_count": len(flow_iterations),
        "maximum_bridge_nodes": max(bridge_nodes, default=0),
        "maximum_flow_iterations": max(flow_iterations, default=0),
        "unhealthy_flow_projection_count": unhealthy,
        "unexplained_controller_fallback_count": unexplained_fallbacks,
    }


def _volume(events):
    committed = tuple(
        event["payload"]["details"] for event in events
        if event["type"] == "atomspace_revision_committed")
    maximum = {
        "cities": 0, "concurrent_goals": 0, "control_edges": 0,
        "control_nodes": 0, "grounded_candidates": 0,
        "legal_actions": 0, "proof_chain_depth": 0, "proof_tree_size": 0,
        "region_scopes": 0, "units": 0,
    }
    scopes_by_snapshot = defaultdict(lambda: defaultdict(set))
    for event in events:
        payload = event["payload"]
        if event["type"] == "state_snapshot":
            own = payload.get("own_state", {})
            grounded = payload.get("grounded_context", {})
            maximum["cities"] = max(
                maximum["cities"], len(own.get("cities", ())))
            maximum["units"] = max(
                maximum["units"], len(own.get("units", ())))
            maximum["legal_actions"] = max(
                maximum["legal_actions"],
                len(grounded.get("legal_actions", ())))
        elif event["type"] == "scope_materialized":
            details = payload.get("details", {})
            scopes_by_snapshot[payload.get("snapshot_id")][
                details.get("scope_kind")].add(details.get("scope_id"))
        elif event["type"] == "pressure_graph_built":
            details = payload.get("details", {})
            maximum["concurrent_goals"] = max(
                maximum["concurrent_goals"],
                int(details.get("goal_count", 0)))
            maximum["grounded_candidates"] = max(
                maximum["grounded_candidates"],
                int(details.get("candidate_atom_count", 0)))
        elif event["type"] == "pressure_propagated":
            dependency = payload.get("dependency", {})
            nodes = set(dependency)
            edge_count = 0
            for children in dependency.values():
                if not isinstance(children, dict):
                    continue
                nodes.update(children)
                edge_count += len(children)
            maximum["control_nodes"] = max(
                maximum["control_nodes"], len(nodes))
            maximum["control_edges"] = max(
                maximum["control_edges"], edge_count)
        elif event["type"] == "pln_result":
            maximum["proof_chain_depth"] = max(
                maximum["proof_chain_depth"],
                int(payload.get("chain_depth", 0)))
            maximum["proof_tree_size"] = max(
                maximum["proof_tree_size"],
                int(payload.get("tree_size", 0)))
    maximum["region_scopes"] = max((
        len(kinds.get("region", ()))
        for kinds in scopes_by_snapshot.values()), default=0)
    maximum.update({
        "event_count": len(events),
        "maximum_atom_count": max(
            (int(value["atom_count"]) for value in committed), default=0),
        "maximum_scope_count": max(
            (int(value["scope_count"]) for value in committed), default=0),
        "maximum_support_count": max(
            (int(value["support_count"]) for value in committed), default=0),
        "omitted_detail_event_count": sum(
            int(value.get("omitted_detail_event_count", 0))
            for value in committed),
        "revision_count": len(committed),
    })
    return maximum


def _run_evidence(run, events=None):
    events = _read_events(run["events_path"]) if events is None else events
    validation = validate_file(run["events_path"])
    projection_rows = _metric_rows(events, "fdas_projection_latency_ms")
    cold_rows = tuple(
        row for row in projection_rows
        if row["payload"]["labels"].get("cold_verified") == "True")
    cold_failures = tuple(
        row for row in cold_rows
        if row["payload"]["labels"].get("cold_equivalent") != "True")
    return {
        "actions": _action_trace(events),
        "cold_verification_count": len(cold_rows),
        "cold_verification_failure_count": len(cold_failures),
        "completion": _completion(events),
        "controller_latency_ms": _latency_summary(
            _metric_values(events, "turn_full_loop_latency_ms")),
        "controller_process_peak_rss_bytes": int(
            run["status"].get("controller_process_peak_rss_bytes", 0)),
        "event_validation_error_count": len(validation.errors),
        "event_validation_valid": bool(validation.valid),
        "fdas_turn_contribution_ms": _latency_summary(
            _turn_contribution(events)),
        "projection_latency_ms": _latency_summary(
            _metric_values(events, "fdas_projection_latency_ms")),
        "results": _result_trace(events),
        "mechanisms": _mechanism_diagnostics(events),
        "shadow": _shadow_diagnostics(events),
        "shadow_latency_ms": _latency_summary(
            _metric_values(events, "fdas_shadow_evaluation_latency_ms")),
        "volume": _volume(events),
        "support_level": run["manifest"].get(
            "dependent_atomspace", {}).get(
                "config", {}).get("events", {}).get("support_level"),
    }


def audit_fdas_shadow_cohort(control_root, shadow_root, minimum_pairs=3):
    """Return a deterministic paired correctness and performance report."""
    controls = _discover(control_root)
    shadows = _discover(shadow_root)
    failures = []
    if set(controls) != set(shadows):
        failures.append({
            "kind": "seed-set-mismatch",
            "control_only": sorted(set(controls).difference(shadows)),
            "shadow_only": sorted(set(shadows).difference(controls)),
        })
    seeds = sorted(set(controls).intersection(shadows))
    if len(seeds) < int(minimum_pairs):
        failures.append({
            "kind": "insufficient-pairs", "observed": len(seeds),
            "required": int(minimum_pairs),
        })

    pairs = []
    shadow_projection = []
    shadow_readout = []
    shadow_turn = []
    controller = []
    controller_rss = []
    maxima = {
        "atoms": 0, "bridge_nodes": 0, "cities": 0,
        "concurrent_goals": 0, "control_edges": 0, "control_nodes": 0,
        "events": 0, "flow_iterations": 0, "grounded_candidates": 0,
        "legal_actions": 0, "proof_chain_depth": 0,
        "proof_tree_size": 0, "region_scopes": 0, "scopes": 0,
        "supports": 0, "units": 0,
    }
    totals = defaultdict(int)
    declared_scenarios = tuple(
        shadows[seed]["manifest"].get("engine_shadow_scenario")
        for seed in seeds
        if shadows[seed]["manifest"].get("engine_shadow_scenario") is not None)
    scenario = declared_scenarios[0] if declared_scenarios else None
    for seed in seeds:
        control = controls[seed]
        shadow = shadows[seed]
        control_manifest = control["manifest"]
        shadow_manifest = shadow["manifest"]
        control_flags = _fdas_flags(control_manifest)
        shadow_flags = _fdas_flags(shadow_manifest)
        control_events = _read_events(control["events_path"])
        shadow_events = _read_events(shadow["events_path"])
        control_evidence = _run_evidence(control, control_events)
        shadow_evidence = _run_evidence(shadow, shadow_events)
        pair_failures = []
        pair_scenario = shadow_manifest.get("engine_shadow_scenario")
        if scenario is not None and (
                pair_scenario != scenario
                or control_manifest.get("engine_shadow_scenario") != scenario):
            pair_failures.append("engine-shadow-scenario-drift")

        if control["status"].get("status") != "completed" \
                or shadow["status"].get("status") != "completed":
            pair_failures.append("run-not-completed")
        if not control_evidence["event_validation_valid"] \
                or not shadow_evidence["event_validation_valid"]:
            pair_failures.append("event-schema-invalid")
        if control_flags != {
                "authority_enabled": False,
                "domain_authority_enabled": [],
                "enabled": False,
                "policy_authority": False,
                "shadow_enabled": True}:
            pair_failures.append("control-fdas-contract-invalid")
        if shadow_flags != {
                "authority_enabled": False,
                "domain_authority_enabled": [],
                "enabled": True,
                "policy_authority": False,
                "shadow_enabled": True}:
            pair_failures.append("shadow-fdas-contract-invalid")
        control_source = control_manifest.get("source", {})
        shadow_source = shadow_manifest.get("source", {})
        if (control_source.get("dirty") or shadow_source.get("dirty")
                or control_source.get("commit") != shadow_source.get("commit")
                or control_source.get("implementation_sha256")
                != shadow_source.get("implementation_sha256")):
            pair_failures.append("source-identity-mismatch-or-dirty")
        if structural_hash(_behavioral_manifest(control_manifest)) \
                != structural_hash(_behavioral_manifest(shadow_manifest)):
            pair_failures.append("non-fdas-manifest-mismatch")
        if pair_scenario is not None:
            policy = shadow_manifest.get("impact_policy", {})
            expected_release = pair_scenario["release_game_config"]
            if (control_manifest.get("engine_shadow_scenario") != pair_scenario
                    or control_manifest.get("release_game_config")
                    != expected_release
                    or shadow_manifest.get("release_game_config")
                    != expected_release):
                pair_failures.append("engine-shadow-scenario-contract-invalid")
            if (policy.get("pressure_controller_mode")
                    != "unified_flow_advisory"
                    or policy.get("pressure_bridge_enabled") is not True
                    or policy.get("pressure_flow_enabled") is not True
                    or policy.get("pressure_flow_live_enabled", False) is not False):
                pair_failures.append("bridge-flow-shadow-contract-invalid")
        action_match = control_evidence["actions"] == shadow_evidence["actions"]
        result_match = control_evidence["results"] == shadow_evidence["results"]
        completion_match = (
            control_evidence["completion"] == shadow_evidence["completion"])
        if not action_match:
            pair_failures.append("ordered-action-trace-mismatch")
        if not result_match:
            pair_failures.append("action-result-trace-mismatch")
        if not completion_match:
            pair_failures.append("behavioral-completion-mismatch")

        diagnostics = shadow_evidence["shadow"]
        fault_count = sum(diagnostics[name] for name in (
            "authority_eligible_count", "authority_violation_count",
            "detail_omission_count", "legal_binding_failure_count",
            "missing_legacy_count", "safety_downgrade_count"))
        fault_count += shadow_evidence["cold_verification_failure_count"]
        if diagnostics["decision_count"] < 1:
            pair_failures.append("no-shadow-decisions")
        if fault_count:
            pair_failures.append("fdas-correctness-fault")
        if (shadow_evidence["volume"]["omitted_detail_event_count"]
                or control_evidence["volume"]["omitted_detail_event_count"]):
            pair_failures.append("atom-detail-omission")
        if pair_scenario is not None:
            for evidence in (control_evidence, shadow_evidence):
                mechanisms = evidence["mechanisms"]
                if (mechanisms["bridge_event_count"] < 1
                        or mechanisms["flow_event_count"] < 1):
                    pair_failures.append("bridge-flow-shadow-not-exercised")
                    break
                if mechanisms["unhealthy_flow_projection_count"]:
                    pair_failures.append("unhealthy-flow-projection")
                    break
                if mechanisms["unexplained_controller_fallback_count"]:
                    pair_failures.append("unexplained-controller-fallback")
                    break
        budget = shadow_manifest["dependent_atomspace"]["config"][
            "materialization"]["maximum_atoms_global"]
        if shadow_evidence["volume"]["maximum_atom_count"] > int(budget):
            pair_failures.append("atom-budget-exceeded")

        for message in pair_failures:
            failures.append({"kind": message, "seed": seed})
        pairs.append({
            "action_count": len(shadow_evidence["actions"]),
            "action_trace_match": action_match,
            "behavioral_completion_match": completion_match,
            "control": {
                "completion": control_evidence["completion"],
                "event_count": control_evidence["volume"]["event_count"],
                "manifest_identity": control_manifest["manifest_identity"],
            },
            "failures": pair_failures,
            "result_trace_match": result_match,
            "seed": seed,
            "shadow": shadow_evidence,
            "shadow_manifest_identity": shadow_manifest["manifest_identity"],
        })
        shadow_projection.extend(_metric_values(
            shadow_events, "fdas_projection_latency_ms"))
        shadow_readout.extend(_metric_values(
            shadow_events, "fdas_shadow_evaluation_latency_ms"))
        shadow_turn.extend(_turn_contribution(shadow_events))
        controller.extend(_metric_values(
            shadow_events, "turn_full_loop_latency_ms"))
        controller_rss.append(
            shadow_evidence["controller_process_peak_rss_bytes"])
        volume = shadow_evidence["volume"]
        maxima["atoms"] = max(maxima["atoms"], volume["maximum_atom_count"])
        maxima["events"] = max(maxima["events"], volume["event_count"])
        maxima["scopes"] = max(maxima["scopes"], volume["maximum_scope_count"])
        maxima["supports"] = max(
            maxima["supports"], volume["maximum_support_count"])
        for name in (
                "cities", "concurrent_goals", "control_edges",
                "control_nodes", "grounded_candidates", "legal_actions",
                "proof_chain_depth", "proof_tree_size", "region_scopes",
                "units"):
            maxima[name] = max(maxima[name], volume[name])
        mechanisms = shadow_evidence["mechanisms"]
        maxima["bridge_nodes"] = max(
            maxima["bridge_nodes"], mechanisms["maximum_bridge_nodes"])
        maxima["flow_iterations"] = max(
            maxima["flow_iterations"],
            mechanisms["maximum_flow_iterations"])
        totals["cold_verification_count"] += shadow_evidence[
            "cold_verification_count"]
        totals["decision_count"] += diagnostics["decision_count"]
        totals["explained_legacy_count"] += diagnostics[
            "explained_legacy_count"]
        totals["extra_fdas_count"] += diagnostics["extra_fdas_count"]
        totals["revision_count"] += volume["revision_count"]
        totals["bridge_event_count"] += mechanisms["bridge_event_count"]
        totals["controller_fallback_count"] += mechanisms[
            "controller_fallback_count"]
        totals["flow_event_count"] += mechanisms["flow_event_count"]
        totals["flow_projection_count"] += mechanisms[
            "flow_projection_count"]
        totals["full_detail_pair_count"] += (
            shadow_evidence["support_level"] == "all")

    volume_expansion = {}
    if scenario is not None:
        for name, reference in sorted(
                scenario["reference_maximum_volume"].items()):
            achieved = maxima[name]
            volume_expansion[name] = {
                "achieved": achieved,
                "passed": achieved > int(reference),
                "reference": int(reference),
            }
            if achieved <= int(reference):
                failures.append({
                    "achieved": achieved,
                    "kind": "high-entity-volume-not-expanded",
                    "metric": name,
                    "reference": int(reference),
                })
        if totals["full_detail_pair_count"] < 1:
            failures.append({"kind": "full-detail-sample-missing"})
        if sum(value > 0 for value in controller_rss) < len(seeds):
            failures.append({
                "kind": "controller-process-rss-evidence-incomplete",
                "observed": sum(value > 0 for value in controller_rss),
                "required": len(seeds),
            })

    fdas_turn_summary = _latency_summary(shadow_turn)
    controller_summary = _latency_summary(controller)
    latency_targets = {
        "controller_p95_below_500_ms": bool(
            controller_summary["p95_ms"] is not None
            and controller_summary["p95_ms"] < CONTROLLER_P95_TARGET_MS),
        "fdas_turn_p95_at_or_below_150_ms": bool(
            fdas_turn_summary["p95_ms"] is not None
            and fdas_turn_summary["p95_ms"] <= FDAS_TURN_P95_TARGET_MS),
    }
    latency_gate_mode = "report-only" if scenario is not None else "acceptance"
    if latency_gate_mode == "acceptance":
        for name, passed in latency_targets.items():
            if not passed:
                failures.append({
                    "kind": "latency-target-failed", "target": name})
    report = {
        "acceptance": {
            "accepted": not failures,
            "failure_count": len(failures),
            "latency_targets": latency_targets,
            "minimum_pairs": int(minimum_pairs),
        },
        "aggregate": {
            "controller_latency_ms": controller_summary,
            "controller_process_peak_rss_bytes": _byte_summary(
                controller_rss),
            "fdas_projection_latency_ms": _latency_summary(shadow_projection),
            "fdas_shadow_latency_ms": _latency_summary(shadow_readout),
            "fdas_turn_contribution_ms": fdas_turn_summary,
            "maximum_volume": maxima,
            "totals": dict(sorted(totals.items())),
            "volume_expansion": volume_expansion,
        },
        "failures": failures,
        "inputs": {
            "control_root": os.path.abspath(control_root),
            "shadow_root": os.path.abspath(shadow_root),
        },
        "pairs": pairs,
        "engine_shadow_scenario": scenario,
        "schema_version": "fdas-engine-shadow-cohort/1.0",
        "structural_hash": None,
        "thresholds": {
            "controller_p95_ms": CONTROLLER_P95_TARGET_MS,
            "fdas_turn_p95_ms": FDAS_TURN_P95_TARGET_MS,
            "latency_gate_mode": latency_gate_mode,
        },
    }
    report["structural_hash"] = structural_hash(
        dict(report, structural_hash=None))
    return report
