"""Pornire: python -m atorch --usb | --sim  [--host 127.0.0.1] [--port 8787]"""
from __future__ import annotations

import argparse
import sys
import webbrowser

from atorch.server.app import create_server
from atorch.service.device import DeviceService


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="atorch", description="Interfata de laborator ATORCH BW600 / BW150")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--usb", action="store_true", help="conectare prin USB HID")
    src.add_argument("--sim", action="store_true", help="aparat simulat (fara hardware)")
    ap.add_argument("--profile", default="bw600", help="bw600 (implicit) sau bw150")
    ap.add_argument("--host", default="127.0.0.1",
                    help="adresa de ascultare; 0.0.0.0 = accesibil din retea (fara autentificare!)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--debug", action="store_true", help="jurnal detaliat: fiecare cadru USB cu timpul de raspuns")
    a = ap.parse_args(argv)
    import logging
    logging.basicConfig(level=logging.DEBUG if a.debug else logging.WARNING,
                        format="%(asctime)s.%(msecs)03d %(name)s: %(message)s", datefmt="%H:%M:%S")

    if a.usb:
        from atorch.transports.usb import UsbHidTransport
        factory, link = (lambda: UsbHidTransport()), "usb"
    else:
        from atorch.transports.simulated import SimCell, SimulatedTransport
        # celula de demonstratie (0,02 Ah): un test BCT dureaza cateva zeci de secunde
        sim = SimulatedTransport(voltage_mv=3400, mode=1, setpoint=5.0, cutoff=3.0,
                                 cell=SimCell(capacity_ah=0.02, v_full=3.4, v_empty=3.0, ri_ohm=0.004))
        factory, link = (lambda: sim), "simulat"

    svc = DeviceService(factory, profile=a.profile)
    svc.start()
    from atorch.bct import BctEngine, TestStore
    store = TestStore()
    store.ensure_seed()
    engine = BctEngine(svc, store)
    srv = create_server(svc, a.host, a.port, link, engine)
    url = f"http://{'127.0.0.1' if a.host == '0.0.0.0' else a.host}:{srv.server_address[1]}/"
    print(f"Atorch Lab: {url}   (Ctrl+C pentru oprire)")
    if a.host not in ("127.0.0.1", "localhost"):
        print("ATENTIE: serverul e accesibil din retea si nu are autentificare.", file=sys.stderr)
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        svc.stop_load()          # la inchidere, sarcina se opreste
        import time
        time.sleep(1.0)
        svc.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
