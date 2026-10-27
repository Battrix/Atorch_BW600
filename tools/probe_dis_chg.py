"""Descarcare CC 3 A pana la 4.0 V -> pauza 5 s -> CDC nativ (porneste cu incarcarea) cu sursa pe intrarea CHARGER.

SIGURANTA: opreste daca V > 4.23 V, V < 3.9 V, |I| > 3.5 A, MOSFET > 80 C sau la depasirea timpului; opreste sarcina la final
si restaureaza setarile aparatului. Sursa OWON: 4.20 V, limita 0.5 A, iesirea PORNITA. Jurnal: logs/discharge-charge-*.txt.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from atorch.protocol import commands, get_profile, parse_live  # noqa: E402
from atorch.service.logfile import start_log  # noqa: E402
from atorch.transports import TransportError, TransportTimeout  # noqa: E402
from atorch.transports.usb import UsbHidTransport, list_devices  # noqa: E402
from probe_cdc import live_raw, settings, write  # noqa: E402

DIS_A, DIS_V = 3.0, 4.0
V_HI, V_LO, I_MAX, T_MAX = 4.23, 3.9, 3.5, 80.0


def watch(t, prof, label, max_s, stop_when_off=True):
    """Citeste si afiseaza ~1/s. Intoarce motivul opririi."""
    t0 = time.monotonic()
    last, seen_run, off_since = 0.0, False, None
    while time.monotonic() - t0 < max_s:
        try:
            r = live_raw(t)
            lv = parse_live(r, prof)
        except TransportTimeout:
            continue
        pl = bytes(r.payload)
        now = time.monotonic() - t0
        v, i = lv["voltage"], lv["current"]
        seen_run = seen_run or lv.running
        if now - last >= 1.0:
            last = now
            print(f"{label} {now:7.1f}s run={int(lv.running)} V={v:.3f} I={i:.3f} W={lv['power']:.3f} "
                  f"Wh={lv.values.get('energy_wh', 0):.3f} mAh={lv.values.get('capacity_mah', 0):.1f} "
                  f"T={lv.values.get('temp_mos', 0):.0f}  b40-57={pl[40:58].hex(' ')}")
        if v > V_HI or v < V_LO or abs(i) > I_MAX or lv.values.get("temp_mos", 0) > T_MAX:
            return f"limita de siguranta (V={v:.3f} I={i:.3f})"
        if stop_when_off and seen_run and not lv.running:
            off_since = off_since or now
            if now - off_since > 4:
                return "aparatul a oprit sarcina"
        else:
            off_since = None
        time.sleep(0.15)
    return "timp maxim"


def stop_load(t, prof) -> bool:
    for _ in range(6):
        try:
            write(t, commands.run(False))
            if not parse_live(live_raw(t), prof).running:
                return True
        except TransportTimeout:
            continue
    return False


def main() -> int:
    start_log("discharge-charge")
    prof = get_profile("bw600")
    devs = list_devices()
    if not devs:
        print("Niciun aparat USB gasit.")
        return 1
    with UsbHidTransport(devs[0].path) as t:
        orig = settings(t)
        lv0 = parse_live(live_raw(t), prof)
        print(f"Setari originale: mod={int(orig['mode'])} setpoint={orig['setpoint']:.3f} cutoff={orig['cutoff']:.3f} "
              f"full_v={orig['full_voltage']:.3f} full_a={orig['full_current']:.3f}")
        if lv0.running:
            print("Sarcina ruleaza deja; opreste-o si reia.")
            return 1
        v0 = lv0["voltage"]
        if not DIS_V + 0.05 <= v0 <= 4.22:
            print(f"Tensiunea celulei {v0:.3f} V nu e intre {DIS_V + 0.05} si 4.22 V; nu pornesc.")
            return 1
        print(f"Celula: {v0:.3f} V. Sursa OWON trebuie sa fie PORNITA: 4.20 V / 0.5 A, pe intrarea CHARGER.")
        if input("Scrie START ca sa continui: ").strip() != "START":
            print("Anulat.")
            return 0
        try:
            # ---- 1) descarcare CC ----
            for fr in (commands.select_mode(commands.Mode.CC), commands.set_setpoint(DIS_A), commands.set_cutoff(DIS_V)):
                write(t, fr)
            c = settings(t)
            if int(c["mode"]) != 0 or abs(c["setpoint"] - DIS_A) > 1e-3 or abs(c["cutoff"] - DIS_V) > 1e-3:
                print("Setarile CC nu au fost aplicate; nu pornesc.")
                return 3
            print(f"Descarcare CC {DIS_A} A pana la {DIS_V} V...")
            write(t, commands.run(True))
            why = watch(t, prof, "[D]", 600)
            print(f"Descarcarea s-a oprit: {why}")
            ok = stop_load(t, prof)
            if not ok or why.startswith("limita"):
                print("Opresc testul aici.")
                return 4
            # ---- 2) pauza 5 s ----
            print("Pauza 5 s...")
            end = time.monotonic() + 5
            while time.monotonic() < end:
                try:
                    lv = parse_live(live_raw(t), prof)
                    print(f"[P] V={lv['voltage']:.3f} I={lv['current']:.3f}")
                except TransportTimeout:
                    pass
                time.sleep(1.0)
            # ---- 3) CDC nativ: incepe cu incarcarea ----
            for fr in (commands.select_mode(commands.Mode.CDC), commands.set_setpoint(1.0), commands.set_cutoff(DIS_V),
                       commands.set_full_voltage(4.2), commands.set_full_current(0.1)):
                write(t, fr)
            c = settings(t)
            print(f"CDC: mod={int(c['mode'])} setpoint={c['setpoint']:.3f} cutoff={c['cutoff']:.3f} "
                  f"full_v={c['full_voltage']:.3f} full_a={c['full_current']:.3f}")
            if int(c["mode"]) != 7:
                print("Modul CDC nu a fost aplicat; nu pornesc.")
                return 5
            print(">>> Priveste sursa OWON: ce tensiune si curent arata acum? <<<")
            write(t, commands.run(True))
            why = watch(t, prof, "[C]", 20 * 60)
            print(f"CDC s-a oprit: {why}")
        except KeyboardInterrupt:
            print("\nOprit de operator.")
        finally:
            print("Sarcina oprita." if stop_load(t, prof) else "ATENTIE: nu am putut confirma oprirea! Opreste de pe aparat.")
            print("Acum OPRESTE iesirea sursei OWON.")
            try:
                for fr in (commands.set_full_voltage(orig["full_voltage"]), commands.set_full_current(orig["full_current"]),
                           commands.set_cutoff(orig["cutoff"]), commands.select_mode(int(orig["mode"])),
                           commands.set_setpoint(orig["setpoint"])):
                    write(t, fr)
                print("Setari originale restaurate.")
            except TransportTimeout:
                print("Restaurarea setarilor nu a reusit complet; verifica aparatul.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TransportError as e:
        print("EROARE USB:", e)
        raise SystemExit(2)
