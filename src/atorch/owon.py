"""OWON SPE8105 SCPI, USB serial 115200 8N1. Connection never enables output."""
from __future__ import annotations

import copy
import math
import threading
import time


class OwonError(ValueError):
    pass


def number(text):
    try:
        value = float(text.strip())
    except (ValueError, TypeError):
        raise OwonError("raspuns numeric OWON invalid") from None
    if not math.isfinite(value):
        raise OwonError("raspuns OWON ne-finit")
    return value


class OwonSupply:
    def __init__(self, port_factory=None, simulated=False):
        self.lock = threading.RLock()
        self.io = None
        self.factory = port_factory
        self.simulated = simulated
        self.stop_poll = threading.Event()
        self.thread = None
        self.state = dict(connected=False, identity="", port="", error="", updated=0,
                          output=False, voltage=0., current=0., power=0., set_voltage=0., set_current=0.)

    def ports(self):
        if self.simulated:
            return [{"port": "SIMULATOR", "description": "OWON simulat, fara acces hardware"}]
        try:
            from serial.tools.list_ports import comports
            return [{"port": p.device, "description": p.description} for p in comports()]
        except ImportError:
            return []

    def snapshot(self):
        with self.lock:
            if self.simulated and self.state["connected"]:
                self.state["updated"] = time.time()
            return copy.deepcopy(self.state)

    def _query(self, command):
        self.io.write((command + "\n").encode("ascii"))
        raw = self.io.read_until(b"\n", 256)
        if not raw or not raw.endswith(b"\n"):
            raise OwonError("OWON nu raspunde la " + command)
        return raw.decode("ascii", errors="strict").strip()

    def _write(self, command):
        if not self.io:
            raise OwonError("OWON nu este conectat")
        self.io.write((command + "\n").encode("ascii"))

    def connect(self, port):
        if self.io or self.state["connected"]:
            raise OwonError("deconecteaza sursa existenta inainte de reconectare")
        if port not in {p["port"] for p in self.ports()} and self.factory is None:
            raise OwonError("alege un port serial disponibil")
        with self.lock:
            try:
                if self.simulated:
                    self.state.update(connected=True, port="SIMULATOR", identity="OWON,SPE8105,SIMULATOR,DEMO",
                                      set_voltage=4.1, set_current=1., error="", updated=time.time())
                    return self.snapshot()
                factory = self.factory
                if factory is None:
                    try:
                        from serial import Serial
                    except ImportError:
                        raise OwonError("lipseste pyserial: pip install -e .[charger]") from None
                    factory = Serial
                self.io = factory(port=port, baudrate=115200, timeout=.8, write_timeout=.8)
                self.io.reset_input_buffer()
                identity = self._query("*IDN?")
                parts = identity.upper().split(",")
                if len(parts) < 2 or parts[0] != "OWON" or parts[1] != "SPE8105":
                    raise OwonError("model neacceptat: " + identity)
                self.state.update(identity=identity, port=port)
                self._refresh()
                self.stop_poll.clear()
                self.thread = threading.Thread(target=self._poll, daemon=True, name="owon-monitor")
                self.thread.start()
                return self.snapshot()
            except Exception as e:
                if self.io:
                    self.io.close()
                    self.io = None
                self.state.update(connected=False, error=str(e))
                raise OwonError(str(e)) from e

    def _refresh(self):
        values = {"set_voltage": number(self._query("VOLT?")),
                  "set_current": number(self._query("CURR?"))}
        output = self._query("OUTP?").upper()
        if output not in ("ON", "OFF", "1", "0"):
            raise OwonError("stare iesire OWON necunoscuta: " + output)
        values.update(output=output in ("ON", "1"), voltage=number(self._query("MEAS:VOLT?")),
                      current=number(self._query("MEAS:CURR?")), power=number(self._query("MEAS:POW?")))
        self.state.update(values, connected=True, error="", updated=time.time())

    def _poll(self):
        while not self.stop_poll.wait(1):
            with self.lock:
                try:
                    self._refresh()
                except Exception as e:
                    self.state.update(connected=False, error=str(e))
                    return  # no autonomous reconnect or output enable

    def configure(self, volts, amps):
        volts, amps = float(volts), float(amps)
        if not math.isfinite(volts) or not math.isfinite(amps) or not (0 < volts <= 80 and 0 < amps <= 10 and volts*amps <= 500):
            raise OwonError("SPE8105: limite 80 V, 10 A, 500 W; valori pozitive")
        with self.lock:
            if not self.state["connected"]:
                raise OwonError("OWON nu este conectat")
            self.output(False)
            if self.simulated:
                self.state.update(set_voltage=volts, set_current=amps, updated=time.time())
                return self.snapshot()
            self._write("CONF:OUTP:MODE CCCV")
            self._write(f"VOLT {volts:.2f}")
            self._write(f"CURR {amps:.3f}")
            self._refresh()
            if abs(self.state["set_voltage"]-volts) > .011 or abs(self.state["set_current"]-amps) > .002:
                raise OwonError("setarile OWON nu au fost confirmate")
            return self.snapshot()

    def output(self, on):
        if not isinstance(on, bool):
            raise OwonError("stare iesire invalida")
        with self.lock:
            if self.simulated:
                if not self.state["connected"]:
                    raise OwonError("sursa simulata nu este conectata")
                v = self.state["set_voltage"] if on else 0.
                i = self.state["set_current"] if on else 0.
                self.state.update(output=on, voltage=v, current=i, power=v*i, updated=time.time())
                return self.snapshot()
            if on and not self.state["connected"]:
                raise OwonError("OWON nu este conectat")
            self._write("OUTP ON" if on else "OUTP OFF")
            state = self._query("OUTP?").upper()
            if state not in ("ON", "OFF", "1", "0") or (state in ("ON", "1")) != on:
                raise OwonError("iesirea OWON nu a fost confirmata")
            self.state.update(output=on, updated=time.time())
            return self.snapshot()

    def disconnect(self):
        self.stop_poll.set()
        if self.thread:
            self.thread.join(2)
        with self.lock:
            if self.io or self.state["connected"]:
                self.output(False)
            if self.io:
                self.io.close()
                self.io = None
            self.state.update(connected=False, output=False)

