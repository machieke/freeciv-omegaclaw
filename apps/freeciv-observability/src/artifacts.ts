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
