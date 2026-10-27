"""Cadre HID pentru BW150 / BW600.

Host -> aparat:  55 05 <addr=01> <cmd> d0 d1 d2 d3 EE FF, completat cu zero la 64 B.
Aparat -> host:  AA 05 <addr> <type> payload... (64 B).
Pe USB scrierea se face cu 65 B (report ID 0 + 64 B). Fara checksum pe HID.
Nu se confunda cu protocolul serial al modulului Wi-Fi (`55 AA ...`).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

FRAME_LEN = 64
TX_HEAD = 0x55
RX_HEAD = 0xAA
PROTO = 0x05
DEFAULT_ADDR = 0x01
TAIL = b"\xEE\xFF"

# Comanda 0x02 porneste bootloader-ul (actualizare firmware). Nu se trimite niciodata.
FORBIDDEN_CMDS = frozenset({0x02})

PAYLOAD_START = 4          # payload-ul incepe dupa AA 05 addr type
PAYLOAD_END = 62           # exclusiv (octetii 4..61)
MIN_PAYLOAD = 51           # cerinta parserului din documentatie


class ProtocolError(ValueError):
    pass


class ForbiddenCommand(ProtocolError):
    pass


def build_frame(cmd: int, data: bytes = b"", addr: int = DEFAULT_ADDR) -> bytes:
    """Cadru de 64 B pentru comanda `cmd` cu datele `data`."""
    if not 0 <= cmd <= 0xFF:
        raise ProtocolError(f"comanda invalida: {cmd}")
    if cmd in FORBIDDEN_CMDS:
        raise ForbiddenCommand(f"comanda 0x{cmd:02X} este blocata (bootloader)")
    if len(data) > FRAME_LEN - 6:
        raise ProtocolError("date prea lungi")
    body = bytes([TX_HEAD, PROTO, addr, cmd]) + bytes(data) + TAIL
    return body.ljust(FRAME_LEN, b"\x00")


def hid_report(frame: bytes) -> bytes:
    """Raport de scriere HID: report ID 0 + cadru de 64 B."""
    if len(frame) != FRAME_LEN:
        raise ProtocolError("cadrul trebuie sa aiba 64 B")
    return b"\x00" + frame


@dataclass(frozen=True)
class Reply:
    addr: int
    type: int
    payload: bytes          # octetii 4..61 ai raspunsului


def parse_reply(raw: bytes) -> Reply:
    """Parseaza un raspuns AA 05 ...; accepta si un report ID 0 in fata."""
    raw = bytes(raw)
    if len(raw) == FRAME_LEN + 1 and raw[0] == 0x00:
        raw = raw[1:]
    if len(raw) < PAYLOAD_START + MIN_PAYLOAD:
        raise ProtocolError(f"raspuns prea scurt: {len(raw)} B")
    if raw[0] != RX_HEAD or raw[1] != PROTO:
        raise ProtocolError(f"antet neasteptat: {raw[0]:02X} {raw[1]:02X}")
    return Reply(addr=raw[2], type=raw[3], payload=raw[PAYLOAD_START:PAYLOAD_END])


def f32be(value: float) -> bytes:
    return struct.pack(">f", value)


def read_f32be(buf: bytes, off: int) -> float:
    return struct.unpack_from(">f", buf, off)[0]


def read_u32le(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]
