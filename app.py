"""
AutoInsight — conversational data-analyst agent (Streamlit front-end).

Run locally:  streamlit run app.py
The manager flow: open -> "Try sample data" (or upload) -> ask in plain English
-> get a verified answer + chart in chat.
"""
import os
import streamlit as st
import pandas as pd

from insight_agent.ingest import load_master, SCHEMA
from insight_agent import agent

st.set_page_config(page_title="AutoInsight — AI Data Analyst",
                   page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# ---------- styling ----------
st.markdown("""
<style>
.block-container {max-width: 1080px; padding-top: 1.4rem;}
h1, h2, h3 {font-family: Inter, system-ui, sans-serif;}
.stChatMessage {border-radius: 14px;}
.kpi {background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:10px 14px;margin-bottom:8px;}
.kpi .v {font-size:1.35rem;font-weight:700;color:#0f172a;}
.kpi .l {font-size:.78rem;color:#64748b;text-transform:uppercase;letter-spacing:.04em;}
.badge-ok {background:#dcfce7;color:#166534;padding:3px 10px;border-radius:999px;font-size:.74rem;font-weight:600;}
.badge-no {background:#fee2e2;color:#991b1b;padding:3px 10px;border-radius:999px;font-size:.74rem;font-weight:600;}
.suggest {color:#475569;font-size:.9rem;}
</style>
""", unsafe_allow_html=True)

SAMPLE = os.path.join(os.path.dirname(__file__), "sample_data", "olist_master.csv.gz")
SUGGESTIONS = [
    "What are the top 5 states by revenue?",
    "Which product categories have the worst review scores?",
    "Show revenue trends over time",
    "Are there anomalies in monthly revenue?",
    "Does delivery delay affect review score?",
    "Compare average delivery time by state",
]


@st.cache_data(show_spinner="Loading dataset…")
def get_sample():
    return load_master(SAMPLE)


def ensure_state():
    st.session_state.setdefault("df", None)
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("queued", None)


def render_result(res):
    st.markdown(res.headline)
    badge = ('<span class="badge-ok">✓ validated</span>' if res.check["passed"]
             else '<span class="badge-no">⚠ check failed</span>')
    st.markdown(f"{badge} &nbsp;<span class='suggest'>independent recompute → {res.check['detail']}</span>",
                unsafe_allow_html=True)
    if res.figure is not None:
        st.plotly_chart(res.figure, use_container_width=True)
    if res.table is not None and len(res.table):
        st.dataframe(res.table, use_container_width=True, hide_index=True)


def run_question(q):
    st.session_state.messages.append({"role": "user", "content": q})
    res = agent.answer(st.session_state.df, q, SCHEMA)
    st.session_state.messages.append({"role": "assistant", "result": res})


# ---------- app ----------
ensure_state()

with st.sidebar:
    st.markdown("## 📊 AutoInsight")
    st.caption("An AI data-analyst agent. Ask questions in plain English; "
               "every answer is independently re-computed before you see it.")
    if st.button("▶  Try sample data (Olist e-commerce)", use_container_width=True, type="primary"):
        st.session_state.df = get_sample()
        st.session_state.messages = []
    up = st.file_uploader("…or upload a prepared CSV", type=["csv", "gz"])
    if up is not None:
        try:
            d = pd.read_csv(up)
            d["order_purchase_timestamp"] = pd.to_datetime(
                d.get("order_purchase_timestamp"), errors="coerce")
            st.session_state.df = d
            st.session_state.messages = []
            st.success(f"Loaded {len(d):,} rows.")
        except Exception as e:
            st.error(f"Could not read file: {e}")

    if st.session_state.df is not None:
        df = st.session_state.df
        st.divider()
        cols = st.columns(2)
        kpis = [("Orders", f"{len(df):,}"),
                ("Revenue", f"R${df['payment_value'].sum()/1e6:.1f}M"),
                ("Avg review", f"{df['review_score'].mean():.2f}★"),
                ("On-time", f"{df['on_time'].mean()*100:.0f}%")]
        for i, (l, v) in enumerate(kpis):
            cols[i % 2].markdown(f"<div class='kpi'><div class='v'>{v}</div><div class='l'>{l}</div></div>",
                                 unsafe_allow_html=True)
    st.divider()
    has_key = bool(os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"))
    st.caption(("🟢 LLM narrative: ON" if has_key else
                "⚪ LLM narrative: OFF (set GROQ_API_KEY to enable richer wording — "
                "the agent is fully functional without it)"))

st.title("AutoInsight")
st.markdown("##### Ask your data anything — trends, anomalies, segments, drivers.")

if st.session_state.df is None:
    st.info("👈 Click **Try sample data** to load the Olist e-commerce dataset "
            "(99k orders), then ask a question below.")
    st.markdown("**Example questions you can ask:**")
    for s in SUGGESTIONS:
        st.markdown(f"- {s}")
else:
    # suggestion chips
    st.markdown("<span class='suggest'>Try:</span>", unsafe_allow_html=True)
    chip_cols = st.columns(3)
    for i, s in enumerate(SUGGESTIONS):
        if chip_cols[i % 3].button(s, key=f"chip{i}", use_container_width=True):
            st.session_state.queued = s

    # replay history
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.markdown(m["content"])
            else:
                render_result(m["result"])

    typed = st.chat_input("Ask about revenue, reviews, delivery, categories, states…")
    q = typed or st.session_state.queued
    if q:
        st.session_state.queued = None
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("Analyzing…"):
                run_question(q)
            render_result(st.session_state.messages[-1]["result"])
