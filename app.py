import random
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

st.set_page_config(page_title="Maths Worksheet Generator", layout="wide")

# Very small, low-distraction control buttons (secondary buttons only)
st.markdown(
    """
<style>
/* Shrink SECONDARY buttons (used for per-question controls) */
button[kind="secondary"] {
    padding: 0.00rem 0.16rem !important;
    font-size: 0.55rem !important;
    line-height: 1 !important;
    height: 0.95rem !important;
    min-height: 0.95rem !important;
    min-width: 1.15rem !important;
}
/* Reduce excess spacing inside columns */
div[data-testid="column"] > div { gap: 0.30rem; }
/* Reduce space above first element */
.block-container { padding-top: 1.2rem; }
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


def _render_canvas(slot: str):
    """Per-question black canvas with white/purple/green ink + eraser."""
    if not _CANVAS_OK:
        st.warning("Drawing component not available. Ensure 'streamlit-drawable-canvas' is installed.")
        return

    mode_key = f"ink__{slot}"
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "white"  # white | purple | green | eraser

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
        height=416,  # 20% smaller than v7
        drawing_mode="freedraw",
        key=f"canvas__{slot}",
    )

    # Ink controls: W (white), P (purple), G (green), E (eraser toggle)
    cW, cP, cG, cE, _ = st.columns([1, 1, 1, 1, 6])

    if cW.button("W", key=f"inkW__{slot}", help="White ink"):
        st.session_state[mode_key] = "white"
        st.rerun()
    if cP.button("P", key=f"inkP__{slot}", help="Purple ink"):
        st.session_state[mode_key] = "purple"
        st.rerun()
    if cG.button("G", key=f"inkG__{slot}", help="Green ink"):
        st.session_state[mode_key] = "green"
        st.rerun()
    if cE.button("E", key=f"inkE__{slot}", help="Eraser (toggle)"):
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
    # clear any old per-question answer toggles
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

    # Font scaling (practice page only)
    if "practice_scale" not in st.session_state:
        st.session_state.practice_scale = 1.00  # 1.0 = default

    scale = float(st.session_state.practice_scale)
    st.markdown(
        f"""
<style>
/* Practice-page font scaling */
.katex, .katex-display > .katex {{
    font-size: {scale:.2f}em !important;
}}
div[data-testid="stMarkdownContainer"] p {{
    font-size: {0.95*scale:.2f}rem !important;
    margin-bottom: 0.25rem;
}}
</style>
""",
        unsafe_allow_html=True,
    )

    top = st.columns([1, 1, 1, 1, 8])
    if top[0].button("←", key="back_main", help="Back"):
        st.session_state.mode = "main"
        st.rerun()

    if top[1].button("N", key="regen_practice", help="New set of 10"):
        st.session_state.practice_seed = random.randint(1, 10**9)
        st.session_state.practice_questions = None
        for k in list(st.session_state.keys()):
            if k.startswith("prac_ans__"):
                del st.session_state[k]
        st.rerun()

    if top[2].button("+", key="prac_plus", help="Increase font size"):
        st.session_state.practice_scale = min(1.60, round(scale + 0.10, 2))
        st.rerun()

    if top[3].button("−", key="prac_minus", help="Decrease font size"):
        st.session_state.practice_scale = max(0.80, round(scale - 0.10, 2))
        st.rerun()

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

    # Two columns (5 per column) for iPad-friendly viewing
    colA, colB = st.columns(2, gap="large")

    for i in range(len(qs)):
        target = colA if i < 5 else colB
        with target:
            q = qs[i]
            st.markdown(f"**{i+1}. {q.prompt}**")
            if q.latex.strip():
                st.latex(q.latex)

            ans_key = f"prac_ans__{i}"
            if ans_key not in st.session_state:
                st.session_state[ans_key] = False

            # Controls row: N, A, answer shown to the RIGHT of A
            cN, cA, cAns = st.columns([1, 1, 10])

            if cN.button("N", key=f"pracN_btn__{i}", help="New version"):
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

            if cA.button("A", key=f"pracA_btn__{i}", help="Show/hide answer"):
                st.session_state[ans_key] = not st.session_state[ans_key]
                st.rerun()

            if st.session_state[ans_key]:
                # Green answer (KaTeX)
                cAns.latex(rf"\color{{green}}{{{qs[i].answer_latex}}}")
            else:
                # keep a small placeholder to reduce layout shifts
                cAns.markdown("&nbsp;", unsafe_allow_html=True)

            st.markdown("<div style='height: 0.75rem'></div>", unsafe_allow_html=True)



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

if st.session_state.mode == "practice":
    _render_practice_mode()
    st.stop()


# ---------------- Main page ----------------
seed = int(st.session_state.master_seed)

if not topics:
    st.warning("Pick at least one topic in the sidebar.")
    st.stop()

if "generated" not in st.session_state or st.session_state.generated is None:
    st.session_state.generated = generate_two_per_topic(topics=topics, max_difficulty=max_diff, seed=seed)

grouped = st.session_state.generated
ordered_topics = [t for t in topics if t in grouped]

# Spacer above first topic block
st.markdown("<div style='height: 0.9rem'></div>", unsafe_allow_html=True)

for topic in ordered_topics:
    qs = grouped.get(topic, [])
    if len(qs) < 2:
        st.info(f"{topic}: not enough templates found at the selected difficulty.")
        continue

    st.markdown(f"#### {topic}")

    # Default: hide the second question until revealed
    show2_key = f"show2__{_slot(topic, 1)}"
    if show2_key not in st.session_state:
        st.session_state[show2_key] = False

    c1, c2 = st.columns(2, gap="large")

    # ---------------- Q1 ----------------
    slot1 = _slot(topic, 0)
    ans1_key = f"ans__{slot1}"
    work1_key = f"work__{slot1}"
    draw1_key = f"draw__{slot1}"

    for k in (ans1_key, work1_key, draw1_key):
        if k not in st.session_state:
            st.session_state[k] = False

    with c1:
        q1 = grouped[topic][0]
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
        if ctrl[0].button("N", key=f"n__{slot1}", help="New version"):
            new_seed = random.randint(1, 10**9)
            grouped[topic][0] = regenerate_question(
                topic=topic, template_id=q1.template_id, max_difficulty=max_diff, new_seed=new_seed
            )
            st.session_state[ans1_key] = False
            st.session_state[work1_key] = False
            st.session_state[draw1_key] = False
            st.session_state[f"ink__{slot1}"] = "white"
            st.session_state.generated = grouped
            st.rerun()

        if ctrl[1].button("A", key=f"a__{slot1}", help="Answer"):
            _toggle(ans1_key, default=False)
            st.rerun()

        if ctrl[2].button("W", key=f"w__{slot1}", help="Working"):
            _toggle(work1_key, default=False)
            st.rerun()

        if ctrl[3].button("D", key=f"d__{slot1}", help="Draw"):
            _toggle(draw1_key, default=False)
            st.rerun()

        if ctrl[4].button("I", key=f"i__{slot1}", help="10-question practice page"):
            _enter_practice(topic=topic, template_id=q1.template_id, max_difficulty=max_diff)

    # ---------------- Q2 (hidden by default) ----------------
    slot2 = _slot(topic, 1)
    ans2_key = f"ans__{slot2}"
    work2_key = f"work__{slot2}"
    draw2_key = f"draw__{slot2}"

    for k in (ans2_key, work2_key, draw2_key):
        if k not in st.session_state:
            st.session_state[k] = False

    with c2:
        q2 = grouped[topic][1]

        if not st.session_state.get(show2_key, False):
            st.info("Second question hidden.")
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
            if ctrl[0].button("N", key=f"n__{slot2}", help="New version"):
                new_seed = random.randint(1, 10**9)
                grouped[topic][1] = regenerate_question(
                    topic=topic, template_id=q2.template_id, max_difficulty=max_diff, new_seed=new_seed
                )
                st.session_state[ans2_key] = False
                st.session_state[work2_key] = False
                st.session_state[draw2_key] = False
                st.session_state[f"ink__{slot2}"] = "white"
                st.session_state.generated = grouped
                st.rerun()

            if ctrl[1].button("A", key=f"a__{slot2}", help="Answer"):
                _toggle(ans2_key, default=False)
                st.rerun()

            if ctrl[2].button("W", key=f"w__{slot2}", help="Working"):
                _toggle(work2_key, default=False)
                st.rerun()

            if ctrl[3].button("D", key=f"d__{slot2}", help="Draw"):
                _toggle(draw2_key, default=False)
                st.rerun()

            if ctrl[4].button("I", key=f"i__{slot2}", help="10-question practice page"):
                _enter_practice(topic=topic, template_id=q2.template_id, max_difficulty=max_diff)

            if ctrl[5].button("H", key=f"h__{slot2}", help="Hide/show Q2"):
                st.session_state[show2_key] = not st.session_state.get(show2_key, False)
                st.rerun()
        else:
            # Only show H (minimal distractions)
            ctrl = st.columns([1, 1, 1, 1, 1, 1])
            if ctrl[5].button("H", key=f"h__{slot2}", help="Hide/show Q2"):
                st.session_state[show2_key] = True
                st.rerun()

    # Spacing between topics: if no buttons pressed (default), make a large gap
    any_active = (
        st.session_state.get(show2_key, False)
        or st.session_state.get(ans1_key, False)
        or st.session_state.get(work1_key, False)
        or st.session_state.get(draw1_key, False)
        or st.session_state.get(ans2_key, False)
        or st.session_state.get(work2_key, False)
        or st.session_state.get(draw2_key, False)
    )

    if not any_active:
        st.markdown("<div style='height: 65vh'></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)


# PDF export (includes both questions per topic)
if ordered_topics:
    pdf_title = "Mixed topics" if len(ordered_topics) > 1 else ordered_topics[0]
    pdf_bytes = build_pdf_bytes(title=pdf_title, grouped={t: grouped[t] for t in ordered_topics}, seed=seed)

    st.download_button(
        label="Download PDF (Questions + Answers)",
        data=pdf_bytes,
        file_name="worksheet.pdf",
        mime="application/pdf",
        type="primary",
    )
