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

describe("Decision Observatory", () => {
  it("opens an action ancestry and reaches the supporting proof in five interactions", async () => {
    const user = userEvent.setup();
    render(<App initialText={demoTrace} />);
    const action = screen.getByRole("button", { name: /1\.7 action sent/ });
    await user.click(action);
    expect(action).toHaveClass("ancestry");
    expect(screen.getByRole("button", { name: /1\.1 llm proposal/ })).toHaveClass("ancestry");
    await user.click(screen.getByRole("button", { name: /Proof explorer/ }));
    expect(screen.getByRole("tree", { name: /AND OR proof tree/ })).toBeInTheDocument();
    await user.click(screen.getByRole("treeitem", { name: /^goal researchable/i }));
    expect(screen.getByText("node-goal")).toBeInTheDocument();
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
  });

  it("fades an uncertain map marker using its logged as-of confidence", async () => {
    const user = userEvent.setup();
    render(<App initialText={decayTrace} />);
    await user.click(screen.getByRole("button", { name: /Map overlay/ }));
    const marker = screen.getByTitle(/confidence 0\.30/);
    expect(marker).toHaveStyle({ opacity: "0.3" });
    expect(screen.getByText(/opacity = logged confidence/)).toBeInTheDocument();
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

  it("renders metric values directly from events", async () => {
    const user = userEvent.setup();
    render(<App initialText={demoTrace} />);
    await user.click(screen.getByRole("button", { name: /^07 Metrics/ }));
    expect(screen.getByText("loop_latency_ms")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText(/UI calculations disabled/)).toBeInTheDocument();
  });

  it("replays PF-PLN goals, scheduling, conductance, activation, and runtime events", async () => {
    const user = userEvent.setup();
    render(<App initialText={pfTrace} />);
    await user.click(screen.getByRole("button", { name: /^08 PF-PLN/ }));
    expect(screen.getByRole("heading", { name: "PF-PLN control path" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "PF-PLN operation schedule" })).toBeInTheDocument();
    expect(screen.getAllByText("expansion").length).toBeGreaterThan(0);
    expect(screen.getByText("◆ selected")).toBeInTheDocument();
    expect(screen.getAllByText("production_expansion").length).toBeGreaterThan(0);
    expect(screen.getByText("effect_without_goal_relief")).toBeInTheDocument();
    expect(screen.getByText("goal_regression_planner")).toBeInTheDocument();
    expect(screen.getByText("impact_planning_pressure_graph_latency_ms")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "inspect event →" }));
    expect(screen.getByRole("heading", { name: "operation_scored" })).toBeInTheDocument();
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
