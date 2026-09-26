import { useCallback, useEffect, useRef, useState } from "react";
import { api, connectLive } from "../api";
import type { Payload } from "../types";

export interface HistoryPoint {
  t: string;
  solar: number;
  load: number;
  battery: number;
  import_kw: number;
  score: number;
}

const MAX_HISTORY = 90;

export function useGridShield() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [connected, setConnected] = useState(false);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [busy, setBusy] = useState(false);
  const payloadRef = useRef<Payload | null>(null);

  payloadRef.current = payload;

  useEffect(() => {
    const unsub = connectLive(setPayload, setConnected);
    return unsub;
  }, []);

  // Safety net: if the WebSocket stream dies (proxy hiccup, server restart),
  // poll the REST API so the dashboard keeps working regardless.
  useEffect(() => {
    if (connected) return;
    const t = setInterval(async () => {
      try {
        const res = await fetch("/api/state/current");
        if (res.ok) {
          const p = (await res.json()) as Payload;
          setPayload(p);
          setConnected(true);
        }
      } catch {
        /* backend not up yet */
      }
    }, 1500);
    return () => clearInterval(t);
  }, [connected]);

  useEffect(() => {
    if (!payload) return;
    const s = payload.state;
    const label = `${String(Math.floor(s.minute_of_day / 60)).padStart(2, "0")}:${String(
      Math.floor(s.minute_of_day % 60),
    ).padStart(2, "0")}`;
    setHistory((h) => {
      const next = [
        ...h,
        {
          t: label,
          solar: s.solar_kw,
          load: s.load_kw,
          battery: s.battery_kw,
          import_kw: s.grid_import_kw,
          score: payload.detection.score,
        },
      ];
      return next.slice(-MAX_HISTORY);
    });
  }, [payload?.state.step_index]);

  const withBusy = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    setBusy(true);
    try {
      return await fn();
    } finally {
      setBusy(false);
    }
  }, []);

  const launchDemo = useCallback(
    (attackType: string, seed?: number) =>
      withBusy(async () => {
        const p = await api.launchDemo({ attack_type: attackType, seed });
        setPayload(p); // apply immediately — don't wait for the next stream frame
        return p;
      }),
    [withBusy],
  );
  const reset = useCallback(
    () =>
      withBusy(async () => {
        const p = await api.reset();
        setPayload(p);
        return p;
      }),
    [withBusy],
  );
  const attack = useCallback(
    (t: string) => withBusy(() => api.attack(t)),
    [withBusy],
  );

  return {
    payload,
    connected,
    history,
    busy,
    launchDemo,
    reset,
    attack,
  };
}
