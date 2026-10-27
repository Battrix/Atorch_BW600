"""Stocare pe disc: baza de baterii (model + valori de referinta) si istoricul testelor (JSON)."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from .catalog import BatteryError, validate_battery


def default_data_dir() -> Path:
    return Path(os.environ.get("ATORCH_DATA") or Path.cwd() / "data")


def _atomic_write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "baterie"


class TestStore:
    __test__ = False        # nu este clasa de test pentru pytest

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else default_data_dir()
        self._lock = threading.Lock()

    # ---- baza de baterii -------------------------------------------------
    @property
    def _bat_file(self) -> Path:
        return self.root / "batteries.json"

    def batteries(self) -> list[dict]:
        try:
            return json.loads(self._bat_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []

    def save_battery(self, b: dict) -> dict:
        validate_battery(b)
        if not str(b.get("model", "")).strip():
            raise BatteryError("modelul bateriei nu poate fi gol")
        with self._lock:
            items = self.batteries()
            b = dict(b, id=b.get("id") or _slug(b["model"]))
            items = [x for x in items if x.get("id") != b["id"]] + [b]
            items.sort(key=lambda x: x["model"].lower())
            _atomic_write(self._bat_file, items)
        return b

    def import_seed(self) -> int:
        """Adauga celulele predefinite care lipsesc (nu atinge ce ai modificat). Intoarce cate au fost adaugate."""
        from .seed_cells import seed_batteries
        with self._lock:
            items = self.batteries()
            have = {x.get("id") for x in items}
            new = [b for b in seed_batteries() if b["id"] not in have]
            if new:
                items = sorted(items + new, key=lambda x: x["model"].lower())
                _atomic_write(self._bat_file, items)
            return len(new)

    def ensure_seed(self) -> int:
        """O singura data pe folder de date: importa celulele predefinite (marker .seed-cells-v2)."""
        marker = self.root / ".seed-cells-v2"
        if marker.exists():
            return 0
        n = self.import_seed()
        try:
            marker.write_text("ok", encoding="utf-8")
        except OSError:
            pass
        return n

    def delete_battery(self, bid: str) -> bool:
        with self._lock:
            items = self.batteries()
            keep = [x for x in items if x.get("id") != bid]
            if len(keep) == len(items):
                return False
            _atomic_write(self._bat_file, keep)
            return True

    # ---- istoricul testelor ---------------------------------------------
    @property
    def _tests_dir(self) -> Path:
        return self.root / "tests"

    def new_test_id(self) -> str:
        return time.strftime("%Y%m%d-%H%M%S")

    def save_test(self, test: dict) -> str:
        tid = test["id"]
        _atomic_write(self._tests_dir / f"{tid}.json", test)
        return tid

    def load_test(self, tid: str) -> dict:
        if not re.fullmatch(r"[0-9]{8}-[0-9]{6}(-[0-9]+)?", tid):
            raise KeyError(tid)
        return json.loads((self._tests_dir / f"{tid}.json").read_text(encoding="utf-8"))

    def list_tests(self) -> list[dict]:
        """Rezumate (fara esantioane), cele mai noi primele."""
        out = []
        for p in sorted(self._tests_dir.glob("*.json"), reverse=True) if self._tests_dir.exists() else []:
            try:
                t = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out.append({k: t.get(k) for k in ("id", "started", "battery", "result", "state")})
        return out
