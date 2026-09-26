import { useGridShield } from "./hooks/useGridShield";
import TwinDiagram from "./components/TwinDiagram";
import { AnomalyChart, BuildingBars, ForecastChart, PowerChart } from "./components/Charts";
import {
  Controls, DeviceList, ExplanationPanel, IncidentTimeline, KpiBar, PhaseTracker,
} from "./components/Panels";

const shell: React.CSSProperties = {
  minHeight: "100vh",
  background: "#0b1220",
  color: "#e2e8f0",
  fontFamily: "'Segoe UI', system-ui, sans-serif",
  padding: 14,
};

const card = {
  background: "#0f172a",
  border: "1px solid #1e293b",
  borderRadius: 10,
  padding: 12,
};

const sectionTitle: React.CSSProperties = {
  fontSize: 11, color: "#94a3b8", marginBottom: 6, letterSpacing: 0.6, textTransform: "uppercase",
};

export default function App() {
  const { payload, connected, history, busy, launchDemo, reset, attack } = useGridShield();

  if (!payload) {
    return (
      <div style={{ ...shell, display: "grid", placeItems: "center" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: 1 }}>
            GridShield <span style={{ color: "#38bdf8" }}>AI</span>
          </div>
          <div style={{ marginTop: 8, color: "#64748b", fontSize: 13 }}>
            {connected ? "syncing telemetry…" : "connecting to backend at :8000…"}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={shell}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 12 }}>
        <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: 0.5 }}>
          GridShield <span style={{ color: "#38bdf8" }}>AI</span>
        </div>
        <div style={{ fontSize: 12, color: "#64748b" }}>Predict · Protect · Optimize</div>
        <div style={{ flex: 1 }} />
        <div style={{ fontSize: 11, color: connected ? "#22c55e" : "#ef4444" }}>
          ● {connected ? "LIVE" : "OFFLINE"} · t={payload.state.timestamp} · step {payload.state.step_index}
        </div>
      </div>

      <KpiBar payload={payload} />

      <div style={{ display: "grid", gridTemplateColumns: "1.25fr 1fr 1fr", gap: 12, marginTop: 12 }}>
        {/* Left column: twin + power chart */}
        <div style={{ display: "grid", gap: 12 }}>
          <TwinDiagram payload={payload} />
          <div style={card}>
            <div style={sectionTitle}>Power flows (5-min steps)</div>
            <PowerChart history={history} />
          </div>
        </div>

        {/* Middle column: security */}
        <div style={{ display: "grid", gap: 12, alignContent: "start" }}>
          <PhaseTracker payload={payload} />
          <div style={card}>
            <div style={sectionTitle}>Anomaly score</div>
            <AnomalyChart history={history} threshold={0.7} />
          </div>
          <ExplanationPanel payload={payload} />
          <Controls payload={payload} busy={busy} launchDemo={launchDemo} reset={reset} attack={attack} />
        </div>

        {/* Right column: ops */}
        <div style={{ display: "grid", gap: 12, alignContent: "start" }}>
          <div style={card}>
            <div style={sectionTitle}>AI forecast — next hour</div>
            <ForecastChart payload={payload} />
          </div>
          <div style={card}>
            <div style={sectionTitle}>Per-building demand</div>
            <BuildingBars payload={payload} />
          </div>
          <DeviceList payload={payload} />
          <IncidentTimeline incidents={payload.incidents.incidents} />
        </div>
      </div>

      <div style={{ marginTop: 12, fontSize: 11, color: "#475569" }}>
        IEEE SmartSecureGrid Challenge 2026 PoC — deterministic simulation (seed {payload.demo.seed ?? "n/a"}) ·
        All attacks are simulated locally; no real infrastructure is touched.
      </div>
    </div>
  );
}
