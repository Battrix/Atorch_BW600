"""Scrie tot ce afiseaza un script si intr-un fisier din `logs/` (folderul proiectului).

Fisierul se goleste la fiecare scriere (flush), deci poate fi citit cat timp scriptul ruleaza.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path


class Tee:
    def __init__(self, stream, fh):
        self._s, self._f = stream, fh

    def write(self, data):
        self._s.write(data)
        self._f.write(data)
        self._f.flush()
        return len(data)

    def flush(self):
        self._s.flush()
        self._f.flush()

    def __getattr__(self, name):
        return getattr(self._s, name)


def start_log(name: str, root: Path | None = None) -> Path:
    """Redirectioneaza stdout si stderr catre consola + fisier. Intoarce calea fisierului."""
    root = root or Path(__file__).resolve().parents[3]
    d = root / "logs"
    d.mkdir(exist_ok=True)
    path = d / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    fh = open(path, "w", encoding="utf-8", buffering=1)
    sys.stdout = Tee(sys.stdout, fh)
    sys.stderr = Tee(sys.stderr, fh)
    print(f"[jurnal: {path.name}]")
    return path
