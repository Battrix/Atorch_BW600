import time
import pytest
from atorch.service.device import CommandFailed, CommandRejected, DeviceService
from atorch.transports.base import TransportError
from atorch.transports.simulated import SimulatedTransport


def make(sim=None, **kw):
    sim = sim or SimulatedTransport(voltage_mv=3299)
    svc = DeviceService(lambda: sim, poll_interval=0.02, settings_interval=0.05,
                        reconnect_delay=0.05, write_pause=0.0, **kw)
    svc.start()
    deadline = time.time() + 2
    while not (svc.snapshot().connected and svc.snapshot().settings) and time.time() < deadline:
        time.sleep(0.01)
    return svc, sim


def test_polling_and_state():
    svc, _ = make()
    try:
        time.sleep(0.2)
        s = svc.snapshot()
        assert s.connected and s.live["voltage"] == pytest.approx(3.299)
        assert s.seq > 3 and not s.running
        assert len(svc.history()) > 3
    finally:
        svc.shutdown()


def test_config_roundtrip_and_limits():
    svc, sim = make()
    try:
        assert "confirmat" in svc.set_mode(0).result(2)
        assert "confirmat" in svc.set_value("setpoint", 0.5).result(2)
        assert "confirmat" in svc.set_value("cutoff", 3.1).result(2)
        assert "confirmat" in svc.set_value("ocp", 40).result(2)
        assert "confirmat" in svc.set_level("brightness", 5).result(2)
        assert "confirmat" in svc.set_timer(1, 30).result(2)
        assert sim.mode == 0 and sim.setpoint == 0.5 and sim.extra["ocp"] == 40
        assert sim.levels["timer_hours"] == 1 and sim.levels["timer_minutes"] == 30
        for bad in (lambda: svc.set_value("setpoint", 99),      # CC max 50 A
                    lambda: svc.set_value("ocp", 100),
                    lambda: svc.set_value("nume", 1),
                    lambda: svc.set_level("brightness", 12),
                    lambda: svc.set_timer(100, 0),
                    lambda: svc.set_mode(11)):
            with pytest.raises(CommandRejected):
                bad().result(2)
    finally:
        svc.shutdown()


def test_start_stop_and_config_locked_while_running():
    svc, sim = make()
    try:
        svc.set_mode(0).result(2)
        svc.set_value("setpoint", 0.5).result(2)
        svc.set_value("cutoff", 3.1).result(2)          # sub tensiunea celulei, altfel sarcina nu trage curent
        assert svc.start_load().result(3) == "pornit"
        time.sleep(0.1)
        assert svc.snapshot().running and svc.snapshot().live["current"] == pytest.approx(0.5)
        with pytest.raises(CommandRejected):
            svc.set_value("cutoff", 3.0).result(2)               # blocat cat ruleaza
        assert svc.stop_load().result(3) == "oprit"
        assert not sim.running
        assert "confirmat" in svc.set_value("cutoff", 3.0).result(2)
    finally:
        svc.shutdown()


def test_unconfirmed_write_fails():
    svc, _ = make(SimulatedTransport(voltage_mv=3299, ignore_writes=True))
    try:
        with pytest.raises(CommandFailed):
            svc.set_value("cutoff", 3.0).result(3)
    finally:
        svc.shutdown()


def test_stop_failure_reported():
    svc, sim = make(SimulatedTransport(voltage_mv=3299, ignore_stop=True))
    svc.stop_attempts, svc.stop_wait = 3, 0.2
    try:
        sim.running = True
        time.sleep(0.1)
        with pytest.raises(CommandFailed) as e:
            svc.stop_load().result(10)
        assert "OPRIREA" in str(e.value)
    finally:
        svc.shutdown()


def test_stop_has_priority_over_queued_commands():
    svc, sim = make()
    try:
        sim.running = True
        time.sleep(0.1)
        futs = [svc.set_value("cutoff", 3.0) for _ in range(5)]
        stop = svc.stop_load()
        assert stop.result(3) == "oprit"
        for f in futs:                                            # restul sunt refuzate sau confirmate, nu blocate
            try:
                f.result(3)
            except CommandRejected:
                pass
    finally:
        svc.shutdown()


def test_reconnect_after_transport_error():
    class Flaky(SimulatedTransport):
        fails = 1
        def send(self, frame):
            if Flaky.fails and frame[3] == 0x05:
                Flaky.fails -= 1
                raise TransportError("cablu scos")
            super().send(frame)
    events = []
    sim = Flaky(voltage_mv=3299)
    svc = DeviceService(lambda: sim, poll_interval=0.02, settings_interval=0.05,
                        reconnect_delay=0.05, write_pause=0.0)
    svc.subscribe(lambda k, d: events.append((k, d.get("connected"))))
    svc.start()
    try:
        time.sleep(0.5)
        assert ("status", False) in events and svc.snapshot().connected
        assert svc.snapshot().live["voltage"] == pytest.approx(3.299)
    finally:
        svc.shutdown()


def test_isolated_timeout_does_not_disconnect():
    from atorch.transports.base import TransportTimeout

    class Hiccup(SimulatedTransport):
        miss = 2
        def send(self, frame):
            if Hiccup.miss and frame[3] == 0x05 and self.sent:
                Hiccup.miss -= 1
                self.sent.append(frame)          # cererea se pierde, fara raspuns
                return
            super().send(frame)
    events = []
    sim = Hiccup(voltage_mv=3299)
    svc = DeviceService(lambda: sim, poll_interval=0.02, settings_interval=0.05,
                        reconnect_delay=0.05, write_pause=0.0)
    svc.subscribe(lambda k, d: events.append((k, d.get("connected"))))
    svc.start()
    try:
        time.sleep(3.5)
        assert svc.snapshot().connected and svc.snapshot().seq > 3
        assert ("status", False) not in events
    finally:
        svc.shutdown()
