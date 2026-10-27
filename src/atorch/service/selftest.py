"""Test de sarcina CC scurt si sigur, pentru verificarea scarii curentului si a puterii.

Garantii:
- refuza sa porneasca daca tensiunea citita e in afara 2.5..4.2 V (pentru celula LiFePO4/Li-ion de test)
- limiteaza curentul la max 1.0 A si durata la max 20 s
- seteaza cutoff sub tensiunea curenta, verifica prin recitire modul, setpoint si cutoff INAINTE de pornire
- opreste sarcina intr-un `finally` (cu reincercari) si verifica oprirea
- restaureaza modul, setpoint-ul si cutoff-ul originale ale aparatului
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from atorch.protocol import commands, get_profile, parse_live, parse_settings
from atorch.transports.base import Transport, TransportTimeout

MAX_CURRENT = 1.0
MAX_SECONDS = 20.0
V_MIN, V_MAX = 2.5, 4.2


class SelfTestAbort(Exception):
    pass


@dataclass
class SelfTestResult:
    samples: list[dict] = field(default_factory=list)
    stopped_ok: bool = False
    restored_ok: bool = False
    log: list[str] = field(default_factory=list)


def _drain(t: Transport) -> None:
    while True:
        try:
            t.receive(0.03)
        except TransportTimeout:
            return


def _write(t: Transport, frame: bytes, pause: float) -> None:
    t.send(frame)
    time.sleep(pause)
    _drain(t)


def _settings(t: Transport):
    return parse_settings(t.exchange(commands.read_settings(), want_type=0x03))


def _live(t: Transport, profile):
    return parse_live(t.exchange(commands.read_live(), want_type=0x05), profile)


def run_cc_selftest(t: Transport, profile_name: str = "bw600", current: float = 0.5,
                    cutoff: float = 3.1, seconds: float = 6.0, pause: float = 0.15,
                    say: Callable[[str], None] = print) -> SelfTestResult:
    if not 0 < current <= MAX_CURRENT:
        raise SelfTestAbort(f"curent {current} A in afara 0..{MAX_CURRENT} A")
    if not 0 < seconds <= MAX_SECONDS:
        raise SelfTestAbort(f"durata {seconds} s in afara 0..{MAX_SECONDS} s")
    profile = get_profile(profile_name)
    res = SelfTestResult()

    def log(msg: str) -> None:
        res.log.append(msg)
        say(msg)

    orig = _settings(t)
    live0 = _live(t, profile)
    log(f"Setari originale: mod={int(orig['mode'])} setpoint={orig['setpoint']:.3f} cutoff={orig['cutoff']:.3f}")
    if live0.running:
        raise SelfTestAbort("sarcina este deja pornita; opreste-o intai")
    v0 = live0["voltage"]
    if not V_MIN <= v0 <= V_MAX:
        raise SelfTestAbort(f"tensiune {v0:.3f} V in afara {V_MIN}..{V_MAX} V; nu pornesc")
    if cutoff >= v0:
        raise SelfTestAbort(f"cutoff {cutoff} V nu e sub tensiunea celulei {v0:.3f} V")
    log(f"Tensiune celula: {v0:.3f} V; test CC {current} A, cutoff {cutoff} V, {seconds} s")

    try:
        _write(t, commands.select_mode(commands.Mode.CC), pause)
        _write(t, commands.set_setpoint(current), pause)
        _write(t, commands.set_cutoff(cutoff), pause)
        chk = _settings(t)
        ok = (int(chk["mode"]) == 0 and abs(chk["setpoint"] - current) < 1e-3
              and abs(chk["cutoff"] - cutoff) < 1e-3)
        log(f"Recitire: mod={int(chk['mode'])} setpoint={chk['setpoint']:.3f} cutoff={chk['cutoff']:.3f}")
        if not ok:
            raise SelfTestAbort("setarile nu au fost aplicate; nu pornesc sarcina")

        _write(t, commands.run(True), pause)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            s = _live(t, profile)
            row = {"t": round(seconds - (end - time.monotonic()), 2), "v": s["voltage"],
                   "i": s["current"], "p": s["power"], "run": s.running}
            res.samples.append(row)
            log(f"  t={row['t']:5.2f}s  V={row['v']:.3f}  I={row['i']:.3f}  P={row['p']:.3f}  run={row['run']}")
            if s["current"] > MAX_CURRENT * 1.5:
                raise SelfTestAbort(f"curent {s['current']:.3f} A prea mare; opresc")
            time.sleep(0.25)
    finally:
        for _ in range(5):                      # oprire garantata, cu reincercari
            try:
                _write(t, commands.run(False), pause)
                if not _live(t, profile).running:
                    res.stopped_ok = True
                    break
            except TransportTimeout:
                continue
        log("Sarcina oprita." if res.stopped_ok else "ATENTIE: nu am putut confirma oprirea! Opreste manual de pe aparat.")
        if res.stopped_ok:
            try:
                _write(t, commands.set_cutoff(orig["cutoff"]), pause)
                _write(t, commands.select_mode(int(orig["mode"])), pause)
                _write(t, commands.set_setpoint(orig["setpoint"]), pause)
                fin = _settings(t)
                res.restored_ok = (int(fin["mode"]) == int(orig["mode"])
                                   and abs(fin["setpoint"] - orig["setpoint"]) < 1e-3
                                   and abs(fin["cutoff"] - orig["cutoff"]) < 1e-3)
            except TransportTimeout:
                res.restored_ok = False
            log("Setari originale restaurate." if res.restored_ok else "ATENTIE: setarile originale nu au fost restaurate complet; verifica aparatul.")
    return res
