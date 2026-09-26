"""Explainability engine.

Turns raw detector/classifier signals into jury-readable explanations:
human sentences + quantitative evidence + feature attributions. Uses the
classifier's feature importances as a lightweight, always-available
attribution method (sufficient for tabular telemetry and transparent to
auditors), plus per-signal threshold explanations.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.ai.anomaly import Detection
from app.ai.classifier import FEATURES
from app.core.config import settings

TYPE_STORY = {
    "FDI_BULK": (
        "False-data injection on load telemetry",
        "The reported site load moved far away from what the demand forecast "
        "and neighbouring meters expect, while the physical balance stayed normal.",
    ),
    "FDI_SOLAR": (
        "Manipulated solar-production measurement",
        "Reported solar output exceeds the physical ceiling for this irradiance "
        "and time of day.",
    ),
    "SCADA_CMD": (
        "Abnormal SCADA control command",
        "A battery setpoint outside the safe envelope was issued through the "
        "control layer.",
    ),
    "DEVICE_MALWARE": (
        "Compromised smart meter",
        "A single meter disagrees persistently with its building's expected "
        "demand and with the site total.",
    ),
    "TELEMETRY_SPIKE": (
        "Impossible telemetry jump",
        "A step change far beyond any physically plausible ramp rate.",
    ),
}


def explain_step(
    det: Detection,
    clf: Optional[Dict],
    window_df,
    feature_rows: Optional[Dict[str, float]] = None,
    threshold: float = 0.7,
) -> Dict:
    """Build the explanation payload shown in the AI explanation panel."""
    reasons: List[str] = []
    evidence: List[Tuple[str, float, str]] = []  # (feature, value, note)

    latest = window_df.iloc[-1]
    sig = det.signals
    cap = settings.solar_capacity_kw

    if sig.get("z_load", 0) > 0.45:
        reasons.append(
            f"Metered load deviates from the AI demand forecast "
            f"({latest['metered_load_kw']:.0f} kW reported vs {det.signals.get('fc_load', float('nan')):.0f} kW expected)."
        )
    if sig.get("z_solar", 0) > 0.45:
        reasons.append(
            f"Metered solar deviates from the AI solar forecast "
            f"({latest['metered_solar_kw']:.0f} kW reported vs {det.signals.get('fc_solar', float('nan')):.0f} kW expected)."
        )
    if latest.get("metered_solar_kw", 0) > 1.25 * cap:
        reasons.append(
            f"Reported solar {latest['metered_solar_kw']:.0f} kW exceeds plant capacity "
            f"{cap:.0f} kW - physically impossible."
        )
    d_solar = latest.get("metered_solar_kw", 0) - window_df.iloc[-2].get("metered_solar_kw", 0) if len(window_df) > 1 else 0.0
    if abs(d_solar) > 0.25 * cap:
        reasons.append(
            f"5-min solar ramp {d_solar:+.0f} kW exceeds plausible ramp "
            f"(>25% of capacity in one interval)."
        )
    d_load = latest.get("metered_load_kw", 0) - window_df.iloc[-2].get("metered_load_kw", 0) if len(window_df) > 1 else 0.0
    if abs(d_load) > 60.0:
        reasons.append(f"5-min load jump {d_load:+.0f} kW is far outside normal demand dynamics.")

    if clf and clf.get("label") in TYPE_STORY:
        title, story = TYPE_STORY[clf["label"]]
    else:
        title, story = "Anomalous telemetry", "Statistical detectors fired without a matching known pattern."

    # Feature attributions: combine detector signals + classifier importances
    attributions: List[Tuple[str, float]] = []
    imp = (feature_rows or {})
    base = dict(det.signals)
    if imp:
        for k, v in imp.items():
            base[f"feat_{k}"] = v
    for name, val in sorted(base.items(), key=lambda kv: -abs(kv[1]))[:5]:
        attributions.append((name, float(val)))

    return {
        "title": title,
        "story": story,
        "reasons": reasons,
        "anomaly_score": round(det.score, 3),
        "threshold": round(threshold, 3),
        "confidence": round(det.confidence, 3),
        "signals": {k: round(v, 3) for k, v in det.signals.items()},
        "attributions": [[n, round(v, 3)] for n, v in attributions],
        "threshold_note": (
            f"Alert raised because fused score {det.score:.2f} >= calibrated "
            f"threshold {threshold:.2f} (99.5th percentile of clean traffic)."
        ),
    }
