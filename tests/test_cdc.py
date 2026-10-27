import threading
import time
from types import SimpleNamespace

import pytest

from atorch.cdc import CdcEngine, phase_of, validate
from atorch.protocol.profiles import BW600_LIMITS
from atorch.service.device import DeviceService
from atorch.transports.simulated import SimCell, SimulatedTransport


def wait_for(fn, timeout=8):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        if fn():
            return
        time.sleep(.02)
    raise AssertionError('timeout')


def test_direction_requires_current_and_run():
    assert phase_of({'running': False, 'current': 1}) == 'idle'
    assert phase_of({'running': True, 'current': 0}) == 'waiting'
    assert phase_of({'running': True, 'current': 1, 'sign_flags': 128}) == 'discharge'
    assert phase_of({'running': True, 'current': 1, 'sign_flags': 0}) == 'charge'


def test_validate_rejects_nonfinite_and_bad_voltage():
    s = SimpleNamespace(connected=True, running=False, updated=time.time(), live={'voltage':3.52})
    p = dict(current=1, empty_v=3.5, full_v=4.1, end_current=.1)
    assert validate(p, s, BW600_LIMITS)['end_current'] == .1
    for key in p:
        with pytest.raises(ValueError):
            validate(dict(p, **{key:float('nan')}),s,BW600_LIMITS)
    with pytest.raises(ValueError):
        validate(dict(p, empty_v=4.2),s,BW600_LIMITS)


def test_double_start_spacing_and_cancel():
    class TimedSim(SimulatedTransport):
        def __init__(self):
            super().__init__(mode=7, cutoff=3)
            self.starts=[]
        def send(self, frame):
            if frame[3] == 0x25 and frame[4] == 1:
                self.starts.append(time.monotonic())
            super().send(frame)
    sim=TimedSim()
    svc=DeviceService(lambda:sim,poll_interval=.02,write_pause=0)
    svc.start()
    try:
        wait_for(lambda: bool(svc.snapshot().settings))
        svc.start_cdc(threading.Event()).result(4)
        assert len(sim.starts)==2
        assert .95 <= sim.starts[1]-sim.starts[0] < 1.5
        svc.stop_load().result(3)
        sim.starts.clear()
        cancel=threading.Event()
        f=svc.start_cdc(cancel)
        wait_for(lambda:len(sim.starts)==1)
        cancel.set()
        with pytest.raises(Exception):
            f.result(3)
        assert len(sim.starts)==1
        assert not sim.running
    finally:
        svc.shutdown()


def test_cdc_persists_stages_and_stop(tmp_path):
    class ScriptedCdc(SimulatedTransport):
        """Etape controlate prin numarul de citiri, independente de viteza PC-ului."""
        ticks = 0
        def _advance_cell(self):
            if self.running and self.mode == 7:
                self.ticks += 1
                if self.ticks <= 5:
                    self.cdc_stage, self.voltage_mv = 0, 3800
                elif self.ticks <= 10:
                    self.cdc_stage, self.voltage_mv = 1, 3510
                elif self.ticks <= 15:
                    self.cdc_stage, self.voltage_mv = 2, 4090
                else:
                    self.running = False
    sim=ScriptedCdc(voltage_mv=3520,mode=0,cutoff=3.5)
    svc=DeviceService(lambda:sim,poll_interval=.02,settings_interval=.03,write_pause=0)
    svc.start()
    e=CdcEngine(svc,root=tmp_path)
    try:
        wait_for(lambda:bool(svc.snapshot().live))
        tid=e.start(dict(current=1,empty_v=3.5,full_v=4.1,end_current=.1,double_start=False))
        wait_for(lambda:e.status()['state'] not in {'idle','preparing','running','stopping'},timeout=10)
        t=e.load(tid)
        assert t['stop_confirmed']
        assert not sim.running
        assert {'charge','discharge'} <= {s['phase'] for s in t['stages']}
        assert any(s['ah']>0 for s in t['stages'])
        assert (tmp_path/'cdc'/f'{tid}.json').exists()
        assert t['state']=='finished'
    finally:
        e.stop()
        svc.shutdown()
