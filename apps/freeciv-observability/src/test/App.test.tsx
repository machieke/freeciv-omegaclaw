import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import demoTrace from "../../../../Autotests/fixtures/freeciv-events/v1/normal-crisp.jsonl?raw";
import decayTrace from "../../../../Autotests/fixtures/freeciv-events/v1/decay-rescout.jsonl?raw";
import invalidationTrace from "../../../../Autotests/fixtures/freeciv-events/v1/invalidation-repair.jsonl?raw";
import quarantineTrace from "../../../../Autotests/fixtures/freeciv-events/v1/quarantine-40.jsonl?raw";
import writeThroughTrace from "../../../../Autotests/fixtures/freeciv-events/v1/bad-write-through.jsonl?raw";
import { App } from "../App";
import { event } from "./helpers";

const pfHash = "a".repeat(64);
const pfTrace = [
  event(1, "pressure_propagated", {
    pressure_id: "pressure-test",
    graph_hash: pfHash,
    result_hash: "b".repeat(64),
    goals: [
      {
        goal_id: "pf-impact:expansion", utility: 1.25, urgency: 1,
        target_strength: 1, safety: false, context: ["authoritative:city-count-over-target"],
      },
      {
        goal_id: "pf-impact:survival", utility: 1.5, urgency: 1,
        target_strength: 1, safety: true, context: ["authoritative:visible-threat"],
      },
    ],
    dependency: { "pf-impact:expansion": { "pf-impact-goal:expansion": 1 } },
    operational_pressure: {
      "pf-impact:expansion": {
        "pf-impact-category:expansion": {
          act: 0.85, direction: 1, expand: 0, infer: 0, observe: 0, retain: 0,
        },
      },
    },
    traces: [{
      goal_id: "pf-impact:expansion", hop: 1,
      conclusion_id: "pf-impact-goal:expansion",
      premise_id: "pf-impact-category:expansion",
      rule_id: "pf-impact-category-route:production_expansion",
      transported_pressure: 0.85,
    }],
    config: { damping: 0.85 },
    conductance_state: null,
  }, 1, 1),
  event(2, "operation_scored", {
    decision_id: "decision-test",
    pressure_id: "pressure-test",
    solver_identity: "pf-pln-pressure-scheduler/1.0",
    selected_operation_id: "operation-founder",
    scores: [{
      operation: {
        operation_id: "operation-founder", mode: "act",
        payload: {
          category: "production_expansion",
          rationale: "produce the next grounded founder",
          action: { action_type: "city_change_production" },
        },
      },
      admissible: true, priority: 0.84, value: 0.85, reason: null,
    }],
    allocations: [],
    structural_hash: "c".repeat(64),
  }, 1, 2),
  event(3, "conductance_updated", {
    feedback_id: "feedback-test",
    category: "production_expansion",
    rule_id: "pf-impact-category-route:production_expansion",
    effect_observed: true,
    applied: true,
    previous_conductance: 1,
    conductance: 0.9753,
    successes: 1,
    no_progress: 1,
    learning_method: "grounded-goal-relief-ema-v2",
    credit_kind: "effect_without_goal_relief",
    realized_relief: 0,
    no_progress_amount: 0.25,
    state_hash: "d".repeat(64),
  }, 1, 3),
  event(4, "metric_sample", {
    name: "pf_pln_phase_enabled", value: 1, unit: "ratio",
    labels: { phase: "1", component: "goal_regression_planner", reason: "enabled" },
  }, 1, 4),
  event(5, "metric_sample", {
    name: "impact_planning_pressure_graph_latency_ms", value: 1.75, unit: "ms",
    labels: { condition: "e_full_loop" },
  }, 1, 5),
].map((row) => JSON.stringify(row)).join("\n");

const proposedTerminalGuardCandidate = JSON.stringify({
  action_type: "unit_move", actor_id: 102, settlement_site_eligible: true,
  target: { x: 13, y: 14 },
});

it("opens the grounded implementation workspace from primary navigation", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: /^09 Grounded planner/ }));
  expect(screen.getByRole("heading", { name: "Grounded planner" })).toBeInTheDocument();
  expect(screen.getByText(/Program evidence is available below/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Grounded planner authority map" }))
    .toBeInTheDocument();
});
const effectiveTerminalGuardCandidate = JSON.stringify({
  action_type: "unit_build_city", actor_id: 102,
});
const unifiedQueryId = "impact-control-query:terminal-guard-test";
const unifiedPayload = (summary: Record<string, unknown>) => ({
  event_schema_version: "1.0",
  query_id: unifiedQueryId,
  semantic_epoch: 17,
  topology_generation: 42,
  config_digest: "1".repeat(64),
  controller_decision_hash: "2".repeat(64),
  artifact_hash: "3".repeat(64),
  parent_event_ids: [],
  summary,
});
const unifiedTrace = [
  event(101, "teleology_estimated", unifiedPayload({
    typed_advantage_count: 2, goal_count: 1,
  }), 4, 7),
  event(102, "requirement_set_materialized", unifiedPayload({
    requirement_set_count: 1, complete_count: 1,
  }), 4, 8),
  event(103, "bridge_estimated", unifiedPayload({
    goal_summaries: [{
      goal_id: "pf-impact:expansion", bridge_factor_mean: 0.34,
      bridge_factor_max: 0.81, node_count: 12,
    }],
  }), 4, 9),
  event(104, "flow_projected", unifiedPayload({
    projections: [{
      health: "healthy", solver: "diagonal-pcg", iterations: 6,
      balance_residual: 5.37e-11, component_count: 2,
    }],
  }), 4, 10),
  event(105, "packet_reserved", unifiedPayload({
    packet_schedule: {
      conserved: true, integrality_gap: 0,
      reservations: [{ state: "committed" }],
      accounting: {
        action: { consumed: 1, declared: 1, stranded: 0 },
        cpu: { consumed: 1, declared: 64, stranded: 63 },
      },
    },
  }), 4, 11),
  event(106, "flow_candidate_selected", unifiedPayload({
    selected_candidate_key: proposedTerminalGuardCandidate,
    effective_candidate_key: effectiveTerminalGuardCandidate,
    selection_disposition: "guarded-fallback",
    calibrated: false,
    confidence: 0.8935,
    transport_readout: {
      disagrees_with_scalar: true, selected_overlap: 0.0045,
      scalar_selected_operation_id: "operation-build-city",
      selected_operation_id: "operation-move",
      candidate_union: {
        readout_policy: "corrected-probe-union",
        members: [
          { operation_id: "operation-build-city",
            reasons: ["scalar-top-k", "scalar-winner", "terminal-protection"] },
          { operation_id: "operation-move", reasons: ["bridge-recall"] },
        ],
        bridge_added_operation_ids: ["operation-move"],
        terminal_protected_operation_ids: ["operation-build-city"],
        safety_protected_operation_ids: [],
      },
    },
  }), 4, 12),
  event(107, "controller_fallback", unifiedPayload({
    advisory_candidate_key: proposedTerminalGuardCandidate,
    advisory_candidate_terminal: false,
    fallback_candidate_key: effectiveTerminalGuardCandidate,
    fallback_candidate_terminal: true,
    fallback_chain: ["unified_flow_advisory", "scalar_v2"],
    gate_reasons: ["uncalibrated-terminal-action-disagreement"],
    health: "fallback",
  }), 4, 13),
  event(108, "candidate_revalidated", unifiedPayload({
    disposition: "commit",
    execution_authority: false,
    plan_materialization_authorized: true,
    checks: ["authoritative-candidate-membership", "server-legal-action-membership"],
  }), 4, 14),
  event(109, "control_outcome_recorded", unifiedPayload({
    effect_observed: true, realized_relief: 1,
  }), 4, 15),
  event(110, "transition_value_estimated", unifiedPayload({
    abstained_operation_count: 0, all_candidate_support: true,
    authority_active: true, authority_requested: true, gate_reason: null,
    operation_count: 2,
    model: {
      observation_count: 64,
      exact_support: [
        { key: { action_category: "expansion", lifecycle_state: "terminal-completion",
          goal_id: "pf-impact:expansion" }, sample_count: 32 },
        { key: { action_category: "expansion", lifecycle_state: "route-progress",
          goal_id: "pf-impact:expansion" }, sample_count: 32 },
      ],
      configuration: { minimum_samples: 30, maximum_half_width: 0.5 },
    },
  }), 4, 16),
  event(111, "transition_value_updated", unifiedPayload({
    applied: true, sample_count: 33,
    observation: {
      predicted_relief: 0.41, realized_relief: 1,
      relief_source: "authoritative:goal-relief",
    },
  }), 4, 17),
  event(112, "path_persistence_applied", unifiedPayload({
    authority_active: true, reordered: true, fallback_reason: null,
    selected_corridor: "unit:102:expansion:route-progress",
    scalar_corridor: "unit:102:expansion:route-progress",
    priority_regret: 0.01, maximum_priority_regret: 0.05,
    decision: { retained_by_dwell: true, retained_by_hysteresis: false },
  }), 4, 18),
].map((row) => JSON.stringify(row)).join("\n");

const combatOperationTrace = [
  event(0, "state_snapshot", {
    snapshot_id: "combat-snapshot-17",
    player_id: 0,
    state_hash: "4".repeat(64),
    source_seq: 17,
    legal_actions_digest: "5".repeat(64),
    own_state: {},
    uncertain_atoms: [],
    map: {},
    grounded_context: {
      schema_version: "1.3",
      legal_actions: [],
      own_units: [],
      visible_enemy_units: [],
      movement_routes: [],
      map_topology: { wrap_x: false, wrap_y: false },
      combat_probabilities: [
        {
          actor_unit_id: 102, target_unit_id: 0, target_unit_ids: [999],
          target_tile_id: 1982,
          response_source_seq: 17, authority: "freeciv-server-action-probability",
          action_probabilities: [
            { action_name: "attack", status: "bounded", minimum: 140, maximum: 140 },
          ],
        },
        {
          actor_unit_id: 103, target_unit_id: 0, target_unit_ids: [999],
          target_tile_id: 1982,
          response_source_seq: 17, authority: "freeciv-server-action-probability",
          action_probabilities: [
            { action_name: "attack", status: "bounded", minimum: 80, maximum: 100 },
          ],
        },
      ],
    },
  }, 3, 0),
  event(1, "operation_proposed", {
    event_schema_version: "1.0",
    operation_id: "combat-operation-1",
    operation_digest: "6".repeat(64),
    operation_type: "attack_then_conditional_attack",
    snapshot_id: "combat-snapshot-17",
    requirement_id: "requirement-set-combat-1",
    actor_id: "unit:102",
    target_id: "unit:999@tile:1982",
    state: "proposed",
    reason_code: "shadow-schedule-selected-no-policy-authority",
    deadline_turn: 3,
    next_action: { action_type: "unit_attack", actor_id: 102 },
    claims: [{ resource: { kind: "actor", owner_id: "unit:102" } }],
    participants: [
      { role: "primary_attacker", actor_id: "unit:102" },
      { role: "conditional_attacker", actor_id: "unit:103" },
    ],
    requirement_set: {
      requirement_set_id: "requirement-set-combat-1",
      premise_ids: ["actor:102:present", "actor:103:present", "target:999:visible"],
    },
    probability_interval: { lower: 0.7, upper: 1, source: "conditional" },
    step_probability_intervals: [
      { lower: 0.7, upper: 0.7, source: "native" },
      { lower: 0.4, upper: 0.5, source: "native" },
    ],
    expected_prevented_loss: 0,
    opportunity_cost: 0,
    bid: 0.7,
    selected: true,
    assignment_digest: "7".repeat(64),
    policy_authority: false,
    shadow_only: true,
    provenance: ["freeciv-server-action-probability", "shadow-only-gdo5"],
  }, 3, 1),
  event(2, "resource_schedule_decided", {
    event_schema_version: "1.0",
    artifact_hash: "8".repeat(64),
    batch_id: "9".repeat(64),
    schedule_digest: "7".repeat(64),
    scheduler_identity: "freeciv-bounded-exact-resource-scheduler/1.0",
    exact_status: "exact",
    fallback_reason: null,
    selected_operation_ids: ["combat-operation-1"],
    packet_committed_operation_ids: ["combat-operation-1"],
    packet_exact_selection_equal: true,
    request_count: 1,
    rejected_operation_count: 0,
    policy_authority: false,
    shadow_only: true,
  }, 3, 2),
].map((row) => JSON.stringify(row)).join("\n");

const productionMapTrace = [
  event(0, "state_snapshot", {
    snapshot_id: "production-map-snapshot",
    player_id: 0,
    state_hash: "9".repeat(64),
    own_state: {
      cities: [{
        city_id: 103, name: "Roma", owner: 0, tile: 458, x: 16, y: 17, size: 1,
      }],
      units: [{
        unit_id: 104, type: "Settlers", owner: 0, tile: 458, x: 16, y: 17,
        hp: 20, moves_left: 6,
      }],
    },
    uncertain_atoms: [],
    map: {
      width: 26, height: 26, tiles: [], visible_tile_ids: [],
      known_hut_tile_ids: [],
    },
  }, 1, 0),
  event(1, "plan_created", {
    plan: {
      plan_id: "impact-plan-map",
      status: "ACTIVE",
      goal_atom_id: "grounded-impact:expansion_move",
      source_proof_hash: pfHash,
      snapshot_id: "production-map-snapshot",
      feasibility_grade: 1,
      scheduler_cost: 141,
      cost_profile: "grounded-impact-utility",
      ledger: [],
      assumptions: [],
      steps: [{
        step_id: "impact-step-map",
        kind: "engine-action",
        target: {
          action_type: "unit_move", actor_id: 104, target: { x: 15, y: 16 },
        },
        predicted_turn: 1,
        actual_turn: null,
        status: "ACTIVE",
        cost: 0,
        spatial: null,
      }],
    },
  }, 1, 1),
].map((row) => JSON.stringify(row)).join("\n");

const resourceFlowTrace = [
  event(0, "production_state", {
    snapshot_id: "resource-flow-snapshot",
    government: {
      available: true, current_id: 2, current_name: "Monarchy",
      target_id: 2, target_name: "Monarchy", revolution_finishes: -1,
      in_revolution: false, selection_required: false, diagnostic: null,
    },
    economy: {
      available: true, diagnostic: null, gold: 50, gold_per_turn: 2,
      operating_gold_per_turn: -3, capitalization_gold_per_turn: 5,
      city_gold_surplus_per_turn: -2, unit_gold_upkeep: 1,
      gold_upkeep_reserve: 1, gold_upkeep_style: "Mixed",
      tax_rate: 40, science_rate: 50, luxury_rate: 10,
    },
    research_flow: {
      gross_beakers_per_turn: 13, tech_upkeep: 4, net_beakers_per_turn: 9,
    },
    score: {
      own: 42, gap_to_leader: -13,
      leader: { player_id: 1, name: "Vikings", score: 55, is_alive: true },
      opponents: [{ player_id: 1, name: "Vikings", score: 55, is_alive: true }],
    },
    cities: [{
      city_id: 3, name: "Roma", size: 5, food_stock: 12, shield_stock: 4,
      outputs: { food: 10, shield: 8, trade: 6, gold: 2, luxury: 1, science: 5 },
      usage: { food: 8, shield: 1, trade: 0, gold: 4, luxury: 0, science: 0 },
      surplus: { food: 2, shield: 7, trade: 6, gold: -2, luxury: 1, science: 5 },
      target: { kind: 3, value: 7, name: "Factory" }, buildable_count: 18,
      buildings: [{ improvement_id: 7, name: "Library", upkeep: 1 }],
      building_changes: [{
        transition: "completed", improvement_id: 7, name: "Library", upkeep: 1,
      }],
      building_upkeep: 1,
    }],
  }, 10, 1),
].map((row) => JSON.stringify(row)).join("\n");

const decisionOnlyAuditTrace = [
  event(0, "llm_proposal", {
    claims: [],
    goals: [
      {
        arguments: ["player", "Advanced Flight"], goal_id: "goal-live-1",
        predicate: "researchable", target_id: "tech-advanced-flight",
      },
      {
        arguments: ["player", "The Corporation"], goal_id: "goal-live-2",
        predicate: "researchable", target_id: "tech-corporation",
      },
    ],
    model: "qwen3-coder-next:latest",
    prompt_version: "engine-live-constrained/1.0",
    proposal_id: "proposal-model",
  }, 1, 1),
  event(1, "verification", {
    check: "graded_candidate_feasible", claim_id: "goal-live-2",
    evidence_atom_ids: ["evidence-goal"], proposal_id: "proposal-model",
    verdict: "believe", verification_id: "verify-goal",
  }, 1, 2),
  event(2, "verification", {
    check: "active_research_has_no_new_selection_action", claim_id: "goal-live-1",
    evidence_atom_ids: [], proposal_id: "proposal-canonical",
    verdict: "believe", verification_id: "verify-continuation",
  }, 2, 1),
  event(3, "verification", {
    check: "plan_invalid", claim_id: "step-invalid",
    evidence_atom_ids: [], proposal_id: "plan-invalid",
    verdict: "disbelieve", verification_id: "verify-plan",
  }, 2, 2),
  event(4, "metric_sample", {
    name: "confabulation_write_through", unit: "ratio", value: 0,
    labels: { condition: "e_full_loop" },
  }, 2, 3),
].map((row) => JSON.stringify(row)).join("\n");

const fdasPayload = (details: Record<string, unknown>) => ({
  revision_id: "fdas-revision-observable",
  snapshot_id: "snapshot-observable",
  ruleset_digest: "ruleset-observable",
  component_id: "fdas-event-emitter",
  component_version: "1.0",
  structural_hash: "f".repeat(64),
  details,
});
const fdasProjectionSummary = {
  atom_counts_by_authority: { deterministic_derived: 1 },
  atom_counts_by_lifecycle: { active: 1 },
  atom_counts_by_namespace: { derived: 1 },
  atom_counts_by_predicate: { "city-provision-deficit": 1 },
  scope_counts_by_kind: { "city-facts": 1 },
  support_counts_by_derivation: { "city-provision-deficit": 1 },
};
const fdasTrace = [
  event(701, "atomspace_revision_started", fdasPayload({
    build_hash: "1".repeat(64), cold_build: true, prior_revision_id: null,
  }), 8, 0),
  event(702, "projection_batch_applied", fdasPayload({
    atom_count: 1, scope_count: 1, support_count: 1,
    projection_summary: fdasProjectionSummary,
  }), 8, 1),
  event(703, "scope_materialized", fdasPayload({
    atom_count: 1, scope_id: "scope:game:test:player:0:city:17:facts", scope_kind: "city-facts",
    scope: {
      scope_id: "scope:game:test:player:0:city:17:facts", scope_kind: "city-facts",
      parent_scope_ids: ["scope:game:test:player:0:empire"], namespaces: ["authoritative", "derived"],
      root_entities: [{ term_type: "entity", kind: "city", entity_id: "17" }],
    },
  }), 8, 2),
  event(704, "atom_rederived", fdasPayload({
    atom_id: "atom-city-17-deficit", predicate: "city-provision-deficit", reason: "newly-projected",
    record: {
      atom_id: "atom-city-17-deficit", authority: "deterministic_derived", dependency_count: 3,
      key: {
        namespace: "derived", predicate: "city-provision-deficit",
        scope_id: "scope:game:test:player:0:city:17:facts",
        arguments: [{ term_type: "entity", kind: "city", entity_id: "17" }],
      },
      lifecycle: "active", materialization_key: "materialized-city-17",
      provenance_ids: ["snapshot-observable"], support_ids: ["support-city-17"],
      tags: [["domain", "city-stability"]], truth: { crisp: true },
      validity: { snapshot_id: "snapshot-observable", valid_from_turn: 8, valid_through_turn: 8 },
    },
  }), 8, 3),
  event(705, "atom_support_added", fdasPayload({
    derivation_id: "city-provision-deficit", support_id: "support-city-17",
    output_atom_ids: ["atom-city-17-deficit"],
    support: {
      support_id: "support-city-17", derivation_id: "city-provision-deficit",
      derivation_version: "1.0", dependencies: [
        { key: { kind: "snapshot-field", owner_id: "city:17", path: "food_surplus" }, fingerprint: "food" },
      ],
    },
  }), 8, 4),
  event(706, "goal_instantiated", fdasPayload({
    goal_id: "goal-city-17", deficit_atom_id: "atom-city-17-deficit",
    deficit_predicate: "city-provision-deficit", scope_id: "scope:game:test:player:0:city:17:facts",
  }), 8, 5),
  event(707, "atomspace_revision_committed", fdasPayload({
    atom_count: 1, scope_count: 1, support_count: 1, build_hash: "1".repeat(64),
    detail_event_count: 4, omitted_detail_event_count: 0,
    projection_summary: fdasProjectionSummary,
  }), 8, 6),
].map((row) => JSON.stringify(row)).join("\n");
const historicalFdasTrace = [
  event(721, "atomspace_revision_started", fdasPayload({
    build_hash: "2".repeat(64), cold_build: true, prior_revision_id: null,
  }), 9, 0),
  event(722, "projection_batch_applied", fdasPayload({
    atom_count: 2, scope_count: 1, support_count: 2,
  }), 9, 1),
  event(723, "scope_materialized", fdasPayload({
    atom_count: 2, scope_id: "scope:historical:city:17:facts", scope_kind: "city-facts",
  }), 9, 2),
  event(724, "atom_rederived", fdasPayload({
    atom_id: "historical-garrison", predicate: "city-garrison-deficit", reason: "newly-projected",
  }), 9, 3),
  event(725, "atom_rederived", fdasPayload({
    atom_id: "historical-defender", predicate: "unit-persistent-defender", reason: "newly-projected",
  }), 9, 4),
  event(726, "goal_instantiated", fdasPayload({
    deficit_atom_id: "historical-garrison", deficit_predicate: "city-garrison-deficit",
    goal_id: "historical-goal-17", scope_id: "scope:historical:city:17:facts",
  }), 9, 5),
  event(727, "atomspace_revision_committed", fdasPayload({
    atom_count: 2, scope_count: 1, support_count: 2, build_hash: "2".repeat(64),
    detail_event_count: 4, omitted_detail_event_count: 0,
  }), 9, 6),
].map((row) => JSON.stringify(row)).join("\n");

describe("Decision Observatory", () => {
  it("defaults Live mode to the dedicated event-tail port", () => {
    render(<App initialText={demoTrace} />);
    expect(screen.getByRole("textbox", { name: "Live endpoint" }))
      .toHaveValue("ws://127.0.0.1:18765");
  });

  it("renders the functional dependent AtomSpace as the primary AtomSpace surface", async () => {
    const user = userEvent.setup();
    render(<App initialText={fdasTrace} />);
    await user.click(screen.getByRole("button", { name: /^03 Atomspace/ }));
    expect(screen.getByRole("heading", { name: "Extended AtomSpace" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "FDAS current revision" }))
      .toHaveTextContent("fdas-revision-observable");
    expect(screen.getByRole("region", { name: "FDAS namespace and authority distribution" }))
      .toHaveTextContent("Deterministic Derived");
    expect(screen.getByRole("region", { name: "FDAS scope topology" }))
      .toHaveTextContent("city-facts");
    const table = screen.getByRole("table", { name: "Extended AtomSpace records" });
    expect(within(table).getByText("city-provision-deficit")).toBeInTheDocument();
    expect(within(table).getByText("city:17")).toBeInTheDocument();
    expect(within(table).getByText("1 / 3")).toBeInTheDocument();
    await user.click(within(table).getAllByRole("row")[1]);
    expect(screen.getByRole("heading", { name: "atom_rederived" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Legacy projection/ }));
    expect(screen.getByRole("heading", { name: "Atomspace inspector" })).toBeInTheDocument();
  });

  it("renders historical identity-only FDAS traces without repetitive unavailable cells", async () => {
    const user = userEvent.setup();
    render(<App initialText={historicalFdasTrace} />);
    await user.click(screen.getByRole("button", { name: /^03 Atomspace/ }));
    expect(screen.getByRole("status")).toHaveTextContent("Historical identity telemetry");
    expect(screen.getByRole("heading", { name: "Current predicates" })).toBeInTheDocument();
    expect(screen.getByText("goal-linked atoms").parentElement).toHaveTextContent("1");
    expect(screen.getByRole("region", { name: "FDAS scope topology" }))
      .toHaveTextContent("materialized at T9.2");
    const table = screen.getByRole("table", { name: "Historical FDAS atom lifecycle records" });
    expect(within(table).getByText("city-garrison-deficit")).toBeInTheDocument();
    expect(within(table).getByText("historical-goal-17")).toBeInTheDocument();
    expect(table).not.toHaveTextContent("detail unavailable");
    expect(screen.queryByRole("combobox", { name: "FDAS namespace" })).not.toBeInTheDocument();
  });

  it("shows authoritative resource flow, score gap, research upkeep, and buildings", async () => {
    const user = userEvent.setup();
    render(<App initialText={resourceFlowTrace} />);
    await user.click(screen.getByRole("button", { name: /^11 Economy & production/ }));
    expect(screen.getByText("operating flow")).toBeInTheDocument();
    expect(screen.getByText("Coinage conversion")).toBeInTheDocument();
    expect(screen.getByText(/-13 to leader/)).toBeInTheDocument();
    expect(screen.getByText(/13 gross/)).toBeInTheDocument();
    expect(screen.getAllByText("Library")).toHaveLength(2);
    expect(screen.getAllByText(/10 produced · 8 consumed/)).toHaveLength(2);
  });

  it("opens an action ancestry and reaches the supporting proof in five interactions", async () => {
    const user = userEvent.setup();
    render(<App initialText={demoTrace} />);
    const action = screen.getByRole("button", { name: /1\.7 action sent/ });
    await user.click(action);
    expect(action).toHaveClass("ancestry");
    expect(screen.getByRole("button", { name: /1\.1 llm proposal/ })).toHaveClass("ancestry");
    await user.click(screen.getByRole("button", { name: /Proof explorer/ }));
    expect(screen.getByRole("tree", { name: /AND OR proof tree/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Proof dependency graph" })).toBeInTheDocument();
    await user.click(screen.getByRole("treeitem", { name: /^goal researchable/i }));
    expect(screen.getByText("node-goal")).toBeInTheDocument();
  });

  it("provides a turn activity matrix, focus mode, and collapsible inspector", async () => {
    const user = userEvent.setup();
    const { container } = render(<App initialText={demoTrace} />);
    expect(screen.getByRole("grid", {
      name: "Decision activity by turn and control stage",
    })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "focus" }));
    expect(container.querySelector(".workspace")).toHaveClass("focus-mode");
    await user.click(screen.getByRole("button", { name: "Close inspector" }));
    expect(container.querySelector(".workspace")).toHaveClass("inspector-closed");
    expect(screen.queryByRole("button", { name: "Close inspector" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "inspector" }));
    expect(screen.getByRole("button", { name: "Close inspector" })).toBeInTheDocument();
  });

  it("explains the evidence pipeline, trust boundary, and routes users to an answer", async () => {
    const user = userEvent.setup();
    render(<App initialText={demoTrace} />);
    await user.click(screen.getByRole("button", { name: /^13 How it works/ }));
    expect(screen.getByRole("heading", {
      name: "See the decision, not just the outcome.",
    })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Evidence pipeline" })).toBeInTheDocument();
    expect(screen.getByText("Observe what was emitted.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How the extended graph stays inspectable" }))
      .toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Extended AtomSpace pipeline" }))
      .toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How PF-PLN is applied" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "PF-PLN application stages" }))
      .toBeInTheDocument();
    expect(screen.getByRole("region", { name: "PF-PLN emitted event chain" }))
      .toBeInTheDocument();
    expect(screen.getByRole("heading", {
      name: "How pressure becomes bridge, flow, and a guarded choice",
    })).toBeInTheDocument();
    expect(screen.getByRole("region", {
      name: "Unified pressure bridge flow emitted event chain",
    })).toBeInTheDocument();
    expect(screen.getByText("Pressure is not belief.")).toBeInTheDocument();
    expect(screen.getByText("Safety is not a soft weight.")).toBeInTheDocument();
    expect(screen.getByText(/Statistical reliability still comes from paired seeds/))
      .toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Can I trust the trace\?/ }));
    expect(screen.getByRole("heading", { name: "Epistemic audit" })).toBeInTheDocument();
  });

  it("restores deep-linked cursor, view, filters, and selection", () => {
    window.history.replaceState(null, "", "/?view=proofs&turn=1&seq=4&selected=node-premise");
    render(<App initialText={demoTrace} />);
    expect(screen.getByRole("heading", { name: "Proof explorer" })).toBeInTheDocument();
    expect(screen.getByText("node-premise")).toBeInTheDocument();
    expect(screen.getByText("T1.4")).toBeInTheDocument();
  });

  it("does not expose future proof state when scrubbed before its event", async () => {
    const user = userEvent.setup();
    render(<App initialText={demoTrace} />);
    await user.click(screen.getByRole("button", { name: /Turn 1, 10 events/ }));
    await user.click(screen.getByRole("button", { name: /Proof explorer/ }));
    expect(screen.getByRole("tree")).toBeInTheDocument();
    const slider = screen.getByRole("slider", { name: "Turn" });
    fireEvent.change(slider, { target: { value: "0" } });
    expect(screen.getByText("No proof trace at this cursor")).toBeInTheDocument();
  });

  it("shows logging gaps instead of reconstructing missing view data", async () => {
    const user = userEvent.setup();
    render(<App initialText={demoTrace.split("\n")[0]} />);
    await user.click(screen.getByRole("button", { name: /Map overlay/ }));
    expect(screen.getByText("logging gap")).toBeInTheDocument();
    expect(screen.getByText(/never infers tiles or paths/)).toBeInTheDocument();
  });

  it("renders exact plan invalidation cause, ETA, and subtree locality", async () => {
    const user = userEvent.setup();
    render(<App initialText={invalidationTrace} />);
    await user.click(screen.getByRole("button", { name: /Plan board/ }));
    expect(screen.getByText("broken: chokepoint-clear")).toBeInTheDocument();
    expect(screen.getByText(/reused 1 · re-derived 1/)).toBeInTheDocument();
    expect(screen.getByText("pred T3")).toBeInTheDocument();
    expect(screen.getAllByText("actual —")).toHaveLength(2);
    expect(screen.getByRole("region", {
      name: "Plan dependency and timing chart",
    })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Plan timing window" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Map overlay/ }));
    expect(screen.getByRole("img", { name: /Logged path for goal-expand/ })).toBeInTheDocument();
  });

  it("fades an uncertain map marker using its logged as-of confidence", async () => {
    const user = userEvent.setup();
    render(<App initialText={decayTrace} />);
    await user.click(screen.getByRole("button", { name: /Map overlay/ }));
    const marker = screen.getByTitle(/confidence 0\.30/);
    expect(marker).toHaveStyle({ opacity: "0.3" });
    expect(screen.getByText(/opacity = logged confidence/)).toBeInTheDocument();
  });

  it("salvages production map traces with entity positions and nested action targets", async () => {
    const user = userEvent.setup();
    const { container } = render(<App initialText={productionMapTrace} />);
    await user.click(screen.getByRole("button", { name: /Map overlay/ }));
    expect(screen.getByRole("status", { name: "Map data coverage" })).toHaveTextContent(
      "Terrain was not emitted in this trace");
    expect(screen.getByText(/26×26 map · 1 cities · 1 units · 1 selected targets/))
      .toBeInTheDocument();
    expect(container.querySelectorAll(".map-tile")).toHaveLength(26 * 26);
    expect(screen.getByRole("region", {
      name: "Map entity and target navigator",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Focus City Roma at 16,17",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Focus Unit Settlers at 16,17",
    })).toBeInTheDocument();
    const overview = screen.getByRole("button", {
      name: "Map viewport overview. Click to pan",
    });
    expect(overview).toBeInTheDocument();
    expect(overview.querySelectorAll(".map-overview-marker")).toHaveLength(2);
    expect(overview.querySelectorAll(".map-overview-target")).toHaveLength(1);
    await user.click(screen.getByRole("button", {
      name: "Set map zoom to 2×",
    }));
    expect(container.querySelector(".map-canvas")).toHaveStyle({ width: "200%" });
    expect(screen.getByTitle("City Roma")).toBeInTheDocument();
    expect(screen.getByTitle("Unit Settlers")).toBeInTheDocument();
    expect(screen.getByRole("img", {
      name: "Logged path for grounded-impact:expansion_move",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tile 15,16/ })).toHaveClass("planned");
    await user.click(screen.getByRole("button", {
      name: "Focus action target 1 at 15,16",
    }));
    expect(screen.getByRole("heading", { name: "engine-action" })).toBeInTheDocument();
    const targetTile = screen.getByRole("button", { name: /Tile 15,16/ });
    expect(targetTile).toHaveClass("selected");
    expect(targetTile).toHaveAttribute("aria-pressed", "true");
    expect(overview.querySelector(".map-overview-selection")).toHaveAttribute("cx", "15.5");
    expect(overview.querySelector(".map-overview-selection")).toHaveAttribute("cy", "16.5");
    expect(screen.getByLabelText("Selected map coordinate")).toHaveTextContent(
      "15,16terrainnot loggedevidenceposition onlyentitiesnonetargetEngine Action");
    fireEvent.keyDown(targetTile, { key: "ArrowRight" });
    const adjacentTile = screen.getByRole("button", { name: /^Tile 16,16/ });
    expect(adjacentTile).toHaveFocus();
    expect(adjacentTile).toHaveClass("selected");
    expect(screen.getByLabelText("Selected map coordinate")).toHaveTextContent(
      "16,16terrainnot loggedevidenceposition onlyentitiesnonetargetnone");
    await user.click(screen.getByRole("button", {
      name: /Tile 16,17, City Roma, Unit Settlers/,
    }));
    expect(screen.getByRole("heading", { name: "state_snapshot" })).toBeInTheDocument();
    expect(screen.getByLabelText("Selected map coordinate")).toHaveTextContent(
      "16,17terrainnot loggedevidenceposition onlyentitiesCity Roma, Unit Settlerstargetnone");
  });

  it("renders all 40 quarantines and makes nonzero write-through loud", async () => {
    const user = userEvent.setup();
    const { container, unmount } = render(<App initialText={quarantineTrace} />);
    await user.click(screen.getByRole("button", { name: /Epistemic audit/ }));
    expect(container.querySelectorAll(".quarantine-row:not(.head)")).toHaveLength(40);
    expect(container.querySelector(".write-through.clear strong")).toHaveTextContent("0");
    unmount();
    render(<App initialText={writeThroughTrace} />);
    await user.click(screen.getByRole("button", { name: /Epistemic audit/ }));
    expect(document.querySelector(".write-through.alarm strong")).toHaveTextContent("1");
  });

  it("separates zero-claim proposals from non-claim decision checks", async () => {
    const user = userEvent.setup();
    render(<App initialText={decisionOnlyAuditTrace} />);
    await user.click(screen.getByRole("button", { name: /Epistemic audit/ }));
    expect(screen.getByRole("region", { name: "Claim audit scope" })).toHaveTextContent(
      "No claims emitted1 model proposal · 2 goals");
    const funnel = screen.getByLabelText("Claim verification funnel");
    expect(within(funnel).getByLabelText("Proposed claims")).toHaveTextContent("0");
    expect(within(funnel).getByLabelText("Claim checks")).toHaveTextContent("0");
    expect(within(funnel).getByLabelText("Quarantined claims")).toHaveTextContent("0");
    expect(within(funnel).getByLabelText("write-through ratio")).toHaveTextContent("0%");
    const decisionChecks = screen.getByRole("region", {
      name: "Non-claim decision checks",
    });
    expect(decisionChecks).toHaveTextContent("3 checks");
    expect(decisionChecks).toHaveTextContent("2 believe");
    expect(decisionChecks).toHaveTextContent("1 disbelieve");
    expect(within(decisionChecks).getByRole("button", {
      name: "Inspect latest active_research_has_no_new_selection_action decision check",
    })).toBeInTheDocument();
    expect(screen.queryByText(/^verified$/i)).not.toBeInTheDocument();
  });

  it("renders metric values directly from events", async () => {
    const user = userEvent.setup();
    render(<App initialText={demoTrace} />);
    await user.click(screen.getByRole("button", { name: /^07 Metrics/ }));
    expect(screen.getByText("loop_latency_ms")).toBeInTheDocument();
    expect(screen.getAllByText("10").length).toBeGreaterThan(0);
    expect(screen.getByText(/UI calculations disabled/)).toBeInTheDocument();
  });

  it("replays PF-PLN goals, scheduling, conductance, activation, and runtime events", async () => {
    const user = userEvent.setup();
    render(<App initialText={pfTrace} />);
    await user.click(screen.getByRole("button", { name: /^08 PF-PLN/ }));
    expect(screen.getByRole("heading", { name: "PF-PLN control path" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "PF-PLN operation schedule" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "PF-PLN pressure flow graph" })).toBeInTheDocument();
    expect(screen.getByLabelText("PF-PLN candidate ranking chart")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Conductance trends" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Runtime composition" })).toBeInTheDocument();
    expect(screen.getAllByText("expansion").length).toBeGreaterThan(0);
    expect(screen.getByText("◆ selected")).toBeInTheDocument();
    expect(screen.getAllByText("production_expansion").length).toBeGreaterThan(0);
    expect(screen.getByText("effect_without_goal_relief")).toBeInTheDocument();
    expect(screen.getByText("goal_regression_planner")).toBeInTheDocument();
    expect(screen.getByText("impact_planning_pressure_graph_latency_ms")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "inspect event →" }));
    expect(screen.getByRole("heading", { name: "operation_scored" })).toBeInTheDocument();
  });

  it("shows unified bridge-flow status, health, and proposed-versus-effective authority", async () => {
    const user = userEvent.setup();
    render(<App initialText={unifiedTrace} />);
    await user.click(screen.getByRole("button", { name: /^08 PF-PLN/ }));
    expect(screen.getByRole("heading", {
      name: "Unified pressure · bridge · flow authority",
    })).toBeInTheDocument();
    expect(screen.getByText("Live authority stopped")).toBeInTheDocument();
    expect(screen.getByText("No score, gameplay, score-lead, or win-rate claim"))
      .toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Unified PF-PLN stage gates" }))
      .toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Unified controller telemetry" }))
      .toBeInTheDocument();
    expect(screen.getByLabelText("Calibrated readout research gates"))
      .toHaveTextContent("calibrated scalarauthority");
    expect(screen.getByRole("heading", { name: "Transition calibration" }))
      .toBeInTheDocument();
    expect(screen.getByText("64")).toBeInTheDocument();
    expect(screen.getByText(/predicted 0.41.*realized 1/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Protected candidate union" }))
      .toBeInTheDocument();
    expect(screen.getByText("Corrected Probe Union")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Path persistence" }))
      .toBeInTheDocument();
    expect(screen.getByText("minimum dwell")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Unified flow decision ledger" }))
      .toBeInTheDocument();
    expect(screen.getByText("Unit Move")).toBeInTheDocument();
    expect(screen.getByText("Unit Build City")).toBeInTheDocument();
    expect(screen.getByText(/terminal retained/i)).toBeInTheDocument();
    expect(screen.getByText(/guard changed authority/i)).toBeInTheDocument();
    expect(screen.getByText("Uncalibrated Terminal Action Disagreement")).toBeInTheDocument();
    expect(screen.getAllByText("1/1", { selector: ".pf-unified-health strong" }).length)
      .toBeGreaterThanOrEqual(3);
    await user.click(screen.getByRole("row", { name: /guard changed authority/i }));
    expect(screen.getByRole("heading", { name: "flow_candidate_selected" }))
      .toBeInTheDocument();
  });

  it("renders native combat intervals and atomic shadow operations without implying authority",
    async () => {
      const user = userEvent.setup();
      render(<App initialText={combatOperationTrace} />);
      await user.click(screen.getByRole("button", { name: /^08 PF-PLN/ }));
      expect(screen.getByRole("heading", {
        name: "Native combat operation laboratory",
      })).toBeInTheDocument();
      expect(screen.getByText("shadow only · no policy authority")).toBeInTheDocument();
      expect(screen.getByRole("table", {
        name: "Native FreeCiv combat probability intervals",
      })).toBeInTheDocument();
      const oddsTable = screen.getByRole("table", {
        name: "Native FreeCiv combat probability intervals",
      });
      expect(within(oddsTable).getAllByText("unit:999")).toHaveLength(2);
      expect(within(oddsTable).queryByText("unit:0")).not.toBeInTheDocument();
      expect(screen.getByRole("table", {
        name: "Atomic combat operation candidates",
      })).toBeInTheDocument();
      expect(screen.getByText("70.0% – 70.0%")).toBeInTheDocument();
      expect(screen.getByText("◆ selected")).toBeInTheDocument();
      expect(screen.getByText("3 / 3")).toBeInTheDocument();
      await user.click(screen.getByText("◆ selected"));
      expect(screen.getByRole("heading", { name: "operation_proposed" }))
        .toBeInTheDocument();
    });

  it("loads a second artifact as a turn-aligned PF-PLN comparison", async () => {
    const user = userEvent.setup();
    const comparisonText = pfTrace.replaceAll("production_expansion", "defense")
      .replaceAll("city_change_production", "unit_move");
    const comparisonEntry = {
      arm: "baseline",
      cohort: "confirmatory",
      condition: "e_full_loop",
      experiment: "pf-paired-test",
      label: "pf-paired-test / baseline / seed-01",
      modifiedAt: "2026-07-27T06:00:00.000Z",
      path: "artifacts/freeciv/pf-paired-test/baseline/seed-01/events.jsonl",
      run: "seed-01",
      sizeBytes: comparisonText.length,
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/freeciv-artifacts") {
        return new Response(JSON.stringify({ entries: [comparisonEntry] }), {
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(comparisonText, {
        headers: { "Content-Type": "application/x-ndjson" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      render(<App initialText={pfTrace} />);
      await user.click(screen.getByRole("button", { name: /Experiment traces/ }));
      const dialog = await screen.findByRole("dialog", { name: "Experiment traces" });
      await user.click(within(dialog).getByRole("button", { name: /Compare pf-paired-test/ }));
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(screen.getByText("paired comparison")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: /^08 PF-PLN/ }));
      expect(screen.getByText("decision diverged")).toBeInTheDocument();
      expect(screen.getByText(/turn-aligned descriptive comparison/i, {
        selector: ".eyebrow",
      })).toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("opens an exact seed/condition counterpart pair in one action", async () => {
    const user = userEvent.setup();
    const primary = {
      arm: "treatment",
      cohort: "confirmatory",
      condition: "e_full_loop",
      experiment: "pf-paired-test",
      label: "pf-paired-test / treatment / seed-01",
      modifiedAt: "2026-07-27T06:00:00.000Z",
      path: "artifacts/freeciv/pf-paired-test/treatment/seed-01/events.jsonl",
      run: "seed-01",
      sizeBytes: pfTrace.length,
    };
    const counterpart = {
      ...primary,
      arm: "baseline",
      label: "pf-paired-test / baseline / seed-01",
      path: "artifacts/freeciv/pf-paired-test/baseline/seed-01/events.jsonl",
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/freeciv-artifacts") {
        return new Response(JSON.stringify({ entries: [primary, counterpart] }), {
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(url.includes("baseline")
        ? pfTrace.replaceAll("production_expansion", "defense")
        : pfTrace, { headers: { "Content-Type": "application/x-ndjson" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      render(<App initialText={demoTrace} />);
      await user.click(screen.getByRole("button", { name: /Experiment traces/ }));
      const dialog = await screen.findByRole("dialog", { name: "Experiment traces" });
      await user.click(within(dialog).getByRole("button", {
        name: `Open exact pair for ${counterpart.label}`,
      }));
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(screen.getByText("exact pair")).toBeInTheDocument();
      expect(screen.getByTitle(primary.label)).toBeInTheDocument();
      expect(fetchMock).toHaveBeenCalledTimes(3);
      await user.click(screen.getByRole("button", { name: /^08 PF-PLN/ }));
      expect(screen.getAllByText("exact pair")).toHaveLength(2);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("filters and loads a generated experiment trace from the repository catalog", async () => {
    const user = userEvent.setup();
    const artifactText = demoTrace.split("\n").filter(Boolean).map((line) => {
      const event = JSON.parse(line) as Record<string, unknown>;
      event.game_id = "artifact-selected-game";
      return JSON.stringify(event);
    }).join("\n");
    const terminal = {
      arm: "baseline",
      cohort: "diagnostic_terminal_elimination_v1",
      condition: "e_full_loop",
      experiment: "impact-terminal-elimination-v1-engine",
      label: "impact-terminal-elimination-v1-engine / baseline / 2146151-00",
      modifiedAt: "2026-07-23T10:57:39.000Z",
      path: "artifacts/freeciv/terminal/games/impact_pair/diagnostic/baseline/e_full_loop/2146151-00/events.jsonl",
      run: "2146151-00",
      sizeBytes: artifactText.length,
    };
    const unrelated = {
      ...terminal,
      experiment: "impact-confirmatory-v4",
      label: "impact-confirmatory-v4 / treatment / 2199160-00",
      path: "artifacts/freeciv/v4/games/impact_pair/confirmatory/treatment/e_full_loop/2199160-00/events.jsonl",
      run: "2199160-00",
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/freeciv-artifacts") {
        return new Response(JSON.stringify({
          entries: [terminal, unrelated],
          generatedAt: "2026-07-23T11:00:00.000Z",
          root: "artifacts/freeciv",
        }), { headers: { "Content-Type": "application/json" } });
      }
      if (url.startsWith("/api/freeciv-artifacts/events?path=")) {
        return new Response(artifactText, {
          headers: { "Content-Type": "application/x-ndjson" },
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      const { container } = render(<App initialText={demoTrace} />);
      await user.click(screen.getByRole("button", { name: /Experiment traces/ }));
      const dialog = await screen.findByRole("dialog", { name: "Experiment traces" });
      expect(within(dialog).getByText(/2 active traces/)).toBeInTheDocument();
      await user.type(within(dialog).getByRole("textbox", {
        name: "Filter experiment traces",
      }), "2146151");
      expect(within(dialog).getByRole("button", {
        name: /Load impact-terminal-elimination-v1-engine/,
      })).toBeInTheDocument();
      expect(within(dialog).queryByText("impact-confirmatory-v4")).not.toBeInTheDocument();
      await user.click(within(dialog).getByRole("button", {
        name: /Load impact-terminal-elimination-v1-engine/,
      }));
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      const topbar = container.querySelector(".topbar");
      expect(topbar).not.toBeNull();
      expect(within(topbar as HTMLElement).getByText("artifact-selected-game")).toBeInTheDocument();
      expect(screen.getByTitle(terminal.label)).toBeInTheDocument();
      expect(fetchMock).toHaveBeenCalledTimes(2);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
