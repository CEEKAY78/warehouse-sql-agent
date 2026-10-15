"""Streamlit front end: question -> SQL -> result table -> grounded answer, with RAG sources.

    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from wsa.cli import DEFAULT_MODEL, RAG, WAREHOUSE, make_agent  # noqa: E402
from wsa.jsonl import read_jsonl  # noqa: E402

MODELS = ["qwen2.5-coder:7b", "qwen2.5:7b-instruct", "qwen3:8b"]
EXAMPLE_QUESTIONS = [
    "Which 5 countries had the highest net revenue?",
    "How many new customers did the shop get in 2011?",
    "What was the net revenue in each quarter of 2011?",
    "What was the gross margin in 2011?",
]

st.set_page_config(page_title="Warehouse SQL agent", layout="wide")
st.title("Warehouse SQL agent")
st.caption("A local LLM (Ollama) answers business questions with SQL over a DuckDB star schema "
           "built from UCI Online Retail II. Read-only, guarded, every number checked.")

if not WAREHOUSE.exists():
    st.error("No warehouse yet: run `python scripts/build_warehouse.py` first.")
    st.stop()

with st.sidebar:
    model = st.selectbox("Model", MODELS, index=MODELS.index(DEFAULT_MODEL))
    use_rag = st.toggle("RAG (glossary + similar examples)", value=True)
    st.markdown("**Try:**")
    for q in EXAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True):
            st.session_state["question"] = q
    runs = sorted((ROOT / "eval" / "runs").glob("*.jsonl"))
    if runs:
        st.markdown("**Evaluation runs**")
        for path in runs:
            rows = read_jsonl(path, skip_broken=True)
            st.write(f"`{path.stem}`: {sum(r['correct'] for r in rows)}/{len(rows)}")


@st.cache_resource
def get_agent(model_name: str, rag: bool):
    if rag and not RAG.exists():
        st.info("Building the RAG index (first run)...")
    return make_agent(model_name, rag)


question = st.text_input("Ask a question about the shop's sales", key="question")
if question:
    agent = get_agent(model, use_rag)
    with st.spinner(f"{model} is thinking..."):
        answer = agent.ask(question)
    if answer.refused:
        st.warning(f"Refused: {answer.text}")
    elif answer.result is None:
        st.error(f"The query failed after {answer.attempts} attempts: {answer.error}")
    else:
        (st.success if answer.grounded else st.warning)(answer.text)
    if answer.sql:
        st.code(answer.sql, language="sql")
    if answer.result is not None:
        st.dataframe(pd.DataFrame(answer.result.rows, columns=answer.result.columns),
                     use_container_width=True)
        if answer.result.truncated:
            st.caption(f"Showing the first {len(answer.result.rows)} rows only.")
    cols = st.columns(3)
    cols[0].metric("SQL attempts", answer.attempts)
    grounded = "n/a" if answer.result is None else ("yes" if answer.grounded else "no")
    cols[1].metric("Numbers grounded", grounded)
    cols[2].metric("Rows", len(answer.result.rows) if answer.result else 0)
    if answer.context_ids:
        st.caption("Retrieved context: " + ", ".join(answer.context_ids))
