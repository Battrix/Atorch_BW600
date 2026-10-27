"""Transport USB HID (VID 0483, PID 5750) pe baza bibliotecii `hidapi` (modulul `hid`).

Functioneaza pe Windows, Linux (x86/ARM) si macOS. Pe Linux este nevoie de o regula udev
(vezi packaging/). Biblioteca se importa tarziu, ca restul pachetului sa mearga fara ea.
"""
from __future__ import annotations

import logging
import time

from atorch.protocol import FRAME_LEN, ProtocolError, hid_report, parse_reply
from atorch.protocol.frames import Reply
from ..base import DeviceInfo, Transport, TransportError, TransportTimeout

log = logging.getLogger("atorch.usb")

VID = 0x0483
PID = 0x5750


def _hid():
    try:
        import hid  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise TransportError("lipseste `hidapi`: pip install hidapi") from e
    return hid


def list_devices(hid_module=None) -> list[DeviceInfo]:
    hid = hid_module or _hid()
    out = []
    for d in hid.enumerate(VID, PID):
        path = d["path"]
        if isinstance(path, bytes):
            path = path.decode(errors="replace")
        out.append(DeviceInfo(
            transport="usb", path=path,
            product=d.get("product_string") or "",
            serial=d.get("serial_number") or "",
            extra=f"interfata {d.get('interface_number', '?')}",
        ))
    return out


class UsbHidTransport(Transport):
    name = "usb"
    _t_tx = 0.0

    def __init__(self, path: str | None = None, hid_module=None):
        self._hid = hid_module or _hid()
        self._path = path
        self._dev = None

    def open(self) -> None:
        dev = self._hid.device()
        try:
            path = self._path
            if not path:                       # ca in scripturile de test: se deschide pe calea exacta
                found = list_devices(self._hid)
                path = found[0].path if found else None
            if path:
                log.debug("deschid %s", path)
                dev.open_path(path.encode() if isinstance(path, str) else path)
            else:
                dev.open(VID, PID)
        except (OSError, ValueError) as e:
            raise TransportError(f"nu pot deschide aparatul USB: {e}") from e
        self._dev = dev

    def close(self) -> None:
        if self._dev is not None:
            try:
                self._dev.close()
            finally:
                self._dev = None

    def send(self, frame: bytes) -> None:
        if self._dev is None:
            raise TransportError("transport inchis")
        self._flush()
        log.debug("TX %s", frame[:12].hex(" "))
        self._t_tx = time.monotonic()
        n = self._dev.write(hid_report(frame))
        if n is not None and n < 0:
            raise TransportError("scriere HID esuata")

    def _flush(self) -> None:
        """Arunca raspunsurile ramase in coada (intarziate sau neasteptate)."""
        for _ in range(16):
            stale = self._dev.read(FRAME_LEN + 1, 0)
            if not stale:
                return
            log.debug("arunc raspuns vechi %s", bytes(stale)[:8].hex(" "))

    def receive(self, timeout: float = 0.8) -> Reply:
        if self._dev is None:
            raise TransportError("transport inchis")
        data = self._dev.read(FRAME_LEN + 1, int(timeout * 1000))
        if not data:
            log.debug("timeout dupa %.0f ms", (time.monotonic() - getattr(self, "_t_tx", 0)) * 1000)
            raise TransportTimeout("fara raspuns")
        log.debug("RX %s (%.0f ms)", bytes(data)[:8].hex(" "), (time.monotonic() - getattr(self, "_t_tx", 0)) * 1000)
        try:
            return parse_reply(bytes(data))
        except ProtocolError as e:
            raise TransportError(f"raspuns invalid: {e}") from e
