import { useMemo, useState } from "react";

import type { ReplayState, TraceEvent } from "./events";
import { GROUNDED_PROGRAM_STATUS } from "./grounded-status";

type GroundedDomain =
  | "movement" | "city_defence" | "combat" | "production" | "research"
  | "transport" | "other";

const DOMAINS: Array<{
  id: GroundedDomain;
  title: string;
  stage: string;
  status: string;
  boundary: string;
}> = [
  { id: "movement", title: "Movement", stage: "GDO-2", status: "parity / abstain",
    boundary: "Native current-step routes and declared bounded subset." },
  { id: "city_defence", title: "City defence", stage: "GDO-4", status: "pilot passed",
    boundary: "Threat/defender ETA, sole-defender safety, and exact assignment." },
  { id: "combat", title: "Atomic combat", stage: "GDO-5", status: "pilot passed",
    boundary: "Conditional attacks, participant/target conflicts, and material risk." },
  { id: "production", title: "Production", stage: "GDO-7A/C", status: "retained replay",
    boundary: "Build timing, city production slots, workers, and explicit abstention." },
  { id: "research", title: "Research", stage: "GDO-7B", status: "retained replay",
    boundary: "Research options, cost/progress, slot identity, and dependency context." },
  { id: "transport", title: "Founder transport", stage: "GDO-6", status: "contract only",
    boundary: "Seat identity, locked partnership, rendezvous, landing, and retention." },
];

const recordOf = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};

const rowsOf = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? value.map(recordOf) : [];

const humanize = (value: unknown): string => String(value ?? "—")
  .replaceAll("_", " ").replaceAll("-", " ")
  .replace(/\b\w/g, (letter) => letter.toUpperCase());

const shortId = (value: unknown): string => {
  const text = String(value ?? "—");
  return text.length > 28 ? `${text.slice(0, 13)}…${text.slice(-9)}` : text;
};

const number = (value: unknown, digits = 3): string => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(digits).replace(/\.?0+$/, "") : "—";
};

const domainOf = (payload: Record<string, unknown>): GroundedDomain => {
  const text = [payload.estimator_id, payload.action_category, payload.action_type,
    payload.operation_type, payload.reason_code].map(String).join(" ").toLowerCase();
  if (/transport|ferry|founder|embark|disembark/.test(text)) return "transport";
  if (/city.?defen|defender|fortif|threat/.test(text)) return "city_defence";
  if (/combat|attack|bombard/.test(text)) return "combat";
  if (/research|technology|tech_/.test(text)) return "research";
  if (/production|city.?worker|build|governor/.test(text)) return "production";
  if (/movement|unit_move|route/.test(text)) return "movement";
  return "other";
};

const eventDomain = (event: TraceEvent): GroundedDomain => domainOf(event.payload);

const reliefText = (payload: Record<string, unknown>): string => {
  const relief = recordOf(payload.expected_relief);
  const entries = Object.entries(relief);
  if (!entries.length) return "—";
  const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);
  return `${number(total)} · ${entries.length} goal${entries.length === 1 ? "" : "s"}`;
};

const resourceKey = (event: TraceEvent): string => {
  const resource = recordOf(event.payload.resource);
  return [resource.kind, resource.owner_id, resource.scope, resource.subresource]
    .filter((value) => value !== null && value !== undefined && value !== "").join(":");
};

function ProgramCloseout() {
  const status = GROUNDED_PROGRAM_STATUS;
  return <>
    <section className="grounded-closeout" aria-labelledby="grounded-closeout-title">
      <header>
        <div><span className="eyebrow">grounded implementation closeout</span>
          <h3 id="grounded-closeout-title">Grounded planner authority map</h3></div>
        <span className="grounded-complete">{status.programStatus}</span>
      </header>
      <div className="grounded-boundary-grid">
        <article><span>supported comparator</span><strong>{status.supportedComparator}</strong>
          <small>grounded estimates + identity-aware exact operation scheduler</small></article>
        <article><span>authority boundary</span><strong>{status.authorityBoundary}</strong>
          <small>unsupported states abstain; commit still uses the current snapshot</small></article>
        <article className="claim"><span>claim boundary</span><strong>{status.claimBoundary}</strong>
          <small>score directions remain descriptive and statistically unresolved</small></article>
        <article className="closed"><span>bridge / flow</span><strong>{status.bridgeFlow.decision}</strong>
          <small>{status.bridgeFlow.passed}/{status.bridgeFlow.total} GDO-9 conditions · {
            status.bridgeFlow.overhead}</small></article>
      </div>
      <ol className="grounded-gates" aria-label="Grounded implementation stage gates">
        {status.gates.map((gate) => <li key={gate.id} className={gate.state}>
          <span>{gate.id}</span><strong>{gate.title}</strong><b>{gate.state}</b>
          <p>{gate.result}</p><code title={gate.evidence}>{gate.evidence}</code>
        </li>)}
      </ol>
    </section>

    <div className="grounded-pilot-grid">
      <section aria-labelledby="city-pilot-title">
        <header><span className="eyebrow">fresh mechanism evidence</span>
          <h3 id="city-pilot-title">City-defence pilot</h3><b>passed</b></header>
        <div><span>paired seeds</span><strong>{status.pilots.cityDefense.pairs}</strong></div>
        <div><span>completion</span><strong>{status.pilots.cityDefense.operations}</strong></div>
        <div><span>coverage</span><strong>{status.pilots.cityDefense.threatDelta}</strong></div>
        <div><span>safety</span><strong>{status.pilots.cityDefense.safety}</strong></div>
        <footer>{status.pilots.cityDefense.latency}</footer>
      </section>
      <section aria-labelledby="combat-pilot-title">
        <header><span className="eyebrow">additional operation slice</span>
          <h3 id="combat-pilot-title">Atomic-combat pilot</h3><b>passed</b></header>
        <div><span>mechanism</span><strong>{status.pilots.combat.completionDelta}</strong></div>
        <div><span>activation</span><strong>{status.pilots.combat.activation}</strong></div>
        <div><span>material residual</span><strong>{status.pilots.combat.material}</strong></div>
        <div><span>score boundary</span><strong>{status.pilots.combat.score}</strong></div>
        <footer>Fresh directional mechanism benefit; no score claim.</footer>
      </section>
    </div>
  </>;
}

function DomainCoverage({ state, onSelectEvent }: {
  state: ReplayState; onSelectEvent: (event: TraceEvent) => void;
}) {
  const estimates = [...state.domainEstimates, ...state.domainAbstentions];
  return <section className="grounded-panel grounded-domains"
    aria-labelledby="grounded-domain-title">
    <header><div><span className="eyebrow">declared support / exact trace counts</span>
      <h3 id="grounded-domain-title">Domain model coverage</h3></div>
      <span>{estimates.length.toLocaleString()} estimate events</span></header>
    <div>
      {DOMAINS.map((domain) => {
        const supported = state.domainEstimates.filter((event) => eventDomain(event) === domain.id);
        const abstained = state.domainAbstentions.filter((event) => eventDomain(event) === domain.id);
        const operations = state.operationEvents.filter((event) => eventDomain(event) === domain.id);
        const evidence = [...supported, ...abstained, ...operations].at(-1);
        return <button key={domain.id} disabled={!evidence}
          onClick={() => evidence && onSelectEvent(evidence)}>
          <span>{domain.stage}</span><strong>{domain.title}</strong><b>{domain.status}</b>
          <p>{domain.boundary}</p>
          <dl><div><dt>typed</dt><dd>{supported.length}</dd></div>
            <div><dt>abstain</dt><dd>{abstained.length}</dd></div>
            <div><dt>lifecycle</dt><dd>{operations.length}</dd></div></dl>
        </button>;
      })}
    </div>
    <footer>Zero events means “not logged in this trace,” never “the mechanism did not run.”
      Static scope labels come from the frozen implementation record.</footer>
  </section>;
}

function EstimateExplorer({ state, onSelectEvent }: {
  state: ReplayState; onSelectEvent: (event: TraceEvent) => void;
}) {
  const [domain, setDomain] = useState<GroundedDomain | "all">("all");
  const [disposition, setDisposition] = useState<"all" | "typed" | "abstained">("all");
  const estimates = useMemo(() => [...state.domainEstimates, ...state.domainAbstentions]
    .sort((left, right) => left.turn - right.turn || left.seq - right.seq)
    .filter((event) => domain === "all" || eventDomain(event) === domain)
    .filter((event) => disposition === "all"
      || (disposition === "typed" ? event.type === "domain_estimate_emitted"
        : event.type === "domain_estimate_abstained"))
    .slice(-200).reverse(), [state, domain, disposition]);
  const exact = state.domainEstimates.filter((event) => [
    "exact_authoritative", "deterministic_derived", "calibrated",
  ].includes(String(event.payload.authority))).length;
  const unknownMass = state.domainEstimates.filter((event) => {
    const transition = recordOf(event.payload.transition);
    return Number(transition.unknown_mass ?? transition.residual_unknown_mass ?? 0) > 0;
  }).length;
  const abstentionReasons = new Set(state.domainAbstentions.map((event) =>
    String(event.payload.abstention_reason ?? "unknown"))).size;
  const latency = state.domainEstimates.map((event) => Number(event.payload.latency_ms))
    .filter(Number.isFinite).sort((a, b) => a - b);
  const p95 = latency.length ? latency[Math.min(latency.length - 1,
    Math.floor(latency.length * .95))] : undefined;

  return <section className="grounded-panel grounded-estimates"
    aria-labelledby="grounded-estimates-title">
    <header><div><span className="eyebrow">GDO-1/2/7 · candidate-invariant readout</span>
      <h3 id="grounded-estimates-title">Grounded transition estimates</h3></div>
      <div className="grounded-filters">
        <label>domain<select aria-label="Grounded estimate domain" value={domain}
          onChange={(event) => setDomain(event.target.value as typeof domain)}>
          <option value="all">all domains</option>{DOMAINS.map((row) =>
            <option key={row.id} value={row.id}>{row.title}</option>)}
          <option value="other">other</option>
        </select></label>
        <label>readout<select aria-label="Grounded estimate disposition" value={disposition}
          onChange={(event) => setDisposition(event.target.value as typeof disposition)}>
          <option value="all">typed + abstained</option><option value="typed">typed</option>
          <option value="abstained">abstained</option>
        </select></label>
      </div></header>
    <div className="grounded-stat-strip" aria-label="Grounded estimate summary">
      <div><span>typed estimates</span><strong>{state.domainEstimates.length.toLocaleString()}</strong>
        <small>{exact.toLocaleString()} live-eligible authority classes</small></div>
      <div><span>explicit abstentions</span><strong>{state.domainAbstentions.length.toLocaleString()}</strong>
        <small>{abstentionReasons} reason codes</small></div>
      <div><span>unknown mass</span><strong>{unknownMass.toLocaleString()}</strong>
        <small>retained rather than normalized away</small></div>
      <div><span>estimator latency p95</span><strong>{p95 === undefined ? "—" : `${number(p95)} ms`}</strong>
        <small>event-provided latency only</small></div>
    </div>
    {estimates.length ? <div className="grounded-estimate-table" role="region"
      aria-label="Grounded transition estimate ledger">
      <div className="head"><span>turn / domain</span><span>candidate</span>
        <span>authority</span><span>confidence / relief</span><span>validity</span>
        <span>estimator / reason</span></div>
      {estimates.map((event) => {
        const payload = event.payload;
        const validity = recordOf(payload.validity);
        const abstained = event.type === "domain_estimate_abstained";
        return <button key={event.event_id} className={abstained ? "abstained" : "typed"}
          onClick={() => onSelectEvent(event)}>
          <span><strong>T{event.turn}.{event.seq}</strong><small>{humanize(eventDomain(event))}</small></span>
          <span><strong>{humanize(payload.action_type)}</strong>
            <small>{shortId(payload.operation_id)}</small></span>
          <span><b>{humanize(payload.authority)}</b><small>risk {number(payload.adverse_risk)}</small></span>
          <span><strong>{number(payload.confidence)}</strong><small>{reliefText(payload)}</small></span>
          <span><strong>through T{number(validity.valid_through_turn, 0)}</strong>
            <small>{shortId(validity.snapshot_id)}</small></span>
          <span><strong>{shortId(payload.estimator_id)}</strong><small>{abstained
            ? humanize(payload.abstention_reason) : `${number(payload.latency_ms)} ms`}</small></span>
        </button>;
      })}
    </div> : <div className="grounded-empty">No matching domain estimate events at this cursor.</div>}
    <footer>Relative candidate utility is not presented as probability. Every row preserves
      authority, confidence, validity, provenance, risk, and abstention exactly as emitted.</footer>
  </section>;
}

function ResourceScheduler({ state, onSelectEvent }: {
  state: ReplayState; onSelectEvent: (event: TraceEvent) => void;
}) {
  const dispositions = new Map<string, number>();
  const hardness = new Map<string, number>();
  for (const event of state.resourceClaims) {
    const disposition = String(event.payload.disposition ?? event.type.replace("resource_claim_", ""));
    dispositions.set(disposition, (dispositions.get(disposition) ?? 0) + 1);
    const kind = String(event.payload.hardness ?? "unknown");
    hardness.set(kind, (hardness.get(kind) ?? 0) + 1);
  }
  const capacities = new Map<string, TraceEvent>();
  for (const event of state.resourceCapacities) capacities.set(resourceKey(event), event);
  const exactSchedules = state.resourceSchedules.filter((event) =>
    event.payload.exact_status === "exact").length;
  const fallbacks = state.resourceSchedules.filter((event) =>
    event.payload.exact_status === "greedy_fallback").length;
  const latestSchedule = state.resourceSchedules.at(-1);
  const latestClaims = state.resourceClaims.slice(-120).reverse();

  return <section className="grounded-panel grounded-resources"
    aria-labelledby="grounded-resources-title">
    <header><div><span className="eyebrow">GDO-3 · identity + time + capacity</span>
      <h3 id="grounded-resources-title">B4 resource scheduler</h3></div>
      <span className="grounded-safety-pass">retained audit · zero hard over-allocation</span></header>
    <div className="grounded-resource-summary">
      <div><span>schedules</span><strong>{state.resourceSchedules.length}</strong>
        <small>{exactSchedules} exact · {fallbacks} deterministic fallbacks</small></div>
      <div><span>current-hard claims</span><strong>{hardness.get("hard_current") ?? 0}</strong>
        <small>eligible for current-step reservation</small></div>
      <div><span>conditional future</span><strong>{hardness.get("conditional_future") ?? 0}</strong>
        <small>never promoted to present authority</small></div>
      <div><span>conflicts blocked</span><strong>{dispositions.get("rejected") ?? 0}</strong>
        <small>rejection is protection, not a violation</small></div>
      <button disabled={!latestSchedule} onClick={() => latestSchedule && onSelectEvent(latestSchedule)}>
        <span>latest solver</span><strong>{humanize(latestSchedule?.payload.exact_status)}</strong>
        <small>{shortId(latestSchedule?.payload.scheduler_identity)}</small></button>
    </div>
    <div className="grounded-resource-grid">
      <section><header><strong>Authoritative capacities</strong><small>{capacities.size} identities</small></header>
        {[...capacities.values()].slice(-16).reverse().map((event) => {
          const resource = recordOf(event.payload.resource);
          const window = recordOf(event.payload.window);
          return <button key={event.event_id} onClick={() => onSelectEvent(event)}>
            <span><strong>{humanize(resource.kind)}</strong><small>{shortId(resourceKey(event))}</small></span>
            <b>{number(event.payload.quantity, 0)}</b>
            <span>T{number(window.start_turn, 0)}–{number(window.end_turn_exclusive, 0)}</span>
          </button>;
        })}
        {!capacities.size && <div className="grounded-empty small">No capacity events logged.</div>}
      </section>
      <section><header><strong>Claim disposition</strong><small>{state.resourceClaims.length} events</small></header>
        <div className="grounded-dispositions">
          {["requested", "reserved", "rejected", "released", "expired"].map((key) =>
            <div key={key} className={key}><span>{key}</span><strong>{dispositions.get(key) ?? 0}</strong></div>)}
        </div>
        <p>Current claims are released after commit or rejection. Future requirements remain
          conditional and must compete again against a fresh snapshot.</p>
      </section>
    </div>
    {latestClaims.length ? <details className="grounded-ledger-details">
      <summary>Claim ledger · latest {latestClaims.length}</summary>
      <div className="grounded-claim-table" role="region" aria-label="Grounded resource claim ledger">
        <div className="head"><span>turn</span><span>resource identity</span>
          <span>window / qty</span><span>hardness</span><span>disposition</span><span>operation</span></div>
        {latestClaims.map((event) => {
          const resource = recordOf(event.payload.resource);
          const window = recordOf(event.payload.window);
          const disposition = String(event.payload.disposition ?? "unknown");
          return <button key={event.event_id} className={disposition}
            onClick={() => onSelectEvent(event)}>
            <span>T{event.turn}.{event.seq}</span>
            <span><strong>{humanize(resource.kind)}</strong><small>{shortId(resourceKey(event))}</small></span>
            <span>T{number(window.start_turn, 0)}–{number(window.end_turn_exclusive, 0)} · {
              number(event.payload.quantity, 0)}</span>
            <span>{humanize(event.payload.hardness)}</span>
            <span><strong>{humanize(disposition)}</strong><small>{humanize(event.payload.reason)}</small></span>
            <span>{shortId(event.payload.operation_id)}</span>
          </button>;
        })}
      </div>
    </details> : <div className="grounded-empty">No identity resource claims at this cursor.</div>}
  </section>;
}

function OperationLifecycle({ state, onSelectEvent }: {
  state: ReplayState; onSelectEvent: (event: TraceEvent) => void;
}) {
  const [domain, setDomain] = useState<GroundedDomain | "all">("all");
  const operations = useMemo(() => {
    const grouped = new Map<string, TraceEvent[]>();
    for (const event of state.operationEvents) {
      const id = String(event.payload.operation_id ?? "");
      if (!id) continue;
      grouped.set(id, [...grouped.get(id) ?? [], event]);
    }
    return [...grouped.entries()].map(([id, events]) => ({ id, events,
      latest: events.at(-1)! })).filter((row) => domain === "all"
        || eventDomain(row.latest) === domain).slice(-120).reverse();
  }, [state.operationEvents, domain]);
  const unique = new Set(state.operationEvents.map((event) => event.payload.operation_id)).size;
  const countState = (name: string): number => state.operationEvents.filter((event) =>
    event.payload.state === name).length;

  return <section className="grounded-panel grounded-operations"
    aria-labelledby="grounded-operations-title">
    <header><div><span className="eyebrow">GDO-4/5/6 · explicit multi-turn coordination</span>
      <h3 id="grounded-operations-title">Operation lifecycle</h3></div>
      <label>domain<select aria-label="Grounded operation domain" value={domain}
        onChange={(event) => setDomain(event.target.value as typeof domain)}>
        <option value="all">all domains</option>{DOMAINS.map((row) =>
          <option key={row.id} value={row.id}>{row.title}</option>)}</select></label></header>
    <div className="grounded-operation-summary" aria-label="Grounded operation lifecycle summary">
      <div><span>stable identities</span><strong>{unique}</strong><small>grouped by operation_id</small></div>
      <div><span>activated</span><strong>{countState("activated")}</strong><small>current claims acquired</small></div>
      <div><span>steps committed</span><strong>{countState("step_committed")}</strong><small>one grounded step at a time</small></div>
      <div><span>repaired</span><strong>{countState("repaired")}</strong><small>reason-coded replacement</small></div>
      <div><span>completed</span><strong>{countState("completed")}</strong><small>authoritative resolution</small></div>
      <div><span>failed / abandoned</span><strong>{countState("failed") + countState("abandoned")}</strong>
        <small>not silently discarded</small></div>
    </div>
    {operations.length ? <div className="grounded-operation-table" role="region"
      aria-label="Grounded operation lifecycle ledger">
      <div className="head"><span>operation</span><span>domain / type</span>
        <span>state trail</span><span>participants / claims</span><span>resolution</span></div>
      {operations.map(({ id, events, latest }) => {
        const participants = rowsOf(latest.payload.participants);
        const claims = rowsOf(latest.payload.claims);
        const trail = events.slice(-8).map((event) => String(event.payload.state));
        return <button key={id} className={String(latest.payload.state)}
          onClick={() => onSelectEvent(latest)}>
          <span><strong>{shortId(id)}</strong><small>T{latest.turn}.{latest.seq}</small></span>
          <span><strong>{humanize(eventDomain(latest))}</strong>
            <small>{humanize(latest.payload.operation_type)}</small></span>
          <span className="state-trail">{trail.map((stateName, index) =>
            <i key={`${stateName}-${index}`} className={stateName}>{humanize(stateName)}</i>)}</span>
          <span><strong>{participants.length} participants · {claims.length} claims</strong>
            <small>{latest.payload.policy_authority === true ? "bounded authority" : "shadow only"}</small></span>
          <span><strong>{humanize(latest.payload.resolution_status ?? latest.payload.state)}</strong>
            <small>{humanize(latest.payload.reason_code)}</small></span>
        </button>;
      })}
    </div> : <div className="grounded-empty">No matching operation lifecycle events at this cursor.</div>}
    <footer>An operation keeps identities, roles, requirements, future conditions, and reason
      codes—but only its next legal step may receive current authority.</footer>
  </section>;
}

function CalibrationAndRelease({ state, onSelectEvent }: {
  state: ReplayState; onSelectEvent: (event: TraceEvent) => void;
}) {
  const status = GROUNDED_PROGRAM_STATUS;
  const calibration = status.calibration;
  const latestEstimate = state.transitionValueEstimates.at(-1);
  const latestUpdate = state.transitionValueUpdates.at(-1);
  const estimateSummary = recordOf(latestEstimate?.payload.summary);
  const updateSummary = recordOf(latestUpdate?.payload.summary);
  const gdo9 = status.gates.find((gate) => gate.id === "GDO-9")!;
  const conditions = [
    ["Candidate-invariant calibrated target slice", true],
    ["Zero hard identity/resource over-allocation", true],
    ["Stable operation completion/failure semantics", true],
    ["B4 exact scheduler is the comparison baseline", true],
    ["Residual route-allocation error identified", false],
    ["Residual proven non-semantic and supported", false],
    ["Incremental value exceeds controller cost", false],
  ] as const;

  return <div className="grounded-calibration-grid">
    <section className="grounded-panel" aria-labelledby="grounded-calibration-title">
      <header><div><span className="eyebrow">GDO-8 · frozen disjoint holdout</span>
        <h3 id="grounded-calibration-title">Contextual transition calibration</h3></div>
        <span className="grounded-safety-pass">prediction gate passed</span></header>
      <div className="grounded-calibration-hero">
        <div><span>raw Brier</span><strong>{calibration.rawBrier}</strong></div><i>→</i>
        <div><span>contextual Brier</span><strong>{calibration.contextualBrier}</strong></div>
        <div className="improvement"><span>improvement</span><strong>{calibration.improvement}</strong>
          <small>95% {calibration.interval}</small></div>
      </div>
      <dl className="grounded-calibration-facts">
        <div><dt>training</dt><dd>{calibration.trainingArms} arms</dd></div>
        <div><dt>holdout</dt><dd>{calibration.holdoutArms} fresh arms</dd></div>
        <div><dt>eligible outcomes</dt><dd>{calibration.outcomes.toLocaleString()}</dd></div>
        <div><dt>coverage</dt><dd>{calibration.coverage}</dd></div>
      </dl>
      <div className="grounded-live-calibration">
        <span>current trace</span>
        {latestEstimate ? <button onClick={() => onSelectEvent(latestEstimate)}>
          <strong>{humanize(estimateSummary.gate_reason ?? "transition value estimated")}</strong>
          <small>{shortId(estimateSummary.model_identity ?? latestEstimate.payload.query_id)}</small>
        </button> : <p>No transition-value estimate logged at this cursor.</p>}
        {latestUpdate && <button onClick={() => onSelectEvent(latestUpdate)}>
          <strong>{updateSummary.applied === true ? "authoritative outcome applied" : "outcome observed"}</strong>
          <small>{shortId(latestUpdate.payload.query_id)}</small>
        </button>}
      </div>
      <footer>Prediction calibration passed. The non-randomized engine diagnostic did not
        establish causal policy, score, or win-rate benefit.</footer>
    </section>

    <section className="grounded-panel grounded-reentry" aria-labelledby="grounded-reentry-title">
      <header><div><span className="eyebrow">GDO-9 · fail-closed release gate</span>
        <h3 id="grounded-reentry-title">Bridge / flow re-entry</h3></div>
        <span className="grounded-release-closed">closed · {status.bridgeFlow.passed}/{status.bridgeFlow.total}</span>
      </header>
      <ol>{conditions.map(([label, passed], index) => <li key={label}
        className={passed ? "passed" : "blocked"}>
        <span>{String(index + 1).padStart(2, "0")}</span><strong>{label}</strong>
        <b>{passed ? "passed" : "blocked"}</b></li>)}</ol>
      <div className="grounded-reentry-result">
        <span>historical engine result</span><strong>{status.bridgeFlow.historicalScore}</strong>
        <small>{status.bridgeFlow.overhead}</small>
      </div>
      <footer><strong>{gdo9.result}</strong><small>{gdo9.evidence}</small></footer>
    </section>
  </div>;
}

export function GroundedPlannerDashboard({ state, onSelectEvent }: {
  state: ReplayState;
  onSelectEvent: (event: TraceEvent) => void;
}) {
  const traceGroundedEvents = state.domainEstimates.length + state.domainAbstentions.length
    + state.resourceSchedules.length + state.resourceClaims.length
    + state.resourceCapacities.length + state.operationEvents.length;
  return <div className="view-content grounded-view">
    <div className="view-heading">
      <div><span className="eyebrow">typed estimates / identity resources / explicit operations</span>
        <h2>Grounded planner</h2></div>
      <p>The frozen program result and the loaded trace are deliberately separate. Static
        gates come from retained audits; dynamic tables contain only emitted events as of the cursor.</p>
    </div>
    <div className="grounded-trace-banner">
      <span className={traceGroundedEvents ? "observed" : "missing"} />
      <strong>{traceGroundedEvents.toLocaleString()} grounded events in this trace</strong>
      <small>{traceGroundedEvents
        ? "Inspect any row to see its exact payload and causal ancestry."
        : "Program evidence is available below, but this trace predates or disabled grounded telemetry."}</small>
    </div>
    <ProgramCloseout />
    <DomainCoverage state={state} onSelectEvent={onSelectEvent} />
    <EstimateExplorer state={state} onSelectEvent={onSelectEvent} />
    <ResourceScheduler state={state} onSelectEvent={onSelectEvent} />
    <OperationLifecycle state={state} onSelectEvent={onSelectEvent} />
    <CalibrationAndRelease state={state} onSelectEvent={onSelectEvent} />
  </div>;
}
