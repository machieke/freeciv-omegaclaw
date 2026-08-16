import { createReadStream, readFileSync, readdirSync, realpathSync, statSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import type { Plugin } from "vite";

import type { ArtifactCatalogEntry, ArtifactCatalogResponse } from "./src/artifacts";

const appRoot = dirname(fileURLToPath(import.meta.url));
export const defaultRepoRoot = resolve(appRoot, "../..");

const posixPath = (value: string): string => value.split(sep).join("/");

const traceIdentity = (relativePath: string): Omit<
  ArtifactCatalogEntry, "modifiedAt" | "path" | "sizeBytes"
> => {
  const parts = relativePath.split("/");
  const experiment = parts[2] ?? "freeciv";
  const games = parts.indexOf("games");
  const track = games >= 0 ? parts[games + 1] : undefined;
  let cohort: string | undefined;
  let arm: string | undefined;
  let condition: string | undefined;
  let run = parts.at(-2) ?? "events";
  if (track === "impact_pair") {
    cohort = parts[games + 2];
    arm = parts[games + 3];
    condition = parts[games + 4];
    run = parts[games + 5] ?? run;
  } else if (games >= 0) {
    condition = parts[games + 2];
    run = parts[games + 3] ?? run;
  }
  const detail = [arm, run].filter(Boolean).join(" / ");
  return {
    arm,
    cohort,
    condition,
    experiment,
    label: detail ? `${experiment} / ${detail}` : `${experiment} / ${run}`,
    run,
  };
};

export function buildArtifactCatalog(repoRoot = defaultRepoRoot): ArtifactCatalogResponse {
  const artifactRoot = resolve(repoRoot, "artifacts/freeciv");
  const entries: ArtifactCatalogEntry[] = [];
  const pending = [artifactRoot];
  while (pending.length > 0) {
    const directory = pending.pop();
    if (!directory) continue;
    let children;
    try {
      children = readdirSync(directory, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const child of children) {
      if (child.isSymbolicLink()) continue;
      const path = resolve(directory, child.name);
      if (child.isDirectory()) {
        if (child.name !== "attempt-history") pending.push(path);
        continue;
      }
      if (!child.isFile() || child.name !== "events.jsonl") continue;
      const relativePath = posixPath(relative(repoRoot, path));
      const stats = statSync(path);
      entries.push({
        ...traceIdentity(relativePath),
        modifiedAt: stats.mtime.toISOString(),
        path: relativePath,
        sizeBytes: stats.size,
      });
    }
  }
  entries.sort((left, right) =>
    right.modifiedAt.localeCompare(left.modifiedAt) || left.path.localeCompare(right.path));
  return {
    entries,
    generatedAt: new Date().toISOString(),
    root: "artifacts/freeciv",
  };
}

export function resolveArtifactEventPath(
  requestedPath: string,
  repoRoot = defaultRepoRoot,
): string | undefined {
  const normalized = requestedPath.replaceAll("\\", "/");
  const segments = normalized.split("/");
  if (
    !normalized.startsWith("artifacts/freeciv/")
    || !normalized.endsWith("/events.jsonl")
    || segments.includes("..")
    || segments.includes("attempt-history")
  ) return undefined;
  const artifactRoot = resolve(repoRoot, "artifacts/freeciv");
  const candidate = resolve(repoRoot, normalized);
  const relativeCandidate = relative(artifactRoot, candidate);
  if (relativeCandidate.startsWith("..") || isAbsolute(relativeCandidate)) return undefined;
  try {
    const realRoot = realpathSync(artifactRoot);
    const realCandidate = realpathSync(candidate);
    const realRelative = relative(realRoot, realCandidate);
    if (realRelative.startsWith("..") || isAbsolute(realRelative)) return undefined;
    if (!statSync(realCandidate).isFile()) return undefined;
    return realCandidate;
  } catch {
    return undefined;
  }
}

const json = (response: ServerResponse, status: number, body: unknown): void => {
  response.statusCode = status;
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.end(JSON.stringify(body));
};

export function loadScalabilityEvidence(repoRoot = defaultRepoRoot): unknown {
  const root = resolve(repoRoot, "artifacts/freeciv/scalability-v1");
  const read = (name: string, optional = false): unknown => {
    try { return JSON.parse(readFileSync(resolve(root, name), "utf-8")); }
    catch (error) { if (optional) return null; throw error; }
  };
  const trialRows = (phase: "discovery" | "heldout"): unknown[] => {
    const material = read(`${phase}/trials.json`, true) as { results?: unknown[] } | null;
    return material?.results ?? [];
  };
  return {
    aggregate: read("aggregate.json"), audit: read("audit.json"),
    claims: read("claim-manifest.json"), discovery: trialRows("discovery"),
    environment: read("environment.json"),
    frozen: read("frozen-preregistration.json", true), heldout: trialRows("heldout"),
    preregistration: read("preregistration.json"),
  };
}

export function artifactRequestHandler(
  request: IncomingMessage,
  response: ServerResponse,
  repoRoot = defaultRepoRoot,
): boolean {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (url.pathname === "/api/freeciv-scalability") {
    if (request.method !== "GET") {
      json(response, 405, { error: "Only GET is supported" });
      return true;
    }
    try {
      json(response, 200, loadScalabilityEvidence(repoRoot));
    } catch {
      json(response, 404, { error: "Scalability campaign artifacts are unavailable" });
    }
    return true;
  }
  if (url.pathname === "/api/freeciv-artifacts/events") {
    if (request.method !== "GET") {
      json(response, 405, { error: "Only GET is supported" });
      return true;
    }
    const eventPath = resolveArtifactEventPath(url.searchParams.get("path") ?? "", repoRoot);
    if (!eventPath) {
      json(response, 404, { error: "Trace is outside the generated artifact catalog" });
      return true;
    }
    response.statusCode = 200;
    response.setHeader("Cache-Control", "no-store");
    response.setHeader("Content-Type", "application/x-ndjson; charset=utf-8");
    createReadStream(eventPath).on("error", () => {
      if (!response.headersSent) {
        json(response, 500, { error: "Trace could not be read" });
      } else {
        response.destroy();
      }
    }).pipe(response);
    return true;
  }
  if (url.pathname !== "/api/freeciv-artifacts") return false;
  if (request.method !== "GET") {
    json(response, 405, { error: "Only GET is supported" });
    return true;
  }
  json(response, 200, buildArtifactCatalog(repoRoot));
  return true;
}

export function freecivArtifactPlugin(repoRoot = defaultRepoRoot): Plugin {
  const install = (middlewares: {
    use(handler: (request: IncomingMessage, response: ServerResponse, next: () => void) => void): void;
  }): void => {
    middlewares.use((request, response, next) => {
      if (!artifactRequestHandler(request, response, repoRoot)) next();
    });
  };
  return {
    name: "freeciv-artifact-catalog",
    configureServer: (server) => install(server.middlewares),
    configurePreviewServer: (server) => install(server.middlewares),
  };
}
