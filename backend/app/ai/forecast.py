"""Short-horizon forecasting models (solar + demand).

Two Ridge-regression pipelines with periodic time features and short lags.
They are deliberately lightweight (<1 s training on a laptop) so the backend
can (re)train at startup if no saved artifact exists, and so the federated
simulation can train several local models per round in milliseconds.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from app.core.config import settings


def _time_features(minute_of_day: float, day_index: int) -> List[float]:
    h = minute_of_day / 60.0
    return [
        math.sin(2 * math.pi * h / 24.0),
        math.cos(2 * math.pi * h / 24.0),
        math.sin(4 * math.pi * h / 24.0),
        math.cos(4 * math.pi * h / 24.0),
        math.sin(2 * math.pi * day_index / 365.0),
        math.cos(2 * math.pi * day_index / 365.0),
    ]


def build_supervised(df: pd.DataFrame, target: str, lags: int = 3) -> pd.DataFrame:
    """Create a supervised frame with lags + rolling stats for `target`."""
    out = pd.DataFrame(index=df.index)
    out["minute_of_day"] = df["minute_of_day"]
    out["day_index"] = df["day_index"]
    for k in range(1, lags + 1):
        out[f"{target}_lag{k}"] = df[target].shift(k)
    out[f"{target}_roll3"] = df[target].shift(1).rolling(3).mean()
    out[f"{target}_roll6"] = df[target].shift(1).rolling(6).mean()
    if target == "metered_solar_kw":
        # Clear-sky proxy: helps the model separate weather from clock.
        out["cloud_factor"] = df["cloud_factor"]
    out["y"] = df[target]
    return out.dropna().reset_index(drop=True)


class LaggerRidgeForecaster:
    """Ridge on periodic time features + lags. One model per target."""

    def __init__(self, name: str, alpha: float = 1.0, lags: int = 3) -> None:
        self.name = name
        self.alpha = alpha
        self.lags = lags
        self.model = Ridge(alpha=alpha)
        self.scaler = StandardScaler()
        self.feature_names: List[str] = []
        self.trained_steps = 0

    # ------------------------------------------------------------------ #
    def fit(self, df: pd.DataFrame, target: str) -> "LaggerRidgeForecaster":
        sup = build_supervised(df, target, self.lags)
        y = sup["y"].to_numpy(dtype=float)
        time_feats = np.array(
            [_time_features(m, d) for m, d in zip(sup["minute_of_day"], sup["day_index"])]
        )
        lag_cols = [c for c in sup.columns if c not in ("y", "minute_of_day", "day_index")]
        X_lags = sup[lag_cols].to_numpy(dtype=float)
        X = np.hstack([time_feats, X_lags])
        self.feature_names = [f"time_{i}" for i in range(time_feats.shape[1])] + lag_cols
        Xs = self.scaler.fit_transform(X)
        self.model.fit(Xs, y)
        self.trained_steps = len(sup)
        return self

    # ------------------------------------------------------------------ #
    def predict_from_history(self, history: pd.DataFrame, target: str, horizon: int = 12) -> np.ndarray:
        """Recursive multi-step forecast from recent observations."""
        if not self.feature_names:
            raise RuntimeError(f"model {self.name} not fitted")
        vals = history[target].tolist()[-(self.lags + 6):]
        last = history.iloc[-1]
        mod = last["minute_of_day"]
        day = last["day_index"]
        preds: List[float] = []
        step_min = settings.step_minutes
        for _ in range(horizon):
            mod += step_min
            if mod >= 1440.0:
                mod -= 1440.0
                day += 1
            feats_lags = []
            for k in range(1, self.lags + 1):
                feats_lags.append(vals[-k])
            roll3 = float(np.mean(vals[-3:]))
            roll6 = float(np.mean(vals[-6:]))
            lag_row = feats_lags + [roll3, roll6]
            if target == "metered_solar_kw":
                lag_row.append(float(last.get("cloud_factor", 0.9)))
            tf = _time_features(mod, day)
            X = np.array(tf + lag_row, dtype=float).reshape(1, -1)
            Xs = self.scaler.transform(X)
            yhat = float(self.model.predict(Xs)[0])
            yhat = max(0.0, yhat)
            preds.append(yhat)
            vals.append(yhat)
        return np.array(preds)
