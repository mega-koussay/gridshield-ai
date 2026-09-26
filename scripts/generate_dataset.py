"""Generate the labeled GridShield AI dataset.

Produces a deterministic CSV of microgrid telemetry where some steps are
attacked (label column) with the attack type recorded. Clean and attacked
samples are kept in the same file but are clearly separated by the columns:

  label        0 = clean, 1 = attacked
  attack_type  "NONE" or one of the five threat classes
  attack_id    episode identifier or ""

Usage:
  python scripts/generate_dataset.py [--steps 6000] [--seed 20260925]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.twin.simulator import MicrogridSimulator  # noqa: E402
from app.twin.attacks import ATTACK_TYPES, AttackSimulator  # noqa: E402

# Public real-world data used ONLY for seasonal benchmarking (see report):
# NREL NSRDB-style irradiance is mimicked parametrically; no external download
# is required at runtime, keeping the PoC fully offline.
DATA_VERSION = "gridshield-synthetic-v1"


def generate(steps: int, seed: int, attack_rate: float = 0.06) -> pd.DataFrame:
    sim = MicrogridSimulator(seed=seed)
    atk = AttackSimulator(seed=seed + 1)
    rng = np.random.default_rng(seed + 2)

    rows = []
    active_label = 0
    active_type = "NONE"
    active_id = ""
    # Schedule attack episodes: each episode hits one random device/type.
    episode_starts = sorted(
        rng.choice(np.arange(200, steps - 40), size=int(steps * attack_rate / 6), replace=False)
    )

    ep_i = 0
    for i in range(steps):
        st = sim.step()
        lab, typ, aid = 0, "NONE", ""
        if ep_i < len(episode_starts) and i == episode_starts[ep_i]:
            t = ATTACK_TYPES[int(rng.integers(0, len(ATTACK_TYPES)))]
            dev = (
                f"MTR_{sim.devices[1 + int(rng.integers(0, settings.n_buildings))].device_id.replace('MTR_', '')}"
                if t in ("DEVICE_MALWARE",)
                else ("MTR_SOLAR" if t in ("FDI_SOLAR", "TELEMETRY_SPIKE") else "SCADA_ESS")
            )
            ev = atk.launch(
                t,
                dev,
                duration_min=int(rng.integers(15, 60)),
                magnitude=float(rng.uniform(0.25, 0.6)) if t != "TELEMETRY_SPIKE" else float(rng.uniform(1.5, 3.0)),
                current_step=st.step_index,
            )
            lab, typ, aid = 1, t, ev.attack_id
            active_label, active_type, active_id = lab, typ, aid
            ep_i += 1
        st = atk.apply_to_state(st)
        # Label every step of an active episode (not just its first).
        if atk.active_attacks:
            cur = atk.active_attacks[-1]
            lab, typ, aid = 1, cur.attack_type, cur.attack_id
        rows.append(
            {
                "step_index": st.step_index,
                "timestamp": st.timestamp,
                "minute_of_day": st.minute_of_day,
                "day_index": st.day_index,
                "solar_kw_true": st.solar_kw,
                "load_kw_true": st.load_kw,
                "battery_kw": st.battery_kw,
                "grid_import_kw": st.grid_import_kw,
                "grid_export_kw": st.grid_export_kw,
                "soc": st.soc,
                "cloud_factor": st.cloud_factor,
                "temperature_c": st.temperature_c,
                "metered_solar_kw": st.metered_solar_kw,
                "metered_load_kw": st.metered_load_kw,
                **{f"MB_{k}": v for k, v in st.metered_building_loads.items()},
                "label": lab,
                "attack_type": typ,
                "attack_id": aid,
            }
        )
    df = pd.DataFrame(rows)
    # Clean-up: after an episode ends, subsequent rows are clean again since
    # apply_to_state only corrupts while the episode is active.
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate GridShield AI dataset")
    ap.add_argument("--steps", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=settings.seed)
    ap.add_argument("--out", type=str, default=str(ROOT / "backend" / "data" / "microgrid_dataset.csv"))
    args = ap.parse_args()

    df = generate(args.steps, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    attacked = int(df["label"].sum())
    print(f"dataset: {len(df)} rows -> {out}")
    print(f"attacked rows: {attacked} ({attacked/len(df)*100:.1f}%)")
    print(df.groupby("attack_type").size().to_string())


if __name__ == "__main__":
    main()
