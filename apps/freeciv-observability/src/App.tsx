import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import type {
  Atom, Plan, PlanStep, PlnResult, ProofNode, ProductionState,
  TechnologyCatalog, TechnologyProgress, UnitLifecycle,
} from "../../../schemas/freeciv-events/v1/types.generated";
import demoTrace from "../../../Autotests/fixtures/freeciv-events/v1/normal-crisp.jsonl?raw";
import {
  type AtomView, type Cursor, type ReplayState, type TraceEvent,
  cursorOf, eventOrder, formatAtom, maxCursor,
} from "./events";
import {
  type ArtifactCatalogEntry, type ArtifactPairQuality,
  artifactPairQuality,
  fetchArtifactCatalog,
  fetchArtifactEventStream,
  findPairedArtifact,
} from "./artifacts";
import { LiveEventClient, type LiveStatus } from "./live";
import { ancestry, densityByTurn, foldEvents } from "./store";
import {
  parseJsonl, parseJsonlStream, type ParseResult, type QuarantinedLine,
} from "./validation";
import { decodeUrlState, encodeUrlState, type ViewName } from "./url-state";
import {
  CHART_COLORS, Sparkline, TurnHeatmap, ValueBar, humanize,
} from "./visuals";

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
  { view: "pfpln", label: "PF-PLN", key: "08" },
  { view: "technology", label: "Technology", key: "09" },
  { view: "economy", label: "Economy & production", key: "10" },
  { view: "forces", label: "Unit lifecycle", key: "11" },
  { view: "about", label: "How it works", key: "12" },
];

const STAGES: Array<{ name: string; types: Set<string> }> = [
  { name: "State ingest", types: new Set([
    "state_snapshot", "technology_progress", "production_state", "unit_lifecycle",
    "observation", "revision",
  ]) },
  { name: "Proposal", types: new Set(["llm_proposal", "quarantine"]) },
  { name: "Verification", types: new Set(["verification", "grounded_check"]) },
  { name: "PLN", types: new Set(["pln_query", "pln_result"]) },
  { name: "PF-PLN", types: new Set([
    "pressure_propagated", "operation_scored", "conductance_updated",
    "rule_proposed", "rule_validated", "llm_call_scheduled",
    "llm_gateway_result", "rule_parameter_updated",
  ]) },
  { name: "Plan", types: new Set(["plan_created", "plan_invalidated", "plan_step_executed"]) },
  { name: "Action", types: new Set(["action_sent", "action_result"]) },
];

const seqAtTurn = (events: TraceEvent[], turn: number): number =>
  Math.max(0, ...events.filter((event) => event.turn === turn).map((event) => event.seq));

function Header({ events, state, mode, status, gameId, focus, inspectorOpen,
  onFocus, onInspector }: {
  events: TraceEvent[]; state: ReplayState; mode: "replay" | "live";
  status: LiveStatus; gameId: string;
  focus: boolean; inspectorOpen: boolean;
  onFocus: () => void; onInspector: () => void;
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
    <div className="layout-controls" aria-label="Workspace layout">
      <button className={focus ? "active" : ""} onClick={onFocus}
        aria-pressed={focus}>focus</button>
      <button className={inspectorOpen ? "active" : ""} onClick={onInspector}
        aria-pressed={inspectorOpen}>inspector</button>
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
  const markers = new Map<number, Set<string>>();
  const mark = (turn: number, value: string): void => {
    const values = markers.get(turn) ?? new Set<string>();
    values.add(value);
    markers.set(turn, values);
  };
  for (const event of events) {
    if (event.type === "plan_invalidated") mark(event.turn, "invalidated");
    if (event.type === "quarantine") mark(event.turn, "quarantine");
    if (event.type === "pressure_propagated") mark(event.turn, "pressure");
    if (event.type === "conductance_updated") mark(event.turn, "learning");
    if (event.type === "metric_sample" && [
      "cities_founded", "settlement_completions", "score_gain", "game_win",
    ].includes(String(event.payload.name))) mark(event.turn, "outcome");
  }
  return <section className="scrubber" aria-label="Global replay cursor">
    <div className="scrubber-label"><span>global cursor</span><strong>Turn {cursor.turn}</strong></div>
    <div className="scrubber-track">
      <div className="density-strip" aria-label="Event density by turn">
        {Array.from({ length: maximum - minimum + 1 }, (_, offset) => minimum + offset).map((turn) =>
          <button key={turn} aria-label={`Turn ${turn}, ${density.get(turn) ?? 0} events`}
            className={`density-tick ${[...markers.get(turn) ?? []].join(" ")} ${turn === cursor.turn ? "active" : ""}`}
            title={[...markers.get(turn) ?? []].join(" · ") || "event activity"}
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

function Timeline({ state, selection, onSelect, onCursor }: {
  state: ReplayState; selection?: Selection; onSelect: (selection: Selection) => void;
  onCursor?: (cursor: Cursor) => void;
}) {
  const [turnWindow, setTurnWindow] = useState<20 | 60 | 0>(60);
  const selectedEvent = selection?.kind === "event" ? selection.value : undefined;
  const highlighted = selectedEvent?.type === "action_sent"
    ? ancestry(state, selectedEvent.event_id) : new Set<string>();
  const allTurns = [...new Set(state.events.map((event) => event.turn))].sort((a, b) => a - b);
  const turns = turnWindow ? allTurns.slice(-turnWindow) : allTurns;
  const heatmapRows = STAGES.map((stage, index) => {
    const counts = new Map<number, number>();
    for (const event of state.events) {
      if (stage.types.has(event.type)) {
        counts.set(event.turn, (counts.get(event.turn) ?? 0) + 1);
      }
    }
    return { label: stage.name, counts, color: CHART_COLORS[index % CHART_COLORS.length] };
  });
  return <div className="view-content timeline-view">
    <div className="view-heading">
      <div><span className="eyebrow">causal replay</span><h2>Decision timeline</h2></div>
      <p>Select an action to illuminate its complete ancestry. Every edge is read from <code>caused_by</code>.</p>
    </div>
    <section className="timeline-overview">
      <header><div><span className="eyebrow">turn × control-stage density</span>
        <h3>Decision activity matrix</h3></div>
        <div className="segmented-control" aria-label="Timeline turn window">
          {([20, 60, 0] as const).map((window) => <button key={window}
            className={turnWindow === window ? "active" : ""}
            onClick={() => setTurnWindow(window)}>{window || "all"}</button>)}
        </div>
      </header>
      <TurnHeatmap rows={heatmapRows} turns={turns}
        label="Decision activity by turn and control stage"
        onTurn={(turn) => onCursor?.({ turn, seq: seqAtTurn(state.events, turn) })} />
      <div className="cursor-marker-legend">
        <span className="pressure">pressure</span><span className="learning">learning</span>
        <span className="outcome">outcome</span><span className="invalidated">invalidation</span>
      </div>
    </section>
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

function ProofGraph({ result, onSelect }: {
  result: PlnResult; onSelect: (selection: Selection) => void;
}) {
  const nodesById = new Map(result.proof.nodes.map((node) => [node.node_id, node]));
  const depthById = new Map<string, number>([[result.proof.root_node_id, 0]]);
  const queue = [result.proof.root_node_id];
  while (queue.length) {
    const id = queue.shift();
    if (!id) continue;
    const depth = depthById.get(id) ?? 0;
    for (const premise of nodesById.get(id)?.premise_node_refs ?? []) {
      if (!depthById.has(premise)) {
        depthById.set(premise, depth + 1);
        queue.push(premise);
      }
    }
  }
  const visible = result.proof.nodes.filter((node) => depthById.has(node.node_id)).slice(0, 120);
  const visibleIds = new Set(visible.map((node) => node.node_id));
  const levels = new Map<number, ProofNode[]>();
  for (const node of visible) {
    const depth = depthById.get(node.node_id) ?? 0;
    levels.set(depth, [...levels.get(depth) ?? [], node]);
  }
  const maximumDepth = Math.max(0, ...levels.keys());
  const height = Math.max(230, ...[...levels.values()].map((level) => level.length * 55 + 40));
  const position = new Map<string, { x: number; y: number }>();
  for (const [depth, level] of levels) {
    level.forEach((node, index) => position.set(node.node_id, {
      x: 60 + depth * (800 / Math.max(1, maximumDepth)),
      y: 28 + (index + 0.5) * ((height - 50) / level.length),
    }));
  }
  return <div className="proof-graph-wrap">
    <svg className="proof-graph" viewBox={`0 0 920 ${height}`} role="img"
      aria-label="Proof dependency graph">
      <defs><marker id="proof-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4"
        orient="auto"><path d="M0,0 L8,4 L0,8 z" /></marker></defs>
      {visible.flatMap((node) => node.premise_node_refs.filter((id) => visibleIds.has(id))
        .map((premise) => {
          const from = position.get(node.node_id);
          const to = position.get(premise);
          if (!from || !to) return null;
          return <line key={`${node.node_id}-${premise}`}
            x1={from.x + 11} y1={from.y} x2={to.x - 11} y2={to.y}
            className="proof-edge" markerEnd="url(#proof-arrow)" />;
        }))}
      {visible.map((node) => {
        const point = position.get(node.node_id);
        if (!point) return null;
        return <g key={node.node_id} transform={`translate(${point.x} ${point.y})`}
          className={`proof-graph-node ${node.satisfied ? "satisfied" : "blocked"} ${node.crisp ? "crisp" : "uncertain"}`}
          role="button" tabIndex={0} aria-label={`${node.kind} ${formatAtom(node.atom)}`}
          onClick={() => onSelect({ kind: "node", value: node })}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") onSelect({ kind: "node", value: node });
          }}>
          <circle r={node.kind === "goal" ? 12 : 9} />
          <text x="16" y="-2">{humanize(node.kind)}</text>
          <text x="16" y="10" className="proof-graph-label">{node.atom.predicate}</text>
          <title>{formatAtom(node.atom)} · confidence {node.tv.confidence}</title>
        </g>;
      })}
    </svg>
    {result.proof.nodes.length > visible.length && <span className="graph-limit">
      Showing the first {visible.length} logged nodes of {result.proof.nodes.length}
    </span>}
  </div>;
}

export function ProofExplorer({ state, selection, onSelect }: {
  state: ReplayState; selection?: Selection; onSelect: (selection: Selection) => void;
}) {
  const [selectedProofId, setSelectedProofId] = useState("latest");
  const [comparison, setComparison] = useState(-1);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(() => new Set());
  const [proofWindow, setProofWindow] = useState(0);
  const [displayMode, setDisplayMode] = useState<"split" | "graph" | "list">("split");
  const explicitProof = state.proofs.find(
    (record) => record.event.event_id === selectedProofId);
  const proofRecord = selectedProofId === "latest" || !explicitProof
    ? state.proofs.at(-1) : explicitProof;
  if (!proofRecord) return <LoggingGap title="No proof trace at this cursor"
    detail="The view will not reconstruct a proof from atoms. Emit pln_result with a lossless proof tree." />;
  const result = proofRecord.result;
  const latestProof = state.proofs.at(-1);
  const isLatestProof = proofRecord.event.event_id === latestProof?.event.event_id;
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
        <div className="segmented-control" aria-label="Proof display">
          {(["split", "graph", "list"] as const).map((mode) => <button key={mode}
            className={displayMode === mode ? "active" : ""}
            onClick={() => setDisplayMode(mode)}>{mode}</button>)}
        </div>
        <label>proof <select aria-label="Proof"
          value={selectedProofId === "latest" || !explicitProof ? "latest" : selectedProofId}
          onChange={(event) => {
            setSelectedProofId(event.target.value);
            setExpandedNodes(new Set());
            setProofWindow(0);
          }}>
          <option value="latest">latest at cursor · T{latestProof?.event.turn}</option>
          {state.proofs.map((record) => <option key={record.event.event_id}
            value={record.event.event_id}>
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
    <section className={`proof-recency ${isLatestProof ? "current" : "historical"}`}
      aria-label="Proof recency">
      <strong>{isLatestProof ? "Current proof at cursor" : "Historical proof selected"}</strong>
      <span>emitted T{proofRecord.event.turn}.{proofRecord.event.seq} ·
        {" "}cursor T{state.cursor.turn}.{state.cursor.seq}</span>
      {!isLatestProof && <button onClick={() => setSelectedProofId("latest")}>
        return to latest
      </button>}
    </section>
    {rows.length > 500 && <div className="virtual-controls" aria-label="Proof node windows">
      <button disabled={safeProofWindow === 0}
        onClick={() => setProofWindow(Math.max(0, safeProofWindow - 1))}>previous 500</button>
      <span>{firstProofRow + 1}–{Math.min(rows.length, firstProofRow + 500)} of {rows.length} visible nodes</span>
      <button disabled={safeProofWindow + 1 >= proofWindowCount}
        onClick={() => setProofWindow(safeProofWindow + 1)}>next 500</button>
    </div>}
    <div className={`proof-workbench mode-${displayMode}`}>
    {displayMode !== "list" && <ProofGraph result={result} onSelect={onSelect} />}
    {displayMode !== "graph" && <div className="proof-grid" role="tree" aria-label="AND OR proof tree">
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
    </div>}
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
      {result.unsatisfied_frontier.some((item) => item.blocker_type === "missing-tech") &&
        <p className="frontier-definition"><b>missing-tech</b> means the named technology
          is not known while its direct prerequisites are satisfied. It is a currently
          researchable frontier—not evidence that its own prerequisites are missing.</p>}
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
  const predicateGroups = new Map<string, AtomView[]>();
  for (const row of rows) {
    predicateGroups.set(row.atom.predicate, [...predicateGroups.get(row.atom.predicate) ?? [], row]);
  }
  const groupedPredicates = [...predicateGroups.entries()]
    .sort((left, right) => right[1].length - left[1].length || left[0].localeCompare(right[0]))
    .slice(0, 12);
  const largestPredicate = Math.max(1, ...groupedPredicates.map(([, values]) => values.length));
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
    <section className="atom-overview">
      <header><div><span className="eyebrow">predicate grouping</span><h3>Atom distribution</h3></div>
        <small>confidence is a display aggregation of logged values</small></header>
      <div className="atom-group-chart">
        {groupedPredicates.map(([predicate, values]) => {
          const uncertain = values.filter((row) => !row.atom.crisp).length;
          const confidence = values.reduce((sum, row) => sum + row.atom.tv.confidence, 0) / values.length;
          return <button key={predicate} onClick={() => onSearch(predicate)}>
            <span><strong>{humanize(predicate)}</strong><small>{predicate}</small></span>
            <ValueBar value={values.length} maximum={largestPredicate}
              label={`${predicate} atom count`} />
            <span><strong>{values.length}</strong><small>{uncertain} uncertain · μc {confidence.toFixed(2)}</small></span>
          </button>;
        })}
      </div>
    </section>
    <div className="atom-table" role="table">
      <div className="atom-row atom-head" role="row">
        <span>predicate</span><span>arguments</span><span>truth value</span>
        <span>confidence history</span><span>provenance</span><span>revised</span>
      </div>
      {rows.slice(firstAtomRow, firstAtomRow + 500).map((row) => <button className={`atom-row ${row.duplicateProvenance ? "duplicate" : ""}`}
        role="row" key={row.atom.atom_id} onClick={() => onSelect({ kind: "atom", value: row })}>
        <strong>{row.atom.predicate}</strong>
        <span>{row.atom.args.map(String).join(" · ")}</span>
        <span className={row.atom.crisp ? "tv-crisp" : "tv-uncertain"}>
          {row.atom.tv.strength.toFixed(2)} / {row.atom.tv.confidence.toFixed(2)}
        </span>
        <Sparkline values={row.history.map((entry) => entry.tv.confidence)}
          minimum={0} maximum={1} label={`${row.atom.predicate} confidence revisions`} />
        <span>{row.atom.provenance_ids.length}</span><span>T{row.lastTurn}</span>
      </button>)}
    </div>
  </div>;
}

function PlanBoard({ state, onSelect }: { state: ReplayState; onSelect: (selection: Selection) => void }) {
  const [ganttWindow, setGanttWindow] = useState<20 | 60 | 0>(20);
  const plans = [...state.plans.values()];
  if (!plans.length) return <LoggingGap title="No plan events at this cursor"
    detail="Plan timing and resource values are rendered only from plan_created events." />;
  const ganttPlans = ganttWindow ? plans.slice(-ganttWindow) : plans;
  const turns = ganttPlans.flatMap((plan) => plan.steps.flatMap((step) =>
    [step.predicted_turn, step.actual_turn].filter((value): value is number => typeof value === "number")));
  const minimumTurn = Math.min(...turns);
  const maximumTurn = Math.max(minimumTurn + 1, ...turns);
  const position = (turn: number): number =>
    (turn - minimumTurn) / Math.max(1, maximumTurn - minimumTurn) * 100;
  return <div className="view-content"><div className="view-heading">
    <div><span className="eyebrow">scheduled intent</span><h2>Plan board</h2></div>
    <p>{plans.length} logged plans · predicted and actual turns remain visually distinct</p>
  </div>
  <section className="plan-gantt" aria-label="Plan dependency and timing chart">
    <header><div><span className="eyebrow">dependency schedule</span><h3>Plan timing</h3></div>
      <div className="gantt-controls"><span>T{minimumTurn}—T{maximumTurn}</span>
        <div className="segmented-control" role="group" aria-label="Plan timing window">
          {([20, 60, 0] as const).map((window) => <button key={window}
            className={ganttWindow === window ? "active" : ""}
            onClick={() => setGanttWindow(window)}>{window || "all"}</button>)}
        </div>
      </div></header>
    <div className="gantt-axis">
      {Array.from({ length: Math.min(12, maximumTurn - minimumTurn + 1) }, (_, index) => {
        const turn = minimumTurn + Math.round(index * (maximumTurn - minimumTurn)
          / Math.max(1, Math.min(11, maximumTurn - minimumTurn)));
        return <span key={`${turn}-${index}`} style={{ left: `${position(turn)}%` }}>T{turn}</span>;
      })}
    </div>
    {ganttPlans.map((plan) => <div className={`gantt-lane status-${plan.status.toLowerCase()}`} key={plan.plan_id}>
      <button className="gantt-plan-label" onClick={() => onSelect({ kind: "plan", value: plan })}>
        <strong>{humanize(plan.goal_atom_id)}</strong><small>{plan.plan_id}</small>
      </button>
      <div className="gantt-track">
        {plan.steps.length > 1 && <span className="gantt-dependency"
          style={{ left: `${position(plan.steps[0].predicted_turn)}%`,
            width: `${position(plan.steps.at(-1)!.predicted_turn) - position(plan.steps[0].predicted_turn)}%` }} />}
        {plan.steps.map((step, index) => <button key={step.step_id}
          className={`gantt-step status-${step.status.toLowerCase()}`}
          style={{ left: `${position(step.predicted_turn)}%` }}
          title={`${step.kind}: predicted T${step.predicted_turn}, actual ${step.actual_turn ?? "not logged"}`}
          onClick={() => onSelect({ kind: "step", value: step, plan })}>
          <span>{index + 1}</span>
          {step.actual_turn !== null && <i style={{
            "--actual-offset": `${position(step.actual_turn) - position(step.predicted_turn)}%`,
          } as React.CSSProperties} />}
        </button>)}
      </div>
    </div>)}
    <footer><span className="predicted">● predicted</span><span className="actual">◆ actual</span>
      <span className="invalid">red lane = invalidated</span></footer>
  </section>
  <div className="plan-grid">{plans.map((plan) => {
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

const spatialRows = (value: unknown): Array<Record<string, unknown>> => {
  if (Array.isArray(value)) {
    return value.filter((row): row is Record<string, unknown> =>
      Boolean(row) && typeof row === "object" && !Array.isArray(row));
  }
  if (value && typeof value === "object") {
    return Object.values(value).filter((row): row is Record<string, unknown> =>
      Boolean(row) && typeof row === "object" && !Array.isArray(row));
  }
  return [];
};

const exactPoint = (value: unknown): { x: number; y: number } | undefined => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const row = value as Record<string, unknown>;
  const x = row.x ?? row.dest_x;
  const y = row.y ?? row.dest_y;
  return Number.isInteger(x) && Number.isInteger(y)
    ? { x: Number(x), y: Number(y) } : undefined;
};

const stepPoint = (step: PlanStep): { x: number; y: number } | undefined => {
  const target = step.target as Record<string, unknown> | undefined;
  return exactPoint(step.spatial) ?? exactPoint(target?.target) ?? exactPoint(target);
};

type MapMarker = {
  key: string;
  kind: "city" | "unit" | "enemy" | "atom";
  label: string;
  x: number;
  y: number;
  confidence: number;
  atom?: AtomView;
};

const entityMarker = (
  row: Record<string, unknown>,
  kind: "city" | "unit" | "enemy",
): MapMarker | undefined => {
  const point = exactPoint(row);
  if (!point) return undefined;
  const id = row.city_id ?? row.unit_id ?? row.id ?? `${point.x}-${point.y}`;
  const name = kind === "city"
    ? String(row.name ?? `city ${id}`)
    : String(row.type ?? row.unit_type ?? `${kind} ${id}`);
  return {
    key: `${kind}-${String(id)}`,
    kind,
    label: `${kind === "city" ? "City" : kind === "enemy" ? "Visible opponent" : "Unit"} ${name}`,
    ...point,
    confidence: 1,
  };
};

const terrainHue = (terrain: unknown): number => {
  if (typeof terrain === "number" && Number.isFinite(terrain)) {
    return (175 + Math.abs(Math.trunc(terrain)) * 37) % 360;
  }
  return [...String(terrain ?? "")].reduce((sum, character) =>
    (sum + character.charCodeAt(0) * 17) % 360, 175);
};

function MapOverlay({ state, selection, onSelect }: {
  state: ReplayState; selection?: Selection; onSelect: (selection: Selection) => void;
}) {
  const spatialPlans = [...state.plans.values()].filter((plan) =>
    plan.steps.some((step) => stepPoint(step)));
  const [planId, setPlanId] = useState<string>();
  const [mapZoom, setMapZoom] = useState(1);
  const [focusedPoint, setFocusedPoint] = useState<{ x: number; y: number }>();
  const mapViewportRef = useRef<HTMLDivElement>(null);
  const [viewportFrame, setViewportFrame] = useState({
    x: 0, y: 0, width: 1, height: 1,
  });
  const syncViewportFrame = () => {
    const viewport = mapViewportRef.current;
    if (!viewport || viewport.scrollWidth <= 0 || viewport.scrollHeight <= 0) return;
    const next = {
      x: viewport.scrollLeft / viewport.scrollWidth,
      y: viewport.scrollTop / viewport.scrollHeight,
      width: Math.min(1, viewport.clientWidth / viewport.scrollWidth),
      height: Math.min(1, viewport.clientHeight / viewport.scrollHeight),
    };
    setViewportFrame((current) => Object.keys(next).every((key) =>
      Math.abs(current[key as keyof typeof current] - next[key as keyof typeof next]) < 0.001)
      ? current : next);
  };
  useEffect(() => {
    const frame = window.requestAnimationFrame(syncViewportFrame);
    return () => window.cancelAnimationFrame(frame);
  }, [mapZoom, state.events.length]);
  const snapshot = state.snapshots.at(-1);
  if (!snapshot) return <LoggingGap title="No map snapshot at this cursor"
    detail="The map never infers tiles or paths without a state_snapshot map payload." />;
  const map = snapshot.payload.map as Record<string, unknown> | undefined;
  const sourceWidth = Number(map?.width ?? 0);
  const sourceHeight = Number(map?.height ?? 0);
  if (!Number.isInteger(sourceWidth) || !Number.isInteger(sourceHeight)
      || sourceWidth <= 0 || sourceHeight <= 0) {
    return <LoggingGap title="Map dimensions were not logged"
    detail="Emit width and height in state_snapshot.map; the view will not guess them." />;
  }
  const width = Math.min(100, sourceWidth);
  const height = Math.min(100, sourceHeight);
  const cropped = width !== sourceWidth || height !== sourceHeight;
  const tileRows = spatialRows(map?.tiles);
  const tileByCoordinate = new Map<string, Record<string, unknown>>();
  for (const tile of tileRows) {
    const index = Number(tile.index ?? tile.tile);
    const x = Number.isInteger(tile.x) ? Number(tile.x)
      : Number.isInteger(index) ? index % sourceWidth : Number.NaN;
    const y = Number.isInteger(tile.y) ? Number(tile.y)
      : Number.isInteger(index) ? Math.floor(index / sourceWidth) : Number.NaN;
    if (Number.isInteger(x) && Number.isInteger(y) && x >= 0 && y >= 0
        && x < width && y < height) {
      tileByCoordinate.set(`${x},${y}`, tile);
    }
  }
  const visible = new Set<string>();
  for (const row of Array.isArray(map?.visible) ? map.visible : []) {
    if (Array.isArray(row) && Number.isInteger(row[0]) && Number.isInteger(row[1])) {
      visible.add(`${Number(row[0])},${Number(row[1])}`);
    }
  }
  for (const value of Array.isArray(map?.visible_tile_ids) ? map.visible_tile_ids : []) {
    if (Number.isInteger(value) && Number(value) >= 0 && Number(value) < sourceWidth * sourceHeight) {
      visible.add(`${Number(value) % sourceWidth},${Math.floor(Number(value) / sourceWidth)}`);
    }
  }
  for (const [key, tile] of tileByCoordinate) {
    if (tile.visible === true) visible.add(key);
  }
  const ownState = snapshot.payload.own_state as Record<string, unknown> | undefined;
  const cities = spatialRows(ownState?.cities)
    .map((row) => entityMarker(row, "city")).filter((row): row is MapMarker => Boolean(row));
  const units = spatialRows(ownState?.units)
    .map((row) => entityMarker(row, "unit")).filter((row): row is MapMarker => Boolean(row));
  const enemies = spatialRows(map?.visible_enemy_units)
    .map((row) => entityMarker(row, "enemy")).filter((row): row is MapMarker => Boolean(row));
  const atomMarkers = [...state.atoms.values()].flatMap((row): MapMarker[] => {
    const point = coordinate(row.atom);
    return point ? [{
      key: `atom-${row.atom.atom_id}`,
      kind: "atom",
      label: formatAtom(row.atom),
      x: point[0],
      y: point[1],
      confidence: row.atom.tv.confidence,
      atom: row,
    }] : [];
  });
  const markers = [...cities, ...units, ...enemies, ...atomMarkers]
    .filter((marker) => marker.x >= 0 && marker.y >= 0
      && marker.x < width && marker.y < height);
  const markersByCoordinate = new Map<string, MapMarker[]>();
  for (const marker of markers) {
    const key = `${marker.x},${marker.y}`;
    markersByCoordinate.set(key, [...markersByCoordinate.get(key) ?? [], marker]);
  }
  const selectedFromInspector = selection?.kind === "plan" ? selection.value
    : selection?.kind === "step" ? selection.plan : undefined;
  const selectedPlan = spatialPlans.find((plan) => plan.plan_id === selectedFromInspector?.plan_id)
    ?? spatialPlans.find((plan) => plan.plan_id === planId) ?? spatialPlans.at(-1);
  const planned = new Map<string, PlanStep>();
  for (const step of selectedPlan?.steps ?? []) {
    const point = stepPoint(step);
    if (point) planned.set(`${point.x},${point.y}`, step);
  }
  const invalid = selectedPlan ? state.invalidations.get(selectedPlan.plan_id) : undefined;
  const path = (selectedPlan?.steps ?? []).flatMap((step) => {
    const point = stepPoint(step);
    return point ? [{ ...point, step }] : [];
  });
  const knownHuts = new Set((Array.isArray(map?.known_hut_tile_ids)
    ? map.known_hut_tile_ids : []).filter(Number.isInteger).map(Number));
  const terrainAvailable = tileByCoordinate.size > 0;
  const visibilityAvailable = visible.size > 0;
  const viewHeight = 1000 * height / width;
  const activePoint = focusedPoint && focusedPoint.x >= 0 && focusedPoint.y >= 0
    && focusedPoint.x < width && focusedPoint.y < height ? focusedPoint : undefined;
  const activeKey = activePoint ? `${activePoint.x},${activePoint.y}` : undefined;
  const activeTile = activeKey ? tileByCoordinate.get(activeKey) : undefined;
  const activeMarkers = activeKey ? markersByCoordinate.get(activeKey) ?? [] : [];
  const activeStep = activeKey ? planned.get(activeKey) : undefined;
  const activeVisible = activeKey ? visible.has(activeKey) : false;
  const activeHut = activePoint
    ? knownHuts.has(activePoint.y * sourceWidth + activePoint.x) : false;
  const focusMapPoint = (x: number, y: number) => {
    setFocusedPoint({ x, y });
    const tile = document.getElementById(`map-tile-${x}-${y}`);
    tile?.focus({ preventScroll: true });
    if (typeof tile?.scrollIntoView === "function") {
      tile.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    }
  };
  const handleMapKey = (event: React.KeyboardEvent<HTMLButtonElement>, x: number, y: number) => {
    const offsets: Record<string, [number, number]> = {
      ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
    };
    if (event.key === "Escape") {
      event.preventDefault();
      setFocusedPoint(undefined);
      event.currentTarget.blur();
      return;
    }
    const offset = offsets[event.key];
    if (!offset) return;
    event.preventDefault();
    focusMapPoint(
      Math.max(0, Math.min(width - 1, x + offset[0])),
      Math.max(0, Math.min(height - 1, y + offset[1])),
    );
  };
  const panFromOverview = (event: React.MouseEvent<HTMLButtonElement>) => {
    const viewport = mapViewportRef.current;
    if (!viewport) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const keyboardPoint = activePoint
      ? { x: (activePoint.x + 0.5) / width, y: (activePoint.y + 0.5) / height }
      : { x: 0.5, y: 0.5 };
    const x = event.detail === 0 || bounds.width <= 0
      ? keyboardPoint.x : (event.clientX - bounds.left) / bounds.width;
    const y = event.detail === 0 || bounds.height <= 0
      ? keyboardPoint.y : (event.clientY - bounds.top) / bounds.height;
    viewport.scrollTo({
      left: Math.max(0, Math.min(1, x)) * viewport.scrollWidth - viewport.clientWidth / 2,
      top: Math.max(0, Math.min(1, y)) * viewport.scrollHeight - viewport.clientHeight / 2,
      behavior: "smooth",
    });
  };
  return <div className="view-content map-view"><div className="view-heading">
    <div><span className="eyebrow">event-provided spatial state</span><h2>Map overlay</h2></div>
    <div className="map-controls"><p>{sourceWidth}×{sourceHeight} map · {cities.length} cities ·
      {" "}{units.length} units · {path.length} selected targets</p>
      {spatialPlans.length > 0 && <label>plan <select aria-label="Map plan overlay"
        value={selectedPlan?.plan_id ?? ""}
        onChange={(event) => setPlanId(event.target.value)}>
        {spatialPlans.map((plan) => <option key={plan.plan_id} value={plan.plan_id}>
          {humanize(plan.goal_atom_id)} · {plan.status}
        </option>)}
      </select></label>}</div>
  </div>
  {(!terrainAvailable || !visibilityAvailable || cropped) && <section className="map-data-status"
    role="status" aria-label="Map data coverage">
    <div><span className="eyebrow">partial spatial evidence</span>
      <strong>{terrainAvailable ? "Packet map available" : "Positional overlay"}</strong></div>
    <p>{!terrainAvailable
      ? "Terrain was not emitted in this trace. Logged cities, units, observations, and action targets remain exact."
      : !visibilityAvailable
        ? "Terrain was emitted without visible-tile evidence; the UI does not infer fog of war."
        : "The source map exceeds the 100×100 display safety window."}</p>
    <div><span>tiles <b>{tileByCoordinate.size}</b></span>
      <span>visible <b>{visible.size}</b></span><span>markers <b>{markers.length}</b></span></div>
  </section>}
  <section className="map-spatial-tools" aria-label="Map navigation controls">
    <div className="map-focus-list" role="region" aria-label="Map entity and target navigator">
      <span className="eyebrow">focus logged position</span>
      <div>
        {path.map(({ x, y, step }, index) => <button key={`target-${step.step_id}`}
          className={`target ${activeKey === `${x},${y}` ? "active" : ""}`}
          aria-label={`Focus action target ${index + 1} at ${x},${y}`}
          aria-pressed={activeKey === `${x},${y}`}
          onClick={() => {
            focusMapPoint(x, y);
            if (selectedPlan) onSelect({ kind: "step", value: step, plan: selectedPlan });
          }}>
          <b>◈</b> target {index + 1} <small>{x},{y}</small>
        </button>)}
        {markers.map((marker) => <button key={marker.key}
          className={`${marker.kind} ${activeKey === `${marker.x},${marker.y}` ? "active" : ""}`}
          aria-label={`Focus ${marker.label} at ${marker.x},${marker.y}`}
          aria-pressed={activeKey === `${marker.x},${marker.y}`}
          onClick={() => {
            focusMapPoint(marker.x, marker.y);
            onSelect(marker.atom
              ? { kind: "atom", value: marker.atom }
              : { kind: "event", value: snapshot });
          }}>
          <b>{marker.kind === "city" ? "◆" : marker.kind === "enemy" ? "×"
            : marker.kind === "unit" ? "●" : "○"}</b>
          {marker.label} <small>{marker.x},{marker.y}</small>
        </button>)}
      </div>
    </div>
    <div className="map-zoom" role="group" aria-label="Map zoom">
      <span className="eyebrow">zoom</span>
      <div>{[1, 1.5, 2, 3].map((zoom) => <button key={zoom}
        aria-label={`Set map zoom to ${zoom}×`}
        aria-pressed={mapZoom === zoom}
        onClick={() => setMapZoom(zoom)}>{zoom}×</button>)}</div>
    </div>
  </section>
  <div className="map-viewport-shell">
  {activePoint && <aside className="map-cursor-readout" aria-label="Selected map coordinate"
    aria-live="polite">
    <div><span className="eyebrow">map cursor</span>
      <strong>{activePoint.x},{activePoint.y}</strong></div>
    <dl>
      <div><dt>terrain</dt><dd>{activeTile?.terrain === undefined
        ? "not logged" : String(activeTile.terrain)}</dd></div>
      <div><dt>evidence</dt><dd>{!terrainAvailable ? "position only"
        : activeVisible ? "visible" : visibilityAvailable ? "not visible" : "visibility not logged"}</dd></div>
      <div><dt>entities</dt><dd title={activeMarkers.map((marker) => marker.label).join(", ")}>
        {activeMarkers.length || "none"}</dd></div>
      <div><dt>target</dt><dd>{activeStep ? humanize(activeStep.kind) : "none"}</dd></div>
      {activeHut && <div><dt>feature</dt><dd>known hut</dd></div>}
    </dl>
    <small>arrow keys move · enter opens evidence · esc clears</small>
  </aside>}
  <button className="map-overview" type="button" onClick={panFromOverview}
    aria-label="Map viewport overview. Click to pan"
    title="Logged positions and current viewport · click to pan"
    style={{ "--map-overview-aspect": `${width} / ${height}` } as React.CSSProperties}>
    <span>overview</span>
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <rect className="map-overview-background" width={width} height={height} />
      {path.map(({ x, y, step }) => <rect key={`overview-target-${step.step_id}`}
        className="map-overview-target" x={x} y={y} width="1" height="1" />)}
      {markers.map((marker) => <circle key={`overview-${marker.key}`}
        className={`map-overview-marker ${marker.kind}`}
        cx={marker.x + 0.5} cy={marker.y + 0.5} r=".38" />)}
      {activePoint && <circle className="map-overview-selection"
        cx={activePoint.x + 0.5} cy={activePoint.y + 0.5} r=".72" />}
      <rect className="map-overview-window"
        x={viewportFrame.x * width} y={viewportFrame.y * height}
        width={viewportFrame.width * width} height={viewportFrame.height * height} />
    </svg>
  </button>
  <div className="map-viewport" ref={mapViewportRef} onScroll={syncViewportFrame}>
  <div className="map-canvas" style={{
    "--map-aspect": `${width} / ${height}`, width: `${mapZoom * 100}%`,
  } as React.CSSProperties}>
  <div className="tile-map" style={{ "--map-width": width } as React.CSSProperties}>
    {Array.from({ length: width * height }, (_, index) => {
      const x = index % width; const y = Math.floor(index / width);
      const tile = tileByCoordinate.get(`${x},${y}`);
      const tileMarkers = markersByCoordinate.get(`${x},${y}`) ?? [];
      const step = planned.get(`${x},${y}`);
      const broken = invalid && tileMarkers.some((marker) => marker.atom?.atom.atom_id ===
        (invalid.payload.broken_assumption as { atom_id?: string } | undefined)?.atom_id);
      const isVisible = visible.has(`${x},${y}`);
      const terrain = tile?.terrain;
      const tileIndex = y * sourceWidth + x;
      const hut = knownHuts.has(tileIndex);
      const markerLabels = tileMarkers.map((marker) => marker.label).join(", ");
      const selected = activeKey === `${x},${y}`;
      return <button key={`${x}-${y}`}
        id={`map-tile-${x}-${y}`}
        aria-label={`Tile ${x},${y}${terrain === undefined ? "" : `, terrain ${String(terrain)}`}${markerLabels ? `, ${markerLabels}` : ""}`}
        aria-pressed={selected}
        title={terrain === undefined ? `Tile ${x},${y}` : `Tile ${x},${y} · terrain ${String(terrain)}`}
        className={`map-tile ${isVisible ? "visible" : terrainAvailable ? "fog" : "unavailable"} ${tile ? "has-terrain" : ""} ${tileMarkers.length ? "has-marker" : ""} ${step ? "planned" : ""} ${broken ? "broken" : ""} ${hut ? "hut" : ""} ${selected ? "selected" : ""}`}
        style={tile && terrain !== undefined
          ? { "--terrain-hue": terrainHue(terrain) } as React.CSSProperties : undefined}
        onKeyDown={(event) => handleMapKey(event, x, y)}
        onClick={() => {
          setFocusedPoint({ x, y });
          const atomMarker = tileMarkers.find((marker) => marker.atom);
          onSelect(atomMarker?.atom
            ? { kind: "atom", value: atomMarker.atom }
            : { kind: "event", value: snapshot });
        }}>
        {tileMarkers.length > 0 && <span className="map-marker-stack">
          {tileMarkers.slice(0, 4).map((marker) => <span key={marker.key}
            className={`map-entity-marker ${marker.kind}`}
            style={{ opacity: marker.confidence }}
            title={`${marker.label}${marker.kind === "atom"
              ? ` confidence ${marker.confidence.toFixed(2)}` : ""}`}>
            {marker.kind === "city" ? "◆" : marker.kind === "enemy" ? "×"
              : marker.kind === "unit" ? "●" : "○"}
          </span>)}
          {tileMarkers.length > 4 && <b>+{tileMarkers.length - 4}</b>}
        </span>}
        {hut && <span className="map-hut" title="Packet-known hut">⌂</span>}
        {step && <em>T{step.predicted_turn}</em>}
      </button>;
    })}
  </div>
  {path.length > 0 && <svg className="map-path-overlay" viewBox={`0 0 1000 ${viewHeight}`}
    role="img" aria-label={`Logged path for ${selectedPlan?.goal_atom_id ?? "selected plan"}`}>
    <polyline points={path.map(({ x, y }) =>
      `${(x + 0.5) / width * 1000},${(y + 0.5) / height * viewHeight}`).join(" ")} />
    {path.map(({ x, y, step }, index) => <g key={step.step_id}
      transform={`translate(${(x + 0.5) / width * 1000} ${(y + 0.5) / height * viewHeight})`}>
      <circle r="15" /><text y="5" textAnchor="middle">{index + 1}</text>
    </g>)}
  </svg>}
  </div></div></div><div className="map-legend">
    <span className="city">◆ city</span><span className="unit">● own unit</span>
    {enemies.length > 0 && <span className="enemy">× visible opponent</span>}
    {atomMarkers.length > 0 && <span>○ uncertain observation opacity = logged confidence</span>}
    <span>□ {visibilityAvailable ? "fog as logged" : "terrain unavailable"}</span>
    <span>◈ selected action target</span></div></div>;
}

function EpistemicAudit({ state, onSelect }: {
  state: ReplayState; onSelect: (selection: Selection) => void;
}) {
  const proposals = state.events.filter((event) => event.type === "llm_proposal");
  const claimsByProposal = proposals.flatMap((event) => {
    const proposalId = String(event.payload.proposal_id ?? "");
    return (Array.isArray(event.payload.claims) ? event.payload.claims : [])
      .flatMap((claim) => claim && typeof claim === "object"
        ? [{ proposalId, claim: claim as Record<string, unknown> }] : []);
  });
  const claimKeys = new Set(claimsByProposal.map(({ proposalId, claim }) =>
    `${proposalId}\u0000${String(claim.claim_id ?? "")}`));
  const isClaimLinked = (event: TraceEvent): boolean => claimKeys.has(
    `${String(event.payload.proposal_id ?? "")}\u0000${String(event.payload.claim_id ?? "")}`,
  );
  const claimVerifications = state.verifications.filter(isClaimLinked);
  const decisionVerifications = state.verifications.filter((event) => !isClaimLinked(event));
  const claimQuarantines = state.quarantines.filter(isClaimLinked);
  const claimCount = claimsByProposal.length;
  const goalCount = proposals.reduce((count, event) => count
    + (Array.isArray(event.payload.goals) ? event.payload.goals.length : 0), 0);
  const writeThrough = [...state.metrics].reverse().find(
    (event) => event.payload.name === "confabulation_write_through");
  const rawWriteValue = writeThrough ? Number(writeThrough.payload.value) : Number.NaN;
  const writeValue = Number.isFinite(rawWriteValue) ? rawWriteValue : undefined;
  const writeUnit = String(writeThrough?.payload.unit ?? "");
  const writeLabel = writeUnit === "ratio" ? "write-through ratio" : "write-through claims";
  const writeDisplay = writeValue === undefined ? "—" : writeUnit === "ratio"
    ? `${(writeValue * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`
    : writeValue.toLocaleString();
  const claimProposalEvents = proposals.filter((event) =>
    Array.isArray(event.payload.claims) && event.payload.claims.length > 0);
  const auditTurns = [...new Set([
    ...claimProposalEvents.map((event) => event.turn),
    ...claimVerifications.map((event) => event.turn),
    ...claimQuarantines.map((event) => event.turn),
  ])].sort((left, right) => left - right);
  const decisionChecks = [...decisionVerifications.reduce((checks, event) => {
    const check = String(event.payload.check ?? "unclassified_check");
    const row = checks.get(check) ?? {
      events: [] as TraceEvent[], believe: 0, disbelieve: 0, quarantine: 0,
    };
    row.events.push(event);
    const verdict = String(event.payload.verdict ?? "");
    if (verdict === "believe") row.believe += 1;
    else if (verdict === "disbelieve") row.disbelieve += 1;
    else if (verdict === "quarantine") row.quarantine += 1;
    checks.set(check, row);
    return checks;
  }, new Map<string, {
    events: TraceEvent[]; believe: number; disbelieve: number; quarantine: number;
  }>())].sort((left, right) => right[1].events.length - left[1].events.length);
  const decisionBelieved = decisionVerifications.filter(
    (event) => event.payload.verdict === "believe").length;
  const decisionDisbelieved = decisionVerifications.filter(
    (event) => event.payload.verdict === "disbelieve").length;
  const decisionQuarantined = decisionVerifications.filter(
    (event) => event.payload.verdict === "quarantine").length;
  const countsByTurn = (events: TraceEvent[], count: (event: TraceEvent) => number = () => 1):
  Map<number, number> => {
    const values = new Map<number, number>();
    for (const event of events) values.set(event.turn, (values.get(event.turn) ?? 0) + count(event));
    return values;
  };
  return <div className="view-content audit-view"><div className="view-heading">
    <div><span className="eyebrow">three-sink verification</span><h2>Epistemic audit</h2></div>
  </div>
  {auditTurns.length > 0 && <section className="audit-heatmap">
    <header><div><span className="eyebrow">verification chronology</span>
      <h3>Claim handling by turn</h3></div></header>
    <TurnHeatmap turns={auditTurns} label="Claims, claim checks, and quarantine by turn"
      onTurn={() => undefined}
      rows={[
        { label: "Claims", counts: countsByTurn(claimProposalEvents,
          (event) => Array.isArray(event.payload.claims) ? event.payload.claims.length : 0), color: CHART_COLORS[0] },
        { label: "Claim checks", counts: countsByTurn(claimVerifications), color: CHART_COLORS[2] },
        { label: "Quarantined", counts: countsByTurn(claimQuarantines), color: CHART_COLORS[3] },
      ]} />
  </section>}
  <section className={`audit-scope-note ${claimCount === 0 ? "empty" : ""}`}
    aria-label="Claim audit scope">
    <div><span className="eyebrow">claim-bearing proposals</span>
      <strong>{claimCount === 0 ? "No claims emitted" : `${claimCount} claims emitted`}</strong></div>
    <p>{proposals.length.toLocaleString()} model proposal{proposals.length === 1 ? "" : "s"} ·
      {" "}{goalCount.toLocaleString()} goal{goalCount === 1 ? "" : "s"} ·
      {" "}only checks matching both proposal and claim IDs enter this funnel.</p>
  </section>
  <div className={`write-through ${writeValue === undefined ? "unknown" : writeValue ? "alarm" : "clear"}`} role="status">
    <span>confabulation {writeLabel}</span><strong>{writeDisplay}</strong>
    <small>{writeThrough ? `event-provided ${writeUnit || "value"}` : "no metric logged · unknown"}</small>
  </div><div className="funnel" aria-label="Claim verification funnel">
    <div aria-label="Proposed claims"><strong>{claimCount}</strong><span>proposed claims</span></div>
    <div aria-label="Claim checks"><strong>{claimVerifications.length}</strong><span>claim checks</span></div>
    <div aria-label="Quarantined claims"><strong>{claimQuarantines.length}</strong><span>quarantined claims</span></div>
    <div className={writeValue ? "alarm" : ""} aria-label={writeLabel}>
      <strong>{writeDisplay}</strong><span>{writeLabel}</span></div>
  </div>
  <section className="decision-checks" aria-label="Non-claim decision checks">
    <header><div><span className="eyebrow">separate verification domain</span>
      <h3>Goal, continuation, and plan checks</h3></div>
      <strong>{decisionVerifications.length.toLocaleString()} checks</strong></header>
    <div className="decision-verdicts">
      <span><b>{decisionBelieved}</b> believe</span>
      <span><b>{decisionDisbelieved}</b> disbelieve</span>
      <span><b>{decisionQuarantined}</b> quarantine</span>
    </div>
    {decisionChecks.length > 0 ? <div className="decision-check-table">
      <div className="head"><span>check</span><span>total</span><span>believe</span>
        <span>disbelieve</span><span>quarantine</span></div>
      {decisionChecks.map(([check, row]) => <button key={check}
        aria-label={`Inspect latest ${check} decision check`}
        onClick={() => onSelect({ kind: "event", value: row.events.at(-1)! })}>
        <strong>{humanize(check)}</strong><span>{row.events.length}</span>
        <span>{row.believe}</span><span>{row.disbelieve}</span><span>{row.quarantine}</span>
      </button>)}
    </div> : <p className="audit-empty-copy">All verification events at this cursor are linked to emitted claims.</p>}
  </section>
  <section className="claim-quarantines" aria-label="Quarantined claim details">
    <header><span className="eyebrow">quarantine sink</span>
      <strong>{claimQuarantines.length.toLocaleString()} claims</strong></header>
    {claimQuarantines.length > 0 ? <div className="quarantine-table"><div className="quarantine-row head">
      <span>turn</span><span>claim verbatim</span><span>failed check</span><span>evidence</span></div>
    {claimQuarantines.map((event) => <button className="quarantine-row" key={event.event_id}
      onClick={() => onSelect({ kind: "event", value: event })}>
      <span>T{event.turn}</span><strong>{String(event.payload.claim)}</strong>
      <span>{String(event.payload.failed_check)}</span>
      <span>{Array.isArray(event.payload.evidence_atoms) ? event.payload.evidence_atoms.length : 0}</span>
    </button>)}
    </div> : <p className="audit-empty-copy">No emitted claims entered quarantine at this cursor.</p>}
  </section></div>;
}

const rowsOf = (value: unknown): Array<Record<string, unknown>> =>
  Array.isArray(value)
    ? value.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    : [];

const recordOf = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};

const numeric = (value: unknown): string =>
  typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString(undefined, { maximumFractionDigits: 4 }) : "—";

const compactPfId = (value: unknown): string => {
  const text = String(value ?? "—");
  const withoutNamespace = text.replace(
    /^pf-impact(?::|-goal:|-category:|-candidate:|-premise:)/, "");
  return withoutNamespace.length > 28
    ? `${withoutNamespace.slice(0, 17)}…${withoutNamespace.slice(-8)}`
    : withoutNamespace;
};

function PressureFlowGraph({ traces, goals, onInspect }: {
  traces: Array<Record<string, unknown>>;
  goals: Array<Record<string, unknown>>;
  onInspect: () => void;
}) {
  const visible = traces.slice(0, 80);
  const goalIds = [...new Set([
    ...goals.map((goal) => String(goal.goal_id ?? "unknown goal")),
    ...visible.map((trace) => String(trace.goal_id ?? "unknown goal")),
  ])];
  const conclusions = [...new Set(visible.map((trace) => String(trace.conclusion_id ?? "unknown conclusion")))];
  const premises = [...new Set(visible.map((trace) => String(trace.premise_id ?? "unknown premise")))];
  const height = Math.max(250, Math.max(goalIds.length, conclusions.length, premises.length) * 46 + 42);
  const position = (items: string[], id: string, x: number): { x: number; y: number } => ({
    x,
    y: 34 + (Math.max(0, items.indexOf(id)) + 0.5) * ((height - 58) / Math.max(1, items.length)),
  });
  const maximum = Math.max(1, ...visible.map((trace) =>
    Math.abs(Number(trace.transported_pressure ?? 0))));
  return <div className="pf-flow-graph-wrap">
    <div className="pf-flow-columns" aria-hidden="true">
      <span>goal field</span><span>rule conclusion</span><span>candidate premise</span>
    </div>
    <svg className="pf-flow-graph" viewBox={`0 0 960 ${height}`} role="img"
      aria-label="PF-PLN pressure flow graph" onClick={onInspect}>
      {visible.flatMap((trace, index) => {
        const goal = String(trace.goal_id ?? "unknown goal");
        const conclusion = String(trace.conclusion_id ?? "unknown conclusion");
        const premise = String(trace.premise_id ?? "unknown premise");
        const from = position(goalIds, goal, 92);
        const middle = position(conclusions, conclusion, 480);
        const to = position(premises, premise, 868);
        const pressure = Math.abs(Number(trace.transported_pressure ?? 0));
        const width = 0.8 + pressure / maximum * 5;
        const color = CHART_COLORS[Math.max(0, goalIds.indexOf(goal)) % CHART_COLORS.length];
        return [
          <path key={`goal-${index}`} d={`M${from.x},${from.y} C270,${from.y} 300,${middle.y} ${middle.x},${middle.y}`}
            stroke={color} strokeWidth={width} className="pf-flow-edge" />,
          <path key={`premise-${index}`} d={`M${middle.x},${middle.y} C650,${middle.y} 680,${to.y} ${to.x},${to.y}`}
            stroke={color} strokeWidth={width} className="pf-flow-edge" />,
        ];
      })}
      {[{ values: goalIds, x: 92, kind: "goal" }, { values: conclusions, x: 480, kind: "rule" },
        { values: premises, x: 868, kind: "premise" }].flatMap(({ values, x, kind }) =>
        values.map((id) => {
          const point = position(values, id, x);
          return <g key={`${kind}-${id}`} transform={`translate(${point.x} ${point.y})`}
            className={`pf-flow-node ${kind}`}>
            <circle r={kind === "goal" ? 9 : 6} />
            <text x={x > 700 ? -12 : 12} y="-2" textAnchor={x > 700 ? "end" : "start"}>
              {compactPfId(id)}
            </text>
            <title>{id}</title>
          </g>;
        }))}
    </svg>
    {traces.length > visible.length && <span className="graph-limit">
      Showing 80 of {traces.length} logged routes
    </span>}
  </div>;
}

const operationParts = (score: Record<string, unknown>, index = 0): {
  operation: Record<string, unknown>; payload: Record<string, unknown>;
  action: Record<string, unknown>; id: string;
} => {
  const operation = recordOf(score.operation);
  const payload = recordOf(operation.payload);
  return {
    operation, payload, action: recordOf(payload.action),
    id: String(operation.operation_id ?? index),
  };
};

function CandidateRanking({ scores, selectedOperationId, onInspect }: {
  scores: Array<Record<string, unknown>>;
  selectedOperationId: string;
  onInspect: () => void;
}) {
  const maximum = Math.max(1e-9, ...scores.flatMap((score) =>
    [Math.abs(Number(score.priority ?? 0)), Math.abs(Number(score.value ?? 0))]));
  return <div className="pf-ranking" aria-label="PF-PLN candidate ranking chart">
    {scores.slice(0, 100).map((score, index) => {
      const parts = operationParts(score, index);
      const selected = parts.id === selectedOperationId;
      const admissible = score.admissible === true;
      const priority = Number(score.priority ?? 0);
      const value = Number(score.value ?? 0);
      return <button key={parts.id}
        className={`${selected ? "selected" : ""} ${admissible ? "" : "rejected"}`}
        onClick={onInspect}>
        <span className="pf-rank-number">{selected ? "◆" : index + 1}</span>
        <span className="pf-rank-label"><strong>{humanize(parts.payload.category)}</strong>
          <small>{String(parts.payload.category ?? "uncategorized")} · {
            humanize(parts.action.action_type ?? parts.operation.mode)}</small></span>
        <span className="pf-rank-bars">
          <ValueBar value={priority} maximum={maximum} color="var(--cyan)"
            label={`${parts.id} priority`} muted={!admissible} />
          <ValueBar value={value} maximum={maximum} color="var(--amber)"
            label={`${parts.id} value`} muted={!admissible} />
        </span>
        <span className="pf-rank-values"><strong>{numeric(priority)}</strong>
          <small>{numeric(value)}</small></span>
        <span className="pf-rank-status">{selected ? "selected" : admissible ? "eligible" : "rejected"}</span>
      </button>;
    })}
  </div>;
}

function PairedTraceComparison({ state, comparisonState, comparisonSource, decision, pairQuality }: {
  state: ReplayState;
  comparisonState?: ReplayState;
  comparisonSource?: string;
  decision?: TraceEvent;
  pairQuality: ArtifactPairQuality;
}) {
  if (!comparisonState || !comparisonSource) return <section className="pf-panel pf-comparison empty">
    <header><div><span className="eyebrow">paired-seed evaluation</span>
      <h3>Trace comparison</h3></div></header>
    <div className="pf-panel-gap">Choose “compare” in Experiment traces to align a second arm by turn.</div>
  </section>;
  const comparisonDecision = [...comparisonState.operationScores].reverse().find(
    (event) => !decision || event.turn <= decision.turn) ?? comparisonState.operationScores.at(-1);
  const selected = (event?: TraceEvent): { category: string; action: string } => {
    const scores = rowsOf(event?.payload.scores);
    const id = String(event?.payload.selected_operation_id ?? "");
    const row = scores.find((score, index) => operationParts(score, index).id === id);
    const parts = operationParts(row ?? {});
    return {
      category: String(parts.payload.category ?? "no selection"),
      action: String(parts.action.action_type ?? parts.operation.mode ?? "—"),
    };
  };
  const primary = selected(decision);
  const comparison = selected(comparisonDecision);
  const outcomeNames = new Set([
    "score_gain", "cities_founded", "settlement_completions", "game_win",
  ]);
  const isOutcome = (name: string): boolean => outcomeNames.has(name) || /^score_turn_\d+$/.test(name);
  const latestMetrics = (source: ReplayState): Map<string, TraceEvent> => {
    const rows = new Map<string, TraceEvent>();
    for (const event of source.metrics) {
      const name = String(event.payload.name);
      if (isOutcome(name)) rows.set(name, event);
    }
    return rows;
  };
  const leftMetrics = latestMetrics(state);
  const rightMetrics = latestMetrics(comparisonState);
  const metricNames = [...new Set([...leftMetrics.keys(), ...rightMetrics.keys()])].sort();
  const diverged = primary.category !== comparison.category || primary.action !== comparison.action;
  return <section className="pf-panel pf-comparison">
    <header><div><span className="eyebrow">turn-aligned descriptive comparison</span>
      <h3>Paired trace comparison</h3></div>
      <div className="pf-comparison-status">
        <span className={`pair-quality ${pairQuality.exact ? "exact" : "warning"}`}
          title={pairQuality.mismatches.join(", ") || "experiment, cohort, condition, seed, and opposing arm match"}>
          {pairQuality.label}
        </span>
        <span className={diverged ? "pf-divergence divergent" : "pf-divergence"}>
          {diverged ? "decision diverged" : "same decision"}
        </span>
      </div></header>
    <div className="pf-arm-comparison">
      <article><span>active trace · T{decision?.turn ?? "—"}</span>
        <strong>{humanize(primary.category)}</strong><small>{humanize(primary.action)}</small></article>
      <div className="pf-vs">vs</div>
      <article><span>comparison · T{comparisonDecision?.turn ?? "—"}</span>
        <strong>{humanize(comparison.category)}</strong><small>{humanize(comparison.action)}</small></article>
    </div>
    {metricNames.length > 0 && <div className="pf-outcome-deltas">
      <div className="head"><span>logged outcome</span><span>active</span>
        <span>comparison</span><span>display difference</span></div>
      {metricNames.map((name) => {
        const left = Number(leftMetrics.get(name)?.payload.value ?? 0);
        const right = Number(rightMetrics.get(name)?.payload.value ?? 0);
        return <div key={name}><strong>{humanize(name)}</strong><span>{numeric(left)}</span>
          <span>{numeric(right)}</span>
          <span className={left - right > 0 ? "positive" : left - right < 0 ? "negative" : ""}>
            {left - right > 0 ? "+" : ""}{numeric(left - right)}
          </span></div>;
      })}
    </div>}
    <footer>Values are logged outcomes at the replay cursor. This display does not estimate causality or uncertainty.</footer>
  </section>;
}

function PfPlnDashboard({ state, onSelect, decisionId, onDecision, comparisonState,
  comparisonSource, pairQuality }: {
  state: ReplayState; onSelect: (selection: Selection) => void;
  decisionId?: string; onDecision: (decision?: string) => void;
  comparisonState?: ReplayState; comparisonSource?: string;
  pairQuality: ArtifactPairQuality;
}) {
  const decisions = state.operationScores;
  const selectedDecision = decisions.find(
    (event) => event.payload.decision_id === decisionId) ?? decisions.at(-1);
  const selectedDecisionId = String(selectedDecision?.payload.decision_id ?? "");
  const pressureId = String(selectedDecision?.payload.pressure_id ?? "");
  const pressureEvent = [...state.pressurePropagations].reverse().find(
    (event) => event.payload.pressure_id === pressureId) ?? state.pressurePropagations.at(-1);
  const goals = rowsOf(pressureEvent?.payload.goals);
  const traces = rowsOf(pressureEvent?.payload.traces);
  const scores = rowsOf(selectedDecision?.payload.scores);
  const selectedOperationId = String(selectedDecision?.payload.selected_operation_id ?? "");
  const selectedScore = scores.find((score) =>
    recordOf(score.operation).operation_id === selectedOperationId);
  const selectedOperation = recordOf(selectedScore?.operation);
  const selectedPayload = recordOf(selectedOperation.payload);
  const phaseMetrics = state.metrics.filter(
    (event) => event.payload.name === "pf_pln_phase_enabled");
  const runtimeMetrics = state.metrics.filter((event) => {
    const name = String(event.payload.name ?? "");
    return name.startsWith("impact_planning_pressure_")
      || name.startsWith("turn_impact_learning_");
  });
  const updatesByCategory = new Map<string, TraceEvent[]>();
  for (const event of state.conductanceUpdates) {
    const category = String(event.payload.category ?? "uncategorized");
    updatesByCategory.set(category, [...updatesByCategory.get(category) ?? [], event]);
  }

  if (!state.pfPlnEvents.length && !phaseMetrics.length) {
    return <LoggingGap title="No PF-PLN control events at this cursor"
      detail="Load a pressure-enabled treatment trace or emit pressure_propagated, operation_scored, and conductance_updated. The browser will not reconstruct pressure or scheduler output." />;
  }

  const summary = [
    { label: "active goals", value: goals.length, event: pressureEvent, detail: "current pressure field" },
    { label: "candidates", value: scores.length, event: selectedDecision, detail: "logged scheduler order" },
    { label: "rejected", value: scores.filter((score) => score.admissible !== true).length,
      event: selectedDecision, detail: "inadmissible candidates" },
    { label: "learned routes", value: updatesByCategory.size,
      event: state.conductanceUpdates.at(-1), detail: "conductance categories" },
  ];

  return <div className="view-content pf-view">
    <div className="view-heading">
      <div><span className="eyebrow">pressure fields / probabilistic logic networks</span>
        <h2>PF-PLN control path</h2></div>
      <p>Trace-only replay. Counts index logged events; goals, pressure, scores,
        selections, and learning values are rendered verbatim.</p>
    </div>

    <div className="pf-summary" aria-label="PF-PLN event coverage">
      {summary.map((item) => <button key={item.label} disabled={!item.event}
        onClick={() => item.event && onSelect({ kind: "event", value: item.event })}>
        <span>{item.label}</span><strong>{item.value.toLocaleString()}</strong>
        <small>{item.detail}</small>
      </button>)}
    </div>

    <section className="pf-decision-focus">
      <header>
        <div><span className="eyebrow">scheduler replay</span><h3>Decision focus</h3></div>
        {decisions.length > 0 && <label>decision
          <select aria-label="PF-PLN decision" value={selectedDecisionId}
            onChange={(event) => {
              onDecision(event.target.value);
              const selected = decisions.find((row) =>
                String(row.payload.decision_id) === event.target.value);
              if (selected) onSelect({ kind: "event", value: selected });
            }}>
            {decisions.slice(-500).reverse().map((event) =>
              <option key={event.event_id} value={String(event.payload.decision_id)}>
                T{event.turn}.{event.seq} · {String(event.payload.decision_id)}
              </option>)}
          </select>
        </label>}
      </header>
      {selectedDecision ? <div className="pf-selected-operation">
        <span className="pf-selection-mark">selected</span>
        <div><strong>{String(selectedPayload.category ?? "uncategorized")}</strong>
          <small>{String(selectedPayload.rationale ?? selectedOperationId ?? "—")}</small></div>
        <div><span>action</span><strong>{
          String(recordOf(selectedPayload.action).action_type ?? selectedOperation.mode ?? "—")
        }</strong></div>
        <div><span>priority</span><strong>{numeric(selectedScore?.priority)}</strong></div>
        <button onClick={() => onSelect({ kind: "event", value: selectedDecision })}>
          inspect event →
        </button>
      </div> : <div className="pf-panel-gap">No operation_scored event was logged.</div>}
    </section>

    <PairedTraceComparison state={state} comparisonState={comparisonState}
      comparisonSource={comparisonSource} decision={selectedDecision}
      pairQuality={pairQuality} />

    <div className="pf-two-column">
      <section className="pf-panel">
        <header><div><span className="eyebrow">latest matched propagation</span>
          <h3>Goal field</h3></div>
          {pressureEvent && <button onClick={() =>
            onSelect({ kind: "event", value: pressureEvent })}>inspect</button>}
        </header>
        {goals.length ? <div className="pf-goals">
          {goals.map((goal, index) => <article key={String(goal.goal_id ?? index)}
            className={goal.safety === true ? "safety" : ""}>
            <div><strong>{compactPfId(goal.goal_id)}</strong>
              {goal.safety === true && <span>safety</span>}</div>
            <dl><div><dt>utility</dt><dd>{numeric(goal.utility)}</dd></div>
              <div><dt>urgency</dt><dd>{numeric(goal.urgency)}</dd></div>
              <div><dt>target</dt><dd>{numeric(goal.target_strength)}</dd></div></dl>
            <small>{Array.isArray(goal.context)
              ? goal.context.map(String).join(" · ") : "no context logged"}</small>
          </article>)}
        </div> : <div className="pf-panel-gap">No goals were logged for this decision.</div>}
      </section>

      <section className="pf-panel">
        <header><div><span className="eyebrow">runtime activation</span>
          <h3>PF-PLN phases</h3></div><span className="pf-count">{phaseMetrics.length}</span></header>
        {phaseMetrics.length ? <div className="pf-phase-list">
          {phaseMetrics.map((event) => {
            const labels = recordOf(event.payload.labels);
            return <button key={event.event_id}
              onClick={() => onSelect({ kind: "event", value: event })}>
              <span>{String(labels.phase ?? "—")}</span>
              <strong>{String(labels.component ?? "unlabeled phase")}</strong>
              <small>{String(labels.reason ?? "—")} · {numeric(event.payload.value)}</small>
            </button>;
          })}
        </div> : <div className="pf-panel-gap">No pf_pln_phase_enabled metrics were logged.</div>}
      </section>
    </div>

    <section className="pf-panel pf-schedule">
      <header><div><span className="eyebrow">event-provided order / {scores.length} candidates</span>
        <h3>Candidate ranking</h3></div>
        <span className="pf-solver">{String(selectedDecision?.payload.solver_identity ?? "no solver identity")}</span>
      </header>
      {scores.length ? <>
        <CandidateRanking scores={scores} selectedOperationId={selectedOperationId}
          onInspect={() => selectedDecision
            && onSelect({ kind: "event", value: selectedDecision })} />
        <details className="pf-exact-table"><summary>Exact scheduler table</summary>
        <div className="pf-table" role="table" aria-label="PF-PLN operation schedule">
        <div className="pf-score-row head" role="row">
          <span>selection</span><span>category / action</span><span>admissible</span>
          <span>priority</span><span>value</span><span>reason</span>
        </div>
        {scores.slice(0, 100).map((score, index) => {
          const operation = recordOf(score.operation);
          const payload = recordOf(operation.payload);
          const action = recordOf(payload.action);
          const operationId = String(operation.operation_id ?? index);
          const selected = operationId === selectedOperationId;
          return <button role="row" key={operationId}
            className={`pf-score-row ${selected ? "selected" : ""}`}
            onClick={() => selectedDecision
              && onSelect({ kind: "event", value: selectedDecision })}>
            <span>{selected ? "◆ selected" : String(index + 1).padStart(2, "0")}</span>
            <span><strong>{String(payload.category ?? "uncategorized")}</strong>
              <small>{String(action.action_type ?? operation.mode ?? "—")}</small></span>
            <span className={score.admissible ? "yes" : "no"}>{
              score.admissible ? "yes" : "no"
            }</span>
            <span>{numeric(score.priority)}</span><span>{numeric(score.value)}</span>
            <span>{String(score.reason ?? "—")}</span>
          </button>;
        })}
        </div></details>
      </> : <div className="pf-panel-gap">No scheduler scores were logged.</div>}
    </section>

    <section className="pf-panel pf-pressure-panel">
        <header><div><span className="eyebrow">transport lineage / {traces.length} routes</span>
          <h3>Pressure topology</h3></div>
          <span className="pf-count">edge width = transported pressure</span></header>
        {traces.length && pressureEvent
          ? <PressureFlowGraph traces={traces} goals={goals}
            onInspect={() => onSelect({ kind: "event", value: pressureEvent })} />
          : <div className="pf-panel-gap">No pressure transport traces were logged.</div>}
    </section>

    <div className="pf-two-column pf-learning-runtime">
      <section className="pf-panel">
        <header><div><span className="eyebrow">grounded feedback / chronological history</span>
          <h3>Conductance trends</h3></div>
          <span className="pf-count">{state.conductanceUpdates.length}</span></header>
        {updatesByCategory.size ? <div className="pf-conductance-chart">
          {[...updatesByCategory.entries()].slice(0, 16).map(([category, updates], index) => {
            const latest = updates.at(-1)!;
            return <button key={category} onClick={() => onSelect({ kind: "event", value: latest })}>
              <span><strong>{humanize(category)}</strong><small>{category}</small></span>
              <Sparkline values={updates.map((event) => Number(event.payload.conductance))}
                minimum={0} maximum={1} color={CHART_COLORS[index % CHART_COLORS.length]}
                label={`${category} conductance history`} />
              <span className="pf-conductance-value">{numeric(latest.payload.conductance)}
                <small>{String(latest.payload.credit_kind ?? "legacy feedback")}</small></span>
            </button>;
          })}
        </div> : <div className="pf-panel-gap">No conductance_updated feedback was logged.</div>}
      </section>

      <section className="pf-panel pf-runtime">
        <header><div><span className="eyebrow">harness-emitted / no browser recomputation</span>
          <h3>Runtime composition</h3></div><span className="pf-count">{runtimeMetrics.length}</span></header>
        {runtimeMetrics.length ? <div className="pf-runtime-chart">
          {runtimeMetrics.map((event, index) => {
            const value = Number(event.payload.value);
            const unit = String(event.payload.unit);
            const sameUnitMaximum = Math.max(1, ...runtimeMetrics
              .filter((row) => row.payload.unit === event.payload.unit)
              .map((row) => Math.abs(Number(row.payload.value))));
            return <button key={event.event_id}
              onClick={() => onSelect({ kind: "event", value: event })}>
              <span><strong>{humanize(event.payload.name)}</strong>
                <small>{String(event.payload.name)}</small></span>
              <ValueBar value={value} maximum={sameUnitMaximum}
                color={CHART_COLORS[index % CHART_COLORS.length]}
                label={String(event.payload.name)} />
              <span className="pf-runtime-value">{numeric(value)} <small>{unit}</small></span>
            </button>;
          })}
        </div> : <div className="pf-panel-gap">No pressure latency or learning metrics were logged.</div>}
      </section>
    </div>
  </div>;
}

type TechnologyStatus = "known" | "current" | "researchable" | "blocked";

function TechnologyGraph({ catalog, progress, focus, onFocus }: {
  catalog: TechnologyCatalog; progress: TechnologyProgress; focus: string;
  onFocus: (name: string) => void;
}) {
  const byName = new Map(catalog.technologies.map((tech) => [tech.name, tech]));
  const known = new Set(progress.known_techs);
  const researchable = new Set(progress.researchable_techs);
  const blocked = new Set(progress.blocked_technologies.map((tech) => tech.name));
  const status = (name: string): TechnologyStatus =>
    name === progress.target?.name ? "current"
      : known.has(name) ? "known"
        : researchable.has(name) ? "researchable"
          : blocked.has(name) ? "blocked" : "blocked";
  const depthByName = new Map<string, number>([[focus, 0]]);
  const queue = [focus];
  while (queue.length) {
    const name = queue.shift();
    if (!name) continue;
    const depth = depthByName.get(name) ?? 0;
    for (const prerequisite of byName.get(name)?.prerequisites ?? []) {
      const prior = depthByName.get(prerequisite);
      if (prior === undefined || depth + 1 < prior) {
        depthByName.set(prerequisite, depth + 1);
        queue.push(prerequisite);
      }
    }
  }
  const levels = new Map<number, string[]>();
  for (const [name, depth] of depthByName) {
    levels.set(depth, [...levels.get(depth) ?? [], name].sort());
  }
  const maximumDepth = Math.max(0, ...levels.keys());
  const height = Math.max(220, ...[...levels.values()].map((items) => items.length * 62 + 50));
  const position = new Map<string, { x: number; y: number }>();
  for (const [depth, names] of levels) {
    names.forEach((name, index) => position.set(name, {
      x: 90 + depth * (760 / Math.max(1, maximumDepth)),
      y: 34 + (index + 0.5) * ((height - 64) / names.length),
    }));
  }
  return <div className="tech-graph-wrap">
    <svg className="tech-graph" viewBox={`0 0 940 ${height}`} role="img"
      aria-label={`Prerequisite graph for ${focus}`}>
      <defs><marker id="tech-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4"
        orient="auto"><path d="M0,0 L8,4 L0,8 z" /></marker></defs>
      {[...depthByName].flatMap(([name]) =>
        (byName.get(name)?.prerequisites ?? []).filter((item) => depthByName.has(item))
          .map((prerequisite) => {
            const from = position.get(name);
            const to = position.get(prerequisite);
            return from && to ? <line key={`${name}-${prerequisite}`}
              x1={from.x - 10} y1={from.y} x2={to.x + 10} y2={to.y}
              markerEnd="url(#tech-arrow)" /> : null;
          }))}
      {[...depthByName].map(([name]) => {
        const point = position.get(name);
        if (!point) return null;
        const techStatus = status(name);
        return <g key={name} transform={`translate(${point.x} ${point.y})`}
          className={`tech-node ${techStatus}`} role="button" tabIndex={0}
          aria-label={`${name}, ${techStatus}`}
          onClick={() => onFocus(name)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") onFocus(name);
          }}>
          <circle r={name === focus ? 12 : 9} />
          <text x={depthByName.get(name) === 0 ? -16 : 16}
            textAnchor={depthByName.get(name) === 0 ? "end" : "start"}>{name}</text>
          <title>{name} · {techStatus}</title>
        </g>;
      })}
    </svg>
    <footer><span className="known">known</span><span className="current">current research</span>
      <span className="researchable">researchable now</span><span className="blocked">blocked</span></footer>
  </div>;
}

export function TechnologyDashboard({ state, onSelect }: {
  state: ReplayState; onSelect: (selection: Selection) => void;
}) {
  const catalogEvent = state.technologyCatalogs.at(-1);
  const progressEvent = state.technologyProgress.at(-1);
  const [statusFilter, setStatusFilter] = useState<"all" | TechnologyStatus>("all");
  const [search, setSearch] = useState("");
  const [focusTech, setFocusTech] = useState("");
  if (!catalogEvent || !progressEvent) return <LoggingGap title="No technology trace at this cursor"
    detail="Load an observability-v2 trace or run the hardened harness. The browser will not infer a tech tree from Atomspace snapshots." />;
  const catalog = catalogEvent.payload as unknown as TechnologyCatalog;
  const progress = progressEvent.payload as unknown as TechnologyProgress;
  const byName = new Map(catalog.technologies.map((tech) => [tech.name, tech]));
  const known = new Set(progress.known_techs);
  const researchable = new Set(progress.researchable_techs);
  const blockerByName = new Map(progress.blocked_technologies.map((tech) => [tech.name, tech]));
  const selectedTech = byName.has(focusTech)
    ? focusTech : progress.target?.name ?? catalog.technologies[0]?.name ?? "";
  const techStatus = (name: string): TechnologyStatus =>
    name === progress.target?.name ? "current"
      : known.has(name) ? "known"
        : researchable.has(name) ? "researchable" : "blocked";
  const target = progress.target;
  const progressSeries = state.technologyProgress
    .map((event) => (event.payload as unknown as TechnologyProgress).target)
    .flatMap((item) => {
      if (!item || item.name !== target?.name || typeof item.progress !== "number") return [];
      return [item.progress];
    });
  const rateSeries = state.technologyProgress
    .map((event) => (event.payload as unknown as TechnologyProgress).target)
    .flatMap((item) => {
      if (!item || item.name !== target?.name
          || typeof item.beakers_per_turn !== "number") return [];
      return [item.beakers_per_turn];
    });
  const acquisitions = state.technologyProgress.flatMap((event) =>
    (event.payload as unknown as TechnologyProgress).acquired_techs.map((name) => ({ name, event })));
  const rows = catalog.technologies.filter((tech) =>
    tech.name.toLowerCase().includes(search.toLowerCase())
    && (statusFilter === "all" || techStatus(tech.name) === statusFilter));
  const selectedBlocker = blockerByName.get(selectedTech);
  const relatedProof = [...state.proofs].reverse().find(({ result }) =>
    result.proof.nodes.some((node) =>
      node.atom.predicate === "researchable"
      && node.atom.args.some((argument) => String(argument) === selectedTech)));
  const government = progress.government;
  const stallExplanation = progress.stall_reason === "government_anarchy"
    ? `${government?.current_name ?? "Anarchy"} is suppressing science output. ${
      government?.selection_required
        ? "The revolution has finished and Freeciv is waiting for a government selection."
        : "The revolution is still in progress."}`
    : progress.stall_reason === "city_disorder"
      ? "At least one city is in disorder, so its productive output is disrupted."
      : progress.stall_reason === "zero_science_output"
        ? "The emitted city economy currently produces zero net science."
        : null;
  return <div className="view-content technology-view">
    <div className="view-heading">
      <div><span className="eyebrow">ruleset-pinned research telemetry</span>
        <h2>Technology progress</h2></div>
      <p>{catalog.technologies.length} technologies · IR {catalog.ir_hash.slice(0, 12)} ·
        {" "}strictly as emitted at T{progressEvent.turn}.{progressEvent.seq}</p>
    </div>
    <section className={`research-hero ${progress.status}`}>
      <div><span className="eyebrow">current target</span>
        <h3>{target?.name ?? "No research target logged"}</h3>
        <strong>{progress.status}</strong></div>
      <div className="research-progress">
        <div><span>{target?.progress ?? "—"} / {target?.cost ?? "—"} beakers</span>
          <span>{target?.remaining ?? "—"} remaining</span></div>
        <progress max={Math.max(1, target?.cost ?? 1)} value={target?.progress ?? 0} />
      </div>
      <dl>
        <div><dt>rate</dt><dd>{target?.beakers_per_turn ?? "—"} / turn</dd></div>
        <div><dt>ETA</dt><dd>{target?.eta_turns === null || target?.eta_turns === undefined
          ? "not converging" : `${target.eta_turns} turns`}</dd></div>
        <div><dt>stalled</dt><dd>{progress.stalled_turns} turns</dd></div>
        <div><dt>known</dt><dd>{progress.known_techs.length}</dd></div>
      </dl>
    </section>
    {progress.status === "stalled" && <section className="research-alert" role="status">
      <strong>Research is stalled.</strong>
      <span>{target?.name} still needs {target?.remaining ?? "unknown"} beakers, but the
        latest emitted rate is {target?.beakers_per_turn ?? "unknown"} per turn. Running longer
        under the same economy will not finish it.{stallExplanation && ` ${stallExplanation}`}</span>
    </section>}
    {government && <section className={`government-status ${
      government.selection_required ? "action-required" : ""}`}>
      <div><span className="eyebrow">government</span>
        <strong>{government.current_name ?? "unknown"}</strong>
        <small>{government.in_revolution ? "revolution state" : "stable government"}</small></div>
      <div><span>target</span><strong>{government.target_name ?? "none selected"}</strong>
        <small>{government.selection_required
          ? "selection required now" : "no intervention required"}</small></div>
      <div><span>revolution finishes</span>
        <strong>{government.revolution_finishes ?? "—"}</strong>
        <small>authoritative turn marker</small></div>
      <p>{government.selection_required
        ? "PF-PLN now prioritizes a packet-legal government_change action above ordinary planning so research can resume."
        : "Research state and government state are shown together because revolution policy can set effective science output to zero."}</p>
    </section>}
    <div className="tech-series">
      <section><header><span>target progress</span><strong>{progressSeries.at(-1) ?? "—"}</strong></header>
        <Sparkline values={progressSeries} minimum={0} maximum={target?.cost ?? undefined}
          label={`${target?.name ?? "Research"} accumulated beakers`} /></section>
      <section><header><span>science throughput</span><strong>{rateSeries.at(-1) ?? "—"}</strong></header>
        <Sparkline values={rateSeries} minimum={0}
          label={`${target?.name ?? "Research"} beakers per turn`} /></section>
      <section><header><span>acquisitions this run</span><strong>{acquisitions.length}</strong></header>
        <div className="tech-acquisitions">{acquisitions.length
          ? acquisitions.slice(-6).map(({ name, event }) => <button key={`${name}-${event.event_id}`}
            onClick={() => onSelect({ kind: "event", value: event })}>{name}<small>T{event.turn}</small></button>)
          : <span>No post-initial technology acquisition logged.</span>}</div></section>
    </div>
    <section className="technology-dependencies">
      <header><div><span className="eyebrow">compiled dependency lineage</span>
        <h3>{selectedTech}</h3></div>
        <div className={`tech-status ${techStatus(selectedTech)}`}>{techStatus(selectedTech)}</div></header>
      <TechnologyGraph catalog={catalog} progress={progress} focus={selectedTech}
        onFocus={setFocusTech} />
      <div className="tech-evidence">
        <span>direct prerequisites</span>
        <strong>{byName.get(selectedTech)?.prerequisites.join(" · ") || "root technology"}</strong>
        <span>missing prerequisites</span>
        <strong>{selectedBlocker?.missing_prerequisites.join(" · ") || "none"}</strong>
        {relatedProof && <button onClick={() => {
          onSelect({ kind: "event", value: relatedProof.event });
          window.dispatchEvent(new CustomEvent("observatory:view", { detail: "proofs" }));
        }}>open logged PLN proof at T{relatedProof.event.turn} →</button>}
      </div>
    </section>
    <section className="technology-catalog">
      <header><input aria-label="Search technologies" placeholder="technology…"
        value={search} onChange={(event) => setSearch(event.target.value)} />
        <select aria-label="Technology status" value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
          <option value="all">all statuses</option><option value="current">current</option>
          <option value="researchable">researchable</option><option value="blocked">blocked</option>
          <option value="known">known</option>
        </select><span>{rows.length} shown</span></header>
      <div className="tech-table">
        <div className="head"><span>technology</span><span>status</span>
          <span>direct prerequisites</span><span>missing now</span></div>
        {rows.map((tech) => <button key={tech.name} onClick={() => setFocusTech(tech.name)}>
          <strong>{tech.name}</strong><span className={techStatus(tech.name)}>
            {techStatus(tech.name)}</span>
          <span>{tech.prerequisites.join(", ") || "—"}</span>
          <span>{blockerByName.get(tech.name)?.missing_prerequisites.join(", ") || "—"}</span>
        </button>)}
      </div>
    </section>
    <footer className="display-boundary"><b>Proof vocabulary:</b> <code>missing-tech</code> means
      a required technology is not known and is itself currently researchable. A technology
      with unmet prerequisites appears as <em>blocked</em> here with those prerequisites named.</footer>
  </div>;
}

const yieldKeys = ["food", "shield", "trade", "gold", "luxury", "science"] as const;

export function EconomyProductionDashboard({ state, onSelect }: {
  state: ReplayState; onSelect: (selection: Selection) => void;
}) {
  const event = state.productionStates.at(-1);
  if (!event) return <LoggingGap title="No economy or production trace at this cursor"
    detail="Load an observability-v2 trace or run the hardened harness. Generic snapshots remain inspectable, but this view requires production_state events." />;
  const production = event.payload as unknown as ProductionState;
  const actionEvents = state.events.filter((row) =>
    row.type === "action_sent"
    && (row.payload.action as Record<string, unknown> | undefined)?.action_type === "city_production");
  const sustainabilityActionTypes = new Set([
    "city_governor", "city_production", "player_rates", "unit_disband",
    "unit_home_city",
  ]);
  const sustainabilityActions = state.events.filter((row) =>
    row.type === "action_sent"
    && sustainabilityActionTypes.has(String(
      (row.payload.action as Record<string, unknown> | undefined)?.action_type ?? "")));
  const completions = state.unitLifecycles.filter((row) =>
    (row.payload as unknown as UnitLifecycle).cause === "production_completed");
  const buildableProofs = state.proofs.filter(({ result }) =>
    result.proof.nodes.some((node) => node.atom.predicate === "buildable"));
  const totalSeries = (key: typeof yieldKeys[number]) => state.productionStates.map((row) => {
    const payload = row.payload as unknown as ProductionState;
    return payload.cities.reduce((sum, city) => sum + Number(city.outputs[key] ?? 0), 0);
  });
  const latestProjection = (cityId: number, targetName: string | null) => {
    for (const scored of [...state.operationScores].reverse()) {
      for (const score of rowsOf(scored.payload.scores)) {
        const operation = recordOf(score.operation);
        const payload = recordOf(operation.payload);
        const action = recordOf(payload.action);
        const target = recordOf(action.target);
        if (Number(action.city_id) === cityId
            && (!targetName || String(target.production_type) === targetName)) {
          const projection = recordOf(payload.projection);
          if (Object.keys(projection).length) {
            return {
              projection, event: scored,
              category: String(payload.category ?? "uncategorized"),
            };
          }
        }
      }
    }
    return undefined;
  };
  const completionsByType = completions.reduce((counts, row) => {
    const payload = row.payload as unknown as UnitLifecycle;
    counts.set(payload.unit_type, (counts.get(payload.unit_type) ?? 0) + 1);
    return counts;
  }, new Map<string, number>());
  const totalSupport = production.cities.reduce((totals, city) => ({
    count: totals.count + (city.support?.count ?? 0),
    food: totals.food + (city.support?.food ?? 0),
    shield: totals.shield + (city.support?.shield ?? 0),
    gold: totals.gold + (city.support?.gold ?? 0),
  }), { count: 0, food: 0, shield: 0, gold: 0 });
  const cityGoldSurplus = production.economy.city_gold_surplus_per_turn;
  const unitGoldUpkeep = production.economy.unit_gold_upkeep;
  const netGold = production.economy.gold_per_turn
    ?? (cityGoldSurplus !== null && cityGoldSurplus !== undefined
      && unitGoldUpkeep !== null && unitGoldUpkeep !== undefined
      ? cityGoldSurplus - unitGoldUpkeep : null);
  const goldReserve = production.economy.gold_upkeep_reserve
    ?? unitGoldUpkeep ?? null;
  const plannerGoldReserve = goldReserve === null ? null : Math.max(5, goldReserve * 2);
  const pressureEvent = state.pressurePropagations.at(-1);
  const pressureGoals = rowsOf(pressureEvent?.payload.goals);
  const pressureGoal = (suffix: string) => pressureGoals.find((goal) =>
    String(goal.goal_id ?? "").endsWith(`:${suffix}`));
  const goalContext = (suffix: string) => {
    const context = pressureGoal(suffix)?.context;
    return Array.isArray(context) ? context.map(String).join(" · ") : "PF goal not logged";
  };
  const foodContext = goalContext("food_sustainability");
  const treasuryContext = goalContext("treasury_sustainability");
  const defenseContext = goalContext("survival");
  const foodGoalAtRisk =
    foodContext.includes("authoritative:city-food-surplus-reserve-deficit");
  const treasuryGoalAtRisk =
    treasuryContext.includes("authoritative:net-gold-or-turn-start-upkeep-reserve-deficit");
  const treasuryCrossesRunway = netGold !== null && netGold < 0
    && production.economy.gold !== null && plannerGoldReserve !== null
    && production.economy.gold + netGold * 2 < plannerGoldReserve;
  const treasuryAtRisk = treasuryGoalAtRisk
    || treasuryCrossesRunway
    || (production.economy.gold !== null && plannerGoldReserve !== null
      && production.economy.gold < plannerGoldReserve);
  const foodDeficits = production.cities.filter((city) =>
    city.surplus.food !== null && Number(city.surplus.food) < 1);
  const foodAtRisk = foodGoalAtRisk || foodDeficits.length > 0;
  const defenseAtRisk =
    defenseContext.includes("authoritative:grounded-production-defense-deficit")
    || defenseContext.includes("authoritative:visible-enemy");
  return <div className="view-content economy-view">
    <div className="view-heading">
      <div><span className="eyebrow">authoritative stocks, rates, queues, projections</span>
        <h2>Economy &amp; production</h2></div>
      <p>{production.cities.length} cities · {actionEvents.length} explicit queue changes ·
        {" "}{completions.length} inferred completions as of cursor</p>
    </div>
    <section className="economy-strip">
      <div><span>treasury</span><strong>{production.economy.gold ?? "—"}</strong><small>gold</small></div>
      <div className={treasuryAtRisk ? "at-risk" : ""}><span>net cash flow</span>
        <strong>{netGold ?? "—"}</strong><small>after unit upkeep</small></div>
      <div><span>city gold surplus</span><strong>{cityGoldSurplus ?? "—"}</strong>
        <small>{production.economy.gold_upkeep_style ?? "unknown"} upkeep style</small></div>
      <div><span>unit upkeep</span><strong>{unitGoldUpkeep ?? "—"}</strong><small>gold / turn</small></div>
      <div><span>planner reserve</span><strong>{plannerGoldReserve ?? "—"}</strong><small>two-turn runway</small></div>
      <div><span>science</span><strong>{production.economy.science_rate ?? "—"}%</strong><small>allocation</small></div>
      <div><span>tax</span><strong>{production.economy.tax_rate ?? "—"}%</strong><small>allocation</small></div>
      <div><span>luxury</span><strong>{production.economy.luxury_rate ?? "—"}%</strong><small>allocation</small></div>
    </section>
    <section className="sustainability-overview">
      <article className={foodAtRisk ? "at-risk" : "safe"}>
        <header><span>food reserve</span><strong>{foodAtRisk ? "at risk" : "safe"}</strong></header>
        <b>{foodDeficits.length} / {production.cities.length} cities below +1</b>
        <small>{foodContext}</small>
      </article>
      <article className={treasuryAtRisk ? "at-risk" : "safe"}>
        <header><span>treasury reserve</span><strong>{treasuryAtRisk ? "at risk" : "safe"}</strong></header>
        <b>{netGold ?? "—"} net · {production.economy.gold ?? "—"} stock</b>
        <small>{treasuryContext}</small>
      </article>
      <article className={defenseAtRisk ? "at-risk" : "safe"}>
        <header><span>local defense</span><strong>{defenseAtRisk ? "pressure active" : "covered"}</strong></header>
        <b>garrisons + visible threats</b><small>{defenseContext}</small>
      </article>
      {pressureEvent && <button onClick={() =>
        onSelect({ kind: "event", value: pressureEvent })}>inspect PF goal field →</button>}
    </section>
    {production.government && <section className={`economy-government ${
      production.government.in_revolution ? "revolution" : ""}`}>
      <div><span>government</span><strong>{production.government.current_name ?? "unknown"}</strong>
        <small>{production.government.selection_required
          ? "government selection required" : "authoritative player state"}</small></div>
      <div><span>supported units</span><strong>{totalSupport.count}</strong>
        <small>home-city ownership tracked</small></div>
      <div><span>support burden</span>
        <strong>{totalSupport.food}F · {totalSupport.shield}S · {totalSupport.gold}G</strong>
        <small>packet upkeep vectors</small></div>
      <p>{production.government.in_revolution
        ? "Revolution is active. Compare effective yields here with the configured tax rates; the planner will exit completed Anarchy before ordinary production."
        : "Production, resource output, citizen mood, and unit support are emitted from the same authoritative snapshot."}</p>
    </section>}
    <section className="yield-series">
      {yieldKeys.map((key, index) => {
        const values = totalSeries(key);
        return <div key={key}><header><strong>{humanize(key)}</strong>
          <span>{values.at(-1) ?? 0}</span></header>
          <Sparkline values={values} minimum={0}
            color={CHART_COLORS[index % CHART_COLORS.length]}
            label={`Emitted city ${key} output display sum`} /></div>;
      })}
    </section>
    <div className="production-layout">
      <section className="city-production-list">
        <header><span className="eyebrow">current city queues</span>
          <strong>{production.cities.length} active cities</strong></header>
        {production.cities.map((city) => {
          const projected = latestProjection(city.city_id, city.target.name);
          const cityFoodAtRisk = city.surplus.food !== null
            && Number(city.surplus.food) < 1;
          return <article key={city.city_id}>
            <header><div><span>#{city.city_id}</span><h3>{city.name}</h3></div>
              <strong>{city.target.name ?? `kind ${city.target.kind} / ${city.target.value}`}</strong></header>
            <div className="city-stocks">
              <div><span>population</span><b>{city.size}</b></div>
              <div><span>food stock</span><b>{city.food_stock ?? "—"}</b></div>
              <div><span>shield stock</span><b>{city.shield_stock ?? "—"}</b></div>
              <div><span>buildable</span><b>{city.buildable_count}</b></div>
            </div>
            {(city.mood || city.support) && <div className={`city-sustainability ${
              city.mood?.disorder || cityFoodAtRisk || city.had_famine ? "at-risk" : ""}`}>
              <div className={cityFoodAtRisk ? "food-risk" : ""}><span>food reserve</span>
                <b>{city.surplus.food === null ? "—"
                  : `${Number(city.surplus.food) >= 0 ? "+" : ""}${city.surplus.food}`}</b>
                <small>{cityFoodAtRisk ? "below planner reserve +1" : "planner reserve satisfied"}</small></div>
              <div><span>citizen mood</span>
                <b>{city.mood?.disorder ? "disorder" : city.mood ? "order" : "—"}</b>
                <small>{city.mood?.final.happy ?? "—"} happy ·
                  {" "}{city.mood?.final.unhappy ?? "—"} unhappy ·
                  {" "}{city.mood?.final.angry ?? "—"} angry</small></div>
              <div><span>mood margin</span><b>{city.mood?.margin ?? "—"}</b>
                <small>happy − unhappy − 2×angry</small></div>
              <div><span>unit support</span><b>{city.support?.count ?? 0}</b>
                <small>{city.support?.food ?? 0} food · {city.support?.shield ?? 0} shields ·
                  {" "}{city.support?.gold ?? 0} gold</small></div>
              <div><span>famine flag</span><b>{city.had_famine ? "yes" : "no"}</b>
                <small>{city.had_famine
                  ? "server reported famine this turn" : "no famine reported"}</small></div>
              <div className={city.governor?.available
                  && city.governor.enabled ? "governor-active" : ""}>
                <span>food governor</span>
                <b>{!city.governor?.available ? "unavailable"
                  : city.governor.enabled ? "active" : "available"}</b>
                <small>{city.governor?.available
                  ? `packet floor ${city.governor.minimal_surplus[0] ?? "—"} · food weight ${
                    city.governor.factor[0] ?? "—"}`
                  : "server CMA capability not observed"}</small>
              </div>
            </div>}
            <div className="yield-grid">
              {yieldKeys.map((key) => <div key={key}><span>{key}</span>
                <strong>{city.outputs[key] ?? "—"}</strong>
                <small>{city.surplus[key] === null ? "—" :
                  `${Number(city.surplus[key]) >= 0 ? "+" : ""}${city.surplus[key]} surplus`}</small>
              </div>)}
            </div>
            {projected ? <button className="production-projection"
              onClick={() => onSelect({ kind: "event", value: projected.event })}>
              <span><b>PF-PLN projection</b><small>{humanize(projected.category)}</small></span>
              <span><b>{numeric(projected.projection.completion_eta_turns)}</b><small>turn ETA</small></span>
              <span><b>{numeric(projected.projection.build_cost)}</b><small>shield cost</small></span>
              <span><b>{numeric(projected.projection.shield_surplus)}</b><small>shield / turn</small></span>
              <span><b>{numeric(projected.projection.projected_unit_completions)}</b><small>horizon units</small></span>
            </button> : <div className="production-projection gap">
              No PF-PLN projection logged for the current queue.</div>}
            {projected?.projection.sustainability_override === true
              && <div className="sustainability-route"><strong>Safety override</strong>
                <span>Queue interruption prevents the next upkeep breach.</span>
                <small>{numeric(projected.projection.avoided_next_completion_upkeep)}
                  {" "}upkeep avoided · {numeric(projected.projection.discarded_shield_stock)}
                  {" "}shields discarded</small></div>}
          </article>;
        })}
      </section>
      <aside className="production-evidence">
        <section><span className="eyebrow">observed production</span><h3>Unit completions</h3>
          {[...completionsByType].sort((a, b) => b[1] - a[1]).map(([name, count]) =>
            <div key={name}><span>{name}</span><strong>{count}</strong></div>)}
          {!completionsByType.size && <p>No completion lifecycle events at this cursor.</p>}
          <small>Historical completions are snapshot-matched and labeled inferred.</small>
        </section>
        <section><span className="eyebrow">model coverage</span><h3>PLN versus PF-PLN</h3>
          <div><span>buildable PLN proofs</span><strong>{buildableProofs.length}</strong></div>
          <div><span>PF operation score events</span><strong>{state.operationScores.length}</strong></div>
          <p>{buildableProofs.length
            ? "Production dependency proofs and PF candidate projections are both present."
            : "No buildable PLN query was logged. Production still affected PF-PLN candidate scoring, but it was not represented as a PLN proof in this run."}</p>
        </section>
        <section><span className="eyebrow">queue decisions</span><h3>Recent changes</h3>
          {sustainabilityActions.slice(-10).reverse().map((row) => {
            const action = row.payload.action as Record<string, unknown>;
            const target = recordOf(action.target);
            return <button key={row.event_id}
              onClick={() => onSelect({ kind: "event", value: row })}>
              <span>T{row.turn} · {humanize(action.action_type)}</span>
              <strong>{String(target.production_type
                ?? (target.tax_rate !== undefined
                  ? `${target.tax_rate}% tax / ${target.science_rate}% science`
                  : target.food_surplus_reserve !== undefined
                    ? `city ${action.city_id} · +${target.food_surplus_reserve} food floor`
                  : action.actor_id !== undefined ? `unit ${action.actor_id}` : "player control"))}</strong>
            </button>;
          })}
          {!sustainabilityActions.length && <p>No sustainability control action at this cursor.</p>}
        </section>
      </aside>
    </div>
    <footer className="display-boundary">City outputs, stocks, support, and cash-flow
      components are exact emitted values. A food reserve below +1 and the upkeep-reserve
      warning are configured planner thresholds. Totals and sparklines are display aggregations.
      PF-PLN goals and projections are shown verbatim from <code>pressure_propagated</code> and
      {" "}<code>operation_scored</code>; inferred completions are never relabeled as exact.</footer>
  </div>;
}

export function UnitLifecycleDashboard({ state, onSelect }: {
  state: ReplayState; onSelect: (selection: Selection) => void;
}) {
  const [quality, setQuality] = useState<"all" | UnitLifecycle["evidence_quality"]>("all");
  const [transition, setTransition] = useState<"all" | UnitLifecycle["transition"]>("all");
  if (!state.unitLifecycles.length) return <LoggingGap title="No unit lifecycle trace at this cursor"
    detail="Load an observability-v2 trace or run the hardened proxy. Exact disappearance causes cannot be reconstructed from generic snapshots." />;
  const rows = state.unitLifecycles.map((event) => ({
    event, payload: event.payload as unknown as UnitLifecycle,
  }));
  const visible = rows.filter(({ payload }) =>
    (quality === "all" || payload.evidence_quality === quality)
    && (transition === "all" || payload.transition === transition));
  const appearances = rows.filter(({ payload }) => payload.transition === "appeared");
  const disappearances = rows.filter(({ payload }) => payload.transition === "disappeared");
  const qualityCounts = rows.reduce((counts, { payload }) => {
    counts.set(payload.evidence_quality, (counts.get(payload.evidence_quality) ?? 0) + 1);
    return counts;
  }, new Map<string, number>());
  const causeCounts = disappearances.reduce((counts, { payload }) => {
    counts.set(payload.cause, (counts.get(payload.cause) ?? 0) + 1);
    return counts;
  }, new Map<string, number>());
  const unitCounts = new Map<number, number>();
  let current = 0;
  for (const { event, payload } of rows) {
    current += payload.transition === "appeared" ? 1 : -1;
    unitCounts.set(event.turn, current);
  }
  const populationSeries = [...unitCounts].sort((a, b) => a[0] - b[0]).map(([, count]) => count);
  return <div className="view-content forces-view">
    <div className="view-heading">
      <div><span className="eyebrow">asset provenance and attrition</span><h2>Unit lifecycle</h2></div>
      <p>Every row states how strongly its cause is supported. Unknown boundary removals stay unknown.</p>
    </div>
    <section className="lifecycle-summary">
      <div><span>appeared</span><strong>{appearances.length}</strong><small>including initial state</small></div>
      <div><span>disappeared</span><strong>{disappearances.length}</strong><small>all causes</small></div>
      <div className="exact"><span>exact</span><strong>{qualityCounts.get("exact") ?? 0}</strong><small>packet/state evidence</small></div>
      <div className="inferred"><span>inferred</span><strong>{qualityCounts.get("inferred") ?? 0}</strong><small>explicit correlation</small></div>
      <div className="unattributed"><span>unattributed</span><strong>{qualityCounts.get("unattributed") ?? 0}</strong><small>cause not logged</small></div>
    </section>
    <div className="lifecycle-overview">
      <section><header><span className="eyebrow">observed force size</span>
        <strong>{populationSeries.at(-1) ?? 0} units</strong></header>
        <Sparkline values={populationSeries} minimum={0} label="Observed own unit count" /></section>
      <section><header><span className="eyebrow">disappearance causes</span>
        <strong>{causeCounts.size} categories</strong></header>
        <div className="cause-bars">{[...causeCounts].sort((a, b) => b[1] - a[1])
          .map(([cause, count]) => <button key={cause}
            onClick={() => {
              const match = [...rows].reverse().find(({ payload }) => payload.cause === cause);
              if (match) onSelect({ kind: "event", value: match.event });
            }}><span>{humanize(cause)}</span><ValueBar value={count}
              maximum={Math.max(1, ...causeCounts.values())} label={`${cause} count`} />
            <strong>{count}</strong></button>)}</div>
      </section>
    </div>
    <section className="lifecycle-method">
      <article><strong>Exact</strong><p>A combat packet or Freeciv notification identified
        the cause, including insufficient-gold disbands, food-support losses, and transport loss.</p></article>
      <article><strong>Inferred</strong><p>A bounded packet correlation supports the cause:
        for example, another unit disappeared on the same tile and turn as kill-stack combat.</p></article>
      <article><strong>Unattributed</strong><p>The unit existed in one snapshot and not the next.
        No combat packet or matching server notification identified why it vanished.</p></article>
    </section>
    <section className="lifecycle-table">
      <header><div>
        <label>transition <select aria-label="Lifecycle transition" value={transition}
          onChange={(event) => setTransition(event.target.value as typeof transition)}>
          <option value="all">all</option><option value="appeared">appeared</option>
          <option value="disappeared">disappeared</option>
        </select></label>
        <label>evidence <select aria-label="Lifecycle evidence quality" value={quality}
          onChange={(event) => setQuality(event.target.value as typeof quality)}>
          <option value="all">all</option><option value="exact">exact</option>
          <option value="inferred">inferred</option><option value="unattributed">unattributed</option>
        </select></label>
      </div><span>{visible.length} transitions</span></header>
      <div className="head"><span>turn</span><span>transition</span><span>unit</span>
        <span>cause</span><span>evidence</span><span>detail</span></div>
      {visible.slice(-500).reverse().map(({ event, payload }) => <button key={event.event_id}
        onClick={() => onSelect({ kind: "event", value: event })}>
        <span>T{event.turn}</span><strong>{payload.transition}</strong>
        <span>#{payload.unit_id} · {payload.unit_type}</span>
        <span>{humanize(payload.cause)}</span>
        <span className={payload.evidence_quality}>{payload.evidence_quality}</span>
        <span title={payload.detail ?? ""}>{payload.detail ?? "No detail logged"}</span>
      </button>)}
    </section>
    <footer className="display-boundary">Historical traces keep their original uncertainty.
      New runs correlate <code>PACKET_UNIT_REMOVE</code> with combat, tile/turn context, and
      Freeciv notifications; every row retains its exact, inferred, or unattributed label.</footer>
  </div>;
}

function MetricsDashboard({ state, onSelect }: {
  state: ReplayState; onSelect: (selection: Selection) => void;
}) {
  const [unitFilter, setUnitFilter] = useState("all");
  if (!state.metrics.length) return <LoggingGap title="No metric samples at this cursor"
    detail="Calibration, intervals, and ablations are rendered only from metric_sample events." />;
  const conditions = [...new Set(state.metrics.map((event) =>
    String((event.payload.labels as Record<string, string> | undefined)?.condition ?? "run")))];
  const units = [...new Set(state.metrics.map((event) => String(event.payload.unit)))].sort();
  const grouped = new Map<string, TraceEvent[]>();
  for (const event of state.metrics) {
    if (unitFilter !== "all" && event.payload.unit !== unitFilter) continue;
    const key = `${String(event.payload.name)}\u0000${String(event.payload.unit)}`;
    grouped.set(key, [...grouped.get(key) ?? [], event]);
  }
  const metricSeries = [...grouped.values()].sort((left, right) =>
    String(left[0].payload.name).localeCompare(String(right[0].payload.name)));
  const maximumByUnit = new Map<string, number>();
  for (const series of metricSeries) {
    const unit = String(series[0].payload.unit);
    const latest = Math.abs(Number(series.at(-1)?.payload.value ?? 0));
    maximumByUnit.set(unit, Math.max(latest, maximumByUnit.get(unit) ?? 0));
  }
  return <div className="view-content metrics-view"><div className="view-heading">
    <div><span className="eyebrow">harness-emitted values</span><h2>Metrics dashboard</h2></div>
    <p>{state.metrics.length} samples · UI calculations disabled</p>
  </div><div className="metric-tools">
    <div className="condition-strip">{conditions.map((condition) => <span key={condition}>{condition}</span>)}</div>
    <label>unit <select aria-label="Metric unit" value={unitFilter}
      onChange={(event) => setUnitFilter(event.target.value)}>
      <option value="all">all units</option>
      {units.map((unit) => <option key={unit} value={unit}>{unit}</option>)}
    </select></label>
  </div>
  <section className="metric-series-chart" aria-label="Metric time series and latest values">
    <header><span>metric</span><span>logged series</span><span>latest / relative within unit</span></header>
    {metricSeries.map((series, index) => {
      const latest = series.at(-1)!;
      const name = String(latest.payload.name);
      const unit = String(latest.payload.unit);
      const value = Number(latest.payload.value);
      const labels = latest.payload.labels as Record<string, string> | undefined;
      return <button key={`${name}-${unit}`} onClick={() => onSelect({ kind: "event", value: latest })}>
        <span><strong>{humanize(name)}</strong><small>{name}</small>
          <em>{String(labels?.condition ?? "run")} · {String(labels?.statistic ?? "sample")}</em></span>
        <Sparkline values={series.map((event) => Number(event.payload.value))}
          color={CHART_COLORS[index % CHART_COLORS.length]} label={`${name} logged values`} />
        <span className="metric-latest"><strong>{value.toLocaleString()}</strong><small>{unit}</small>
          <ValueBar value={value} maximum={maximumByUnit.get(unit) ?? 1}
            color={CHART_COLORS[index % CHART_COLORS.length]}
            label={`${name} relative magnitude within ${unit}`} />
        </span>
      </button>;
    })}
  </section>
  <footer className="display-boundary">Sparklines connect logged samples. Bar lengths are display scaling within a unit;
    the UI does not recompute experimental statistics.</footer>
  </div>;
}

function HowItWorks({ onNavigate }: { onNavigate: (view: ViewName) => void }) {
  const questions: Array<{
    question: string; answer: string; view: ViewName; label: string;
  }> = [
    {
      question: "What happened?",
      answer: "Replay every logged stage in order and follow an action back through its causal ancestry.",
      view: "timeline",
      label: "Decision timeline",
    },
    {
      question: "Why was it allowed?",
      answer: "Inspect the exact proof tree, confidence values, rules, and unsatisfied frontier.",
      view: "proofs",
      label: "Proof explorer",
    },
    {
      question: "What did the agent know?",
      answer: "See the atomspace exactly as it existed at the selected turn and sequence.",
      view: "atoms",
      label: "Atomspace",
    },
    {
      question: "What changed the plan?",
      answer: "Trace dependencies, invalidations, repairs, timing, and their map-level consequences.",
      view: "plans",
      label: "Plan board",
    },
    {
      question: "Did the policy behave differently?",
      answer: "Compare exact paired arms and inspect pressure, rankings, learning, and logged outcomes.",
      view: "pfpln",
      label: "PF-PLN",
    },
    {
      question: "Why is research stuck?",
      answer: "Track the current target, accumulated beakers, science rate, stall duration, acquisitions, and the ruleset-pinned prerequisite graph.",
      view: "technology",
      label: "Technology",
    },
    {
      question: "What is each city producing?",
      answer: "Inspect named yields, stocks, queues, explicit queue changes, observed completions, and PF-PLN production projections.",
      view: "economy",
      label: "Economy & production",
    },
    {
      question: "Why did a unit disappear?",
      answer: "Review every lifecycle transition, cause category, supporting evidence, and whether the cause is exact, inferred, or unavailable.",
      view: "forces",
      label: "Unit lifecycle",
    },
    {
      question: "Can I trust the trace?",
      answer: "Surface quarantines, causal gaps, schema issues, and prohibited write-throughs.",
      view: "audit",
      label: "Epistemic audit",
    },
  ];

  return <div className="view-content about-view">
    <section className="about-hero">
      <div className="about-hero-copy">
        <span className="eyebrow">orientation / evidence before inference</span>
        <h2>See the decision, not just the outcome.</h2>
        <p>The Decision Observatory turns the agent&apos;s append-only event stream into a
          time-traveling explanation of what it observed, proved, planned, selected, and learned.</p>
        <div className="about-hero-actions">
          <button onClick={() => onNavigate("timeline")}>Explore a decision <span>→</span></button>
          <button onClick={() => onNavigate("pfpln")}>Inspect PF-PLN <span>→</span></button>
        </div>
      </div>
      <aside className="about-trust">
        <span>trust contract</span>
        <strong>Observe what was emitted.</strong>
        <p>The browser never reruns the planner, fills missing facts, or upgrades a visual
          difference into a performance claim.</p>
        <div><span>schema</span><b>v1.0</b></div>
        <div><span>projection</span><b>strict as-of</b></div>
        <div><span>missing data</span><b>shown as a gap</b></div>
      </aside>
    </section>

    <section className="about-section about-pipeline-section">
      <header>
        <div><span className="eyebrow">one source of truth</span><h3>How evidence becomes a view</h3></div>
        <p>Every screen is a read-only projection over accepted JSONL events at the global cursor.</p>
      </header>
      <ol className="about-pipeline" aria-label="Evidence pipeline">
        <li>
          <span>01</span><strong>Emit</strong>
          <p>The agent and harness append typed decisions, proofs, technology, production,
            lifecycle, state, actions, and metrics.</p>
          <code>events.jsonl</code>
        </li>
        <li>
          <span>02</span><strong>Validate</strong>
          <p>Schema-compatible events pass through; malformed input is quarantined and stays visible.</p>
          <code>strict + lossless</code>
        </li>
        <li>
          <span>03</span><strong>Fold</strong>
          <p>The global turn and sequence cursor reconstructs only what was known at that moment.</p>
          <code>state @ T.seq</code>
        </li>
        <li>
          <span>04</span><strong>Inspect</strong>
          <p>Linked views expose causal ancestry while the inspector preserves the exact payload.</p>
          <code>trace → evidence</code>
        </li>
        <li>
          <span>05</span><strong>Compare</strong>
          <p>Exact seed-matched arms reveal descriptive differences without claiming causality.</p>
          <code>treatment ↔ baseline</code>
        </li>
      </ol>
    </section>

    <section className="about-section pf-about" aria-labelledby="pf-about-title">
      <header>
        <div><span className="eyebrow">applied control path / bounded authority</span>
          <h3 id="pf-about-title">How PF-PLN is applied</h3></div>
        <p>PF-PLN ranks where the existing agent should spend attention. It does not replace
          authoritative state, legal-action enumeration, planning, or execution checks.</p>
      </header>
      <div className="pf-about-intro">
        <div>
          <span className="eyebrow">the core idea</span>
          <h4>Turn unsatisfied goals into pressure on grounded operations.</h4>
          <p>Each goal keeps its own demand while pressure travels backward through declared
            causal and procedural routes. The scheduler compares only resolvable, admissible
            operations, then the ordinary plan and engine boundary retain final authority.</p>
        </div>
        <dl>
          <div><dt>inputs</dt><dd>immutable snapshot + server-advertised legal candidates</dd></div>
          <div><dt>changes</dt><dd>candidate priority and bounded attention allocation</dd></div>
          <div><dt>never changes</dt><dd>truth values, legality, or execution authorization</dd></div>
        </dl>
      </div>

      <ol className="pf-application-flow" aria-label="PF-PLN application stages">
        <li>
          <span>01 / ground</span><strong>Read authoritative state</strong>
          <p>The adapter derives its view from the immutable turn snapshot and the exact legal
            candidates advertised by the server.</p>
          <code>state_snapshot</code>
        </li>
        <li>
          <span>02 / demand</span><strong>Form active goals</strong>
          <p>Survival, expansion, score, and exploration receive utility, urgency, target
            strength, safety status, and grounded context.</p>
          <code>goals[]</code>
        </li>
        <li>
          <span>03 / transport</span><strong>Propagate pressure</strong>
          <p>Damped reverse traversal follows compatible causal or procedural routes.
            Conductance modulates learned routes; pressure remains keyed by goal.</p>
          <code>pressure_propagated</code>
        </li>
        <li>
          <span>04 / schedule</span><strong>Filter and rank operations</strong>
          <p>The scheduler combines expected goal relief, grounded value, information or option
            value, and scalarized cost. Harm to an active safety goal is a veto.</p>
          <code>operation_scored</code>
        </li>
        <li>
          <span>05 / commit</span><strong>Use the existing execution path</strong>
          <p>The selected operation becomes a snapshot-bound plan and still passes commitment,
            monitor, legal-action, refresh, and engine checks.</p>
          <code>plan_created → action_result</code>
        </li>
        <li>
          <span>06 / learn</span><strong>Credit verified relief</strong>
          <p>Post-action authoritative state classifies no effect, local effect, direct relief,
            or bounded downstream relief before route conductance changes.</p>
          <code>conductance_updated</code>
        </li>
      </ol>

      <div className="pf-example">
        <header>
          <div><span className="eyebrow">worked control example</span><h4>Expansion target not yet met</h4></div>
          <button onClick={() => onNavigate("pfpln")}>Open PF-PLN replay <span>→</span></button>
        </header>
        <div className="pf-example-path">
          <article><span>observe</span><strong>Owned city count is below the configured target.</strong>
            <p>The gap is grounded in the snapshot; it is not inferred from pressure.</p></article>
          <i aria-hidden="true">→</i>
          <article><span>focus</span><strong>Expansion demand reaches legal production, movement,
            and settlement categories.</strong>
            <p>Route conductance can favor categories that previously produced real relief.</p></article>
          <i aria-hidden="true">→</i>
          <article><span>choose</span><strong>The scheduler selects one admissible concrete
            operation.</strong>
            <p>Safety and materially worse grounded choices remain guarded.</p></article>
          <i aria-hidden="true">→</i>
          <article><span>verify</span><strong>A later snapshot must confirm city or population
            progress.</strong>
            <p>Movement or production changes alone do not count as goal relief.</p></article>
        </div>
      </div>

      <div className="pf-event-chain" role="region" aria-label="PF-PLN emitted event chain">
        <span>emitted evidence</span>
        <code>state_snapshot</code><i>→</i><code>pressure_propagated</code><i>→</i>
        <code>operation_scored</code><i>→</i><code>plan_created</code><i>→</i>
        <code>action_sent</code><i>→</i><code>action_result</code><i>→</i>
        <code>state_snapshot</code><i>→</i><code>conductance_updated</code>
      </div>

      <div className="pf-guardrails">
        <article><span>truth firewall</span><strong>Pressure is not belief.</strong>
          <p>Propagation cannot write atoms or modify confidence.</p></article>
        <article><span>safety firewall</span><strong>Safety is not a soft weight.</strong>
          <p>A harmful operation is inadmissible, regardless of aggregate benefit.</p></article>
        <article><span>causal firewall</span><strong>Association cannot authorize action.</strong>
          <p>Only compatible causal and procedural paths carry action pressure.</p></article>
        <article><span>learning firewall</span><strong>Effect is not automatically relief.</strong>
          <p>Credit is idempotent, provenance-linked, and grounded in admitted predicates.</p></article>
      </div>
    </section>

    <section className="about-section">
      <header>
        <div><span className="eyebrow">question-led navigation</span><h3>Start with what you need to know</h3></div>
        <p>Each view answers a different layer of the same recorded decision.</p>
      </header>
      <div className="about-question-grid">
        {questions.map((item) => <button key={item.question}
          onClick={() => onNavigate(item.view)}>
          <span>{item.question}</span>
          <strong>{item.answer}</strong>
          <small>{item.label} <b>→</b></small>
        </button>)}
      </div>
    </section>

    <div className="about-lower-grid">
      <section className="about-section about-workflow">
        <header>
          <div><span className="eyebrow">recommended workflow</span><h3>From run to root cause</h3></div>
        </header>
        <ol>
          <li><span>1</span><div><strong>Load a trace</strong>
            <p>Open a generated experiment or local JSONL stream.</p></div></li>
          <li><span>2</span><div><strong>Move through time</strong>
            <p>Use the global cursor; every view stays aligned to the same moment.</p></div></li>
          <li><span>3</span><div><strong>Follow the evidence</strong>
            <p>Select a decision, proof, atom, or plan and inspect its exact source event.</p></div></li>
          <li><span>4</span><div><strong>Compare carefully</strong>
            <p>Prefer exact pairs, then use the experiment statistics for score or win-rate claims.</p></div></li>
        </ol>
      </section>

      <section className="about-section about-why">
        <header>
          <div><span className="eyebrow">why it matters</span><h3>Accountability for autonomous play</h3></div>
        </header>
        <div>
          <article><span>01 / correctness</span><strong>Debug causes, not symptoms.</strong>
            <p>Distinguish a bad observation, proof, plan, selection, or action from the final result.</p></article>
          <article><span>02 / honesty</span><strong>Keep absence visible.</strong>
            <p>A logging gap remains a gap—never a fabricated zero, inferred path, or reconstructed proof.</p></article>
          <article><span>03 / improvement</span><strong>Connect behavior to evidence.</strong>
            <p>Use paired replays to locate divergence, then rely on repeated cohorts to quantify impact.</p></article>
        </div>
      </section>
    </div>

    <footer className="about-boundary">
      <span>interpretation boundary</span>
      <p>This app explains recorded behavior. Statistical reliability still comes from paired seeds,
        sufficient cohorts, confidence intervals, and fresh engine-backed confirmation.</p>
    </footer>
  </div>;
}

function LoggingGap({ title, detail }: { title: string; detail: string }) {
  return <div className="logging-gap"><span>logging gap</span><h2>{title}</h2><p>{detail}</p></div>;
}

function Inspector({ selection, onClose }: { selection?: Selection; onClose: () => void }) {
  if (!selection) return <aside className="inspector empty">
    <button className="inspector-close" aria-label="Close inspector" onClick={onClose}>×</button>
    <span className="eyebrow">inspector</span>
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
  return <aside className="inspector">
    <button className="inspector-close" aria-label="Close inspector" onClick={onClose}>×</button>
    <span className="eyebrow">inspector / {selection.kind}</span>
    <h2>{title}</h2><p className="mono-id">{subtitle}</p>{history}
    <pre>{JSON.stringify(value, null, 2)}</pre></aside>;
}

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

function ArtifactBrowser({ open, onClose, onLoad, onCompare, onLoadPair }: {
  open: boolean;
  onClose: () => void;
  onLoad: (entry: ArtifactCatalogEntry) => Promise<void>;
  onCompare: (entry: ArtifactCatalogEntry) => Promise<void>;
  onLoadPair: (primary: ArtifactCatalogEntry, comparison: ArtifactCatalogEntry) => Promise<void>;
}) {
  const [entries, setEntries] = useState<ArtifactCatalogEntry[]>([]);
  const [query, setQuery] = useState("");
  const [catalogStatus, setCatalogStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [loadingPath, setLoadingPath] = useState<string>();
  const [comparingPath, setComparingPath] = useState<string>();
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
      if (event.key === "Escape" && !loadingPath && !comparingPath) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [comparingPath, loadingPath, onClose, open]);

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

  const compare = async (entry: ArtifactCatalogEntry): Promise<void> => {
    setComparingPath(entry.path);
    setError(undefined);
    try {
      await onCompare(entry);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Comparison trace could not be loaded");
    } finally {
      setComparingPath(undefined);
    }
  };

  const selectPair = async (
    entry: ArtifactCatalogEntry,
    pair: ArtifactCatalogEntry,
  ): Promise<void> => {
    setLoadingPath(entry.path);
    setComparingPath(pair.path);
    setError(undefined);
    try {
      const [primary, comparison] = pair.arm === "treatment" && entry.arm !== "treatment"
        ? [pair, entry] : [entry, pair];
      await onLoadPair(primary, comparison);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Paired traces could not be loaded");
    } finally {
      setLoadingPath(undefined);
      setComparingPath(undefined);
    }
  };

  return <div className="artifact-backdrop" onMouseDown={(event) => {
    if (event.target === event.currentTarget && !loadingPath && !comparingPath) onClose();
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
          disabled={Boolean(loadingPath || comparingPath)}>×</button>
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
        {visible.map((entry) => {
          const pair = findPairedArtifact(entry, entries);
          return <div className="artifact-entry" key={entry.path}>
          <button aria-label={`Load ${entry.label}`}
            disabled={Boolean(loadingPath || comparingPath)}
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
          </button>
          <div className="artifact-entry-actions">
            {pair && <button className="artifact-pair"
              aria-label={`Open exact pair for ${entry.label}`}
              title={`Open with ${pair.arm ?? "opposite arm"} / ${pair.run}`}
              disabled={Boolean(loadingPath || comparingPath)}
              onClick={() => void selectPair(entry, pair)}>
              {loadingPath === entry.path && comparingPath === pair.path ? "loading…" : "open pair"}
            </button>}
            <button className={comparingPath === entry.path ? "artifact-compare loading" : "artifact-compare"}
              aria-label={`Compare ${entry.label}`}
              disabled={Boolean(loadingPath || comparingPath)}
              onClick={() => void compare(entry)}>
              {comparingPath === entry.path ? "loading…" : "compare"}
            </button>
          </div>
        </div>;
        })}
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
  const [pfDecision, setPfDecision] = useState(decoded.decision);
  const [focusMode, setFocusMode] = useState(decoded.focus ?? false);
  const [inspectorOpen, setInspectorOpen] = useState(decoded.inspector ?? true);
  const [mode, setMode] = useState<"replay" | "live">("replay");
  const [artifactBrowserOpen, setArtifactBrowserOpen] = useState(false);
  const [traceSource, setTraceSource] = useState("bundled demonstration");
  const [activeArtifact, setActiveArtifact] = useState<ArtifactCatalogEntry>();
  const [comparisonEvents, setComparisonEvents] = useState<TraceEvent[]>([]);
  const [comparisonSource, setComparisonSource] = useState<string>();
  const [comparisonArtifact, setComparisonArtifact] = useState<ArtifactCatalogEntry>();
  const [liveStatus, setLiveStatus] = useState<LiveStatus>("idle");
  const [liveUrl, setLiveUrl] = useState(
    String(import.meta.env.VITE_FREECIV_LIVE_URL ?? "ws://127.0.0.1:8765"));
  const [liveGameId, setLiveGameId] = useState(initial.events[0]?.game_id ?? "freeciv-live");
  const liveClient = useRef<LiveEventClient | undefined>(undefined);
  const state = useMemo(() => foldEvents(events, cursor), [events, cursor]);
  const comparisonState = useMemo(() => comparisonEvents.length
    ? foldEvents(comparisonEvents, { turn: cursor.turn, seq: Number.MAX_SAFE_INTEGER })
    : undefined, [comparisonEvents, cursor.turn]);
  const pairQuality = useMemo(() =>
    artifactPairQuality(activeArtifact, comparisonArtifact),
  [activeArtifact, comparisonArtifact]);

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
    window.history.replaceState(null, "", encodeUrlState({
      view, cursor, selected, decision: pfDecision, search, channel,
      focus: focusMode, inspector: inspectorOpen,
    }));
  }, [view, cursor, selection, pfDecision, search, channel, focusMode, inspectorOpen]);
  useEffect(() => () => liveClient.current?.stop(), []);

  const applyReplay = (
    parsed: ParseResult,
    source: string,
    artifact?: ArtifactCatalogEntry,
  ): void => {
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
    setActiveArtifact(artifact);
    setComparisonEvents([]);
    setComparisonSource(undefined);
    setComparisonArtifact(undefined);
    setPfDecision(undefined);
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
    applyReplay(parsed, entry.label, entry);
  };

  const loadComparisonArtifact = async (entry: ArtifactCatalogEntry): Promise<void> => {
    const parsed = await parseJsonlStream(await fetchArtifactEventStream(entry));
    if (parsed.events.length === 0) {
      throw new Error("The selected comparison artifact contains no valid trace events");
    }
    if (parsed.events.length > eventLimit) {
      throw new Error(`The comparison artifact exceeds the ${eventLimit.toLocaleString()} event limit`);
    }
    setComparisonEvents(parsed.events.sort(eventOrder));
    setComparisonSource(entry.label);
    setComparisonArtifact(entry);
  };

  const loadArtifactPair = async (
    primary: ArtifactCatalogEntry,
    comparison: ArtifactCatalogEntry,
  ): Promise<void> => {
    const [primaryStream, comparisonStream] = await Promise.all([
      fetchArtifactEventStream(primary),
      fetchArtifactEventStream(comparison),
    ]);
    const [primaryParsed, comparisonParsed] = await Promise.all([
      parseJsonlStream(primaryStream),
      parseJsonlStream(comparisonStream),
    ]);
    if (!primaryParsed.events.length || !comparisonParsed.events.length) {
      throw new Error("One or both paired artifacts contain no valid trace events");
    }
    if (comparisonParsed.events.length > eventLimit) {
      throw new Error(`The comparison artifact exceeds the ${eventLimit.toLocaleString()} event limit`);
    }
    applyReplay(primaryParsed, primary.label, primary);
    setComparisonEvents(comparisonParsed.events.sort(eventOrder));
    setComparisonSource(comparison.label);
    setComparisonArtifact(comparison);
  };

  const stopLive = (): void => {
    liveClient.current?.stop();
    liveClient.current = undefined;
    setMode("replay"); setLiveStatus("idle");
  };

  const startLive = (): void => {
    liveClient.current?.stop();
    setEvents([]); setInvalidLines([]); setCursor({ turn: 0, seq: 0 });
    setActiveArtifact(undefined); setComparisonEvents([]);
    setComparisonSource(undefined); setComparisonArtifact(undefined);
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

  const main = view === "timeline" ? <Timeline state={state} selection={selection}
    onSelect={setSelection} onCursor={setCursor} />
    : view === "proofs" ? <ProofExplorer state={state} selection={selection} onSelect={setSelection} />
      : view === "atoms" ? <Atomspace state={state} onSelect={setSelection} search={search}
        channel={channel} onSearch={setSearch} onChannel={setChannel} />
        : view === "plans" ? <PlanBoard state={state} onSelect={setSelection} />
          : view === "map" ? <MapOverlay state={state} selection={selection} onSelect={setSelection} />
            : view === "audit" ? <EpistemicAudit state={state} onSelect={setSelection} />
              : view === "metrics" ? <MetricsDashboard state={state} onSelect={setSelection} />
                : view === "pfpln" ? <PfPlnDashboard state={state} onSelect={setSelection}
                  decisionId={pfDecision} onDecision={setPfDecision}
                  comparisonState={comparisonState} comparisonSource={comparisonSource}
                  pairQuality={pairQuality} />
                  : view === "technology" ? <TechnologyDashboard state={state}
                    onSelect={setSelection} />
                    : view === "economy" ? <EconomyProductionDashboard state={state}
                      onSelect={setSelection} />
                      : view === "forces" ? <UnitLifecycleDashboard state={state}
                        onSelect={setSelection} />
                        : view === "about" ? <HowItWorks onNavigate={setView} />
                          : <LoggingGap title={`${NAV.find((item) => item.view === view)?.label} awaits its event milestone`}
                            detail="This surface never derives missing data from another event type." />;

  return <div className="app-shell">
    <Header events={events} state={state} mode={mode} status={liveStatus} gameId={liveGameId}
      focus={focusMode} inspectorOpen={inspectorOpen}
      onFocus={() => setFocusMode((value) => !value)}
      onInspector={() => setInspectorOpen((value) => !value)} />
    <Scrubber events={events} cursor={cursor} onChange={setCursor} />
    {(invalidLines.length > 0 || state.unknown.length > 0 || state.loggingGaps.length > 0) &&
      <div className="anomaly-bar" role="alert"><strong>Trace anomalies visible</strong>
        <span>{invalidLines.length} invalid lines</span><span>{state.unknown.length} unknown events</span>
        <span>{state.loggingGaps.length} logging gaps</span></div>}
    {comparisonSource && <div className="comparison-banner" role="status">
      <span>paired comparison</span><strong>{comparisonSource}</strong>
      <span className={`pair-quality ${pairQuality.exact ? "exact" : "warning"}`}
        title={pairQuality.mismatches.join(", ") || "all pair keys match"}>{pairQuality.label}</span>
      <small>{pairQuality.exact
        ? "Same experiment, cohort, condition, and seed; opposing arms."
        : `Check ${pairQuality.mismatches.join(", ")}. Differences remain descriptive.`}</small>
      <button onClick={() => {
        setComparisonEvents([]); setComparisonSource(undefined); setComparisonArtifact(undefined);
      }}>clear</button>
    </div>}
    <div className={`workspace ${focusMode ? "focus-mode" : ""} ${!inspectorOpen ? "inspector-closed" : ""}`}>
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
      {inspectorOpen && <Inspector selection={selection} onClose={() => setInspectorOpen(false)} />}
    </div>
    <ArtifactBrowser open={artifactBrowserOpen} onClose={() => setArtifactBrowserOpen(false)}
      onLoad={loadArtifact} onCompare={loadComparisonArtifact} onLoadPair={loadArtifactPair} />
  </div>;
}
