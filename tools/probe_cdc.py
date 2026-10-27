"""Observa modul CDC nativ al BW600 cu o celula Li-ion 18650 si o sursa reglabila pe intrarea CHARGER.

SIGURANTA: opreste daca V > 4.23 V, V < 3.0 V, |I| > 2 A, MOSFET > 80 C sau la depasirea timpului; opreste sarcina la final
si restaureaza setarile. Sursa trebuie reglata la 4.20 V, limita 0.5 A. Scrie in logs/cdc-*.txt.
Faze: A) sursa oprita, B) sursa pornita dar aparat inactiv (se vede daca apare tensiunea incarcatorului),
C) ruleaza CDC (incarcare -> descarcare -> incarcare) si se noteaza ce se schimba.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atorch.protocol import commands, get_profile, parse_live, parse_settings  # noqa: E402
from atorch.service.logfile import start_log  # noqa: E402
from atorch.transports import TransportError, TransportTimeout  # noqa: E402
from atorch.transports.usb import UsbHidTransport, list_devices  # noqa: E402

V_HI, V_LO, I_MAX, T_MAX = 4.23, 3.0, 2.0, 80.0


def settings(t):
    return parse_settings(t.exchange(commands.read_settings(), want_type=0x03))


def live_raw(t):
    return t.exchange(commands.read_live(), want_type=0x05)


def write(t, frame, pause=0.2):
    t.send(frame)
    time.sleep(pause)
    while True:
        try:
            t.receive(0.03)
        except TransportTimeout:
            return


def snapshot(t, prof, label, seconds=5.0):
    rows = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        try:
            r = live_raw(t)
            rows.append((parse_live(r, prof), bytes(r.payload)))
        except TransportTimeout:
            pass
        time.sleep(0.25)
    if not rows:
        print(f"[{label}] fara date")
        return None
    lv, pl = rows[-1]
    print(f"[{label}] V={lv['voltage']:.3f} I={lv['current']:.3f} run={lv.running}  payload[40:58]={pl[40:58].hex(' ')}  payload={pl.hex(' ')}")
    return rows[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", type=float, default=1.0, help="curent de descarcare A (max 2)")
    ap.add_argument("--cutoff", type=float, default=4.10, help="tensiune de oprire descarcare V")
    ap.add_argument("--full-v", type=float, default=4.20, help="tensiune max incarcare V (max 4.20)")
    ap.add_argument("--full-a", type=float, default=0.10, help="curent final de incarcare A")
    ap.add_argument("--max-min", type=float, default=45.0)
    a = ap.parse_args()
    if not (0 < a.current <= I_MAX and a.full_v <= 4.20 and 3.0 < a.cutoff < a.full_v and 0.02 <= a.full_a <= 0.5):
        print("Parametri in afara limitelor de siguranta.")
        return 2
    start_log("cdc")
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
        if not 3.5 <= lv0["voltage"] <= 4.22:
            print(f"Tensiunea celulei {lv0['voltage']:.3f} V nu e intre 3.5 si 4.22 V; nu pornesc.")
            return 1
        print(f"Celula: {lv0['voltage']:.3f} V")
        input("\nFAZA A: sursa OWON cu iesirea OPRITA. Apasa Enter... ")
        snapshot(t, prof, "A sursa oprita")
        input("\nFAZA B: porneste iesirea sursei (4.20 V, 0.5 A) cu cablurile pe intrarea CHARGER. Apasa Enter... ")
        snapshot(t, prof, "B sursa pornita, aparat inactiv")
        ans = input("\nFAZA C: pornesc CDC (incarcare -> descarcare -> incarcare). Scrie START ca sa continui: ")
        if ans.strip() != "START":
            print("Anulat.")
            return 0
        stopped = False
        try:
            for fr in (commands.select_mode(commands.Mode.CDC), commands.set_setpoint(a.current),
                       commands.set_cutoff(a.cutoff), commands.set_full_voltage(a.full_v),
                       commands.set_full_current(a.full_a)):
                write(t, fr)
            chk = settings(t)
            print(f"Recitire: mod={int(chk['mode'])} setpoint={chk['setpoint']:.3f} cutoff={chk['cutoff']:.3f} "
                  f"full_v={chk['full_voltage']:.3f} full_a={chk['full_current']:.3f}")
            if (int(chk["mode"]) != 7 or abs(chk["setpoint"] - a.current) > 1e-3 or abs(chk["cutoff"] - a.cutoff) > 1e-3
                    or abs(chk["full_voltage"] - a.full_v) > 1e-3 or abs(chk["full_current"] - a.full_a) > 1e-3):
                print("Setarile nu au fost aplicate; nu pornesc.")
                return 3
            write(t, commands.run(True))
            t0 = time.monotonic()
            last_print, seen_run, off_since = 0.0, False, None
            while time.monotonic() - t0 < a.max_min * 60:
                try:
                    r = live_raw(t)
                    lv = parse_live(r, prof)
                except TransportTimeout:
                    continue
                pl = bytes(r.payload)
                now = time.monotonic() - t0
                v, i = lv["voltage"], lv["current"]
                seen_run = seen_run or lv.running
                if now - last_print >= 1.0:
                    last_print = now
                    print(f"{now:7.1f}s run={int(lv.running)} V={v:.3f} I={i:.3f} W={lv['power']:.3f} Wh={lv.values.get('energy_wh', 0):.3f} "
                          f"mAh={lv.values.get('capacity_mah', 0):.1f} T={lv.values.get('temp_mos', 0):.0f}  b40-57={pl[40:58].hex(' ')}")
                if v > V_HI or v < V_LO or abs(i) > I_MAX or lv.values.get("temp_mos", 0) > T_MAX:
                    print(f"!!! limita de siguranta depasita (V={v:.3f} I={i:.3f}); opresc.")
                    break
                if seen_run and not lv.running:
                    off_since = off_since or now
                    if now - off_since > 5:
                        print("Aparatul a oprit singur sarcina; ciclul s-a incheiat.")
                        break
                else:
                    off_since = None
                try:
                    s3 = settings(t)
                    sig = (int(s3["mode"]), round(s3["setpoint"], 3), round(s3["cutoff"], 3))
                    if getattr(main, "_sig", None) != sig:
                        main._sig = sig
                        print(f"{now:7.1f}s [03] mod={sig[0]} setpoint={sig[1]} cutoff={sig[2]}")
                except TransportTimeout:
                    pass
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\nOprit de operator.")
        finally:
            for _ in range(6):
                try:
                    write(t, commands.run(False))
                    if not parse_live(live_raw(t), prof).running:
                        stopped = True
                        break
                except TransportTimeout:
                    continue
            print("Sarcina oprita." if stopped else "ATENTIE: nu am putut confirma oprirea! Opreste de pe aparat.")
            print("Acum OPRESTE iesirea sursei OWON.")
            if stopped:
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
