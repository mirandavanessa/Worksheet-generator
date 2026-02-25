import random
import time
import hashlib
import streamlit as st

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

# ---------- CSS: minimal distraction controls + instruction bar + floating timer ----------
st.markdown(
    """
<style>
/* Increase top padding so top controls are not hidden by Streamlit header */
.block-container { padding-top: 2.4rem; }

/* Shrink SECONDARY buttons (used for per-question micro-controls) */
button[kind="secondary"] {
    padding: 0.00rem 0.14rem !important;
    font-size: 0.52rem !important;
    line-height: 1 !important;
    height: 0.92rem !important;
    min-height: 0.92rem !important;
    min-width: 1.05rem !important;
}

/* PRIMARY buttons: use as a very subtle "instruction bar" (barely visible) */
button[kind="primary"] {
    background: rgba(0,0,0,0.00) !important;
    color: rgba(255,255,255,0.00) !important; /* label is NBSP; keep invisible */
    border: 1px solid rgba(255,255,255,0.10) !important;
    padding: 0.18rem 0.40rem !important;
    font-size: 0.80rem !important;
    height: 1.60rem !important;
    min-height: 1.60rem !important;
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

/* Instruction overlay text (sits on top of a blank primary button) */
.inst-overlay {
    margin-top: -1.60rem;          /* pull overlay onto the button */
    height: 1.60rem;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;          /* clicks go to the button underneath */
    font-weight: 700;
    letter-spacing: 0.03em;
    font-size: 0.78rem;
    margin-bottom: 0;
}

/* Floating timer (fixed top-right) */
.floating-timer {
    position: fixed;
    top: 0.65rem;
    right: 1.00rem;
    z-index: 10000;
    background: rgba(0,0,0,0.92);
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 8px;
    padding: 0.25rem 0.50rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size: 0.85rem;
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


# ---------------- Floating timer ----------------
def _render_floating_timer():
    # Start a stopwatch on first load
    _set_default("timer_start", time.time())

    if _AUTOREFRESH_OK:
        # Refresh once per second without blocking
        st_autorefresh(interval=1000, key="__timer_refresh__")

    elapsed = int(time.time() - float(st.session_state.timer_start))
    mm = elapsed // 60
    ss = elapsed % 60
    st.markdown(f"<div class='floating-timer'>{mm:02d}:{ss:02d}</div>", unsafe_allow_html=True)


# ---------------- Global font scaling (main + practice) ----------------
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


# ---------------- Instruction line (tap to cycle) ----------------
def _instruction_bar(slot: str):
    """
    Black instruction bar, tap to cycle:
      blank -> EMPTY HAND, EYES ON THE BOARD
            -> COPY DOWN IN YOUR BOOKS IN PURPLE PEN  (purple text)
            -> DO ON YOUR WHITEBOARDS AND HOVER WHEN READY
            -> blank
    Implemented as a blank primary button + overlay text (pointer-events disabled).
    """
    state_key = f"inst_state__{slot}"
    _set_default(state_key, 0)

    # Clickable area: blank label
    if st.button("\u00A0", key=f"inst_btn__{slot}", type="primary", use_container_width=True):
        st.session_state[state_key] = (int(st.session_state[state_key]) + 1) % 4
        st.rerun()

    state = int(st.session_state[state_key])
    if state == 0:
        msg = "&nbsp;"
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

    st.markdown(
        f"<div class='inst-overlay' style='color:{color};'>{msg}</div>",
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

# global ui scale
_set_default("ui_scale", 1.00)
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

        _instruction_bar(slot1)

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

        # Instruction bar exists even when Q2 is hidden (still clickable)
        _instruction_bar(slot2)

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
