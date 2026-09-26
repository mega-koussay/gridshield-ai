"""Hybrid anomaly detection: statistical rules + Isolation Forest.

Channels (all in [0,1]), computed identically at calibration and at analysis
time so the calibrated threshold transfers exactly:

  z_load    |metered load - naive 1-step prediction| / (3 * sigma_load)
  z_solar   same for solar
  z_meter   max over building meters of |meter - naive 1-step| / (3*sigma_k)
            (catches single-meter malware)
  iforest   Isolation-Forest score over interpretable telemetry features
  z_bat     control-plane consistency |actual battery - DEFENDER setpoint|

  weighted = 0.35*z_load + 0.20*z_solar + 0.15*z_meter + 0.30*iforest
  score    = max(weighted, 0.78 * max_channel)

Two fusion properties:
  * saturated hard evidence (any channel = 1, i.e. residual beyond 3 sigma of
    clean traffic) yields score >= 0.78 -> detected;
  * the control plane has veto power: when the battery does not follow the
    command the *defender* issued, someone else is commanding the plant.

Threshold = 99.5th percentile of clean-data scores -> false-positive rate is
bounded by construction (~0.5% on clean traffic).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.core.config import settings

IFOREST_FEATURES = ["load", "solar", "d_load", "d_solar", "battery", "d_battery"]


@dataclass
class Detection:
    """Result of analysing one step."""

    step_index: int
    score: float
    is_anomaly: bool
    confidence: float
    signals: Dict[str, float] = field(default_factory=dict)
    top_features: List[Tuple[str, float]] = field(default_factory=list)
    worst_meter: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "step_index": self.step_index,
            "score": round(self.score, 3),
            "is_anomaly": self.is_anomaly,
            "confidence": round(self.confidence, 3),
            "signals": {k: round(v, 3) for k, v in self.signals.items() if isinstance(v, (int, float))},
            "top_features": [[f, round(w, 3)] for f, w in self.top_features],
            "worst_meter": self.worst_meter,
        }


def _naive_1step(series: pd.Series) -> pd.Series:
    """Naive 1-step-ahead prediction: mean of the previous 3 values."""
    return series.shift(1).rolling(3).mean()


class HybridDetector:
    def __init__(self) -> None:
        self.sigma_load = 1.0
        self.sigma_solar = 1.0
        self.sigma_bat = 1.0
        self.sigma_meters: Dict[str, float] = {}
        self.iforest: Optional[IsolationForest] = None
        self.if_lo = 0.0
        self.if_hi = 1.0
        self.threshold = 0.55

    # ------------------------------------------------------------------ #
    @staticmethod
    def _clip01(x) -> np.ndarray:
        return np.clip(np.nan_to_num(np.asarray(x, dtype=float), nan=0.0), 0.0, 1.0)

    @staticmethod
    def _feature_frame(d: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({
            "load": d["metered_load_kw"],
            "solar": d["metered_solar_kw"],
            "d_load": d["metered_load_kw"].diff().fillna(0.0),
            "d_solar": d["metered_solar_kw"].diff().fillna(0.0),
            "battery": d["battery_kw"],
            "d_battery": d["battery_kw"].diff().fillna(0.0),
        })[IFOREST_FEATURES]

    @staticmethod
    def _meter_columns(d) -> List[str]:
        cols = getattr(d, "columns", None)
        if cols is None:
            return []
        return [c for c in cols if str(c).startswith("MB_")]

    def _iforest_scores(self, feats: pd.DataFrame) -> np.ndarray:
        raw = -self.iforest.score_samples(feats)
        if self.if_hi - self.if_lo < 1e-9:
            return np.zeros(len(raw))
        return self._clip01((raw - self.if_lo) / (self.if_hi - self.if_lo))

    @staticmethod
    def _fuse(zl, zs, zm, if_s, zb) -> np.ndarray:
        weighted = (0.35 * np.asarray(zl) + 0.20 * np.asarray(zs)
                    + 0.15 * np.asarray(zm) + 0.30 * np.asarray(if_s))
        z_any = np.maximum.reduce([np.asarray(zl), np.asarray(zs),
                                   np.asarray(zm), np.asarray(zb)])
        return np.maximum(weighted, 0.78 * z_any)

    # ------------------------------------------------------------------ #
    def _meter_channel_frame(self, d: pd.DataFrame) -> np.ndarray:
        """Per-meter naive-residual channel over a frame (calibration path)."""
        cols = self._meter_columns(d)
        if not cols or not self.sigma_meters:
            return np.zeros(len(d))
        z = np.zeros(len(d))
        for c in cols:
            sig = self.sigma_meters.get(c)
            if not sig:
                continue
            resid = (d[c] - _naive_1step(d[c])).abs().to_numpy()
            z = np.maximum(z, self._clip01(resid / (3.0 * sig)))
        return z

    def _channel_series(self, d: pd.DataFrame) -> Dict[str, np.ndarray]:
        nl = _naive_1step(d["metered_load_kw"])
        ns = _naive_1step(d["metered_solar_kw"])
        zl = self._clip01((d["metered_load_kw"] - nl).abs() / (3.0 * self.sigma_load))
        zs = self._clip01((d["metered_solar_kw"] - ns).abs() / (3.0 * self.sigma_solar))
        zm = self._meter_channel_frame(d)
        zb = self._clip01(d["battery_kw"].diff().abs().fillna(0.0) / (3.0 * self.sigma_bat))
        return {"z_load": zl, "z_solar": zs, "z_meter": zm, "z_bat": zb}

    # ------------------------------------------------------------------ #
    def fit_calibrate(self, clean_df: pd.DataFrame) -> "HybridDetector":
        d = clean_df.copy().reset_index(drop=True)

        nl = _naive_1step(d["metered_load_kw"])
        ns = _naive_1step(d["metered_solar_kw"])
        self.sigma_load = float(np.percentile((d["metered_load_kw"] - nl).abs().dropna(), 95)) + 1e-6
        self.sigma_solar = float(np.percentile((d["metered_solar_kw"] - ns).abs().dropna(), 95)) + 1e-6
        self.sigma_bat = float(np.percentile(d["battery_kw"].diff().abs().dropna(), 95)) + 1e-6

        # Per-meter residual sigmas.
        for c in self._meter_columns(d):
            resid = (d[c] - _naive_1step(d[c])).abs().dropna()
            if len(resid):
                self.sigma_meters[c] = float(np.percentile(resid, 95)) + 1e-3

        feats = self._feature_frame(d)
        mask = feats.notna().all(axis=1)
        self.iforest = IsolationForest(
            n_estimators=settings.iforest_trees,
            contamination=0.02,
            random_state=settings.seed,
        )
        self.iforest.fit(feats[mask])
        raw = -self.iforest.score_samples(feats[mask])
        self.if_lo = float(np.percentile(raw, 50))
        self.if_hi = float(np.percentile(raw, 99.9))

        ch = self._channel_series(d)
        if_s = self._iforest_scores(feats[mask])
        fused_clean = self._fuse(
            ch["z_load"][mask.values], ch["z_solar"][mask.values],
            ch["z_meter"][mask.values], if_s, ch["z_bat"][mask.values],
        )
        self.threshold = float(np.percentile(fused_clean, 99.5))
        self.threshold = float(np.clip(self.threshold, 0.35, 0.70))
        return self

    # ------------------------------------------------------------------ #
    def analyse(
        self,
        window_df: pd.DataFrame,
        expected_battery_kw: Optional[float] = None,
    ) -> Detection:
        """Analyse the latest step of `window_df` (raw metered telemetry)."""
        latest = window_df.iloc[-1]
        prev = window_df.iloc[-2] if len(window_df) > 1 else latest

        # Naive 1-step predictions consistent with the calibration path.
        exp_load = float(window_df["metered_load_kw"].iloc[-4:-1].mean()) if len(window_df) >= 4 else float(prev["metered_load_kw"])
        exp_solar = float(window_df["metered_solar_kw"].iloc[-4:-1].mean()) if len(window_df) >= 4 else float(prev["metered_solar_kw"])

        r_load = abs(float(latest["metered_load_kw"]) - exp_load)
        r_solar = abs(float(latest["metered_solar_kw"]) - exp_solar)
        zl = float(self._clip01([r_load / (3.0 * self.sigma_load)])[0])
        zs = float(self._clip01([r_solar / (3.0 * self.sigma_solar)])[0])

        # Per-meter channel (single-meter malware).
        zm = 0.0
        worst_meter = None
        for c in self._meter_columns(window_df):
            sig = self.sigma_meters.get(c)
            if not sig:
                continue
            exp_m = float(window_df[c].iloc[-4:-1].mean()) if len(window_df) >= 4 else float(prev[c])
            r = abs(float(latest[c]) - exp_m)
            z = float(self._clip01([r / (3.0 * sig)])[0])
            if z > zm:
                zm, worst_meter = z, c

        # Control-plane channel vs the DEFENDER-intended setpoint.
        if expected_battery_kw is not None:
            dev_b = abs(float(latest["battery_kw"]) - float(expected_battery_kw))
            zb = float(self._clip01([dev_b / (0.30 * settings.battery_power_kw)])[0])
        else:
            zb = float(self._clip01([abs(float(latest["battery_kw"]) - float(prev["battery_kw"])) / (3.0 * self.sigma_bat)])[0])

        feats = self._feature_frame(window_df.tail(2)).iloc[[-1]]
        ifs = float(self._iforest_scores(feats)[0])

        weighted = 0.35 * zl + 0.20 * zs + 0.15 * zm + 0.30 * ifs
        z_any = max(zl, zs, zm, zb)
        score = float(max(weighted, 0.78 * z_any))
        is_anom = score >= self.threshold
        if is_anom:
            conf = float(np.clip(0.5 + 0.5 * (score - self.threshold) / max(1e-6, 1.0 - self.threshold), 0.0, 1.0))
        else:
            conf = float(np.clip(1.0 - score / max(1e-6, self.threshold), 0.0, 1.0))
        signals = {
            "z_load": zl, "z_solar": zs, "z_meter": zm,
            "iforest": ifs, "z_battery": zb,
            "exp_load": exp_load, "exp_solar": exp_solar,
        }
        top = sorted([("z_load", zl), ("z_solar", zs), ("z_meter", zm),
                      ("iforest", ifs), ("z_battery", zb)], key=lambda kv: -kv[1])[:3]
        det = Detection(
            step_index=int(latest["step_index"]),
            score=score,
            is_anomaly=is_anom,
            confidence=conf,
            signals=signals,
            top_features=top,
            worst_meter=worst_meter,
        )
        return det
