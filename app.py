from __future__ import annotations

import hashlib
import random

import streamlit as st
import streamlit.components.v1 as components

from question_bank import (
    available_levels,
    available_topics,
    generate_questions_by_template,
    generate_two_per_topic,
    get_template,
    regenerate_question,
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

BUILD_ID = "v39.3-practice-spacing-no-tooltips"
print(f"BUILD={BUILD_ID}")
try:
    print("AVAILABLE_TOPICS=", available_topics())
except Exception as _e:
    print("TOPIC_LOAD_ERROR", _e)


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
</style>
""",
        unsafe_allow_html=True,
    )


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
      top:6.55rem;
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
      background: rgba(255,255,255,0.85);
      z-index: 99998;
      pointer-events:none;
    }
    #mw-timer-display{
      background: rgba(0,0,0,0.92);
      color:#fff;
      border: 1px solid rgba(255,255,255,0.25);
      border-radius: 12px;
      padding: 0.55rem 0.85rem;
      font-size: 2.70rem;
      line-height: 1;
      letter-spacing: 0.03em;
      cursor: pointer;
      text-align: center;
      box-shadow: 0 6px 18px rgba(0,0,0,0.28);
    }
    #mw-timer-panel{
      margin-top: 0.45rem;
      background: rgba(0,0,0,0.92);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 12px;
      padding: 0.55rem 0.65rem;
      display:none;
      color:#fff;
      width: 13.5rem;
      box-shadow: 0 10px 24px rgba(0,0,0,0.30);
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
      color:#fff;
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
      color:#fff;
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
def _instruction_line(slot: str):
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
        color = "#FFFFFF"
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
        st.markdown(f"<div class='inst-line' style='color:{color};'>{safe_msg}</div>", unsafe_allow_html=True)


# ---------------- Canvas ----------------
def _render_canvas(slot: str):
    if not _CANVAS_OK:
        st.warning("Drawing component not available. Ensure 'streamlit-drawable-canvas' is installed.")
        return

    mode_key = f"ink__{slot}"
    _set_default(mode_key, "white")
    mode = st.session_state[mode_key]

    ink_map = {
        "white": "#FFFFFF",
        "purple": "#B000FF",
        "green": "#00FF00",
        "eraser": "#000000",
    }
    stroke_color = ink_map.get(mode, "#FFFFFF")
    stroke_width = 12 if mode == "eraser" else 3

    st_canvas(
        fill_color="rgba(255, 255, 255, 0)",
        stroke_width=stroke_width,
        stroke_color=stroke_color,
        background_color="#000000",
        height=416,
        drawing_mode="freedraw",
        key=f"canvas__{slot}",
    )

    cW, cP, cG, cE, _ = st.columns([1, 1, 1, 1, 8])
    if cW.button("W", key=f"inkW__{slot}", type="secondary"):
        st.session_state[mode_key] = "white"
        st.rerun()
    if cP.button("P", key=f"inkP__{slot}", type="secondary"):
        st.session_state[mode_key] = "purple"
        st.rerun()
    if cG.button("G", key=f"inkG__{slot}", type="secondary"):
        st.session_state[mode_key] = "green"
        st.rerun()
    if cE.button("E", key=f"inkE__{slot}", type="secondary"):
        st.session_state[mode_key] = "white" if st.session_state[mode_key] == "eraser" else "eraser"
        st.rerun()


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
                st.markdown(f"**{i+1}. {_pretty_text(q.prompt)}**")
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
                    cAns.latex(rf"\color{{#00ff00}}{{{qs[i].answer_latex}}}")
                else:
                    cAns.markdown("&nbsp;", unsafe_allow_html=True)

        st.markdown("<div style='height: 0.35rem'></div>", unsafe_allow_html=True)


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Settings")

    _all_topics = available_topics()

    def _set_topics(new_list: list[str]):
        # keep ordering consistent with available_topics()
        new_list = [t for t in new_list if t in _all_topics]
        st.session_state["topics_select"] = sorted(new_list, key=lambda x: _all_topics.index(x))

    if "topics_select" not in st.session_state:
        _set_topics([t for t in DEFAULT_TOPICS if t in _all_topics])

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

    topics = st.multiselect("Topics", options=_all_topics, key="topics_select")
    st.caption("Tip: tap Topics and type to search (e.g. Area, Perimeter, Polygon).")

    max_diff = st.slider("Max difficulty", 1, 5, 5)

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
    for k in (ans1_key, work1_key, draw1_key):
        _set_default(k, False)

    with c1:
        q1 = grouped[topic][0]
        _instruction_line(slot1)

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

        if st.session_state[draw1_key]:
            _render_canvas(slot1)

        ctrl = st.columns(5)
        if ctrl[0].button("N", key=f"n__{slot1}", type="secondary"):
            _regen_one(topic, 0, int(max_diff))
            st.session_state[ans1_key] = False
            st.session_state[work1_key] = False
            st.session_state[draw1_key] = False
            st.session_state[f"ink__{slot1}"] = "white"
            st.rerun()

        if ctrl[1].button("A", key=f"a__{slot1}", type="secondary"):
            _toggle(ans1_key, default=False)
            st.session_state.pdf_cache = None
            st.rerun()

        if ctrl[2].button("W", key=f"w__{slot1}", type="secondary"):
            _toggle(work1_key, default=False)
            st.rerun()

        if ctrl[3].button("D", key=f"d__{slot1}", type="secondary"):
            _toggle(draw1_key, default=False)
            st.rerun()

        if ctrl[4].button("I", key=f"i__{slot1}", type="secondary"):
            _enter_practice(topic=topic, template_id=q1.template_id, max_difficulty=int(max_diff))

    # Q2
    slot2 = _slot(topic, 1)
    ans2_key = f"ans__{slot2}"
    work2_key = f"work__{slot2}"
    draw2_key = f"draw__{slot2}"
    for k in (ans2_key, work2_key, draw2_key):
        _set_default(k, False)

    with c2:
        q2 = grouped[topic][1]
        _instruction_line(slot2)

        if not st.session_state.get(show2_key, False):
            st.markdown("&nbsp;", unsafe_allow_html=True)
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

            if st.session_state[draw2_key]:
                _render_canvas(slot2)

        if st.session_state.get(show2_key, False):
            ctrl = st.columns(6)
            if ctrl[0].button("N", key=f"n__{slot2}", type="secondary"):
                _regen_one(topic, 1, int(max_diff))
                st.session_state[ans2_key] = False
                st.session_state[work2_key] = False
                st.session_state[draw2_key] = False
                st.session_state[f"ink__{slot2}"] = "white"
                st.rerun()

            if ctrl[1].button("A", key=f"a__{slot2}", type="secondary"):
                _toggle(ans2_key, default=False)
                st.rerun()

            if ctrl[2].button("W", key=f"w__{slot2}", type="secondary"):
                _toggle(work2_key, default=False)
                st.rerun()

            if ctrl[3].button("D", key=f"d__{slot2}", type="secondary"):
                _toggle(draw2_key, default=False)
                st.rerun()

            if ctrl[4].button("I", key=f"i__{slot2}", type="secondary"):
                _enter_practice(topic=topic, template_id=q2.template_id, max_difficulty=int(max_diff))

            if ctrl[5].button("H", key=f"h__{slot2}", type="secondary"):
                st.session_state[show2_key] = not st.session_state.get(show2_key, False)
                st.rerun()
        else:
            ctrl = st.columns([1, 1, 1, 1, 1, 1])
            if ctrl[5].button("H", key=f"h__{slot2}", type="secondary"):
                st.session_state[show2_key] = True
                st.rerun()

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
