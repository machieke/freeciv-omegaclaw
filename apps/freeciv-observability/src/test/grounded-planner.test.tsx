import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { GroundedPlannerDashboard } from "../GroundedPlanner";
import { foldEvents } from "../store";
import { event } from "./helpers";

const hash = "a".repeat(64);

const estimate = event(1, "domain_estimate_emitted", {
  request_id: "estimate-request-1", candidate_action_id: hash,
  action_category: "combat_attack", action_type: "unit_attack",
  actor_id: "unit:10", target_id: "unit:20", operation_id: "combat-operation-1",
  context_key: { action_category: "combat_attack", lifecycle_state: "proposed" },
  authority: "deterministic_derived", confidence: 0.92,
  validity: { snapshot_id: "snapshot-4", valid_through_turn: 4 },
  estimator_id: "freeciv-grounded-combat/1.0", estimator_version: "1.0",
  transition: { outcomes: [], unknown_mass: 0.08 },
  expected_relief: { "goal:defence": 3.5 }, adverse_risk: 0.12, latency_ms: 0.41,
  provenance: ["freeciv-server-action-probability"],
}, 4, 1);

const abstention = event(2, "domain_estimate_abstained", {
  request_id: "estimate-request-2", candidate_action_id: "b".repeat(64),
  action_category: "transport_founder", action_type: "unit_move",
  actor_id: "unit:30", target_id: "tile:50", operation_id: "transport-operation-1",
  context_key: { action_category: "transport_founder", lifecycle_state: "proposed" },
  authority: "abstain", confidence: 0,
  validity: { snapshot_id: "snapshot-4", valid_through_turn: 4 },
  estimator_id: "freeciv-grounded-transport/1.0", estimator_version: "1.0",
  transition: { outcomes: [], unknown_mass: 1 }, expected_relief: {},
  adverse_risk: 0, latency_ms: 0.2, provenance: ["authoritative-visible-state"],
  abstention_reason: "missing-native-route", missing_fields: ["movement_route"],
}, 4, 2);

const capacity = event(3, "resource_capacity_changed", {
  event_schema_version: "1.0", capacity_id: "c".repeat(64),
  resource: { kind: "actor", owner_id: "unit:10", scope: "current", subresource: null },
  window: { start_turn: 4, end_turn_exclusive: 5 }, quantity: 1,
  snapshot_id: "snapshot-4", authority: "authoritative-unit-state",
  previous_capacity_id: null, previous_quantity: null, reason: "initial-observation",
  shadow_only: true,
}, 4, 3);

const claim = (index: number, type: string, disposition: string, turn: number) =>
  event(index, type, {
    event_schema_version: "1.0", scheduler_identity: "bounded-exact/1.0",
    schedule_digest: "d".repeat(64), snapshot_id: `snapshot-${turn}`,
    operation_id: "combat-operation-1", claim_id: index.toString(16).padStart(64, "0"),
    resource: { kind: "actor", owner_id: "unit:10", scope: "current", subresource: null },
    window: { start_turn: turn, end_turn_exclusive: turn + 1 }, quantity: 1,
    hardness: "hard_current", exclusive: true, source_step_id: "attack-step-1",
    disposition, reason: null, conflict_resource_ids: [], conflicting_operation_ids: [],
    shadow_only: true,
  }, turn, index);

const schedule = event(7, "resource_schedule_decided", {
  event_schema_version: "1.0", artifact_hash: "e".repeat(64), batch_id: "f".repeat(64),
  schedule_digest: "d".repeat(64), scheduler_identity: "freeciv-bounded-exact/1.0",
  exact_status: "exact", fallback_reason: null,
  selected_operation_ids: ["combat-operation-1"],
  packet_committed_operation_ids: ["combat-operation-1"], packet_exact_selection_equal: true,
  request_count: 1, rejected_operation_count: 0, policy_authority: false, shadow_only: true,
}, 4, 7);

const operationPayload = (state: string, selected = true) => ({
  event_schema_version: "1.0", operation_id: "combat-operation-1",
  operation_digest: "1".repeat(64), operation_type: "attack_then_conditional_attack",
  snapshot_id: "snapshot-4", requirement_id: "requirement-combat-1",
  actor_id: "unit:10", target_id: "unit:20", state, reason_code: null,
  deadline_turn: 6, next_action: { action_type: "unit_attack", actor_id: 10 },
  claims: [{ resource: { kind: "actor", owner_id: "unit:10" } }],
  participants: [{ role: "primary", actor_id: "unit:10" },
    { role: "conditional", actor_id: "unit:11" }],
  expected_prevented_loss: 4, opportunity_cost: 1, bid: 3, selected,
  assignment_digest: "2".repeat(64), policy_authority: false, shadow_only: true,
  provenance: ["grounded-combat"],
});

const proposed = event(8, "operation_proposed", operationPayload("proposed"), 4, 8);
const activated = event(9, "operation_activated", operationPayload("activated"), 5, 1);
const committed = event(10, "operation_step_committed", operationPayload("step_committed"), 5, 2);
const completed = event(11, "operation_completed", {
  ...operationPayload("completed"), resolution_status: "resolved_success",
  resolution_snapshot_id: "snapshot-6",
}, 6, 1);

const state = foldEvents([
  estimate, abstention, capacity,
  claim(4, "resource_claim_requested", "requested", 4),
  claim(5, "resource_claim_reserved", "reserved", 4),
  claim(6, "resource_claim_released", "released", 5),
  schedule, proposed, activated, committed, completed,
], { turn: 6, seq: 1 });

describe("grounded implementation observability", () => {
  it("indexes every grounded event family at the replay cursor", () => {
    expect(state.domainEstimates).toEqual([estimate]);
    expect(state.domainAbstentions).toEqual([abstention]);
    expect(state.resourceCapacities).toEqual([capacity]);
    expect(state.resourceSchedules).toEqual([schedule]);
    expect(state.resourceClaims).toHaveLength(3);
    expect(state.operationEvents).toHaveLength(4);
    expect(state.unknown).toHaveLength(0);
    expect(state.pfPlnEvents).toContain(abstention);
    expect(state.pfPlnEvents.some((row) => row.type === "resource_claim_released")).toBe(true);
  });

  it("renders program gates and trace-only estimate, resource, and lifecycle ledgers", async () => {
    const user = userEvent.setup();
    const inspect = vi.fn();
    render(<GroundedPlannerDashboard state={state} onSelectEvent={inspect} />);

    expect(screen.getByRole("heading", { name: "Grounded planner" })).toBeInTheDocument();
    expect(screen.getByText("Implementation complete")).toBeInTheDocument();
    expect(screen.getByText(/Mechanism and prediction claims only/i)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Grounded implementation stage gates" }))
      .toBeInTheDocument();
    expect(screen.getByText("GDO-9")).toBeInTheDocument();
    expect(screen.getByText("closed · 4/7")).toBeInTheDocument();
    expect(screen.getByText("0 legality · 0 hard reservation · 0 sole-defender violations"))
      .toBeInTheDocument();

    const estimates = screen.getByRole("region", { name: "Grounded transition estimate ledger" });
    expect(within(estimates).getByText("Deterministic Derived")).toBeInTheDocument();
    expect(within(estimates).getByText("Missing Native Route")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Grounded estimate domain"), "transport");
    expect(within(estimates).queryByText("Deterministic Derived")).not.toBeInTheDocument();
    expect(within(estimates).getByText("Missing Native Route")).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "B4 resource scheduler" })).toBeInTheDocument();
    expect(screen.getByText("retained audit · zero hard over-allocation")).toBeInTheDocument();
    await user.click(screen.getByText(/Claim ledger · latest 3/i));
    expect(screen.getByRole("region", { name: "Grounded resource claim ledger" }))
      .toBeInTheDocument();

    const lifecycle = screen.getByRole("region", { name: "Grounded operation lifecycle ledger" });
    expect(within(lifecycle).getByText("Resolved Success")).toBeInTheDocument();
    expect(within(lifecycle).getByText("2 participants · 1 claims")).toBeInTheDocument();
    await user.click(within(lifecycle).getByRole("button", { name: /Resolved Success/i }));
    expect(inspect).toHaveBeenCalledWith(completed);
  });

  it("keeps bridge and flow visibly disabled after grounded calibration", () => {
    render(<GroundedPlannerDashboard state={state} onSelectEvent={() => undefined} />);
    expect(screen.getByRole("heading", { name: "Contextual transition calibration" }))
      .toBeInTheDocument();
    expect(screen.getByText("0.267491")).toBeInTheDocument();
    expect(screen.getByText("0.041237")).toBeInTheDocument();
    expect(screen.getByText("Live bridge and source–sink flow authority disabled"))
      .toBeInTheDocument();
    expect(screen.getAllByText("blocked")).toHaveLength(3);
  });
});
