"""
Streamlit UI for the NL -> SQL engine.
Run with:  streamlit run app.py
"""
import logging
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # loads GEMINI_API_KEY from a .env file if present
logging.getLogger("google_genai.models").setLevel(logging.ERROR)  # hide harmless AFC notice

st.set_page_config(page_title="Ask your data", page_icon="🗄️", layout="wide")

# ---- pre-flight checks (before importing the engine, which needs the API key) ----------------
if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
    st.error("GEMINI_API_KEY not found. Create a `.env` file next to app.py containing "
             "`GEMINI_API_KEY=your-key`, then restart the app.")
    st.stop()

from nl2sql import ask, get_schema_text  # noqa: E402
from prompts import DB_REGISTRY          # noqa: E402

missing = [k for k, v in DB_REGISTRY.items() if not os.path.exists(v["path"])]
if missing:
    st.error(f"Database file(s) missing for: {', '.join(missing)}. Run `python seed_databases.py` first.")
    st.stop()

EXAMPLES = {
    "ecommerce": [
        "Top 5 customers by total spend in 2025 with their city",
        "Month-over-month revenue growth for 2025",
        "Which product categories have a return rate above the overall average?",
        "Best-selling product in each parent category",
    ],
    "hr": [
        "Active employees earning more than their department average",
        "Attrition rate per department in 2024",
        "Employees allocated more than 100% across active projects",
        "Average performance rating per department for 2025",
    ],
    "hospital": [
        "Top 5 doctors by no-show percentage",
        "Outstanding balance by insurance provider",
        "Most prescribed medicine for each severe diagnosis",
        "Monthly revenue collected in 2025",
    ],
}

# ---- session state ------------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # each: {"question": str, "result": dict}

# ---- sidebar ------------------------------------------------------------------------------------
with st.sidebar:
    st.title("🗄️ Ask your data")
    choice = st.selectbox("Database", ["Auto-detect"] + list(DB_REGISTRY))
    pinned = None if choice == "Auto-detect" else choice
    show_sql = st.toggle("Show generated SQL", value=True)

    if pinned:
        st.caption(DB_REGISTRY[pinned]["description"])
        with st.expander("View schema"):
            st.code(get_schema_text(pinned), language="sql")
        st.markdown("**Try one of these**")
        for i, ex in enumerate(EXAMPLES.get(pinned, [])):
            if st.button(ex, key=f"ex_{pinned}_{i}", width="stretch"):
                st.session_state.pending = ex
    else:
        st.caption("The app will pick the right database for each question.")

    if st.button("🧹 Clear conversation", width="stretch"):
        st.session_state.messages = []
        st.rerun()


# ---- rendering ----------------------------------------------------------------------------------
def render_result(result: dict, idx: int):
    status = result["status"]
    if status == "ok":
        st.caption(f"Database: **{result['database']}** — {result['interpretation']}")
        for a in result.get("assumptions") or []:
            st.info(f"Assumption: {a}")
        if show_sql:
            st.markdown("**Generated SQL**")
            st.code(result["sql"], language="sql")

        df = pd.DataFrame(result["rows"], columns=result["columns"])
        if df.empty:
            st.warning("The query ran successfully but returned no rows.")
            return
        st.dataframe(df, width="stretch", hide_index=True)
        note = f"{len(df)} row(s)"
        if result.get("truncated"):
            note += " (result capped — refine your question to narrow it)"
        if result.get("attempts", 1) > 1:
            note += f" · fixed automatically after {result['attempts'] - 1} retry"
        st.caption(note)

        c1, c2 = st.columns([1, 6])
        c1.download_button("⬇ CSV", df.to_csv(index=False).encode(), f"result_{idx}.csv", "text/csv",
                           key=f"dl_{idx}")
        numeric = df.select_dtypes("number").columns.tolist()
        if len(df.columns) >= 2 and 2 <= len(df) <= 60 and numeric and df.columns[0] not in numeric:
            with st.expander("Chart"):
                st.bar_chart(df.set_index(df.columns[0])[numeric[:1]])
    elif status == "clarification":
        st.warning(result["message"])
    elif status == "no_database":
        st.warning(result["message"])
    else:
        st.error("I couldn't produce a working query for that.")
        with st.expander("Details"):
            st.code(result.get("sql") or "", language="sql")
            st.write(result.get("error"))


st.header("Ask a question in plain English")
for i, m in enumerate(st.session_state.messages):
    with st.chat_message("user"):
        st.write(m["question"])
    with st.chat_message("assistant"):
        render_result(m["result"], i)

typed = st.chat_input("e.g. Which customers ordered in 2024 but not in 2025?")
question = st.session_state.pop("pending", None) or typed

if question:
    with st.chat_message("user"):
        st.write(question)
    history = [(m["question"], m["result"]["sql"])
               for m in st.session_state.messages if m["result"]["status"] == "ok"]
    with st.chat_message("assistant"):
        with st.spinner("Thinking and querying..."):
            try:
                result = ask(question, db_key=pinned, history=history)
            except Exception as e:  # network / API-key / quota problems
                result = {"status": "error", "sql": "", "error": f"Gemini API problem: {e}"}
        st.session_state.messages.append({"question": question, "result": result})
        render_result(result, len(st.session_state.messages) - 1)