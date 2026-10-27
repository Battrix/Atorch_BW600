import struct
import pytest
from atorch.protocol import (
    ForbiddenCommand, ProtocolError, build_frame, commands, get_profile,
    hid_report, parse_live, parse_reply, parse_settings,
)


def reply(type_, payload: bytes) -> bytes:
    raw = bytes([0xAA, 0x05, 0x01, type_]) + payload
    return raw.ljust(64, b"\x00")


def test_frame_layout():
    f = build_frame(0x25, bytes([1, 0, 0, 0]))
    assert len(f) == 64
    assert f[:10] == bytes([0x55, 0x05, 0x01, 0x25, 1, 0, 0, 0, 0xEE, 0xFF])
    assert f[10:] == bytes(54)
    assert len(hid_report(f)) == 65 and hid_report(f)[0] == 0


def test_doc_examples():
    assert commands.set_setpoint(1.0)[4:8] == bytes([0x3F, 0x80, 0, 0])
    assert commands.set_cutoff(3.0)[4:8] == bytes([0x40, 0x40, 0, 0])
    assert commands.select_mode(commands.Mode.CC)[3] == 0x47
    assert commands.select_mode(commands.Mode.CDXN)[3] == 0x50
    assert commands.run(False)[4:8] == bytes(4)


def test_bootloader_blocked():
    with pytest.raises(ForbiddenCommand):
        build_frame(0x02)


def test_limits_checked():
    with pytest.raises(ProtocolError):
        commands.set_brightness(10)
    with pytest.raises(ProtocolError):
        commands.select_mode(12)


def test_timer_frames():
    p = get_profile("bw600")
    h, m = p.set_timer(1, 30)
    assert h[4:8] == bytes([1, 0, 0, 1]) and m[4:8] == bytes([30, 0, 0, 2])
    with pytest.raises(ProtocolError):
        get_profile("bw600").select_bat(1)       # BAT nu exista in profilul sq6emm
    assert get_profile("bw600-doc").select_bat(3)[3] == 0x36


def test_settings_parse():
    pl = bytearray(58)
    for off, v in {0: 2.5, 16: 3.0, 20: 4.2, 28: 50.0, 32: 600.0}.items():
        struct.pack_into(">f", pl, off, v)
    pl[44], pl[46], pl[49], pl[50] = 0, 7, 1, 30
    s = parse_settings(parse_reply(reply(0x03, bytes(pl))))
    assert s["setpoint"] == 2.5 and s["cutoff"] == 3.0 and s["full_voltage"] == pytest.approx(4.2)
    assert s["brightness"] == 7 and s["timer_hours"] == 1 and s["timer_minutes"] == 30


def _live_payload(**fields):
    pl = bytearray(58)
    for off, v in fields.items():
        struct.pack_into("<I", pl, int(off[1:]), v)
    return pl


def test_live_bw600():
    pl = _live_payload(o4=12345, o8=2500, o12=30862, o20=1500, o24=800, o32=31000)
    pl[48] = 1
    live = parse_live(parse_reply(reply(0x05, bytes(pl))), get_profile("bw600"))
    assert live["voltage"] == pytest.approx(12.345)
    assert live["current"] == pytest.approx(2.5)
    assert live["energy_wh"] == pytest.approx(1.5)
    assert live["capacity_mah"] == pytest.approx(0.8)
    assert live["temp_probe"] == pytest.approx(31.0)
    assert live.running


def test_live_bw150_power_computed():
    pl = _live_payload(o4=10000, o8=2000)
    pl[48] = 1
    pl[49], pl[50] = 5, 2
    live = parse_live(parse_reply(reply(0x05, bytes(pl))), get_profile("bw150"))
    assert live["power"] == pytest.approx(20.0)
    assert live["cycle_count"] == 5 and live["cycle_index"] == 2 and live.running


def test_reply_validation():
    with pytest.raises(ProtocolError):
        parse_reply(bytes([0x55, 5]) + bytes(62))
    with pytest.raises(ProtocolError):
        parse_reply(bytes(10))
    # report ID 0 in fata e acceptat
    assert parse_reply(b"\x00" + reply(0x05, bytes(58))).type == 0x05
    with pytest.raises(ProtocolError):
        parse_live(parse_reply(reply(0x03, bytes(58))), get_profile("bw600"))
