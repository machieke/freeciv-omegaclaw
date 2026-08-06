import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { Scrubber } from "../App";
import { event } from "./helpers";

it("renders a full-telemetry scrubber above the JavaScript argument limit", () => {
  const events = Array.from({ length: 150_000 }, (_, index) => event(
    index + 1,
    "metric_sample",
    { name: "atomspace_detail", value: index },
    Math.floor(index / 300) + 1,
    index % 300,
  ));

  render(<Scrubber events={events} cursor={{ turn: 500, seq: 299 }}
    onChange={() => undefined} />);

  expect(screen.getByRole("slider", { name: "Turn" })).toHaveAttribute("min", "1");
  expect(screen.getByRole("slider", { name: "Turn" })).toHaveAttribute("max", "500");
  expect(screen.getByText("Turn 500")).toBeInTheDocument();
}, 15_000);
