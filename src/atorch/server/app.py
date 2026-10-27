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
from urllib.parse import urlparse

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


def make_handler(service: DeviceService, hub: Hub, link: str):
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
            if path in ("/", "/index.html"):
                return self._file("index.html")
            return self._file(path.lstrip("/"))

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
                  link: str = "usb") -> ThreadingHTTPServer:
    hub = Hub(service)

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):      # clientul a inchis conexiunea: normal
            import sys
            if not isinstance(sys.exc_info()[1], (ConnectionError, OSError)):
                super().handle_error(request, client_address)

    srv = Server((host, port), make_handler(service, hub, link))
    return srv
