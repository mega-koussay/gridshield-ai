"""Deterministic synthetic microgrid digital twin.

Physics/state model
-------------------
The twin advances in fixed 5-minute steps of *simulated* time. Every step each
component produces a measurement; smart meters add small Gaussian noise so the
telemetry looks realistic but stays reproducible (seeded RNG).

Components:
  * Solar PV plant     - clear-sky bell curve * cloud intermittency.
  * Battery (BESS)     - SOC, power/energy limits, round-trip efficiency.
  * Grid connection    - import/export within configurable limits.
  * Buildings (6)      - daily demand profiles with occupancy/weather effects.
  * Smart meters       - noisy per-building measurements + solar meter.
  * SCADA layer        - battery power setpoint + grid breaker state.

Everything derives from a single numpy Generator seeded from settings, so a
given seed + step index always yields the same telemetry.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from app.core.config import settings


@dataclass
class Device:
    """A monitored field device (meter, inverter, SCADA node)."""

    device_id: str
    kind: str  # meter | inverter | scada
    label: str
    compromised: bool = False
    isolated: bool = False
    health: float = 100.0  # 0-100 security health score
    last_attack_step: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "kind": self.kind,
            "label": self.label,
            "compromised": self.compromised,
            "isolated": self.isolated,
            "health": round(self.health, 1),
            "last_attack_step": self.last_attack_step,
        }


@dataclass
class GridState:
    """Full state snapshot of the microgrid at one simulated instant."""

    step_index: int
    minute_of_day: float
    day_index: int
    timestamp: str
    # Power [kW]
    solar_kw: float
    load_kw: float
    battery_kw: float  # positive = charging
    battery_setpoint_kw: float
    grid_import_kw: float
    grid_export_kw: float
    # Energy
    soc: float  # 0..1
    # Weather/environment
    cloud_factor: float
    temperature_c: float
    # Meters (what the SCADA layer *sees*, potentially corrupted)
    metered_solar_kw: float
    metered_load_kw: float
    metered_building_loads: Dict[str, float] = field(default_factory=dict)
    # True (twin) per-building loads
    building_loads: Dict[str, float] = field(default_factory=dict)
    # Derived
    unmet_load_kw: float = 0.0
    overload: bool = False
    blackout: bool = False
    grid_breaker_open: bool = False

    def to_dict(self) -> dict:
        return {
            "step_index": self.step_index,
            "minute_of_day": round(self.minute_of_day, 1),
            "day_index": self.day_index,
            "timestamp": self.timestamp,
            "solar_kw": round(self.solar_kw, 2),
            "load_kw": round(self.load_kw, 2),
            "battery_kw": round(self.battery_kw, 2),
            "battery_setpoint_kw": round(self.battery_setpoint_kw, 2),
            "grid_import_kw": round(self.grid_import_kw, 2),
            "grid_export_kw": round(self.grid_export_kw, 2),
            "soc": round(self.soc, 4),
            "cloud_factor": round(self.cloud_factor, 3),
            "temperature_c": round(self.temperature_c, 1),
            "metered_solar_kw": round(self.metered_solar_kw, 2),
            "metered_load_kw": round(self.metered_load_kw, 2),
            "metered_building_loads": {k: round(v, 2) for k, v in self.metered_building_loads.items()},
            "building_loads": {k: round(v, 2) for k, v in self.building_loads.items()},
            "unmet_load_kw": round(self.unmet_load_kw, 2),
            "overload": self.overload,
            "blackout": self.blackout,
            "grid_breaker_open": self.grid_breaker_open,
        }


BUILDING_NAMES = [
    "B1_Offices",
    "B2_Library",
    "B3_DataCenter",
    "B4_Cafeteria",
    "B5_Labs",
    "B6_Dormitory",
]

# Base peak demand [kW] per building; shaped by daily profile below.
BUILDING_PEAK_KW = {
    "B1_Offices": 42.0,
    "B2_Library": 30.0,
    "B3_DataCenter": 65.0,
    "B4_Cafeteria": 28.0,
    "B5_Labs": 38.0,
    "B6_Dormitory": 35.0,
}


def daily_load_shape(minute_of_day: float, kind_index: int) -> float:
    """Normalized (0..1] daily demand shape for a building archetype."""
    h = (minute_of_day / 60.0) % 24.0
    # Morning + evening peaks, night trough; archetypes shift the phase.
    phase = [0.0, 0.6, 0.0, 1.4, 0.3, -1.0][kind_index % 6]
    depth = [0.25, 0.35, 0.55, 0.40, 0.30, 0.45][kind_index % 6]
    base = depth + (1.0 - depth) * 0.5 * (
        1.0 + math.cos((h - (10.0 + phase)) / 24.0 * 2.0 * math.pi)
    )
    # Cafeteria lunch bump
    if kind_index % 6 == 3:
        bump = math.exp(-((h - 12.5) ** 2) / 1.5)
        base += 0.45 * bump
    # Data center nearly flat
    if kind_index % 6 == 2:
        base = 0.75 + 0.2 * math.sin(h / 24.0 * 2.0 * math.pi)
    return float(min(max(base, 0.05), 1.2))


def clear_sky_irradiance(minute_of_day: float, day_index: int) -> float:
    """Normalized clear-sky irradiance 0..1 with seasonal sun-height factor."""
    h = (minute_of_day / 60.0) % 24.0
    seasonal = 1.0 + 0.12 * math.sin((day_index % 365) / 365.0 * 2.0 * math.pi)
    x = (h - 6.0) / 12.0  # 0 at 06:00, 1 at 18:00
    if x <= 0.0 or x >= 1.0:
        return 0.0
    return max(0.0, math.sin(x * math.pi)) * seasonal


class MicrogridSimulator:
    """Seeded, deterministic microgrid digital twin."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self.seed = seed if seed is not None else settings.seed
        self.rng = np.random.default_rng(self.seed)
        self.n_buildings = settings.n_buildings
        self.step_index = 0
        self.day_index = 0
        self.minute_of_day = 6.0 * 60.0  # start at 06:00
        self.soc = 0.55
        self.cloud_state = 0.85  # smoothOU process
        self.temperature_c = 22.0
        self.battery_setpoint_kw = 0.0
        self.grid_breaker_open = False
        self.devices: List[Device] = [
            Device("MTR_SOLAR", "inverter", "Solar Inverter Meter")
        ]
        for i, name in enumerate(BUILDING_NAMES[: self.n_buildings]):
            self.devices.append(Device(f"MTR_{name}", "meter", f"Smart Meter {name}"))
        self.devices.append(Device("SCADA_ESS", "scada", "SCADA ESS Controller"))
        self.devices.append(Device("SCADA_GRID", "scada", "SCADA Grid Breaker"))
        self._last_state: Optional[GridState] = None

    # ------------------------------------------------------------------ #
    def reset(self, seed: Optional[int] = None, start_soc: float = 0.55) -> None:
        self.seed = seed if seed is not None else self.seed
        self.rng = np.random.default_rng(self.seed)
        self.step_index = 0
        self.day_index = 0
        self.minute_of_day = 6.0 * 60.0
        self.soc = start_soc
        self.cloud_state = 0.85
        self.temperature_c = 22.0
        self.battery_setpoint_kw = 0.0
        self.grid_breaker_open = False
        for d in self.devices:
            d.compromised = False
            d.isolated = False
            d.health = 100.0
            d.last_attack_step = None
        self._last_state = None

    # ------------------------------------------------------------------ #
    def _advance_cloud(self) -> float:
        """Smooth OU-like cloud factor in [0.25, 1.0]; 1 = clear."""
        jump = self.rng.normal(0.0, 0.05)
        self.cloud_state = float(np.clip(self.cloud_state + jump, 0.25, 1.0))
        # Pull gently back towards clear sky.
        self.cloud_state = float(np.clip(self.cloud_state + 0.08 * (1.0 - self.cloud_state), 0.25, 1.0))
        return self.cloud_state

    def true_solar_kw(self, minute_of_day: float, day_index: int) -> float:
        irr = clear_sky_irradiance(minute_of_day, day_index)
        return irr * self.cloud_state * settings.solar_capacity_kw

    def true_building_loads(self) -> Dict[str, float]:
        loads: Dict[str, float] = {}
        for i, name in enumerate(BUILDING_NAMES[: self.n_buildings]):
            shape = daily_load_shape(self.minute_of_day, i)
            temp_effect = 1.0 + 0.010 * max(0.0, self.temperature_c - 26.0)
            noise = float(self.rng.normal(1.0, 0.03))
            loads[name] = max(0.5, BUILDING_PEAK_KW.get(name, 30.0) * shape * temp_effect * noise)
        return loads

    # ------------------------------------------------------------------ #
    def compute_power_balance(
        self,
        solar_kw: float,
        load_kw: float,
        battery_setpoint_kw: Optional[float] = None,
    ) -> Dict[str, float]:
        """Solve one step of power balance and update SOC.

        battery_setpoint_kw > 0 means charging. If None, a simple rule-based
        controller arbitrates (used before AI optimizer proposes a schedule).
        """
        if battery_setpoint_kw is None:
            surplus = solar_kw - load_kw
            if surplus > 0:
                # charge up to limit, respecting SOC window
                room = (settings.battery_soc_max - self.soc) * settings.battery_capacity_kwh * 12.0  # kWh per 5-min
                p_charge = min(settings.battery_power_kw, surplus, max(room, 0.0))
                setpoint = p_charge
            else:
                need = -surplus
                avail = (self.soc - settings.battery_soc_min) * settings.battery_capacity_kwh * 12.0
                p_dis = min(settings.battery_power_kw, need, max(avail, 0.0))
                setpoint = -p_dis
        else:
            setpoint = float(np.clip(battery_setpoint_kw, -settings.battery_power_kw, settings.battery_power_kw))

        # SOC update with efficiency
        dt_h = settings.step_minutes / 60.0
        if setpoint > 0:  # charging
            energy_in = setpoint * settings.battery_eta * dt_h
            energy_in = min(energy_in, (settings.battery_soc_max - self.soc) * settings.battery_capacity_kwh)
            actual_charge_kw = energy_in / (settings.battery_eta * dt_h) if dt_h > 0 else 0.0
            self.soc += energy_in / settings.battery_capacity_kwh
            battery_kw = actual_charge_kw
        else:  # discharging
            energy_out = -setpoint / settings.battery_eta * dt_h
            energy_out = min(energy_out, (self.soc - settings.battery_soc_min) * settings.battery_capacity_kwh)
            actual_dis_kw = energy_out * settings.battery_eta / dt_h if dt_h > 0 else 0.0
            self.soc -= energy_out / settings.battery_capacity_kwh
            battery_kw = -actual_dis_kw

        net = solar_kw + battery_kw - load_kw  # >0 export, <0 import
        if self.grid_breaker_open:
            grid_import = 0.0
            grid_export = 0.0
            unmet = max(0.0, load_kw - solar_kw - max(battery_kw, 0.0) - max(-battery_kw, 0.0))
            unmet = max(0.0, load_kw - solar_kw - battery_kw)
        else:
            if net >= 0:
                grid_export = min(net, settings.grid_export_limit_kw)
                grid_import = 0.0
            else:
                grid_import = min(-net, settings.grid_import_limit_kw)
                grid_export = 0.0
            unmet = max(0.0, load_kw - solar_kw - battery_kw - grid_import)

        overload = grid_import > settings.grid_import_limit_kw * 0.98
        blackout = unmet > 1.0
        return {
            "battery_kw": battery_kw,
            "grid_import_kw": grid_import,
            "grid_export_kw": grid_export,
            "unmet_load_kw": unmet,
            "overload": overload,
            "blackout": blackout,
        }

    # ------------------------------------------------------------------ #
    def step(self, battery_setpoint_kw: Optional[float] = None) -> GridState:
        """Advance one 5-minute simulated step and return the new state."""
        self._advance_cloud()
        # Slow temperature drift
        self.temperature_c += float(self.rng.normal(0.0, 0.08))
        self.temperature_c = float(np.clip(self.temperature_c, 12.0, 38.0))

        solar_kw = self.true_solar_kw(self.minute_of_day, self.day_index)
        loads = self.true_building_loads()
        load_kw = float(sum(loads.values()))

        bal = self.compute_power_balance(solar_kw, load_kw, battery_setpoint_kw)
        self.battery_setpoint_kw = bal["battery_kw"]

        # Smart-meter measurement noise (uncorrupted path)
        def noisy(v: float, rel: float = 0.01, abs_kw: float = 0.15) -> float:
            return max(0.0, v + self.rng.normal(0.0, rel * v + abs_kw))

        metered_solar = noisy(solar_kw, 0.012, 0.3)
        metered_loads = {k: noisy(v) for k, v in loads.items()}
        metered_load = float(sum(metered_loads.values()))

        hh = int(self.minute_of_day // 60) % 24
        mm = int(self.minute_of_day % 60)
        state = GridState(
            step_index=self.step_index,
            minute_of_day=self.minute_of_day,
            day_index=self.day_index,
            timestamp=f"day{self.day_index:02d}T{hh:02d}:{mm:02d}",
            solar_kw=solar_kw,
            load_kw=load_kw,
            battery_kw=bal["battery_kw"],
            battery_setpoint_kw=self.battery_setpoint_kw,
            grid_import_kw=bal["grid_import_kw"],
            grid_export_kw=bal["grid_export_kw"],
            soc=self.soc,
            cloud_factor=self.cloud_state,
            temperature_c=self.temperature_c,
            metered_solar_kw=metered_solar,
            metered_load_kw=metered_load,
            metered_building_loads=metered_loads,
            building_loads=loads,
            unmet_load_kw=bal["unmet_load_kw"],
            overload=bal["overload"],
            blackout=bal["blackout"],
            grid_breaker_open=self.grid_breaker_open,
        )
        self._last_state = state
        self.step_index += 1
        self.minute_of_day += settings.step_minutes
        if self.minute_of_day >= 1440.0:
            self.minute_of_day -= 1440.0
            self.day_index += 1
        return state

    # ------------------------------------------------------------------ #
    @property
    def last_state(self) -> Optional[GridState]:
        return self._last_state

    def device_health_update(self, device_id: str, delta: float) -> None:
        for d in self.devices:
            if d.device_id == device_id:
                d.health = float(np.clip(d.health + delta, 0.0, 100.0))
                return

    def set_compromised(self, device_id: str, value: bool) -> None:
        for d in self.devices:
            if d.device_id == device_id:
                d.compromised = value
                return

    def set_isolated(self, device_id: str, value: bool) -> None:
        for d in self.devices:
            if d.device_id == device_id:
                d.isolated = value
                return
