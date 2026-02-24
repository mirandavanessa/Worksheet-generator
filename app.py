import random
import streamlit as st

from question_bank import available_topics, generate_questions
from pdf_export import build_pdf_bytes

st.set_page_config(page_title="Worksheet Generator", layout="wide")
st.title("Worksheet Generator (MathsWhiteboard-style)")

with st.sidebar:
    st.header("Settings")
    topics = st.multiselect("Topics", options=available_topics(), default=available_topics()[:3])
    max_diff = st.slider("Max difficulty", 1, 5, 2)
    n_q = st.number_input("Number of questions", min_value=4, max_value=30, value=8, step=1)
    show_answers = st.toggle("Show answers on screen", value=False)

    if "seed" not in st.session_state:
        st.session_state.seed = random.randint(1, 10**9)

    colA, colB = st.columns(2)
    with colA:
        if st.button("Regenerate"):
            st.session_state.seed = random.randint(1, 10**9)
    with colB:
        seed_manual = st.number_input("Seed", min_value=1, max_value=10**9, value=int(st.session_state.seed))
        st.session_state.seed = int(seed_manual)

seed = int(st.session_state.seed)

if not topics:
    st.warning("Pick at least one topic in the sidebar.")
    st.stop()

questions = generate_questions(topics=topics, max_difficulty=max_diff, n=int(n_q), seed=seed)

st.caption(f"Seed: {seed}  •  Topics: {', '.join(topics)}  •  Max difficulty: {max_diff}")

if not questions:
    st.error("No questions matched your filters.")
    st.stop()

for i, q in enumerate(questions, start=1):
    st.markdown(f"**{i}. {q.prompt}**  _(Topic: {q.topic})_")
    st.latex(q.latex)

    if show_answers:
        with st.expander("Answer", expanded=False):
            st.latex(q.answer_latex)

st.divider()

pdf_title = " / ".join(topics) if len(topics) <= 3 else "Mixed topics"
pdf_bytes = build_pdf_bytes(title=pdf_title, questions=questions, seed=seed)

st.download_button(
    label="Download PDF (Questions + Answers)",
    data=pdf_bytes,
    file_name="worksheet.pdf",
    mime="application/pdf",
)
