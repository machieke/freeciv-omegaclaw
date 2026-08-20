import { useEffect, useState } from "react";

import {
  fetchScalabilityEvidence, type ScalingEvidence, type ScalingTrial,
} from "./scalability";

type JsonObject = Record<string, unknown>;

const objectOf = (value: unknown): JsonObject =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject : {};
const rowsOf = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const numberOf = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;
const statusOf = (value: unknown): string => typeof value === "string" ? value : "not-entered";
const displayStatus = (value: string): string => value.replaceAll("-", " ");

const compact = (value?: number): string => {
  if (value === undefined) return "—";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}m`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
};

const milliseconds = (value?: number): string => value === undefined
  ? "—" : value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(1)} ms`;

const bytes = (value?: number): string => value === undefined
  ? "—" : value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(2)} GiB`
    : value >= 1024 ** 2 ? `${(value / 1024 ** 2).toFixed(1)} MiB`
      : `${compact(value)} B`;

const ratio = (value?: number): string => value === undefined ? "—" : `${value.toFixed(2)}×`;

const ENGINE_VOLUME_LABELS: Array<[string, string]> = [
  ["atoms", "atoms"], ["supports", "supports"], ["scopes", "scopes"],
  ["cities", "cities"], ["units", "units"], ["region_scopes", "regions"],
  ["legal_actions", "legal actions"], ["concurrent_goals", "concurrent goals"],
  ["grounded_candidates", "grounded candidates"], ["proof_chain_depth", "proof depth"],
  ["proof_tree_size", "proof tree"], ["control_nodes", "control nodes"],
  ["control_edges", "control edges"], ["bridge_nodes", "bridge nodes"],
  ["flow_iterations", "flow iterations"], ["events", "events"],
];

const SURFACES = ["atomspace", "proof", "bridge", "fluid"] as const;

function ScalingPlot({ points, maximum, label }: {
  points: number[][]; maximum?: number; label: string;
}) {
  const valid = points.filter((row) => row.length >= 2 && row[0] > 0 && row[1] > 0);
  if (!valid.length) return <div className="scale-empty-plot">No eligible fit points</div>;
  const xs = valid.map((row) => Math.log10(row[0]));
  const ys = valid.map((row) => Math.log10(row[1]));
  const xMin = Math.min(...xs); const xMax = Math.max(...xs);
  const yMin = Math.min(...ys); const yMax = Math.max(...ys);
  const point = (row: number[]): [number, number] => [
    34 + ((Math.log10(row[0]) - xMin) / Math.max(0.0001, xMax - xMin)) * 242,
    112 - ((Math.log10(row[1]) - yMin) / Math.max(0.0001, yMax - yMin)) * 86,
  ];
  const ordered = [...valid].sort((left, right) => left[0] - right[0]);
  return <svg className="scale-plot" viewBox="0 0 300 138" role="img" aria-label={label}>
    <line x1="34" y1="112" x2="282" y2="112" /><line x1="34" y1="18" x2="34" y2="112" />
    <polyline points={ordered.map((row) => point(row).join(",")).join(" ")} />
    {valid.map((row, index) => { const [x, y] = point(row); return <circle key={index} cx={x} cy={y} r="4">
      <title>{compact(row[0])} work · {milliseconds(row[1])}</title></circle>; })}
    <text x="34" y="130">{compact(Math.min(...valid.map((row) => row[0])))}</text>
    <text x="282" y="130" textAnchor="end">{compact(Math.max(...valid.map((row) => row[0])))}</text>
    {maximum !== undefined && <text x="282" y="13" textAnchor="end">β limit {maximum.toFixed(2)}</text>}
  </svg>;
}

const workSummary = (trial?: ScalingTrial): string => {
  if (!trial) return "no completed trial";
  const work = trial.actual_work;
  const surface = trial.trial.cell.surface;
  if (surface === "atomspace") return `${compact(numberOf(work.live_revision_atoms))} atoms · ${compact(numberOf(work.supports))} supports · ${compact(numberOf(work.scopes))} scopes`;
  if (surface === "proof") return `${compact(numberOf(work.relevant_rules))} relevant · depth ${compact(numberOf(work.maximum_depth_attempted) ?? numberOf(work.proof_depth_requested))} · ${compact(numberOf(work.indexed_distractor_rules))} distractors`;
  if (surface === "bridge") return `${compact(numberOf(work.nodes))} nodes · ${compact(numberOf(work.edges))} edges · ${compact(numberOf(work.candidates))} candidates`;
  if (surface === "fluid") return `${compact(numberOf(work.edge_updates))} edge updates · ${compact(numberOf(work.edges))} edges`;
  if (surface === "combined") return `${compact(numberOf(work.live_revision_atoms))} atoms · ${compact(numberOf(work.relevant_rules))} proof rules · ${compact(numberOf(work.bridge_edges))} bridge edges`;
  if (surface === "captured") return `${compact(numberOf(work.amplified_atoms))} amplified atoms · turn ${compact(numberOf(work.turn))}`;
  return "work counters unavailable";
};

const latencyOf = (trial?: ScalingTrial): number | undefined => {
  if (!trial) return undefined;
  const metrics = trial.metrics;
  const surface = trial.trial.cell.surface;
  if (surface === "atomspace") return numberOf(metrics.incremental_ms);
  if (surface === "bridge") return numberOf(metrics.controller_inclusive_ms)
    ?? numberOf(metrics.kernel_elapsed_ms);
  if (surface === "combined") return numberOf(metrics.combined_elapsed_ms);
  if (surface === "captured") return numberOf(metrics.amplification_ms);
  return numberOf(metrics.kernel_elapsed_ms);
};

const primaryWork = (trial: ScalingTrial): number => {
  const work = trial.actual_work;
  const surface = trial.trial.cell.surface;
  if (surface === "atomspace") return numberOf(work.live_revision_atoms) ?? -1;
  if (surface === "proof") return numberOf(work.relevant_rules) ?? -1;
  if (surface === "bridge") return numberOf(work.edges) ?? -1;
  if (surface === "fluid") return numberOf(work.edge_updates) ?? -1;
  return -1;
};

export function ScalabilityDashboard({ initialData }: { initialData?: ScalingEvidence }) {
  const [evidence, setEvidence] = useState<ScalingEvidence | undefined>(initialData);
  const [error, setError] = useState<string>();
  const [phase, setPhase] = useState<"discovery" | "heldout">(
    initialData?.heldout.length ? "heldout" : "discovery");
  useEffect(() => {
    if (initialData) return;
    const controller = new AbortController();
    void fetchScalabilityEvidence(controller.signal).then((value) => {
      setEvidence(value); setPhase(value.heldout.length ? "heldout" : "discovery");
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(
        reason instanceof Error ? reason.message : "Scalability evidence unavailable");
    });
    return () => controller.abort();
  }, [initialData]);
  const trials = evidence ? (phase === "heldout" ? evidence.heldout : evidence.discovery) : [];
  if (error) return <div className="logging-gap"><span>scaling evidence</span>
    <h2>Campaign artifacts could not be loaded</h2><p>{error}</p></div>;
  if (!evidence) return <div className="scale-loading">Loading scalability evidence…</div>;
  const aggregate = objectOf(evidence.aggregate);
  const phaseReports = objectOf(aggregate.phase_reports);
  const phaseReport = objectOf(phaseReports[phase]);
  const surfaces = objectOf(phaseReport.surfaces);
  const gates = objectOf(phaseReport.gates);
  const combined = objectOf(phaseReport.combined);
  const captured = objectOf(phaseReport.captured);
  const engine = objectOf(aggregate.engine_shadow);
  const enginePerformance = objectOf(engine.performance);
  const engineVolume = objectOf(engine.maximum_volume);
  const engineTotals = objectOf(engine.totals);
  const engineTransfer = objectOf(engine.synthetic_transfer);
  const engineScenario = objectOf(engine.engine_shadow_scenario);
  const engineRelease = objectOf(engineScenario.release_game_config);
  const engineExpansion = objectOf(engine.volume_expansion);
  const claims = objectOf(evidence.claims);
  const audit = objectOf(evidence.audit);
  const semanticFailures = rowsOf(audit.semantic_failures);
  const environment = evidence.environment;
  const gateCards: Array<[string, string, unknown]> = [
    ["G2", "AtomSpace", gates.atomspace], ["G3", "Deep proof", gates.proof],
    ["G4", "Bridge", gates.bridge], ["G5", "Fluid", gates.fluid],
    ["G6", "Combined", combined.gate], ["G7", "Captured", captured.gate],
    ["G8", "Engine shadow", engine.gate], ["G9", "Claim audit", claims.g9_complete === true ? "pass" : "not-entered"],
  ];
  const completed = trials.filter((row) => row.status === "completed").length;
  return <div className="view-content scalability-view">
    <div className="view-heading">
      <div><span className="eyebrow">larger AtomSpace / deeper inference / bridge + fluid</span>
        <h2>Scalability campaign</h2></div>
      <p>{completed} completed {phase} trials · audit {audit.valid === true ? "integrity valid" : "integrity failed"}
        {semanticFailures.length ? ` · ${semanticFailures.length} retained semantic failures` : ""} · no gameplay claim</p>
    </div>
    <section className={`scale-claim-boundary ${phase}`}>
      <div><span>evidence phase</span><strong>{phase}</strong><small>{phase === "heldout"
        ? "Frozen cells may enter a claim when cohorts and audits are complete."
        : "Screening evidence can find defects, but cannot authorize a scaling claim."}</small></div>
      <div className="segmented-control" aria-label="Scaling evidence phase">
        <button className={phase === "discovery" ? "active" : ""} onClick={() => setPhase("discovery")}>discovery</button>
        <button className={phase === "heldout" ? "active" : ""} onClick={() => setPhase("heldout")}>held-out</button>
      </div>
      <div><span>source</span><strong>{String(environment.git_commit ?? "unknown").slice(0, 10)}</strong>
        <small>{environment.git_dirty === true ? "dirty discovery source" : "clean source"} · {String(environment.machine ?? "host")}</small></div>
      <div><span>freeze</span><strong>{evidence.frozen ? "frozen" : "open"}</strong>
        <small>{evidence.frozen ? `${String(evidence.frozen.freeze_hash).slice(0, 12)}…` : "held-out execution disabled"}</small></div>
    </section>
    <section className="scale-gates" aria-label="G2 through G9 gate status">
      {gateCards.map(([id, label, raw]) => { const status = statusOf(raw); return <article key={String(id)} className={status}>
        <span>{id}</span><strong>{label}</strong><b>{displayStatus(status)}</b></article>; })}
    </section>
    <section className="scale-surface-grid">
      {SURFACES.map((surface) => {
        const report = objectOf(surfaces[surface]);
        const selectedSource = typeof report.selected_source_identity === "string"
          ? report.selected_source_identity : undefined;
        const hasFitContract = Array.isArray(report.fit_trial_ids);
        const fitTrialIds = new Set(rowsOf(report.fit_trial_ids).map(String));
        const trial = trials.filter((row) => row.status === "completed"
          && row.trial.cell.surface === surface
          && (!selectedSource || row.trial.source_identity === selectedSource)
          && (!hasFitContract || fitTrialIds.has(row.trial_id)))
          .sort((left, right) => primaryWork(right) - primaryWork(left))[0];
        const points = rowsOf(report.points).filter(Array.isArray).map((row) => row.map(Number));
        const interval = rowsOf(report.exponent_95_ci).map(Number);
        const labels = Object.entries(objectOf(report.absolute_labels));
        return <article className="scale-surface" key={surface}>
          <header><div><span>{trial?.trial.cell.tier ?? "not entered"}</span><h3>{surface}</h3></div>
            <b className={statusOf(report.gate)}>{displayStatus(statusOf(report.gate))}</b></header>
          <p>{workSummary(trial)}</p>
          <div className="scale-kpis">
            <div><span>measured latency</span><strong>{milliseconds(latencyOf(trial))}</strong></div>
            <div><span>peak RSS</span><strong>{bytes(numberOf(trial?.metrics.peak_rss_bytes))}</strong></div>
            <div><span>fit β</span><strong>{numberOf(report.exponent)?.toFixed(3) ?? "—"}</strong>
              <small>{interval.length === 2 ? `[${interval[0].toFixed(3)}, ${interval[1].toFixed(3)}]` : "CI not entered"}</small></div>
          </div>
          <ScalingPlot points={points} maximum={numberOf(report.maximum_exponent)}
            label={`${surface} time versus realized work`} />
          <small className="scale-fit-selection">fit: {String(report.fit_selection ?? "canonical primary axis")}
            {numberOf(report.excluded_stress_trials)
              ? ` · ${numberOf(report.excluded_stress_trials)} stress trials shown separately from the fit`
              : ""}{numberOf(report.semantic_failure_count)
              ? ` · ${numberOf(report.semantic_failure_count)} semantic failures retained`
              : ""}</small>
          <div className="scale-labels">{labels.length ? labels.map(([name, raw]) => {
            const label = objectOf(raw); const status = statusOf(label.status);
            return <div key={name}><span>{name}</span><b className={status}>{displayStatus(status)}</b>
              <small>{numberOf(label.sample_count) ?? 0}/50 · p95 {milliseconds(numberOf(label.p95))}</small></div>;
          }) : <span>No absolute latency labels</span>}</div>
        </article>;
      })}
    </section>
    <section className="scale-transfer-grid">
      <article><header><span>G6 / interaction</span><b className={statusOf(combined.gate)}>{displayStatus(statusOf(combined.gate))}</b></header>
        <strong>{numberOf(combined.paired_trials) ?? 0} paired cells</strong>
        <p>Maximum combined / isolated-stage ratio: {numberOf(combined.maximum_ratio)?.toFixed(3) ?? "—"} · bound 2.0</p></article>
      <article><header><span>G7 / realistic shapes</span><b className={statusOf(captured.gate)}>{displayStatus(statusOf(captured.gate))}</b></header>
        <strong>{numberOf(captured.paired_trials) ?? 0} paired snapshots</strong>
        <p>Max timing ratio {numberOf(captured.maximum_timing_ratio)?.toFixed(3) ?? "—"} · RSS {numberOf(captured.maximum_rss_ratio)?.toFixed(3) ?? "—"}</p></article>
      <article><header><span>G8 / engine shadow</span><b className={statusOf(engine.gate)}>{displayStatus(statusOf(engine.gate))}</b></header>
        <strong>{numberOf(engine.pair_count) ?? 0} engine pairs</strong>
        <p>{numberOf(engine.pair_count)
          ? `${compact(numberOf(engineVolume.atoms))} naturally achieved atoms · ${milliseconds(numberOf(objectOf(enginePerformance.fdas_turn_contribution_ms).p95_ms))} FDAS p95`
          : "Ordered action, result, completion, authority, and event-ledger checks are required."}</p></article>
      <article><header><span>G9 / claim manifest</span><b className={claims.g9_complete === true ? "pass" : "not-entered"}>{claims.g9_complete === true ? "complete" : "incomplete"}</b></header>
        <strong>{numberOf(claims.heldout_result_count) ?? 0} held-out results</strong>
        <p>{claims.frozen === true ? "Frozen source and cells recorded." : "No source freeze; all results remain discovery-only."}</p></article>
    </section>
    <section className="scale-engine-detail" aria-label="Engine-backed shadow confirmation">
      <header><div><span className="eyebrow">G8 · grounded transfer</span>
        <h3>Engine-backed shadow confirmation</h3></div>
        <b className={statusOf(engine.gate)}>{displayStatus(statusOf(engine.gate))}</b></header>
      <div className="scale-engine-context">
        <div><span>scenario</span><strong>{String(engineScenario.scenario_id ?? "not entered")}</strong>
          <small>fixed high-entity FreeCiv construction</small></div>
        <div><span>paired seeds</span><strong>{compact(numberOf(engine.pair_count))} / {compact(numberOf(engineScenario.minimum_pairs))}</strong>
          <small>control and FDAS-shadow action parity</small></div>
        <div><span>horizon</span><strong>{compact(numberOf(engineScenario.horizon_turn))} turns</strong>
          <small>fog {engineRelease.fogofwar === false ? "disabled" : "configured"} · {String(engineRelease.startunits ?? "—")}</small></div>
        <div><span>source report</span><strong>{String(engine.source_report_hash ?? "unavailable").slice(0, 12)}</strong>
          <small>{engine.valid === true ? "structural and ledger audit valid" : "awaiting accepted cohort"}</small></div>
      </div>
      {numberOf(engine.pair_count) ? <div className="scale-engine-body">
        <article><header><h4>Naturally achieved volume</h4><small>observed maxima, never configured caps</small></header>
          <dl className="scale-engine-volume">{ENGINE_VOLUME_LABELS.map(([name, label]) => <div key={name}>
            <dt>{label}</dt><dd>{compact(numberOf(engineVolume[name]))}</dd></div>)}</dl></article>
        <article><header><h4>Live-path cost</h4><small>distribution across all shadow turns</small></header>
          <div className="scale-engine-metrics">
            <div><span>controller p95</span><strong>{milliseconds(numberOf(objectOf(enginePerformance.controller_latency_ms).p95_ms))}</strong>
              <small>max {milliseconds(numberOf(objectOf(enginePerformance.controller_latency_ms).maximum_ms))}</small></div>
            <div><span>FDAS turn p95</span><strong>{milliseconds(numberOf(objectOf(enginePerformance.fdas_turn_contribution_ms).p95_ms))}</strong>
              <small>projection + shadow readout</small></div>
            <div><span>projection p95</span><strong>{milliseconds(numberOf(objectOf(enginePerformance.fdas_projection_latency_ms).p95_ms))}</strong>
              <small>{compact(numberOf(objectOf(enginePerformance.fdas_projection_latency_ms).count))} samples</small></div>
            <div><span>process RSS p95</span><strong>{bytes(numberOf(objectOf(enginePerformance.controller_process_peak_rss_bytes).p95_bytes))}</strong>
              <small>max {bytes(numberOf(objectOf(enginePerformance.controller_process_peak_rss_bytes).maximum_bytes))}</small></div>
          </div>
          <div className="scale-engine-transfer"><span>nearest synthetic transfer</span>
            <strong>{ratio(numberOf(engineTransfer.latency_ratio_engine_fdas_projection_p95_to_synthetic_incremental_p95))} latency · {ratio(numberOf(engineTransfer.memory_ratio_engine_controller_rss_p95_to_synthetic_process_rss_p95))} memory</strong>
            <small>{engineTransfer.entered === true
              ? `${String(engineTransfer.nearest_synthetic_tier ?? "tier unknown")} at ${compact(numberOf(engineTransfer.nearest_synthetic_work_atoms))} atoms; descriptive, no acceptance threshold`
              : String(engineTransfer.reason ?? "awaiting synthetic transfer match")}</small></div>
        </article>
        <article><header><h4>Mechanism exercise</h4><small>aggregate trace accounting</small></header>
          <dl className="scale-engine-volume compact">{[
            ["decision_count", "shadow decisions"], ["revision_count", "FDAS revisions"],
            ["bridge_event_count", "bridge estimates"], ["flow_event_count", "flow events"],
            ["flow_projection_count", "flow projections"], ["controller_fallback_count", "fallbacks"],
            ["explained_legacy_count", "explained legacy"], ["extra_fdas_count", "extra candidates"],
            ["cold_verification_count", "cold verifications"], ["full_detail_pair_count", "full-detail pairs"],
          ].map(([name, label]) => <div key={name}><dt>{label}</dt><dd>{compact(numberOf(engineTotals[name]))}</dd></div>)}</dl></article>
        <article><header><h4>High-entity expansion</h4><small>strictly above the prior engine cohort</small></header>
          <div className="scale-engine-expansion">{Object.entries(engineExpansion).map(([name, raw]) => {
            const row = objectOf(raw); const passed = row.passed === true;
            return <div key={name} className={passed ? "pass" : "fail"}><span>{name.replaceAll("_", " ")}</span>
              <strong>{compact(numberOf(row.reference))} → {compact(numberOf(row.achieved))}</strong>
              <b>{passed ? "expanded" : "not expanded"}</b></div>;
          })}</div></article>
      </div> : <div className="scale-engine-empty"><strong>No admissible engine pair has entered G8.</strong>
        <p>The synthetic and captured scaling evidence remains visible above. Engine integration, natural volume, overhead, and transfer ratios stay unclaimed until all fixed control/shadow pairs complete from the frozen source.</p></div>}
    </section>
    <section className="scale-accounting">
      <header><div><span className="eyebrow">frozen manifest accounting</span><h3>Every planned cell keeps a disposition</h3></div>
        <strong>{rowsOf(claims.cell_accounting).length} cells</strong></header>
      {rowsOf(claims.cell_accounting).length ? <div>{rowsOf(claims.cell_accounting).slice(0, 200).map((raw, index) => {
        const row = objectOf(raw); const status = statusOf(row.status);
        return <span key={`${String(row.payload_id)}-${index}`} className={status} title={String(row.payload_id)}>
          {String(row.surface)} / {String(row.tier)} <b>{displayStatus(status)}</b></span>;
      })}</div> : <p>No frozen held-out cells. Discovery results above remain visible, but none can enter a claim.</p>}
    </section>
  </div>;
}
