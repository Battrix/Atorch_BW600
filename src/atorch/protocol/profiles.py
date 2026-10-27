"""Profiluri de aparat: comenzi si layout-uri de masuratori care difera intre modele.

SURSE IN CONFLICT (de decis cu teste pe aparat, vezi docs/SOURCES.md):
- Masuratori BW600: documentatia noastra (Wh la 16, mAh la 20) vs sq6emm (Ohm la 16,
  Wh la 20, mAh la 24). Profilul implicit "bw600" urmeaza sq6emm (verificat de autor pe
  BW600-DK); varianta noastra este "bw600-doc", pentru comparatie pe aparat.
- Comenzi BW600: doc = timer 0x32, reset 0x35, BAT 0x36; sq6emm = timer 0x31, clear 0x32,
  factory reset 0x33, zero 0x34, 0x35 = grup inregistrari, 0x36 nefolosit de firmware.
  Profilul "bw600" urmeaza sq6emm; "bw600-doc" urmeaza documentatia.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .frames import build_frame, ProtocolError

# camp -> (offset in payload, tip, divizor). tip: "u32le" sau "u8"
Layout = dict[str, tuple[int, str, float]]

BW600_LIVE: Layout = {
    "voltage": (4, "u32le", 1000),
    "current": (8, "u32le", 1000),
    "power": (12, "u32le", 1000),
    "resistance": (16, "u32le", 1000),
    "energy_wh": (20, "u32le", 1000),
    "capacity_mah": (24, "u32le", 1000),
    "temp_cpu": (28, "u32le", 1000),
    "temp_probe": (32, "u32le", 1000),
    "temp_mos": (36, "u32le", 1000),
    "fan": (40, "u32le", 1000),
    "run_flag": (48, "u8", 1),
    "sign_flags": (56, "u8", 1),
}

BW600_DOC_LIVE: Layout = {
    "voltage": (4, "u32le", 1000),
    "current": (8, "u32le", 1000),
    "power": (12, "u32le", 1000),
    "energy_wh": (16, "u32le", 1000),
    "capacity_mah": (20, "u32le", 1000),
    "raw_counter": (24, "u32le", 1),
    "temp_probe": (28, "u32le", 1000),
    "temp_mos": (32, "u32le", 1000),
    "temp_aux": (36, "u32le", 1000),
    "fan": (40, "u32le", 1000),
    "run_flag": (44, "u8", 1),
}

BW150_LIVE: Layout = {          # puterea se calculeaza U*I
    "voltage": (4, "u32le", 1000),
    "current": (8, "u32le", 1000),
    "energy_wh": (20, "u32le", 1000),
    "capacity_mah": (24, "u32le", 1000),
    "raw_counter": (28, "u32le", 1),
    "temp_probe": (32, "u32le", 1000),
    "temp_mos": (36, "u32le", 1000),
    "fan": (40, "u32le", 1000),
    "run_flag": (48, "u8", 1),
    "cycle_count": (49, "u8", 1),
    "cycle_index": (50, "u8", 1),
}

# Layout comun al payload-ului 03 (configuratie); confirmat de ambele surse.
SETTINGS_FLOATS = {
    "setpoint": 0, "cal_temp": 4, "cal_voltage": 8, "cal_current": 12,
    "cutoff": 16, "full_voltage": 20, "full_current": 24,
    "ocp": 28, "opp": 32, "ntc_otp": 36, "mos_otp": 40,
}
SETTINGS_BYTES = {
    "mode": 44, "language": 45, "brightness": 46, "standby_brightness": 47,
    "standby_time": 48, "timer_hours": 49, "timer_minutes": 50, "cycles": 51,
}


@dataclass(frozen=True)
class DeviceProfile:
    name: str
    title: str
    live_layout: Layout
    live_power_computed: bool
    cmd_timer: int
    cmd_clear: int | None
    cmd_zero: int | None = None
    cmd_cycles: int | None = None
    cmd_bat: int | None = None
    # limite software din documentatie (min, max)
    limits: dict[str, tuple[float, float]] = field(default_factory=dict)
    notes: str = ""

    def _need(self, cmd: int | None, what: str) -> int:
        if cmd is None:
            raise ProtocolError(f"{what} nu exista pe profilul {self.name}")
        return cmd

    def set_timer(self, hours: int, minutes: int) -> list[bytes]:
        """Timer: ore (d3=1) apoi minute (d3=2). Doua cadre, de trimis in ordine."""
        if not (0 <= hours <= 99 and 0 <= minutes <= 59):
            raise ProtocolError("timer in afara limitelor")
        return [
            build_frame(self.cmd_timer, bytes([hours, 0, 0, 1])),
            build_frame(self.cmd_timer, bytes([minutes, 0, 0, 2])),
        ]

    def clear_counters(self) -> bytes:
        return build_frame(self._need(self.cmd_clear, "clear"), bytes(4))

    def set_cycles(self, n: int) -> bytes:
        if not 1 <= n <= 99:
            raise ProtocolError("cicluri 1..99")
        return build_frame(self._need(self.cmd_cycles, "cicluri"), bytes([0, 0, 0, n]))

    def select_bat(self, slot: int) -> bytes:
        if not 1 <= slot <= 99:
            raise ProtocolError("BAT 1..99")
        return build_frame(self._need(self.cmd_bat, "BAT"), bytes([0, 0, 0, slot]))


BW150_LIMITS = {
    "cc": (0.01, 25), "cp": (0.01, 150), "cv": (1, 200), "cr": (0.1, 10000),
    "cutoff": (0, 200), "ocp": (0.01, 25), "opp": (1, 150),
    "ntc_otp": (1, 100), "mos_otp": (1, 100),
}
BW600_LIMITS = {
    "cc": (0.01, 50), "cp": (0.01, 600), "cv": (1, 200), "cr": (0.1, 10000),
    "cutoff": (0, 200), "ocp": (0.01, 60), "opp": (1, 650),
    "ntc_otp": (1, 100), "mos_otp": (1, 150),
}

PROFILES: dict[str, DeviceProfile] = {
    "bw150": DeviceProfile(
        name="bw150", title="ATORCH BW150", live_layout=BW150_LIVE,
        live_power_computed=True, cmd_timer=0x31, cmd_clear=0x34, cmd_cycles=0x35,
        limits=BW150_LIMITS, notes="Layout din documentatia noastra (fw 1.1.0).",
    ),
    "bw600": DeviceProfile(
        name="bw600", title="ATORCH BW600 / BW600-DK", live_layout=BW600_LIVE,
        live_power_computed=False, cmd_timer=0x31, cmd_clear=0x32, cmd_zero=0x34,
        cmd_cycles=0x37, limits=BW600_LIMITS,
        notes="Layout si comenzi dupa sq6emm (fw 2.0.5). De verificat pe aparat.",
    ),
    "bw600-doc": DeviceProfile(
        name="bw600-doc", title="BW600 (varianta din documentatie)",
        live_layout=BW600_DOC_LIVE, live_power_computed=False,
        cmd_timer=0x32, cmd_clear=0x35, cmd_bat=0x36, limits=BW600_LIMITS,
        notes="Varianta documentatiei noastre; pentru comparatie pe aparat.",
    ),
}


def get_profile(name: str) -> DeviceProfile:
    try:
        return PROFILES[name.lower()]
    except KeyError:
        raise ProtocolError(f"profil necunoscut: {name}") from None
