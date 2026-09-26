"""GridShield AI configuration.

All simulation behaviour is deterministic: a single seed drives the synthetic
microgrid generator, the AI models and the demo scenario so that a run can be
reproduced exactly on any laptop.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repository root (search upwards from this file).
_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / ".env.local", override=False)


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


class Settings:
    """Simple settings object (pydantic-free to keep deps light)."""

    def __init__(self) -> None:
        self.app_name: str = "GridShield AI"
        self.version: str = "1.0.0"
        self.tagline: str = "Predict. Protect. Optimize."

        # ---- Server ----
        self.host: str = _env("GRIDSHIELD_HOST", "127.0.0.1")
        self.port: int = _env_int("GRIDSHIELD_PORT", 8000)
        self.log_level: str = _env("GRIDSHIELD_LOG_LEVEL", "info")

        # ---- Determinism ----
        self.seed: int = _env_int("GRIDSHIELD_SEED", 20260925)

        # ---- Simulation clock ----
        self.tick_seconds: float = _env_float("GRIDSHIELD_TICK_SECONDS", 1.0)
        self.step_minutes: int = _env_int("GRIDSHIELD_STEP_MINUTES", 5)
        # 1 simulated hour of microgrid time per real second at default tick.
        self.minutes_per_real_second: float = _env_float(
            "GRIDSHIELD_MINUTES_PER_REAL_SECOND", 60.0
        )

        # ---- Microgrid sizing ----
        self.solar_capacity_kw: float = _env_float("GRIDSHIELD_SOLAR_KW", 250.0)
        self.battery_capacity_kwh: float = _env_float("GRIDSHIELD_BATTERY_KWH", 500.0)
        self.battery_power_kw: float = _env_float("GRIDSHIELD_BATTERY_KW", 200.0)
        self.battery_eta: float = _env_float("GRIDSHIELD_BATTERY_ETA", 0.95)
        self.battery_soc_min: float = _env_float("GRIDSHIELD_SOC_MIN", 0.10)
        self.battery_soc_max: float = _env_float("GRIDSHIELD_SOC_MAX", 0.90)
        self.grid_import_limit_kw: float = _env_float("GRIDSHIELD_GRID_LIMIT_KW", 400.0)
        self.grid_export_limit_kw: float = _env_float("GRIDSHIELD_EXPORT_LIMIT_KW", 150.0)

        # ---- Devices / loads ----
        self.n_buildings: int = _env_int("GRIDSHIELD_BUILDINGS", 6)

        # ---- Scenario / demo ----
        self.scenario_seed: int = _env_int("GRIDSHIELD_SCENARIO_SEED", 2026)
        self.attack_start_minute: int = _env_int("GRIDSHIELD_ATTACK_START_MIN", 180)
        self.attack_duration_min: int = _env_int("GRIDSHIELD_ATTACK_DURATION_MIN", 30)

        # ---- AI ----
        self.anomaly_z_threshold: float = _env_float("GRIDSHIELD_ANOMALY_Z", 4.0)
        self.iforest_trees: int = _env_int("GRIDSHIELD_IFOREST_TREES", 150)
        self.forecast_horizon_steps: int = _env_int("GRIDSHIELD_HORIZON", 12)
        self.models_dir: Path = Path(_env("GRIDSHIELD_MODELS_DIR", str(_ROOT / "backend" / "models")))
        self.data_dir: Path = Path(_env("GRIDSHIELD_DATA_DIR", str(_ROOT / "backend" / "data")))
        self.reports_dir: Path = Path(_env("GRIDSHIELD_REPORTS_DIR", str(_ROOT / "backend" / "reports")))

        # ---- Storage ----
        self.db_path: Path = Path(_env("GRIDSHIELD_DB", str(_ROOT / "backend" / "gridshield.db")))

        # ---- Federated learning ----
        self.fl_rounds: int = _env_int("GRIDSHIELD_FL_ROUNDS", 8)
        self.fl_participants: int = _env_int("GRIDSHIELD_FL_PARTICIPANTS", 6)

        self.ensure_dirs()

    def ensure_dirs(self) -> None:
        for p in (self.models_dir, self.data_dir, self.reports_dir):
            p.mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict:
        return {
            "app_name": self.app_name,
            "version": self.version,
            "seed": self.seed,
            "tick_seconds": self.tick_seconds,
            "step_minutes": self.step_minutes,
            "solar_capacity_kw": self.solar_capacity_kw,
            "battery_capacity_kwh": self.battery_capacity_kwh,
            "battery_power_kw": self.battery_power_kw,
            "n_buildings": self.n_buildings,
            "scenario_seed": self.scenario_seed,
            "db_path": str(self.db_path),
        }


settings = Settings()
