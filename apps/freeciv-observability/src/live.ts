import { compareCursor, cursorOf, type Cursor, type TraceEvent } from "./events";
import { validateTraceEvent } from "./validation";

export type LiveStatus = "idle" | "connecting" | "backfilling" | "live" | "reconnecting" | "stopped";

export interface LiveAnomaly {
  code: string;
  message: string;
  raw?: string;
}

interface SocketLike {
  readyState: number;
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
}

export type SocketFactory = (url: string) => SocketLike;

export interface LiveClientOptions {
  url: string;
  gameId: string;
  schemaVersion?: string;
  after?: Cursor;
  maxReconnects?: number;
  reconnectBaseMs?: number;
  socketFactory?: SocketFactory;
  onEvent: (event: TraceEvent) => void;
  onAnomaly: (anomaly: LiveAnomaly) => void;
  onStatus?: (status: LiveStatus) => void;
}

const CLOSED = 3;

export class LiveEventClient {
  private readonly options: Required<Pick<LiveClientOptions,
    "schemaVersion" | "maxReconnects" | "reconnectBaseMs">> & LiveClientOptions;
  private socket?: SocketLike;
  private stopped = false;
  private reconnects = 0;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private cursor: Cursor;
  private readonly eventIds = new Set<string>();

  constructor(options: LiveClientOptions) {
    this.options = {
      schemaVersion: "1.0", maxReconnects: 8, reconnectBaseMs: 100,
      ...options,
    };
    this.cursor = options.after ?? { turn: -1, seq: -1 };
  }

  get resumeCursor(): Cursor { return { ...this.cursor }; }

  start(): void {
    if (!this.stopped && this.socket && this.socket.readyState !== CLOSED) return;
    this.stopped = false;
    this.connect(this.reconnects > 0 ? "reconnecting" : "connecting");
  }

  stop(): void {
    this.stopped = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = undefined;
    this.socket?.close(1000, "client stop");
    this.options.onStatus?.("stopped");
  }

  private connect(status: LiveStatus): void {
    this.options.onStatus?.(status);
    const factory = this.options.socketFactory ?? ((url: string) => new WebSocket(url));
    let socket: SocketLike;
    try {
      socket = factory(this.options.url);
    } catch (error) {
      this.options.onAnomaly({
        code: "E_LIVE_CONNECT", message: error instanceof Error ? error.message : "connection failed",
      });
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;
    socket.onopen = () => {
      socket.send(JSON.stringify({
        type: "subscribe", game_id: this.options.gameId,
        schema_version: this.options.schemaVersion, after: this.cursor,
      }));
      this.options.onStatus?.("backfilling");
    };
    socket.onmessage = (message) => this.receive(String(message.data));
    socket.onerror = () => this.options.onAnomaly({
      code: "E_LIVE_SOCKET", message: "live event socket reported an error",
    });
    socket.onclose = (event) => {
      if (this.stopped || event.code === 1000) return;
      this.options.onAnomaly({
        code: "E_LIVE_DISCONNECT",
        message: `socket closed (${event.code || "no code"}); replaying from T${this.cursor.turn}.${this.cursor.seq}`,
      });
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    if (this.reconnects >= this.options.maxReconnects) {
      this.options.onAnomaly({
        code: "E_LIVE_RECONNECT_LIMIT", message: "bounded reconnect limit reached",
      });
      this.options.onStatus?.("stopped");
      return;
    }
    const delay = Math.min(5_000, this.options.reconnectBaseMs * (2 ** this.reconnects));
    this.reconnects += 1;
    this.options.onStatus?.("reconnecting");
    this.reconnectTimer = setTimeout(() => this.connect("reconnecting"), delay);
  }

  private receive(raw: string): void {
    let value: unknown;
    try {
      value = JSON.parse(raw);
    } catch (error) {
      this.options.onAnomaly({ code: "E_LIVE_JSON", message: "invalid live JSON", raw });
      return;
    }
    if (value && typeof value === "object" && "protocol_version" in value) {
      const control = value as Record<string, unknown>;
      if (control.type === "subscribed") {
        this.options.onStatus?.("live");
      } else if (control.type === "tail_error") {
        this.options.onAnomaly({
          code: String(control.code ?? "E_LIVE_TAIL"),
          message: String(control.message ?? "tail rejected the subscription"), raw,
        });
      } else {
        this.options.onAnomaly({ code: "E_LIVE_CONTROL", message: "unknown tail control message", raw });
      }
      return;
    }
    const validation = validateTraceEvent(value);
    if (!validation.valid) {
      this.options.onAnomaly({ code: "E_LIVE_SCHEMA", message: validation.reason ?? "invalid event", raw });
      return;
    }
    const event = value as TraceEvent;
    if (event.game_id !== this.options.gameId) {
      this.options.onAnomaly({ code: "E_LIVE_GAME", message: "event game_id changed", raw });
      return;
    }
    if (event.schema_version !== this.options.schemaVersion) {
      this.options.onAnomaly({ code: "E_LIVE_SCHEMA_VERSION", message: "event schema is incompatible", raw });
      return;
    }
    const next = cursorOf(event);
    const order = compareCursor(next, this.cursor);
    if (this.eventIds.has(event.event_id) || order === 0) {
      this.options.onAnomaly({ code: "E_LIVE_DUPLICATE", message: "duplicate event suppressed", raw });
      return;
    }
    if (order < 0) {
      this.options.onAnomaly({ code: "E_LIVE_OUT_OF_ORDER", message: "out-of-order event suppressed", raw });
      return;
    }
    const hasPrior = this.cursor.turn >= 0;
    const gap = hasPrior && (
      (next.turn === this.cursor.turn && next.seq !== this.cursor.seq + 1)
      || (next.turn > this.cursor.turn && next.seq !== 0)
    );
    if (gap) {
      this.options.onAnomaly({
        code: "E_LIVE_GAP",
        message: `cursor gap after T${this.cursor.turn}.${this.cursor.seq}; reconnect required`, raw,
      });
      this.socket?.close(4001, "cursor gap");
      return;
    }
    this.cursor = next;
    this.reconnects = 0;
    this.eventIds.add(event.event_id);
    this.options.onEvent(event);
  }
}
