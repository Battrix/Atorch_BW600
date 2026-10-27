"""Chimii de baterii, valori implicite si validare. Valorile pe celula sunt puncte de plecare, editabile."""
from __future__ import annotations

# nominal / full (incarcata) / empty (descarcata) in volti pe celula (sau pe element de 2 V la plumb)
CHEMISTRIES: dict[str, dict] = {
    "lifepo4": {"name": "LiFePO4", "nominal": 3.2, "full": 3.65, "empty": 2.5},
    "nmc": {"name": "Li-ion NMC / NCA", "nominal": 3.6, "full": 4.2, "empty": 3.0},
    "lco": {"name": "Li-ion LCO (3,7 V)", "nominal": 3.7, "full": 4.2, "empty": 3.0},
    "lipo": {"name": "Li-Po", "nominal": 3.7, "full": 4.2, "empty": 3.2},
    "lto": {"name": "LTO", "nominal": 2.3, "full": 2.8, "empty": 1.5},
    "pb": {"name": "Plumb-acid (per element 2 V)", "nominal": 2.0, "full": 2.15, "empty": 1.75},
    "nimh": {"name": "NiMH / NiCd", "nominal": 1.2, "full": 1.4, "empty": 1.0},
}


class BatteryError(ValueError):
    pass


def derive_battery(chemistry: str, series: int, rated_ah: float, model: str = "", **extra) -> dict:
    """Calculeaza tensiunile pachetului din chimie si numarul de elemente in serie."""
    if chemistry not in CHEMISTRIES:
        raise BatteryError(f"chimie necunoscuta: {chemistry}")
    series = int(series)
    if series < 1 or series > 100:
        raise BatteryError("numar de elemente in serie: 1..100")
    c = CHEMISTRIES[chemistry]
    rec = {
        "model": model, "chemistry": chemistry, "series": series, "rated_ah": float(rated_ah),
        "nominal_v": round(c["nominal"] * series, 3),
        "full_v": round(c["full"] * series, 3),
        "empty_v": round(c["empty"] * series, 3),
        "discharge_a": round(float(rated_ah) * 0.2, 3),     # 0,2C, valoare uzuala pentru test de capacitate
        "pass_pct": 80.0,
        "ri_max_mohm": None,
        "notes": "",
    }
    rec.update(extra)
    validate_battery(rec)
    return rec


def validate_battery(b: dict) -> None:
    for k in ("rated_ah", "nominal_v", "full_v", "empty_v", "discharge_a", "pass_pct"):
        if k not in b or not isinstance(b[k], (int, float)):
            raise BatteryError(f"lipseste sau e invalid: {k}")
    if b["rated_ah"] <= 0:
        raise BatteryError("capacitatea declarata trebuie sa fie > 0")
    if not 0 < b["empty_v"] < b["full_v"]:
        raise BatteryError("tensiunea descarcata trebuie sa fie sub tensiunea full")
    if not b["empty_v"] <= b["nominal_v"] <= b["full_v"]:
        raise BatteryError("tensiunea nominala trebuie sa fie intre descarcat si full")
    if b["discharge_a"] <= 0:
        raise BatteryError("curentul de descarcare trebuie sa fie > 0")
    if not 1 <= b["pass_pct"] <= 100:
        raise BatteryError("pragul de acceptare: 1..100 %")
    r = b.get("ri_max_mohm")
    if r is not None and not (isinstance(r, (int, float)) and r > 0):
        raise BatteryError("rezistenta interna maxima trebuie sa fie > 0 sau goala")
