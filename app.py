import random
import streamlit as st

from question_bank import available_topics, generate_two_per_topic, regenerate_question
from pdf_export import build_pdf_bytes

# Optional drawing canvas (per-question)
try:
    from streamlit_drawable_canvas import st_canvas
    _CANVAS_OK = True
except Exception:
    st_canvas = None
    _CANVAS_OK = False

st.set_page_config(page_title="Worksheet Generator", layout="wide")

# Small, low-distraction control buttons (secondary buttons only)
st.markdown(
    """
<style>
/* Shrink SECONDARY buttons (used for per-question controls) */
button[kind="secondary"] {
    padding: 0.02rem 0.22rem !important;
    font-size: 0.62rem !important;
    line-height: 1 !important;
    height: 1.10rem !important;
    min-height: 1.10rem !important;
    min-width: 1.45rem !important;
}
/* Reduce excess spacing between elements inside columns */
div[data-testid="column"] > div { gap: 0.35rem; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("Worksheet Generator")
st.caption(
    "Two questions per topic (side-by-side) • "
    "N=new version • H=hide/show Q2 • A=answer • W=working • D=drawing pad"
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

seed = int(st.session_state.master_seed)

if not topics:
    st.warning("Pick at least one topic in the sidebar.")
    st.stop()

# Generate or reuse
if "generated" not in st.session_state or st.session_state.generated is None:
    st.session_state.generated = generate_two_per_topic(topics=topics, max_difficulty=max_diff, seed=seed)

grouped = st.session_state.generated
ordered_topics = [t for t in topics if t in grouped]

def _render_canvas(slot: str):
    """Black canvas + white pen, per question."""
    if not _CANVAS_OK:
        st.warning("Drawing component not available. Ensure 'streamlit-drawable-canvas' is installed.")
        return
    st_canvas(
        fill_color="rgba(255, 255, 255, 0)",
        stroke_width=3,
        stroke_color="#FFFFFF",
        background_color="#000000",
        height=260,
        drawing_mode="freedraw",
        key=f"canvas__{slot}",
    )

for topic in ordered_topics:
    st.markdown(f"### {topic}")
    qs = grouped.get(topic, [])
    if len(qs) < 2:
        st.info("Not enough templates found for this topic at the selected difficulty.")
        continue

    # Default: hide the second question until revealed
    show2_key = f"show2__{_slot(topic, 1)}"
    if show2_key not in st.session_state:
        st.session_state[show2_key] = False

    c1, c2 = st.columns(2, gap="large")

    # ---------------- Q1 (always visible) ----------------
    slot1 = _slot(topic, 0)
    ans1_key = f"ans__{slot1}"
    work1_key = f"work__{slot1}"
    draw1_key = f"draw__{slot1}"
    for k in (ans1_key, work1_key, draw1_key):
        if k not in st.session_state:
            st.session_state[k] = False

    with c1:
        q1 = grouped[topic][0]

        # Content first
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

        # Controls at bottom
        ctrl = st.columns(4)
        if ctrl[0].button("N", key=f"n__{slot1}", help="New version (this question only)"):
            new_seed = random.randint(1, 10**9)
            grouped[topic][0] = regenerate_question(
                topic=topic, template_id=q1.template_id, max_difficulty=max_diff, new_seed=new_seed
            )
            st.session_state[ans1_key] = False
            st.session_state[work1_key] = False
            st.session_state[draw1_key] = False
            st.session_state.generated = grouped
            st.rerun()

        if ctrl[1].button("A", key=f"a__{slot1}", help="Show/hide answer"):
            _toggle(ans1_key, default=False)
            st.rerun()

        if ctrl[2].button("W", key=f"w__{slot1}", help="Show/hide full working"):
            _toggle(work1_key, default=False)
            st.rerun()

        if ctrl[3].button("D", key=f"d__{slot1}", help="Show/hide drawing pad"):
            _toggle(draw1_key, default=False)
            st.rerun()

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
            st.info("Second question hidden. Press **H** to reveal.")
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

        # Controls at bottom (always show H; others only when revealed)
        if st.session_state.get(show2_key, False):
            ctrl = st.columns(5)
            if ctrl[0].button("N", key=f"n__{slot2}", help="New version (this question only)"):
                new_seed = random.randint(1, 10**9)
                grouped[topic][1] = regenerate_question(
                    topic=topic, template_id=q2.template_id, max_difficulty=max_diff, new_seed=new_seed
                )
                st.session_state[ans2_key] = False
                st.session_state[work2_key] = False
                st.session_state[draw2_key] = False
                st.session_state.generated = grouped
                st.rerun()

            if ctrl[1].button("A", key=f"a__{slot2}", help="Show/hide answer"):
                _toggle(ans2_key, default=False)
                st.rerun()

            if ctrl[2].button("W", key=f"w__{slot2}", help="Show/hide full working"):
                _toggle(work2_key, default=False)
                st.rerun()

            if ctrl[3].button("D", key=f"d__{slot2}", help="Show/hide drawing pad"):
                _toggle(draw2_key, default=False)
                st.rerun()

            if ctrl[4].button("H", key=f"h__{slot2}", help="Hide/show the second question"):
                st.session_state[show2_key] = not st.session_state.get(show2_key, False)
                st.rerun()
        else:
            # Only show H (minimal distractions)
            ctrl = st.columns([1, 1, 1, 1, 1])
            if ctrl[4].button("H", key=f"h__{slot2}", help="Hide/show the second question"):
                st.session_state[show2_key] = True
                st.rerun()

    st.divider()

# PDF export (always includes both questions for each topic)
pdf_title = "Mixed topics" if len(ordered_topics) > 1 else ordered_topics[0]
pdf_bytes = build_pdf_bytes(title=pdf_title, grouped={t: grouped[t] for t in ordered_topics}, seed=seed)

st.download_button(
    label="Download PDF (Questions + Answers)",
    data=pdf_bytes,
    file_name="worksheet.pdf",
    mime="application/pdf",
    type="primary",
)
