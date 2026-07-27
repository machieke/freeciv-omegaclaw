import { describe, expect, it } from "vitest";

import {
  type ArtifactCatalogEntry, artifactPairQuality, findPairedArtifact,
} from "../artifacts";

const entry = (
  arm: string,
  run = "seed-01",
  condition = "e_full_loop",
): ArtifactCatalogEntry => ({
  arm,
  cohort: "confirmatory",
  condition,
  experiment: "impact-confirmatory",
  label: `impact-confirmatory / ${arm} / ${run}`,
  modifiedAt: "2026-07-27T06:00:00.000Z",
  path: `artifacts/freeciv/impact-confirmatory/${arm}/${run}/events.jsonl`,
  run,
  sizeBytes: 100,
});

describe("artifact pairing", () => {
  it("finds only the opposite arm with an identical experiment, cohort, condition, and seed", () => {
    const treatment = entry("treatment");
    const baseline = entry("baseline");
    expect(findPairedArtifact(treatment, [
      entry("baseline", "seed-02"),
      entry("baseline", "seed-01", "d_no_pf"),
      baseline,
    ])).toEqual(baseline);
    expect(artifactPairQuality(treatment, baseline)).toEqual({
      exact: true,
      label: "exact pair",
      mismatches: [],
    });
  });

  it("reports mismatched keys and same-arm comparisons", () => {
    expect(artifactPairQuality(entry("treatment"), entry("treatment", "seed-02"))).toEqual({
      exact: false,
      label: "pair mismatch",
      mismatches: ["run", "opposite arm"],
    });
    expect(artifactPairQuality()).toEqual({
      exact: false,
      label: "unverified pair",
      mismatches: ["catalog metadata unavailable"],
    });
  });
});
