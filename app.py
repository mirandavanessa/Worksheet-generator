import random
import time
import hashlib
import streamlit as st
import streamlit.components.v1 as components

from question_bank import (
    available_topics,
    generate_two_per_topic,
    regenerate_question,
    generate_questions_by_template,
)
from pdf_export import build_pdf_bytes

# Optional drawing canvas (per-question)
try:
    from streamlit_drawable_canvas import st_canvas
    _CANVAS_OK = True
except Exception:
    st_canvas = None
    _CANVAS_OK = False

# Optional auto-refresh for floating timer
try:
    from streamlit_autorefresh import st_autorefresh
    _AUTOREFRESH_OK = True
except Exception:
    st_autorefresh = None
    _AUTOREFRESH_OK = False

st.set_page_config(page_title="Maths Worksheet Generator", layout="wide")

# ---------- CSS: minimal distraction controls + instruction cycle + floating timer ----------
st.markdown(
    """
<style>
/* Increase top padding so top controls are not hidden by Streamlit header */
.block-container { padding-top: 3.8rem; }

/* Shrink SECONDARY buttons (used for per-question micro-controls) */
button[kind="secondary"] {
    padding: 0.00rem 0.14rem !important;
    font-size: 0.52rem !important;
    line-height: 1 !important;
    height: 0.92rem !important;
    min-height: 0.92rem !important;
    min-width: 1.05rem !important;
}

/* Keep the download button clearly visible */
div[data-testid="stDownloadButton"] button {
    background: rgba(0,0,0,0.92) !important;
    color: #FFFFFF !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
}

/* Keep the sidebar primary action (Regenerate ALL) clearly visible */
div[data-testid="stSidebar"] button[kind="primary"] {
    background: rgba(0,0,0,0.92) !important;
    color: #FFFFFF !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
}

/* Reduce excess spacing inside columns */
div[data-testid="column"] > div { gap: 0.35rem; }

/* Instruction line text (large) */
.inst-line {
    min-height: 2.0rem;
    display: flex;
    align-items: center;
    font-weight: 800;
    letter-spacing: 0.03em;
    font-size: 1.56rem; /* ~2x previous */
    margin: 0.10rem 0 0.10rem 0;
}

/* Make ONLY the instruction-cycle button a small black circle */
button[title="Instruction cycle"],
button[aria-label="Instruction cycle"],
button[title="Cycle instruction"],
button[aria-label="Cycle instruction"] {
    border-radius: 999px !important;
    background: rgba(0,0,0,0.92) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    min-width: 0.92rem !important;
    width: 0.92rem !important;
    padding: 0 !important;
}
button[title="Instruction cycle"] span,
button[aria-label="Instruction cycle"] span,
button[title="Cycle instruction"] span,
button[aria-label="Cycle instruction"] span {
    font-size: 0.60rem !important;
    line-height: 1 !important;
}

/* Floating timer (fixed top-right) */
.floating-timer {
    position: fixed;
    top: 4.15rem; /* below Streamlit header */
    right: 1.00rem;
    z-index: 10000;
    background: rgba(0,0,0,0.92);
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 10px;
    padding: 0.55rem 0.85rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size: 2.55rem;
}

@keyframes mw_flash {
  0%, 49% {
    background: rgba(220, 30, 30, 0.95);
    border-color: rgba(255, 80, 80, 0.90);
    box-shadow: 0 0 18px rgba(255, 80, 80, 0.55);
  }
  50%, 100% {
    background: rgba(0,0,0,0.92);
    border-color: rgba(255,255,255,0.25);
    box-shadow: none;
  }
}

.floating-timer.alarm {
  animation: mw_flash 0.6s infinite;
}
</style>
""",
    unsafe_allow_html=True,
)

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
]


def _slot(topic: str, idx: int) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in topic)
    return f"{safe}__{idx}"


def _toggle(key: str, default: bool = False):
    st.session_state[key] = not st.session_state.get(key, default)


def _set_default(key: str, default):
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------- Floating timer (countdown) ----------------
def _init_countdown_timer_defaults():
    _set_default("timer_minutes", 2)
    _set_default("timer_duration_sec", int(st.session_state.timer_minutes) * 60)
    _set_default("timer_running", False)
    _set_default("timer_start_ts", time.time())
    _set_default("timer_elapsed_before", 0.0)
    _set_default("timer_alarm", False)
    _set_default("timer_audio_unlocked", False)


def _timer_elapsed_total() -> float:
    elapsed = float(st.session_state.timer_elapsed_before)
    if bool(st.session_state.timer_running):
        elapsed += (time.time() - float(st.session_state.timer_start_ts))
    return elapsed


def _timer_remaining_sec() -> int:
    duration = int(st.session_state.timer_duration_sec)
    remaining = duration - int(_timer_elapsed_total())
    return max(0, remaining)


def _render_floating_timer():
    _init_countdown_timer_defaults()

    # Auto-refresh only while running
    if bool(st.session_state.timer_running) and _AUTOREFRESH_OK:
        st_autorefresh(interval=1000, key="__timer_refresh__")

    remaining = _timer_remaining_sec()

    # Stop automatically when it hits 0
    if remaining == 0 and bool(st.session_state.timer_running):
        st.session_state.timer_running = False
        st.session_state.timer_elapsed_before = float(st.session_state.timer_duration_sec)

    # Alarm becomes active once we actually reach 0
    if remaining == 0 and (float(st.session_state.timer_elapsed_before) >= float(st.session_state.timer_duration_sec)):
        st.session_state.timer_alarm = True
    else:
        st.session_state.timer_alarm = False

    mm = remaining // 60
    ss = remaining % 60

    cls = "floating-timer alarm" if bool(st.session_state.timer_alarm) else "floating-timer"
    st.markdown(f"<div class='{cls}'>{mm:02d}:{ss:02d}</div>", unsafe_allow_html=True)

    # Best-effort buzzer at 0 (requires audio to be unlocked by a user gesture on many iOS devices)
    if bool(st.session_state.timer_audio_unlocked):
        alarm_flag = "true" if bool(st.session_state.timer_alarm) else "false"
        components.html(
            f"""
<div style='display:none'></div>
<script>
(function() {{
  window.__mwAudio = window.__mwAudio || {{}};
  function getCtx() {{
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!window.__mwAudio.ctx) window.__mwAudio.ctx = new AC();
    const ctx = window.__mwAudio.ctx;
    if (ctx.state === 'suspended') {{ try {{ ctx.resume(); }} catch(e) {{}} }}
    return ctx;
  }}

  // Try to unlock audio context once (best-effort). Many iOS devices require a user gesture.
  (function unlockOnce() {{
    if (window.__mwAudio.unlocked) return;
    const ctx = getCtx();
    if (!ctx) return;
    try {{
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      g.gain.value = 0.001;
      o.connect(g); g.connect(ctx.destination);
      o.start();
      o.stop(ctx.currentTime + 0.01);
      window.__mwAudio.unlocked = true;
    }} catch(e) {{}}
  }})();

  function beep() {{
    const ctx = getCtx();
    if (!ctx) return;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = 'square';
    o.frequency.value = 440;
    g.gain.setValueAtTime(0.0001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.22, ctx.currentTime + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
    o.connect(g); g.connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + 0.26);
  }}

  function startBuzz() {{
    if (window.__mwAudio.buzzInterval) return;
    beep();
    window.__mwAudio.buzzInterval = setInterval(beep, 700);
  }}

  function stopBuzz() {{
    if (window.__mwAudio.buzzInterval) {{
      clearInterval(window.__mwAudio.buzzInterval);
      window.__mwAudio.buzzInterval = null;
    }}
  }}

  const alarmOn = {alarm_flag};
  if (alarmOn) startBuzz(); else stopBuzz();
}})();
</script>
""",
            height=0,
        )


def _timer_controls_row(key_prefix: str):
    """Controls shown near the top: set minutes, start/pause, reset."""
    _init_countdown_timer_defaults()

    cLbl, cM, cStart, cReset, _ = st.columns([1, 2, 1, 1, 7], gap="small")
    with cLbl:
        st.markdown("<div style='height:0.15rem'></div><div style='font-weight:700;'>min</div>", unsafe_allow_html=True)

    with cM:
        mins = st.number_input(
            "Timer minutes",
            min_value=1,
            max_value=60,
            value=int(st.session_state.timer_minutes),
            step=1,
            key=f"{key_prefix}__mins",
            label_visibility="collapsed",
            disabled=bool(st.session_state.timer_running),
        )

        # Apply minutes immediately when not running (treat as a reset)
        if int(mins) != int(st.session_state.timer_minutes) and not bool(st.session_state.timer_running):
            st.session_state.timer_minutes = int(mins)
            st.session_state.timer_duration_sec = int(mins) * 60
            st.session_state.timer_elapsed_before = 0.0
            st.session_state.timer_start_ts = time.time()
            st.session_state.timer_alarm = False
            st.rerun()


    with cStart:
        label = "Pause" if bool(st.session_state.timer_running) else "Start"
        if st.button(label, key=f"{key_prefix}__startpause", type="secondary"):
            if bool(st.session_state.timer_running):
                # Pause
                now = time.time()
                st.session_state.timer_elapsed_before = float(st.session_state.timer_elapsed_before) + (now - float(st.session_state.timer_start_ts))
                st.session_state.timer_running = False
            else:
                # Start / resume
                # Mark audio as unlocked by a user gesture (best-effort for iOS autoplay restrictions)
                st.session_state.timer_audio_unlocked = True
                # If already finished, restart from full duration
                if _timer_remaining_sec() == 0:
                    st.session_state.timer_duration_sec = int(st.session_state.timer_minutes) * 60
                    st.session_state.timer_elapsed_before = 0.0
                st.session_state.timer_start_ts = time.time()
                st.session_state.timer_running = True
                st.session_state.timer_alarm = False
            st.rerun()

    with cReset:
        if st.button("Reset", key=f"{key_prefix}__reset", type="secondary"):
            st.session_state.timer_running = False
            st.session_state.timer_duration_sec = int(st.session_state.timer_minutes) * 60
            st.session_state.timer_elapsed_before = 0.0
            st.session_state.timer_start_ts = time.time()
            st.session_state.timer_alarm = False
            st.rerun()


# ---------------- Global font scaling (main + practice) ---------------- (main + practice) ----------------
def _render_scale_css(scale: float):
    st.markdown(
        f"""
<style>
.katex, .katex-display > .katex {{
    font-size: {scale:.2f}em !important;
}}
div[data-testid="stMarkdownContainer"] p {{
    font-size: {0.98*scale:.2f}rem !important;
    margin-bottom: 0.25rem;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def _scale_controls_row(key_prefix: str):
    # Buttons appear under the top spacer so they don't hide behind Streamlit header
    cols = st.columns([1, 1, 10])
    if cols[0].button("+", key=f"{key_prefix}__plus", help="Increase font size", type="secondary"):
        st.session_state.ui_scale = min(1.70, round(float(st.session_state.ui_scale) + 0.10, 2))
        st.rerun()
    if cols[1].button("−", key=f"{key_prefix}__minus", help="Decrease font size", type="secondary"):
        st.session_state.ui_scale = max(0.80, round(float(st.session_state.ui_scale) - 0.10, 2))
        st.rerun()


# ---------------- Instruction line (cycle button + large text) ----------------
def _instruction_line(slot: str):
    """Small black circle button cycles a large instruction message (or blank)."""
    state_key = f"inst_state__{slot}"
    _set_default(state_key, 0)

    cbtn, ctext = st.columns([1, 20], gap="small")
    with cbtn:
        if st.button("●", key=f"inst_btn__{slot}", help="Instruction cycle", type="secondary"):
            st.session_state[state_key] = (int(st.session_state[state_key]) + 1) % 4
            st.rerun()

    state = int(st.session_state[state_key])
    if state == 0:
        msg = ""
        color = "#FFFFFF"
    elif state == 1:
        msg = "EMPTY HANDS! EYES ON THE BOARD!"
        color = "#FF3B3B"  # red
    elif state == 2:
        msg = "COPY DOWN IN YOUR BOOKS IN PURPLE PEN"
        color = "#B000FF"  # purple
    else:
        msg = "DO ON YOUR WHITEBOARDS AND HOVER WHEN READY"
        color = "#2F81F7"  # blue

    with ctext:
        safe_msg = msg if msg else "&nbsp;"
        st.markdown(
            f"<div class='inst-line' style='color:{color};'>{safe_msg}</div>",
            unsafe_allow_html=True,
        )


# ---------------- Canvas (per-question) ----------------
def _render_canvas(slot: str):
    """Per-question black canvas with white/purple/green ink + eraser."""
    if not _CANVAS_OK:
        st.warning("Drawing component not available. Ensure 'streamlit-drawable-canvas' is installed.")
        return

    mode_key = f"ink__{slot}"
    _set_default(mode_key, "white")  # white | purple | green | eraser
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
        height=416,  # as agreed (v8); user didn't request change now
        drawing_mode="freedraw",
        key=f"canvas__{slot}",
    )

    # Ink controls: W, P, G, E
    cW, cP, cG, cE, _ = st.columns([1, 1, 1, 1, 8])
    if cW.button("W", key=f"inkW__{slot}", help="White ink", type="secondary"):
        st.session_state[mode_key] = "white"
        st.rerun()
    if cP.button("P", key=f"inkP__{slot}", help="Purple ink", type="secondary"):
        st.session_state[mode_key] = "purple"
        st.rerun()
    if cG.button("G", key=f"inkG__{slot}", help="Green ink", type="secondary"):
        st.session_state[mode_key] = "green"
        st.rerun()
    if cE.button("E", key=f"inkE__{slot}", help="Eraser (toggle)", type="secondary"):
        st.session_state[mode_key] = "white" if st.session_state[mode_key] == "eraser" else "eraser"
        st.rerun()


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


# ---------------- Practice page ----------------
def _render_practice_mode():
    ctx = st.session_state.get("practice_ctx")
    if not ctx:
        st.session_state.mode = "main"
        st.rerun()

    topic = ctx["topic"]
    template_id = ctx["template_id"]
    max_difficulty = int(ctx["max_difficulty"])

    # extra spacing at top (so controls aren't hidden)
    st.markdown("<div style='height: 1.6rem'></div>", unsafe_allow_html=True)

    # timer controls under spacer
    _timer_controls_row("practice_timer")

    # top controls row under spacer
    top = st.columns([1, 1, 1, 1, 8])
    if top[0].button("←", key="back_main", help="Back", type="secondary"):
        st.session_state.mode = "main"
        st.rerun()

    if top[1].button("N", key="regen_practice", help="New set of 10", type="secondary"):
        st.session_state.practice_seed = random.randint(1, 10**9)
        st.session_state.practice_questions = None
        for k in list(st.session_state.keys()):
            if k.startswith("prac_ans__"):
                del st.session_state[k]
        st.rerun()

    # shared font scaling buttons
    _scale_controls_row("practice_top")

    st.markdown(f"#### {topic}")

    if st.session_state.get("practice_questions") is None:
        qs = generate_questions_by_template(
            topic=topic,
            template_id=template_id,
            max_difficulty=max_difficulty,
            n=10,
            seed=int(st.session_state.practice_seed),
        )
        st.session_state.practice_questions = qs
    else:
        qs = st.session_state.practice_questions

    # Row-wise numbering: (1,2) then (3,4) ...
    for row in range(5):
        left_idx = 2 * row
        right_idx = 2 * row + 1
        colL, colR = st.columns(2, gap="large")

        for target_col, i in [(colL, left_idx), (colR, right_idx)]:
            with target_col:
                q = qs[i]
                st.markdown(f"**{i+1}. {q.prompt}**")
                if q.latex.strip():
                    st.latex(q.latex)

                ans_key = f"prac_ans__{i}"
                _set_default(ans_key, False)

                # Controls row: N, A, answer shown to the RIGHT of A
                cN, cA, cAns = st.columns([1, 1, 10])

                if cN.button("N", key=f"pracN_btn__{i}", help="New version", type="secondary"):
                    new_seed = random.randint(1, 10**9)
                    qs[i] = regenerate_question(
                        topic=topic,
                        template_id=q.template_id,
                        max_difficulty=max_difficulty,
                        new_seed=new_seed,
                    )
                    st.session_state.practice_questions = qs
                    st.session_state[ans_key] = False
                    st.rerun()

                if cA.button("A", key=f"pracA_btn__{i}", help="Show/hide answer", type="secondary"):
                    st.session_state[ans_key] = not st.session_state[ans_key]
                    st.rerun()

                if st.session_state[ans_key]:
                    cAns.latex(rf"\color{{green}}{{{qs[i].answer_latex}}}")
                else:
                    cAns.markdown("&nbsp;", unsafe_allow_html=True)

        st.markdown("<div style='height: 1.1rem'></div>", unsafe_allow_html=True)


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Settings")

    topics = st.multiselect(
        "Topics",
        options=available_topics(),
        default=[t for t in DEFAULT_TOPICS if t in available_topics()],
    )
    max_diff = st.slider("Max difficulty", 1, 5, 3)

    if "master_seed" not in st.session_state:
        st.session_state.master_seed = random.randint(1, 10**9)

    colA, colB = st.columns(2)
    with colA:
        if st.button("Regenerate ALL", type="primary"):
            st.session_state.master_seed = random.randint(1, 10**9)
            st.session_state.generated = None
            st.session_state.pdf_cache = None
            st.session_state.pdf_fp = None
    with colB:
        master_seed_manual = st.number_input(
            "Master seed",
            min_value=1,
            max_value=10**9,
            value=int(st.session_state.master_seed),
        )
        st.session_state.master_seed = int(master_seed_manual)


# ---------------- App modes ----------------
if "mode" not in st.session_state:
    st.session_state.mode = "main"

# global ui scale (default to maximum so you can only decrease)
_set_default("ui_scale", 1.70)
_render_scale_css(float(st.session_state.ui_scale))

# floating timer (all pages)
_render_floating_timer()

if st.session_state.mode == "practice":
    _render_practice_mode()
    st.stop()


# ---------------- Main page ----------------
seed = int(st.session_state.master_seed)

if not topics:
    st.warning("Pick at least one topic in the sidebar.")
    st.stop()

# Extra top space so nothing is clipped by the header
st.markdown("<div style='height: 1.9rem'></div>", unsafe_allow_html=True)

# timer controls under the spacer
_timer_controls_row("main_timer")

# Main-page font controls under the spacer
_scale_controls_row("main_top")

if "generated" not in st.session_state or st.session_state.generated is None:
    st.session_state.generated = generate_two_per_topic(topics=topics, max_difficulty=max_diff, seed=seed)
    st.session_state.pdf_cache = None
    st.session_state.pdf_fp = None

grouped = st.session_state.generated
ordered_topics = [t for t in topics if t in grouped]

# slightly more space before first topic (as requested)
st.markdown("<div style='height: 1.4rem'></div>", unsafe_allow_html=True)

# Constant spacing between topics (keep even when buttons are pressed) – +10% vs prior 65vh
GAP_VH = 72  # 65 * 1.1 ≈ 71.5

for topic in ordered_topics:
    qs = grouped.get(topic, [])
    if len(qs) < 2:
        st.info(f"{topic}: not enough templates found at the selected difficulty.")
        continue

    st.markdown(f"#### {topic}")

    # Default: hide the second question until revealed
    show2_key = f"show2__{_slot(topic, 1)}"
    _set_default(show2_key, False)

    c1, c2 = st.columns(2, gap="large")

    # ---------------- Q1 ----------------
    slot1 = _slot(topic, 0)
    ans1_key = f"ans__{slot1}"
    work1_key = f"work__{slot1}"
    draw1_key = f"draw__{slot1}"
    for k in (ans1_key, work1_key, draw1_key):
        _set_default(k, False)

    with c1:
        q1 = grouped[topic][0]

        _instruction_line(slot1)

        st.markdown(f"**{q1.prompt}**")
        if q1.latex.strip():
            st.latex(q1.latex)

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

        # Controls at bottom: N A W D I
        ctrl = st.columns(5)
        if ctrl[0].button("N", key=f"n__{slot1}", help="New version", type="secondary"):
            new_seed = random.randint(1, 10**9)
            grouped[topic][0] = regenerate_question(
                topic=topic, template_id=q1.template_id, max_difficulty=max_diff, new_seed=new_seed
            )
            st.session_state[ans1_key] = False
            st.session_state[work1_key] = False
            st.session_state[draw1_key] = False
            st.session_state[f"ink__{slot1}"] = "white"
            st.session_state.generated = grouped
            st.session_state.pdf_cache = None
            st.session_state.pdf_fp = None
            st.rerun()

        if ctrl[1].button("A", key=f"a__{slot1}", help="Answer", type="secondary"):
            _toggle(ans1_key, default=False)
            st.session_state.pdf_cache = None
            st.rerun()

        if ctrl[2].button("W", key=f"w__{slot1}", help="Working", type="secondary"):
            _toggle(work1_key, default=False)
            st.rerun()

        if ctrl[3].button("D", key=f"d__{slot1}", help="Draw", type="secondary"):
            _toggle(draw1_key, default=False)
            st.rerun()

        if ctrl[4].button("I", key=f"i__{slot1}", help="10-question practice page", type="secondary"):
            _enter_practice(topic=topic, template_id=q1.template_id, max_difficulty=max_diff)

    # ---------------- Q2 (hidden by default) ----------------
    slot2 = _slot(topic, 1)
    ans2_key = f"ans__{slot2}"
    work2_key = f"work__{slot2}"
    draw2_key = f"draw__{slot2}"
    for k in (ans2_key, work2_key, draw2_key):
        _set_default(k, False)

    with c2:
        q2 = grouped[topic][1]

        # Instruction line exists even when Q2 is hidden (still clickable)
        _instruction_line(slot2)

        if not st.session_state.get(show2_key, False):
            # Leave blank (no "hidden" message)
            st.markdown("&nbsp;", unsafe_allow_html=True)
        else:
            st.markdown(f"**{q2.prompt}**")
            if q2.latex.strip():
                st.latex(q2.latex)

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

        # Controls at bottom
        if st.session_state.get(show2_key, False):
            ctrl = st.columns(6)
            if ctrl[0].button("N", key=f"n__{slot2}", help="New version", type="secondary"):
                new_seed = random.randint(1, 10**9)
                grouped[topic][1] = regenerate_question(
                    topic=topic, template_id=q2.template_id, max_difficulty=max_diff, new_seed=new_seed
                )
                st.session_state[ans2_key] = False
                st.session_state[work2_key] = False
                st.session_state[draw2_key] = False
                st.session_state[f"ink__{slot2}"] = "white"
                st.session_state.generated = grouped
                st.session_state.pdf_cache = None
                st.session_state.pdf_fp = None
                st.rerun()

            if ctrl[1].button("A", key=f"a__{slot2}", help="Answer", type="secondary"):
                _toggle(ans2_key, default=False)
                st.rerun()

            if ctrl[2].button("W", key=f"w__{slot2}", help="Working", type="secondary"):
                _toggle(work2_key, default=False)
                st.rerun()

            if ctrl[3].button("D", key=f"d__{slot2}", help="Draw", type="secondary"):
                _toggle(draw2_key, default=False)
                st.rerun()

            if ctrl[4].button("I", key=f"i__{slot2}", help="10-question practice page", type="secondary"):
                _enter_practice(topic=topic, template_id=q2.template_id, max_difficulty=max_diff)

            if ctrl[5].button("H", key=f"h__{slot2}", help="Hide/show Q2", type="secondary"):
                st.session_state[show2_key] = not st.session_state.get(show2_key, False)
                st.rerun()
        else:
            # Only show H (minimal distractions)
            ctrl = st.columns([1, 1, 1, 1, 1, 1])
            if ctrl[5].button("H", key=f"h__{slot2}", help="Hide/show Q2", type="secondary"):
                st.session_state[show2_key] = True
                st.rerun()

    # Constant spacing between topic blocks (+10%), always present
    st.markdown(f"<div style='height: {GAP_VH}vh'></div>", unsafe_allow_html=True)


# ---------------- PDF export (cached so timer refresh doesn't rebuild every second) ----------------
if ordered_topics:
    pdf_title = "Mixed topics" if len(ordered_topics) > 1 else ordered_topics[0]

    # Build a quick fingerprint of current questions (fast; used to cache PDF bytes)
    fp_parts = []
    for t in ordered_topics:
        for q in grouped[t][:2]:
            fp_parts.append(f"{t}|{q.template_id}|{q.prompt}|{q.latex}|{q.answer_latex}")
    fp_raw = "||".join(fp_parts).encode("utf-8")
    fp = hashlib.md5(fp_raw).hexdigest()

    if st.session_state.get("pdf_fp") != fp or st.session_state.get("pdf_cache") is None:
        st.session_state.pdf_cache = build_pdf_bytes(
            title=pdf_title,
            grouped={t: grouped[t] for t in ordered_topics},
            seed=seed,
        )
        st.session_state.pdf_fp = fp

    st.download_button(
        label="Download PDF (Questions + Answers)",
        data=st.session_state.pdf_cache,
        file_name="worksheet.pdf",
        mime="application/pdf",
        type="primary",
    )
