"""Cauta in masuratori (05) campul care arata tensiunea de pe intrarea incarcatorului. Doar citire.

Pasi (scriptul iti spune cand): 1) incarcatorul DECONECTAT / oprit, 2) CONECTAT si pornit. Dupa fiecare faza apesi Enter.
Compara apoi toate campurile de 4 octeti si arata cele care s-au schimbat. Rezultatul in logs/charger-*.txt.
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atorch.protocol import commands  # noqa: E402
from atorch.service.logfile import start_log  # noqa: E402
from atorch.transports import TransportError, TransportTimeout  # noqa: E402
from atorch.transports.usb import UsbHidTransport, list_devices  # noqa: E402


def capture(t, seconds=6.0):
    rows = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        try:
            rows.append(bytes(t.exchange(commands.read_live(), want_type=0x05).payload))
        except TransportTimeout:
            pass
        time.sleep(0.25)
    return rows


def u32(b, o):
    return int.from_bytes(b[o:o + 4], "little")


def summarize(rows):
    """Pentru fiecare offset de 4 octeti: valoarea mediana (u32 little-endian) si octetul brut cel mai frecvent."""
    out = {}
    for o in range(0, 56, 1):
        vals = [u32(r, o) for r in rows if len(r) >= o + 4]
        if vals:
            out[o] = int(statistics.median(vals))
    return out


def main() -> int:
    start_log("charger")
    devs = list_devices()
    if not devs:
        print("Niciun aparat USB gasit.")
        return 1
    with UsbHidTransport(devs[0].path) as t:
        input("\nFAZA 1: incarcatorul DECONECTAT de la aparat (sau oprit). Apasa Enter... ")
        a = capture(t)
        print(f"  {len(a)} citiri.")
        print("  payload 05 (ultima):", a[-1].hex(" "))
        input("\nFAZA 2: conecteaza incarcatorul la intrarea CHARGER si PORNESTE-L. Apasa Enter... ")
        b = capture(t)
        print(f"  {len(b)} citiri.")
        print("  payload 05 (ultima):", b[-1].hex(" "))
    if not a or not b:
        print("Prea putine citiri, repeta.")
        return 2
    sa, sb = summarize(a), summarize(b)
    print("\nDiferente (offset octet: deconectat -> conectat). Valorile mari sunt u32 little-endian; /1000 pentru volti:")
    for o in sorted(sa):
        if sa[o] != sb.get(o):
            print(f"  off {o:2d}: {sa[o]:>12d} -> {sb[o]:>12d}   (/1000: {sa[o] / 1000:.3f} -> {sb[o] / 1000:.3f})")
    print("\nGata. Spune-mi doar ca s-a terminat; citesc eu fisierul din logs/.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TransportError as e:
        print("EROARE USB:", e)
        raise SystemExit(2)
