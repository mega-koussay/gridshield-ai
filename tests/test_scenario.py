"""Integration tests: full demo chain + API + persistence."""
import pytest
from fastapi.testclient import TestClient

from app.ai.federated import run_federated
from app.core.config import settings
from app.services.orchestrator import orchestrator, DEMO_PHASES


def _run_demo(attack: str, steps: int = 110):
    p = orchestrator.launch_demo(seed=2026, attack_type=attack)
    alerts = 0
    for _ in range(steps):
        p = orchestrator.step()
        if p["detection"]["is_anomaly"]:
            alerts += 1
    return p, alerts


@pytest.mark.parametrize("attack", ["FDI_BULK", "FDI_SOLAR", "SCADA_CMD", "DEVICE_MALWARE", "TELEMETRY_SPIKE"])
def test_demo_chain_completes_for_every_attack(attack):
    p, alerts = _run_demo(attack)
    assert alerts >= 1, f"{attack} was never detected"
    assert p["kpis"]["detection_latency_steps"] is not None
    assert p["kpis"]["detection_latency_steps"] <= 3
    assert p["demo"]["phase"] == "RECOVERY"
    assert any(i["status"] == "recovered" for i in p["incidents"]["incidents"])


def test_demo_is_deterministic():
    p1, a1 = _run_demo("FDI_BULK")
    p2, a2 = _run_demo("FDI_BULK")
    assert a1 == a2
    assert p1["kpis"]["detection_latency_steps"] == p2["kpis"]["detection_latency_steps"]
    assert p1["state"]["soc"] == pytest.approx(p2["state"]["soc"])


def test_clean_run_has_no_false_alerts():
    orchestrator.reset(seed=99)
    p = None
    for _ in range(60):
        p = orchestrator.step()
    assert p["detection"]["is_anomaly"] is False or p["detection"]["score"] < 0.9
    assert p["kpis"]["attack_status"] in ("NORMAL", "RECOVERED")


def test_attack_changes_telemetry():
    """No fake attacks: metered values must differ from true values."""
    orchestrator.reset(seed=7)
    orchestrator.attacks.launch("FDI_BULK", "MTR_B1_Offices", duration_min=30,
                                current_step=orchestrator.sim.step_index + 2)
    corrupted = False
    for _ in range(20):
        p = orchestrator.step()
        if p["state"]["metered_load_kw"] > p["state"]["load_kw"] * 1.15:
            corrupted = True
    assert corrupted


def test_explanation_has_reasons():
    p, _ = _run_demo("FDI_BULK")
    assert p["explanation"] is not None
    assert len(p["explanation"]["reasons"]) >= 1
    assert p["explanation"]["confidence"] > 0


def test_fl_converges_close_to_centralized():
    import pandas as pd
    df = pd.read_csv(settings.data_dir / "microgrid_dataset.csv")
    clean = df[df["label"] == 0].head(2000)
    fl = run_federated(clean, rounds=6)
    assert fl["final_global_mae"] <= fl["centralized_mae"] * 1.25 + 0.5


# --------------------------------------------------------------------- #
def test_health_endpoint():
    from app.main import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["models"]["detector"] is True


def test_demo_endpoint_and_incident_history():
    from app.main import app
    client = TestClient(app)
    r = client.post("/api/demo/launch", json={"seed": 2026, "attack_type": "FDI_BULK"})
    assert r.status_code == 200
    for _ in range(60):
        client.post("/api/sim/step")
    r2 = client.get("/api/incidents")
    assert r2.status_code == 200
    assert r2.json()["open_count"] >= 0
    r3 = client.get("/api/incidents/history")
    assert r3.status_code == 200
    assert isinstance(r3.json(), list)


def test_attack_endpoint_rejects_unknown_type():
    from app.main import app
    client = TestClient(app)
    r = client.post("/api/attack/launch", json={"attack_type": "NOT_REAL"})
    assert r.status_code == 400
