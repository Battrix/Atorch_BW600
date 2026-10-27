"""Server web local (doar biblioteca standard): API JSON, flux live (SSE) si fisierele interfetei.

Securitate: implicit asculta doar pe 127.0.0.1. Cererile POST cu antet Origin sunt acceptate
numai daca Origin-ul are acelasi host ca Host-ul cererii.
"""
from __future__ import annotations

import json
import mimetypes
import queue
import threading
from concurrent.futures import TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from atorch.bct import BctEngine, BctError, TestStore
from atorch.bct.catalog import CHEMISTRIES, BatteryError, derive_battery
from atorch.service.device import CommandFailed, CommandRejected, DeviceService

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
CMD_TIMEOUT = 12.0


class Hub:
    """Distribuie evenimentele serviciului catre clientii SSE."""

    def __init__(self, service: DeviceService):
        self.service = service
        self._clients: set[queue.Queue] = set()
        self._lock = threading.Lock()
        service.subscribe(self._on_event)

    def _on_event(self, kind: str, data: dict) -> None:
        msg = (kind, data)
        with self._lock:
            for q in list(self._clients):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    try:
                        q.get_nowait()
                        q.put_nowait(msg)
                    except (queue.Empty, queue.Full):
                        pass

    def add(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._clients.add(q)
        return q

    def remove(self, q: queue.Queue) -> None:
        with self._lock:
            self._clients.discard(q)


def _state_payload(service: DeviceService, link: str) -> dict:
    s = service.snapshot()
    p = service.profile
    return {
        "device": {"title": p.title, "profile": p.name, "link": link},
        "state": {"connected": s.connected, "running": s.running, "live": s.live,
                  "settings": s.settings, "updated": s.updated, "error": s.last_error},
        "limits": {k: list(v) for k, v in p.limits.items()},
    }


def make_handler(service: DeviceService, hub: Hub, link: str, engine: BctEngine | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AtorchLab/0.1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):      # fara zgomot in consola
            pass

        # ---- raspunsuri ------------------------------------------------
        def _json(self, obj, status=200):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _file(self, rel: str):
            path = (UI_DIR / rel).resolve()
            if UI_DIR not in path.parents and path != UI_DIR or not path.is_file():
                return self._json({"error": "negasit"}, 404)
            body = path.read_bytes()
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        # ---- GET -------------------------------------------------------
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/state":
                return self._json(_state_payload(service, link))
            if path == "/api/history":
                return self._json(service.history()[-3600:])
            if path == "/api/stream":
                return self._stream()
            if path.startswith("/api/bct/"):
                return self._bct_get(path, parse_qs(urlparse(self.path).query))
            if path in ("/", "/index.html"):
                return self._file("index.html")
            return self._file(path.lstrip("/"))

        # ---- BCT ---------------------------------------------------------
        def _bct_get(self, path, qs):
            if engine is None:
                return self._json({"error": "BCT indisponibil"}, 404)
            store = engine.store
            if path == "/api/bct/status":
                return self._json(engine.status())
            if path == "/api/bct/catalog":
                return self._json({"chemistries": CHEMISTRIES, "batteries": store.batteries(),
                                   "tests": store.list_tests()})
            if path == "/api/bct/test":
                tid = (qs.get("id") or [""])[0]
                try:
                    t = engine.get_test(tid)
                except (KeyError, FileNotFoundError, ValueError):
                    return self._json({"error": "test negasit"}, 404)
                mx = int((qs.get("max") or ["1200"])[0])
                smp = t.get("samples", [])
                if len(smp) > mx > 1:
                    step = len(smp) / mx
                    smp = [smp[int(i * step)] for i in range(mx - 1)] + [smp[-1]]
                return self._json(dict(t, samples=smp))
            if path == "/api/bct/report":
                from atorch.report import ReportUnavailable, build_certificate, load_workshop
                tid = (qs.get("id") or [""])[0]
                try:
                    t = engine.get_test(tid)
                except (KeyError, FileNotFoundError, ValueError):
                    return self._json({"error": "test negasit"}, 404)
                if not t.get("result"):
                    return self._json({"error": "testul nu are rezultat inca"}, 409)
                try:
                    pdf = build_certificate(t, load_workshop(store.root))
                except ReportUnavailable as e:
                    return self._json({"error": str(e)}, 501)
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(pdf)))
                self.send_header("Content-Disposition", f'inline; filename="certificat-BTX-{tid}.pdf"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(pdf)
                return
            return self._json({"error": "negasit"}, 404)

        def _bct_post(self, path, b):
            if engine is None:
                return {"ok": False, "error": "BCT indisponibil"}, 404
            store = engine.store
            try:
                if path == "/api/bct/start":
                    extra = {k: str(b.get("extra", {}).get(k, ""))[:200]
                             for k in ("client", "serial", "operator", "notes")}
                    tid = engine.start(b["battery"], extra)
                    return {"ok": True, "message": "test pornit", "id": tid}, 200
                if path == "/api/bct/stop":
                    engine.stop()
                    return {"ok": True, "message": "oprire cerută"}, 200
                if path == "/api/bct/pause":
                    engine.pause()
                    return {"ok": True, "message": "pauză cerută"}, 200
                if path == "/api/bct/resume":
                    engine.resume()
                    return {"ok": True, "message": "reluare cerută"}, 200
                if path == "/api/bct/reset":
                    engine.reset()
                    return {"ok": True, "message": "testul a fost resetat"}, 200
                if path == "/api/bct/derive":
                    return {"ok": True, "battery": derive_battery(b["chemistry"], int(b["series"]), float(b["rated_ah"]),
                                                                   model=str(b.get("model", "")))}, 200
                if path == "/api/bct/battery":
                    return {"ok": True, "battery": store.save_battery(b["battery"])}, 200
                if path == "/api/bct/seed":
                    return {"ok": True, "added": store.import_seed()}, 200
                if path == "/api/bct/battery/delete":
                    return {"ok": store.delete_battery(str(b["id"]))}, 200
            except (BctError, BatteryError) as e:
                return {"ok": False, "error": str(e)}, 409
            return {"ok": False, "error": "comanda necunoscuta"}, 404

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = hub.add()
            try:
                self.wfile.write(b"retry: 1500\n\n")
                self.wfile.flush()
                while True:
                    try:
                        kind, data = q.get(timeout=15)
                        chunk = f"event: {kind}\ndata: {json.dumps(data)}\n\n".encode()
                    except queue.Empty:
                        chunk = b": keepalive\n\n"
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionError, OSError):
                pass
            finally:
                hub.remove(q)

        # ---- POST ------------------------------------------------------
        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return True
            host = self.headers.get("Host", "")
            return urlparse(origin).netloc == host

        def do_POST(self):
            if not self._origin_ok():
                return self._json({"ok": False, "error": "origine nepermisa"}, 403)
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json({"ok": False, "error": "JSON invalid"}, 400)
            path = urlparse(self.path).path
            if path.startswith("/api/bct/"):
                obj, code = self._bct_post(path, body)
                return self._json(obj, code)
            try:
                fut = self._dispatch(path, body)
            except (KeyError, TypeError, ValueError):
                return self._json({"ok": False, "error": "parametri lipsa sau invalizi"}, 400)
            if fut is None:
                return self._json({"ok": False, "error": "comanda necunoscuta"}, 404)
            try:
                msg = fut.result(CMD_TIMEOUT)
                return self._json({"ok": True, "message": msg})
            except CommandRejected as e:
                return self._json({"ok": False, "error": str(e)}, 409)
            except CommandFailed as e:
                return self._json({"ok": False, "error": str(e)}, 502)
            except FutureTimeout:
                return self._json({"ok": False, "error": "aparatul nu a raspuns la timp"}, 504)

        def _dispatch(self, path, b):
            if path == "/api/power":
                return service.start_load() if bool(b["on"]) else service.stop_load()
            if path == "/api/mode":
                return service.set_mode(int(b["mode"]))
            if path == "/api/value":
                return service.set_value(str(b["name"]), float(b["value"]))
            if path == "/api/level":
                return service.set_level(str(b["name"]), int(b["value"]))
            if path == "/api/timer":
                return service.set_timer(int(b["hours"]), int(b["minutes"]))
            return None

    return Handler


def create_server(service: DeviceService, host: str = "127.0.0.1", port: int = 8787,
                  link: str = "usb", engine: BctEngine | None = None) -> ThreadingHTTPServer:
    hub = Hub(service)
    if engine is not None:
        engine.subscribe(lambda kind, data: hub._on_event(kind, data))

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):      # clientul a inchis conexiunea: normal
            import sys
            if not isinstance(sys.exc_info()[1], (ConnectionError, OSError)):
                super().handle_error(request, client_address)

    srv = Server((host, port), make_handler(service, hub, link, engine))
    return srv
