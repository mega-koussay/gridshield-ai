"""Attack-type identification.

A small RandomForest over interpretable telemetry features classifies each
step into NONE / FDI_BULK / FDI_SOLAR / SCADA_CMD / DEVICE_MALWARE /
TELEMETRY_SPIKE and returns class probabilities used by the explainability
layer. Trained on the labeled generated dataset.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from app.core.config import settings

CLASSES = ["NONE", "FDI_BULK", "FDI_SOLAR", "SCADA_CMD", "DEVICE_MALWARE", "TELEMETRY_SPIKE"]

FEATURES = [
    "load_resid_ratio",   # |metered_load - pred| / metered_load
    "solar_resid_ratio",  # |metered_solar - pred| / max(metered_solar, 1)
    "d_load",             # first diff of metered load
    "d_solar",            # first diff of metered solar
    "d_battery",          # first diff of battery power (SCADA abuse)
    "battery_extreme",    # battery at/beyond power rating (hijack sign)
    "meter_split",        # max |per-meter residual| / site load
    "load_to_solar",      # ratio feature
    "solar_share_jump",   # solar jump vs capacity
]


def make_features(df: pd.DataFrame, pred_load=None, pred_solar=None) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    pl = pred_load if pred_load is not None else df["metered_load_kw"].shift(1).rolling(3).mean()
    ps = pred_solar if pred_solar is not None else df["metered_solar_kw"].shift(1).rolling(3).mean()
    f["load_resid_ratio"] = ((df["metered_load_kw"] - pl) / df["metered_load_kw"].clip(lower=1.0)).fillna(0.0)
    f["solar_resid_ratio"] = ((df["metered_solar_kw"] - ps) / df["metered_solar_kw"].clip(lower=1.0)).fillna(0.0)
    f["d_load"] = df["metered_load_kw"].diff().fillna(0.0)
    f["d_solar"] = df["metered_solar_kw"].diff().fillna(0.0)
    f["d_battery"] = df["battery_kw"].diff().fillna(0.0) if "battery_kw" in df.columns else 0.0
    pmax = settings.battery_power_kw
    if "battery_kw" in df.columns:
        f["battery_extreme"] = (
            (df["battery_kw"].abs() >= 0.95 * pmax)
            & (df["battery_kw"].diff().abs() > 0.3 * pmax)
        ).astype(float)
    else:
        f["battery_extreme"] = 0.0
    mb_cols = [c for c in df.columns if c.startswith("MB_")]
    if mb_cols:
        tot = df[mb_cols].sum(axis=1).clip(lower=1.0)
        prev = df[mb_cols].shift(1)
        prev_tot = prev.sum(axis=1).clip(lower=1.0)
        share_now = df[mb_cols].div(tot, axis=0)
        share_prev = prev.div(prev_tot, axis=0)
        f["meter_split"] = (share_now - share_prev).abs().max(axis=1).fillna(0.0)
    else:
        f["meter_split"] = 0.0
    f["load_to_solar"] = (df["metered_load_kw"] / df["metered_solar_kw"].clip(lower=5.0)).fillna(0.0)
    f["solar_share_jump"] = (df["metered_solar_kw"].diff().fillna(0.0) / settings.solar_capacity_kw).clip(-1, 3)
    return f[FEATURES]


class AttackClassifier:
    def __init__(self) -> None:
        self.model: Optional[RandomForestClassifier] = None
        self.importances: Dict[str, float] = {}

    def fit(self, df: pd.DataFrame) -> "AttackClassifier":
        X = make_features(df)
        y = df["attack_type"].where(df["attack_type"].isin(CLASSES), "NONE")
        mask = X.notna().all(axis=1)
        self.model = RandomForestClassifier(
            n_estimators=180, max_depth=12, min_samples_leaf=3,
            class_weight="balanced", random_state=settings.seed, n_jobs=-1,
        )
        self.model.fit(X[mask], y[mask])
        self.importances = dict(zip(FEATURES, self.model.feature_importances_.round(3)))
        return self

    def predict(self, window_df: pd.DataFrame, pred_load: float, pred_solar: float) -> Dict:
        f = make_features(window_df.tail(3), pred_load=np.full(len(window_df.tail(3)), pred_load),
                          pred_solar=np.full(len(window_df.tail(3)), pred_solar))
        X = f.iloc[[-1]]
        proba = self.model.predict_proba(X)[0]
        classes = list(self.model.classes_)
        ranked = sorted(zip(classes, proba), key=lambda kv: -kv[1])
        return {
            "label": ranked[0][0],
            "confidence": float(ranked[0][1]),
            "probs": {c: float(p) for c, p in ranked[:4]},
        }
