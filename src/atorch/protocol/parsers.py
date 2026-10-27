"""Decodare payload 03 (configuratie) si 05 (masuratori)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .frames import Reply, ProtocolError, read_f32be, read_u32le
from .profiles import DeviceProfile, SETTINGS_BYTES, SETTINGS_FLOATS

TYPE_SETTINGS = 0x03
TYPE_LIVE = 0x05


@dataclass
class Settings:
    values: dict[str, float] = field(default_factory=dict)

    def __getitem__(self, k: str) -> float:
        return self.values[k]


@dataclass
class Live:
    values: dict[str, float] = field(default_factory=dict)
    running: bool = False

    def __getitem__(self, k: str) -> float:
        return self.values[k]

    def get(self, k: str, default: float | None = None):
        return self.values.get(k, default)


def parse_settings(reply: Reply) -> Settings:
    if reply.type != TYPE_SETTINGS:
        raise ProtocolError(f"nu e raspuns de configuratie (type {reply.type:02X})")
    p = reply.payload
    out: dict[str, float] = {}
    for name, off in SETTINGS_FLOATS.items():
        out[name] = read_f32be(p, off)
    for name, off in SETTINGS_BYTES.items():
        out[name] = p[off]
    return Settings(out)


def parse_live(reply: Reply, profile: DeviceProfile) -> Live:
    if reply.type != TYPE_LIVE:
        raise ProtocolError(f"nu e raspuns de masuratori (type {reply.type:02X})")
    p = reply.payload
    out: dict[str, float] = {}
    for name, (off, kind, div) in profile.live_layout.items():
        if kind == "u32le":
            raw = read_u32le(p, off)
        elif kind == "u8":
            raw = p[off]
        else:
            raise ProtocolError(f"tip necunoscut: {kind}")
        out[name] = raw / div if div != 1 else raw
    if profile.live_power_computed:
        out["power"] = out["voltage"] * out["current"]
    running = bool(out.get("run_flag", 0) == 1)
    return Live(out, running)
