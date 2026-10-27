"""Observare PASIVA: citeste periodic 03 (configuratie) si 05 (masuratori) si arata ce octeti se schimba.

Folosit pentru a descoperi cum raporteaza aparatul modurile care nu sunt documentate (BCT, Dynamic load,
variantele cu unda, BRT/PT/CT...). Utilizatorul navigheaza in meniul aparatului; scriptul noteaza schimbarile.
Trimite NUMAI comenzile de citire 03 si 05.
"""
from __future__ import annotations

import time
from typing import Callable

from atorch.protocol import commands
from atorch.transports.base import Transport, TransportTimeout

# octeti din payload-ul 05 care variaza continuu (V, A, W, temperaturi, ventilator); ascunsi implicit
NOISY_LIVE = set(range(4, 16)) | set(range(28, 44))


def _hex(b: bytes) -> str:
    return b.hex(" ")


def monitor(t: Transport, seconds: float = 120.0, interval: float = 0.5, show_all: bool = False,
            say: Callable[[str], None] = print, stop: Callable[[], bool] = lambda: False) -> list[str]:
    """Intoarce lista de linii afisate. Se opreste dupa `seconds` sau cand stop() e adevarat."""
    out: list[str] = []

    def emit(msg: str) -> None:
        out.append(msg)
        say(msg)

    prev: dict[int, bytes] = {}
    t0 = time.monotonic()
    first = True
    while time.monotonic() - t0 < seconds and not stop():
        for cmd_frame, typ in ((commands.read_settings(), 0x03), (commands.read_live(), 0x05)):
            try:
                pl = t.exchange(cmd_frame, want_type=typ).payload
            except TransportTimeout:
                continue
            if first:
                emit(f"[{typ:02X}] initial: {_hex(pl)}")
            elif typ in prev and pl != prev[typ]:
                ts = time.monotonic() - t0
                diffs = []
                for i, (a, b) in enumerate(zip(prev[typ], pl)):
                    if a != b and (show_all or typ == 0x03 or i not in NOISY_LIVE):
                        diffs.append(f"off {i}: {a:02X} -> {b:02X}")
                if diffs:
                    emit(f"{ts:7.1f}s [{typ:02X}] " + "; ".join(diffs))
            prev[typ] = pl
        first = False
        time.sleep(interval)
    return out
