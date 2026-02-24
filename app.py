import random
import streamlit as st

from question_bank import (
    available_topics,
    generate_question_from_template,
    generate_set_meta,
)
from pdf_export import build_pdf_bytes

st.set_page_config(page_title="Worksheet Generator", layout="wide")
st.title("Worksheet Generator")

with st.sidebar:
    st.header("Settings")
    topics = st.multiselect("Topics", options=available_topics(), default=available_topics()[:3])
    max_diff = st.slider("Max difficulty", 1, 5, 2)
    n_q = st.number_input("Number of questions", min_value=4, max_value=40, value=8, step=1)

    st.divider()
    show_answers = st.toggle("Show answers (on screen)", value=False)

    # keep a settings signature so we can rebuild the set automatically when settings change
    settings_sig = (tuple(topics), int(max_diff), int(n_q))

    if "settings_sig" not in st.session_state:
        st.session_state.settings_sig = settings_sig

    if "set_seed" not in st.session_state:
        st.session_state.set_seed = random.randint(1, 10**9)

    if "q_meta" not in st.session_state:
        st.session_state.q_meta = []

    colA, colB = st.columns(2)
    with colA:
        if st.button("Regenerate all"):
            st.session_state.set_seed = random.randint(1, 10**9)
            st.session_state.q_meta = generate_set_meta(topics, int(max_diff), int(n_q), int(st.session_state.set_seed))
            # reset working toggles
            for i in range(int(n_q)):
                st.session_state.pop(f"show_work_{i}", None)

    with colB:
        seed_manual = st.number_input("Set seed", min_value=1, max_value=10**9, value=int(st.session_state.set_seed))
        st.session_state.set_seed = int(seed_manual)

# Validate topics
if not topics:
    st.warning("Pick at least one topic in the sidebar.")
    st.stop()

# Rebuild set if settings changed or meta empty
if st.session_state.settings_sig != settings_sig or not st.session_state.q_meta:
    st.session_state.settings_sig = settings_sig
    st.session_state.q_meta = generate_set_meta(topics, int(max_diff), int(n_q), int(st.session_state.set_seed))
    for i in range(int(n_q)):
        st.session_state.pop(f"show_work_{i}", None)

if not st.session_state.q_meta:
    st.error("No questions matched your filters.")
    st.stop()

st.caption(f"Seed: {int(st.session_state.set_seed)}  •  Topics: {', '.join(topics)}  •  Max difficulty: {int(max_diff)}")

questions = []
for meta in st.session_state.q_meta:
    questions.append(generate_question_from_template(meta["template_id"], int(meta["seed"])))

# Render questions
for i, q in enumerate(questions):
    left, right = st.columns([0.78, 0.22])

    with left:
        st.markdown(f"### {i+1}.")
        st.latex(q.prompt)
        st.latex(q.latex)

        if show_answers:
            st.markdown("**Answer:**")
            st.latex(q.answer_latex)

        show_work_key = f"show_work_{i}"
        if st.session_state.get(show_work_key, False):
            st.markdown("**Working:**")
            for step in q.working_steps_latex:
                st.latex(step)

    with right:
        st.markdown(" ")
        st.markdown(" ")
        if st.button("New version", key=f"regen_{i}"):
            # keep the same template_id but change the seed
            st.session_state.q_meta[i]["seed"] = random.randint(1, 10**9)
            st.session_state[show_work_key] = False
            st.rerun()

        label = "Hide working" if st.session_state.get(show_work_key, False) else "Show working"
        if st.button(label, key=f"work_{i}"):
            st.session_state[show_work_key] = not st.session_state.get(show_work_key, False)
            st.rerun()

    st.divider()

# PDF download
pdf_title = " / ".join(topics) if len(topics) <= 3 else "Mixed topics"
pdf_bytes = build_pdf_bytes(title=pdf_title, questions=questions, seed=int(st.session_state.set_seed))

st.download_button(
    label="Download PDF (Questions + Answers)",
    data=pdf_bytes,
    file_name="worksheet.pdf",
    mime="application/pdf",
)
