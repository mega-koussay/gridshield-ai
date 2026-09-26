"""Automated resilience responder.

When the detector raises an alert, this engine executes the response chain:
identify -> explain -> isolate -> stop trusting -> reconstruct -> recompute
state -> re-optimize -> log. Every action is recorded in the incident log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from app.core.config import settings
from app.twin.simulator import MicrogridSimulator


@dataclass
class ResponseAction:
    step_index: int
    action: str
    detail: str

    def to_dict(self) -> dict:
        return {"step_index": self.step_index, "action": self.action, "detail": self.detail}


@dataclass
class Incident:
    incident_id: str
    attack_type: str
    device_id: str
    detected_step: int
    resolved_step: Optional[int] = None
    confidence: float = 0.0
    actions: List[ResponseAction] = field(default_factory=list)
    status: str = "open"  # open | contained | recovered

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "attack_type": self.attack_type,
            "device_id": self.device_id,
            "detected_step": self.detected_step,
            "resolved_step": self.resolved_step,
            "confidence": round(self.confidence, 3),
            "status": self.status,
            "actions": [a.to_dict() for a in self.actions],
        }


class Responder:
    def __init__(self, sim: MicrogridSimulator) -> None:
        self.sim = sim
        self.incidents: List[Incident] = []
        self._counter = 0
        self.recovery_start_step: Optional[int] = None
        self.last_recovery_steps: Optional[int] = None

    def reset(self) -> None:
        self.incidents = []
        self._counter = 0
        self.recovery_start_step = None
        self.last_recovery_steps = None

    # ------------------------------------------------------------------ #
    def open_incident(self, attack_type: str, device_id: str, step: int, confidence: float) -> Incident:
        self._counter += 1
        inc = Incident(
            incident_id=f"INC-{self._counter:04d}",
            attack_type=attack_type,
            device_id=device_id,
            detected_step=step,
            confidence=confidence,
        )
        inc.actions.append(ResponseAction(step, "DETECTED",
                          f"{attack_type} suspected on {device_id} (confidence {confidence*100:.0f}%)"))
        self.incidents.append(inc)
        self.recovery_start_step = step
        return inc

    # ------------------------------------------------------------------ #
    def attribute_device(self, attack_type: str, window_df, latest) -> str:
        """Pick the most likely compromised device from the telemetry."""
        if attack_type in ("FDI_SOLAR", "TELEMETRY_SPIKE"):
            return "MTR_SOLAR"
        if attack_type == "SCADA_CMD":
            return "SCADA_ESS"
        if attack_type == "DEVICE_MALWARE":
            # Meter furthest from its proportional share of the site load.
            per = latest.get("metered_building_loads", {})
            total = sum(per.values()) or 1.0
            shares = {k: v / total for k, v in per.items()}
            expected = 1.0 / max(1, len(per))
            dev = max(shares, key=lambda k: abs(shares[k] - expected))
            return f"MTR_{dev}"
        # FDI_BULK: site-level; pick the meter with the largest 5-min jump.
        per = latest.get("metered_building_loads", {})
        if per and len(window_df) > 1:
            prev = window_df.iloc[-2].get("metered_building_loads", {})
            deltas = {k: per.get(k, 0) - prev.get(k, 0) for k in per}
            dev = max(deltas, key=lambda k: abs(deltas[k]))
            return f"MTR_{dev}"
        return "SCADA_ESS"

    # ------------------------------------------------------------------ #
    def contain(self, inc: Incident, step: int) -> None:
        dev = inc.device_id
        self.sim.set_isolated(dev, True)
        self.sim.set_compromised(dev, True)
        self.sim.device_health_update(dev, -40.0)
        inc.actions.append(ResponseAction(step, "ISOLATED",
                          f"{dev} isolated from the SCADA network; its data no longer trusted."))
        inc.status = "contained"

    def recover(self, inc: Incident, step: int, recon_note: str) -> None:
        inc.actions.append(ResponseAction(step, "RECONSTRUCTED", recon_note))
        # After a short probation the device is re-admitted (patched).
        if inc.status == "contained" and self.recovery_start_step is not None \
                and step - inc.detected_step >= 6 and step - inc.detected_step > 0:
            pass  # re-admission handled by orchestrator once stable

    def readmit(self, inc: Incident, step: int) -> None:
        self.sim.set_isolated(inc.device_id, False)
        self.sim.set_compromised(inc.device_id, False)
        self.sim.device_health_update(inc.device_id, +40.0)
        inc.actions.append(ResponseAction(step, "RESTORED",
                          f"{inc.device_id} re-admitted after clean probation; health restored."))
        inc.status = "recovered"
        inc.resolved_step = step
        if self.recovery_start_step is not None:
            self.last_recovery_steps = step - self.recovery_start_step

    # ------------------------------------------------------------------ #
    def log_optimization(self, inc: Incident, step: int, note: str) -> None:
        inc.actions.append(ResponseAction(step, "RE-OPTIMIZED", note))

    def status(self) -> Dict:
        open_inc = [i for i in self.incidents if i.status != "recovered"]
        return {
            "incidents": [i.to_dict() for i in self.incidents[-12:]],
            "open_count": len(open_inc),
            "last_recovery_steps": self.last_recovery_steps,
        }
