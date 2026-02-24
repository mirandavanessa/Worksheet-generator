import random
import streamlit as st

from question_bank import available_topics, generate_two_per_topic, regenerate_question
from pdf_export import build_pdf_bytes

st.set_page_config(page_title="Worksheet Generator", layout="wide")

st.title("Worksheet Generator")
st.caption("Two questions per topic (side-by-side) • Per-question regenerate • Full working toggle")

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
        if st.button("Regenerate ALL"):
            st.session_state.master_seed = random.randint(1, 10**9)
            st.session_state.generated = None
    with colB:
        master_seed_manual = st.number_input("Master seed", min_value=1, max_value=10**9, value=int(st.session_state.master_seed))
        st.session_state.master_seed = int(master_seed_manual)

seed = int(st.session_state.master_seed)

if not topics:
    st.warning("Pick at least one topic in the sidebar.")
    st.stop()

# Generate or reuse
if "generated" not in st.session_state or st.session_state.generated is None:
    st.session_state.generated = generate_two_per_topic(topics=topics, max_difficulty=max_diff, seed=seed)

grouped = st.session_state.generated

# Ensure topic order stays as selected
ordered_topics = [t for t in topics if t in grouped]

# UI: each topic row has two columns
for topic in ordered_topics:
    st.markdown(f"### {topic}")
    qs = grouped.get(topic, [])
    if len(qs) < 2:
        st.info("Not enough templates found for this topic at the selected difficulty.")
        continue

    c1, c2 = st.columns(2, gap="large")
    for col, idx in [(c1, 0), (c2, 1)]:
        q = qs[idx]
        with col:
            # prompt
            st.markdown(f"**{q.prompt}**")
            if q.latex.strip():
                st.latex(q.latex)

            # Buttons
            btn_row = st.columns(2)
            regen_key = f"regen_{q.qid}"
            work_key = f"work_{q.qid}"

            if work_key not in st.session_state:
                st.session_state[work_key] = False

            with btn_row[0]:
                if st.button("New version", key=regen_key):
                    new_seed = random.randint(1, 10**9)
                    new_q = regenerate_question(topic=topic, template_id=q.template_id, max_difficulty=max_diff, new_seed=new_seed)
                    grouped[topic][idx] = new_q
                    st.session_state.generated = grouped
                    st.rerun()

            with btn_row[1]:
                label = "Hide working" if st.session_state[work_key] else "Show working"
                if st.button(label, key=f"toggle_{q.qid}"):
                    st.session_state[work_key] = not st.session_state[work_key]
                    st.rerun()

            # Working
            if st.session_state[work_key]:
                st.markdown("**Working:**")
                for kind, content in q.working:
                    if kind == "text":
                        st.markdown(f"- {content}")
                    else:
                        st.latex(content)

            # Answer (collapsed)
            with st.expander("Answer"):
                st.latex(q.answer_latex)

    st.divider()

# PDF export
pdf_title = "Mixed topics" if len(ordered_topics) > 1 else ordered_topics[0]
pdf_bytes = build_pdf_bytes(title=pdf_title, grouped={t: grouped[t] for t in ordered_topics}, seed=seed)

st.download_button(
    label="Download PDF (Questions + Answers)",
    data=pdf_bytes,
    file_name="worksheet.pdf",
    mime="application/pdf",
)
