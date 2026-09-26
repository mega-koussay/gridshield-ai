// Shared types for the GridShield AI backend payloads.
export interface TwinState {
  step_index: number;
  minute_of_day: number;
  day_index: number;
  timestamp: string;
  solar_kw: number;
  load_kw: number;
  battery_kw: number;
  battery_setpoint_kw: number;
  grid_import_kw: number;
  grid_export_kw: number;
  soc: number;
  cloud_factor: number;
  temperature_c: number;
  metered_solar_kw: number;
  metered_load_kw: number;
  metered_building_loads: Record<string, number>;
  building_loads: Record<string, number>;
  unmet_load_kw: number;
  overload: boolean;
  blackout: boolean;
  grid_breaker_open: boolean;
}

export interface DeviceInfo {
  device_id: string;
  kind: string;
  label: string;
  compromised: boolean;
  isolated: boolean;
  health: number;
  last_attack_step: number | null;
}

export interface DetectionInfo {
  step_index: number;
  score: number;
  is_anomaly: boolean;
  confidence: number;
  signals: Record<string, number>;
  top_features: [string, number][];
  worst_meter: string | null;
}

export interface ClassificationInfo {
  label: string;
  confidence: number;
  probs: Record<string, number>;
}

export interface ExplanationInfo {
  title: string;
  story: string;
  reasons: string[];
  anomaly_score: number;
  threshold: number;
  confidence: number;
  signals: Record<string, number>;
  attributions: [string, number][];
  threshold_note: string;
  reconstruction?: {
    replaced: string[];
    trusted_solar_kw: number;
    trusted_load_kw: number;
  };
}

export interface IncidentAction {
  step_index: number;
  action: string;
  detail: string;
}

export interface IncidentInfo {
  incident_id: string;
  attack_type: string;
  device_id: string;
  detected_step: number;
  resolved_step: number | null;
  confidence: number;
  status: string;
  actions: IncidentAction[];
}

export interface Kpis {
  energy_balance_kw: number;
  soc: number;
  anomaly_score: number;
  attack_status: string;
  unmet_load_kw: number;
  blackout: boolean;
  overload: boolean;
  detection_latency_steps: number | null;
  recovery_steps: number | null;
  reconstruction_mae: number | null;
  self_sufficiency: number;
  defender_setpoint_kw: number | null;
  control_hijacked: boolean;
}

export interface DemoInfo {
  active: boolean;
  phase: string;
  phases: string[];
  log: { phase: string; step_index: number; message: string }[];
  attack_scheduled_step: number | null;
  seed: number | null;
}

export interface GridEvent {
  ts: number;
  step_index: number;
  kind: string;
  severity: string;
  message: string;
  extra?: Record<string, unknown>;
}

export interface Payload {
  state: TwinState;
  trusted: {
    solar_kw: number;
    load_kw: number;
    replaced: string[];
  };
  forecast: {
    load_kw: number[];
    solar_kw: number[];
    horizon_min: number;
  };
  detection: DetectionInfo;
  classification: ClassificationInfo;
  explanation: ExplanationInfo | null;
  devices: DeviceInfo[];
  attacks: { active: Record<string, unknown>[]; total_injected: number };
  incidents: { incidents: IncidentInfo[]; open_count: number; last_recovery_steps: number | null };
  kpis: Kpis;
  demo: DemoInfo;
  events: GridEvent[];
  server_time: number;
  ticks: number;
}

export const ATTACK_TYPES = [
  "FDI_BULK",
  "FDI_SOLAR",
  "SCADA_CMD",
  "DEVICE_MALWARE",
  "TELEMETRY_SPIKE",
] as const;

export type AttackType = (typeof ATTACK_TYPES)[number];

export const ATTACK_DESCRIPTIONS: Record<AttackType, string> = {
  FDI_BULK: "False-data injection: site load readings are inflated.",
  FDI_SOLAR: "Solar production measurement is overstated.",
  SCADA_CMD: "Hijacked SCADA session drives the battery setpoint.",
  DEVICE_MALWARE: "One smart meter reports corrupted per-building demand.",
  TELEMETRY_SPIKE: "Physically impossible jump in the solar telemetry.",
};
