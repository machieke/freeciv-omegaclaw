import type { CSSProperties } from "react";

export const CHART_COLORS = [
  "#5dd8d0", "#e8ae57", "#80d49a", "#ef8f6a", "#8eb8ff", "#c79ae8",
];

export const humanize = (value: unknown): string =>
  String(value ?? "unknown")
    .replace(/^pf-impact:/, "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

export function Sparkline({ values, minimum, maximum, color = "var(--cyan)", label }: {
  values: number[];
  minimum?: number;
  maximum?: number;
  color?: string;
  label: string;
}) {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return <span className="sparkline-empty">no series</span>;
  const low = minimum ?? Math.min(...finite);
  const high = maximum ?? Math.max(...finite);
  const span = Math.max(1e-9, high - low);
  const width = 180;
  const height = 42;
  const points = finite.map((value, index) => {
    const x = finite.length === 1 ? width / 2 : index * width / (finite.length - 1);
    const y = height - 4 - ((value - low) / span) * (height - 8);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  const last = points.split(" ").at(-1)?.split(",") ?? ["0", "0"];
  return <svg className="sparkline" viewBox={`0 0 ${width} ${height}`}
    preserveAspectRatio="none" role="img" aria-label={label}>
    <line x1="0" x2={width} y1={height - 4} y2={height - 4} className="spark-baseline" />
    <polyline points={points} fill="none" stroke={color} strokeWidth="2"
      vectorEffect="non-scaling-stroke" />
    <circle cx={last[0]} cy={last[1]} r="2.7" fill={color} />
  </svg>;
}

export function ValueBar({ value, maximum, color = "var(--cyan)", label, muted = false }: {
  value: number;
  maximum: number;
  color?: string;
  label: string;
  muted?: boolean;
}) {
  const width = Math.max(0, Math.min(100, maximum > 0 ? Math.abs(value) / maximum * 100 : 0));
  return <span className={`value-bar ${muted ? "muted" : ""}`}
    role="img" aria-label={`${label}: ${value}`}>
    <span style={{ "--bar-width": `${width}%`, "--bar-color": color } as CSSProperties} />
  </span>;
}

export function TurnHeatmap({ rows, turns, onTurn, label }: {
  rows: Array<{ label: string; counts: Map<number, number>; color?: string }>;
  turns: number[];
  onTurn: (turn: number) => void;
  label: string;
}) {
  const maximum = Math.max(1, ...rows.flatMap((row) => [...row.counts.values()]));
  return <div className="turn-heatmap" role="grid" aria-label={label}
    style={{ "--turn-count": Math.max(1, turns.length) } as CSSProperties}>
    <div className="heatmap-corner">track / turn</div>
    <div className="heatmap-turns">
      {turns.map((turn, index) => <span key={turn}>
        {index === 0 || index === turns.length - 1 || index % Math.max(1, Math.floor(turns.length / 8)) === 0
          ? turn : ""}
      </span>)}
    </div>
    {rows.map((row) => <div className="heatmap-track" key={row.label}>
      <strong>{row.label}</strong>
      <div>{turns.map((turn) => {
        const count = row.counts.get(turn) ?? 0;
        return <button key={turn} aria-label={`${row.label}, turn ${turn}, ${count} events`}
          title={`${row.label} · T${turn} · ${count}`}
          style={{
            "--cell-opacity": count ? 0.18 + 0.82 * count / maximum : 0.04,
            "--cell-color": row.color ?? "var(--cyan)",
          } as CSSProperties}
          onClick={() => onTurn(turn)} />;
      })}</div>
    </div>)}
  </div>;
}
