"use strict";
const $ = (id) => document.getElementById(id);
const B = {catalog: null, status: {}, test: null, connected: false, running: false, live: {}, curId: null, pollT: 0};
const FIELDS = {nominal_v: "f_nominal", full_v: "f_full", empty_v: "f_empty", discharge_a: "f_cur", pass_pct: "f_pass", ri_max_mohm: "f_ri"};
const ACTIVE = ["preparing", "running"];

/* ---------- utilitare ---------- */
function log(msg, err) {
  const li = document.createElement("li");
  if (err) li.className = "err";
  const t = document.createElement("time");
  t.textContent = new Date().toLocaleTimeString("ro-RO");
  li.append(t, document.createTextNode(" " + msg));
  $("log").prepend(li);
  while ($("log").children.length > 30) $("log").lastChild.remove();
}
async function api(path, body) {
  try {
    const r = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    return await r.json();
  } catch (e) { return {ok: false, error: "serverul nu răspunde"}; }
}
const num = (id) => { const v = $(id).value.trim(); return v === "" ? null : Number(v); };
const fmt = (v, d = 3) => (v == null || !isFinite(v)) ? "—" : Number(v).toFixed(d);
function hms(s) {
  s = Math.max(0, Math.round(s || 0));
  return `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/* ---------- baterie: formular ---------- */
function batteryFromForm() {
  const b = {model: $("f_model").value.trim(), chemistry: $("f_chem").value, series: num("f_series"), rated_ah: num("f_rated")};
  for (const [k, id] of Object.entries(FIELDS)) b[k] = num(id);
  const sel = $("pick").value;
  if (sel) b.id = sel;
  return b;
}
function fillForm(b) {
  $("f_model").value = b.model || ""; $("f_chem").value = b.chemistry || "lifepo4";
  $("f_series").value = b.series ?? 1; $("f_rated").value = b.rated_ah ?? "";
  for (const [k, id] of Object.entries(FIELDS)) $(id).value = b[k] ?? "";
}
async function calc() {
  const r = await api("/api/bct/derive", {chemistry: $("f_chem").value, series: num("f_series"), rated_ah: num("f_rated"), model: $("f_model").value});
  if (!r.ok) { log("Calcul: " + r.error, true); return; }
  const keep = $("f_model").value; fillForm(Object.assign(r.battery, {model: keep}));
  log("Tensiunile și curentul 0,2C au fost calculate; le poți modifica.");
}
$("calc").onclick = calc;
$("pick").onchange = () => {
  const b = (B.catalog.batteries || []).find((x) => x.id === $("pick").value);
  if (b) fillForm(b);
  $("pickInfo").textContent = b && b.notes ? b.notes : "";
};
$("seedBtn").onclick = async () => {
  const r = await api("/api/bct/seed", {});
  log(r.ok ? (r.added ? `Au fost adăugate ${r.added} celule.` : "Toate celulele predefinite sunt deja în bază.") : "Import: eroare", !r.ok);
  await loadCatalog($("pick").value);
};
$("save").onclick = async () => {
  const old = (B.catalog.batteries || []).find((x) => x.id === $("pick").value) || {};
  const b = Object.assign({}, old, batteryFromForm()); delete b.id; if ($("pick").value) b.id = $("pick").value;
  const r = await api("/api/bct/battery", {battery: b});
  if (!r.ok) { log("Salvare: " + (r.error || "eroare"), true); return; }
  log(`Bateria „${r.battery.model}” a fost salvată în baza de date.`);
  await loadCatalog(r.battery.id);
};
$("del").onclick = async () => {
  const id = $("pick").value;
  if (!id) { log("Alege mai întâi o baterie din bază.", true); return; }
  if (!confirm("Ștergi bateria din baza de date? (testele salvate rămân)")) return;
  await api("/api/bct/battery/delete", {id});
  log("Baterie ștearsă."); await loadCatalog("");
};

async function loadCatalog(selectId) {
  const c = await api("/api/bct/catalog");
  if (c.error) { log("Catalog: " + c.error, true); return; }
  B.catalog = c;
  const chem = $("f_chem"); chem.innerHTML = "";
  for (const [k, v] of Object.entries(c.chemistries)) chem.add(new Option(v.name, k));
  const pick = $("pick"); pick.length = 1;
  const groups = {"18650": "Celule 18650", "21700": "Celule 21700", "": "Alte baterii"};
  for (const [f, title] of Object.entries(groups)) {
    const og = document.createElement("optgroup"); og.label = title;
    for (const b of c.batteries.filter((x) => (x.form || "") === f)) og.append(new Option(`${b.model} (${b.nominal_v} V, ${b.rated_ah} Ah)`, b.id));
    if (og.children.length) pick.append(og);
  }
  if (selectId !== undefined) { pick.value = selectId; pick.onchange(); }
  renderHistory();
}

/* ---------- istoric ---------- */
function renderHistory() {
  const ol = $("hist"); ol.innerHTML = "";
  const tests = B.catalog ? B.catalog.tests : [];
  if (!tests.length) { ol.innerHTML = '<li class="empty">Niciun test salvat.</li>'; return; }
  for (const t of tests) {
    const li = document.createElement("li");
    const v = t.result ? t.result.verdict : "—";
    const cls = v === "POZITIV" ? "pos" : v === "NEGATIV" ? "neg" : "nef";
    const d = t.started ? new Date(t.started * 1000).toLocaleString("ro-RO") : t.id;
    li.innerHTML = `<span></span><b class="${cls}">${v}</b>`;
    li.firstChild.textContent = `${d} — ${t.battery ? t.battery.model : ""}`;
    li.onclick = () => showTest(t.id);
    ol.append(li);
  }
}

/* ---------- afisare test ---------- */
function setText(id, t) { $(id).textContent = t; }
function renderLive() {
  const L = B.live, ok = B.connected && L.voltage != null;
  setText("rV", ok ? fmt(L.voltage, 3) : "--.---");
  setText("rA", ok ? fmt(L.current, 3) : "--.---");
  setText("sW", ok ? fmt(L.power, 2) + " W" : "—");
  setText("sTm", ok && L.temp_mos != null ? L.temp_mos.toFixed(0) + " °C" : "—");
  setText("sTp", ok && L.temp_probe != null ? L.temp_probe.toFixed(0) + " °C" : "—");
}
function renderStatus() {
  const s = B.status, act = ACTIVE.includes(s.state);
  $("lamp").className = "lamp " + (!B.connected ? "bad" : act ? "run" : "ok");
  setText("linkText", !B.connected ? "Fără conexiune cu aparatul" : act ? "Test în curs" : "Conectat, în așteptare");
  $("start").disabled = !B.connected || act;
  $("cfg").disabled = act;
  $("lockNote").hidden = !act;
  $("pdf").disabled = !(s.result && s.id && !act);
  setText("msg", s.message || (B.connected ? "Alege bateria și apasă Start test." : "—"));
  setText("rAh", act || s.result ? fmt(s.ah, 3) : "-.---");
  setText("sT", act || s.result ? hms(s.elapsed) : "—");
  setText("sWh", act || s.result ? fmt(s.wh, 2) + " Wh" : "—");
  setText("sSoc", s.soc_pct == null || !act ? "—" : s.soc_pct.toFixed(0) + " %");
  setText("sRi", s.ri_mohm == null ? "—" : s.ri_mohm.toFixed(1) + " mΩ");
  const bn = $("banner"), r = s.result;
  bn.hidden = !r;
  if (r) {
    bn.className = "banner " + (r.verdict === "POZITIV" ? "pos" : r.verdict === "NEGATIV" ? "neg" : "nef");
    const why = r.reasons && r.reasons.length ? r.reasons.join("; ") : `capacitate ${r.capacity_pct.toFixed(1)} % din cea declarată`;
    bn.innerHTML = `<span></span><small></small>`;
    bn.firstChild.textContent = `Rezultat: ${r.verdict}`;
    bn.lastChild.textContent = `${r.capacity_ah.toFixed(3)} Ah (${r.capacity_pct.toFixed(1)} %), ${r.energy_wh.toFixed(1)} Wh, ${hms(r.duration_s)} — ${why}`;
  }
}

/* ---------- grafice ---------- */
function plot(canvas, pts, o) {
  const dpr = window.devicePixelRatio || 1, W = canvas.clientWidth, H = canvas.clientHeight;
  if (!W || !H) return;
  canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
  const cx = canvas.getContext("2d"); cx.setTransform(dpr, 0, 0, dpr, 0, 0); cx.clearRect(0, 0, W, H);
  const L = 52, R = 10, T = 8, Bm = 22, w = W - L - R, h = H - T - Bm;
  cx.font = "11px Consolas, 'DejaVu Sans Mono', monospace"; cx.textBaseline = "middle";
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const [x, y] of pts) { if (y == null) continue; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
  if (!isFinite(x0)) { cx.fillStyle = "#6f828c"; cx.fillText("fără date", L + 8, T + 14); return; }
  if (o.zero) y0 = Math.min(0, y0);
  if (x1 - x0 < 1e-9) x1 = x0 + 1;
  let span = Math.max(y1 - y0, o.minSpan || 0.01); const pad = span * 0.1; y1 = y0 + span + pad; if (!o.zero) y0 -= pad; span = y1 - y0;
  const X = (x) => L + (x - x0) / (x1 - x0) * w, Y = (y) => T + h - (y - y0) / span * h;
  cx.strokeStyle = "#1f2b31"; cx.fillStyle = "#6f828c"; cx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = y0 + span * i / 4, py = Y(y);
    cx.beginPath(); cx.moveTo(L, py); cx.lineTo(L + w, py); cx.stroke();
    cx.textAlign = "right"; cx.fillText(y.toFixed(o.dec ?? 2), L - 6, py);
  }
  for (let i = 0; i <= 4; i++) {
    const x = x0 + (x1 - x0) * i / 4; cx.textAlign = "center"; cx.fillText(o.xfmt(x), X(x), H - 9);
  }
  cx.strokeStyle = o.color; cx.lineWidth = 1.6; cx.beginPath();
  let pen = false;
  for (const [x, y] of pts) { if (y == null) { pen = false; continue; } pen ? cx.lineTo(X(x), Y(y)) : cx.moveTo(X(x), Y(y)); pen = true; }
  cx.stroke();
}
function drawCharts() {
  const s = (B.test && B.test.samples) || [];
  const tfmt = (x) => x >= 3600 ? (x / 3600).toFixed(1) + " h" : x >= 60 ? (x / 60).toFixed(0) + " min" : x.toFixed(0) + " s";
  plot($("cV"), s.map((p) => [p[0], p[1]]), {color: "#f4d03f", dec: 3, minSpan: 0.02, xfmt: tfmt});
  plot($("cA"), s.map((p) => [p[0], p[2]]), {color: "#3cc8e8", dec: 2, minSpan: 0.1, zero: true, xfmt: tfmt});
  let ah = 0, prev = null; const d = [];
  for (const p of s) { if (prev) ah += (p[2] + prev[2]) / 2 * (p[0] - prev[0]) / 3600; prev = p; d.push([ah, p[1]]); }
  plot($("cD"), d, {color: "#ee6aa7", dec: 3, minSpan: 0.02, xfmt: (x) => x.toFixed(x < 10 ? 2 : 1) + " Ah"});
  plot($("cT"), s.map((p) => [p[0], p[4]]), {color: "#9fe870", dec: 0, minSpan: 2, xfmt: tfmt});
}

/* ---------- test curent / istoric ---------- */
async function showTest(id) {
  const t = await api("/api/bct/test?id=" + encodeURIComponent(id) + "&max=1200");
  if (t.error) { log("Test: " + t.error, true); return; }
  B.test = t; B.curId = id;
  if (!ACTIVE.includes(B.status.state) || B.status.id !== id) {
    const r = t.result || {};
    B.status = {state: t.state, id, message: r.end_reason || "", ah: r.capacity_ah || 0, wh: r.energy_wh || 0, elapsed: r.duration_s || 0,
                ri_mohm: r.ri_mohm, soc_pct: null, result: t.result, battery: t.battery};
    renderStatus();
  }
  drawCharts();
}
async function pollChart() {
  if (ACTIVE.includes(B.status.state) && B.status.id) await showTest(B.status.id);
}
setInterval(pollChart, 3000);

/* ---------- comenzi ---------- */
$("start").onclick = async () => {
  const b = batteryFromForm();
  const extra = {client: $("f_client").value, serial: $("f_serial").value, operator: $("f_operator").value, notes: $("f_notes").value};
  for (const k of ["rated_ah", "nominal_v", "full_v", "empty_v", "discharge_a", "pass_pct"]) if (b[k] == null) { log("Completează toate câmpurile bateriei (butonul Calculează ajută).", true); return; }
  const r = await api("/api/bct/start", {battery: b, extra});
  if (!r.ok) { log("Start: " + r.error, true); return; }
  log("Test pornit."); B.curId = r.id; B.test = {samples: []}; await showTest(r.id);
};
$("pdf").onclick = async () => {
  const id = B.status.id;
  const r = await fetch("/api/bct/report?id=" + encodeURIComponent(id));
  if (!r.ok) { const e = await r.json().catch(() => ({})); log("Certificat: " + (e.error || "eroare"), true); return; }
  const blob = await r.blob(), a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.target = "_blank"; a.download = "certificat-BTX-" + id + ".pdf"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  log("Certificatul PDF a fost generat.");
};
$("stop").onclick = $("stopTop").onclick = async () => {
  const r = await api("/api/bct/stop", {});
  log(r.ok ? "Oprire cerută." : "Stop: " + (r.error || "eroare"), !r.ok);
};

/* ---------- flux live ---------- */
function init() {
  loadCatalog();
  fetch("/api/state").then((r) => r.json()).then((s) => {
    setText("devTitle", s.device.title + " · " + s.device.link);
    B.connected = s.state.connected; B.live = s.state.live || {}; renderLive(); renderStatus();
  }).catch(() => {});
  fetch("/api/bct/status").then((r) => r.json()).then(async (s) => { B.status = s; renderStatus(); if (s.id) await showTest(s.id); }).catch(() => {});
  const es = new EventSource("/api/stream");
  es.addEventListener("sample", (ev) => { B.live = JSON.parse(ev.data); B.connected = true; renderLive(); if (!B.running) { B.running = true; renderStatus(); } });
  es.addEventListener("status", (ev) => { B.connected = JSON.parse(ev.data).connected; renderStatus(); renderLive(); });
  es.addEventListener("bct", async (ev) => {
    const prev = B.status.state; B.status = JSON.parse(ev.data); renderStatus();
    if (prev !== B.status.state && !ACTIVE.includes(B.status.state)) { await showTest(B.status.id); const c = await api("/api/bct/catalog"); if (!c.error) { B.catalog = c; renderHistory(); } }
  });
  es.onerror = () => { B.connected = false; renderStatus(); renderLive(); };
}
new ResizeObserver(drawCharts).observe(document.querySelector(".charts"));
init();
