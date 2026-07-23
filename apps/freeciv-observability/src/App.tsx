import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import type { Atom, Plan, PlanStep, PlnResult, ProofNode } from "../../../schemas/freeciv-events/v1/types.generated";
import demoTrace from "../../../Autotests/fixtures/freeciv-events/v1/normal-crisp.jsonl?raw";
import {
  type AtomView, type Cursor, type ReplayState, type TraceEvent,
  cursorOf, eventOrder, formatAtom, maxCursor,
} from "./events";
import {
  type ArtifactCatalogEntry,
  fetchArtifactCatalog,
  fetchArtifactEventStream,
} from "./artifacts";
import { LiveEventClient, type LiveStatus } from "./live";
import { ancestry, densityByTurn, foldEvents } from "./store";
import {
  parseJsonl, parseJsonlStream, type ParseResult, type QuarantinedLine,
} from "./validation";
import { decodeUrlState, encodeUrlState, type ViewName } from "./url-state";

type Selection =
  | { kind: "event"; value: TraceEvent }
  | { kind: "atom"; value: AtomView }
  | { kind: "node"; value: ProofNode }
  | { kind: "plan"; value: Plan }
  | { kind: "step"; value: PlanStep; plan: Plan };

const NAV: Array<{ view: ViewName; label: string; key: string }> = [
  { view: "timeline", label: "Decision timeline", key: "01" },
  { view: "proofs", label: "Proof explorer", key: "02" },
  { view: "atoms", label: "Atomspace", key: "03" },
  { view: "plans", label: "Plan board", key: "04" },
  { view: "map", label: "Map overlay", key: "05" },
  { view: "audit", label: "Epistemic audit", key: "06" },
  { view: "metrics", label: "Metrics", key: "07" },
];

const STAGES: Array<{ name: string; types: Set<string> }> = [
  { name: "State ingest", types: new Set(["state_snapshot", "observation", "revision"]) },
  { name: "Proposal", types: new Set(["llm_proposal", "quarantine"]) },
  { name: "Verification", types: new Set(["verification", "grounded_check"]) },
  { name: "PLN", types: new Set(["pln_query", "pln_result"]) },
  { name: "Plan", types: new Set(["plan_created", "plan_invalidated", "plan_step_executed"]) },
  { name: "Action", types: new Set(["action_sent", "action_result"]) },
];

const seqAtTurn = (events: TraceEvent[], turn: number): number =>
  Math.max(0, ...events.filter((event) => event.turn === turn).map((event) => event.seq));

function Header({ events, state, mode, status, gameId }: {
  events: TraceEvent[]; state: ReplayState; mode: "replay" | "live";
  status: LiveStatus; gameId: string;
}) {
  const shownGameId = state.events[0]?.game_id ?? (gameId || "no trace");
  return <header className="topbar">
    <div className="brand-mark" aria-hidden="true"><span>Ω</span></div>
    <div>
      <div className="eyebrow">FreeCiv / epistemic control surface</div>
      <h1>Decision Observatory</h1>
    </div>
    <div className="run-identity">
      <span className={`live-dot ${mode === "live" ? "streaming" : ""}`} /> {mode} · {status}
      <strong>{shownGameId}</strong>
    </div>
    <div className="top-stat"><span>events</span><strong>{events.length.toLocaleString()}</strong></div>
    <div className="top-stat"><span>as of</span><strong>T{state.cursor.turn}.{state.cursor.seq}</strong></div>
  </header>;
}

function Scrubber({ events, cursor, onChange }: {
  events: TraceEvent[]; cursor: Cursor; onChange: (cursor: Cursor) => void;
}) {
  const turns = events.map((event) => event.turn);
  const minimum = Math.min(...turns, 0);
  const maximum = Math.max(...turns, 0);
  const density = densityByTurn(events);
  const maxDensity = Math.max(1, ...density.values());
  const markers = new Map<number, string>();
  for (const event of events) {
    if (event.type === "plan_invalidated") markers.set(event.turn, "invalidated");
    if (event.type === "quarantine") markers.set(event.turn, "quarantine");
  }
  return <section className="scrubber" aria-label="Global replay cursor">
    <div className="scrubber-label"><span>global cursor</span><strong>Turn {cursor.turn}</strong></div>
    <div className="scrubber-track">
      <div className="density-strip" aria-label="Event density by turn">
        {Array.from({ length: maximum - minimum + 1 }, (_, offset) => minimum + offset).map((turn) =>
          <button key={turn} aria-label={`Turn ${turn}, ${density.get(turn) ?? 0} events`}
            className={`density-tick ${markers.get(turn) ?? ""} ${turn === cursor.turn ? "active" : ""}`}
            style={{ opacity: 0.2 + 0.8 * ((density.get(turn) ?? 0) / maxDensity) }}
            onClick={() => onChange({ turn, seq: seqAtTurn(events, turn) })} />)}
      </div>
      <input aria-label="Turn" type="range" min={minimum} max={maximum} value={cursor.turn}
        onChange={(event) => {
          const turn = Number(event.target.value);
          onChange({ turn, seq: seqAtTurn(events, turn) });
        }} />
    </div>
    <div className="cursor-readout"><span>seq</span><strong>{cursor.seq}</strong></div>
  </section>;
}

function Timeline({ state, selection, onSelect }: {
  state: ReplayState; selection?: Selection; onSelect: (selection: Selection) => void;
}) {
  const selectedEvent = selection?.kind === "event" ? selection.value : undefined;
  const highlighted = selectedEvent?.type === "action_sent"
    ? ancestry(state, selectedEvent.event_id) : new Set<string>();
  return <div className="view-content timeline-view">
    <div className="view-heading">
      <div><span className="eyebrow">causal replay</span><h2>Decision timeline</h2></div>
      <p>Select an action to illuminate its complete ancestry. Every edge is read from <code>caused_by</code>.</p>
    </div>
    <div className="swimlanes">
      {STAGES.map((stage) => {
        const events = state.events.filter((event) => stage.types.has(event.type));
        return <section className="swimlane" key={stage.name}>
          <header><span>{stage.name}</span><small>{events.length}</small></header>
          <div className="lane-events">
            {events.length ? events.slice(-200).map((event) =>
              <button key={event.event_id}
                className={`event-node event-${event.type} ${highlighted.has(event.event_id) ? "ancestry" : ""}`}
                onClick={() => onSelect({ kind: "event", value: event })}
                onDoubleClick={() => event.type === "pln_result"
                  && window.dispatchEvent(new CustomEvent("observatory:view", { detail: "proofs" }))}>
                <span className="node-seq">{event.turn}.{event.seq}</span>
                <strong>{event.type.replaceAll("_", " ")}</strong>
                <small>{event.event_id.slice(-8)}</small>
              </button>) : <div className="empty-lane">No events as of cursor</div>}
          </div>
        </section>;
      })}
    </div>
  </div>;
}

type ProofRow = { node: ProofNode; depth: number; expandable: boolean; expanded: boolean };

const proofRows = (proof: PlnResult["proof"], expandedNodes: Set<string>): ProofRow[] => {
  const nodes = new Map(proof.nodes.map((node) => [node.node_id, node]));
  const rows: ProofRow[] = [];
  const seen = new Set<string>();
  const visit = (nodeId: string, depth: number): void => {
    if (seen.has(nodeId)) return;
    seen.add(nodeId);
    const node = nodes.get(nodeId);
    if (!node) return;
    const expandable = depth >= 4 && node.premise_node_refs.length > 0;
    const expanded = expandedNodes.has(nodeId);
    rows.push({ node, depth, expandable, expanded });
    if (depth < 4 || expanded) {
      for (const child of node.premise_node_refs) visit(child, depth + 1);
    }
  };
  visit(proof.root_node_id, 0);
  return rows;
};

export function ProofExplorer({ state, selection, onSelect }: {
  state: ReplayState; selection?: Selection; onSelect: (selection: Selection) => void;
}) {
  const [selectedProof, setSelectedProof] = useState(0);
  const [comparison, setComparison] = useState(-1);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(() => new Set());
  const [proofWindow, setProofWindow] = useState(0);
  const proofRecord = state.proofs[Math.min(selectedProof, Math.max(0, state.proofs.length - 1))];
  if (!proofRecord) return <LoggingGap title="No proof trace at this cursor"
    detail="The view will not reconstruct a proof from atoms. Emit pln_result with a lossless proof tree." />;
  const result = proofRecord.result;
  const frontier = new Set(result.unsatisfied_frontier.map((item) => item.node_id));
  const rows = proofRows(result.proof, expandedNodes);
  const comparisonProof = comparison >= 0 ? state.proofs[comparison]?.result.proof : undefined;
  const comparisonNodes = new Map(comparisonProof?.nodes.map((node) => [node.atom.atom_id, node]) ?? []);
  const proofWindowCount = Math.max(1, Math.ceil(rows.length / 500));
  const safeProofWindow = Math.min(proofWindow, proofWindowCount - 1);
  const firstProofRow = safeProofWindow * 500;
  const displayedRows = rows.slice(firstProofRow, firstProofRow + 500).map(({ node, depth, expandable, expanded }) => {
    const compared = comparisonNodes.get(node.atom.atom_id);
    return {
      node, depth, expandable, expanded, atomText: formatAtom(node.atom),
      className: `proof-node ${node.crisp ? "crisp" : "uncertain"} ${frontier.has(node.node_id) ? "frontier" : ""} ${comparisonProof && !compared ? "diff-added" : ""} ${compared?.tv.confidence !== undefined && compared.tv.confidence !== node.tv.confidence ? "diff-tv" : ""}`,
    };
  });
  const selectedNode = selection?.kind === "node" ? selection.value : undefined;
  const sourcePlan = [...state.plans.values()].find(
    (plan) => plan.source_proof_hash === result.proof.structural_hash);
  const crispViolation = result.proof.nodes.some((node) => node.crisp && node.tv.strength !== 1);
  return <div className="view-content proof-view">
    <div className="view-heading">
      <div><span className="eyebrow">PLN boundary / {result.status}</span><h2>Proof explorer</h2></div>
      <div className="proof-controls">
        <label>proof <select aria-label="Proof" value={selectedProof}
          onChange={(event) => {
            setSelectedProof(Number(event.target.value));
            setExpandedNodes(new Set());
            setProofWindow(0);
          }}>
          {state.proofs.map((record, index) => <option key={record.event.event_id} value={index}>
            {record.result.query_id} · T{record.event.turn}
          </option>)}
        </select></label>
        <label>diff <select aria-label="Compare proof" value={comparison}
          onChange={(event) => setComparison(Number(event.target.value))}>
          <option value={-1}>off</option>
          {state.proofs.map((record, index) => <option key={record.event.event_id} value={index}>
            {record.result.query_id} · T{record.event.turn}
          </option>)}
        </select></label>
      </div>
    </div>
    <div className="proof-summary">
      <div><span>nodes</span><strong>{result.proof.nodes.length}</strong></div>
      <div><span>depth</span><strong>{result.chain_depth}</strong></div>
      <div><span>latency</span><strong>{result.latency_ms.toFixed(2)} ms</strong></div>
      <div><span>frontier</span><strong>{result.unsatisfied_frontier.length}</strong></div>
      {crispViolation && <div className="violation">crisp drift violation</div>}
    </div>
    {rows.length > 500 && <div className="virtual-controls" aria-label="Proof node windows">
      <button disabled={safeProofWindow === 0}
        onClick={() => setProofWindow(Math.max(0, safeProofWindow - 1))}>previous 500</button>
      <span>{firstProofRow + 1}–{Math.min(rows.length, firstProofRow + 500)} of {rows.length} visible nodes</span>
      <button disabled={safeProofWindow + 1 >= proofWindowCount}
        onClick={() => setProofWindow(safeProofWindow + 1)}>next 500</button>
    </div>}
    <div className="proof-grid" role="tree" aria-label="AND OR proof tree">
      {displayedRows.map(({ node, depth, expandable, expanded, atomText, className }) => <div role="treeitem" key={node.node_id}
        tabIndex={0}
        aria-level={depth + 1} aria-label={`${node.kind} ${atomText}`}
        aria-expanded={expandable ? expanded : undefined}
        className={className}
        style={{ marginLeft: `${depth * 28}px`, "--confidence": node.tv.confidence } as React.CSSProperties}
        onClick={() => onSelect({ kind: "node", value: node })}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect({ kind: "node", value: node });
          } else if (expandable && event.key === "ArrowRight" && !expanded) {
            event.preventDefault();
            setExpandedNodes((prior) => new Set(prior).add(node.node_id));
          } else if (expandable && event.key === "ArrowLeft" && expanded) {
            event.preventDefault();
            setExpandedNodes((prior) => {
              const next = new Set(prior); next.delete(node.node_id); return next;
            });
          }
        }}>
        <strong className="proof-atom"><b>{node.kind.toUpperCase()}</b> · {atomText}</strong>
        <span className={`proof-tv ${node.satisfied ? "satisfied" : "blocked"}`}>
          ⟨{node.tv.strength.toFixed(2)}, {node.tv.confidence.toFixed(2)}⟩ · {node.satisfied ? "✓" : "×"}
        </span>
        <small>{node.rule_applied ?? "state premise"}</small>
        {expandable && <button className="proof-expand"
          aria-label={`${expanded ? "Collapse" : "Expand"} premises for ${atomText}`}
          onClick={(event) => {
            event.stopPropagation();
            setExpandedNodes((prior) => {
              const next = new Set(prior);
              if (expanded) next.delete(node.node_id); else next.add(node.node_id);
              return next;
            });
            setProofWindow(0);
          }}>{expanded ? "−" : `+${node.premise_node_refs.length}`}</button>}
      </div>)}
    </div>
    {sourcePlan?.branch_scores && sourcePlan.branch_scores.length > 0 && <section className="branch-strip">
      <h3>OR branch comparison</h3>
      <div className="branch-head"><span>branch</span><span>feasibility grade</span><span>scheduler cost</span></div>
      {sourcePlan.branch_scores.map((branch) => <div key={branch.branch_id}
        className={branch.branch_id === sourcePlan.selected_branch_id ? "selected" : ""}>
        <strong>{branch.branch_id}</strong><span>{branch.feasibility_grade.toFixed(3)}</span>
        <span>{branch.scheduler_cost.toFixed(3)} · {sourcePlan.cost_profile}</span>
      </div>)}
    </section>}
    {selectedNode && <section className="formula-panel" aria-label="Confidence formula details">
      <span>confidence flow</span><strong>{selectedNode.formula
        ? String((selectedNode.formula as Record<string, unknown>).name ?? "logged formula")
        : "no formula logged"}</strong>
      <code>{JSON.stringify(selectedNode.formula ?? { logging_gap: "formula" })}</code>
      <em>λ {selectedNode.dampening_lambda ?? "not applied"}</em>
    </section>}
    {result.unsatisfied_frontier.length > 0 && <section className="frontier-list">
      <h3>Unsatisfied frontier</h3>
      {result.unsatisfied_frontier.map((item) => <div key={item.node_id}>
        <strong>{item.blocker_type}</strong><span>{item.detail}</span>
      </div>)}
    </section>}
  </div>;
}

function Atomspace({ state, onSelect, search, channel, onSearch, onChannel }: {
  state: ReplayState; onSelect: (selection: Selection) => void;
  search: string; channel: "all" | "crisp" | "uncertain";
  onSearch: (value: string) => void;
  onChannel: (value: "all" | "crisp" | "uncertain") => void;
}) {
  const [atomWindow, setAtomWindow] = useState(0);
  const rows = [...state.atoms.values()].filter(({ atom }) => {
    const text = `${atom.predicate} ${atom.args.join(" ")}`.toLowerCase();
    return text.includes(search.toLowerCase())
      && (channel === "all" || (channel === "crisp" ? atom.crisp : !atom.crisp));
  }).sort((left, right) => left.atom.predicate.localeCompare(right.atom.predicate)
    || left.atom.atom_id.localeCompare(right.atom.atom_id));
  const atomWindowCount = Math.max(1, Math.ceil(rows.length / 500));
  const safeAtomWindow = Math.min(atomWindow, atomWindowCount - 1);
  const firstAtomRow = safeAtomWindow * 500;
  return <div className="view-content atom-view">
    <div className="view-heading">
      <div><span className="eyebrow">strict as-of projection</span><h2>Atomspace inspector</h2></div>
      <p>{rows.length.toLocaleString()} indexed atoms at T{state.cursor.turn}.{state.cursor.seq}</p>
    </div>
    <div className="table-tools">
      <input aria-label="Search atoms" placeholder="predicate, argument, entity…" value={search}
        onChange={(event) => { setAtomWindow(0); onSearch(event.target.value); }} />
      <select aria-label="Atom channel" value={channel}
        onChange={(event) => {
          setAtomWindow(0);
          onChannel(event.target.value as "all" | "crisp" | "uncertain");
        }}>
        <option value="all">all channels</option><option value="crisp">crisp</option>
        <option value="uncertain">uncertain</option>
      </select>
      <div className="atom-window-controls" aria-label="Atom row windows">
        <button disabled={safeAtomWindow === 0}
          onClick={() => setAtomWindow(Math.max(0, safeAtomWindow - 1))}>‹</button>
        <span>{rows.length ? firstAtomRow + 1 : 0}–{Math.min(rows.length, firstAtomRow + 500)} / {rows.length}</span>
        <button disabled={safeAtomWindow + 1 >= atomWindowCount}
          onClick={() => setAtomWindow(safeAtomWindow + 1)}>›</button>
      </div>
    </div>
    <div className="atom-table" role="table">
      <div className="atom-row atom-head" role="row">
        <span>predicate</span><span>arguments</span><span>truth value</span><span>provenance</span><span>revised</span>
      </div>
      {rows.slice(firstAtomRow, firstAtomRow + 500).map((row) => <button className={`atom-row ${row.duplicateProvenance ? "duplicate" : ""}`}
        role="row" key={row.atom.atom_id} onClick={() => onSelect({ kind: "atom", value: row })}>
        <strong>{row.atom.predicate}</strong>
        <span>{row.atom.args.map(String).join(" · ")}</span>
        <span className={row.atom.crisp ? "tv-crisp" : "tv-uncertain"}>
          {row.atom.tv.strength.toFixed(2)} / {row.atom.tv.confidence.toFixed(2)}
        </span>
        <span>{row.atom.provenance_ids.length}</span><span>T{row.lastTurn}</span>
      </button>)}
    </div>
  </div>;
}

function PlanBoard({ state, onSelect }: { state: ReplayState; onSelect: (selection: Selection) => void }) {
  const plans = [...state.plans.values()];
  if (!plans.length) return <LoggingGap title="No plan events at this cursor"
    detail="Plan timing and resource values are rendered only from plan_created events." />;
  return <div className="view-content"><div className="view-heading">
    <div><span className="eyebrow">scheduled intent</span><h2>Plan board</h2></div>
  </div><div className="plan-grid">{plans.map((plan) => {
    const invalidation = state.invalidations.get(plan.plan_id);
    const invalidPayload = invalidation?.payload;
    return <article key={plan.plan_id}
    className={`plan-card status-${plan.status.toLowerCase()}`}>
    <button className="plan-title" onClick={() => onSelect({ kind: "plan", value: plan })}>
    <span className="status-chip">{plan.status}</span><h3>{plan.goal_atom_id}</h3>
    <div className="plan-metrics"><span>ETA <strong>{plan.predicted_turns ?? "—"}</strong></span>
      <span>cost <strong>{plan.scheduler_cost}</strong></span><span>grade <strong>{plan.feasibility_grade}</strong></span></div>
    </button>
    <ol>{plan.steps.map((step) => <li key={step.step_id}><button
      onClick={() => onSelect({ kind: "step", value: step, plan })}><span>{step.kind}</span>
      <strong>pred T{step.predicted_turn}</strong><strong>actual {step.actual_turn === null ? "—" : `T${step.actual_turn}`}</strong>
      <small>{step.status}</small></button></li>)}</ol>
    {plan.ledger.length > 0 && <div className="ledger"><h4>Resource ledger</h4>
      {plan.ledger.map((entry, index) => <div key={`${entry.step_id}-${entry.resource}-${index}`}>
        <strong>{entry.resource}</strong><span>{entry.available}</span><span>−{entry.allocated}</span><span>={entry.remaining}</span>
      </div>)}</div>}
    {plan.assumptions.length > 0 && <div className="assumptions"><h4>Assumption margins</h4>
      {plan.assumptions.map((assumption) => {
        const confidence = state.atoms.get(assumption.atom_id)?.atom.tv.confidence
          ?? assumption.accepted_tv.confidence;
        const near = confidence >= assumption.threshold && confidence - assumption.threshold <= 0.05;
        return <div key={assumption.atom_id} className={near ? "near" : confidence < assumption.threshold ? "broken" : ""}>
          <strong>{assumption.atom_id}</strong><span>{confidence.toFixed(2)} / {assumption.threshold.toFixed(2)}</span>
          <meter min={0} max={1} low={assumption.threshold} value={confidence} />
        </div>;
      })}</div>}
    {invalidation && <div className="invalidation-detail" role="alert">
      <strong>{String(invalidPayload?.reason ?? "invalidated")}</strong>
      <span>broken: {String((invalidPayload?.broken_assumption as { atom_id?: string } | undefined)?.atom_id ?? "unknown")}</span>
      <small>reused {(invalidPayload?.reused_subtree_hashes as unknown[] | undefined)?.length ?? 0} · re-derived {(invalidPayload?.rederived_subtree_hashes as unknown[] | undefined)?.length ?? 0}</small>
    </div>}
  </article>})}</div></div>;
}

const coordinate = (atom: Atom): [number, number] | undefined => {
  const values = atom.args.filter((value): value is number => typeof value === "number");
  return values.length >= 2 ? [values.at(-2)!, values.at(-1)!] : undefined;
};

function MapOverlay({ state, selection, onSelect }: {
  state: ReplayState; selection?: Selection; onSelect: (selection: Selection) => void;
}) {
  const snapshot = state.snapshots.at(-1);
  if (!snapshot) return <LoggingGap title="No map snapshot at this cursor"
    detail="The map never infers tiles or paths without a state_snapshot map payload." />;
  const map = snapshot.payload.map as Record<string, unknown> | undefined;
  const width = Math.min(30, Number(map?.width ?? 0));
  const height = Math.min(20, Number(map?.height ?? 0));
  if (!width || !height) return <LoggingGap title="Map dimensions were not logged"
    detail="Emit width and height in state_snapshot.map; the view will not guess them." />;
  const visible = new Set((Array.isArray(map?.visible) ? map.visible : []).map((row) => JSON.stringify(row)));
  const positioned = [...state.atoms.values()].filter((row) => coordinate(row.atom));
  const selectedPlan = selection?.kind === "plan" ? selection.value
    : selection?.kind === "step" ? selection.plan : undefined;
  const planned = new Map<string, PlanStep>();
  for (const step of selectedPlan?.steps ?? []) {
    const spatial = step.spatial as { x?: number; y?: number } | null;
    if (spatial && Number.isInteger(spatial.x) && Number.isInteger(spatial.y)) {
      planned.set(`${spatial.x},${spatial.y}`, step);
    }
  }
  const invalid = selectedPlan ? state.invalidations.get(selectedPlan.plan_id) : undefined;
  return <div className="view-content map-view"><div className="view-heading">
    <div><span className="eyebrow">event-provided spatial state</span><h2>Map overlay</h2></div>
    <p>{width}×{height} logged tiles · {positioned.length} markers</p>
  </div><div className="tile-map" style={{ "--map-width": width } as React.CSSProperties}>
    {Array.from({ length: width * height }, (_, index) => {
      const x = index % width; const y = Math.floor(index / width);
      const marker = positioned.find((row) => {
        const point = coordinate(row.atom); return point?.[0] === x && point[1] === y;
      });
      const step = planned.get(`${x},${y}`);
      const broken = invalid && marker?.atom.atom_id ===
        (invalid.payload.broken_assumption as { atom_id?: string } | undefined)?.atom_id;
      return <button key={`${x}-${y}`} aria-label={`Tile ${x},${y}`}
        className={`map-tile ${visible.has(JSON.stringify([x, y])) ? "visible" : "fog"} ${marker ? "has-marker" : ""} ${step ? "planned" : ""} ${broken ? "broken" : ""}`}
        onClick={() => marker && onSelect({ kind: "atom", value: marker })}>
        {marker && <span className="uncertain-marker" style={{ opacity: marker.atom.tv.confidence }}
          title={`${formatAtom(marker.atom)} confidence ${marker.atom.tv.confidence.toFixed(2)}`} />}
        {step && <em>T{step.predicted_turn}</em>}
      </button>;
    })}
  </div><div className="map-legend"><span>● uncertain marker opacity = logged confidence</span>
    <span>□ fog as logged</span><span>◈ selected plan ETA</span></div></div>;
}

function EpistemicAudit({ state, onSelect }: {
  state: ReplayState; onSelect: (selection: Selection) => void;
}) {
  const proposals = state.events.filter((event) => event.type === "llm_proposal");
  const claimCount = proposals.reduce((count, event) => count
    + (Array.isArray(event.payload.claims) ? event.payload.claims.length : 0), 0);
  const writeThrough = [...state.metrics].reverse().find(
    (event) => event.payload.name === "confabulation_write_through");
  const writeValue = writeThrough ? Number(writeThrough.payload.value) : undefined;
  return <div className="view-content audit-view"><div className="view-heading">
    <div><span className="eyebrow">three-sink verification</span><h2>Epistemic audit</h2></div>
  </div><div className={`write-through ${writeValue === undefined ? "unknown" : writeValue ? "alarm" : "clear"}`} role="status">
    <span>confabulation write-through</span><strong>{writeValue ?? "—"}</strong>
    <small>{writeThrough ? "event-provided metric" : "no metric logged · unknown"}</small>
  </div><div className="funnel" aria-label="Verification funnel">
    <div><strong>{claimCount}</strong><span>claims made</span></div>
    <div><strong>{state.verifications.length}</strong><span>verified</span></div>
    <div><strong>{state.quarantines.length}</strong><span>quarantined</span></div>
    <div className={writeValue ? "alarm" : ""}><strong>{writeValue ?? "—"}</strong><span>write-throughs</span></div>
  </div><div className="quarantine-table"><div className="quarantine-row head">
    <span>turn</span><span>claim verbatim</span><span>failed check</span><span>evidence</span></div>
    {state.quarantines.map((event) => <button className="quarantine-row" key={event.event_id}
      onClick={() => onSelect({ kind: "event", value: event })}>
      <span>T{event.turn}</span><strong>{String(event.payload.claim)}</strong>
      <span>{String(event.payload.failed_check)}</span>
      <span>{Array.isArray(event.payload.evidence_atoms) ? event.payload.evidence_atoms.length : 0}</span>
    </button>)}
  </div></div>;
}

function MetricsDashboard({ state, onSelect }: {
  state: ReplayState; onSelect: (selection: Selection) => void;
}) {
  if (!state.metrics.length) return <LoggingGap title="No metric samples at this cursor"
    detail="Calibration, intervals, and ablations are rendered only from metric_sample events." />;
  const conditions = [...new Set(state.metrics.map((event) =>
    String((event.payload.labels as Record<string, string> | undefined)?.condition ?? "run")))];
  return <div className="view-content metrics-view"><div className="view-heading">
    <div><span className="eyebrow">harness-emitted values</span><h2>Metrics dashboard</h2></div>
    <p>{state.metrics.length} samples · UI calculations disabled</p>
  </div><div className="condition-strip">{conditions.map((condition) => <span key={condition}>{condition}</span>)}</div>
  <div className="metric-grid">{state.metrics.slice(-500).map((event) => {
    const labels = event.payload.labels as Record<string, string> | undefined;
    return <button className="metric-card" key={event.event_id}
      onClick={() => onSelect({ kind: "event", value: event })}>
      <span>{String(labels?.condition ?? "run")} · {String(labels?.statistic ?? "sample")}</span>
      <strong>{Number(event.payload.value).toLocaleString()}</strong>
      <h3>{String(event.payload.name)}</h3><small>{String(event.payload.unit)}</small>
    </button>;
  })}</div></div>;
}

function LoggingGap({ title, detail }: { title: string; detail: string }) {
  return <div className="logging-gap"><span>logging gap</span><h2>{title}</h2><p>{detail}</p></div>;
}

function Inspector({ selection }: { selection?: Selection }) {
  if (!selection) return <aside className="inspector empty"><span className="eyebrow">inspector</span>
    <h2>Nothing selected</h2><p>Select an event, proof node, atom, or plan. Its exact trace payload will appear here.</p></aside>;
  let title = "";
  let subtitle = "";
  let value: unknown;
  let history: ReactNode = null;
  if (selection.kind === "event") {
    title = selection.value.type; subtitle = `${selection.value.turn}.${selection.value.seq}`;
    value = selection.value;
  } else if (selection.kind === "node") {
    title = selection.value.kind; subtitle = selection.value.node_id; value = selection.value;
  } else if (selection.kind === "plan") {
    title = selection.value.plan_id; subtitle = selection.value.status; value = selection.value;
  } else if (selection.kind === "step") {
    title = selection.value.kind; subtitle = `${selection.plan.plan_id} / ${selection.value.step_id}`;
    value = selection.value;
  } else {
    title = selection.value.atom.predicate; subtitle = selection.value.atom.atom_id;
    value = selection.value.atom;
    history = <div className="revision-history"><h3>Revision history</h3>
      {selection.value.history.map((entry) => <div key={`${entry.eventId}-${entry.operation}`}>
        <span>T{entry.turn}.{entry.seq}</span><strong>{entry.operation}</strong>
        <small>{entry.tv.strength.toFixed(2)} / {entry.tv.confidence.toFixed(2)}</small>
      </div>)}</div>;
  }
  return <aside className="inspector"><span className="eyebrow">inspector / {selection.kind}</span>
    <h2>{title}</h2><p className="mono-id">{subtitle}</p>{history}
    <pre>{JSON.stringify(value, null, 2)}</pre></aside>;
}

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

function ArtifactBrowser({ open, onClose, onLoad }: {
  open: boolean;
  onClose: () => void;
  onLoad: (entry: ArtifactCatalogEntry) => Promise<void>;
}) {
  const [entries, setEntries] = useState<ArtifactCatalogEntry[]>([]);
  const [query, setQuery] = useState("");
  const [catalogStatus, setCatalogStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [loadingPath, setLoadingPath] = useState<string>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setCatalogStatus("loading");
    setError(undefined);
    void fetchArtifactCatalog(controller.signal).then((catalog) => {
      setEntries(catalog.entries);
      setCatalogStatus("ready");
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setCatalogStatus("error");
      setError(reason instanceof Error ? reason.message : "Artifact catalog unavailable");
    });
    return () => controller.abort();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === "Escape" && !loadingPath) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [loadingPath, onClose, open]);

  if (!open) return null;
  const normalizedQuery = query.trim().toLowerCase();
  const matches = normalizedQuery
    ? entries.filter((entry) => [
      entry.experiment, entry.cohort, entry.arm, entry.condition, entry.run, entry.path,
    ].some((value) => value?.toLowerCase().includes(normalizedQuery)))
    : entries;
  const visible = matches.slice(0, 200);

  const select = async (entry: ArtifactCatalogEntry): Promise<void> => {
    setLoadingPath(entry.path);
    setError(undefined);
    try {
      await onLoad(entry);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Trace could not be loaded");
    } finally {
      setLoadingPath(undefined);
    }
  };

  return <div className="artifact-backdrop" onMouseDown={(event) => {
    if (event.target === event.currentTarget && !loadingPath) onClose();
  }}>
    <section className="artifact-dialog" role="dialog" aria-modal="true"
      aria-labelledby="artifact-dialog-title">
      <header>
        <div>
          <span className="eyebrow">repository / generated evidence</span>
          <h2 id="artifact-dialog-title">Experiment traces</h2>
          <p>Select an active game stream. Archived failed attempts stay excluded.</p>
        </div>
        <button aria-label="Close experiment traces" onClick={onClose}
          disabled={Boolean(loadingPath)}>×</button>
      </header>
      <div className="artifact-tools">
        <label>
          <span>Filter traces</span>
          <input autoFocus aria-label="Filter experiment traces"
            placeholder="experiment, cohort, arm, seed…" value={query}
            onChange={(event) => setQuery(event.target.value)} />
        </label>
        <div>
          <strong>{matches.length.toLocaleString()}</strong>
          <span>matches / {entries.length.toLocaleString()} active traces</span>
        </div>
      </div>
      {catalogStatus === "loading" && <div className="artifact-state">Scanning generated artifacts…</div>}
      {catalogStatus === "error" && <div className="artifact-state error">{error}</div>}
      {catalogStatus === "ready" && visible.length === 0 &&
        <div className="artifact-state">No generated traces match this filter.</div>}
      {visible.length > 0 && <div className="artifact-list" aria-label="Generated experiment traces">
        {visible.map((entry) => <button key={entry.path}
          aria-label={`Load ${entry.label}`}
          disabled={Boolean(loadingPath)}
          className={loadingPath === entry.path ? "loading" : ""}
          onClick={() => void select(entry)}>
          <span className="artifact-kind">{entry.arm ?? "trace"}</span>
          <span className="artifact-name">
            <strong>{entry.experiment}</strong>
            <small>{[entry.cohort, entry.run].filter(Boolean).join(" / ")}</small>
          </span>
          <span className="artifact-meta">
            <strong>{formatBytes(entry.sizeBytes)}</strong>
            <small>{new Date(entry.modifiedAt).toLocaleString()}</small>
          </span>
          <span className="artifact-action">
            {loadingPath === entry.path ? "loading…" : "open →"}
          </span>
        </button>)}
      </div>}
      {matches.length > visible.length && <footer>
        Showing the newest {visible.length} matches. Refine the filter to find an older trace.
      </footer>}
      {error && catalogStatus !== "error" && <div className="artifact-load-error" role="alert">{error}</div>}
    </section>
  </div>;
}

export function App({ initialText = demoTrace }: { initialText?: string }) {
  const eventLimit = 250_000;
  const initial = useMemo(() => parseJsonl(initialText), [initialText]);
  const [events, setEvents] = useState<TraceEvent[]>(() => initial.events.sort(eventOrder));
  const [invalidLines, setInvalidLines] = useState<QuarantinedLine[]>(initial.quarantined);
  const terminal = maxCursor(events);
  const decoded = useMemo(() => decodeUrlState(window.location.search, terminal), []);
  const [cursor, setCursor] = useState<Cursor>(decoded.cursor);
  const [view, setView] = useState<ViewName>(decoded.view);
  const [selection, setSelection] = useState<Selection>();
  const [search, setSearch] = useState(decoded.search ?? "");
  const [channel, setChannel] = useState<"all" | "crisp" | "uncertain">(decoded.channel ?? "all");
  const [mode, setMode] = useState<"replay" | "live">("replay");
  const [artifactBrowserOpen, setArtifactBrowserOpen] = useState(false);
  const [traceSource, setTraceSource] = useState("bundled demonstration");
  const [liveStatus, setLiveStatus] = useState<LiveStatus>("idle");
  const [liveUrl, setLiveUrl] = useState(
    String(import.meta.env.VITE_FREECIV_LIVE_URL ?? "ws://127.0.0.1:8765"));
  const [liveGameId, setLiveGameId] = useState(initial.events[0]?.game_id ?? "freeciv-live");
  const liveClient = useRef<LiveEventClient | undefined>(undefined);
  const state = useMemo(() => foldEvents(events, cursor), [events, cursor]);

  useEffect(() => {
    if (!decoded.selected || selection) return;
    const event = state.eventsById.get(decoded.selected);
    if (event) { setSelection({ kind: "event", value: event }); return; }
    const atom = state.atoms.get(decoded.selected);
    if (atom) { setSelection({ kind: "atom", value: atom }); return; }
    const plan = state.plans.get(decoded.selected);
    if (plan) { setSelection({ kind: "plan", value: plan }); return; }
    for (const candidate of state.plans.values()) {
      const step = candidate.steps.find((item) => item.step_id === decoded.selected);
      if (step) { setSelection({ kind: "step", value: step, plan: candidate }); return; }
    }
    for (const proof of state.proofs) {
      const node = proof.result.proof.nodes.find((candidate) => candidate.node_id === decoded.selected);
      if (node) { setSelection({ kind: "node", value: node }); return; }
    }
  }, [decoded.selected, selection, state]);
  useEffect(() => {
    const handler = (event: Event) => setView((event as CustomEvent<ViewName>).detail);
    window.addEventListener("observatory:view", handler);
    return () => window.removeEventListener("observatory:view", handler);
  }, []);
  useEffect(() => {
    const selected = selection?.kind === "event" ? selection.value.event_id
      : selection?.kind === "atom" ? selection.value.atom.atom_id
      : selection?.kind === "node" ? selection.value.node_id
          : selection?.kind === "plan" ? selection.value.plan_id
            : selection?.kind === "step" ? selection.value.step_id : undefined;
    window.history.replaceState(null, "", encodeUrlState({ view, cursor, selected, search, channel }));
  }, [view, cursor, selection, search, channel]);
  useEffect(() => () => liveClient.current?.stop(), []);

  const applyReplay = (parsed: ParseResult, source: string): void => {
    const sorted = parsed.events.sort(eventOrder);
    if (sorted.length > eventLimit) {
      parsed.quarantined.push({
        line: 0, raw: "", reason: `E_EVENT_LIMIT: ${sorted.length} exceeds ${eventLimit}`,
      });
      sorted.splice(eventLimit);
    }
    liveClient.current?.stop();
    setMode("replay"); setLiveStatus("idle");
    setEvents(sorted); setInvalidLines(parsed.quarantined); setCursor(maxCursor(sorted));
    setLiveGameId(sorted[0]?.game_id ?? "freeciv-live");
    setTraceSource(source);
    setSelection(undefined);
  };

  const loadFile = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = event.target.files?.[0];
    if (!file) return;
    applyReplay(await parseJsonlStream(file.stream()), file.name);
    event.target.value = "";
  };

  const loadArtifact = async (entry: ArtifactCatalogEntry): Promise<void> => {
    const parsed = await parseJsonlStream(await fetchArtifactEventStream(entry));
    if (parsed.events.length === 0) {
      throw new Error("The selected artifact contains no valid trace events");
    }
    applyReplay(parsed, entry.label);
  };

  const stopLive = (): void => {
    liveClient.current?.stop();
    liveClient.current = undefined;
    setMode("replay"); setLiveStatus("idle");
  };

  const startLive = (): void => {
    liveClient.current?.stop();
    setEvents([]); setInvalidLines([]); setCursor({ turn: 0, seq: 0 });
    setSelection(undefined); setMode("live");
    const client = new LiveEventClient({
      url: liveUrl, gameId: liveGameId, after: { turn: -1, seq: -1 },
      onStatus: setLiveStatus,
      onAnomaly: (anomaly) => setInvalidLines((prior) => [...prior, {
        line: 0, raw: anomaly.raw ?? "", reason: `${anomaly.code}: ${anomaly.message}`,
      }]),
      onEvent: (event) => setEvents((prior) => {
        if (prior.length >= eventLimit) {
          setInvalidLines((items) => [...items, {
            line: 0, raw: "", reason: `E_EVENT_LIMIT: live trace exceeds ${eventLimit}`,
          }]);
          client.stop();
          return prior;
        }
        setCursor(cursorOf(event));
        return [...prior, event];
      }),
    });
    liveClient.current = client;
    client.start();
  };

  const main = view === "timeline" ? <Timeline state={state} selection={selection} onSelect={setSelection} />
    : view === "proofs" ? <ProofExplorer state={state} selection={selection} onSelect={setSelection} />
      : view === "atoms" ? <Atomspace state={state} onSelect={setSelection} search={search}
        channel={channel} onSearch={setSearch} onChannel={setChannel} />
        : view === "plans" ? <PlanBoard state={state} onSelect={setSelection} />
          : view === "map" ? <MapOverlay state={state} selection={selection} onSelect={setSelection} />
            : view === "audit" ? <EpistemicAudit state={state} onSelect={setSelection} />
              : view === "metrics" ? <MetricsDashboard state={state} onSelect={setSelection} />
                : <LoggingGap title={`${NAV.find((item) => item.view === view)?.label} awaits its event milestone`}
                  detail="This surface never derives missing data from another event type." />;

  return <div className="app-shell">
    <Header events={events} state={state} mode={mode} status={liveStatus} gameId={liveGameId} />
    <Scrubber events={events} cursor={cursor} onChange={setCursor} />
    {(invalidLines.length > 0 || state.unknown.length > 0 || state.loggingGaps.length > 0) &&
      <div className="anomaly-bar" role="alert"><strong>Trace anomalies visible</strong>
        <span>{invalidLines.length} invalid lines</span><span>{state.unknown.length} unknown events</span>
        <span>{state.loggingGaps.length} logging gaps</span></div>}
    <div className="workspace">
      <nav className="side-nav" aria-label="Observability views">
        <div className="mode-switch">
          <button className={mode === "replay" ? "active" : ""} onClick={stopLive}>Replay</button>
          <button className={mode === "live" ? "active" : ""} onClick={startLive}>Live</button>
        </div>
        <button className="artifact-browser-trigger" onClick={() => setArtifactBrowserOpen(true)}>
          <span>↗</span>Experiment traces
        </button>
        <div className="live-config" aria-label="Live event-tail configuration">
          <label>endpoint<input aria-label="Live endpoint" value={liveUrl}
            onChange={(event) => setLiveUrl(event.target.value)} /></label>
          <label>game<input aria-label="Live game ID" value={liveGameId}
            onChange={(event) => setLiveGameId(event.target.value)} /></label>
          <small>{liveStatus} · resume/backfill enabled</small>
        </div>
        {NAV.map((item) => <button key={item.view} className={view === item.view ? "active" : ""}
          onClick={() => setView(item.view)}><span>{item.key}</span>{item.label}</button>)}
        <label className="file-loader">Load JSONL<input type="file" accept=".jsonl,application/x-ndjson"
          onChange={(event) => void loadFile(event)} /></label>
        <div className="trace-source" title={traceSource}>
          <span>loaded trace</span><strong>{traceSource}</strong>
        </div>
        <div className="schema-lock"><span>schema lock</span><strong>v1.0</strong><small>strict / lossless</small></div>
      </nav>
      <main>{main}</main>
      <Inspector selection={selection} />
    </div>
    <ArtifactBrowser open={artifactBrowserOpen} onClose={() => setArtifactBrowserOpen(false)}
      onLoad={loadArtifact} />
  </div>;
}
