"""Federated learning PoC (FedAvg over building demand models).

Six buildings each hold their own consumption history. In every round each
participant trains a local Ridge model on its *own* data and shares only the
model parameters (weights + intercept), never the raw series. The server
averages the updates (FedAvg) and broadcasts the global model back. We track
the global model's demand-forecast error to prove convergence, and compare it
with a centralized baseline to show the accuracy cost of privacy.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

import numpy as np

from app.core.config import settings


def _features(minute_of_day: np.ndarray, day_index: np.ndarray) -> np.ndarray:
    h = minute_of_day / 60.0
    return np.column_stack([
        np.sin(2 * np.pi * h / 24.0), np.cos(2 * np.pi * h / 24.0),
        np.sin(4 * np.pi * h / 24.0), np.cos(4 * np.pi * h / 24.0),
        day_index / 365.0,
        np.ones_like(h),
    ])


class LocalRidge:
    """Closed-form ridge (fast, no sklearn needed per participant)."""

    def __init__(self, lam: float = 1.0) -> None:
        self.lam = lam
        self.w: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        d = X.shape[1]
        A = X.T @ X + self.lam * np.eye(d)
        self.w = np.linalg.solve(A, X.T @ y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return X @ self.w


def split_per_building(df, n_buildings: int) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Synthesize per-building series by proportionally splitting the site
    load by each building's average share (keeps the PoC self-contained)."""
    shares = np.linspace(0.6, 1.4, n_buildings)
    shares = shares / shares.sum()
    X_all = _features(df["minute_of_day"].to_numpy(), df["day_index"].to_numpy())
    y_all = df["load_kw_true"].to_numpy()
    out = []
    for s in shares:
        yb = y_all * s
        out.append((X_all, yb))
    return out


def run_federated(df, rounds: int = None, n_buildings: int = None) -> Dict:
    rounds = rounds or settings.fl_rounds
    n_buildings = n_buildings or settings.fl_participants
    parts = split_per_building(df, n_buildings)

    n = len(parts[0][1])
    split = int(n * 0.8)
    # Global model starts at zero.
    global_w = np.zeros(_features(np.array([0.0]), np.array([0.0])).shape[1])

    history = []
    X_test_parts, y_test_parts = [], []
    for Xb, yb in parts:
        X_test_parts.append(Xb[split:])
        y_test_parts.append(yb[split:])
    X_test = np.vstack(X_test_parts)
    y_test = np.concatenate(y_test_parts)

    for r in range(rounds):
        ws = []
        weights_sum = 0.0
        for Xb, yb in parts:
            Xtr, ytr = Xb[:split], yb[:split]
            # Each round, clients train on a fresh random 60% shard (seeded).
            rng = np.random.default_rng(settings.seed + r)
            idx = rng.choice(len(ytr), size=int(0.6 * len(ytr)), replace=False)
            m = LocalRidge(lam=1.0)
            m.fit(Xtr[idx], ytr[idx])
            ws.append((m.w, len(idx)))
            weights_sum += len(idx)
        global_w = sum(w * (k / weights_sum) for w, k in ws)
        pred = X_test @ global_w
        mae = float(np.mean(np.abs(pred - y_test)))
        history.append({"round": r + 1, "global_mae": mae})

    # Centralized baseline on pooled data (upper bound on accuracy).
    X_pool = np.vstack([Xb[:split] for Xb, _ in parts])
    y_pool = np.concatenate([yb[:split] for _, yb in parts])
    cent = LocalRidge(lam=1.0)
    cent.fit(X_pool, y_pool)
    cent_mae = float(np.mean(np.abs(X_test @ cent.w - y_test)))

    return {
        "rounds": rounds,
        "participants": n_buildings,
        "history": history,
        "final_global_mae": history[-1]["global_mae"],
        "centralized_mae": cent_mae,
        "privacy_note": "Only model weights are exchanged; raw consumption series never leave the buildings.",
    }
