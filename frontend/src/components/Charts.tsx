import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { HistoryPoint } from "../hooks/useGridShield";
import type { Payload } from "../types";

const axis = { stroke: "#475569", fontSize: 10 };
const tipStyle = { background: "#0f172a", border: "1px solid #334155", fontSize: 12, color: "#e2e8f0" };

export function PowerChart({ history }: { history: HistoryPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={history} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
        <XAxis dataKey="t" tick={axis} minTickGap={28} />
        <YAxis tick={axis} />
        <Tooltip contentStyle={tipStyle} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Area type="monotone" dataKey="solar" name="Solar kW" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.25} strokeWidth={1.6} isAnimationActive={false} />
        <Area type="monotone" dataKey="load" name="Load kW" stroke="#38bdf8" fill="#38bdf8" fillOpacity={0.15} strokeWidth={1.6} isAnimationActive={false} />
        <Line type="monotone" dataKey="battery" name="Battery kW" stroke="#22c55e" strokeWidth={1.2} dot={false} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function AnomalyChart({ history, threshold }: { history: HistoryPoint[]; threshold: number }) {
  return (
    <ResponsiveContainer width="100%" height={150}>
      <LineChart data={history} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
        <XAxis dataKey="t" tick={axis} minTickGap={28} />
        <YAxis tick={axis} domain={[0, 1]} />
        <Tooltip contentStyle={tipStyle} />
        <ReferenceLine y={threshold} stroke="#ef4444" strokeDasharray="4 3" label={{ value: "threshold", fill: "#ef4444", fontSize: 10, position: "insideTopRight" }} />
        <Line type="stepAfter" dataKey="score" name="anomaly score" stroke="#f43f5e" strokeWidth={1.6} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ForecastChart({ payload }: { payload: Payload }) {
  const s = payload.state;
  const fc = payload.forecast;
  const data = fc.load_kw.map((l, i) => ({
    t: `+${(i + 1) * 5}m`,
    fc_load: l,
    fc_solar: fc.solar_kw[i],
    now_load: i === 0 ? s.metered_load_kw : undefined,
    now_solar: i === 0 ? s.metered_solar_kw : undefined,
  }));
  return (
    <ResponsiveContainer width="100%" height={170}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
        <XAxis dataKey="t" tick={axis} minTickGap={24} />
        <YAxis tick={axis} />
        <Tooltip contentStyle={tipStyle} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line type="monotone" dataKey="fc_load" name="load fc kW" stroke="#38bdf8" strokeWidth={1.6} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="fc_solar" name="solar fc kW" stroke="#f59e0b" strokeWidth={1.6} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="now_load" name="load now" stroke="#0ea5e9" strokeWidth={0} dot={{ r: 3, fill: "#0ea5e9" }} isAnimationActive={false} />
        <Line type="monotone" dataKey="now_solar" name="solar now" stroke="#d97706" strokeWidth={0} dot={{ r: 3, fill: "#d97706" }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function BuildingBars({ payload }: { payload: Payload }) {
  const data = Object.entries(payload.state.metered_building_loads).map(([k, v]) => ({
    name: k.replace(/^B\d+_/, "").slice(0, 10),
    kW: Math.round(v * 10) / 10,
  }));
  return (
    <ResponsiveContainer width="100%" height={150}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" tick={axis} />
        <YAxis tick={axis} />
        <Tooltip contentStyle={tipStyle} />
        <Bar dataKey="kW" fill="#38bdf8" radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
