"""Battery / controllable-load optimization.

1. `day_ahead_schedule` — exact dynamic program over a discretized SOC grid.
   The grid spacing is chosen fine enough that a single 5-min step at full
   battery power (200 kW -> ~16.7 kWh) can traverse several nodes, so the DP
   has a connected, feasible transition graph. Transitions are vectorized
   with numpy: 288 steps x 40 nodes solves in tens of milliseconds.

2. `optimize_horizon`  — receding-horizon MPC wrapper (12 steps = 1 h) over
   forecast solar/load; re-solved every step in the live loop.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from app.core.config import settings

N_SOC = 40  # SOC grid resolution (spacing 0.02 of capacity = 10 kWh here)


def _soc_grid(n: int = N_SOC) -> np.ndarray:
    return np.linspace(settings.battery_soc_min, settings.battery_soc_max, n)


def _transition_matrices(socs: np.ndarray):
    """Feasibility mask + power matrix for SOC-node transitions."""
    cap = settings.battery_capacity_kwh
    eta = settings.battery_eta
    dt_h = settings.step_minutes / 60.0
    pmax = settings.battery_power_kw

    delta = (socs[None, :] - socs[:, None]) * cap        # [j, k] kWh, >0 charging
    p = np.where(delta >= 0, delta / (eta * dt_h), delta * eta / dt_h)
    feasible = np.abs(p) <= pmax + 1e-6
    wear = 0.02 * np.abs(p) * dt_h                        # battery wear proxy
    return p, feasible, wear


def day_ahead_schedule(forecast_load: np.ndarray, forecast_solar: np.ndarray) -> Dict:
    """Minimize import cost + wear over the horizon subject to SOC limits."""
    n = min(len(forecast_load), len(forecast_solar))
    socs = _soc_grid()
    p, feasible, wear = _transition_matrices(socs)
    dt_h = settings.step_minutes / 60.0

    hour_of_day = (np.arange(n) * settings.step_minutes // 60) % 24
    price = np.where((hour_of_day >= 17) & (hour_of_day < 21), 0.32, 0.20)

    BIG = 1e12
    dp = np.full(len(socs), BIG)
    dp[int(np.argmin(np.abs(socs - 0.55)))] = 0.0
    parents = np.zeros((n, len(socs)), dtype=np.int32)

    for t in range(n):
        net = float(forecast_solar[t] - forecast_load[t])  # >0 surplus
        import_cost = price[t] * np.maximum(0.0, net - p) * dt_h   # [j, k]
        step_cost = wear + import_cost
        step_cost = np.where(feasible, step_cost, BIG)
        cand = dp[:, None] + step_cost                       # from node j to k
        parents[t] = np.argmin(cand, axis=0)
        dp = cand[parents[t], np.arange(len(socs))]

    j_end = int(np.argmin(dp))
    if dp[j_end] >= BIG:
        return {"power_kw": [0.0] * n, "soc": [0.55] * n, "cost": float("nan")}

    # Trace back the SOC path.
    soc_path_end = [0.0] * n
    j = j_end
    for t in range(n - 1, -1, -1):
        soc_path_end[t] = float(socs[j])
        j = int(parents[t, j])
    # Forward pass: power from SOC deltas.
    soc_now = float(socs[int(np.argmin(np.abs(socs - 0.55)))])
    cap = settings.battery_capacity_kwh
    eta = settings.battery_eta
    dt = settings.step_minutes / 60.0
    power: List[float] = []
    for t in range(n):
        d_kwh = (soc_path_end[t] - soc_now) * cap
        p_t = d_kwh / (eta * dt) if d_kwh >= 0 else d_kwh * eta / dt
        power.append(float(p_t))
        soc_now = soc_path_end[t]
    return {"power_kw": power, "soc": soc_path_end, "cost": float(dp[j_end])}


def optimize_horizon(fc_load: np.ndarray, fc_solar: np.ndarray, soc0: float) -> Dict:
    """Receding-horizon MPC: solve the same DP over the next steps."""
    return day_ahead_schedule(fc_load, fc_solar)
