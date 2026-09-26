import type { Payload } from "./types";

async function post(url: string, body?: unknown): Promise<Payload> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

export const api = {
  launchDemo: (opts: { seed?: number; attack_type?: string; delay_min?: number } = {}) =>
    post("/api/demo/launch", opts),

  reset: () => post("/api/demo/reset"),

  step: () => post("/api/sim/step"),

  attack: (attack_type: string, duration_min = 30, delay_min = 0) =>
    post("/api/attack/launch", { attack_type, duration_min, delay_min }),

  setpoint: (battery_kw: number) =>
    post("/api/sim/scada-setpoint", { battery_kw }),
};

/** Subscribe to the live WebSocket stream; returns an unsubscribe fn. */
export function connectLive(
  onPayload: (p: Payload) => void,
  onStatus: (ok: boolean) => void,
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let retry = 0;

  const open = () => {
    if (closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/live`);
    ws.onopen = () => {
      retry = 0;
      onStatus(true);
    };
    ws.onmessage = (ev) => {
      try {
        onPayload(JSON.parse(ev.data));
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      onStatus(false);
      if (!closed && retry < 10) {
        retry += 1;
        setTimeout(open, Math.min(4000, 500 * retry));
      }
    };
    ws.onerror = () => ws?.close();
  };
  open();
  return () => {
    closed = true;
    ws?.close();
  };
}
