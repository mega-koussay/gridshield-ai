"""Attack simulator: five threat classes corrupting metered telemetry.

All attacks are strictly local to the simulated telemetry path. Nothing here
touches real infrastructure; the simulator never modifies true twin state,
only what the SCADA layer *sees* (metered_* fields) - except SCADA_CMD, which
deliberately abuses the battery setpoint, because that is what a real
compromised SCADA session would do. The impact therefore becomes measurable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from app.core.config import settings
from .simulator import GridState, MicrogridSimulator

ATTACK_TYPES = (
    "FDI_BULK",         # false-data injection: shift metered load by a fraction
    "FDI_SOLAR",        # overstate solar production measurement
    "SCADA_CMD",        # abnormal battery control command applied to the twin
    "DEVICE_MALWARE",   # compromised meter drifts per-building values
    "TELEMETRY_SPIKE",  # sudden physically impossible telemetry change
)


@dataclass
class AttackEvent:
    """A single active or completed attack episode."""

    attack_id: str
    attack_type: str
    device_id: str
    start_step: int
    duration_steps: int
    magnitude: float
    active: bool = True
    steps_done: int = 0

    def to_dict(self) -> dict:
        return {
            "attack_id": self.attack_id,
            "attack_type": self.attack_type,
            "device_id": self.device_id,
            "start_step": self.start_step,
            "duration_steps": self.duration_steps,
            "magnitude": self.magnitude,
            "active": self.active,
            "steps_done": self.steps_done,
        }


class AttackSimulator:
    """Injects controlled faults into metered telemetry only."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self.rng = np.random.default_rng(seed if seed is not None else settings.scenario_seed)
        self.active_attacks: List[AttackEvent] = []
        self._counter = 0
        self.total_injected = 0
        self._pending_scada_cmd: Dict[str, float] = {}

    # ------------------------------------------------------------------ #
    def launch(
        self,
        attack_type: str,
        device_id: str,
        duration_min: int = 30,
        magnitude: Optional[float] = None,
        current_step: int = 0,
    ) -> AttackEvent:
        """Schedule an attack starting at `current_step` (or immediately)."""
        if attack_type not in ATTACK_TYPES:
            raise ValueError(f"Unknown attack type: {attack_type}")
        self._counter += 1
        if magnitude is None:
            magnitude = {
                "FDI_BULK": 0.35,
                "FDI_SOLAR": 0.45,
                "SCADA_CMD": 1.0,
                "DEVICE_MALWARE": 0.30,
                "TELEMETRY_SPIKE": 3.0,
            }[attack_type]
        ev = AttackEvent(
            attack_id=f"ATK-{self._counter:04d}",
            attack_type=attack_type,
            device_id=device_id,
            start_step=int(current_step),
            duration_steps=max(1, int(duration_min / settings.step_minutes)),
            magnitude=float(magnitude),
        )
        self.active_attacks.append(ev)
        return ev

    # ------------------------------------------------------------------ #
    def apply_to_state(self, state: GridState, current_step: Optional[int] = None) -> GridState:
        """Corrupt the metered fields of `state` for every active attack.

        Called by the orchestrator *after* the twin produced clean telemetry.
        Episodes with a future `start_step` are skipped until due. Advances
        per-episode step counters; deactivates finished episodes.
        """
        now = int(current_step) if current_step is not None else state.step_index
        still_active: List[AttackEvent] = []
        for ev in self.active_attacks:
            if now < ev.start_step:
                still_active.append(ev)  # armed but not yet due
                continue
            if ev.steps_done >= ev.duration_steps:
                ev.active = False
                continue
            self._apply_one(ev, state)
            ev.steps_done += 1
            self.total_injected += 1
            if ev.steps_done >= ev.duration_steps:
                ev.active = False
            still_active.append(ev)
        self.active_attacks = still_active
        return state

    # ------------------------------------------------------------------ #
    def _apply_one(self, ev: AttackEvent, state: GridState) -> None:
        t = ev.attack_type
        if t == "FDI_BULK":
            # Additive offset + proportional exaggeration of total load.
            state.metered_load_kw = state.metered_load_kw * (1.0 + ev.magnitude) + 8.0
            for k in list(state.metered_building_loads.keys()):
                state.metered_building_loads[k] *= 1.0 + ev.magnitude * 0.9
        elif t == "FDI_SOLAR":
            # Report far more solar production than actually produced.
            state.metered_solar_kw = state.metered_solar_kw * (1.0 + ev.magnitude) + 12.0 * ev.magnitude
        elif t == "SCADA_CMD":
            # Real control-path attack: force the battery setpoint in the twin.
            self._pending_scada_cmd["battery_setpoint"] = ev.magnitude * settings.battery_power_kw
        elif t == "DEVICE_MALWARE":
            # One compromised meter drifts its own reading away from truth.
            key = ev.device_id.replace("MTR_", "")
            if key in state.metered_building_loads:
                drift = state.metered_building_loads[key] * (1.0 + ev.magnitude)
                state.metered_building_loads[key] = drift
                state.metered_load_kw = float(sum(state.metered_building_loads.values()))
        elif t == "TELEMETRY_SPIKE":
            # Physically implausible jump in the reported solar meter.
            state.metered_solar_kw = min(
                state.metered_solar_kw + ev.magnitude * settings.solar_capacity_kw,
                3.0 * settings.solar_capacity_kw,
            )

    # ------------------------------------------------------------------ #
    def pop_scada_command(self) -> Optional[float]:
        """Return (and clear) a forced battery setpoint if a SCADA_CMD ran."""
        return self._pending_scada_cmd.pop("battery_setpoint", None)

    def clear(self) -> None:
        self.active_attacks = []
        self._pending_scada_cmd.clear()
        self.total_injected = 0

    # ------------------------------------------------------------------ #
    def status(self) -> Dict[str, object]:
        return {
            "active": [e.to_dict() for e in self.active_attacks if e.active],
            "total_injected": self.total_injected,
        }
