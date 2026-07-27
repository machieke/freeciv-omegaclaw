export interface ArtifactCatalogEntry {
  arm?: string;
  cohort?: string;
  condition?: string;
  experiment: string;
  label: string;
  modifiedAt: string;
  path: string;
  run: string;
  sizeBytes: number;
}

export interface ArtifactCatalogResponse {
  entries: ArtifactCatalogEntry[];
  generatedAt: string;
  root: string;
}

export interface ArtifactPairQuality {
  exact: boolean;
  label: "exact pair" | "pair mismatch" | "unverified pair";
  mismatches: string[];
}

const pairFields = ["experiment", "cohort", "condition", "run"] as const;

export const findPairedArtifact = (
  entry: ArtifactCatalogEntry,
  entries: ArtifactCatalogEntry[],
): ArtifactCatalogEntry | undefined => {
  if (!entry.arm) return undefined;
  return entries.find((candidate) => candidate.path !== entry.path
    && Boolean(candidate.arm)
    && candidate.arm !== entry.arm
    && pairFields.every((field) => candidate[field] === entry[field]));
};

export const artifactPairQuality = (
  primary?: ArtifactCatalogEntry,
  comparison?: ArtifactCatalogEntry,
): ArtifactPairQuality => {
  if (!primary || !comparison) {
    return { exact: false, label: "unverified pair", mismatches: ["catalog metadata unavailable"] };
  }
  const mismatches: string[] = pairFields.filter(
    (field) => primary[field] !== comparison[field]);
  if (!primary.arm || !comparison.arm || primary.arm === comparison.arm) mismatches.push("opposite arm");
  return mismatches.length
    ? { exact: false, label: "pair mismatch", mismatches }
    : { exact: true, label: "exact pair", mismatches: [] };
};

const catalogEndpoint = "/api/freeciv-artifacts";
const eventsEndpoint = "/api/freeciv-artifacts/events";

const errorMessage = async (response: Response): Promise<string> => {
  try {
    const body = await response.json() as { error?: unknown };
    if (typeof body.error === "string") return body.error;
  } catch {
    // A non-JSON response is reported with its status below.
  }
  return `${response.status} ${response.statusText}`.trim();
};

export async function fetchArtifactCatalog(signal?: AbortSignal): Promise<ArtifactCatalogResponse> {
  const response = await fetch(catalogEndpoint, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`Artifact catalog unavailable: ${await errorMessage(response)}`);
  }
  return await response.json() as ArtifactCatalogResponse;
}

export async function fetchArtifactEventStream(
  entry: ArtifactCatalogEntry,
): Promise<ReadableStream<Uint8Array>> {
  const response = await fetch(`${eventsEndpoint}?path=${encodeURIComponent(entry.path)}`, {
    headers: { Accept: "application/x-ndjson" },
  });
  if (!response.ok) {
    throw new Error(`Trace unavailable: ${await errorMessage(response)}`);
  }
  if (!response.body) throw new Error("Trace response did not include a readable stream");
  return response.body;
}
