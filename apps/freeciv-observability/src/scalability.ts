export interface ScalingTrial {
  actual_work: Record<string, unknown>;
  correctness: Record<string, unknown>;
  metrics: Record<string, unknown>;
  status: "completed" | "failed" | "stopped";
  trial: {
    arm: string;
    cell: {
      parameters: Record<string, unknown>;
      seed: number;
      surface: string;
      tier: string;
    };
    phase: "discovery" | "heldout";
    source_identity: string;
  };
  trial_id: string;
}

export interface ScalingEvidence {
  aggregate: Record<string, unknown>;
  audit: Record<string, unknown>;
  claims: Record<string, unknown>;
  discovery: ScalingTrial[];
  environment: Record<string, unknown>;
  frozen: Record<string, unknown> | null;
  heldout: ScalingTrial[];
  preregistration: Record<string, unknown>;
}

export async function fetchScalabilityEvidence(
  signal?: AbortSignal,
): Promise<ScalingEvidence> {
  const response = await fetch("/api/freeciv-scalability", {
    headers: { Accept: "application/json" }, signal,
  });
  if (!response.ok) {
    throw new Error(`Scalability evidence unavailable: ${response.status} ${response.statusText}`);
  }
  return await response.json() as ScalingEvidence;
}
