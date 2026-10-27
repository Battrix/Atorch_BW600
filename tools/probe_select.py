"""Verifica DOAR selectarea modurilor (0..11): trimite comanda de mod, citeste inapoi si noteaza.

NU porneste sarcina. Refuza daca aparatul ruleaza. La final reface modul initial.
Rezultatul se scrie in logs/select-*.txt.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atorch.protocol import commands  # noqa: E402
from atorch.protocol.parsers import parse_live, parse_settings  # noqa: E402
from atorch.protocol.profiles import PROFILES  # noqa: E402
from atorch.service.logfile import start_log  # noqa: E402
from atorch.transports import TransportError  # noqa: E402
from atorch.transports.usb import UsbHidTransport, list_devices  # noqa: E402


def read_mode(t):
    return t.exchange(commands.read_settings(), want_type=0x03).payload


def main() -> int:
    start_log("select")
    prof = PROFILES["bw600"]
    devs = list_devices()
    if not devs:
        print("Niciun aparat USB gasit.")
        return 1
    with UsbHidTransport(devs[0].path) as t:
        live = parse_live(t.exchange(commands.read_live(), want_type=0x05), prof)
        if live.running:
            print("Aparatul RULEAZA. Opreste sarcina de pe aparat si reia.")
            return 1
        before = read_mode(t)
        orig = before[44]
        print(f"Mod initial: {orig}  (byte45={before[45]:02X})")
        try:
            for m in range(0, 12):
                t.send(commands.select_mode(m))
                time.sleep(0.4)
                pl = read_mode(t)
                ok = "OK" if pl[44] == m else f"DIFERIT (a raportat {pl[44]})"
                print(f"select {m:2d} (cmd 0x{0x47 + m:02X}): byte44={pl[44]:02X} byte45={pl[45]:02X} -> {ok}")
                if pl[44] != m and m >= 10:
                    print("  Ma opresc aici, comanda nu pare sa fie selectie de mod.")
                    break
        finally:
            t.send(commands.select_mode(orig))
            time.sleep(0.4)
            print(f"Mod restaurat: {read_mode(t)[44]}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TransportError as e:
        print("EROARE USB:", e)
        raise SystemExit(2)
