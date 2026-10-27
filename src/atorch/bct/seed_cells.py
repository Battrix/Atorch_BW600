"""Celule Li-ion 18650 / 21700 predefinite pentru baza de baterii.

Capacitatea (`rated_ah`) este valoarea nominala/tipica a producatorului; `min_ah` e minimul garantat din fisa
(unde e cunoscut). `empty_v` este tensiunea de taiere din fisa. Curentul de test este 0,2C (conditia standard
din fisele tehnice). `verified=True` = valori citite direct din fisa/specificatia producatorului sau dintr-un
distribuitor care o citeaza; restul sunt valori publicate uzual si trebuie confruntate cu fisa lotului tau.
"""
from __future__ import annotations

# (brand, model, form, ah_tipic, v_taiere, i_max_continuu_A, ri_ac_mohm, verificat)
_CELLS = [
    # --- 18650 ---
    ("Samsung", "INR18650-25R", "18650", 2.5, 2.5, 20, 18, True),
    ("Samsung", "INR18650-30Q", "18650", 3.0, 2.5, 15, None, False),
    ("Samsung", "INR18650-35E", "18650", 3.5, 2.65, 8, 35, True),
    ("Samsung", "INR18650-20S", "18650", 2.0, 2.5, 30, None, False),
    ("LG", "INR18650-MJ1", "18650", 3.5, 2.5, 10, None, False),
    ("LG", "INR18650-HG2", "18650", 3.0, 2.5, 20, None, False),
    ("LG", "INR18650-HE4", "18650", 2.5, 2.5, 20, None, False),
    ("Panasonic", "NCR18650B", "18650", 3.35, 2.5, 4.87, None, False),
    ("Panasonic", "NCR18650GA", "18650", 3.45, 2.5, 10, None, False),
    ("Panasonic", "NCR18650PF", "18650", 2.9, 2.5, 10, None, False),
    ("Murata (Sony)", "US18650VTC4", "18650", 2.1, 2.5, 30, None, False),
    ("Murata (Sony)", "US18650VTC5", "18650", 2.6, 2.5, 20, None, False),
    ("Murata (Sony)", "US18650VTC5A", "18650", 2.6, 2.5, 25, None, False),
    ("Murata (Sony)", "US18650VTC6", "18650", 3.0, 2.5, 15, None, False),
    ("Molicel", "INR18650-P26A", "18650", 2.6, 2.5, 35, None, True),
    ("Molicel", "INR18650-P28A", "18650", 2.8, 2.5, 35, None, False),
    ("Molicel", "INR18650-P30B", "18650", 3.0, 2.5, 30, None, False),
    ("Molicel", "INR18650-M35A", "18650", 3.5, 2.5, 10, None, False),
    ("EVE", "INR18650-25P", "18650", 2.5, 2.5, 30, None, False),
    ("EVE", "INR18650-30P", "18650", 3.0, 2.5, 30, None, False),
    ("EVE", "INR18650-35V", "18650", 3.5, 2.5, 10, None, False),
    # --- 21700 ---
    ("Samsung", "INR21700-30T", "21700", 3.0, 2.5, 35, None, False),
    ("Samsung", "INR21700-40T", "21700", 4.0, 2.5, 35, None, False),
    ("Samsung", "INR21700-48X", "21700", 4.8, 2.5, 10, None, False),
    ("Samsung", "INR21700-50E", "21700", 5.0, 2.5, 9.8, None, False),
    ("Samsung", "INR21700-50S", "21700", 5.0, 2.5, 25, 14, True),
    ("LG", "INR21700-M50LT", "21700", 5.0, 2.5, 7.3, None, False),
    ("Molicel", "INR21700-P42A", "21700", 4.2, 2.5, 45, None, False),
    ("Molicel", "INR21700-P45B", "21700", 4.5, 2.5, 45, None, False),
    ("Murata (Sony)", "US21700VTC6A", "21700", 4.0, 2.5, 30, None, False),
    ("EVE", "INR21700-40P", "21700", 4.0, 2.5, 35, None, False),
]


# LFP prismatice 3,2 V: (brand, model, ah, v_taiere, i_max_continuu_A, ri_ac_mohm, verificat)
# Ri = valoarea maxima AC 1 kHz din fisa/lista; i_max doar unde e in fisa. Incarcare 3,65 V la toate.
_LFP = [
    ("EVE", "LF50K", 50, 2.5, None, 0.7, False),
    ("EVE", "LF90K", 90, 2.5, None, 0.5, False),
    ("EVE", "LF100LA", 102, 2.5, None, 0.5, False),
    ("EVE", "LF105", 105, 2.5, None, 0.32, False),
    ("EVE", "LF125", 125, 2.5, None, 0.4, False),
    ("EVE", "LF160", 160, 2.5, None, 0.21, False),
    ("EVE", "LF173", 173, 2.5, None, 0.25, False),
    ("EVE", "LF230", 230, 2.5, None, 0.25, False),
    ("EVE", "LF280K", 280, 2.5, 280, 0.25, True),
    ("EVE", "LF304", 304, 2.5, None, 0.16, False),
    ("EVE", "MB30", 306, 2.5, None, 0.18, False),
    ("EVE", "MB31", 314, 2.5, None, 0.18, False),
    ("EVE", "LF560K", 560, 2.5, None, 0.25, False),
    ("CALB", "L135F72 (CAM72)", 72, 2.5, 72, 0.5, True),
    ("CALB", "CA100", 100, 2.5, 100, 0.6, True),
    ("CALB", "CA180", 180, 2.5, 180, 0.5, True),
    ("Cornex", "PF173-314A", 314, 2.5, None, None, False),
]
MAX_TEST_A = 40.0       # ramane sub limita de 50 A a aparatului BW600; curentul de test se poate schimba


def seed_batteries() -> list[dict]:
    out = []
    for brand, model, form, ah, cut, imax, ri, ok in _CELLS:
        name = f"{brand} {model}"
        notes = f"Celulă {form}; descărcare continuă max. {imax:g} A; tensiune de tăiere {cut:g} V"
        if ri:
            notes += f"; rezistență internă AC (1 kHz) ≤ {ri} mΩ"
        notes += ". " + ("Valori din fișa tehnică." if ok else "Valori uzuale publicate: verifică fișa lotului.")
        out.append({
            "id": "seed-" + "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-"),
            "model": name, "brand": brand, "form": form, "chemistry": "nmc", "series": 1,
            "rated_ah": ah, "nominal_v": 3.6, "full_v": 4.2, "empty_v": cut,
            "discharge_a": round(ah * 0.2, 3), "pass_pct": 80.0, "ri_max_mohm": None,
            "max_cont_a": imax, "ri_ac_mohm": ri, "verified": ok, "notes": notes, "seed": True,
        })
    for brand, model, ah, cut, imax, ri, ok in _LFP:
        name = f"{brand} {model}"
        i02 = ah * 0.2
        notes = f"Celulă LFP prismatică; încărcare max. 3,65 V; tensiune de tăiere {cut:g} V"
        if imax:
            notes += f"; descărcare continuă max. {imax:g} A"
        if ri:
            notes += f"; rezistență internă AC (1 kHz) ≤ {ri} mΩ"
        if i02 > MAX_TEST_A:
            notes += f"; curent de test limitat la {MAX_TEST_A:g} A (0,2C ar fi {i02:g} A, peste limita aparatului)"
        notes += ". " + ("Valori din fișa tehnică." if ok else "Valori uzuale publicate (capacitate/Ri din liste de distribuitori, tăiere 2,5 V uzuală): verifică fișa lotului.")
        out.append({
            "id": "seed-" + "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-"),
            "model": name, "brand": brand, "form": "prismatic", "chemistry": "lifepo4", "series": 1,
            "rated_ah": float(ah), "nominal_v": 3.2, "full_v": 3.65, "empty_v": cut,
            "discharge_a": round(min(i02, MAX_TEST_A), 3), "pass_pct": 80.0, "ri_max_mohm": None,
            "max_cont_a": imax, "ri_ac_mohm": ri, "verified": ok, "notes": notes, "seed": True,
        })
    return out
