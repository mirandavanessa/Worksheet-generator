from __future__ import annotations

import hashlib
import random
import html
import json
import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont

import streamlit as st
import streamlit.components.v1 as components

from question_bank import (
    available_levels,
    available_strands,
    available_topics,
    generate_questions_by_template,
    generate_two_per_topic,
    get_template,
    regenerate_question,
    topics_in_strand,
)
from pdf_export import build_pdf_bytes


# Optional drawing canvas (per-question)
try:
    from streamlit_drawable_canvas import st_canvas  # type: ignore
    _CANVAS_OK = True
except Exception:
    st_canvas = None
    _CANVAS_OK = False

st.set_page_config(page_title="Maths Worksheet Generator", layout="wide")

BUILD_ID = "v39.34-html-scratchpad-widthfix-height"
print(f"BUILD={BUILD_ID}")
try:
    print("AVAILABLE_TOPICS=", available_topics())
except Exception as _e:
    print("TOPIC_LOAD_ERROR", _e)


# ---------- Persist sidebar selection in the URL (survives refresh on iPad) ----------
# We store the last-used selection (topics/strand/max_diff/levels) as a compact base64 JSON
# in the query string (param: sel). This prevents the app from reverting to Defaults
# after a browser refresh.


def _encode_sel_state(obj: dict) -> str:
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_sel_state(s: str) -> dict:
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    raw = base64.urlsafe_b64decode((s + pad).encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _qp_get(key: str):
    try:
        v = st.query_params.get(key)
        if isinstance(v, list):
            return v[0] if v else None
        return v
    except Exception:
        try:
            q = st.experimental_get_query_params()
            return (q.get(key) or [None])[0]
        except Exception:
            return None


def _qp_set(**kwargs):
    try:
        for k, v in kwargs.items():
            st.query_params[k] = v
    except Exception:
        try:
            st.experimental_set_query_params(**kwargs)
        except Exception:
            pass


def _load_selection_from_query_params(all_topics: list[str], all_strands: list[str]) -> bool:
    raw = _qp_get("sel")
    if not raw:
        return False
    try:
        data = _decode_sel_state(str(raw))
    except Exception:
        return False

    topics = data.get("topics", [])
    if not isinstance(topics, list):
        topics = []
    topics = [t for t in topics if isinstance(t, str) and t in all_topics]
    topics = sorted(topics, key=lambda x: all_topics.index(x))
    st.session_state["topics_select"] = topics

    strand = data.get("strand")
    if isinstance(strand, str) and strand in all_strands:
        st.session_state["strand_select"] = strand

    md = data.get("max_diff")
    if isinstance(md, int) and 1 <= md <= 5:
        st.session_state["max_diff"] = md

    levels = data.get("levels", {})
    if isinstance(levels, dict):
        for t, lvl in levels.items():
            if isinstance(t, str) and t in all_topics and isinstance(lvl, str):
                st.session_state[f"level__{_safe_topic_key(t)}"] = lvl

    return True


def _save_selection_to_query_params(topics: list[str], strand: str, max_diff: int, topics_levels: dict[str, str], all_topics: list[str]):
    topics = [t for t in topics if t in all_topics]
    topics = sorted(topics, key=lambda x: all_topics.index(x))

    payload = {
        "topics": topics,
        "strand": strand,
        "max_diff": int(max_diff),
        "levels": {t: topics_levels.get(t, "") for t in topics if topics_levels.get(t)},
    }
    enc = _encode_sel_state(payload)

    cur = _qp_get("sel")
    if (cur == enc) or (st.session_state.get("__last_sel_qp") == enc):
        return

    _qp_set(sel=enc)
    st.session_state["__last_sel_qp"] = enc


# ---------- Presets (stored in URL query params: presets=...) ----------
# Stores multiple named selections without requiring accounts.


def _load_presets_from_query_params() -> dict:
    raw = _qp_get("presets")
    if not raw:
        return {}
    try:
        data = _decode_sel_state(str(raw))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    # Expected: {name: {topics:[...], strand:"...", max_diff:int, levels:{...}}}
    out: dict = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, dict):
            out[k] = v
    return out


def _save_presets_to_query_params(presets: dict) -> None:
    try:
        enc = _encode_sel_state(presets)
    except Exception:
        return
    cur = _qp_get("presets")
    if (cur == enc) or (st.session_state.get("__last_presets_qp") == enc):
        return
    _qp_set(presets=enc)
    st.session_state["__last_presets_qp"] = enc



# ---------- Global UI CSS (keep action buttons small + dark grey; not affected by text scaling) ----------
st.markdown(
    r"""
<style>
/* Invert theme: white background, black text */
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stApp"], [data-testid="stMain"] {
  background: #ffffff !important;
  color: #000000 !important;
}
section[data-testid="stSidebar"], [data-testid="stSidebar"], [data-testid="stSidebarContent"] {
  background: #ffffff !important;
  color: #000000 !important;
}
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {
  background: #ffffff !important;
}
/* Default text colours */
div[data-testid="stMarkdownContainer"] { color: #000000; }
.katex, .katex-display { color: #000000; }

/* Slight top padding so controls aren't hidden behind Streamlit header */
.block-container { padding-top: 3.4rem; }

/* Action buttons (N/A/W/D/I/H etc + font size controls): keep tiny + dark grey.
   IMPORTANT: Streamlit renders button labels using a nested stMarkdownContainer,
   so we must override that too; otherwise the global text-scaling CSS will enlarge them.
*/
button[kind="secondary"],
button[data-testid="baseButton-secondary"],
div[data-testid="stButton"] > button,
div.stButton > button {
  padding: 0px 4px !important;
  font-size: 11px !important;     /* fixed size */
  line-height: 1 !important;
  height: 20px !important;
  min-height: 20px !important;
  min-width: 22px !important;
  background: rgba(255,255,255,0.92) !important;
  color: #555555 !important;
  border: 1px solid rgba(85,85,85,0.30) !important;
  border-radius: 6px !important;
}

button[kind="secondary"] *,
button[data-testid="baseButton-secondary"] *,
div[data-testid="stButton"] > button *,
div.stButton > button * {
  color: #555555 !important;
}

/* Force button-label typography to stay fixed (Streamlit uses stMarkdownContainer inside buttons) */
button[kind="secondary"] div[data-testid="stMarkdownContainer"] p,
button[kind="secondary"] div[data-testid="stMarkdownContainer"] span,
button[kind="secondary"] div[data-testid="stMarkdownContainer"] strong,
button[data-testid="baseButton-secondary"] div[data-testid="stMarkdownContainer"] p,
button[data-testid="baseButton-secondary"] div[data-testid="stMarkdownContainer"] span,
button[data-testid="baseButton-secondary"] div[data-testid="stMarkdownContainer"] strong,
div[data-testid="stButton"] > button div[data-testid="stMarkdownContainer"] p,
div[data-testid="stButton"] > button div[data-testid="stMarkdownContainer"] span,
div[data-testid="stButton"] > button div[data-testid="stMarkdownContainer"] strong,
div.stButton > button div[data-testid="stMarkdownContainer"] p,
div.stButton > button div[data-testid="stMarkdownContainer"] span,
div.stButton > button div[data-testid="stMarkdownContainer"] strong {
  font-size: 11px !important;
  line-height: 1 !important;
  margin: 0 !important;
  padding: 0 !important;
  color: #555555 !important;
}

/* Keep download button readable */
div[data-testid="stDownloadButton"] button {
  background: rgba(255,255,255,0.92) !important;
  color: #000000 !important;
  border: 1px solid rgba(0,0,0,0.25) !important;
  font-size: 14px !important;
  height: auto !important;
  padding: 6px 12px !important;
}
div[data-testid="stDownloadButton"] button * { color: #000000 !important; }

/* Sidebar primary button (Regenerate ALL) readable */
div[data-testid="stSidebar"] button[kind="primary"],
div[data-testid="stSidebar"] button[data-testid="baseButton-primary"] {
  background: rgba(255,255,255,0.92) !important;
  color: #000000 !important;
  border: 1px solid rgba(0,0,0,0.25) !important;
  font-size: 14px !important;
  height: auto !important;
  padding: 6px 12px !important;
}
div[data-testid="stSidebar"] button[kind="primary"] * { color: #000000 !important; }

/* Sidebar typography: reduce headings/labels/captions (not the dropdown list itself) */
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2 {
  font-size: 1.05rem !important;
}
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4 {
  font-size: 0.90rem !important;
}
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] .stCaption {
  font-size: 0.85rem !important;
}

/* Topic title styling (small + dark grey) */
.topic-title {
  font-size: 0.78rem !important;
  color: #555555 !important;
  font-weight: 650 !important;
  margin: 0.0rem 0 0.25rem 0 !important;
}

/* Practice page: question number colour */
.prac-num {
  color: #7fbfff !important;  /* light blue */
  font-weight: 800 !important;
}
/* Instruction line text (coloured banners) */
.inst-line {
  min-height: 2.0rem !important;
  display: flex !important;
  align-items: center !important;
  font-weight: 800 !important;
  letter-spacing: 0.03em !important;
  font-size: 1.68rem !important;  /* 30% smaller than previous 2.4rem */
  margin: 0.10rem 0 0.10rem 0 !important;
}

/* Remove border around the drawable canvas (scratch pad) */
iframe[title^="streamlit_drawable_canvas"],
iframe[title*="drawable_canvas"],
iframe[title*="streamlit_drawable_canvas"],
div[data-testid="stCanvas"] iframe {
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
}

</style>
""",
    unsafe_allow_html=True,
)


# ---------- Helpers ----------
DEFAULT_TOPICS = [
    "Continuing sequences",
    "Finding the nth term",
    "Using the nth term",
    "Solving 1 step equations",
    "Solving 2 step equations",
    "Finding percentages using non-calculator methods",
    "Finding percentages using calculator methods",
    "Increasing and decreasing by percentages using non-calculator methods",
    "Increasing and decreasing by percentages using calculator methods",
    "Completing the square",
    "Perimeter of rectilinear shapes",
    "Area of shapes",
    "Interior and exterior angles of polygons",
]

def _slot(topic: str, idx: int) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in topic)
    return f"{safe}__{idx}"

def _toggle(key: str, default: bool = False):
    st.session_state[key] = not st.session_state.get(key, default)

def _set_default(key: str, default):
    if key not in st.session_state:
        st.session_state[key] = default


# ---------- Callbacks ----------
def _shift_level(topic: str, delta: int, ids: list[str], safe_topic: str) -> None:
    """Shift the selected level for a topic (main-page − / + buttons)."""
    if not ids:
        return
    key_level = f"level__{safe_topic}"
    cur = st.session_state.get(key_level, ids[0])
    try:
        idx = ids.index(cur)
    except ValueError:
        idx = 0
    new_idx = max(0, min(len(ids) - 1, idx + int(delta)))
    new_level_id = ids[new_idx]

    # Update widget-backed state
    st.session_state[key_level] = new_level_id
    if 'topics_levels' not in st.session_state or not isinstance(st.session_state.get('topics_levels'), dict):
        st.session_state.topics_levels = {}
    st.session_state.topics_levels[topic] = new_level_id

    # Clear caches so questions regenerate cleanly
    st.session_state.generated = None
    st.session_state.pair_params_map = None
    st.session_state.level_name_map = None
    st.session_state.pdf_cache = None
    st.session_state.pdf_fp = None

def _safe_topic_key(topic: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in topic)

def _q_sig(prompt: str, latex: str, diagram_png: bytes | None) -> tuple[str, str, str]:
    d = hashlib.md5(diagram_png).hexdigest() if diagram_png else ""
    return (prompt.strip(), latex.strip(), d)

def _pretty_text(s: str) -> str:
    # Basic “powers in plain text” fix for prompts (units mainly).
    return (
        s.replace("cm^2", "cm²")
         .replace("cm^3", "cm³")
         .replace("m^2", "m²")
         .replace("m^3", "m³")
    )


# ---------- UI scale (font size) ----------
def _render_scale_css(scale: float) -> None:
    """Scale question text + maths for readability (iPad-first)."""
    st.markdown(
        f"""
<style>
/* Maths (KaTeX) */
.katex, .katex-display > .katex {{
    color: #000000;
    font-size: {scale:.2f}em !important;
}}

/* Tighten KaTeX vertical margins */
.katex-display {{ margin: 0.12em 0 !important; }}

/* Markdown text (questions, answers, working) */
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li,
div[data-testid="stMarkdownContainer"] strong,
div[data-testid="stMarkdownContainer"] span {{
    font-size: {scale:.2f}rem !important;
    line-height: 1.20 !important;
    margin: 0 !important;
}}

/* Tighten markdown vertical spacing */
div[data-testid="stMarkdownContainer"] p {{ margin: 0 0 0.12rem 0 !important; }}
div[data-testid="stMarkdownContainer"] ul {{ margin: 0 0 0.10rem 1.2rem !important; }}
div[data-testid="stMarkdownContainer"] li {{ margin: 0 0 0.08rem 0 !important; }}

/* Captions + labels */
div[data-testid="stCaptionContainer"],
.stCaption,
label {{
    font-size: {0.85*scale:.2f}rem !important;
}}

/* Re-apply sidebar typography reduction AFTER scale injection */
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2 {{
  font-size: 1.05rem !important;
}}
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4 {{
  font-size: 0.90rem !important;
}}
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] .stCaption {{
  font-size: 0.85rem !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )

def _scale_controls_row(key_prefix: str) -> None:
    """Text-size controls (no tooltips)."""
    _set_default("ui_scale", 3.0)

    c1, c2, c3, _ = st.columns([1, 1, 1, 12], gap="small")
    if c1.button("−", key=f"{key_prefix}__minus", type="secondary"):
        st.session_state.ui_scale = max(0.80, round(float(st.session_state.ui_scale) - 0.20, 2))
        st.rerun()
    if c2.button("+", key=f"{key_prefix}__plus", type="secondary"):
        st.session_state.ui_scale = min(4.00, round(float(st.session_state.ui_scale) + 0.20, 2))
        st.rerun()
    if c3.button("R", key=f"{key_prefix}__reset", type="secondary"):
        st.session_state.ui_scale = 3.0
        st.rerun()


# Apply initial UI scale (default is large; user can reduce)
_set_default("ui_scale", 3.0)
_render_scale_css(float(st.session_state.ui_scale))


# ---------- Floating overlay timer + centre line (JS injection) ----------
def _inject_overlay_timer():
    components.html(
        r"""
<div style="display:none"></div>
<script>
(function () {
  const doc = window.parent.document;
  if (doc.getElementById("mw-floating-timer")) return;

  const style = doc.createElement("style");
  style.id = "mw-floating-timer-style";
  style.textContent = `
    #mw-floating-timer{
      position:fixed;
      top: 3.45rem;
      left:50%;
      transform: translateX(-50%);
      z-index:999999;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      user-select:none;
      -webkit-user-select:none;
      -webkit-touch-callout:none;
    }
    #mw-centerline{
      position:fixed;
      top:0;
      bottom:0;
      left:50%;
      transform: translateX(-50%);
      width:2px;
      background: rgba(0,0,0,0.85);
      z-index: 99998;
      pointer-events:none;
    }
    #mw-timer-display{
      background: rgba(255,255,255,0.92);
      color:#000;
      border: 1px solid rgba(0,0,0,0.25);
      border-radius: 12px;
      padding: 0.55rem 0.85rem;
      font-size: 2.70rem;
      line-height: 1;
      letter-spacing: 0.03em;
      cursor: pointer;
      text-align: center;
      box-shadow: 0 6px 18px rgba(0,0,0,0.14);
    }
    #mw-timer-panel{
      margin-top: 0.45rem;
      background: rgba(255,255,255,0.92);
      border: 1px solid rgba(0,0,0,0.18);
      border-radius: 12px;
      padding: 0.55rem 0.65rem;
      display:none;
      color:#000;
      width: 13.5rem;
      box-shadow: 0 10px 24px rgba(0,0,0,0.16);
    }
    #mw-timer-panel label{
      display:block;
      font-size: 0.82rem;
      opacity: 0.85;
      margin-bottom: 0.12rem;
    }
    #mw-timer-row{
      display:flex;
      gap:0.45rem;
      align-items:center;
      margin-bottom:0.45rem;
    }
    #mw-timer-row input{
      width: 5.9rem;
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 10px;
      color:#000;
      padding: 0.35rem 0.45rem;
      font-size: 0.95rem;
    }
    #mw-timer-btns{
      display:flex;
      gap:0.45rem;
      align-items:center;
      justify-content:space-between;
    }
    #mw-timer-btns button{
      flex: 1 1 auto;
      background: rgba(255,255,255,0.10);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 10px;
      color:#000;
      padding: 0.35rem 0.45rem;
      font-size: 0.92rem;
      cursor:pointer;
    }
    #mw-timer-btns button:active{ transform: translateY(1px); }
    @keyframes mwFlash {
      0% { box-shadow: 0 0 0 rgba(255,0,0,0); filter:none; }
      50% { box-shadow: 0 0 22px rgba(255,0,0,0.65); filter: brightness(1.25); }
      100% { box-shadow: 0 0 0 rgba(255,0,0,0); filter:none; }
    }
    .mw-alarm #mw-timer-display{
      animation: mwFlash 0.55s infinite;
      border-color: rgba(255,0,0,0.55);
    }
  `;
  doc.head.appendChild(style);

  if (!doc.getElementById("mw-centerline")) {
    const line = doc.createElement("div");
    line.id = "mw-centerline";
    doc.body.appendChild(line);
  }

  const root = doc.createElement("div");
  root.id = "mw-floating-timer";
  root.innerHTML = `
    <div id="mw-timer-display" aria-label="Timer">00:30</div>
    <div id="mw-timer-panel" aria-label="Timer controls">
      <div id="mw-timer-row">
        <div style="flex:1 1 auto">
          <label>Minutes</label>
          <input id="mw-min" type="number" min="0" max="999" step="1" inputmode="numeric"/>
        </div>
        <div style="flex:1 1 auto">
          <label>Seconds</label>
          <input id="mw-sec" type="number" min="0" max="59" step="1" inputmode="numeric"/>
        </div>
      </div>
      <div id="mw-timer-btns">
        <button id="mw-start">Start</button>
        <button id="mw-reset">Reset</button>
      </div>
    </div>
  `;
  doc.body.appendChild(root);

  const display = doc.getElementById("mw-timer-display");
  const panel = doc.getElementById("mw-timer-panel");
  const minInput = doc.getElementById("mw-min");
  const secInput = doc.getElementById("mw-sec");
  const startBtn = doc.getElementById("mw-start");
  const resetBtn = doc.getElementById("mw-reset");

  const LS_KEY = "mw_timer_state_v2";
  function loadState(){
    try{
      const s = JSON.parse(window.localStorage.getItem(LS_KEY) || "{}");
      return {
        minutes: Number.isFinite(s.minutes) ? s.minutes : 0,
        seconds: Number.isFinite(s.seconds) ? s.seconds : 30,
      };
    } catch(e){
      return {minutes:0, seconds:30};
    }
  }
  function saveState(minutes, seconds){
    try{ window.localStorage.setItem(LS_KEY, JSON.stringify({minutes, seconds})); } catch(e){}
  }

  let {minutes, seconds} = loadState();
  minutes = Math.max(0, minutes|0);
  seconds = Math.max(0, seconds|0);
  if (seconds > 59) seconds = 59;

  minInput.value = String(minutes);
  secInput.value = String(seconds);

  let durationMs = (minutes*60 + seconds) * 1000;
  if (durationMs <= 0) durationMs = 30*1000;
  let remainingMs = durationMs;

  let running = false;
  let endAt = null;
  let tickHandle = null;

  let audioCtx = null;
  let buzzInterval = null;
  function getCtx(){
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!audioCtx) audioCtx = new AC();
    if (audioCtx.state === "suspended") { try { audioCtx.resume(); } catch(e){} }
    return audioCtx;
  }
  function beep(){
    const ctx = getCtx();
    if (!ctx) return;
    try{
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "square";
      o.frequency.value = 440;
      g.gain.setValueAtTime(0.0001, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.22);
      o.connect(g); g.connect(ctx.destination);
      o.start();
      o.stop(ctx.currentTime + 0.24);
    } catch(e){}
  }
  function startBuzz(){
    if (buzzInterval) return;
    beep();
    buzzInterval = setInterval(beep, 700);
  }
  function stopBuzz(){
    if (buzzInterval){ clearInterval(buzzInterval); buzzInterval = null; }
  }

  function fmt(ms){
    const total = Math.max(0, Math.ceil(ms/1000));
    const mm = Math.floor(total/60);
    const ss = total % 60;
    return String(mm).padStart(2,"0")+":"+String(ss).padStart(2,"0");
  }
  function render(){ display.textContent = fmt(remainingMs); }

  function setAlarm(on){
    if (on) root.classList.add("mw-alarm");
    else root.classList.remove("mw-alarm");
  }

  function stopTimer(){
    running = false;
    endAt = null;
    if (tickHandle) { clearInterval(tickHandle); tickHandle = null; }
    startBtn.textContent = "Start";
  }

  function tick(){
    if (!running) return;
    remainingMs = Math.max(0, endAt - Date.now());
    render();
    if (remainingMs <= 0){
      stopTimer();
      setAlarm(true);
      startBuzz();
    }
  }

  function startTimer(){
    getCtx();
    stopBuzz();
    setAlarm(false);
    if (remainingMs <= 0) remainingMs = durationMs;
    running = true;
    endAt = Date.now() + remainingMs;
    startBtn.textContent = "Pause";
    if (!tickHandle) tickHandle = setInterval(tick, 200);
  }

  function pauseTimer(){
    if (!running) return;
    remainingMs = Math.max(0, endAt - Date.now());
    stopTimer();
    render();
  }

  function applyDurationFromInputs(){
    let m = parseInt(minInput.value || "0", 10);
    let s = parseInt(secInput.value || "0", 10);
    if (!Number.isFinite(m) || m < 0) m = 0;
    if (!Number.isFinite(s) || s < 0) s = 0;
    if (s > 59) s = 59;
    minutes = m; seconds = s;
    minInput.value = String(minutes);
    secInput.value = String(seconds);
    saveState(minutes, seconds);

    durationMs = (minutes*60 + seconds) * 1000;
    if (durationMs <= 0) durationMs = 30*1000;

    remainingMs = durationMs;
    stopBuzz();
    setAlarm(false);
    stopTimer();
    render();
  }

  display.addEventListener("click", function(){
    getCtx();
    panel.style.display = (panel.style.display === "none" || panel.style.display === "") ? "block" : "none";
  });

  minInput.addEventListener("change", function(){ if (!running) applyDurationFromInputs(); });
  secInput.addEventListener("change", function(){ if (!running) applyDurationFromInputs(); });

  startBtn.addEventListener("click", function(){
    getCtx();
    if (running) pauseTimer();
    else startTimer();
  });

  resetBtn.addEventListener("click", function(){
    getCtx();
    applyDurationFromInputs();
  });

  render();
})();
</script>
""",
        height=0,
    )

# Inject timer + centre line on all pages
_inject_overlay_timer()


# ---------------- Instruction line (cycle) ----------------
def _instruction_line(slot: str, align: str = "left"):
    state_key = f"inst_state__{slot}"
    _set_default(state_key, 0)

    cbtn, ctext = st.columns([1, 20], gap="small")
    with cbtn:
        if st.button("●", key=f"inst_btn__{slot}", type="secondary"):
            st.session_state[state_key] = (int(st.session_state[state_key]) + 1) % 4
            st.rerun()

    state = int(st.session_state[state_key])
    if state == 0:
        msg = ""
        color = "#000000"
    elif state == 1:
        msg = "EMPTY HANDS! EYES ON THE BOARD!"
        color = "#FF3B3B"
    elif state == 2:
        msg = "COPY DOWN IN YOUR BOOKS IN PURPLE PEN"
        color = "#B000FF"
    else:
        msg = "DO ON YOUR WHITEBOARDS AND HOVER WHEN READY"
        color = "#2F81F7"

    with ctext:
        safe_msg = msg if msg else "&nbsp;"
        justify = 'flex-end' if align == 'right' else 'flex-start'
        st.markdown(
            f"<div class='inst-line' style='color:{color}; justify-content:{justify}; text-align:{align}; width:100%;'>{safe_msg}</div>",
            unsafe_allow_html=True,
        )



# ---------------- Canvas (embedded question background + height zoom) ----------------

def _pil_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def _latex_to_rgba(latex: str, fontsize: int = 22, dpi: int = 220) -> Image.Image:
    """Render matplotlib mathtext to tight transparent PNG (RGBA)."""
    fig = plt.figure(figsize=(0.01, 0.01), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.text(0, 0.5, f"${latex}$", fontsize=fontsize, va="center", ha="left", color="black")
    fig.canvas.draw()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, transparent=True, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    try:
        return float(draw.textlength(text, font=font))
    except Exception:
        box = draw.textbbox((0, 0), text, font=font)
        return float(box[2] - box[0])


def _wrap_pil_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if _text_width(draw, test, font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


@st.cache_data(show_spinner=False)
def _question_bg_png(
    prompt: str,
    latex: str,
    diagram_png: bytes | None,
    embed_scale: float,
    width_px: int,
    height_px: int,
) -> bytes:
    """
    Build a full-height scratchpad background:
    - question content at the top (prompt + latex + diagram)
    - blank space underneath for working

    Notes:
    - `embed_scale` is intentionally decoupled from the main page `ui_scale` so the
      embedded question doesn't become huge.
    - We auto-shrink to ensure the whole question fits into the top portion of
      the pad, leaving plenty of blank space underneath.
    """
    # How much of the pad height we're willing to use for the question content.
    # The rest stays blank for working.
    CONTENT_MAX = int(height_px * 0.42)

    def _render(scale: float) -> tuple[Image.Image, int]:
        img = Image.new("RGBA", (width_px, height_px), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)

        pad = max(10, int(14 * scale))
        y = pad
        max_text_w = width_px - 2 * pad

        # Prompt (keep footprint similar to the old on-page prompt)
        prompt_font = _pil_font(max(12, int(18 * scale)))
        for line in _wrap_pil_text(draw, _pretty_text(prompt.strip()), prompt_font, max_text_w):
            draw.text((pad, y), line, fill=(0, 0, 0, 255), font=prompt_font)
            y += int(prompt_font.size * 1.18)

        y += int(8 * scale)

        # LaTeX (optional)
        if latex and latex.strip():
            latex_img = _latex_to_rgba(latex.strip(), fontsize=max(14, int(22 * scale)))
            if latex_img.width > max_text_w:
                s = max_text_w / float(latex_img.width)
                new_w = max(1, int(latex_img.width * s))
                new_h = max(1, int(latex_img.height * s))
                latex_img = latex_img.resize((new_w, new_h), Image.LANCZOS)
            img.alpha_composite(latex_img, dest=(pad, y))
            y += latex_img.height + int(10 * scale)

        # Diagram (optional)
        if diagram_png:
            d = Image.open(io.BytesIO(diagram_png)).convert("RGBA")
            # Cap diagram height so it doesn't eat the workspace.
            max_diag_h = int(250 * min(max(scale, 1.0), 1.6))
            s = min(max_text_w / float(d.width), max_diag_h / float(d.height), 1.0)
            new_w = max(1, int(d.width * s))
            new_h = max(1, int(d.height * s))
            d = d.resize((new_w, new_h), Image.LANCZOS)
            img.alpha_composite(d, dest=(pad, y))
            y += d.height + int(8 * scale)

        return img, y

    # Start with the requested scale, then shrink if needed so the whole question
    # fits within the CONTENT_MAX band.
    scale = max(0.65, float(embed_scale))
    for _ in range(4):
        img, used_y = _render(scale)
        if used_y <= CONTENT_MAX:
            break
        # Reduce proportionally (keep a small safety margin)
        scale = max(0.65, scale * (CONTENT_MAX / float(used_y)) * 0.97)

    img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()



def _png_bytes_to_data_url(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"

def _call_st_canvas_compat(*, _bg_img=None, _bg_bytes: bytes | None = None, **base_kwargs):
    """Call st_canvas with a background image across drawable-canvas variants.

    Different package versions use different kwarg names. We try a small set of
    combinations and fall back gracefully.
    """
    variants = []

    if _bg_img is not None:
        variants += [
            {"background_image": _bg_img},
            {"background_image": _bg_img, "background_color": "#FFFFFF"},
            {"background_image": _bg_img, "backgroundColor": "#FFFFFF"},
            {"backgroundImage": _bg_img},
            {"backgroundImage": _bg_img, "background_color": "#FFFFFF"},
            {"backgroundImage": _bg_img, "backgroundColor": "#FFFFFF"},
        ]

    if _bg_bytes is not None:
        try:
            url = _png_bytes_to_data_url(_bg_bytes)
            init = {
                "version": "4.4.0",
                "objects": [
                    {
                        "type": "image",
                        "left": 0,
                        "top": 0,
                        "scaleX": 1,
                        "scaleY": 1,
                        "opacity": 1,
                        "src": url,
                        "crossOrigin": "anonymous",
                        "selectable": False,
                        "evented": False,
                        "hasControls": False,
                        "hasBorders": False,
                        "lockMovementX": True,
                        "lockMovementY": True,
                        "lockScalingX": True,
                        "lockScalingY": True,
                        "lockRotation": True,
                    }
                ],
                "background": "#FFFFFF",
            }
            variants += [
                {"background_image_url": url},
                {"background_image_url": url, "background_color": "#FFFFFF"},
                {"background_image_url": url, "backgroundColor": "#FFFFFF"},
                {"backgroundImageUrl": url},
                {"backgroundImageUrl": url, "background_color": "#FFFFFF"},
                {"backgroundImageUrl": url, "backgroundColor": "#FFFFFF"},
                {"initial_drawing": init},
                {"initialDrawing": init},
            ]
        except Exception:
            pass

    variants += [
        {"background_color": "#FFFFFF"},
        {"backgroundColor": "#FFFFFF"},
        {},  # final attempt with no background args
    ]

    last_type_error: TypeError | None = None
    for extra in variants:
        try:
            return st_canvas(**base_kwargs, **extra)
        except TypeError as e:
            last_type_error = e
            continue

    # If everything failed, raise the last TypeError (most informative).
    if last_type_error:
        raise last_type_error
    return st_canvas(**base_kwargs)

def _render_canvas(slot: str, q) -> None:
    """Per-question scratchpad with embedded question as a fixed background image.

    Uses a lightweight HTML/JS canvas overlay (via components.html) instead of
    streamlit-drawable-canvas background_image, which is unreliable on some
    Streamlit Cloud builds.
    """
    # Default height: +25% from previous tall pad (728 -> 910)
    DEFAULT_H = 1140
    STEP = 360
    MIN_H = 760
    MAX_H = 2200
    CANVAS_W = 700  # keep width consistent

    h_key = f"canvas_h__{slot}"
    if h_key not in st.session_state:
        st.session_state[h_key] = DEFAULT_H

    ver_key = f"canvas_ver__{slot}"
    _set_default(ver_key, 0)

    mode_key = f"ink__{slot}"
    _set_default(mode_key, "black")
    mode = st.session_state[mode_key]

    # Colours (white theme): black/purple/dark-green + eraser removes strokes
    ink_map = {
        "black": "#000000",
        "purple": "#B000FF",
        "green": "#008000",
        "eraser": "#000000",  # colour unused in eraser mode
    }
    stroke_color = ink_map.get(mode, "#000000")
    stroke_width = 12 if mode == "eraser" else 3

    # Controls ABOVE the scratchpad: zoom then ink
    cZm, cZp, cZr, cB, cP, cG, cE, _ = st.columns([1, 1, 1, 1, 1, 1, 1, 8])

    if cZm.button("−", key=f"zhm__{slot}", type="secondary"):
        st.session_state[h_key] = max(MIN_H, int(st.session_state[h_key]) - STEP)
        st.rerun()
    if cZp.button("+", key=f"zhp__{slot}", type="secondary"):
        st.session_state[h_key] = min(MAX_H, int(st.session_state[h_key]) + STEP)
        st.rerun()
    if cZr.button("R", key=f"zhr__{slot}", type="secondary"):
        st.session_state[h_key] = DEFAULT_H
        st.rerun()

    if cB.button("B", key=f"inkB__{slot}", type="secondary"):
        st.session_state[mode_key] = "black"
        st.rerun()
    if cP.button("P", key=f"inkP__{slot}", type="secondary"):
        st.session_state[mode_key] = "purple"
        st.rerun()
    if cG.button("G", key=f"inkG__{slot}", type="secondary"):
        st.session_state[mode_key] = "green"
        st.rerun()
    if cE.button("E", key=f"inkE__{slot}", type="secondary"):
        st.session_state[mode_key] = "black" if st.session_state[mode_key] == "eraser" else "eraser"
        st.rerun()

    ui_scale = float(st.session_state.get("ui_scale", 3.0))
    height_px = int(st.session_state[h_key])

    # Embedded question scale is intentionally smaller than the page ui_scale,
    # so the question doesn't eat the scratchpad workspace.
    embed_scale = max(0.90, min(1.60, ui_scale * 0.55))

    bg_bytes = _question_bg_png(
        prompt=q.prompt,
        latex=q.latex,
        diagram_png=getattr(q, "diagram_png", None),
        embed_scale=embed_scale,
        width_px=CANVAS_W,
        height_px=height_px,
    )
    bg_b64 = base64.b64encode(bg_bytes).decode("ascii")

    # Use a localStorage key that changes when the question changes
    ls_key = f"mw_pad::{slot}::{int(st.session_state[ver_key])}::{getattr(q, 'qid', '')}"

    # HTML scratchpad: background image + transparent drawing canvas overlay.
    # Drawing is stored in localStorage as a PNG dataURL, so reruns/refresh keep the ink.
    html_block = f"""
<div id="{ls_key}" style="width:100%; max-width:{CANVAS_W}px; height:{height_px}px; position:relative; background:#ffffff; border-radius:10px; overflow:hidden;">
  <img id="bg" src="data:image/png;base64,{bg_b64}" style="position:absolute; left:0; top:0; width:100%; height:100%; pointer-events:none; user-select:none;" />
  <canvas id="draw" width="{CANVAS_W}" height="{height_px}" style="position:absolute; left:0; top:0; width:100%; height:100%; touch-action:none;"></canvas>
</div>
<script>
(function(){{
  const KEY = {json.dumps(ls_key)};
  const root = document.getElementById({json.dumps(ls_key)});
  if(!root) return;
  const canvas = root.querySelector('#draw');
  const ctx = canvas.getContext('2d');

  // Restore previous ink layer
  try {{
    const saved = window.localStorage.getItem(KEY);
    if(saved) {{
      const img = new Image();
      img.onload = () => {{ ctx.clearRect(0,0,canvas.width,canvas.height); ctx.drawImage(img,0,0); }};
      img.src = saved;
    }}
  }} catch(e){{}}

  let drawing = false;
  let lastX = 0, lastY = 0;

  function getPos(ev){{
    const rect = canvas.getBoundingClientRect();
    const x = (ev.clientX - rect.left) * (canvas.width / rect.width);
    const y = (ev.clientY - rect.top) * (canvas.height / rect.height);
    return [x,y];
  }}

  function setMode(){{
    const mode = {json.dumps(mode)};
    if(mode === 'eraser'){{
      ctx.globalCompositeOperation = 'destination-out';
      ctx.strokeStyle = 'rgba(0,0,0,1)';
      ctx.lineWidth = {stroke_width};
    }} else {{
      ctx.globalCompositeOperation = 'source-over';
      ctx.strokeStyle = {json.dumps(stroke_color)};
      ctx.lineWidth = {stroke_width};
    }}
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
  }}
  setMode();

  function save(){{
    try {{
      const url = canvas.toDataURL('image/png');
      window.localStorage.setItem(KEY, url);
    }} catch(e){{}}
  }}

  function pointerDown(ev){{
    drawing = true;
    const [x,y] = getPos(ev);
    lastX = x; lastY = y;
    ev.preventDefault();
  }}
  function pointerMove(ev){{
    if(!drawing) return;
    const [x,y] = getPos(ev);
    ctx.beginPath();
    ctx.moveTo(lastX,lastY);
    ctx.lineTo(x,y);
    ctx.stroke();
    lastX = x; lastY = y;
    ev.preventDefault();
  }}
  function pointerUp(ev){{
    if(!drawing) return;
    drawing = false;
    save();
    ev.preventDefault();
  }}

  canvas.addEventListener('pointerdown', pointerDown);
  canvas.addEventListener('pointermove', pointerMove);
  canvas.addEventListener('pointerup', pointerUp);
  canvas.addEventListener('pointercancel', pointerUp);
  canvas.addEventListener('pointerleave', pointerUp);
}})();
</script>
"""
    components.html(html_block, height=height_px + 6)


# ---------------- Practice mode ----------------
def _enter_practice(topic: str, template_id: str, max_difficulty: int):
    st.session_state.mode = "practice"
    st.session_state.practice_ctx = {
        "topic": topic,
        "template_id": template_id,
        "max_difficulty": max_difficulty,
    }
    st.session_state.practice_seed = random.randint(1, 10**9)
    st.session_state.practice_questions = None
    for k in list(st.session_state.keys()):
        if k.startswith("prac_ans__"):
            del st.session_state[k]
    st.rerun()


def _render_practice_mode():
    ctx = st.session_state.get("practice_ctx")
    if not ctx:
        st.session_state.mode = "main"
        st.rerun()

    topic = ctx["topic"]
    template_id = ctx["template_id"]
    max_difficulty = int(ctx["max_difficulty"])

    st.markdown("<div style='height: 1.6rem'></div>", unsafe_allow_html=True)

    top = st.columns([1, 1, 8])
    if top[0].button("←", key="back_main", type="secondary"):
        st.session_state.mode = "main"
        st.rerun()

    if top[1].button("N", key="regen_practice", type="secondary"):
        st.session_state.practice_seed = random.randint(1, 10**9)
        st.session_state.practice_questions = None
        for k in list(st.session_state.keys()):
            if k.startswith("prac_ans__"):
                del st.session_state[k]
        st.rerun()

    # Text size controls
    _scale_controls_row("practice_top")

    st.markdown(f"<div class='topic-title'>{topic}</div>", unsafe_allow_html=True)

    if st.session_state.get("practice_questions") is None:
        qs = generate_questions_by_template(topic=topic, template_id=template_id, max_difficulty=max_difficulty, n=10, seed=int(st.session_state.practice_seed))
        st.session_state.practice_questions = qs
    else:
        qs = st.session_state.practice_questions

    for row in range(5):
        left_idx = 2 * row
        right_idx = 2 * row + 1
        colL, colR = st.columns(2, gap="medium")

        for target_col, i in [(colL, left_idx), (colR, right_idx)]:
            with target_col:
                q = qs[i]
                prompt_txt = html.escape(_pretty_text(q.prompt))
                st.markdown(f"<p><span class='prac-num'>{i+1}.</span> <strong>{prompt_txt}</strong></p>", unsafe_allow_html=True)
                if q.latex.strip():
                    st.latex(q.latex)
                if getattr(q, "diagram_png", None):
                    st.image(q.diagram_png, use_column_width=True)

                ans_key = f"prac_ans__{i}"
                _set_default(ans_key, False)

                cN, cA, cAns = st.columns([1, 1, 10])

                if cN.button("N", key=f"pracN_btn__{i}", type="secondary"):
                    new_seed = random.randint(1, 10**9)
                    # Avoid re-generating identical to itself (rare)
                    qs[i] = regenerate_question(topic=topic, template_id=q.template_id, max_difficulty=max_difficulty, new_seed=new_seed)
                    st.session_state.practice_questions = qs
                    st.session_state[ans_key] = False
                    st.rerun()

                if cA.button("A", key=f"pracA_btn__{i}", type="secondary"):
                    st.session_state[ans_key] = not st.session_state[ans_key]
                    st.rerun()

                if st.session_state[ans_key]:
                    cAns.latex(rf"\color{{#008000}}{{{qs[i].answer_latex}}}")
                else:
                    cAns.markdown("&nbsp;", unsafe_allow_html=True)

        st.markdown("<div style='height: 0.35rem'></div>", unsafe_allow_html=True)


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Settings")

    _all_topics = available_topics()
    _all_strands = available_strands()

    # Load presets (persisted in URL) once
    if "saved_presets" not in st.session_state:
        st.session_state["saved_presets"] = _load_presets_from_query_params()

    def _set_topics(new_list: list[str]):
        # keep ordering consistent with available_topics()
        new_list = [t for t in new_list if t in _all_topics]
        st.session_state["topics_select"] = sorted(new_list, key=lambda x: _all_topics.index(x))

    if "topics_select" not in st.session_state:
        # Try to restore from URL first (survives refresh).
        loaded = _load_selection_from_query_params(_all_topics, _all_strands)
        if not loaded:
            _set_topics([t for t in DEFAULT_TOPICS if t in _all_topics])

    # ---- Presets (save/load/delete) ----
    st.subheader("Presets")
    presets: dict = st.session_state.get("saved_presets", {}) or {}
    preset_names = ["(none)"] + sorted([k for k in presets.keys() if isinstance(k, str)], key=str.lower)
    # Apply any pending preset UI changes BEFORE widgets are created (avoids StreamlitAPIException)
    pending_pick = st.session_state.pop("preset_pick_pending", None)
    if pending_pick is not None:
        st.session_state["preset_pick"] = pending_pick if pending_pick in preset_names else "(none)"
    if st.session_state.pop("preset_name_pending_clear", False):
        st.session_state["preset_name"] = ""
    preset_pick = st.selectbox("Preset", options=preset_names, key="preset_pick")
    preset_name = st.text_input("Name", key="preset_name", placeholder="e.g. Y9 Algebra")

    p1, p2, p3 = st.columns(3)
    if p1.button("Save", use_container_width=True):
        name = (preset_name or "").strip() or (preset_pick if preset_pick != "(none)" else "")
        if name:
            cur_topics = list(st.session_state.get("topics_select", []))
            cur_strand = str(st.session_state.get("strand_select", "All"))
            cur_md = int(st.session_state.get("max_diff", 5))
            cur_levels = {t: st.session_state.get(f"level__{_safe_topic_key(t)}", "") for t in cur_topics}
            presets[name] = {"topics": cur_topics, "strand": cur_strand, "max_diff": cur_md, "levels": cur_levels}
            st.session_state["saved_presets"] = presets
            _save_presets_to_query_params(presets)
            st.session_state["preset_pick_pending"] = name
            st.session_state["preset_name_pending_clear"] = True
            st.rerun()

    if p2.button("Load", use_container_width=True):
        if preset_pick in presets:
            data = presets[preset_pick]
            # Apply the preset to current session state
            try:
                topics = data.get("topics", []) if isinstance(data, dict) else []
                if not isinstance(topics, list):
                    topics = []
                topics = [t for t in topics if isinstance(t, str) and t in _all_topics]
                _set_topics(topics)

                strand2 = data.get("strand") if isinstance(data, dict) else None
                if isinstance(strand2, str) and strand2 in _all_strands:
                    st.session_state["strand_select"] = strand2

                md2 = data.get("max_diff") if isinstance(data, dict) else None
                if isinstance(md2, int) and 1 <= md2 <= 5:
                    st.session_state["max_diff"] = md2

                levels2 = data.get("levels", {}) if isinstance(data, dict) else {}
                if isinstance(levels2, dict):
                    for t, lvl in levels2.items():
                        if isinstance(t, str) and t in _all_topics and isinstance(lvl, str) and lvl:
                            st.session_state[f"level__{_safe_topic_key(t)}"] = lvl
            except Exception:
                pass
            st.rerun()

    if p3.button("Delete", use_container_width=True):
        if preset_pick in presets:
            presets.pop(preset_pick, None)
            st.session_state["saved_presets"] = presets
            _save_presets_to_query_params(presets)
            st.session_state["preset_pick_pending"] = "(none)"
            st.rerun()

    st.divider()

    # Strand-first browsing (scales as the topic bank grows)
    if "strand_select" not in st.session_state:
        st.session_state["strand_select"] = "Algebra" if "Algebra" in _all_strands else (_all_strands[0] if _all_strands else "All")

    strand = st.selectbox("Strand", options=_all_strands, key="strand_select")

    # Selection actions
    a, b, c = st.columns(3)
    if a.button("Defaults", use_container_width=True):
        _set_topics([t for t in DEFAULT_TOPICS if t in _all_topics])
        st.rerun()
    if b.button("All", use_container_width=True):
        _set_topics(list(_all_topics))
        st.rerun()
    if c.button("Clear", use_container_width=True):
        _set_topics([])
        st.rerun()

    # Only show topics from the selected strand, but always include already-selected topics
    # so the selection never disappears when switching strands.
    strand_topics = topics_in_strand(strand)
    cur_sel = list(st.session_state.get("topics_select", []))
    allowed = set(strand_topics) | set(cur_sel)
    topic_options = [t for t in _all_topics if t in allowed]

    # Optional quick filter (useful once the bank grows)
    topic_search = st.text_input("Search", key="topic_search", placeholder="Type to filter topics")
    if topic_search and topic_search.strip():
        s = topic_search.strip().lower()
        topic_options = [t for t in topic_options if (s in t.lower()) or (t in cur_sel)]

    topics = st.multiselect("Topics", options=topic_options, key="topics_select")
    st.caption("Type to search. Switch Strand to filter the list.")

    if "max_diff" not in st.session_state:
        st.session_state["max_diff"] = 5

    max_diff = st.slider("Max difficulty", 1, 5, value=int(st.session_state.get("max_diff", 5)), key="max_diff")

    st.subheader("Levels")
    topics_levels: dict[str, str] = {}
    for _t in topics:
        opts = available_levels(_t, max_difficulty=max_diff)
        if not opts:
            continue
        safe = _safe_topic_key(_t)
        key = f"level__{safe}"
        ids = [x[0] for x in opts]
        names = {x[0]: x[1] for x in opts}
        if key not in st.session_state or st.session_state[key] not in ids:
            st.session_state[key] = ids[0]
        topics_levels[_t] = st.selectbox(
            f"{_t}",
            options=ids,
            format_func=lambda k: names.get(k, k),
            key=key,
        )

    st.session_state.topics_levels = topics_levels
    _save_selection_to_query_params(topics=topics, strand=strand, max_diff=int(max_diff), topics_levels=topics_levels, all_topics=_all_topics)


    if "master_seed" not in st.session_state:
        st.session_state.master_seed = random.randint(1, 10**9)

    colA, colB = st.columns(2)
    with colA:
        if st.button("Regenerate ALL", type="primary"):
            st.session_state.master_seed = random.randint(1, 10**9)
            st.session_state.generated = None
            st.session_state.pair_params_map = None
            st.session_state.level_name_map = None
            st.session_state.pdf_cache = None
            st.session_state.pdf_fp = None
    with colB:
        st.number_input("Master seed", min_value=1, max_value=10**9, value=int(st.session_state.master_seed))

    with st.expander("Diagnostics", expanded=False):
        st.caption(f"Build: {BUILD_ID}")
        st.write(_all_topics)


# ---------------- App modes ----------------
if "mode" not in st.session_state:
    st.session_state.mode = "main"

if st.session_state.mode == "practice":
    _render_practice_mode()
    st.stop()


# ---------------- Main page ----------------
topics_levels = st.session_state.get("topics_levels", {})
if not topics_levels:
    st.warning("Pick at least one topic in the sidebar.")
    st.stop()

# Text size controls
_scale_controls_row("main_top")
_render_scale_css(float(st.session_state.ui_scale))

seed = int(st.session_state.master_seed)

# If topic/level settings changed, regenerate
settings_fp = hashlib.sha1(repr((seed, int(max_diff), tuple(sorted(topics_levels.items())))).encode()).hexdigest()
if st.session_state.get("settings_fp") != settings_fp:
    st.session_state.settings_fp = settings_fp
    st.session_state.generated = None
    st.session_state.pair_params_map = None
    st.session_state.level_name_map = None
    st.session_state.pdf_cache = None
    st.session_state.pdf_fp = None

if "generated" not in st.session_state or st.session_state.generated is None:
    with st.status("Generating questions…", expanded=False) as status:
        grouped, pair_params_map, level_name_map = generate_two_per_topic(topics_levels=topics_levels, max_difficulty=int(max_diff), seed=seed)
        status.update(label="Questions generated", state="complete")
    st.session_state.generated = grouped
    st.session_state.pair_params_map = pair_params_map
    st.session_state.level_name_map = level_name_map
    st.session_state.pdf_cache = None
    st.session_state.pdf_fp = None

grouped = st.session_state.generated
level_name_map = st.session_state.get("level_name_map") or {}
ordered_topics = [t for t in topics_levels.keys() if t in grouped]

# spacing before first topic
st.markdown("<div style='height: 1.4rem'></div>", unsafe_allow_html=True)

GAP_VH = 72

def _regen_one(topic: str, idx: int, max_diff: int) -> None:
    """Regenerate ONE question and avoid duplicating the other question in the pair."""
    g = st.session_state.generated
    other = g[topic][1 - idx]
    other_sig = _q_sig(other.prompt, other.latex, other.diagram_png)

    for _ in range(60):
        cand = regenerate_question(topic=topic, template_id=g[topic][idx].template_id, max_difficulty=int(max_diff), new_seed=random.randint(1, 10**9))
        cand_sig = _q_sig(cand.prompt, cand.latex, cand.diagram_png)
        if cand_sig != other_sig:
            g[topic][idx] = cand
            break

    st.session_state.generated = g
    st.session_state.pdf_cache = None
    st.session_state.pdf_fp = None

for topic in ordered_topics:
    qs = grouped.get(topic, [])
    if len(qs) < 2:
        st.info(f"{topic}: not enough templates found at the selected difficulty.")
        continue

    safe_topic = _safe_topic_key(topic)
    level_opts = available_levels(topic, max_difficulty=int(max_diff))
    ids = [x[0] for x in level_opts]
    names = {x[0]: x[1] for x in level_opts}

    cur_level_id = st.session_state.topics_levels.get(topic, ids[0] if ids else "")
    cur_level_name = names.get(cur_level_id, level_name_map.get(topic, "")) if ids else level_name_map.get(topic, "")

    h1, h2, h3 = st.columns([8, 1, 1])
    h1.markdown(f"<div class='topic-title'>{topic}{(' — ' + cur_level_name) if cur_level_name else ''}</div>", unsafe_allow_html=True)

    if ids and len(ids) > 1:
        h2.button("−", key=f"lvlm__{safe_topic}", type="secondary", on_click=_shift_level, args=(topic, -1, ids, safe_topic))
        h3.button("+", key=f"lvlp__{safe_topic}", type="secondary", on_click=_shift_level, args=(topic, +1, ids, safe_topic))

    show2_key = f"show2__{_slot(topic, 1)}"
    _set_default(show2_key, False)

    c1, c2 = st.columns(2, gap="large")

    # Q1
    slot1 = _slot(topic, 0)
    ans1_key = f"ans__{slot1}"
    work1_key = f"work__{slot1}"
    draw1_key = f"draw__{slot1}"
    _set_default(ans1_key, False)
    _set_default(work1_key, False)
    # Default: scratchpad open
    _set_default(draw1_key, True)

    with c1:
            q1 = grouped[topic][0]
            _instruction_line(slot1, align="left")

            # Action buttons (always above the scratchpad / answer / working).
            # If the scratchpad is showing, put D first on the row.
            if bool(st.session_state.get(draw1_key, False)):
                cD, cN, cA, cW, cI = st.columns(5)
            else:
                cN, cA, cW, cD, cI = st.columns(5)

            if cN.button("N", key=f"n__{slot1}", type="secondary"):
                _regen_one(topic, 0, int(max_diff))
                st.session_state[ans1_key] = False
                st.session_state[work1_key] = False
                st.session_state[draw1_key] = True
                st.session_state[f"ink__{slot1}"] = "black"
                st.session_state[f"canvas_ver__{slot1}"] = int(st.session_state.get(f"canvas_ver__{slot1}", 0)) + 1
                st.session_state[f"canvas_h__{slot1}"] = 910
                st.rerun()

            if cA.button("A", key=f"a__{slot1}", type="secondary"):
                _toggle(ans1_key, default=False)
                st.session_state.pdf_cache = None
                st.rerun()

            if cW.button("W", key=f"w__{slot1}", type="secondary"):
                _toggle(work1_key, default=False)
                st.rerun()

            if cD.button("D", key=f"d__{slot1}", type="secondary"):
                _toggle(draw1_key, default=False)
                st.rerun()

            if cI.button("I", key=f"i__{slot1}", type="secondary"):
                _enter_practice(topic=topic, template_id=q1.template_id, max_difficulty=int(max_diff))

            # Main view: question embedded into scratchpad (default), or shown normally if scratchpad is hidden
            if st.session_state.get(draw1_key, False):
                _render_canvas(slot1, q1)
            else:
                st.markdown(f"**{_pretty_text(q1.prompt)}**")
                if q1.latex.strip():
                    st.latex(q1.latex)
                if getattr(q1, "diagram_png", None):
                    st.image(q1.diagram_png, use_column_width=True)

            if st.session_state[ans1_key]:
                st.markdown("**Answer:**")
                st.latex(q1.answer_latex)

            if st.session_state[work1_key]:
                st.markdown("**Working:**")
                for kind, content in q1.working:
                    if kind == "text":
                        st.markdown(f"- {content}")
                    else:
                        st.latex(content)


    # Q2
    slot2 = _slot(topic, 1)
    ans2_key = f"ans__{slot2}"
    work2_key = f"work__{slot2}"
    draw2_key = f"draw__{slot2}"
    _set_default(ans2_key, False)
    _set_default(work2_key, False)
    # Default: scratchpad open
    _set_default(draw2_key, True)

    with c2:
            q2 = grouped[topic][1]
            _instruction_line(slot2, align="right")

            if not st.session_state.get(show2_key, False):
                st.markdown("&nbsp;", unsafe_allow_html=True)
                ctrl = st.columns([1, 1, 1, 1, 1, 1])
                if ctrl[5].button("H", key=f"h__{slot2}", type="secondary"):
                    st.session_state[show2_key] = True
                    st.rerun()
            else:
                # Action buttons (always above the scratchpad / answer / working).
                # If the scratchpad is showing, put D first on the row.
                if bool(st.session_state.get(draw2_key, False)):
                    cD, cN, cA, cW, cI, cH = st.columns(6)
                else:
                    cN, cA, cW, cD, cI, cH = st.columns(6)

                if cN.button("N", key=f"n__{slot2}", type="secondary"):
                    _regen_one(topic, 1, int(max_diff))
                    st.session_state[ans2_key] = False
                    st.session_state[work2_key] = False
                    st.session_state[draw2_key] = True
                    st.session_state[f"ink__{slot2}"] = "black"
                    st.session_state[f"canvas_ver__{slot2}"] = int(st.session_state.get(f"canvas_ver__{slot2}", 0)) + 1
                    st.session_state[f"canvas_h__{slot2}"] = 910
                    st.rerun()

                if cA.button("A", key=f"a__{slot2}", type="secondary"):
                    _toggle(ans2_key, default=False)
                    st.rerun()

                if cW.button("W", key=f"w__{slot2}", type="secondary"):
                    _toggle(work2_key, default=False)
                    st.rerun()

                if cD.button("D", key=f"d__{slot2}", type="secondary"):
                    _toggle(draw2_key, default=False)
                    st.rerun()

                if cI.button("I", key=f"i__{slot2}", type="secondary"):
                    _enter_practice(topic=topic, template_id=q2.template_id, max_difficulty=int(max_diff))

                if cH.button("H", key=f"h__{slot2}", type="secondary"):
                    st.session_state[show2_key] = not st.session_state.get(show2_key, False)
                    st.rerun()

                # Main view: question embedded into scratchpad (default), or shown normally if scratchpad is hidden
                if st.session_state.get(draw2_key, False):
                    _render_canvas(slot2, q2)
                else:
                    st.markdown(f"**{_pretty_text(q2.prompt)}**")
                    if q2.latex.strip():
                        st.latex(q2.latex)
                    if getattr(q2, "diagram_png", None):
                        st.image(q2.diagram_png, use_column_width=True)

                if st.session_state[ans2_key]:
                    st.markdown("**Answer:**")
                    st.latex(q2.answer_latex)

                if st.session_state[work2_key]:
                    st.markdown("**Working:**")
                    for kind, content in q2.working:
                        if kind == "text":
                            st.markdown(f"- {content}")
                        else:
                            st.latex(content)


    st.markdown(f"<div style='height: {GAP_VH}vh'></div>", unsafe_allow_html=True)


# ---------------- PDF export (cached) ----------------
if ordered_topics:
    pdf_title = "Mixed topics" if len(ordered_topics) > 1 else ordered_topics[0]

    fp_parts = []
    for t in ordered_topics:
        for q in grouped[t][:2]:
            fp_parts.append(f"{t}|{q.template_id}|{q.prompt}|{q.latex}|{q.answer_latex}")
    fp_raw = "||".join(fp_parts).encode("utf-8")
    fp = hashlib.md5(fp_raw).hexdigest()

    if st.session_state.get("pdf_fp") != fp or st.session_state.get("pdf_cache") is None:
        with st.status("Building PDF…", expanded=False) as status:
            titled_grouped = {
                (f"{t} — {level_name_map.get(t, '')}" if level_name_map.get(t, '') else t): grouped[t]
                for t in ordered_topics
            }
            st.session_state.pdf_cache = build_pdf_bytes(title=pdf_title, grouped=titled_grouped, seed=seed)
            st.session_state.pdf_fp = fp
            status.update(label="PDF ready", state="complete")

    st.download_button(
        label="Download PDF (Questions + Answers)",
        data=st.session_state.pdf_cache,
        file_name="worksheet.pdf",
        mime="application/pdf",
        type="primary",
    )