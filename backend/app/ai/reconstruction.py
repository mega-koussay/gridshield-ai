"""Reconstruction of corrupted measurements.

Channel-aware reconstruction: only the telemetry channels that the incident's
attack type actually corrupts are replaced.

  FDI_BULK        site load total is corrupted -> AI forecast trajectory
                  frozen at containment time (no feedback drift: the forecast
                  never re-ingests its own reconstructions).
  FDI_SOLAR /
  TELEMETRY_SPIKE solar meter corrupted -> frozen solar forecast trajectory.
  DEVICE_MALWARE  one meter corrupted -> spatial consensus of the healthy
                  meters (real data), anchored to the forecast regime.
  SCADA_CMD       load/solar telemetry is clean; the defense is revoking the
                  attacker's control session, so nothing is replaced.

The reconstruction error vs. the twin's TRUE values is tracked for the
recovery-quality KPI.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np


# Attack types that corrupt each channel.
LOAD_CORRUPTING = {"FDI_BULK"}
SOLAR_CORRUPTING = {"FDI_SOLAR", "TELEMETRY_SPIKE"}


class ReconstructionEngine:
    def __init__(self) -> None:
        self.reconstructions: List[Dict] = []
        self.errors: List[float] = []

    def reset(self) -> None:
        self.reconstructions = []
        self.errors = []

    # ------------------------------------------------------------------ #
    def reconstruct(
        self,
        state_dict: Dict,
        pred_load: float,
        pred_solar: float,
        isolated_devices: List[str],
        attack_type: str = "ANOMALY",
    ) -> Dict:
        """Return trusted solar/load for the control loop."""
        trusted = {
            "solar_kw": state_dict["metered_solar_kw"],
            "load_kw": state_dict["metered_load_kw"],
            "replaced": [],
            "errors": {},
        }

        replace_solar = "MTR_SOLAR" in isolated_devices and (
            attack_type in SOLAR_CORRUPTING or attack_type == "ANOMALY"
        )
        replace_load = any(d.startswith("MTR_B") for d in isolated_devices) and (
            attack_type in LOAD_CORRUPTING | {"DEVICE_MALWARE"} or attack_type == "ANOMALY"
        )

        if replace_solar:
            trusted["solar_kw"] = float(pred_solar)
            trusted["replaced"].append("MTR_SOLAR")
            true = state_dict.get("solar_kw_true", state_dict.get("solar_kw"))
            if true is not None:
                err = abs(float(pred_solar) - float(true))
                trusted["errors"]["solar"] = err
                self.errors.append(err)

        if replace_load:
            per_building = state_dict.get("metered_building_loads", {})
            healthy = [float(v) for k, v in per_building.items()
                       if f"MTR_{k}" not in isolated_devices]
            all_m = max(1, len(per_building))
            if healthy and attack_type == "DEVICE_MALWARE":
                # Spatial consensus: healthy meters are real observations.
                # Scale their sum to the site level assuming the isolated
                # building sits at the average share.
                healthy_site = sum(healthy) * (all_m / max(1, len(healthy)))
                # Anchor 30% on the forecast to stay in the predicted regime.
                trusted["load_kw"] = 0.7 * healthy_site + 0.3 * float(pred_load)
            else:
                # Site-wide corruption: trust the (frozen) AI forecast.
                trusted["load_kw"] = float(pred_load)
            trusted["replaced"].extend([d for d in isolated_devices if d.startswith("MTR_B")])
            true = state_dict.get("load_kw_true", state_dict.get("load_kw"))
            if true is not None:
                err = abs(trusted["load_kw"] - float(true))
                trusted["errors"]["load"] = err
                self.errors.append(err)

        self.reconstructions.append(trusted)
        return trusted

    def stats(self) -> Dict:
        if not self.errors:
            return {"n": 0, "mae": None, "rmse": None}
        e = np.array(self.errors)
        return {
            "n": int(len(e)),
            "mae": float(np.mean(e)),
            "rmse": float(np.sqrt(np.mean(e ** 2))),
        }
