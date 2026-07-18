import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import demoTrace from "../../../../Autotests/fixtures/freeciv-events/v1/normal-crisp.jsonl?raw";
import decayTrace from "../../../../Autotests/fixtures/freeciv-events/v1/decay-rescout.jsonl?raw";
import invalidationTrace from "../../../../Autotests/fixtures/freeciv-events/v1/invalidation-repair.jsonl?raw";
import quarantineTrace from "../../../../Autotests/fixtures/freeciv-events/v1/quarantine-40.jsonl?raw";
import writeThroughTrace from "../../../../Autotests/fixtures/freeciv-events/v1/bad-write-through.jsonl?raw";
import { App } from "../App";

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
});
