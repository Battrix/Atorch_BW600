import math
import time

import pytest

from atorch.owon import OwonError, OwonSupply


class ScpiPort:
    def __init__(self, identity='OWON,SPE8105,TEST,V1.1.0', ignore_voltage=False):
        self.identity=identity
        self.ignore_voltage=ignore_voltage
        self.volts,self.amps,self.on=4.2,1.07,False
        self.commands=[]
        self.reply=b''
        self.closed=False
    def reset_input_buffer(self): pass
    def close(self): self.closed=True
    def write(self, raw):
        cmd=raw.decode().strip();self.commands.append(cmd)
        replies={'*IDN?':self.identity,'VOLT?':str(self.volts),'CURR?':str(self.amps),
                 'OUTP?':'ON' if self.on else 'OFF','MEAS:VOLT?':str(self.volts if self.on else 0),
                 'MEAS:CURR?':str(self.amps if self.on else 0),
                 'MEAS:POW?':str(self.volts*self.amps if self.on else 0)}
        if cmd in replies:self.reply=(replies[cmd]+'\n').encode()
        elif cmd.startswith('VOLT ') and not self.ignore_voltage:self.volts=float(cmd.split()[1])
        elif cmd.startswith('CURR '):self.amps=float(cmd.split()[1])
        elif cmd=='OUTP ON':self.on=True
        elif cmd=='OUTP OFF':self.on=False
    def read_until(self, delim, size):
        r,self.reply=self.reply,b'';return r


def source(port=None):
    port=port or ScpiPort()
    return OwonSupply(port_factory=lambda **kw:port),port


def test_connect_is_read_only_and_checks_identity():
    s,p=source()
    try:
        st=s.connect('COM14')
        assert st['connected'] and not st['output']
        assert all(c.endswith('?') for c in p.commands)
        assert st['set_voltage']==4.2
    finally:s.disconnect()
    s,p=source(ScpiPort(identity='OTHER,MODEL,TEST,V1'))
    with pytest.raises(OwonError):s.connect('COM14')
    assert p.closed and not s.snapshot()['connected']
    assert 'OUTP ON' not in p.commands


def test_configuration_off_readback_and_manual_output():
    s,p=source()
    try:
        s.connect('COM14');s.configure(4.1,1)
        assert s.snapshot()['set_voltage']==4.1
        assert s.snapshot()['set_current']==1
        assert not p.on
        assert p.commands.index('OUTP OFF') < p.commands.index('VOLT 4.10')
        s.output(True);assert p.on
        s.output(False);assert not p.on
    finally:s.disconnect()


@pytest.mark.parametrize('v,i',[(81,1),(4.1,11),(80,10),(math.nan,1),(4.1,math.inf),(0,1)])
def test_limits_rejected_before_io(v,i):
    s,p=source()
    with pytest.raises(OwonError):s.configure(v,i)
    assert not p.commands


def test_ignored_voltage_does_not_enable_output():
    s,p=source(ScpiPort(ignore_voltage=True))
    try:
        s.connect('COM14')
        with pytest.raises(OwonError):s.configure(4.1,1)
        assert not p.on and 'OUTP ON' not in p.commands
    finally:s.disconnect()


def test_simulator_never_opens_serial():
    def forbidden(**kw):raise AssertionError('hardware accessed')
    s=OwonSupply(port_factory=forbidden,simulated=True)
    s.connect('SIMULATOR');s.configure(4.1,1);s.output(True)
    assert s.snapshot()['output']
    s.disconnect();assert not s.snapshot()['output']
