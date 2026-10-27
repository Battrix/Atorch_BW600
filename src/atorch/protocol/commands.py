"""Constructori de comenzi. Fiecare intoarce un cadru de 64 B gata de trimis.

Comenzile cu semantica diferita intre modele (timer, reset, cicluri, BAT) se
construiesc prin profilul aparatului (profiles.py), nu aici.
Calibrarea, factory reset si bootloader NU au constructori in acest modul.
"""
from __future__ import annotations

import enum

from .frames import build_frame, f32be, ProtocolError

# Comenzi comune BW150 / BW600
READ_SETTINGS = 0x03
INIT = 0x04
READ_LIVE = 0x05
SETPOINT = 0x21
BRIGHTNESS = 0x22
STANDBY_BRIGHTNESS = 0x23
STANDBY_TIME = 0x24
RUN = 0x25
CUTOFF = 0x29
FULL_VOLTAGE = 0x2A
FULL_CURRENT = 0x2B          # confirmat in sq6emm (BW600); neconfirmat pe BW150
OCP = 0x2C
OPP = 0x2D
NTC_OTP = 0x2E
MOS_OTP = 0x2F
MODE_BASE = 0x47             # cmd = 0x47 + mod (0..9)

# Date implicite pentru citiri, asa cum apar in documentatia noastra.
POLL_DATA = bytes([0x0B, 0x00, 0x8C])


class Mode(enum.IntEnum):
    CC = 0
    CV = 1
    CR = 2
    CP = 3
    BRT = 4
    PT = 5
    CT = 6
    CDC = 7
    CDCDC = 8
    CDXN = 9


def read_settings() -> bytes:
    return build_frame(READ_SETTINGS, POLL_DATA)


def read_live() -> bytes:
    return build_frame(READ_LIVE, POLL_DATA)


def init(type_id: int) -> bytes:
    """Secventa de initializare din documentatie: 04 cu 00 00 00 00 pentru TYPE 1..10."""
    return build_frame(INIT, bytes(4), addr=type_id)


def select_mode(mode: Mode | int) -> bytes:
    m = int(mode)
    if not 0 <= m <= 9:
        raise ProtocolError("mod invalid (0..9)")
    return build_frame(MODE_BASE + m)


def run(on: bool) -> bytes:
    return build_frame(RUN, bytes([1 if on else 0, 0, 0, 0]))


def _float_cmd(cmd: int, value: float) -> bytes:
    return build_frame(cmd, f32be(value))


def set_setpoint(value: float) -> bytes:
    return _float_cmd(SETPOINT, value)


def set_cutoff(volts: float) -> bytes:
    return _float_cmd(CUTOFF, volts)


def set_full_voltage(volts: float) -> bytes:
    return _float_cmd(FULL_VOLTAGE, volts)


def set_full_current(amps: float) -> bytes:
    return _float_cmd(FULL_CURRENT, amps)


def set_ocp(amps: float) -> bytes:
    return _float_cmd(OCP, amps)


def set_opp(watts: float) -> bytes:
    return _float_cmd(OPP, watts)


def set_ntc_otp(celsius: float) -> bytes:
    return _float_cmd(NTC_OTP, celsius)


def set_mos_otp(celsius: float) -> bytes:
    return _float_cmd(MOS_OTP, celsius)


def _level_cmd(cmd: int, value: int, lo: int, hi: int) -> bytes:
    if not lo <= value <= hi:
        raise ProtocolError(f"valoare in afara limitelor {lo}..{hi}")
    return build_frame(cmd, bytes([0, 0, 0, value]))


def set_brightness(level: int) -> bytes:
    return _level_cmd(BRIGHTNESS, level, 0, 9)


def set_standby_brightness(level: int) -> bytes:
    return _level_cmd(STANDBY_BRIGHTNESS, level, 0, 9)


def set_standby_time(seconds: int) -> bytes:
    return _level_cmd(STANDBY_TIME, seconds, 0, 255)
