"""Transport simulat pentru teste si dezvoltare fara aparat."""
from __future__ import annotations

import struct
from collections import deque

from atorch.protocol import parse_reply
from atorch.protocol.frames import Reply
from .base import Transport, TransportTimeout


def make_reply(type_: int, payload: bytes, addr: int = 1) -> bytes:
    return (bytes([0xAA, 0x05, addr, type_]) + payload).ljust(64, b"\x00")


class SimulatedTransport(Transport):
    """Raspunde la 03/05 cu valori fixe si memoreaza cadrele trimise."""

    name = "sim"

    def __init__(self, voltage_mv=12000, current_ma=0, layout="bw600"):
        self.sent: list[bytes] = []
        self._q: deque[bytes] = deque()
        self.voltage_mv, self.current_ma, self.layout = voltage_mv, current_ma, layout
        self.is_open = False

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def send(self, frame: bytes) -> None:
        self.sent.append(frame)
        cmd = frame[3]
        if cmd == 0x05:
            pl = bytearray(58)
            struct.pack_into("<I", pl, 4, self.voltage_mv)
            struct.pack_into("<I", pl, 8, self.current_ma)
            self._q.append(make_reply(0x05, bytes(pl)))
        elif cmd == 0x03:
            pl = bytearray(58)
            struct.pack_into(">f", pl, 0, 1.0)
            self._q.append(make_reply(0x03, bytes(pl)))

    def receive(self, timeout: float = 0.8) -> Reply:
        if not self._q:
            raise TransportTimeout("fara raspuns (simulat)")
        return parse_reply(self._q.popleft())
