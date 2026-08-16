import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  buildArtifactCatalog,
  loadScalabilityEvidence,
  resolveArtifactEventPath,
} from "../../artifact-server";

const roots: string[] = [];

afterEach(() => {
  while (roots.length > 0) {
    const root = roots.pop();
    if (root) rmSync(root, { force: true, recursive: true });
  }
});

describe("generated artifact catalog", () => {
  it("catalogs active event streams and rejects traversal and archived attempts", () => {
    const repoRoot = mkdtempSync(join(tmpdir(), "freeciv-observability-"));
    roots.push(repoRoot);
    const active = join(
      repoRoot,
      "artifacts/freeciv/impact-terminal/games/impact_pair/diagnostic/baseline/e_full_loop/2146151-00",
    );
    const archived = join(
      repoRoot,
      "artifacts/freeciv/impact-terminal/attempt-history/impact_pair/diagnostic/baseline/e_full_loop/2146151-00/retry",
    );
    mkdirSync(active, { recursive: true });
    mkdirSync(archived, { recursive: true });
    writeFileSync(join(active, "events.jsonl"), "{\"type\":\"run_started\"}\n");
    writeFileSync(join(archived, "events.jsonl"), "{\"type\":\"run_started\"}\n");

    const catalog = buildArtifactCatalog(repoRoot);
    expect(catalog.entries).toHaveLength(1);
    expect(catalog.entries[0]).toMatchObject({
      arm: "baseline",
      cohort: "diagnostic",
      experiment: "impact-terminal",
      run: "2146151-00",
    });
    expect(resolveArtifactEventPath(catalog.entries[0].path, repoRoot))
      .toBe(join(active, "events.jsonl"));
    expect(resolveArtifactEventPath(
      "artifacts/freeciv/../../etc/passwd/events.jsonl", repoRoot,
    )).toBeUndefined();
    expect(resolveArtifactEventPath(
      "artifacts/freeciv/impact-terminal/attempt-history/run/events.jsonl", repoRoot,
    )).toBeUndefined();
  });

  it("loads the fixed scalability evidence bundle without scanning arbitrary paths", () => {
    const repoRoot = mkdtempSync(join(tmpdir(), "freeciv-scalability-"));
    roots.push(repoRoot);
    const campaign = join(repoRoot, "artifacts/freeciv/scalability-v1");
    mkdirSync(join(campaign, "discovery"), { recursive: true });
    for (const [name, value] of Object.entries({
      "aggregate.json": { artifact_type: "freeciv-scalability-report" },
      "audit.json": { valid: true }, "claim-manifest.json": { g9_complete: false },
      "environment.json": { git_commit: "abc" },
      "preregistration.json": { artifact_type: "freeciv-scalability-preregistration" },
    })) writeFileSync(join(campaign, name), JSON.stringify(value));
    writeFileSync(join(campaign, "discovery/trials.json"), JSON.stringify({ results: [{ trial_id: "one" }] }));

    const evidence = loadScalabilityEvidence(repoRoot) as Record<string, unknown>;

    expect(evidence.frozen).toBeNull();
    expect(evidence.heldout).toEqual([]);
    expect(evidence.discovery).toEqual([{ trial_id: "one" }]);
  });
});
