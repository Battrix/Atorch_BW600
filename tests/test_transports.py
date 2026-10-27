import pytest
from atorch.protocol import commands, get_profile, parse_live
from atorch.transports import TransportTimeout
from atorch.transports.simulated import SimulatedTransport
from atorch.transports.usb import UsbHidTransport, list_devices
from atorch.transports.usb.hid import PID, VID


class FakeDevice:
    def __init__(self, replies):
        self.replies, self.written, self.opened = list(replies), [], None

    def open(self, vid, pid): self.opened = (vid, pid)
    def open_path(self, p): self.opened = p
    def close(self): self.opened = None
    def write(self, data): self.written.append(bytes(data)); return len(data)
    def read(self, n, timeout_ms): return list(self.replies.pop(0)) if self.replies else []


class FakeHid:
    def __init__(self, dev): self.dev = dev
    def device(self): return self.dev
    def enumerate(self, vid, pid):
        assert (vid, pid) == (VID, PID)
        return [{"path": b"\\\\?\\hid#vid_0483", "product_string": "ATORCH BW600",
                 "serial_number": "968511", "interface_number": 0}]


def test_list_devices():
    d = list_devices(FakeHid(FakeDevice([])))[0]
    assert d.product == "ATORCH BW600" and d.serial == "968511"


def test_usb_exchange_filters_type_and_writes_65_bytes():
    from atorch.transports.simulated import make_reply
    dev = FakeDevice([make_reply(0x03, bytes(58)), make_reply(0x05, bytes(58))])
    t = UsbHidTransport(hid_module=FakeHid(dev))
    t.open()
    r = t.exchange(commands.read_live(), want_type=0x05)
    assert r.type == 0x05
    assert len(dev.written[0]) == 65 and dev.written[0][0] == 0
    t.close()


def test_usb_timeout():
    t = UsbHidTransport(hid_module=FakeHid(FakeDevice([])))
    t.open()
    with pytest.raises(TransportTimeout):
        t.exchange(commands.read_live(), timeout=0.05)


def test_simulated_roundtrip():
    with SimulatedTransport(voltage_mv=13500, current_ma=2000) as t:
        r = t.exchange(commands.read_live(), want_type=0x05)
        live = parse_live(r, get_profile("bw600"))
        assert live["voltage"] == pytest.approx(13.5)
        t.send(commands.run(True))
        assert t.sent[-1][3] == 0x25
