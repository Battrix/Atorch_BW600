"""Test USB DOAR PENTRU CITIRE: trimite numai comenzile 03 si 05 si afiseaza ce primeste.

Nu trimite nicio comanda de scriere/pornire. Decodeaza masuratorile cu profilurile BW600
(sq6emm) si BW600-doc, ca sa vedem pe aparat care dintre ele are valori credibile.

Rulare (din radacina repo-ului):
    pip install -e .[usb]
    python tools/probe_read.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atorch.protocol import commands, get_profile, parse_live, parse_settings  # noqa: E402
from atorch.transports import TransportError  # noqa: E402
from atorch.transports.usb import UsbHidTransport, list_devices  # noqa: E402


def fmt(live) -> str:
    keys = ["voltage", "current", "power", "resistance", "energy_wh", "capacity_mah",
            "temp_cpu", "temp_probe", "temp_mos", "temp_aux", "fan", "raw_counter"]
    return "  ".join(f"{k}={live[k]:.3f}" for k in keys if k in live.values) + f"  run={live.running}"


def main() -> int:
    try:
        devs = list_devices()
    except TransportError as e:
        print("EROARE:", e)
        return 2
    if not devs:
        print("Niciun aparat USB 0483:5750 gasit.")
        return 1
    for i, d in enumerate(devs):
        print(f"[{i}] {d}   cale={d.path}")
    dev = devs[0]
    print(f"\nFolosesc: {dev}\n")
    with UsbHidTransport(dev.path) as t:
        s = parse_settings(t.exchange(commands.read_settings(), want_type=0x03))
        print("CONFIGURATIE:")
        for k, v in s.values.items():
            print(f"  {k:20s} {v}")
        live_reply = t.exchange(commands.read_live(), want_type=0x05)
        print("\nRAW payload 05 (primii 58 B):\n ", live_reply.payload.hex(" "))
        for name in ("bw600", "bw600-doc", "bw150"):
            print(f"\nProfil {name}:")
            print("  ", fmt(parse_live(live_reply, get_profile(name))))
    print("\nGata. Copiaza tot textul de mai sus si trimite-mi-l.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
