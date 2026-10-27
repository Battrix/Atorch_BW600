"""Test de sarcina CC scurt (BW600, USB). PORNESTE sarcina pentru cateva secunde.

Verifica scara curentului si a puterii: mod CC, 0.5 A, cutoff 3.1 V, 6 secunde, apoi oprire
si restaurarea setarilor originale. Pentru celula LiFePO4/Li-ion de 2.5..4.2 V.

Rulare:   py tools\\probe_load.py
Optiuni:  --current 0.5   --cutoff 3.1   --seconds 6   (max 1.0 A, max 20 s)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atorch.service.selftest import SelfTestAbort, run_cc_selftest  # noqa: E402
from atorch.transports import TransportError  # noqa: E402
from atorch.transports.usb import UsbHidTransport, list_devices  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", type=float, default=0.5)
    ap.add_argument("--cutoff", type=float, default=3.1)
    ap.add_argument("--seconds", type=float, default=6.0)
    a = ap.parse_args()
    try:
        devs = list_devices()
    except TransportError as e:
        print("EROARE:", e)
        return 2
    if not devs:
        print("Niciun aparat USB gasit.")
        return 1
    print(f"Aparat: {devs[0]}")
    print(f"Voi porni sarcina in CC la {a.current} A, cutoff {a.cutoff} V, {a.seconds} s.")
    print("Verifica: celula conectata cu polaritatea corecta, multimetru in paralel.")
    if input("Scrie START si Enter pentru a continua (orice altceva anuleaza): ").strip() != "START":
        print("Anulat.")
        return 0
    try:
        with UsbHidTransport(devs[0].path) as t:
            r = run_cc_selftest(t, "bw600", a.current, a.cutoff, a.seconds)
    except SelfTestAbort as e:
        print("OPRIT DIN SIGURANTA:", e)
        return 3
    except TransportError as e:
        print("EROARE USB:", e)
        return 2
    print("\nRezultat:", "OK" if r.stopped_ok and r.restored_ok else "VERIFICA APARATUL")
    return 0 if r.stopped_ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
