"""Monitor CDC nativ. Nu comuta releul si nu inventeaza o comanda Charge ON."""
from __future__ import annotations

import copy
import math
import queue
import threading
import time
import uuid
from pathlib import Path

from atorch.bct.store import _atomic_write, default_data_dir


ACTIVE = {"preparing", "running", "stopping"}


def phase_of(row):
    if not row.get("running"):
        return "idle"
    if row.get("current", 0) < 0.02:
        return "waiting"
    return "discharge" if int(row.get("sign_flags", 0)) & 0x80 else "charge"


def validate(params, snapshot, limits):
    p = dict(params)
    for key in ("current", "empty_v", "full_v", "end_current"):
        if isinstance(p.get(key), bool):
            raise ValueError("valoare numerica invalida")
        p[key] = float(p[key])
        if not math.isfinite(p[key]):
            raise ValueError("valorile trebuie sa fie finite")
    if not snapshot.connected or time.time() - snapshot.updated > 5:
        raise ValueError("nu exista masuratori USB recente")
    if snapshot.running:
        raise ValueError("opreste aparatul inainte de configurare")
    if not limits["cc"][0] <= p["current"] <= limits["cc"][1]:
        raise ValueError("curent de descarcare in afara limitelor")
    if not 0 <= p["empty_v"] < p["full_v"] <= limits["cutoff"][1]:
        raise ValueError("tensiunile trebuie sa respecte 0 <= empty < full")
    if not 0 < p["end_current"] <= limits["cc"][1]:
        raise ValueError("prag de terminare invalid")
    voltage = snapshot.live.get("voltage", 0)
    if not 0 < voltage < p["full_v"]:
        raise ValueError("verifica bateria: tensiunea trebuie sa fie sub pragul full")
    if p["current"] * max(voltage, p["full_v"]) > limits["cp"][1]:
        raise ValueError("puterea de descarcare depaseste limita aparatului")
    if not isinstance(p.get("double_start", True), bool):
        raise ValueError("double_start trebuie sa fie boolean")
    p["double_start"] = p.get("double_start", True)
    p["battery"] = str(p.get("battery", ""))[:160]
    if not isinstance(p.get("manage_charger", False), bool):
        raise ValueError("manage_charger trebuie sa fie boolean")
    p["manage_charger"] = p.get("manage_charger", False)
    if p["manage_charger"]:
        p["charge_current"] = float(p.get("charge_current", 1))
        if not math.isfinite(p["charge_current"]) or not 0 < p["charge_current"] <= 10:
            raise ValueError("curentul OWON trebuie sa fie intre 0 si 10 A")
        if p["full_v"] > 80 or p["full_v"] * p["charge_current"] > 500:
            raise ValueError("limitele SPE8105 sunt 80 V si 500 W")
        if p["end_current"] >= p["charge_current"]:
            raise ValueError("curentul de terminare trebuie sa fie sub curentul de incarcare OWON")
    return p


class CdcEngine:
    def __init__(self, service, root=None, bct=None, charger=None):
        self.svc, self.bct = service, bct
        self.charger = charger
        self.root = Path(root or default_data_dir()) / "cdc"
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.events = queue.Queue(maxsize=2000)
        self.thread = None
        self.test = None
        service.subscribe(self._sample)

    def active(self):
        with self.lock:
            return self.test is not None and self.test["state"] in ACTIVE

    def _sample(self, kind, row):
        if kind == "sample" and self.active():
            try:
                self.events.put_nowait(copy.deepcopy(row))
            except queue.Full:
                self.cancel.set()

    def status(self, samples=False):
        with self.lock:
            if not self.test:
                return {"state": "idle", "phase": "idle", "samples": []}
            out = {k: v for k, v in self.test.items() if k != "samples"}
            if samples:
                out["samples"] = self.test["samples"][-2000:]
            return copy.deepcopy(out)

    def start(self, params):
        with self.lock:
            if self.active() or self.bct and self.bct.active():
                raise ValueError("un test CDC sau BCT este deja activ")
            if self.svc.profile.name != "bw600":
                raise ValueError("CDC este disponibil momentan numai pe profilul BW600 verificat")
            p = validate(params, self.svc.snapshot(), self.svc.profile.limits)
            if p["manage_charger"] and (self.charger is None or not self.charger.snapshot()["connected"]):
                raise ValueError("conecteaza OWON SPE8105 inainte de pornirea CDC")
            self.cancel.clear()
            while not self.events.empty():
                self.events.get_nowait()
            self.test = {"id": uuid.uuid4().hex, "state": "preparing", "phase": "waiting",
                         "started": time.time(), "device": self.svc.profile.title,
                         "params": p, "stages": [], "samples": [], "message": "Configurare si recitire",
                         "stop_confirmed": False, "charger_stop_confirmed": None,
                         "data_gaps": 0, "elapsed": 0}
            self.thread = threading.Thread(target=self._run, daemon=True, name="atorch-cdc")
            self.thread.start()
            return self.test["id"]

    def stop(self):
        self.cancel.set()
        future = self.svc.stop_load()
        if self.active() and self.test["params"].get("manage_charger"):
            try:
                self.charger.output(False)
            except Exception:
                pass  # repeated and reported by finalization
        return future

    def _save(self):
        with self.lock:
            _atomic_write(self.root / (self.test["id"] + ".json"), self.test)

    def history(self):
        items = []
        for file in sorted(self.root.glob("*.json"), reverse=True):
            import json
            try:
                t = json.loads(file.read_text(encoding="utf-8"))
                items.append({k: t.get(k) for k in ("id", "state", "started", "params", "message")})
            except (OSError, ValueError):
                continue
        return sorted(items, key=lambda t: t["started"], reverse=True)[:100]

    def load(self, tid):
        import json
        if len(tid) != 32 or any(c not in "0123456789abcdef" for c in tid):
            raise ValueError("id invalid")
        with self.lock:
            if self.test and tid == self.test["id"]:
                return copy.deepcopy(self.test)
        return json.loads((self.root / (tid + ".json")).read_text(encoding="utf-8"))

    def _command(self, future):
        future.result(15)
        if self.cancel.is_set():
            raise ValueError("test oprit de operator")

    def _run(self):
        p = self.test["params"]
        previous = None
        stage = None
        seen_current = False
        off_since = None
        state, message = "error", "eroare CDC"
        try:
            self._save()  # verify persistence before energising
            self._command(self.svc.set_mode(7))
            for key, val in (("setpoint", p["current"]), ("cutoff", p["empty_v"]),
                             ("full_voltage", p["full_v"]), ("full_current", p["end_current"])):
                self._command(self.svc.set_value(key, val))
            if p["manage_charger"]:
                self.charger.configure(p["full_v"], p["charge_current"])
                if self.cancel.is_set():
                    raise ValueError("test oprit inainte de activarea sursei")
                self.test["charger"] = self.charger.snapshot()
                self.charger.output(True)
            self._command(self.svc.start_cdc(self.cancel, p["double_start"]))
            began = time.monotonic()
            last_rx = began
            last_save = began
            with self.lock:
                self.test.update(state="running", message="Astept curentul masurat")
            while not self.cancel.is_set():
                try:
                    row = self.events.get(timeout=0.25)
                except queue.Empty:
                    if time.monotonic() - last_rx > 5:
                        raise ValueError("conexiune pierduta; date partiale")
                    continue
                now = time.monotonic()
                last_rx = now
                if row["t"] < self.test["started"]:
                    continue
                phase = phase_of(row)
                v, i, w = (row.get(k, 0) for k in ("voltage", "current", "power"))
                if p["manage_charger"]:
                    ch = self.charger.snapshot()
                    if not ch["connected"] or time.time()-ch["updated"] > 5:
                        raise ValueError("conexiune OWON pierduta; oprire CDC")
                    if not ch["output"]:
                        raise ValueError("iesirea OWON este oprita in timpul testului")
                    if ch["voltage"] > p["full_v"] + .03:
                        raise ValueError("tensiune OWON peste pragul full")
                    row = dict(row, charger_voltage=ch["voltage"], charger_current=ch["current"],
                               charger_power=ch["power"], charger_output=ch["output"], charger_updated=ch["updated"])
                if v > p["full_v"] + 0.02:
                    raise ValueError("tensiune peste pragul full; oprire ceruta")
                if phase in ("charge", "discharge"):
                    seen_current = True
                if not seen_current and now - began > 30:
                    raise ValueError("curent absent dupa Start; confirmarea pe display poate fi necesara")
                with self.lock:
                    if stage is None or stage["phase"] != phase:
                        stage = {"phase": phase, "started": row["t"], "ended": row["t"], "ah": 0., "wh": 0.}
                        self.test["stages"].append(stage)
                    if previous and previous["phase"] == phase and phase in ("charge", "discharge"):
                        dt = row["t"] - previous["t"]
                        if 0 < dt <= 2:
                            stage["ah"] += (i + previous["current"]) * dt / 7200
                            stage["wh"] += (w + previous["power"]) * dt / 7200
                        elif dt > 2:
                            self.test["data_gaps"] += 1
                    stage["ended"] = row["t"]
                    row = dict(row, phase=phase)
                    self.test["samples"].append(row)
                    self.test.update(phase=phase, live=row, elapsed=row["t"]-self.test["started"],
                                     message={"charge": "Incarcare", "discharge": "Descarcare", "waiting": "Asteptare / tranzitie", "idle": "Aparat oprit"}[phase])
                previous = row
                if seen_current and not row.get("running") and i < 0.02:
                    off_since = off_since or now
                    if now - off_since >= 1:
                        phases = [x["phase"] for x in self.test["stages"] if x["phase"] in ("charge", "discharge")]
                        complete = any(phases[j:j+3] == ["charge", "discharge", "charge"] for j in range(len(phases)-2))
                        reached = any(x["phase"] == "charge" and x["voltage"] >= p["full_v"]-.03 for x in self.test["samples"])
                        state = "finished" if complete and reached else "incomplete"
                        message = "Secventa CDC observata si prag full atins" if state == "finished" else "Aparatul s-a oprit; secventa sau tensiunea finala nu confirma un CDC complet"
                        break
                else:
                    off_since = None
                if now-last_save >= 3:
                    self._save()
                    last_save = now
            else:
                state, message = "aborted", "Oprit de operator"
        except Exception as e:
            message = str(e)
            state = "aborted" if self.cancel.is_set() else "error"
        finally:
            with self.lock:
                self.test["state"] = "stopping"
            stop_future = self.svc.stop_load()
            charger_ok = None
            if p["manage_charger"]:
                try:
                    self.charger.output(False)
                    charger_ok = True
                except Exception:
                    charger_ok = False
                    message += "; OPRIRE OWON NECONFIRMATA"
            try:
                stop_future.result(15)
                stop_ok = True
            except Exception:
                stop_ok = False
            with self.lock:
                self.test.update(state=state if stop_ok and charger_ok is not False else "error", phase="idle" if stop_ok else "unknown",
                                 stop_confirmed=stop_ok, finished=time.time(),
                                 charger_stop_confirmed=charger_ok,
                                 message=message if stop_ok else message+"; OPRIRE NECONFIRMATA")
            try:
                self._save()
            except OSError as e:
                with self.lock:
                    self.test["message"] += "; salvare esuata: " + str(e)
