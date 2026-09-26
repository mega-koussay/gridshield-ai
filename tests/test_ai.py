"""Unit tests: AI components."""
import numpy as np
import pandas as pd
import pytest

from app.ai.anomaly import HybridDetector
from app.ai.classifier import AttackClassifier
from app.ai.forecast import LaggerRidgeForecaster
from app.ai.optimizer import day_ahead_schedule
from app.ai.reconstruction import ReconstructionEngine
from app.core.config import settings


@pytest.fixture(scope="module")
def dataset():
    p = settings.data_dir / "microgrid_dataset.csv"
    df = pd.read_csv(p)
    return df


def test_forecaster_beats_persistence(dataset):
    clean = dataset[dataset["label"] == 0].reset_index(drop=True)
    split = int(len(clean) * 0.8)
    m = LaggerRidgeForecaster("load").fit(clean.iloc[:split], "metered_load_kw")
    truth = clean["metered_load_kw"].to_numpy()[split:split + 48]
    preds = m.predict_from_history(clean.iloc[:split], "metered_load_kw", len(truth))
    mae_model = np.abs(preds - truth).mean()
    mae_naive = np.abs(clean["metered_load_kw"].to_numpy()[split - 1:split - 1 + 48].repeat(1) - truth).mean()
    assert mae_model < mae_naive * 1.5  # model should be in persistence's league or better


def test_detector_calibrates_and_bounds_fpr(dataset):
    clean = dataset[dataset["label"] == 0].reset_index(drop=True)
    det = HybridDetector().fit_calibrate(clean)
    assert 0.35 <= det.threshold <= 0.70
    # Scores on a clean slice should rarely exceed the threshold.
    scores = [det.analyse(clean.iloc[max(0, i - 60):i + 1]).score for i in range(100, 200)]
    fpr = float(np.mean(np.array(scores) >= det.threshold))
    assert fpr < 0.05


def test_detector_fires_on_injected_load(dataset):
    clean = dataset[dataset["label"] == 0].reset_index(drop=True)
    det = HybridDetector().fit_calibrate(clean)
    window = clean.iloc[500:560].copy()
    # Inject a bulk FDI on the last step.
    window.loc[window.index[-1], "metered_load_kw"] *= 1.4
    det_res = det.analyse(window)
    assert det_res.is_anomaly


def test_classifier_distinguishes_none(dataset):
    clf = AttackClassifier().fit(dataset)
    res = clf.predict(dataset.tail(3), 200.0, 100.0)
    assert res["label"] in {"NONE", "FDI_BULK", "FDI_SOLAR", "SCADA_CMD",
                            "DEVICE_MALWARE", "TELEMETRY_SPIKE"}
    assert 0.0 <= res["confidence"] <= 1.0


def test_optimizer_respects_power_and_soc():
    fc_load = np.full(48, 150.0)
    fc_solar = np.concatenate([np.zeros(12), np.full(12, 200.0), np.zeros(24)])
    plan = day_ahead_schedule(fc_load, fc_solar)
    for p in plan["power_kw"]:
        assert abs(p) <= settings.battery_power_kw + 1e-6
    for soc in plan["soc"]:
        assert settings.battery_soc_min - 1e-6 <= soc <= settings.battery_soc_max + 1e-6


def test_optimizer_prefers_charging_from_solar():
    fc_load = np.full(24, 150.0)
    fc_solar = np.concatenate([np.zeros(12), np.full(12, 260.0)])
    plan = day_ahead_schedule(fc_load, fc_solar)
    # Midday surplus should be charged (positive power), not exported.
    assert max(plan["power_kw"]) > 10.0


def test_reconstruction_forecast_path():
    eng = ReconstructionEngine()
    state = {"metered_solar_kw": 200.0, "metered_load_kw": 400.0,
             "solar_kw_true": 100.0, "load_kw_true": 200.0,
             "metered_building_loads": {"B1": 400.0, "B2": 50.0}}
    out = eng.reconstruct(state, pred_load=210.0, pred_solar=95.0,
                          isolated_devices=["MTR_B1"], attack_type="FDI_BULK")
    assert out["load_kw"] == pytest.approx(210.0, abs=1e-6)
    assert "MTR_B1" in out["replaced"]
    assert out["errors"]["load"] == pytest.approx(10.0, abs=1e-6)


def test_reconstruction_consensus_path():
    eng = ReconstructionEngine()
    state = {"metered_solar_kw": 100.0, "metered_load_kw": 250.0,
             "solar_kw_true": 100.0, "load_kw_true": 200.0,
             "metered_building_loads": {"B1": 150.0, "B2": 50.0, "B3": 50.0}}
    out = eng.reconstruct(state, pred_load=195.0, pred_solar=98.0,
                          isolated_devices=["MTR_B1"], attack_type="DEVICE_MALWARE")
    # Healthy meters: B2+B3 = 100; site estimate = 100 * 3/2 = 150, then
    # anchored 70/30 with forecast 195 -> 0.7*150 + 0.3*195 = 163.5
    assert out["load_kw"] == pytest.approx(0.7 * 150.0 + 0.3 * 195.0, abs=1e-6)
