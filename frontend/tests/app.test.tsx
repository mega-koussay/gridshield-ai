import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { KpiBar, PhaseTracker, Controls } from "../src/components/Panels";
import type { Payload } from "../src/types";

const basePayload: Payload = {
  state: {
    step_index: 42, minute_of_day: 600, day_index: 0, timestamp: "day00T10:00",
    solar_kw: 120, load_kw: 200, battery_kw: -50, battery_setpoint_kw: -50,
    grid_import_kw: 130, grid_export_kw: 0, soc: 0.5, cloud_factor: 0.9,
    temperature_c: 22, metered_solar_kw: 121, metered_load_kw: 320,
    metered_building_loads: { B1: 50, B2: 60 }, building_loads: { B1: 50, B2: 60 },
    unmet_load_kw: 0, overload: false, blackout: false, grid_breaker_open: false,
  },
  trusted: { solar_kw: 120, load_kw: 200, replaced: [] },
  forecast: { load_kw: [200, 201], solar_kw: [120, 118], horizon_min: 60 },
  detection: {
    step_index: 42, score: 0.2, is_anomaly: false, confidence: 0.8,
    signals: { z_load: 0.1, z_solar: 0.1, z_meter: 0, z_battery: 0 }, top_features: [], worst_meter: null,
  },
  classification: { label: "NONE", confidence: 0.7, probs: { NONE: 0.7 } },
  explanation: null,
  devices: [
    { device_id: "MTR_SOLAR", kind: "inverter", label: "Solar Inverter Meter", compromised: false, isolated: false, health: 100, last_attack_step: null },
  ],
  attacks: { active: [], total_injected: 0 },
  incidents: { incidents: [], open_count: 0, last_recovery_steps: null },
  kpis: {
    energy_balance_kw: -80, soc: 0.5, anomaly_score: 0.2, attack_status: "NORMAL",
    unmet_load_kw: 0, blackout: false, overload: false, detection_latency_steps: null,
    recovery_steps: null, reconstruction_mae: null, self_sufficiency: 0.6,
    defender_setpoint_kw: -50, control_hijacked: false,
  },
  demo: {
    active: false, phase: "NORMAL",
    phases: ["NORMAL", "ATTACK", "DETECTION", "EXPLANATION", "DEFENSE", "RECONSTRUCTION", "RE-OPTIMIZATION", "RECOVERY"],
    log: [], attack_scheduled_step: null, seed: 2026,
  },
  events: [], server_time: 0, ticks: 1,
};

describe("KpiBar", () => {
  it("renders attack status and SOC", () => {
    render(<KpiBar payload={basePayload} />);
    expect(screen.getByText("NORMAL")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
  });

  it("shows attack state in red wording", () => {
    const p = { ...basePayload, kpis: { ...basePayload.kpis, attack_status: "UNDER_ATTACK" } };
    render(<KpiBar payload={p} />);
    expect(screen.getByText("UNDER ATTACK")).toBeTruthy();
  });
});

describe("PhaseTracker", () => {
  it("lists all eight demo phases", () => {
    render(<PhaseTracker payload={{ ...basePayload, demo: { ...basePayload.demo, active: true } }} />);
    for (const ph of basePayload.demo.phases) expect(screen.getAllByText(new RegExp(ph)).length).toBeGreaterThan(0);
  });
});

describe("Controls", () => {
  it("launches demo with the selected attack and seed", () => {
    const launch = vi.fn();
    render(<Controls payload={basePayload} busy={false} launchDemo={launch} reset={vi.fn()} attack={vi.fn()} />);
    fireEvent.click(screen.getByText("▶ RUN DEMO"));
    expect(launch).toHaveBeenCalledWith("FDI_BULK", 2026);
  });
  it("reset button calls reset", () => {
    const reset = vi.fn();
    render(<Controls payload={basePayload} busy={false} launchDemo={vi.fn()} reset={reset} attack={vi.fn()} />);
    fireEvent.click(screen.getByText("⟲ RESET"));
    expect(reset).toHaveBeenCalled();
  });
});
