"""Unit tests: deterministic twin + attack simulator."""
import numpy as np
import pytest

from app.core.config import settings
from app.twin.attacks import AttackSimulator
from app.twin.simulator import MicrogridSimulator


def test_determinism_same_seed():
    a = MicrogridSimulator(seed=7)
    b = MicrogridSimulator(seed=7)
    for _ in range(50):
        sa = a.step()
        sb = b.step()
        assert sa.solar_kw == sb.solar_kw
        assert sa.load_kw == sb.load_kw
        assert sa.soc == pytest.approx(sb.soc)


def test_different_seeds_diverge():
    a = MicrogridSimulator(seed=7)
    b = MicrogridSimulator(seed=8)
    vals_a = [a.step().load_kw for _ in range(20)]
    vals_b = [b.step().load_kw for _ in range(20)]
    assert not np.allclose(vals_a, vals_b)


def test_soc_bounds_respected():
    sim = MicrogridSimulator(seed=3)
    for _ in range(300):
        st = sim.step()
        assert settings.battery_soc_min - 1e-6 <= st.soc <= settings.battery_soc_max + 1e-6


def test_power_balance_holds():
    """Solar + battery discharge + import >= load - export (with losses)."""
    sim = MicrogridSimulator(seed=11)
    for _ in range(100):
        st = sim.step()
        supply = st.solar_kw + max(0.0, -st.battery_kw) + st.grid_import_kw
        demand = st.load_kw + max(0.0, st.battery_kw)
        assert supply >= demand - 5.0  # 5 kW tolerance for SOC-window clipping


def test_meter_noise_bounded():
    sim = MicrogridSimulator(seed=5)
    for _ in range(100):
        st = sim.step()
        if st.solar_kw > 5:
            assert abs(st.metered_solar_kw - st.solar_kw) < 0.2 * st.solar_kw + 2


def test_fdi_bulk_corrupts_only_metered():
    sim = MicrogridSimulator(seed=9)
    atk = AttackSimulator(seed=9)
    st = sim.step()
    true_load = st.load_kw
    ev = atk.launch("FDI_BULK", "MTR_B1_Offices", duration_min=15, current_step=st.step_index)
    st2 = atk.apply_to_state(st, current_step=st.step_index)
    assert st2.metered_load_kw > true_load * 1.2   # metered inflated
    assert st2.load_kw == true_load                # truth untouched


def test_scada_cmd_schedules_override():
    atk = AttackSimulator(seed=1)
    atk.launch("SCADA_CMD", "SCADA_ESS", magnitude=1.0, current_step=0)
    st_next = 1  # any state; override is popped by orchestrator
    atk._apply_one(atk.active_attacks[0], type("S", (), {"step_index": 0})())
    assert atk.pop_scada_command() == pytest.approx(settings.battery_power_kw)
    assert atk.pop_scada_command() is None


def test_attack_expires_after_duration():
    sim = MicrogridSimulator(seed=2)
    atk = AttackSimulator(seed=2)
    st = sim.step()
    ev = atk.launch("FDI_SOLAR", "MTR_SOLAR", duration_min=10, current_step=st.step_index)
    for i in range(3):
        st = sim.step()
        atk.apply_to_state(st, current_step=st.step_index)
    assert not ev.active
