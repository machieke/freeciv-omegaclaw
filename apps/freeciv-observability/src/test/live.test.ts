import { afterEach, describe, expect, it, vi } from "vitest";

import demoTrace from "../../../../Autotests/fixtures/freeciv-events/v1/normal-crisp.jsonl?raw";
import type { TraceEvent } from "../events";
import { LiveEventClient, type LiveAnomaly, type SocketFactory } from "../live";

class FakeSocket {
  readyState = 0;
  sent: string[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  send(data: string): void { this.sent.push(data); }
  close(code = 1000, reason = ""): void {
    this.readyState = 3;
    this.onclose?.({ code, reason } as CloseEvent);
  }
  open(): void { this.readyState = 1; this.onopen?.(new Event("open")); }
  message(value: unknown): void {
    const data = typeof value === "string" ? value : JSON.stringify(value);
    this.onmessage?.({ data } as MessageEvent<string>);
  }
}

const events = demoTrace.trim().split("\n").map((line) => JSON.parse(line) as TraceEvent);
const subscribed = {
  protocol_version: "1", type: "subscribed", game_id: events[0].game_id,
  schema_version: "1.0", after: { turn: -1, seq: -1 }, persisted_first: true,
};

afterEach(() => vi.useRealTimers());

describe("persisted live event client", () => {
  it("resumes after forced disconnect without double-applying persisted events", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const received: TraceEvent[] = [];
    const anomalies: LiveAnomaly[] = [];
    const factory: SocketFactory = () => {
      const socket = new FakeSocket(); sockets.push(socket); return socket;
    };
    const client = new LiveEventClient({
      url: "ws://tail", gameId: events[0].game_id, reconnectBaseMs: 1,
      socketFactory: factory, onEvent: (event) => received.push(event),
      onAnomaly: (anomaly) => anomalies.push(anomaly),
    });

    client.start();
    sockets[0].open();
    expect(JSON.parse(sockets[0].sent[0]).after).toEqual({ turn: -1, seq: -1 });
    sockets[0].message(subscribed);
    sockets[0].message(events[0]);
    sockets[0].message(events[1]);
    sockets[0].close(1006, "forced");
    vi.advanceTimersByTime(1);

    expect(sockets).toHaveLength(2);
    sockets[1].open();
    expect(JSON.parse(sockets[1].sent[0]).after).toEqual({
      turn: events[1].turn, seq: events[1].seq,
    });
    sockets[1].message(subscribed);
    sockets[1].message(events[1]);
    sockets[1].message(events[2]);
    expect(received.map((event) => event.event_id)).toEqual(
      [events[0].event_id, events[1].event_id, events[2].event_id]);
    expect(anomalies.map((item) => item.code)).toContain("E_LIVE_DISCONNECT");
    expect(anomalies.map((item) => item.code)).toContain("E_LIVE_DUPLICATE");
    client.stop();
  });

  it("rejects incompatible, out-of-order, gap, and truncated messages visibly", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const anomalies: LiveAnomaly[] = [];
    const received: TraceEvent[] = [];
    const client = new LiveEventClient({
      url: "ws://tail", gameId: events[0].game_id, reconnectBaseMs: 1,
      socketFactory: () => { const socket = new FakeSocket(); sockets.push(socket); return socket; },
      onEvent: (event) => received.push(event), onAnomaly: (item) => anomalies.push(item),
    });
    client.start(); sockets[0].open(); sockets[0].message(subscribed);
    sockets[0].message("{truncated");
    sockets[0].message({ ...events[0], schema_version: "2.0" });
    sockets[0].message(events[2]);
    sockets[0].message(events[1]);
    sockets[0].message({ ...events[3], seq: events[3].seq + 1 });

    expect(received).toHaveLength(1);
    expect(anomalies.map((item) => item.code)).toEqual(expect.arrayContaining([
      "E_LIVE_JSON", "E_LIVE_SCHEMA", "E_LIVE_OUT_OF_ORDER", "E_LIVE_GAP",
    ]));
    client.stop();
  });
});
