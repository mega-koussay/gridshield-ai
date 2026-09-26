"""Orchestrator: the live control loop of GridShield AI.

Each tick performs:
  defender MPC setpoint -> twin step (+ attacker SCADA hijack if active) ->
  detection -> classification -> automated response -> trusted-data path
  (forecast on trusted history + reconstruction) -> KPI/event emission.

Two data planes are kept strictly apart:
  * RAW window      - exactly what the SCADA layer sees, attacks included.
  * TRUSTED window  - reconstructed values for isolated devices; AI models
                      (forecast, MPC, classifier context) run only on this.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from app.ai.anomaly import HybridDetector
from app.ai.classifier import AttackClassifier
from app.ai.explain import explain_step
from app.ai.forecast import LaggerRidgeForecaster
from app.ai.optimizer import optimize_horizon
from app.ai.reconstruction import ReconstructionEngine
from app.core.config import settings
from app.services.responder import Responder
from app.twin.attacks import ATTACK_TYPES, AttackSimulator
from app.twin.simulator import MicrogridSimulator

DEMO_PHASES = [
    "NORMAL", "ATTACK", "DETECTION", "EXPLANATION",
    "DEFENSE", "RECONSTRUCTION", "RE-OPTIMIZATION", "RECOVERY",
]

# Bump when detector/forecaster internals change so stale artifacts are
# retrained instead of loaded.
MODEL_VERSION = "v6"


class Orchestrator:
    def __init__(self) -> None:
        self.sim = MicrogridSimulator()
        self.attacks = AttackSimulator()
        self.detector = HybridDetector()
        self.clf = AttackClassifier()
        self.fc_solar = LaggerRidgeForecaster("solar")
        self.fc_load = LaggerRidgeForecaster("load")
        self.responder = Responder(self.sim)
        self.recon = ReconstructionEngine()
        self.window: Deque[dict] = deque(maxlen=240)
        self.trusted_window: Deque[dict] = deque(maxlen=240)
        self.events: Deque[dict] = deque(maxlen=500)
        self.df_window: Optional[pd.DataFrame] = None
        self.df_trusted: Optional[pd.DataFrame] = None
        self.mpc_plan: Optional[Dict] = None
        self.mpc_t: int = 0
        self.last_recon: Optional[Dict] = None
        self.last_payload: Optional[Dict] = None
        self.started_at = time.time()
        self.ticks = 0
        # Demo state
        self.demo_active = False
        self.demo_seed: Optional[int] = None
        self.demo_attack: Optional[object] = None
        self.demo_attack_step: Optional[int] = None
        self.demo_detected_step: Optional[int] = None
        self.demo_phase_idx = 0
        self.demo_log: List[Dict] = []
        self.detection_latency: Optional[int] = None
        self._contain_step: Optional[int] = None
        self._reopt_step: Optional[int] = None
        self._stable_since: Optional[int] = None
        self._clean_streak = 0
        self._recon_trajectory: Optional[Dict] = None
        self.last_explanation: Optional[Dict] = None
        self._load_models()

    # ------------------------------------------------------------------ #
    def _load_models(self) -> None:
        """Load saved artifacts; train from the labeled dataset if missing."""
        mdir = settings.models_dir
        f_solar = mdir / "forecaster_solar.joblib"
        f_load = mdir / "forecaster_load.joblib"
        f_det = mdir / "detector.joblib"
        f_clf = mdir / "classifier.joblib"
        df = self._load_dataset()
        if df is None:
            df = self._make_quick_dataset()
        try:
            if f_solar.exists() and f_load.exists() and f_det.exists() and f_clf.exists():
                ver_file = mdir / "VERSION.txt"
                if not ver_file.exists() or ver_file.read_text().strip() != MODEL_VERSION:
                    raise FileNotFoundError("artifact version mismatch")
                self.fc_solar = joblib.load(f_solar)
                self.fc_load = joblib.load(f_load)
                self.detector = joblib.load(f_det)
                self.clf = joblib.load(f_clf)
                self._log_event("SYSTEM", "Models loaded from artifacts.", "info")
                return
        except Exception as exc:  # corrupted artifacts -> retrain
            self._log_event("SYSTEM", f"Artifact load failed ({exc}); retraining.", "warn")
        clean = df[df["label"] == 0] if "label" in df.columns else df
        self.fc_solar.fit(clean, "metered_solar_kw")
        self.fc_load.fit(clean, "metered_load_kw")
        self.detector.fit_calibrate(clean)
        self.clf.fit(df)
        joblib.dump(self.fc_solar, f_solar)
        joblib.dump(self.fc_load, f_load)
        joblib.dump(self.detector, f_det)
        joblib.dump(self.clf, f_clf)
        (mdir / "VERSION.txt").write_text(MODEL_VERSION)
        self._log_event("SYSTEM", "Models trained and saved.", "info")

    def _load_dataset(self) -> Optional[pd.DataFrame]:
        p = settings.data_dir / "microgrid_dataset.csv"
        if p.exists():
            return pd.read_csv(p)
        return None

    def _make_quick_dataset(self, steps: int = 4000) -> pd.DataFrame:
        """Offline fallback: generate a clean + attacked dataset in-process."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
        from generate_dataset import generate  # type: ignore
        df = generate(steps, settings.seed)
        df.to_csv(settings.data_dir / "microgrid_dataset.csv", index=False)
        return df

    # ------------------------------------------------------------------ #
    def _log_event(self, kind: str, message: str, severity: str = "info", **extra) -> None:
        ev = {
            "ts": time.time(),
            "step_index": self.ticks,
            "kind": kind,
            "severity": severity,
            "message": message,
        }
        ev.update(extra)
        self.events.append(ev)

    # ------------------------------------------------------------------ #
    def reset(self, seed: Optional[int] = None) -> None:
        """Full deterministic reset of the live session."""
        self.sim.reset(seed=seed)
        self.attacks.clear()
        self.responder.reset()
        self.recon.reset()
        self.window.clear()
        self.trusted_window.clear()
        self.df_window = None
        self.df_trusted = None
        self.events.clear()
        self.mpc_plan = None
        self.last_recon = None
        self.demo_active = False
        self.demo_seed = None
        self.demo_attack = None
        self.demo_attack_step = None
        self.demo_detected_step = None
        self.demo_phase_idx = 0
        self.demo_log = []
        self.detection_latency = None
        self._contain_step = None
        self._reopt_step = None
        self._stable_since = None
        self._clean_streak = 0
        self._recon_trajectory = None
        self.last_explanation = None
        self.ticks = 0
        self.started_at = time.time()
        self._log_event("SYSTEM", f"Session reset (seed={seed if seed is not None else self.sim.seed}).", "info")
        # Warm the rolling windows so detectors/forecasts work immediately.
        # Battery held at its start SOC during warm-up so demos begin with a
        # healthy storage level; the grid covers the morning load.
        for _ in range(36):
            sd = self._raw_step(battery_setpoint=0.0)
            self._trusted_append(sd)

    # ------------------------------------------------------------------ #
    def _raw_step(self, battery_setpoint: Optional[float] = None) -> Dict:
        """One twin step + attack injection; appends RAW telemetry."""
        st = self.sim.step(battery_setpoint_kw=battery_setpoint)
        st2 = self.attacks.apply_to_state(st, current_step=st.step_index)
        sd = st2.to_dict()
        for k, v in sd.get("metered_building_loads", {}).items():
            sd[f"MB_{k}"] = v
        self.window.append(sd)
        self.df_window = pd.DataFrame(list(self.window))
        return sd

    def _trusted_append(self, sd: Dict, trusted: Optional[Dict] = None) -> None:
        """Append the current step to the TRUSTED window.

        `trusted` carries reconstructed values for isolated devices; without
        it the raw metered values are trusted as-is.
        """
        row = dict(sd)
        if trusted:
            row["metered_solar_kw"] = trusted["solar_kw"]
            row["metered_load_kw"] = trusted["load_kw"]
            for k in list(sd.get("metered_building_loads", {}).keys()):
                raw_total = sum(float(v) for v in sd["metered_building_loads"].values())
                if raw_total > 1.0:
                    share = float(sd["metered_building_loads"][k]) / raw_total
                    row[f"MB_{k}"] = share * trusted["load_kw"]
        self.trusted_window.append(row)
        self.df_trusted = pd.DataFrame(list(self.trusted_window))

    def _trusted_prev(self, sd: Dict) -> pd.DataFrame:
        """Trusted history + the current RAW row: the frame detectors and the
        classifier score. Past rows are trusted, the current row is exactly
        what SCADA sees right now."""
        rows = list(self.trusted_window)[:-1] if self.trusted_window else []
        rows = rows + [sd]
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    def _mpc_setpoint(self, force_resolve: bool = False) -> Optional[float]:
        """Defender battery setpoint: MPC over the TRUSTED window."""
        if self.df_trusted is None or len(self.df_trusted) < 8:
            return None
        if force_resolve or self.mpc_plan is None or self.mpc_t >= len(self.mpc_plan["power_kw"]):
            fc_solar = self.fc_solar.predict_from_history(
                self.df_trusted, "metered_solar_kw", settings.forecast_horizon_steps)
            fc_load = self.fc_load.predict_from_history(
                self.df_trusted, "metered_load_kw", settings.forecast_horizon_steps)
            self.mpc_plan = optimize_horizon(fc_load, fc_solar, self.sim.soc)
            self.mpc_t = 0
        p = float(self.mpc_plan["power_kw"][self.mpc_t])
        self.mpc_t += 1
        return float(np.clip(p, -settings.battery_power_kw, settings.battery_power_kw))

    def _forecast_now(self, horizon: int) -> tuple:
        """Forecasts for the CURRENT step from trusted history (fc[0] = now)."""
        if self.df_trusted is None or len(self.df_trusted) < 10:
            z = np.zeros(horizon)
            return z, z
        fc_solar = self.fc_solar.predict_from_history(
            self.df_trusted, "metered_solar_kw", horizon)
        fc_load = self.fc_load.predict_from_history(
            self.df_trusted, "metered_load_kw", horizon)
        return fc_load, fc_solar

    # ------------------------------------------------------------------ #
    def step(self) -> Dict:
        """One full live tick; returns the payload pushed to the dashboard."""
        self.ticks += 1
        isolated_now = any(d.isolated for d in self.sim.devices)
        # 1) DEFENDER control path: MPC over trusted data. While a device is
        # isolated, force a re-solve so the plan reflects reconstructed data.
        defender_setpoint = self._mpc_setpoint(force_resolve=isolated_now)
        # 2) If a SCADA_CMD attack is live, it hijacks the control path: the
        # twin physics receive the attacker's setpoint instead.
        sim_now = self.sim.step_index
        scada_active = any(
            a.active and a.attack_type == "SCADA_CMD"
            and a.start_step <= sim_now < a.start_step + a.duration_steps
            for a in self.attacks.active_attacks
        )
        actual_setpoint = defender_setpoint
        # Isolation at the network level revokes the attacker's control
        # session: while the compromised SCADA node is contained, its
        # commands never reach the plant.
        scada_blocked = any(d.isolated for d in self.sim.devices)
        if scada_active and not scada_blocked:
            override = self.attacks.pop_scada_command()
            if override is not None:
                actual_setpoint = float(override)
        sd = self._raw_step(battery_setpoint=actual_setpoint)

        # 3) detection + classification on (trusted history + current raw row)
        score_frame = self._trusted_prev(sd)
        det = self.detector.analyse(
            score_frame,
            expected_battery_kw=defender_setpoint,
        )
        clf = self.clf.predict(
            score_frame,
            float(det.signals.get("exp_load", sd["metered_load_kw"])),
            float(det.signals.get("exp_solar", sd["metered_solar_kw"])),
        )

        # 4) response chain
        explanation = None
        recon_info = None
        isolated = [d.device_id for d in self.sim.devices if d.isolated]
        if det.is_anomaly:
            self._clean_streak = 0
        else:
            self._clean_streak += 1
        if det.is_anomaly and not isolated:
            atk_type = clf["label"] if clf["label"] != "NONE" else "ANOMALY"
            dev = self.responder.attribute_device(atk_type, score_frame, score_frame.iloc[-1])
            inc = self.responder.open_incident(atk_type, dev, self.ticks, det.confidence)
            self.responder.contain(inc, self.ticks)
            isolated = [dev]
            self._contain_step = self.ticks
            self._log_event("DETECTION",
                            f"Anomaly score {det.score:.2f} >= {self.detector.threshold:.2f}: "
                            f"{atk_type} on {dev}",
                            "critical", confidence=det.confidence)
            if self.demo_active and self.demo_detected_step is None:
                self.demo_detected_step = det.step_index
                if self.demo_attack_step is not None:
                    self.detection_latency = max(1, det.step_index - self.demo_attack_step)
        elif det.is_anomaly and isolated:
            # Attack ongoing on contained segment; keep trusting reconstructions.
            for inc in self.responder.incidents:
                if inc.status == "contained":
                    inc.actions.append(
                        ResponseActionLight(self.ticks, "STILL_ANOMALOUS",
                                            f"Anomaly persists (score {det.score:.2f}); "
                                            f"{inc.device_id} stays isolated."))
        elif not det.is_anomaly and isolated and self._clean_streak >= 8:
            # Probation over: re-admit after sustained clean telemetry.
            for inc in self.responder.incidents:
                if inc.status == "contained":
                    self.responder.readmit(inc, self.ticks)
                    self._log_event("RESPONSE",
                                    f"{inc.device_id} restored to service after clean probation.",
                                    "info")
            isolated = [d.device_id for d in self.sim.devices if d.isolated]

        # 5) trusted data path: reconstruct the current step, then forecast
        # ahead. While isolated, fc_load/fc_solar come from the trajectory
        # frozen at containment so reconstructions never re-ingest themselves.
        if isolated:
            inc_type = next((i.attack_type for i in self.responder.incidents
                             if i.status in ("open", "contained")), "ANOMALY")
            if self._recon_trajectory is None:
                # Freeze a 2-hour trajectory at containment time.
                traj_len = int(120 / settings.step_minutes)
                fcl, fcs = self._forecast_now(traj_len)
                self._recon_trajectory = {
                    "load": list(map(float, fcl)),
                    "solar": list(map(float, fcs)),
                    "t": 0,
                }
            traj = self._recon_trajectory
            t = min(traj["t"], len(traj["load"]) - 1)
            recon_info = self.recon.reconstruct(
                sd, traj["load"][t], traj["solar"][t], isolated,
                attack_type=inc_type)
            traj["t"] += 1
            self.last_recon = recon_info
            self._trusted_append(sd, recon_info)
            if self._reopt_step is None or self.ticks - self._reopt_step >= 2:
                note = (f"Trusted values rebuilt from AI forecast "
                        f"(solar {recon_info['solar_kw']:.0f} kW, load {recon_info['load_kw']:.0f} kW); "
                        f"MPC re-solved on trusted data.")
                for inc in self.responder.incidents:
                    if inc.status in ("contained", "open"):
                        self.responder.log_optimization(inc, self.ticks, note)
                self._reopt_step = self.ticks
            explanation = explain_step(det, clf, score_frame,
                                       feature_rows=self.clf.importances,
                                       threshold=self.detector.threshold)
            explanation["reconstruction"] = {
                "replaced": recon_info["replaced"],
                "trusted_solar_kw": round(recon_info["solar_kw"], 1),
                "trusted_load_kw": round(recon_info["load_kw"], 1),
            }
            # Keep the most recent ALERT explanation (with its reasons); do
            # not overwrite it with the quiet probation frames.
            if det.is_anomaly or explanation["reasons"]:
                self.last_explanation = explanation
            fc_load, fc_solar = self._forecast_now(settings.forecast_horizon_steps)
        else:
            fc_load, fc_solar = self._forecast_now(settings.forecast_horizon_steps)
            self._trusted_append(sd)
            # Keep the most recent alert explanation visible after recovery
            # so the jury can review it during the demo.
            explanation = self.last_explanation

        # 6) demo phase machine
        if self.demo_active:
            self._advance_demo(det, isolated)

        # 7) build payload
        payload = self._build_payload(sd, det, clf, explanation, recon_info,
                                      fc_load, fc_solar, defender_setpoint)
        self.last_payload = payload
        return payload

    # ------------------------------------------------------------------ #
    def _advance_demo(self, det, isolated) -> None:
        # All demo timing runs on the twin clock (sim.step_index), the same
        # clock the attack scheduler uses.
        sim_now = self.sim.step_index
        if self.demo_phase_idx == 0 and self.demo_attack_step is not None \
                and sim_now >= self.demo_attack_step:
            self.demo_phase_idx = 1  # ATTACK live
            self._demo_note("ATTACK", "Controlled false-data injection launched.")
        if self.demo_phase_idx == 1 and self.demo_detected_step is not None:
            self.demo_phase_idx = 2
            self._demo_note("DETECTION",
                            f"AI detector fired after {self.detection_latency} step(s).")
            self.demo_phase_idx = 3
            self._demo_note("EXPLANATION", "Explanation generated for the alert.")
        if self.demo_phase_idx == 3 and self._contain_step is not None:
            self.demo_phase_idx = 4
            self._demo_note("DEFENSE", "Compromised device isolated automatically.")
            self.demo_phase_idx = 5
            self._demo_note("RECONSTRUCTION", "Trusted values reconstructed from AI forecast.")
        if self.demo_phase_idx == 5 and self._reopt_step is not None:
            self.demo_phase_idx = 6
            self._demo_note("RE-OPTIMIZATION", "Battery/load schedule re-optimized.")
        if self.demo_phase_idx == 6 and not isolated:
            self.demo_phase_idx = 7
            self._demo_note("RECOVERY", "Grid back to stable, trusted operation.")

    def _demo_note(self, phase: str, msg: str) -> None:
        self.demo_log.append({"phase": phase, "step_index": self.ticks, "message": msg})
        self._log_event("DEMO", msg, "info", phase=phase)

    # ------------------------------------------------------------------ #
    def launch_demo(self, seed: Optional[int] = None, attack_type: str = "FDI_BULK",
                    delay_min: int = 0, magnitude: Optional[float] = None) -> Dict:
        """Deterministic one-click scenario: reset, warm up, schedule attack."""
        self.reset(seed=seed)
        self.demo_active = True
        self.demo_seed = seed if seed is not None else settings.scenario_seed
        delay_steps = max(0, int(delay_min / settings.step_minutes))
        # Schedule the strike a few twin-steps after the warm-up so the jury
        # sees stable operation first. Twin clock: sim.step_index.
        self.demo_attack_step = self.sim.step_index + delay_steps + 6
        ev = self.attacks.launch(
            attack_type if attack_type in ATTACK_TYPES else "FDI_BULK",
            "MTR_B1_Offices" if attack_type in ("FDI_BULK", "DEVICE_MALWARE") else "MTR_SOLAR",
            duration_min=settings.attack_duration_min,
            magnitude=magnitude,
            current_step=self.demo_attack_step,
        )
        # Arm the episode at its scheduled step; apply_to_state skips it
        # until the twin reaches start_step.
        self._log_event("DEMO",
                        f"Demo scenario armed: {ev.attack_type} on {ev.device_id} "
                        f"at twin step {self.demo_attack_step}.",
                        "info")
        payload = self.step()
        return payload

    # ------------------------------------------------------------------ #
    def _build_payload(self, sd, det, clf, explanation, recon_info, fc_load, fc_solar, setpoint) -> Dict:
        devices = [d.to_dict() for d in self.sim.devices]
        sim_now = self.sim.step_index
        live = [
            a for a in self.attacks.active_attacks
            if a.start_step <= sim_now < a.start_step + a.duration_steps
        ]
        isolated_any = any(d.isolated for d in self.sim.devices)
        if live and not isolated_any:
            atk_status = "UNDER_ATTACK"
        elif live and isolated_any:
            atk_status = "CONTAINED"
        elif isolated_any:
            atk_status = "CONTAINED"
        elif self.responder.incidents and any(i.status == "recovered" for i in self.responder.incidents):
            atk_status = "RECOVERED"
        else:
            atk_status = "NORMAL"
        kpis = {
            "energy_balance_kw": round(sd["solar_kw"] - sd["load_kw"], 1),
            "soc": round(sd["soc"], 3),
            "anomaly_score": round(det.score, 3),
            "attack_status": atk_status,
            "unmet_load_kw": round(sd["unmet_load_kw"], 2),
            "blackout": sd["blackout"],
            "overload": sd["overload"],
            "detection_latency_steps": self.detection_latency,
            "recovery_steps": self.responder.last_recovery_steps,
            "reconstruction_mae": self.recon.stats()["mae"],
            "self_sufficiency": self._self_sufficiency(),
            "defender_setpoint_kw": round(setpoint, 1) if setpoint is not None else None,
            "control_hijacked": bool(
                sd["battery_kw"] != 0.0 and setpoint is not None
                and abs(sd["battery_kw"] - setpoint) > 0.05 * settings.battery_power_kw
            ),
        }
        demo = {
            "active": self.demo_active,
            "phase": DEMO_PHASES[min(self.demo_phase_idx, len(DEMO_PHASES) - 1)],
            "phases": DEMO_PHASES,
            "log": self.demo_log[-8:],
            "attack_scheduled_step": self.demo_attack_step,
            "seed": self.demo_seed,
        }
        return {
            "state": sd,
            "trusted": {
                "solar_kw": round(self.last_recon["solar_kw"], 1) if self.last_recon else round(sd["metered_solar_kw"], 1),
                "load_kw": round(self.last_recon["load_kw"], 1) if self.last_recon else round(sd["metered_load_kw"], 1),
                "replaced": self.last_recon["replaced"] if self.last_recon else [],
            },
            "forecast": {
                "load_kw": [round(float(x), 1) for x in fc_load],
                "solar_kw": [round(float(x), 1) for x in fc_solar],
                "horizon_min": settings.forecast_horizon_steps * settings.step_minutes,
            },
            "detection": det.to_dict(),
            "classification": clf,
            "explanation": explanation,
            "devices": devices,
            "attacks": self.attacks.status(),
            "incidents": self.responder.status(),
            "kpis": kpis,
            "demo": demo,
            "events": list(self.events)[-30:],
            "server_time": time.time(),
            "ticks": self.ticks,
        }

    def _self_sufficiency(self) -> float:
        """Share of demand served by solar+battery over the trusted window."""
        df = self.df_trusted
        if df is None or df.empty:
            return 1.0
        served = (df["solar_kw"] - df["grid_import_kw"]).clip(lower=0)
        denom = max(1e-6, df["load_kw"].sum())
        val = float(served.sum() / denom)
        return round(min(1.0, max(0.0, val)), 3)

    # ------------------------------------------------------------------ #
    def health(self) -> Dict:
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.version,
            "ticks": self.ticks,
            "uptime_s": round(time.time() - self.started_at, 1),
            "models": {
                "forecaster_solar": self.fc_solar.trained_steps > 0,
                "forecaster_load": self.fc_load.trained_steps > 0,
                "detector": self.detector.iforest is not None,
                "classifier": self.clf.model is not None,
            },
            "active_attacks": len([a for a in self.attacks.active_attacks if a.active]),
            "open_incidents": self.responder.status()["open_count"],
        }


class ResponseActionLight:
    """Lightweight action tuple for ongoing-attack notes (no dataclass import
    cycle): matches ResponseAction.to_dict()."""

    def __init__(self, step_index: int, action: str, detail: str) -> None:
        self.step_index = step_index
        self.action = action
        self.detail = detail

    def to_dict(self) -> dict:
        return {"step_index": self.step_index, "action": self.action, "detail": self.detail}


# Module-level singleton used by the API layer.
orchestrator = Orchestrator()
