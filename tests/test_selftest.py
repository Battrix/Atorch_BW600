import pytest
from atorch.service.selftest import SelfTestAbort, run_cc_selftest
from atorch.transports.simulated import SimulatedTransport

Q = dict(pause=0.0, say=lambda m: None)


def test_happy_path_restores_and_stops():
    t = SimulatedTransport(voltage_mv=3299)
    r = run_cc_selftest(t, current=0.5, cutoff=3.1, seconds=0.6, **Q)
    assert r.stopped_ok and r.restored_ok
    assert r.samples and any(abs(s["i"] - 0.5) < 1e-3 and s["run"] for s in r.samples)
    assert not t.running and t.mode == 1 and t.setpoint == 5.0 and t.cutoff == pytest.approx(14.8, abs=1e-3)


def test_refuses_bad_voltage():
    for mv in (1000, 12000):
        t = SimulatedTransport(voltage_mv=mv)
        with pytest.raises(SelfTestAbort):
            run_cc_selftest(t, seconds=0.5, **Q)
        assert all(f[3] != 0x25 for f in t.sent)        # nu s-a trimis niciodata RUN


def test_refuses_cutoff_above_cell():
    t = SimulatedTransport(voltage_mv=3299)
    with pytest.raises(SelfTestAbort):
        run_cc_selftest(t, cutoff=3.5, seconds=0.5, **Q)


def test_limits():
    t = SimulatedTransport(voltage_mv=3299)
    with pytest.raises(SelfTestAbort):
        run_cc_selftest(t, current=2.0, **Q)
    with pytest.raises(SelfTestAbort):
        run_cc_selftest(t, seconds=60, **Q)


def test_writes_not_applied_never_starts():
    t = SimulatedTransport(voltage_mv=3299, ignore_writes=True)
    with pytest.raises(SelfTestAbort):
        run_cc_selftest(t, seconds=0.5, **Q)
    assert not t.running
    assert all(not (f[3] == 0x25 and f[4] == 1) for f in t.sent)


def test_stop_failure_is_reported():
    t = SimulatedTransport(voltage_mv=3299, ignore_stop=True)
    r = run_cc_selftest(t, seconds=0.4, **Q)
    assert not r.stopped_ok and not r.restored_ok
