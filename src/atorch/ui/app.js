"use strict";
const $ = (id) => document.getElementById(id);
const MODES = ["CC", "CV", "CR", "CP", "BRT", "PT", "CT", "CDC", "CDCDC", "CDxN", "Dynamic load", "BCT"];
const SP_UNIT = ["A", "V", "Ω", "W"];
const SP_NAME = ["Curent setat", "Tensiune setată", "Rezistență setată", "Putere setată"];
const FIELD_NAMES = {setpoint: "Valoare setată", cutoff: "Tensiune de oprire", ocp: "Curent maxim",
  opp: "Putere maximă", full_voltage: "Tensiune full", ntc_otp: "Temperatură sondă", mos_otp: "Temperatură MOSFET"};
const CH = [
  {key: "voltage", name: "V", color: "#f4d03f", minSpan: 0.02, zero: false},
  {key: "current", name: "A", color: "#3cc8e8", minSpan: 0.1, zero: true},
  {key: "power", name: "W", color: "#ee6aa7", minSpan: 0.5, zero: true},
];

const S = {connected: false, running: false, settings: {}, live: {}, buf: [], win: 60, paused: false, pauseT: 0, limits: {}};

/* ---------- jurnal ---------- */
function log(msg, err) {
  const li = document.createElement("li");
  if (err) li.className = "err";
  const t = document.createElement("time");
  t.textContent = new Date().toLocaleTimeString("ro-RO");
  li.append(t, document.createTextNode(msg));
  $("log").prepend(li);
  while ($("log").children.length > 40) $("log").lastChild.remove();
}

/* ---------- API ---------- */
async function api(path, body) {
  try {
    const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const j = await r.json();
    return j;
  } catch (e) {
    return {ok: false, error: "serverul nu răspunde"};
  }
}

/* ---------- afișaj ---------- */
function fmtRead(v) {
  if (v == null || !isFinite(v)) return "--.---";
  if (Math.abs(v) >= 1000) return v.toFixed(1);
  if (Math.abs(v) >= 100) return v.toFixed(2);
  return v.toFixed(3);
}
function setText(id, t) { $(id).textContent = t; }

function renderLive() {
  const L = S.live, ok = S.connected && L.voltage != null;
  for (const [id, k] of [["rV", "voltage"], ["rA", "current"], ["rW", "power"]]) {
    setText(id, ok ? fmtRead(L[k]) : "--.---");
    $(id).parentElement.classList.toggle("stale", !ok);
  }
  if (!ok) { for (const id of ["sR", "sWh", "sAh", "sTp", "sTm", "sTc", "sFan"]) setText(id, "—"); return; }
  setText("sR", L.resistance == null ? "—" : (L.resistance >= 9999.9 ? "deschis" : L.resistance.toFixed(3) + " Ω"));
  setText("sWh", L.energy_wh == null ? "—" : L.energy_wh.toFixed(3) + " Wh");
  setText("sAh", L.capacity_mah == null ? "—" : L.capacity_mah.toFixed(1) + " mAh");
  setText("sTp", L.temp_probe == null ? "—" : L.temp_probe.toFixed(1) + " °C");
  setText("sTm", L.temp_mos == null ? "—" : L.temp_mos.toFixed(1) + " °C");
  setText("sTc", L.temp_cpu == null ? "—" : L.temp_cpu.toFixed(1) + " °C");
  setText("sFan", L.fan == null ? "—" : L.fan.toFixed(0) + " %");
  renderGauge();
}

function renderStatus(err) {
  const lamp = $("lamp");
  lamp.className = "lamp " + (!S.connected ? "bad" : S.running ? "run" : "ok");
  setText("linkText", !S.connected ? ("Fără conexiune cu aparatul" + (err ? ": " + err : ""))
    : S.running ? "Sarcina este pornită" : "Conectat, sarcina oprită");
  $("start").disabled = !S.connected || S.running;
  $("cfg").disabled = !S.connected || S.running;
  $("lockNote").hidden = !(S.connected && S.running);
}

function renderSettings() {
  const s = S.settings, mode = s.mode;
  document.querySelectorAll("#modes button").forEach((b) => b.classList.toggle("on", Number(b.dataset.m) === mode));
  const electrical = mode >= 0 && mode <= 3;
  setText("spLabel", electrical ? SP_NAME[mode] : "Valoare setată");
  setText("spUnit", electrical ? SP_UNIT[mode] : "");
  $("in_setpoint").disabled = !electrical;
  document.querySelector('[data-set="setpoint"]').disabled = !electrical;
  setText("modeHint", mode == null ? "" : electrical ? "" : mode >= 10 ?
    `Aparatul este în modul ${MODES[mode] || mode}. Acest mod se selectează și se configurează de pe aparat; aici îl vezi doar.` :
    `Mod ${MODES[mode]} selectat. Parametrii lui (ex. trepte, durate) se configurează deocamdată de pe aparat.`);
  for (const name of ["setpoint", "cutoff", "full_voltage", "ocp", "opp", "ntc_otp", "mos_otp"]) syncInput("in_" + name, s[name]);
  syncInput("in_th", s.timer_hours); syncInput("in_tm", s.timer_minutes);
  const sp = electrical && s.setpoint != null ? `${MODES[mode]} ${trim(s.setpoint)} ${SP_UNIT[mode]}` : (mode != null ? MODES[mode] : "—");
  const cut = s.cutoff != null ? `, oprire la ${trim(s.cutoff)} V` : "";
  const tl = (s.timer_hours || s.timer_minutes) ? `, limită ${s.timer_hours} h ${s.timer_minutes} min` : "";
  setText("summary", sp + cut + tl);
  renderGauge();
}
/* Nivel baterie estimat: (V - tensiune descarcat) / (tensiune full - tensiune descarcat), ca la BCT. */
function renderGauge() {
  const s = S.settings, v = S.live && S.live.voltage;
  const lo = s.cutoff, hi = s.full_voltage;
  const ok = v != null && lo != null && hi != null && hi > lo;
  $("gaugeBox").hidden = !ok;
  if (!ok) return;
  const pct = Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100));
  setText("gaugePct", pct.toFixed(0) + " %");
  $("gaugeFill").style.width = pct + "%";
  setText("gaugeLo", trim(lo) + " V (descărcat)");
  setText("gaugeHi", trim(hi) + " V (full)");
}
function trim(v) { return Number(v.toFixed(4)).toString(); }
function syncInput(id, v) {
  const el = $(id);
  if (v == null || document.activeElement === el || el.dataset.dirty) return;
  el.value = Number.isInteger(v) ? String(v) : trim(v);
}

/* ---------- grafice ---------- */
const cv = $("chart"), cx = cv.getContext("2d");
let drawQueued = false;
function queueDraw() { if (!drawQueued) { drawQueued = true; requestAnimationFrame(() => { drawQueued = false; draw(); }); } }

function niceStep(span, n) {
  const raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
  return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
}
function decimals(step) { return Math.max(0, Math.min(6, -Math.floor(Math.log10(step)) + (step < 1 ? 0 : 0))); }

function draw() {
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (!W || !H) return;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, W, H);
  const buf = S.buf;
  const tEnd = S.paused ? S.pauseT : (buf.length ? buf[buf.length - 1].t : Date.now() / 1000);
  const t0 = tEnd - S.win;
  const left = 64, right = 12, top = 8, bottom = 24, gap = 8;
  const sh = (H - top - bottom - gap * 2) / 3, pw = W - left - right;
  const vis = buf.filter((p) => p.t >= t0 - 2 && p.t <= tEnd + 0.01);
  cx.font = "12px Consolas, 'DejaVu Sans Mono', monospace";
  cx.textBaseline = "middle";
  CH.forEach((ch, i) => {
    const y0 = top + i * (sh + gap);
    let lo = Infinity, hi = -Infinity;
    for (const p of vis) { const v = p[ch.key]; if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v; } }
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    if (ch.zero) lo = Math.min(0, lo);
    let span = Math.max(hi - lo, ch.minSpan);
    const padv = span * 0.12; hi += padv; if (!ch.zero || lo < 0) lo -= padv; span = hi - lo;
    const step = niceStep(span, 4), dec = decimals(step);
    const yOf = (v) => y0 + sh - ((v - lo) / (hi - lo)) * sh;
    cx.strokeStyle = "#1f2b31"; cx.lineWidth = 1; cx.fillStyle = ch.color + "cc"; cx.textAlign = "right";
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
      const y = Math.round(yOf(v)) + 0.5;
      cx.beginPath(); cx.moveTo(left, y); cx.lineTo(left + pw, y); cx.stroke();
      cx.fillText(v.toFixed(dec), left - 8, y);
    }
    cx.strokeStyle = "#2f3b41"; cx.strokeRect(left + 0.5, y0 + 0.5, pw, sh);
    cx.fillStyle = ch.color; cx.textAlign = "left"; cx.fillText(ch.name, left + 8, y0 + 12);
    // linia
    cx.beginPath(); cx.strokeStyle = ch.color; cx.lineWidth = 1.8; cx.lineJoin = "round";
    let prev = null, started = false;
    cx.save(); cx.beginPath(); cx.rect(left, y0, pw, sh); cx.clip(); cx.beginPath();
    for (const p of vis) {
      const v = p[ch.key]; if (v == null) continue;
      const x = left + ((p.t - t0) / S.win) * pw, y = yOf(v);
      if (!started || (prev != null && p.t - prev > 2)) cx.moveTo(x, y); else cx.lineTo(x, y);
      started = true; prev = p.t;
    }
    cx.stroke(); cx.restore();
  });
  // axa timpului
  cx.fillStyle = "#6f828c"; cx.textAlign = "center";
  const ticks = 4;
  for (let k = 0; k <= ticks; k++) {
    const sec = S.win - (S.win / ticks) * k, x = left + (pw / ticks) * k;
    const label = k === ticks ? "acum" : S.win >= 300 ? `−${Math.round(sec / 60)} min` : `−${Math.round(sec)} s`;
    cx.fillText(label, Math.min(Math.max(x, left + 14), left + pw - 14), H - 10);
  }
  if (S.paused) { cx.fillStyle = "#f4d03f"; cx.textAlign = "right"; cx.fillText("pauză", W - right - 6, top + 12); }
}

/* ---------- evenimente ---------- */
function applyState(st) {
  S.connected = !!st.connected; S.running = !!st.running;
  if (st.live && Object.keys(st.live).length) S.live = st.live;
  if (st.settings && Object.keys(st.settings).length) S.settings = st.settings;
  renderLive(); renderStatus(st.error); renderSettings();
}

async function init() {
  try {
    const st = await (await fetch("/api/state")).json();
    S.limits = st.limits;
    setText("devTitle", st.device.title); setText("devLink", st.device.link === "usb" ? "USB" : st.device.link);
    applyState(st.state);
    const hist = await (await fetch("/api/history")).json();
    S.buf = hist; queueDraw();
  } catch (e) { log("Nu pot citi starea de la server.", true); }
  const es = new EventSource("/api/stream");
  es.addEventListener("sample", (ev) => {
    const p = JSON.parse(ev.data);
    S.buf.push(p); if (S.buf.length > 7200) S.buf.splice(0, S.buf.length - 7200);
    S.live = p; S.connected = true;
    const was = S.running; S.running = !!p.running;
    renderLive(); if (was !== S.running) renderStatus(); queueDraw();
  });
  es.addEventListener("settings", (ev) => { S.settings = JSON.parse(ev.data); renderSettings(); });
  es.addEventListener("status", (ev) => { const d = JSON.parse(ev.data); S.connected = d.connected; renderStatus(d.error); renderLive(); if (!d.connected) log("Conexiunea cu aparatul s-a pierdut. Se reîncearcă automat.", true); else log("Conectat la aparat."); });
  es.onerror = () => { S.connected = false; renderStatus("serverul nu răspunde"); renderLive(); };
  es.onopen = () => { fetch("/api/state").then((r) => r.json()).then((s) => applyState(s.state)).catch(() => {}); };
}

/* ---------- comenzi ---------- */
async function run(label, body, path) {
  const r = await api(path, body);
  log(r.ok ? `${label}: ${r.message}` : `${label}: ${r.error}`, !r.ok);
  return r;
}
$("start").onclick = () => run("Start", {on: true}, "/api/power");
$("stop").onclick = $("stopTop").onclick = () => run("Stop", {on: false}, "/api/power");
document.querySelectorAll("#modes button").forEach((b) => b.onclick = () => run("Mod " + b.textContent, {mode: Number(b.dataset.m)}, "/api/mode"));
document.querySelectorAll("[data-set]").forEach((b) => {
  const name = b.dataset.set, input = $("in_" + name);
  const go = async () => {
    const v = parseFloat(input.value);
    if (!isFinite(v)) { log(`${FIELD_NAMES[name]}: introdu un număr.`, true); return; }
    const r = await run(FIELD_NAMES[name], {name, value: v}, "/api/value");
    if (r.ok) { delete input.dataset.dirty; input.blur(); }
  };
  b.onclick = go;
  input.addEventListener("input", () => { input.dataset.dirty = "1"; });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
});
$("setTimer").onclick = async () => {
  const h = parseInt($("in_th").value || "0", 10), m = parseInt($("in_tm").value || "0", 10);
  const r = await run("Limită de timp", {hours: h, minutes: m}, "/api/timer");
  if (r.ok) { delete $("in_th").dataset.dirty; delete $("in_tm").dataset.dirty; }
};
for (const id of ["in_th", "in_tm"]) $(id).addEventListener("input", () => { $(id).dataset.dirty = "1"; });

document.querySelectorAll("#win button").forEach((b) => b.onclick = () => {
  document.querySelectorAll("#win button").forEach((x) => x.classList.remove("on"));
  b.classList.add("on"); S.win = Number(b.dataset.s); queueDraw();
});
$("pause").onclick = () => {
  S.paused = !S.paused; S.pauseT = S.buf.length ? S.buf[S.buf.length - 1].t : 0;
  $("pause").classList.toggle("on", S.paused); $("pause").textContent = S.paused ? "Reia graficul" : "Pauză grafic"; queueDraw();
};
$("csv").onclick = () => {
  const cols = ["voltage", "current", "power", "resistance", "energy_wh", "capacity_mah", "temp_probe", "temp_mos", "temp_cpu", "fan", "running"];
  const head = ["timp_iso", "tensiune_V", "curent_A", "putere_W", "rezistenta_ohm", "energie_Wh", "capacitate_mAh", "temp_sonda_C", "temp_mosfet_C", "temp_cpu_C", "ventilator_pct", "sarcina_pornita"];
  const rows = S.buf.map((p) => [new Date(p.t * 1000).toISOString(), ...cols.map((c) => p[c] == null ? "" : (c === "running" ? (p[c] ? 1 : 0) : p[c]))].join(","));
  const blob = new Blob([head.join(",") + "\n" + rows.join("\n") + "\n"], {type: "text/csv"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = "atorch-" + new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-") + ".csv"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  log(`Exportate ${S.buf.length} eșantioane în CSV.`);
};
new ResizeObserver(queueDraw).observe(cv);
init();
