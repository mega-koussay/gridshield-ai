import { useState } from "react";
import type { IncidentInfo, Payload } from "../types";
import { ATTACK_DESCRIPTIONS, ATTACK_TYPES } from "../types";

const card: React.CSSProperties = {
  background: "#0f172a",
  border: "1px solid #1e293b",
  borderRadius: 10,
  padding: 12,
};

export function KpiBar({ payload }: { payload: Payload }) {
  const k = payload.kpis;
  const s = payload.state;
  const statusColor =
    k.attack_status === "UNDER_ATTACK" ? "#ef4444"
      : k.attack_status === "CONTAINED" ? "#f59e0b"
        : k.attack_status === "RECOVERED" ? "#38bdf8" : "#22c55e";
  const items: { label: string; value: string; color?: string }[] = [
    { label: "ATTACK STATUS", value: k.attack_status.replace("_", " "), color: statusColor },
    { label: "ANOMALY SCORE", value: k.anomaly_score.toFixed(2), color: k.anomaly_score >= 0.7 ? "#ef4444" : undefined },
    { label: "ENERGY BALANCE", value: `${k.energy_balance_kw > 0 ? "+" : ""}${k.energy_balance_kw} kW` },
    { label: "BATTERY SOC", value: `${(k.soc * 100).toFixed(0)}%`, color: k.soc < 0.2 ? "#ef4444" : undefined },
    { label: "SELF-SUFFICIENCY", value: `${(k.self_sufficiency * 100).toFixed(0)}%` },
    { label: "UNMET LOAD", value: `${k.unmet_load_kw.toFixed(1)} kW`, color: k.blackout ? "#ef4444" : undefined },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10 }}>
      {items.map((it) => (
        <div key={it.label} style={card}>
          <div style={{ fontSize: 10, color: "#64748b", letterSpacing: 0.6 }}>{it.label}</div>
          <div style={{ fontSize: 19, fontWeight: 700, color: it.color ?? "#e2e8f0" }}>{it.value}</div>
        </div>
      ))}
    </div>
  );
}

export function PhaseTracker({ payload }: { payload: Payload }) {
  const idx = payload.demo.phases.indexOf(payload.demo.phase);
  return (
    <div style={card}>
      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8, letterSpacing: 0.6 }}>
        DEMO SCENARIO {payload.demo.active ? `(seed ${payload.demo.seed})` : "— press RUN DEMO"}
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {payload.demo.phases.map((p, i) => (
          <div key={p} style={{
            fontSize: 10, padding: "4px 8px", borderRadius: 12,
            background: i <= idx ? "#134e4a" : "#1e293b",
            color: i <= idx ? "#5eead4" : "#64748b",
            border: i === idx ? "1px solid #14b8a6" : "1px solid transparent",
            fontWeight: i === idx ? 700 : 400,
          }}>
            {i + 1}. {p}
          </div>
        ))}
      </div>
      {payload.demo.log.length > 0 && (
        <div style={{ marginTop: 8, fontSize: 11, color: "#94a3b8", lineHeight: 1.5 }}>
          {payload.demo.log.slice(-3).map((l, i) => (
            <div key={i}>▸ <b style={{ color: "#5eead4" }}>{l.phase}</b> — {l.message}</div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ExplanationPanel({ payload }: { payload: Payload }) {
  const ex = payload.explanation;
  const d = payload.detection;
  if (!ex) {
    return (
      <div style={card}>
        <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 6, letterSpacing: 0.6 }}>AI EXPLANATION</div>
        <div style={{ fontSize: 12, color: "#64748b" }}>
          {d.is_anomaly ? "Analyzing…" : "No active alert. Detectors watching solar, load, per-meter and control channels."}
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: "#475569" }}>
          Channels: load {d.signals.z_load?.toFixed(2)} · solar {d.signals.z_solar?.toFixed(2)} ·
          meter {d.signals.z_meter?.toFixed(2)} · control {d.signals.z_battery?.toFixed(2)}
        </div>
      </div>
    );
  }
  return (
    <div style={{ ...card, borderColor: "#7f1d1d" }}>
      <div style={{ fontSize: 11, color: "#f87171", letterSpacing: 0.6 }}>AI EXPLANATION — ACTIVE ALERT</div>
      <div style={{ fontSize: 15, fontWeight: 700, margin: "4px 0", color: "#fecaca" }}>{ex.title}</div>
      <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 8 }}>{ex.story}</div>
      <ul style={{ margin: "6px 0", paddingLeft: 18, fontSize: 12, color: "#e2e8f0", lineHeight: 1.55 }}>
        {ex.reasons.map((r, i) => <li key={i}>{r}</li>)}
      </ul>
      <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>{ex.threshold_note}</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {ex.attributions.map(([n, v]) => (
          <span key={n} style={{
            fontSize: 10, background: "#1e293b", borderRadius: 10, padding: "2px 8px",
            color: "#94a3b8",
          }}>{n}: {v}</span>
        ))}
      </div>
      {ex.reconstruction && (
        <div style={{ marginTop: 8, fontSize: 12, color: "#5eead4" }}>
          Reconstructed trusted values — solar {ex.reconstruction.trusted_solar_kw} kW,
          load {ex.reconstruction.trusted_load_kw} kW ({ex.reconstruction.replaced.length} device(s) bypassed)
        </div>
      )}
    </div>
  );
}

export function DeviceList({ payload }: { payload: Payload }) {
  return (
    <div style={card}>
      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8, letterSpacing: 0.6 }}>DEVICE HEALTH</div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <tbody>
          {payload.devices.map((d) => (
            <tr key={d.device_id}>
              <td style={{ padding: "3px 0", color: "#e2e8f0" }}>{d.label}</td>
              <td style={{ color: "#64748b", fontSize: 10 }}>{d.kind}</td>
              <td style={{ textAlign: "right" }}>
                <span style={{
                  fontSize: 10, borderRadius: 10, padding: "2px 8px",
                  background: d.isolated ? "#7f1d1d" : d.compromised ? "#78350f" : "#14532d",
                  color: d.isolated ? "#fecaca" : d.compromised ? "#fde68a" : "#bbf7d0",
                }}>
                  {d.isolated ? "ISOLATED" : d.compromised ? "COMPROMISED" : "TRUSTED"} {d.health.toFixed(0)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function IncidentTimeline({ incidents }: { incidents: IncidentInfo[] }) {
  return (
    <div style={card}>
      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8, letterSpacing: 0.6 }}>INCIDENT TIMELINE</div>
      {incidents.length === 0 && <div style={{ fontSize: 12, color: "#64748b" }}>No incidents — grid secure.</div>}
      {incidents.slice(-3).reverse().map((inc) => (
        <div key={inc.incident_id} style={{ marginBottom: 10, borderLeft: `3px solid ${inc.status === "recovered" ? "#22c55e" : "#ef4444"}`, paddingLeft: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#e2e8f0" }}>
            {inc.incident_id} · {inc.attack_type} · {inc.device_id}
          </div>
          <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>
            confidence {(inc.confidence * 100).toFixed(0)}% · status {inc.status}
          </div>
          {inc.actions.map((a, i) => (
            <div key={i} style={{ fontSize: 11, color: "#94a3b8" }}>
              <b style={{ color: "#5eead4" }}>{a.action}</b> — {a.detail}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function Controls({ payload, busy, launchDemo, reset, attack }: {
  payload: Payload; busy: boolean;
  launchDemo: (t: string, seed?: number) => void;
  reset: () => void;
  attack: (t: string) => void;
}) {
  const [selected, setSelected] = useState<string>("FDI_BULK");
  const [seed, setSeed] = useState<number>(2026);
  return (
    <div style={card}>
      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8, letterSpacing: 0.6 }}>CONTROLS</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <select value={selected} onChange={(e) => setSelected(e.target.value)} style={{
          background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155",
          borderRadius: 6, padding: "6px 8px", fontSize: 12,
        }}>
          {ATTACK_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} style={{
          width: 90, background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155",
          borderRadius: 6, padding: "6px 8px", fontSize: 12,
        }} title="Scenario seed (reproducibility)" />
        <button onClick={() => launchDemo(selected, seed)} disabled={busy} style={{
          background: "#0ea5e9", color: "#04283a", fontWeight: 700, border: "none",
          borderRadius: 6, padding: "7px 14px", fontSize: 12, cursor: "pointer",
        }}>▶ RUN DEMO</button>
        <button onClick={reset} disabled={busy} style={{
          background: "#334155", color: "#e2e8f0", border: "none",
          borderRadius: 6, padding: "7px 14px", fontSize: 12, cursor: "pointer",
        }}>⟲ RESET</button>
        <button onClick={() => attack(selected)} disabled={busy} style={{
          background: "#b91c1c", color: "#fee2e2", border: "none",
          borderRadius: 6, padding: "7px 14px", fontSize: 12, cursor: "pointer",
        }}>☠ LAUNCH ATTACK ONLY</button>
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: "#64748b" }}>
        {ATTACK_DESCRIPTIONS[selected as keyof typeof ATTACK_DESCRIPTIONS]}
      </div>
      <div style={{ marginTop: 6, fontSize: 11, color: "#475569" }}>
        Attacks are injected ONLY into this local simulation's telemetry.
      </div>
    </div>
  );
}
