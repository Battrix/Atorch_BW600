import json
import shutil
import subprocess
import pytest

pytest.importorskip("reportlab")
from atorch.report import build_certificate, load_workshop


def make_test(verdict="POZITIV"):
    samples = [[i * 60.0, 3.4 - i * 0.002, 20.0, 68.0 - i * 0.1, 31.0 + i * 0.01, None] for i in range(300)]
    return {"id": "20261027-120000", "started": 1793100000, "device": "ATORCH BW600 / BW600-DK",
            "battery": {"model": "Șasiu ăîțș LFP 300Ah", "chemistry": "lifepo4", "series": 16, "rated_ah": 300.0,
                        "nominal_v": 51.2, "full_v": 58.4, "empty_v": 40.0, "discharge_a": 60.0, "pass_pct": 80.0},
            "extra": {"client": "Client Țărănescu", "serial": "SN1", "operator": "Florin", "notes": "ok"},
            "samples": samples,
            "result": {"verdict": verdict, "capacity_ah": 290.1, "energy_wh": 14800.0, "capacity_pct": 96.7,
                       "duration_s": 17400, "ri_mohm": 12.3, "ocv_start": 55.1, "v_end": 40.0,
                       "reasons": [] if verdict == "POZITIV" else ["capacitate 70% sub pragul de 80%"], "end_reason": ""}}


def test_certificate_is_a_pdf(tmp_path):
    pdf = build_certificate(make_test())
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000
    p = tmp_path / "c.pdf"
    p.write_bytes(pdf)
    if shutil.which("pdftotext"):
        txt = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
        assert "REZULTAT: POZITIV" in txt and "BATTRIX ENERGY" in txt and "CAPACITĂȚII" in txt
        assert "Țărănescu" in txt and "290,1" in txt
    if shutil.which("pdfinfo"):
        assert "Pages:           1" in subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True).stdout


def test_negative_and_unfinished_variants():
    assert b"%PDF" in build_certificate(make_test("NEGATIV"))
    t = make_test("NEFINALIZAT")
    t["samples"] = []
    t["result"]["end_reason"] = "Test oprit de operator"
    assert b"%PDF" in build_certificate(t)


def test_workshop_defaults_file(tmp_path):
    w = load_workshop(tmp_path)
    assert w["name"] == "BATTRIX ENERGY" and "RO52455005" in w["legal"]
    (tmp_path / "workshop.json").write_text(json.dumps({"contact": "x@y.ro"}), encoding="utf-8")
    assert load_workshop(tmp_path)["contact"] == "x@y.ro"
