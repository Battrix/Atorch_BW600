"""Observare pasiva a aparatului (USB): nu trimite nicio comanda de scriere.

Porneste scriptul, apoi NAVIGHEAZA PE APARAT prin meniu: intra pe rand in CC, CV, CR, CP, BRT, PT, CT,
CDC, CDCDC, CDxn, variantele cu unda, BCT, Dynamic load. La fiecare schimbare vezi ce octeti s-au modificat.
Spune-mi ce mod ai selectat la fiecare linie. Ctrl+C pentru oprire.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atorch.service.sniff import monitor  # noqa: E402
from atorch.transports import TransportError  # noqa: E402
from atorch.transports.usb import UsbHidTransport, list_devices  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=600)
    ap.add_argument("--all", action="store_true", help="arata si octetii zgomotosi (V, A, W, temperaturi)")
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
    print("Navigheaza pe aparat prin meniu. Ctrl+C pentru oprire.\n")
    try:
        with UsbHidTransport(devs[0].path) as t:
            monitor(t, seconds=a.seconds, show_all=a.all)
    except KeyboardInterrupt:
        print("\nOprit.")
    except TransportError as e:
        print("EROARE USB:", e)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
