"""Transport simulat cu stare, pentru teste si dezvoltare fara aparat."""
from __future__ import annotations

import struct
from collections import deque

from atorch.protocol import parse_reply
from atorch.protocol.frames import Reply
from .base import Transport, TransportTimeout


def make_reply(type_: int, payload: bytes, addr: int = 1) -> bytes:
    return (bytes([0xAA, 0x05, addr, type_]) + payload).ljust(64, b"\x00")


class SimulatedTransport(Transport):
    """Imita un BW600 (layout sq6emm): tine mod, setpoint, cutoff si starea de rulare.

    In modul CC cu sarcina pornita, curentul = setpoint (daca tensiunea > cutoff).
    `ignore_writes=True` simuleaza un aparat care nu aplica scrierile (pentru teste de siguranta).
    """

    name = "sim"

    def __init__(self, voltage_mv=12000, current_ma=0, layout="bw600",
                 mode=1, setpoint=5.0, cutoff=14.8, ignore_writes=False,
                 ignore_stop=False):
        self.sent: list[bytes] = []
        self._q: deque[bytes] = deque()
        self.voltage_mv, self.layout = voltage_mv, layout
        self.mode, self.setpoint, self.cutoff = mode, setpoint, cutoff
        self.running = False
        self.fixed_current_ma = current_ma
        self.ignore_writes, self.ignore_stop = ignore_writes, ignore_stop
        self.is_open = False

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    @property
    def current_ma(self) -> int:
        if self.running and self.mode == 0 and self.voltage_mv / 1000 > self.cutoff:
            return int(self.setpoint * 1000)
        return self.fixed_current_ma

    def _apply(self, frame: bytes) -> None:
        cmd = frame[3]
        if cmd == 0x25:
            on = frame[4] == 1
            if on or not self.ignore_stop:
                self.running = on
        if self.ignore_writes:
            return
        if cmd == 0x21:
            self.setpoint = struct.unpack(">f", frame[4:8])[0]
        elif cmd == 0x29:
            self.cutoff = struct.unpack(">f", frame[4:8])[0]
        elif 0x47 <= cmd <= 0x50 and not self.running:
            self.mode = cmd - 0x47

    def send(self, frame: bytes) -> None:
        self.sent.append(frame)
        cmd = frame[3]
        if cmd == 0x05:
            pl = bytearray(58)
            v, i = self.voltage_mv, self.current_ma
            struct.pack_into("<I", pl, 4, v)
            struct.pack_into("<I", pl, 8, i)
            struct.pack_into("<I", pl, 12, v * i // 1000)
            struct.pack_into("<I", pl, 16, 9999991)
            pl[48] = 1 if self.running else 0
            self._q.append(make_reply(0x05, bytes(pl)))
        elif cmd == 0x03:
            pl = bytearray(58)
            struct.pack_into(">f", pl, 0, self.setpoint)
            struct.pack_into(">f", pl, 16, self.cutoff)
            pl[44] = self.mode
            self._q.append(make_reply(0x03, bytes(pl)))
        else:
            self._apply(frame)

    def receive(self, timeout: float = 0.8) -> Reply:
        if not self._q:
            raise TransportTimeout("fara raspuns (simulat)")
        return parse_reply(self._q.popleft())
