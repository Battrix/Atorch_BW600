"""Motorul BCT: ruleaza in PC si foloseste aparatul in modul CC.

Pasi: validare -> configurare (CC, curent, tensiune de oprire) -> pornire -> inregistrare (Ah, Wh, rezistenta
interna din caderea de tensiune la pornire) -> oprire la tensiunea de descarcat (o aplica aparatul insusi;
PC-ul o verifica in plus) -> rezultat POZITIV / NEGATIV / NEFINALIZAT.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeout

from atorch.service.device import CommandFailed, CommandRejected, DeviceService
from .catalog import BatteryError, validate_battery
from .store import TestStore

log = logging.getLogger("atorch.bct")

IDLE, PREPARING, RUNNING, FINISHED, ABORTED, ERROR = "idle", "preparing", "running", "finished", "aborted", "error"
ACTIVE = (PREPARING, RUNNING)


class BctError(Exception):
    """Testul nu poate porni (validare, stare aparat)."""


def validate_params(battery: dict, service_state, limits: dict) -> float:
    """Verificari inainte de pornire. Intoarce tensiunea in repaus masurata (OCV)."""
    try:
        validate_battery(battery)
    except BatteryError as e:
        raise BctError(str(e)) from None
    if not service_state.connected:
        raise BctError("aparatul nu este conectat")
    if service_state.running:
        raise BctError("sarcina rulează deja; oprește-o înainte de test")
    ocv = service_state.live.get("voltage")
    if ocv is None:
        raise BctError("nu am o măsurătoare de tensiune de la aparat")
    i = battery["discharge_a"]
    lo, hi = limits["cc"]
    if not lo <= i <= hi:
        raise BctError(f"curentul de descărcare {i} A e în afara limitelor aparatului ({lo}..{hi} A)")
    if i * ocv > limits["opp"][1]:
        raise BctError(f"puterea {i * ocv:.0f} W depășește limita aparatului ({limits['opp'][1]:.0f} W)")
    if ocv < battery["empty_v"] + 0.05:
        raise BctError(f"bateria are {ocv:.3f} V, la sau sub tensiunea de descărcat ({battery['empty_v']} V); "
                       "nu are ce să descarce")
    if ocv > battery["full_v"] * 1.08:
        raise BctError(f"bateria are {ocv:.3f} V, mult peste tensiunea full ({battery['full_v']} V); verifică datele")
    return float(ocv)


class BctEngine:
    def __init__(self, service: DeviceService, store: TestStore | None = None, min_dt: float = 1.0,
                 settle_tol: float = 0.05, settle_timeout: float = 15.0, start_timeout: float = 10.0,
                 silence_timeout: float = 15.0):
        self.svc, self.store = service, store or TestStore()
        self.min_dt, self.settle_tol, self.settle_timeout = min_dt, settle_tol, settle_timeout
        self.start_timeout, self.silence_timeout = start_timeout, silence_timeout
        self._lock = threading.Lock()
        self._q: queue.Queue = queue.Queue(maxsize=20000)
        self._abort = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = self._blank()
        self._test: dict | None = None
        self._listeners: list = []
        service.subscribe(self._on_event)

    # ---- API --------------------------------------------------------------
    def subscribe(self, cb) -> None:
        self._listeners.append(cb)

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def current_test(self) -> dict | None:
        with self._lock:
            return dict(self._test) if self._test else None

    def get_test(self, tid: str) -> dict:
        """Testul in curs (cu esantioane) sau unul salvat. KeyError daca nu exista."""
        with self._lock:
            if self._test and self._test["id"] == tid:
                return dict(self._test, samples=list(self._test["samples"]))
        return self.store.load_test(tid)

    def active(self) -> bool:
        return self._status["state"] in ACTIVE

    def start(self, battery: dict, extra: dict | None = None) -> str:
        if self.active():
            raise BctError("un test este deja în curs")
        ocv = validate_params(battery, self.svc.snapshot(), self.svc.profile.limits)
        tid = self.store.new_test_id()
        self._abort.clear()
        while not self._q.empty():
            self._q.get_nowait()
        with self._lock:
            self._test = {"id": tid, "state": PREPARING, "battery": dict(battery), "extra": dict(extra or {}),
                          "device": self.svc.profile.title, "ocv_start": ocv, "started": time.time(),
                          "samples": [], "result": None}
            self._status = dict(self._blank(), state=PREPARING, id=tid, message="Pregătesc aparatul…",
                                battery=dict(battery), ocv=ocv)
        self._thread = threading.Thread(target=self._run, args=(tid,), name="atorch-bct", daemon=True)
        self._thread.start()
        self._notify()
        return tid

    def stop(self) -> None:
        self._abort.set()

    def join(self, timeout: float = 10.0) -> None:
        if self._thread:
            self._thread.join(timeout)

    # ---- intern -------------------------------------------------------------
    @staticmethod
    def _blank() -> dict:
        return {"state": IDLE, "id": None, "message": "", "elapsed": 0.0, "ah": 0.0, "wh": 0.0, "ocv": None,
                "ri_mohm": None, "v": None, "i": None, "soc_pct": None, "result": None, "battery": None}

    def _notify(self) -> None:
        st = self.status()
        for cb in list(self._listeners):
            try:
                cb("bct", st)
            except Exception:
                log.exception("abonat BCT defect")

    def _on_event(self, kind: str, data: dict) -> None:
        if kind == "sample" and self.active():
            try:
                self._q.put_nowait(data)
            except queue.Full:
                pass

    def _set(self, **kw) -> None:
        with self._lock:
            self._status.update(kw)

    def _cfg(self, fut, what: str):
        try:
            return fut.result(8)
        except (CommandRejected, CommandFailed) as e:
            raise BctError(f"{what}: {e}") from None
        except FutureTimeout:
            raise BctError(f"{what}: aparatul nu a răspuns") from None

    def _run(self, tid: str) -> None:
        t = self._test
        b = t["battery"]
        state, message = ERROR, ""
        try:
            self._cfg(self.svc.set_mode(0), "mod CC")
            self._cfg(self.svc.set_value("cutoff", b["empty_v"]), "tensiune de oprire")
            self._cfg(self.svc.set_value("setpoint", b["discharge_a"]), "curent de descărcare")
            self._cfg(self.svc.set_value("full_voltage", b["full_v"]), "tensiune full")
            if self._abort.is_set():
                raise BctError("întrerupt înainte de pornire")
            self._cfg(self.svc.start_load(), "pornire sarcină")
            state, message = self._record(t, b)
        except BctError as e:
            state, message = (ABORTED if self._abort.is_set() else ERROR), str(e)
        except Exception as e:                      # orice eroare: sarcina trebuie oprita
            log.exception("eroare BCT")
            state, message = ERROR, f"eroare interna: {e}"
        finally:
            self._ensure_stopped()
            self._finish(t, state, message)

    def _ensure_stopped(self) -> None:
        try:
            if self.svc.snapshot().running:
                self.svc.stop_load().result(15)
        except Exception as e:
            log.error("oprirea sarcinii la final a esuat: %s", e)
            self._set(message="ATENȚIE: nu am putut confirma oprirea sarcinii. Oprește de pe aparat.")

    def _record(self, t: dict, b: dict):
        t0 = time.time()
        t["t0"] = t0
        self._set(state=RUNNING, message="Descărcare în curs")
        with self._lock:
            t["state"] = RUNNING
        ah = wh = 0.0
        prev = None
        last_store = -1e9
        seen_running = False
        settled_at = None
        ri = None
        below = 0
        last_rx = time.monotonic()
        sp = b["discharge_a"]
        self._notify()
        while True:
            if self._abort.is_set():
                self._cfg(self.svc.stop_load(), "oprire")
                return ABORTED, "Test oprit de operator"
            try:
                row = self._q.get(timeout=0.5)
            except queue.Empty:
                if time.monotonic() - last_rx > self.silence_timeout:
                    return ABORTED, "Conexiunea cu aparatul s-a pierdut; datele sunt parțiale"
                continue
            last_rx = time.monotonic()
            ts = row["t"]
            if ts < t0:
                continue
            v, i, w = row.get("voltage", 0.0), row.get("current", 0.0), row.get("power", 0.0)
            running = row.get("running", False)
            if running:
                seen_running = True
            elif not seen_running:
                if ts - t0 > self.start_timeout:
                    return ERROR, "Sarcina nu a pornit"
                continue
            if prev is not None and running:
                dt = ts - prev[0]
                if 0 < dt < 5:                         # trapez; goluri mari nu se integreaza
                    ah += (i + prev[1]) / 2 * dt / 3600
                    wh += (w + prev[2]) / 2 * dt / 3600
            prev = (ts, i, w)
            if running and ri is None and sp > 0:
                if abs(i - sp) <= self.settle_tol * sp:
                    ri = max(0.0, (t["ocv_start"] - v) / i * 1000)
                    settled_at = ts
                elif ts - t0 > self.settle_timeout:
                    ri = float("nan")
            rel = ts - t0
            if rel - last_store >= self.min_dt:
                last_store = rel
                s = [round(rel, 2), round(v, 4), round(i, 4), round(w, 3),
                     row.get("temp_mos"), row.get("temp_probe")]
                with self._lock:
                    t["samples"].append(s)
            span = b["full_v"] - b["empty_v"]
            self._set(elapsed=rel, ah=ah, wh=wh, v=v, i=i, ri_mohm=None if ri != ri else ri,
                      soc_pct=max(0.0, min(100.0, (v - b["empty_v"]) / span * 100)))
            self._notify()
            if running:
                below = below + 1 if v <= b["empty_v"] else 0
                if below >= 3:                          # al doilea nivel de siguranta, pe langa cel al aparatului
                    self._cfg(self.svc.stop_load(), "oprire la tensiune")
                    return FINISHED, "Tensiunea de descărcat atinsă"
            elif v > b["empty_v"] + 0.05:
                return ABORTED, "Sarcina a fost oprită de pe aparat înainte de tensiunea de descărcat"
            else:
                return FINISHED, "Tensiunea de descărcat atinsă (aparatul a oprit sarcina)"

    def _finish(self, t: dict, state: str, message: str) -> None:
        st = self.status()
        b = t["battery"]
        ah, wh = st["ah"], st["wh"]
        ri = st["ri_mohm"]
        pct = ah / b["rated_ah"] * 100 if b["rated_ah"] else 0.0
        dur = st["elapsed"]
        if state == FINISHED:
            ok_cap = pct >= b["pass_pct"]
            ri_max = b.get("ri_max_mohm")
            ok_ri = True if (ri_max is None or ri is None) else ri <= ri_max
            verdict = "POZITIV" if (ok_cap and ok_ri) else "NEGATIV"
            reasons = []
            if not ok_cap:
                reasons.append(f"capacitate {pct:.1f}% sub pragul de {b['pass_pct']:.0f}%")
            if not ok_ri:
                reasons.append(f"rezistență internă {ri:.1f} mΩ peste limita de {ri_max} mΩ")
        else:
            verdict, ok_cap, ok_ri, reasons = "NEFINALIZAT", None, None, [message]
        result = {"verdict": verdict, "capacity_ah": round(ah, 4), "energy_wh": round(wh, 3),
                  "capacity_pct": round(pct, 2), "duration_s": round(dur, 1), "ri_mohm": None if ri is None else round(ri, 2),
                  "ocv_start": t["ocv_start"], "v_end": st["v"], "reasons": reasons, "end_reason": message}
        with self._lock:
            t["state"], t["result"], t["finished"] = state, result, time.time()
            self._status.update(state=state, message=message, result=result)
        try:
            self.store.save_test(dict(t))
        except OSError as e:
            log.error("nu am putut salva testul: %s", e)
            self._set(message=message + f" (salvarea a eșuat: {e})")
        self._notify()
