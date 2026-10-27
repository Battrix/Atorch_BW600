"""Genereaza certificatul PDF (A4, o pagina) dintr-un test BCT salvat. Grafice vectoriale desenate direct."""
from __future__ import annotations

import io
import json
import time
from datetime import datetime
from pathlib import Path

from atorch.bct.catalog import CHEMISTRIES

FONT_DIR = Path(__file__).resolve().parent / "fonts"


class ReportUnavailable(RuntimeError):
    """reportlab nu este instalat."""


def default_workshop() -> dict:
    return {
        "name": "BATTRIX ENERGY",
        "tagline": "Atelier de reparații electronice și recondiționare baterii",
        "legal": "BONDICI IOSIF-FLORIN P.F.A. · CUI RO52455005",
        "address": "Satu Mare, România",
        "contact": "info@battrix.ro · battrix.ro",
        "signer": "",
    }


def load_workshop(root: Path) -> dict:
    """Citeste data/workshop.json (il creeaza cu valorile implicite daca lipseste; poate fi editat de mana)."""
    path = Path(root) / "workshop.json"
    base = default_workshop()
    try:
        base.update(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    except (OSError, ValueError):
        pass
    return base


def _ro(v, d=3, unit="") -> str:
    if v is None:
        return "—"
    s = f"{v:.{d}f}".replace(".", ",")
    return f"{s} {unit}".strip()


def _hms(sec) -> str:
    sec = int(round(sec or 0))
    return f"{sec // 3600}:{sec // 60 % 60:02d}:{sec % 60:02d}"


def _thin(samples: list, n: int = 500) -> list:
    if len(samples) <= n:
        return samples
    step = len(samples) / n
    return [samples[int(i * step)] for i in range(n - 1)] + [samples[-1]]


def build_certificate(test: dict, workshop: dict | None = None) -> bytes:
    try:
        from reportlab.lib.colors import HexColor, white
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError as e:
        raise ReportUnavailable("Pentru certificat PDF instalează reportlab: py -m pip install reportlab") from e

    for name, f in (("DV", "DejaVuSans.ttf"), ("DV-B", "DejaVuSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f)))

    ws = dict(default_workshop(), **(workshop or {}))
    b, r, ex = test["battery"], test.get("result") or {}, test.get("extra") or {}
    verdict = r.get("verdict", "NEFINALIZAT")
    col = {"POZITIV": HexColor("#1f7a3f"), "NEGATIV": HexColor("#b3261e")}.get(verdict, HexColor("#8a6d00"))
    ink, soft, line = HexColor("#1c2226"), HexColor("#5a666d"), HexColor("#b8c0c5")
    samples = test.get("samples") or []
    started = datetime.fromtimestamp(test.get("started", time.time()))
    cert_no = "BTX-" + test["id"]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Certificat test baterie {cert_no}")
    c.setAuthor(ws["name"])
    W, H = A4
    M = 15 * mm

    # ---- antet atelier ----
    c.setFillColor(HexColor("#10181d")); c.rect(0, H - 30 * mm, W, 30 * mm, stroke=0, fill=1)
    c.setFillColor(white); c.setFont("DV-B", 20); c.drawString(M, H - 14 * mm, ws["name"])
    c.setFont("DV", 8.5); c.setFillColor(HexColor("#cfd9de"))
    c.drawString(M, H - 20 * mm, ws["tagline"])
    c.drawString(M, H - 25 * mm, f'{ws["legal"]} · {ws["address"]}')
    c.drawRightString(W - M, H - 14 * mm, f"Nr. {cert_no}")
    c.drawRightString(W - M, H - 20 * mm, started.strftime("Data testului: %d.%m.%Y %H:%M"))
    c.drawRightString(W - M, H - 25 * mm, ws["contact"])

    y = H - 40 * mm
    c.setFillColor(ink); c.setFont("DV-B", 14)
    c.drawString(M, y, "CERTIFICAT DE TEST AL CAPACITĂȚII BATERIEI")

    # ---- rezultat ----
    y -= 5 * mm
    c.setFillColor(col); c.roundRect(M, y - 17 * mm, W - 2 * M, 17 * mm, 2 * mm, stroke=0, fill=1)
    c.setFillColor(white); c.setFont("DV-B", 18); c.drawString(M + 5 * mm, y - 8 * mm, f"REZULTAT: {verdict}")
    c.setFont("DV", 9)
    pct = r.get("capacity_pct")
    if verdict == "NEFINALIZAT":
        why = r.get("end_reason") or "Testul nu a fost dus până la capăt."
    elif verdict == "POZITIV":
        why = f'Capacitate măsurată {_ro(pct, 1)}% din cea declarată (prag de acceptare {_ro(b["pass_pct"], 0)}%).'
    else:
        why = "; ".join(r.get("reasons") or []) or "Valorile nu respectă criteriile de acceptare."
    c.drawString(M + 5 * mm, y - 14 * mm, why[:120])
    y -= 22 * mm

    def table(x, y0, title, rows, w):
        c.setFillColor(ink); c.setFont("DV-B", 10); c.drawString(x, y0, title)
        c.setStrokeColor(line); c.line(x, y0 - 1.6 * mm, x + w, y0 - 1.6 * mm)
        yy = y0 - 6.2 * mm
        for k, v in rows:
            c.setFont("DV", 8.6); c.setFillColor(soft); c.drawString(x, yy, k)
            c.setFont("DV-B", 8.8); c.setFillColor(ink); c.drawRightString(x + w, yy, str(v)[:48])
            yy -= 5 * mm
        return yy

    colw = (W - 2 * M - 8 * mm) / 2
    chem = b.get("chemistry", "")
    left = [("Client", ex.get("client") or "—"), ("Model baterie", b.get("model") or "—"),
            ("Serie / identificare", ex.get("serial") or "—"), ("Chimie", CHEMISTRIES.get(chem, {}).get("name", chem) or "—"),
            ("Elemente în serie", b.get("series", "—")),
            ("Tensiune nominală", _ro(b["nominal_v"], 2, "V")), ("Tensiune full (încărcată)", _ro(b["full_v"], 2, "V")),
            ("Tensiune descărcată", _ro(b["empty_v"], 2, "V")), ("Capacitate declarată", _ro(b["rated_ah"], 3 if b["rated_ah"] < 1 else 2, "Ah"))]
    right = [("Curent de descărcare (CC)", _ro(b["discharge_a"], 2, "A")),
             ("Tensiune în repaus la start", _ro(r.get("ocv_start"), 3, "V")),
             ("Tensiune la final", _ro(r.get("v_end"), 3, "V")),
             ("Capacitate măsurată", _ro(r.get("capacity_ah"), 3, "Ah")),
             ("Capacitate față de declarată", _ro(pct, 1, "%")),
             ("Energie debitată", _ro(r.get("energy_wh"), 2, "Wh")),
             ("Durată test", _hms(r.get("duration_s"))),
             ("Rezistență internă (DC)", _ro(r.get("ri_mohm"), 1, "mΩ")),
             ("Aparat de test", test.get("device", "—"))]
    y1 = table(M, y, "Date baterie", left, colw)
    y2 = table(M + colw + 8 * mm, y, "Parametri și valori măsurate", right, colw)
    y = min(y1, y2) - 2 * mm

    # ---- grafice ----
    gw, gh = colw, 47 * mm

    def chart(x, ytop, title, pts, color, xlab, ylab, dec=2, zero=False, xfmt=None):
        c.setFillColor(ink); c.setFont("DV-B", 9); c.drawString(x, ytop, title)
        top, left_pad, bot = ytop - 3 * mm, 11 * mm, 7 * mm
        px, pw, py, ph = x + left_pad, gw - left_pad - 2 * mm, ytop - gh + bot, gh - 3 * mm - bot
        c.setStrokeColor(line); c.setLineWidth(0.4); c.rect(px, py, pw, ph, stroke=1, fill=0)
        pts = [p for p in pts if p[1] is not None]
        if len(pts) < 2:
            c.setFillColor(soft); c.setFont("DV", 8); c.drawString(px + 3 * mm, py + ph / 2, "fără date"); return
        x0, x1 = pts[0][0], pts[-1][0]
        x0 = min(p[0] for p in pts); x1 = max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        if zero:
            y0 = min(0.0, y0)
        sp = max(y1 - y0, 1e-6) * 1.1 if y1 - y0 > 1e-6 else 1.0
        if not zero:
            y0 -= sp * 0.05
        y1 = y0 + sp
        X = lambda v: px + (v - x0) / max(x1 - x0, 1e-9) * pw
        Y = lambda v: py + (v - y0) / sp * ph
        c.setFont("DV", 6.5); c.setFillColor(soft); c.setStrokeColor(HexColor("#e1e5e8"))
        for i in range(5):
            v = y0 + sp * i / 4
            c.line(px, Y(v), px + pw, Y(v)); c.drawRightString(px - 1.2 * mm, Y(v) - 2, _ro(v, dec))
            xv = x0 + (x1 - x0) * i / 4
            c.drawCentredString(X(xv), py - 3.2 * mm, (xfmt or (lambda t: _ro(t, 1)))(xv))
        c.setFont("DV", 6.5); c.drawRightString(px + pw, py - 6.2 * mm, xlab)
        c.saveState(); c.translate(x + 2.2 * mm, py + ph / 2); c.rotate(90); c.drawCentredString(0, 0, ylab); c.restoreState()
        c.setStrokeColor(color); c.setLineWidth(1.0)
        path = c.beginPath(); path.moveTo(X(pts[0][0]), Y(pts[0][1]))
        for p in pts[1:]:
            path.lineTo(X(p[0]), Y(p[1]))
        c.drawPath(path, stroke=1, fill=0)

    s = _thin(samples)
    total = s[-1][0] if s else 0
    if total < 180:
        unit_t, div, tdec = "timp [s]", 1.0, 0
    elif total < 7200:
        unit_t, div, tdec = "timp [min]", 60.0, 0
    else:
        unit_t, div, tdec = "timp [h]", 3600.0, 1
    cum, prev, vah = 0.0, None, []
    for p in samples:
        if prev:
            cum += (p[2] + prev[2]) / 2 * (p[0] - prev[0]) / 3600
        prev = p
        vah.append((cum, p[1]))
    vah = _thin(vah)
    ytop = y
    chart(M, ytop, "Tensiune în timp", [(p[0] / div, p[1]) for p in s], HexColor("#c28f00"), unit_t, "V", 2, xfmt=lambda t: _ro(t, tdec))
    chart(M + colw + 8 * mm, ytop, "Curent în timp", [(p[0] / div, p[2]) for p in s], HexColor("#1b87a6"), unit_t, "A", 2, zero=True, xfmt=lambda t: _ro(t, tdec))
    ytop -= gh + 3 * mm
    chart(M, ytop, "Curba de descărcare", vah, HexColor("#c2185b"), "capacitate [Ah]", "V", 2, xfmt=lambda t: _ro(t, 2))
    chart(M + colw + 8 * mm, ytop, "Temperatură MOSFET", [(p[0] / div, p[4]) for p in s], HexColor("#3d8b1f"), unit_t, "°C", 1, xfmt=lambda t: _ro(t, tdec))
    y = ytop - gh - 4 * mm

    # ---- note, metoda, semnatura ----
    c.setFillColor(soft); c.setFont("DV", 7.2)
    note = ex.get("notes") or ""
    if note:
        c.setFillColor(ink); c.setFont("DV-B", 8); c.drawString(M, y, "Observații: "); c.setFont("DV", 8)
        c.drawString(M + 19 * mm, y, note[:110]); y -= 5 * mm
    c.setFillColor(soft); c.setFont("DV", 7)
    for line_ in ("Metodă: descărcare la curent constant (CC) cu sarcina electronică programabilă; capacitatea este integrala curentului măsurat,",
                  "până la tensiunea de descărcat. Rezistența internă DC = (tensiune în repaus − tensiune sub sarcină) / curent, la pornirea sarcinii;",
                  "include rezistența cablurilor și a contactelor. Rezultatul se referă exclusiv la starea bateriei la data și ora testului."):
        c.drawString(M, y, line_); y -= 3.4 * mm
    y -= 5 * mm
    c.setStrokeColor(ink); c.setLineWidth(0.5)
    c.line(M, y, M + 60 * mm, y); c.line(W - M - 60 * mm, y, W - M, y)
    c.setFont("DV", 7.5); c.setFillColor(soft)
    c.drawString(M, y - 3.5 * mm, f'Operator: {ex.get("operator") or ws.get("signer") or ""}')
    c.drawRightString(W - M, y - 3.5 * mm, "Semnătură și ștampilă")
    c.setFont("DV", 6.5)
    c.drawCentredString(W / 2, 8 * mm, f'{ws["name"]} · {ws["address"]} · {ws["contact"]} · generat {datetime.now().strftime("%d.%m.%Y %H:%M")}')
    c.showPage()
    c.save()
    return buf.getvalue()
