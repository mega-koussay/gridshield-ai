import type { Payload } from "../types";

interface Props {
  payload: Payload;
}

function flowColor(kw: number): string {
  if (Math.abs(kw) < 1) return "#94a3b8";
  return kw > 0 ? "#22c55e" : "#f59e0b";
}

function FlowLine({
  x1, y1, x2, y2, kw, label, dashed,
}: {
  x1: number; y1: number; x2: number; y2: number; kw: number; label?: string; dashed?: boolean;
}) {
  const active = Math.abs(kw) >= 1;
  return (
    <g>
      <line
        x1={x1} y1={y1} x2={x2} y2={y2}
        stroke={flowColor(kw)}
        strokeWidth={active ? 2 + Math.min(4, Math.abs(kw) / 40) : 1.2}
        strokeDasharray={dashed ? "5,4" : active ? "8,5" : undefined}
        opacity={active ? 0.9 : 0.35}
      >
        {active && (
          <animate
            attributeName="stroke-dashoffset"
            from="26" to="0" dur="1s" repeatCount="indefinite"
          />
        )}
      </line>
      {label && (
        <text
          x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 7}
          textAnchor="middle" fontSize="11" fill="#e2e8f0"
          style={{ fontWeight: 600 }}
        >
          {label}
        </text>
      )}
    </g>
  );
}

/** One-line diagram of the microgrid; the 2D digital twin. */
export default function TwinDiagram({ payload }: Props) {
  const s = payload.state;
  const attack = payload.kpis.attack_status;
  const stroke = attack === "UNDER_ATTACK" ? "#ef4444" : attack === "CONTAINED" ? "#f59e0b" : "#1e293b";

  const solarShown = s.solar_kw;
  const loadShown = s.load_kw;
  const batt = s.battery_kw; // + charging, - discharging
  const imp = s.grid_import_kw;
  const exp = s.grid_export_kw;

  return (
    <svg viewBox="0 0 640 400" style={{ width: "100%", height: "auto" }}>
      <defs>
        <radialGradient id="sunGrad" cx="50%" cy="50%">
          <stop offset="0%" stopColor="#fde047" />
          <stop offset="100%" stopColor="#f59e0b" />
        </radialGradient>
      </defs>

      {/* background */}
      <rect x="0" y="0" width="640" height="400" rx="12" fill="#0b1220" stroke={stroke} strokeWidth="2" />
      <text x="20" y="28" fontSize="14" fill="#94a3b8">DIGITAL TWIN — {payload.state.timestamp}</text>
      <text x="620" y="28" fontSize="12" textAnchor="end"
        fill={attack === "NORMAL" ? "#22c55e" : attack === "RECOVERED" ? "#38bdf8" : attack === "CONTAINED" ? "#f59e0b" : "#ef4444"}>
        {attack.replace("_", " ")}
      </text>

      {/* Solar plant (top-left) */}
      <g>
        <rect x="40" y="60" width="130" height="90" rx="10" fill="#111c33" stroke={payload.devices.find(d => d.device_id === "MTR_SOLAR")?.isolated ? "#ef4444" : "#334155"} />
        <circle cx="70" cy="92" r="16" fill="url(#sunGrad)" opacity={solarShown > 1 ? 1 : 0.25} />
        <path d="M 55 128 L 85 106 L 115 128 Z" fill="#1e3a5f" stroke="#3b82f6" />
        <text x="105" y="85" fontSize="13" fill="#e2e8f0" fontWeight="600">Solar PV</text>
        <text x="105" y="102" fontSize="12" fill="#7dd3fc">{solarShown.toFixed(0)} kW</text>
        <text x="105" y="140" fontSize="10" fill={payload.trusted.replaced.includes("MTR_SOLAR") ? "#f59e0b" : "#64748b"}>
          {payload.trusted.replaced.includes("MTR_SOLAR") ? "isolated — AI value" : "trusted"}
        </text>
      </g>

      {/* Battery (top-right) */}
      <g>
        <rect x="470" y="60" width="130" height="90" rx="10" fill="#111c33" stroke={payload.devices.find(d => d.device_id === "SCADA_ESS")?.isolated ? "#ef4444" : "#334155"} />
        <rect x="490" y="80" width="26" height="46" rx="4" fill="none" stroke="#94a3b8" />
        <rect x="490" y={126 - 46 * s.soc} width="26" height={46 * s.soc} rx="3"
          fill={s.soc < 0.2 ? "#ef4444" : s.soc < 0.35 ? "#f59e0b" : "#22c55e"} />
        <text x="530" y="92" fontSize="13" fill="#e2e8f0" fontWeight="600">Battery</text>
        <text x="530" y="110" fontSize="12" fill="#7dd3fc">{(s.soc * 100).toFixed(0)}% SOC</text>
        <text x="530" y="128" fontSize="11" fill={flowColor(-batt)}>
          {batt > 0 ? `charging ${batt.toFixed(0)} kW` : batt < 0 ? `discharging ${(-batt).toFixed(0)} kW` : "idle"}
        </text>
      </g>

      {/* Grid (left-bottom) */}
      <g>
        <rect x="40" y="230" width="130" height="90" rx="10" fill="#111c33" stroke={s.grid_breaker_open ? "#ef4444" : "#334155"} />
        <text x="60" y="262" fontSize="13" fill="#e2e8f0" fontWeight="600">Utility Grid</text>
        <text x="60" y="282" fontSize="12" fill={imp > 0 ? "#f59e0b" : exp > 0 ? "#22c55e" : "#64748b"}>
          {imp > 0 ? `import ${imp.toFixed(0)} kW` : exp > 0 ? `export ${exp.toFixed(0)} kW` : "standby"}
        </text>
        <text x="60" y="302" fontSize="10" fill="#64748b">limit {400} kW</text>
      </g>

      {/* Buildings (right-bottom) */}
      <g>
        <rect x="470" y="230" width="130" height="90" rx="10" fill="#111c33" stroke="#334155" />
        <text x="488" y="258" fontSize="13" fill="#e2e8f0" fontWeight="600">Campus Load</text>
        <text x="488" y="278" fontSize="12" fill="#7dd3fc">{loadShown.toFixed(0)} kW</text>
        <text x="488" y="296" fontSize="10" fill="#64748b">
          {Object.keys(s.building_loads).length} buildings · {s.temperature_c.toFixed(0)}°C
        </text>
      </g>

      {/* Central bus */}
      <circle cx="320" cy="190" r="26" fill="#0f172a" stroke="#38bdf8" strokeWidth="2" />
      <text x="320" y="186" textAnchor="middle" fontSize="10" fill="#94a3b8">microgrid</text>
      <text x="320" y="200" textAnchor="middle" fontSize="12" fill="#e2e8f0" fontWeight="700">BUS</text>

      {/* Power flows */}
      <FlowLine x1={170} y1={105} x2={300} y2={180} kw={solarShown} label={`${solarShown.toFixed(0)} kW`} />
      <FlowLine x1={470} y1={105} x2={340} y2={180} kw={-batt} label={Math.abs(batt) > 1 ? `${Math.abs(batt).toFixed(0)} kW` : undefined} />
      <FlowLine x1={170} y1={275} x2={300} y2={205} kw={imp} label={imp > 1 ? `${imp.toFixed(0)} kW` : undefined} />
      <FlowLine x1={300} y1={205} x2={170} y2={275} kw={exp} />
      <FlowLine x1={340} y1={180} x2={470} y2={275} kw={loadShown} label={`${loadShown.toFixed(0)} kW`} />

      {/* Blackout / overload banner */}
      {(s.blackout || s.overload) && (
        <text x="320" y="380" textAnchor="middle" fontSize="13" fill="#ef4444" fontWeight="700">
          {s.blackout ? "⚠ LOAD SHEDDING ACTIVE" : "⚠ GRID IMPORT NEAR LIMIT"}
        </text>
      )}
    </svg>
  );
}
