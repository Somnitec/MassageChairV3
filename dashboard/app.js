"use strict";
// Dashboard client: subscribe to the chair host's event stream, render the
// chair graphic + interface, and POST button presses back. No framework.

const ASSETS = "/assets/chair/";
const LS_KEY = "chair_v3_settings";

const OVERLAYS = [
  "roller_pounding_on", "roller_kneading_on", "roller_up_on", "roller_down_on",
  "feet_roller_on", "airbag_shoulders_on", "airbag_arms_on", "airbag_legs_on",
  "airbag_outside_on", "airpump_on", "butt_vibration_on",
  "chair_up_on", "chair_down_on", "chair_status_up", "chair_status_down",
];

const $ = (sel) => document.querySelector(sel);
const overlayEls = {};
let streaming = false;
let clock = { elapsed: 0, session_s: 0, base: Date.now() };
let isGenerating = false;
let isSpeaking   = false;
let _pendingOptions = null;
let sensorHeadphones = false;
let sensorSitting    = false;
let chairState       = "idle";
// overlay state — mirrored from the latest panel_update
let activeOverlays  = new Set();
let panelStatus     = "green";
// roller position tracked locally for smooth cursor animation
let manualRollerPos = 0.5;

// hotspot → overlay name mapping
const HOTSPOT_OVERLAY = {
  knead:      "roller_kneading_on",
  pound:      "roller_pounding_on",
  shoulders:  "airbag_shoulders_on",
  arms:       "airbag_arms_on",
  legs:       "airbag_legs_on",
  feet:       "feet_roller_on",
  airbags:    "airbag_outside_on",
  airpump:    "airpump_on",
  vibration:  "butt_vibration_on",
  recline:    "chair_down_on",
};

// model loading state
let _modelReady   = false;
let _loadingModel = "";

// settings countdown
let _cdTimer = null;
let _cdSecs  = 0;

// --- localStorage helpers ------------------------------------------------
function _readLS() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; }
}
function _writeLS(s) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(s)); } catch {}
}

// --- build the layered chair --------------------------------------------
function buildChair() {
  const chair = $("#chair");

  const base = document.createElement("img");
  base.src = ASSETS + "chair_background.png";
  base.className = "layer base";
  chair.insertBefore(base, chair.firstChild);

  const tint = document.createElement("div");
  tint.className = "layer tint";
  tint.id = "backlight-tint";
  tint.style.webkitMaskImage = tint.style.maskImage = `url(${ASSETS}backlight_on.png)`;
  chair.insertBefore(tint, chair.firstChild.nextSibling);

  for (const name of OVERLAYS) {
    const img = document.createElement("img");
    img.src = ASSETS + name + ".png";
    img.className = "layer hidden";
    chair.insertBefore(img, chair.querySelector(".hotspot"));
    overlayEls[name] = img;
  }

  for (const s of ["green", "red"]) {
    const img = document.createElement("img");
    img.src = ASSETS + "redgreen_statuslight_" + s + ".png";
    img.className = "layer status hidden";
    chair.insertBefore(img, chair.querySelector(".hotspot"));
    overlayEls["status_" + s] = img;
  }

  const cursor = document.createElement("img");
  cursor.src = ASSETS + "roller_position_cursor.png";
  cursor.className = "layer cursor";
  cursor.id = "cursor";
  chair.insertBefore(cursor, chair.querySelector(".hotspot"));
}

function renderPanel(p) {
  if (!p) return;

  // sync mirror state
  activeOverlays = new Set(p.layers);
  if (p.status) panelStatus = p.status;
  if (p.roller_pos != null) manualRollerPos = p.roller_pos;

  for (const name of OVERLAYS) {
    overlayEls[name].classList.toggle("hidden", !activeOverlays.has(name));
  }
  const tint = $("#backlight-tint");
  tint.style.background = p.led_css;
  tint.classList.toggle("hidden", !activeOverlays.has("backlight_on"));

  overlayEls.status_green.classList.toggle("hidden", p.status !== "green");
  overlayEls.status_red.classList.toggle("hidden",   p.status !== "red");

  // roller_pos 0 = feet (bottom), 1 = neck (top); track range: +2% (bottom) to -16% (top)
  if (!_rollerHoldDir) {
    $("#cursor").style.transform = `translateY(${(2 - p.roller_pos * 18).toFixed(1)}%)`;
  }

  for (const k of ["intensity", "speed", "vibration"]) {
    $(`[data-bar=${k}]`).style.width = p[k] + "%";
    $(`[data-val=${k}]`).textContent = p[k];
  }
  $("#technique").textContent = p.technique;
  $("#areas").textContent = (p.areas || []).join(", ") || "—";
  $("#airbags").textContent = p.airbags ? "ON" : "off";
  $("#led").textContent = p.led_color;
  $("#led-swatch").style.background = p.led_css;

  updateAreaLegend(p.areas || []);
}

function renderTurn(s, showOptions) {
  $("#phase").textContent = "phase: " + s.phase;
  $("#latency").textContent = (s.latency_s != null ? s.latency_s + "s" : "—");
  if (!streaming) $("#spoken").textContent = s.spoken_text || "…";
  if (showOptions) {
    setOptions(s.screen_options, false);
  }
  renderPanel(s.panel);
  renderLeds(s.button_leds);
  if (s.profile) renderProfile(s.profile);
  clock = { elapsed: s.elapsed || 0, session_s: s.session_s || clock.session_s, base: Date.now() };
  tickClock();
  if (s.expired) addLog({ line: "— session over —", level: "warn" });
}

function renderLeds(leds) {
  if (!leds) return;
  document.querySelectorAll(".led-btn[data-led]").forEach((btn) => {
    const v = leds[btn.dataset.led] ?? 30;
    const alpha = (v / 100).toFixed(2);
    btn.style.boxShadow = v > 5
      ? `0 0 ${4 + v / 10}px ${v / 20}px rgba(255,179,71,${alpha}),
         inset 0 0 ${v / 15}px rgba(255,179,71,${alpha * 0.4})`
      : "";
    btn.style.borderColor = v > 5 ? `rgba(255,179,71,${0.3 + alpha * 0.7})` : "";
  });
}

function setOptions(opts, thinking) {
  document.querySelectorAll(".opt").forEach((b, i) => {
    if (thinking) {
      b.classList.add("thinking");
      b.dataset.realText = b.dataset.realText || b.textContent;
    } else {
      b.classList.remove("thinking");
      delete b.dataset.realText;
      b.textContent = (opts && opts[i]) || "…";
    }
  });
}

function renderProfile(pr) {
  $("#sentiment").textContent = pr.sentiment || "—";
  $("#note").textContent = pr.note || "";
  $("#traits").textContent = (pr.inferred_traits && pr.inferred_traits.length)
    ? "traits: " + pr.inferred_traits.join(", ") : "";
  $("#trail").textContent = (pr.sentiment_log && pr.sentiment_log.length)
    ? "trail: " + pr.sentiment_log.join(" → ") : "";
}

// --- generating / speaking state ----------------------------------------
function setGenerating(active) {
  isGenerating = active;
  $("#gen-indicator").classList.toggle("hidden", !active);
  $("#gen-cursor").classList.toggle("hidden", !active);
  $("#speech-box").classList.toggle("generating", active);
  if (active) {
    setOptions(null, true);
    if (!streaming) { $("#spoken").textContent = ""; streaming = true; }
  } else {
    streaming = false;
    $("#gen-cursor").classList.add("hidden");
    if (isSpeaking) setOptions(null, true);
  }
}

function onSpeakingDone(opts) {
  isSpeaking = false;
  _pendingOptions = null;
  setOptions(opts, false);
}

// --- streaming spoken text ----------------------------------------------
function onDelta(text) {
  if (!streaming) { $("#spoken").textContent = ""; streaming = true; }
  $("#spoken").textContent += text;
}

// --- model loading overlay ----------------------------------------------
function showModelLoading(model) {
  _modelReady   = false;
  _loadingModel = model;
  $("#loading-label").textContent = `loading ${model}…`;
  $("#loading-label").style.color = "";
  $("#loading-spinner").style.display = "";
  $("#loading-retry").classList.add("hidden");
  $("#model-loading").classList.remove("hidden");
}

function hideModelLoading() {
  _modelReady = true;
  $("#model-loading").classList.add("hidden");
}

// --- sensor state -------------------------------------------------------
const STATE_LABELS = {
  idle:             "IDLE",
  headphones_only:  "HEADPHONES",
  sitting_only:     "SITTING",
  active:           "ACTIVE",
};

function updateSensorUI(state, headphones, sitting) {
  chairState       = state || chairState;
  sensorHeadphones = headphones;
  sensorSitting    = sitting;

  const pill = $("#state-pill");
  pill.textContent = STATE_LABELS[chairState] || chairState.toUpperCase();
  pill.className = pill.className.replace(/\bstate-\S+/g, "").trim();
  pill.classList.add("state-pill", "state-" + chairState);

  const hBtn = $("#toggle-headphones");
  hBtn.classList.toggle("sensor-on",  sensorHeadphones);
  hBtn.classList.toggle("sensor-off", !sensorHeadphones);

  const sBtn = $("#toggle-sitting");
  sBtn.classList.toggle("sensor-on",  sensorSitting);
  sBtn.classList.toggle("sensor-off", !sensorSitting);

  const active = chairState === "active";
  document.querySelectorAll(".opt, .ctl, .rate, .vol, .lang").forEach((b) => {
    b.disabled = !active;
    b.style.opacity = active ? "" : "0.4";
  });
}

function toggleSensor(which) {
  const h = which === "headphones" ? !sensorHeadphones : sensorHeadphones;
  const s = which === "sitting"    ? !sensorSitting    : sensorSitting;
  fetch("/sensor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ headphones: h, sitting: s }),
  }).catch(() => {});
}

// --- log + physical-press highlight -------------------------------------
function addLog(e) {
  const ul = $("#log");
  const li = document.createElement("li");
  const ts = e.ts ? `<span class="ts">${escapeHtml(e.ts)}</span> ` : "";
  if (e.type === "button") {
    const who = e.source === "physical" ? "physical" : "you";
    li.innerHTML = `${ts}<span class="who ${e.source}">${who}</span> ${escapeHtml(e.label)}`;
    if (e.source === "physical") flashControl(e);
  } else {
    li.className = "sys " + (e.level || "");
    li.innerHTML = ts + escapeHtml(e.line);
  }
  ul.appendChild(li);
  while (ul.children.length > 200) ul.removeChild(ul.firstChild);
  ul.scrollTop = ul.scrollHeight;
}

function flashControl(e) {
  let el = null;
  if (e.kind === "OPTION") el = document.querySelector(`.opt[data-opt="${e.value}"]`);
  else if (e.kind === "RATING") el = document.querySelector(`.rate[data-rate="${e.value}"]`);
  else if (e.kind) el = document.querySelector(`.ctl[data-btn="${e.kind}"]`);
  if (el) { el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 700); }
}

const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// --- send presses --------------------------------------------------------
function press(button, value) {
  if (chairState !== "active") return;
  fetch("/press", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ button, value, source: "dashboard" }),
  }).catch(() => {});
}

function wireControls() {
  document.querySelectorAll(".opt").forEach((b) =>
    b.addEventListener("click", () => press("OPTION", +b.dataset.opt)));
  document.querySelectorAll(".ctl").forEach((b) =>
    b.addEventListener("click", () => press(b.dataset.btn)));
  document.querySelectorAll(".rate").forEach((b) =>
    b.addEventListener("click", () => press("RATING", +b.dataset.rate)));
  document.querySelectorAll(".vol").forEach((b) =>
    b.addEventListener("click", () => press("VOLUME", +b.dataset.vol)));
  document.querySelectorAll(".lang").forEach((b) =>
    b.addEventListener("click", () => press("LANGUAGE", b.dataset.dir)));
  $("#toggle-headphones").addEventListener("click", () => toggleSensor("headphones"));
  $("#toggle-sitting").addEventListener("click",    () => toggleSensor("sitting"));
}

// --- hotspot clicks — single chair-level handler fires all hit zones ----
function postOverlay(body) {
  fetch("/overlay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).catch(() => {});
}

function wireHotspots() {
  const chair = $("#chair");
  chair.addEventListener("click", (e) => {
    const cx = e.clientX, cy = e.clientY;

    const overlayHits = new Set();
    let   hitStatus       = false;
    let   rollerTrackRect = null;

    document.querySelectorAll(".hotspot").forEach((hs) => {
      if (hs.dataset.rollerDir) return;   // hold buttons — handled separately
      const r = hs.getBoundingClientRect();
      if (cx < r.left || cx > r.right || cy < r.top || cy > r.bottom) return;

      const key = hs.dataset.area || hs.dataset.technique || hs.dataset.toggle;
      if (key === "status") { hitStatus = true; return; }
      const ov = key ? HOTSPOT_OVERLAY[key] : null;
      if (ov) overlayHits.add(ov);
      if ("rollerTrack" in hs.dataset) rollerTrackRect = hs.getBoundingClientRect();
    });

    // each overlay toggled independently; server handles mutual exclusion
    for (const ov of overlayHits) {
      postOverlay({ name: ov, active: !activeOverlays.has(ov) });
    }

    // status light: flip red ↔ green
    if (hitStatus) {
      postOverlay({ status: panelStatus === "green" ? "red" : "green" });
    }

    // roller track seek: top of track = neck = pos 1; bottom = feet = pos 0
    if (rollerTrackRect) {
      manualRollerPos = Math.max(0, Math.min(1,
        1 - (cy - rollerTrackRect.top) / rollerTrackRect.height));
      $("#cursor").style.transform =
        `translateY(${(2 - manualRollerPos * 18).toFixed(1)}%)`;
      postOverlay({ roller_pos: manualRollerPos, source: "seek" });
    }
  });
}

// --- roller hold buttons: show overlay + move cursor while held -----------
// TODO [Phase 3 — real chair]: Replace the simulated roller_pos with dead-reckoning
// from actual motor run time. On boot, the roller runs down to bottom_sensor then
// up to top_sensor; transit time is measured and averaged over several calibration
// runs to build a px/ms constant. Subsequent up/down commands accumulate elapsed
// time to estimate position. The bottom_sensor and top_sensor sprites in
// assets/chair/ already exist for the UI indicator.

let _rollerHoldRaf  = null;   // requestAnimationFrame id
let _rollerPostTimer = null;  // setInterval id for throttled POSTs
let _rollerHoldDir  = 0;      // -1 = up (toward neck), +1 = down (toward feet)
let _rollerHoldEl   = null;   // the button element being held

// Speed calibration: fraction of full travel per second while holding.
// Will be replaced by real motor timing in Phase 3.
const ROLLER_SPEED_PER_SEC = 0.25;
let _rollerLastTick = 0;

function _rollerTick(ts) {
  if (!_rollerHoldDir) return;
  const dt = _rollerLastTick ? Math.min((ts - _rollerLastTick) / 1000, 0.1) : 0;
  _rollerLastTick = ts;
  // dir=-1 = up = toward neck = toward pos 1, so negate dir
  manualRollerPos = Math.max(0, Math.min(1, manualRollerPos - _rollerHoldDir * ROLLER_SPEED_PER_SEC * dt));
  const pct = (2 - manualRollerPos * 18).toFixed(1);
  const cursor = $("#cursor");
  if (cursor) cursor.style.transform = `translateY(${pct}%)`;
  _rollerHoldRaf = requestAnimationFrame(_rollerTick);
}

function _startRollerHold(el, dir) {
  _stopRollerHold();
  _rollerHoldDir  = dir;
  _rollerHoldEl   = el;
  _rollerLastTick = 0;
  el.classList.add("hs-held");
  postOverlay({ roller_dir: dir < 0 ? "up" : "down" });
  _rollerHoldRaf   = requestAnimationFrame(_rollerTick);
  _rollerPostTimer = setInterval(() => postOverlay({ roller_pos: manualRollerPos }), 80);
}

function _stopRollerHold() {
  if (!_rollerHoldDir) return;
  cancelAnimationFrame(_rollerHoldRaf);
  clearInterval(_rollerPostTimer);
  _rollerHoldRaf = _rollerPostTimer = null;
  if (_rollerHoldEl) { _rollerHoldEl.classList.remove("hs-held"); _rollerHoldEl = null; }
  postOverlay({ roller_dir: "stop" });
  _rollerHoldDir = 0;
}

function wireRollerButtons() {
  document.querySelectorAll(".hotspot[data-roller-dir]").forEach((el) => {
    const dir = el.dataset.rollerDir === "up" ? -1 : 1;
    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      _startRollerHold(el, dir);
    });
    el.addEventListener("pointerup",     _stopRollerHold);
    el.addEventListener("pointercancel", _stopRollerHold);
  });
  // safety: stop if pointer leaves the window
  window.addEventListener("pointerup", _stopRollerHold);
}

function updateAreaLegend(areas) {
  areas = areas || [];
  $("#active-areas").textContent = areas.length ? areas.join(", ") : "none active";
  document.querySelectorAll(".hotspot[data-area]").forEach((hs) => {
    const ov = HOTSPOT_OVERLAY[hs.dataset.area];
    hs.classList.toggle("hs-active", ov ? activeOverlays.has(ov) : false);
  });
}

// --- settings countdown -------------------------------------------------
function _startCountdown() {
  _cdSecs = 10;
  _updateApplyBtn();
  _cdTimer = setInterval(() => {
    _cdSecs--;
    _updateApplyBtn();
    if (_cdSecs <= 0) {
      clearInterval(_cdTimer);
      _cdTimer = null;
      saveSettings();
    }
  }, 1000);
}

function _cancelCountdown() {
  if (_cdTimer) { clearInterval(_cdTimer); _cdTimer = null; }
  _cdSecs = 0;
  _updateApplyBtn();
}

function _updateApplyBtn() {
  const btn = $("#settings-save");
  if (!btn) return;
  btn.textContent = (_cdTimer && _cdSecs > 0) ? `apply (${_cdSecs})` : "apply";
}

// --- settings panel -----------------------------------------------------
function _populateSettingsForm(s) {
  // model dropdown
  const sel = $("#s-model");
  const prev = sel.value;
  sel.innerHTML = "";
  for (const m of (s.models || [])) {
    const o = document.createElement("option");
    o.value = m; o.textContent = m;
    sel.appendChild(o);
  }
  // select: prefer current form value → localStorage → server default
  const local = _readLS();
  const want = prev || local.model || s.model;
  if (want) {
    // add if not in list
    if (![...sel.options].some(o => o.value === want)) {
      const o = document.createElement("option");
      o.value = want; o.textContent = want;
      sel.appendChild(o);
    }
    sel.value = want;
  }

  const lsSessionMin = local.session_s ? Math.round(local.session_s / 60) : null;
  const srvSessionMin = s.session_s ? Math.round(s.session_s / 60) : 10;

  const sentMin = local.sentences_min ?? s.sentences_min ?? 1;
  const sentMax = local.sentences_max ?? s.sentences_max ?? 5;
  const wMin    = local.words_min     ?? s.words_min     ?? 15;
  const wMax    = local.words_max     ?? s.words_max     ?? 100;

  $("#s-sent-min").value = sentMin;
  $("#s-sent-max").value = sentMax;
  $("#s-sent-range").textContent = `${sentMin} – ${sentMax}`;
  $("#s-words-min").value = wMin;
  $("#s-words-max").value = wMax;
  $("#s-words-range").textContent = `${wMin} – ${wMax}`;

  $("#s-session").value      = lsSessionMin          ?? srvSessionMin;
  $("#s-session-val").textContent = $("#s-session").value;
  $("#s-tts").checked        = local.tts_enabled     ?? (s.tts_enabled !== false);

  // pattern buttons
  const pb = $("#pattern-btns");
  pb.innerHTML = "";
  for (const name of (s.patterns || [])) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pat-btn";
    btn.textContent = name.replace(/_/g, " ");
    btn.addEventListener("click", () => sendPattern(name));
    pb.appendChild(btn);
  }
}

function openSettings(withCountdown = false) {
  // Populate from localStorage immediately, then refresh from server
  const local = _readLS();
  if (local.sentences_min != null) { $("#s-sent-min").value = local.sentences_min; }
  if (local.sentences_max != null) { $("#s-sent-max").value = local.sentences_max; }
  if (local.sentences_min != null || local.sentences_max != null) {
    $("#s-sent-range").textContent = `${$("#s-sent-min").value} – ${$("#s-sent-max").value}`;
  }
  if (local.words_min != null) { $("#s-words-min").value = local.words_min; }
  if (local.words_max != null) { $("#s-words-max").value = local.words_max; }
  if (local.words_min != null || local.words_max != null) {
    $("#s-words-range").textContent = `${$("#s-words-min").value} – ${$("#s-words-max").value}`;
  }
  if (local.session_s) {
    const min = Math.round(local.session_s / 60);
    $("#s-session").value = min;
    $("#s-session-val").textContent = min;
  }
  if (local.tts_enabled !== undefined) {
    $("#s-tts").checked = local.tts_enabled;
  }

  fetch("/settings")
    .then(r => r.json())
    .then(s => _populateSettingsForm(s))
    .catch(() => {});

  $("#settings-overlay").classList.remove("hidden");

  if (withCountdown) _startCountdown();
}

function closeSettings(e) {
  if (!e || e.target === $("#settings-overlay") || e.currentTarget === $("#settings-close")) {
    if (!_modelReady) {
      // First startup: closing without applying → apply current values
      saveSettings();
      return;
    }
    _cancelCountdown();
    $("#settings-overlay").classList.add("hidden");
  }
}

function saveSettings() {
  _cancelCountdown();
  const sentMin = Math.min(+$("#s-sent-min").value, +$("#s-sent-max").value);
  const sentMax = Math.max(+$("#s-sent-min").value, +$("#s-sent-max").value);
  const wMin    = Math.min(+$("#s-words-min").value, +$("#s-words-max").value);
  const wMax    = Math.max(+$("#s-words-min").value, +$("#s-words-max").value);
  const body = {
    model:         $("#s-model").value,
    sentences_min: sentMin,
    sentences_max: sentMax,
    words_min:     wMin,
    words_max:     wMax,
    session_s:     +$("#s-session").value * 60,
    tts_enabled:   $("#s-tts").checked,
  };
  _writeLS(body);
  fetch("/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).catch(() => {});
  // Trigger model load and show loading overlay
  showModelLoading(body.model);
  fetch("/warmup", { method: "POST" }).catch(() => {});
  $("#settings-overlay").classList.add("hidden");
}

function sendPattern(name) {
  fetch("/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pattern: name }),
  }).catch(() => {});
}

function wireSettings() {
  $("#settings-btn").addEventListener("click", () => openSettings(false));
  $("#settings-close").addEventListener("click", (e) => closeSettings({ currentTarget: e.currentTarget }));
  $("#settings-overlay").addEventListener("click", closeSettings);
  $("#settings-save").addEventListener("click", saveSettings);

  // Cancel countdown if user touches any control
  ["s-model", "s-sent-min", "s-sent-max", "s-words-min", "s-words-max",
   "s-session", "s-tts"].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", _cancelCountdown);
    el.addEventListener("input",  _cancelCountdown);
  });

  // Live display for sentence range
  const _updateSentRange = () => {
    const lo = Math.min(+$("#s-sent-min").value, +$("#s-sent-max").value);
    const hi = Math.max(+$("#s-sent-min").value, +$("#s-sent-max").value);
    $("#s-sent-range").textContent = `${lo} – ${hi}`;
  };
  $("#s-sent-min").addEventListener("input", _updateSentRange);
  $("#s-sent-max").addEventListener("input", _updateSentRange);

  // Live display for words range
  const _updateWordsRange = () => {
    const lo = Math.min(+$("#s-words-min").value, +$("#s-words-max").value);
    const hi = Math.max(+$("#s-words-min").value, +$("#s-words-max").value);
    $("#s-words-range").textContent = `${lo} – ${hi}`;
  };
  $("#s-words-min").addEventListener("input", _updateWordsRange);
  $("#s-words-max").addEventListener("input", _updateWordsRange);

  $("#s-session").addEventListener("input", () => {
    $("#s-session-val").textContent = $("#s-session").value;
  });

  // Retry button on loading overlay
  $("#loading-retry").addEventListener("click", () => {
    if (_loadingModel) {
      showModelLoading(_loadingModel);
      fetch("/warmup", { method: "POST" }).catch(() => {});
    }
  });
}

// --- local clock between turns ------------------------------------------
function tickClock() {
  if (chairState !== "active") {
    $("#clock").textContent = clock.session_s ? `t = 0s / ${clock.session_s}s` : `t = —`;
    return;
  }
  const secs = clock.elapsed + Math.floor((Date.now() - clock.base) / 1000);
  const shown = Math.min(secs, clock.session_s);
  $("#clock").textContent = `t = ${shown}s / ${clock.session_s}s`;
}
setInterval(tickClock, 1000);

// --- animated thinking dots on screen buttons ---------------------------
let _thinkFrame = 0;
const _THINK_FRAMES = ["thinking.", "thinking..", "thinking..."];
setInterval(() => {
  if (!isGenerating && !isSpeaking) return;
  _thinkFrame = (_thinkFrame + 1) % _THINK_FRAMES.length;
  document.querySelectorAll(".opt.thinking").forEach((b) => {
    b.textContent = _THINK_FRAMES[_thinkFrame];
  });
}, 450);

// --- event stream --------------------------------------------------------
function connect() {
  const es = new EventSource("/events");
  es.onopen = () => {
    $("#conn").textContent = "live";
    $("#conn").classList.remove("off");
  };
  es.onerror = () => {
    $("#conn").textContent = "reconnecting…";
    $("#conn").classList.add("off");
  };
  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    switch (e.type) {
      case "hello":
        (e.log || []).forEach(addLog);
        if (e.state) {
          renderTurn(e.state, true);
          updateSensorUI(e.state.chair_state, !!e.state.headphones, !!e.state.sitting);
          setGenerating(!!e.state.generating);
        }
        break;
      case "status":
        setGenerating(!!e.generating);
        if (e.chair_state) updateSensorUI(e.chair_state, sensorHeadphones, sensorSitting);
        break;
      case "sensors":
        updateSensorUI(e.chair_state, !!e.headphones, !!e.sitting);
        break;
      case "state_update":
        if (e.screen_options && !isSpeaking) setOptions(e.screen_options, false);
        if (e.spoken_text !== undefined && !isGenerating)
          $("#spoken").textContent = e.spoken_text || "…";
        if (e.chair_state) updateSensorUI(e.chair_state, sensorHeadphones, sensorSitting);
        break;
      case "delta":
        onDelta(e.text);
        break;
      case "turn":
        streaming = false;
        isSpeaking = true;
        _pendingOptions = e.screen_options;
        setGenerating(false);
        renderTurn(e, false);
        setOptions(null, true);
        break;
      case "speaking_done":
        onSpeakingDone(e.screen_options || _pendingOptions);
        break;
      case "clock_reset":
        clock = { elapsed: 0, session_s: e.session_s || clock.session_s, base: Date.now() };
        tickClock();
        break;
      case "panel_update":
        renderPanel(e.panel);
        break;
      case "button":
        addLog(e);
        break;
      case "log":
        addLog(e);
        break;
      case "model_ready":
        hideModelLoading();
        break;
      case "model_error":
        $("#loading-label").textContent = `⚠ ${e.error || "load failed"}`;
        $("#loading-label").style.color = "var(--red)";
        $("#loading-spinner").style.display = "none";
        $("#loading-retry").classList.remove("hidden");
        break;
    }
  };
}

buildChair();
wireControls();
wireHotspots();
wireRollerButtons();
wireSettings();
updateAreaLegend([]);
connect();
// Auto-open settings with countdown on every page load
openSettings(true);
