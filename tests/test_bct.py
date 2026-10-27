import time
import pytest
from atorch.bct import BctEngine, BctError, TestStore, derive_battery, validate_battery
from atorch.bct.catalog import BatteryError
from atorch.service.device import DeviceService
from atorch.transports.simulated import SimCell, SimulatedTransport


def make(tmp_path, cell=None, **kw):
    sim = SimulatedTransport(voltage_mv=3400, cell=cell or SimCell(capacity_ah=0.006, v_full=3.4, v_empty=3.0, ri_ohm=0.004))
    svc = DeviceService(lambda: sim, poll_interval=0.02, settings_interval=0.05, reconnect_delay=0.05, write_pause=0.0)
    svc.start()
    end = time.time() + 2
    while not (svc.snapshot().connected and svc.snapshot().settings) and time.time() < end:
        time.sleep(0.01)
    time.sleep(0.1)
    eng = BctEngine(svc, TestStore(tmp_path), min_dt=0.05, **kw)
    return svc, sim, eng


def battery(**kw):
    b = derive_battery("lifepo4", 1, 0.006, model="Celula test")
    b.update(full_v=3.4, empty_v=3.0, nominal_v=3.2, discharge_a=5.0)
    b.update(kw)
    return b


def wait(eng, secs=20):
    end = time.time() + secs
    while eng.active() and time.time() < end:
        time.sleep(0.02)
    eng.join(5)
    return eng.status()


def test_derive_battery_series_and_validation():
    b = derive_battery("lifepo4", 16, 100, model="Pack 48V")
    assert b["nominal_v"] == pytest.approx(51.2) and b["full_v"] == pytest.approx(58.4)
    assert b["empty_v"] == pytest.approx(40.0) and b["discharge_a"] == pytest.approx(20.0)
    with pytest.raises(BatteryError):
        derive_battery("nu-exista", 1, 10)
    with pytest.raises(BatteryError):
        validate_battery(dict(b, empty_v=60))


def test_store_battery_roundtrip(tmp_path):
    st = TestStore(tmp_path)
    saved = st.save_battery(derive_battery("nmc", 10, 5, model="Bosch 36V 5Ah", ri_max_mohm=120))
    assert saved["id"] == "bosch-36v-5ah"
    assert [x["model"] for x in st.batteries()] == ["Bosch 36V 5Ah"]
    assert st.delete_battery("bosch-36v-5ah") and st.batteries() == []
    with pytest.raises(BatteryError):
        st.save_battery(derive_battery("nmc", 10, 5, model="  "))


def test_full_discharge_positive(tmp_path):
    svc, sim, eng = make(tmp_path)
    try:
        eng.start(battery(rated_ah=0.005))          # celula 0.006 Ah, declarat 0.005 -> >= 80%
        st = wait(eng)
        assert st["state"] == "finished", st
        r = st["result"]
        assert r["verdict"] == "POZITIV"
        assert 0.003 < r["capacity_ah"] < 0.0065 and r["capacity_pct"] >= 80
        assert r["ri_mohm"] == pytest.approx(4.0, abs=1.0)
        assert not sim.running
        saved = TestStore(tmp_path).list_tests()
        assert len(saved) == 1 and saved[0]["result"]["verdict"] == "POZITIV"
        full = TestStore(tmp_path).load_test(saved[0]["id"])
        assert len(full["samples"]) > 5
    finally:
        svc.shutdown()


def test_low_capacity_negative(tmp_path):
    svc, sim, eng = make(tmp_path)
    try:
        eng.start(battery(rated_ah=0.012))          # declarat dublu fata de real -> ~50%
        st = wait(eng)
        assert st["state"] == "finished" and st["result"]["verdict"] == "NEGATIV"
        assert "sub pragul" in st["result"]["reasons"][0]
    finally:
        svc.shutdown()


def test_high_internal_resistance_negative(tmp_path):
    svc, sim, eng = make(tmp_path)
    try:
        eng.start(battery(rated_ah=0.005, ri_max_mohm=1.0))
        st = wait(eng)
        assert st["result"]["verdict"] == "NEGATIV" and "rezistență" in st["result"]["reasons"][0]
    finally:
        svc.shutdown()


def test_abort_stops_load_and_is_unfinished(tmp_path):
    cell = SimCell(capacity_ah=5.0, v_full=3.4, v_empty=2.8, ri_ohm=0.002)
    svc, sim, eng = make(tmp_path, cell)
    try:
        eng.start(battery(rated_ah=5.0))
        time.sleep(0.5)
        assert sim.running
        eng.stop()
        st = wait(eng)
        assert st["state"] == "aborted" and st["result"]["verdict"] == "NEFINALIZAT"
        assert not sim.running
    finally:
        svc.shutdown()


def test_manual_stop_on_device_is_not_a_finished_test(tmp_path):
    cell = SimCell(capacity_ah=5.0, v_full=3.4, v_empty=2.8, ri_ohm=0.002)
    svc, sim, eng = make(tmp_path, cell)
    try:
        eng.start(battery(rated_ah=5.0))
        time.sleep(0.4)
        sim.running = False                         # operatorul opreste de pe aparat
        st = wait(eng)
        assert st["state"] == "aborted" and st["result"]["verdict"] == "NEFINALIZAT"
    finally:
        svc.shutdown()


def test_refuses_bad_starts(tmp_path):
    svc, sim, eng = make(tmp_path)
    try:
        with pytest.raises(BctError, match="limitelor"):
            eng.start(battery(discharge_a=80))                  # peste 50 A
        with pytest.raises(BctError, match="descărcat"):
            eng.start(battery(empty_v=3.39, full_v=3.6, nominal_v=3.5))
        with pytest.raises(BctError, match="peste tensiunea full"):
            eng.start(battery(full_v=3.0, empty_v=2.0, nominal_v=2.5))
        with pytest.raises(BctError):
            eng.start(dict(battery(), rated_ah=-1))
        assert not sim.running and not eng.active()
    finally:
        svc.shutdown()
