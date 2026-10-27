"""Serviciul de aparat: un singur fir proprietar al transportului.

- citeste periodic masuratorile (05) si configuratia (03)
- executa comenzi dintr-o coada; scrierile de configuratie se verifica prin recitire
- configuratia este blocata cat timp sarcina e pornita; START/STOP sunt mereu permise
- STOP are prioritate maxima si se reincearca pana e confirmat
- la erori de transport se reconecteaza automat
"""
from __future__ import annotations

import collections
import copy
import logging
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Callable

from atorch.protocol import ProtocolError, commands, get_profile, parse_live, parse_settings
from atorch.transports.base import Transport, TransportError, TransportTimeout

log = logging.getLogger("atorch.service")

MODE_LIMIT_KEYS = {0: "cc", 1: "cv", 2: "cr", 3: "cp", 7: "cc", 8: "cc", 9: "cc"}
# nume -> (functie de constructie, cheie in setari, toleranta)
_FLOAT_SETTINGS = {
    "setpoint": (commands.set_setpoint, "setpoint"),
    "cutoff": (commands.set_cutoff, "cutoff"),
    "full_voltage": (commands.set_full_voltage, "full_voltage"),
    "full_current": (commands.set_full_current, "full_current"),
    "ocp": (commands.set_ocp, "ocp"),
    "opp": (commands.set_opp, "opp"),
    "ntc_otp": (commands.set_ntc_otp, "ntc_otp"),
    "mos_otp": (commands.set_mos_otp, "mos_otp"),
}
_LEVEL_SETTINGS = {
    "brightness": (commands.set_brightness, 0, 9),
    "standby_brightness": (commands.set_standby_brightness, 0, 9),
    "standby_time": (commands.set_standby_time, 0, 255),
}


class CommandRejected(Exception):
    """Comanda a fost refuzata inainte de a fi trimisa (validare, stare)."""


class CommandFailed(Exception):
    """Comanda a fost trimisa dar efectul nu a putut fi confirmat."""


@dataclass
class State:
    connected: bool = False
    running: bool = False
    live: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    last_error: str = ""
    updated: float = 0.0
    seq: int = 0


@dataclass
class _Cmd:
    fn: Callable[[Transport], object]
    future: Future
    priority: int = 1          # 0 = STOP


class DeviceService:
    def __init__(self, transport_factory: Callable[[], Transport], profile: str = "bw600",
                 poll_interval: float = 0.25, settings_interval: float = 2.0,
                 reconnect_delay: float = 2.0, write_pause: float = 0.15,
                 verify_attempts: int = 3):
        self._factory = transport_factory
        self.profile = get_profile(profile)
        self.poll_interval, self.settings_interval = poll_interval, settings_interval
        self.reconnect_delay, self.write_pause = reconnect_delay, write_pause
        self.verify_attempts = verify_attempts
        self.stop_attempts, self.stop_wait = 8, 0.8
        self.max_misses = 5
        self._state = State()
        self._lock = threading.Lock()
        self._subs: list[Callable[[str, dict], None]] = []
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._counter = 0
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._history: collections.deque = collections.deque(maxlen=7200)   # ~30 min la 4 Hz

    # ---- ciclu de viata -------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, name="atorch-device", daemon=True)
        self._thread.start()

    def shutdown(self, timeout: float = 3.0) -> None:
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout)

    # ---- stare si evenimente -------------------------------------------
    def snapshot(self) -> State:
        with self._lock:
            return copy.deepcopy(self._state)

    def history(self) -> list[dict]:
        with self._lock:
            return list(self._history)

    def subscribe(self, cb: Callable[[str, dict], None]) -> None:
        self._subs.append(cb)

    def _emit(self, kind: str, data: dict) -> None:
        for cb in list(self._subs):
            try:
                cb(kind, data)
            except Exception:                       # un abonat defect nu opreste serviciul
                log.exception("abonat defect")

    # ---- API de comenzi (intorc Future) --------------------------------
    def _submit(self, fn, priority: int = 1) -> Future:
        fut: Future = Future()
        self._counter += 1
        self._q.put((priority, self._counter, _Cmd(fn, fut, priority)))
        return fut

    def start_load(self) -> Future:
        return self._submit(lambda t: self._do_run(t, True))

    def stop_load(self) -> Future:
        return self._submit(lambda t: self._do_run(t, False), priority=0)

    def start_cdc(self, cancel: threading.Event, second_start: bool = True) -> Future:
        """Secventa observata pe BW600; STOP poate anula al doilea START."""
        def execute(t):
            if cancel.is_set():
                raise CommandRejected("pornire anulata")
            if self._read_live(t).running:
                raise CommandRejected("aparatul ruleaza deja")
            t.send(commands.run(True))
            if second_start:
                if cancel.wait(1.0):
                    t.send(commands.run(False))
                    raise CommandRejected("pornire anulata")
                t.send(commands.run(True))
            return "Start transmis; se asteapta curentul masurat"
        return self._submit(execute)

    def set_mode(self, mode: int) -> Future:
        if not 0 <= int(mode) <= 9:
            return self._rejected("mod invalid")
        return self._submit(lambda t: self._do_config(
            t, [commands.select_mode(int(mode))], lambda s: int(s["mode"]) == int(mode)))

    def set_value(self, name: str, value: float) -> Future:
        """setpoint, cutoff, full_voltage, full_current, ocp, opp, ntc_otp, mos_otp."""
        if name not in _FLOAT_SETTINGS:
            return self._rejected(f"setare necunoscuta: {name}")
        err = self._check_limits(name, float(value))
        if err:
            return self._rejected(err)
        build, key = _FLOAT_SETTINGS[name]
        return self._submit(lambda t: self._do_config(
            t, [build(float(value))], lambda s: abs(s[key] - float(value)) <= max(1e-3, abs(value) * 1e-5)))

    def set_level(self, name: str, value: int) -> Future:
        if name not in _LEVEL_SETTINGS:
            return self._rejected(f"setare necunoscuta: {name}")
        build, lo, hi = _LEVEL_SETTINGS[name]
        if not lo <= int(value) <= hi:
            return self._rejected(f"{name}: {lo}..{hi}")
        return self._submit(lambda t: self._do_config(
            t, [build(int(value))], lambda s: int(s[name]) == int(value)))

    def set_timer(self, hours: int, minutes: int) -> Future:
        try:
            frames = self.profile.set_timer(int(hours), int(minutes))
        except ProtocolError as e:
            return self._rejected(str(e))
        return self._submit(lambda t: self._do_config(
            t, frames, lambda s: int(s["timer_hours"]) == int(hours) and int(s["timer_minutes"]) == int(minutes)))

    def _rejected(self, msg: str) -> Future:
        f: Future = Future()
        f.set_exception(CommandRejected(msg))
        return f

    def _check_limits(self, name: str, value: float) -> str:
        lim = self.profile.limits
        if name == "setpoint":
            mode = self._state.settings.get("mode")
            key = MODE_LIMIT_KEYS.get(int(mode)) if mode is not None else None
            if key is None:
                return "setpoint-ul nu se poate schimba in acest mod (sau modul e necunoscut)"
            lo, hi = lim[key]
        elif name == "full_voltage":
            lo, hi = lim["cutoff"]
        elif name == "full_current":
            lo, hi = 0.001, lim["cc"][1]
        elif name in lim:
            lo, hi = lim[name]
        else:
            return ""
        if not lo <= value <= hi:
            return f"{name}: {value} in afara limitelor {lo}..{hi}"
        return ""

    # ---- executia comenzilor (in firul serviciului) ---------------------
    def _write(self, t: Transport, frame: bytes) -> None:
        t.send(frame)
        time.sleep(self.write_pause)
        while True:
            try:
                t.receive(0.03)
            except TransportTimeout:
                return

    def _read_settings(self, t: Transport):
        try:
            s = parse_settings(t.exchange(commands.read_settings(), want_type=0x03))
        except TransportTimeout:
            raise TransportTimeout("fara raspuns la citirea configuratiei (03)") from None
        with self._lock:
            self._state.settings = dict(s.values)
        return s

    def _read_live(self, t: Transport):
        try:
            return parse_live(t.exchange(commands.read_live(), want_type=0x05), self.profile)
        except TransportTimeout:
            raise TransportTimeout("fara raspuns la citirea masuratorilor (05)") from None

    def _do_config(self, t: Transport, frames: list[bytes], verify: Callable) -> str:
        if self._read_live(t).running:
            raise CommandRejected("configuratia este blocata cat timp sarcina e pornita")
        for attempt in range(1, self.verify_attempts + 1):
            for f in frames:
                self._write(t, f)
            if verify(self._read_settings(t)):
                return f"confirmat (incercarea {attempt})"
        raise CommandFailed("valoarea nu a fost confirmata de aparat dupa recitire")

    def _do_run(self, t: Transport, on: bool) -> str:
        attempts = self.verify_attempts if on else self.stop_attempts
        for attempt in range(1, attempts + 1):
            self._write(t, commands.run(on))
            deadline = time.monotonic() + (2.0 if on else self.stop_wait)
            while time.monotonic() < deadline:
                live = self._read_live(t)
                if live.running == on and (on or live.get("current", 0) < 0.02):
                    return "pornit" if on else "oprit"
                time.sleep(0.1)
        raise CommandFailed("pornirea nu a fost confirmata" if on else "OPRIREA NU A FOST CONFIRMATA")

    # ---- bucla principala ----------------------------------------------
    def _set_connected(self, ok: bool, err: str = "") -> None:
        with self._lock:
            changed = self._state.connected != ok
            self._state.connected = ok
            self._state.last_error = err
        if changed:
            self._emit("status", {"connected": ok, "error": err})

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            t = None
            try:
                t = self._factory()
                t.open()
                self._set_connected(True)
                self._loop(t)
            except (TransportError, ProtocolError, OSError) as e:
                log.warning("transport: %s", e)
                self._set_connected(False, str(e))
            finally:
                if t is not None:
                    try:
                        t.close()
                    except Exception:
                        pass
            self._stop_evt.wait(self.reconnect_delay)

    def _loop(self, t: Transport) -> None:
        last_settings = 0.0
        misses = 0
        self._read_settings(t)
        while not self._stop_evt.is_set():
            t0 = time.monotonic()
            # comenzi in asteptare (STOP are prioritatea 0)
            while True:
                try:
                    _, _, cmd = self._q.get_nowait()
                except queue.Empty:
                    break
                try:
                    cmd.future.set_result(cmd.fn(t))
                except (CommandRejected, CommandFailed) as e:
                    cmd.future.set_exception(e)
                except TransportTimeout as e:           # un timeout izolat nu inchide conexiunea
                    cmd.future.set_exception(CommandFailed(str(e)))
                except (TransportError, ProtocolError, OSError) as e:
                    cmd.future.set_exception(CommandFailed(f"transport: {e}"))
                    raise
            try:
                live = self._read_live(t)
            except TransportTimeout as e:
                misses += 1
                log.warning("%s (%d/%d)", e, misses, self.max_misses)
                if misses >= self.max_misses:
                    raise
                self._stop_evt.wait(self.poll_interval)
                continue
            misses = 0
            row = dict(live.values, running=live.running, t=time.time())
            with self._lock:
                self._state.live = dict(live.values)
                self._state.running = live.running
                self._state.updated = row["t"]
                self._state.seq += 1
                self._history.append(row)
            self._emit("sample", row)
            if time.monotonic() - last_settings >= self.settings_interval:
                try:
                    self._emit("settings", dict(self._read_settings(t).values))
                except TransportTimeout as e:
                    log.warning("%s", e)
                last_settings = time.monotonic()
            self._stop_evt.wait(max(0.0, self.poll_interval - (time.monotonic() - t0)))
