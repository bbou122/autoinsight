"""
AutoInsight — conversational + interactive AI data-analyst (Streamlit).
Created by Braden Bourgeois · LSU.  Run: streamlit run app.py
"""
import os
import streamlit as st
import pandas as pd
from insight_agent.ingest import load_master, SCHEMA
from insight_agent import agent, explore

st.set_page_config(page_title="AutoInsight — AI Data Analyst", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {max-width: 1180px; padding-top: 1.2rem;}
html, body, [class*="css"] {font-family: Inter, system-ui, sans-serif;}
.hero {background: linear-gradient(120deg,#1e3a8a 0%,#2563eb 55%,#0ea5e9 100%);
       border-radius:18px; padding:26px 30px; color:#fff; margin-bottom:8px;
       box-shadow:0 10px 30px rgba(37,99,235,.25);}
.hero h1 {margin:0; font-size:2.1rem; font-weight:800; letter-spacing:-.5px;}
.hero p {margin:.35rem 0 0; font-size:1.02rem; opacity:.92;}
.hero .by {margin-top:.6rem; font-size:.8rem; opacity:.8; letter-spacing:.03em;}
.kpi {background:#fff;border:1px solid #e6eaf0;border-radius:14px;padding:14px 16px;text-align:left;
      box-shadow:0 1px 2px rgba(16,24,40,.04);}
.kpi .v {font-size:1.5rem;font-weight:800;color:#0f172a;line-height:1.1;}
.kpi .l {font-size:.72rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-top:2px;}
.badge-ok {background:#dcfce7;color:#166534;padding:3px 10px;border-radius:999px;font-size:.74rem;font-weight:700;}
.badge-no {background:#fee2e2;color:#991b1b;padding:3px 10px;border-radius:999px;font-size:.74rem;font-weight:700;}
.story {color:#475569;font-size:.9rem;margin:-6px 2px 14px;}
.foot {text-align:center;color:#94a3b8;font-size:.82rem;margin-top:26px;padding-top:14px;border-top:1px solid #e6eaf0;}
.foot b {color:#475569;}
div[data-testid="stMetricValue"] {font-size:1.4rem;}
</style>
""", unsafe_allow_html=True)

SAMPLE = os.path.join(os.path.dirname(__file__), "sample_data", "olist_master.csv.gz")
SUGGESTIONS = [
    "Top 5 states by revenue",
    "Worst product categories by review score",
    "In São Paulo, revenue by product category",
    "What state made the most revenue in January 2018?",
    "Does delivery delay affect review score?",
    "Revenue trend over time",
]


@st.cache_data(show_spinner="Loading Olist dataset…")
def get_sample():
    return load_master(SAMPLE)


def kpi_row(d):
    cols = st.columns(5)
    vals = [("Orders", f"{len(d):,}"),
            ("Revenue", f"R${d['payment_value'].sum()/1e6:.1f}M"),
            ("Avg order", f"R${d['payment_value'].mean():,.0f}"),
            ("Avg review", f"{d['review_score'].mean():.2f}★"),
            ("On-time", f"{d['on_time'].mean()*100:.0f}%")]
    for c, (l, v) in zip(cols, vals):
        c.markdown(f"<div class='kpi'><div class='v'>{v}</div><div class='l'>{l}</div></div>",
                   unsafe_allow_html=True)


def render_result(res):
    st.markdown(res.headline)
    if res.intent not in ("help",):
        badge = ('<span class="badge-ok">✓ validated</span>' if res.check["passed"]
                 else '<span class="badge-no">⚠ check failed</span>')
        st.markdown(f"{badge} &nbsp;<span class='story'>independent recompute → {res.check['detail']}</span>",
                    unsafe_allow_html=True)
    if res.figure is not None:
        st.plotly_chart(res.figure, use_container_width=True)
    if res.table is not None and len(res.table):
        st.dataframe(res.table, use_container_width=True, hide_index=True)


# ---------- state + auto-load sample (zero friction) ----------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("queued", None)
if "df" not in st.session_state:
    st.session_state.df = get_sample()
df = st.session_state.df

with st.sidebar:
    st.markdown("## 📊 AutoInsight")
    st.caption("An AI data-analyst agent. Ask in plain English or explore interactively — "
               "every answer is independently re-computed before you see it.")
    st.markdown("**Dataset:** Olist Brazilian e-commerce · 99k orders · 2016–2018")
    up = st.file_uploader("Upload a prepared CSV (optional)", type=["csv", "gz"])
    if up is not None:
        try:
            d = pd.read_csv(up)
            d["order_purchase_timestamp"] = pd.to_datetime(d.get("order_purchase_timestamp"), errors="coerce")
            st.session_state.df = d
            st.session_state.messages = []
            st.success(f"Loaded {len(d):,} rows.")
            df = d
        except Exception as e:
            st.error(f"Could not read file: {e}")
    if st.button("↺ Reset to sample data", use_container_width=True):
        st.session_state.df = get_sample()
        st.session_state.messages = []
        st.rerun()
    st.divider()
    has_key = bool(os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"))
    st.caption("🟢 LLM narrative: ON" if has_key else
               "⚪ LLM narrative: OFF — fully functional without a key (set GROQ_API_KEY for richer wording).")
    st.caption("Created by **Braden Bourgeois** · LSU")

st.markdown(
    "<div class='hero'><h1>AutoInsight</h1>"
    "<p>A conversational + interactive AI data analyst. Ask anything, or explore the story in the data.</p>"
    "<div class='by'>Created by Braden Bourgeois · LSU</div></div>",
    unsafe_allow_html=True)

tab_ask, tab_explore, tab_dict = st.tabs(["💬  Ask the agent", "📊  Explore dashboard", "📖  Data dictionary"])

# ============================ ASK ============================
with tab_ask:
    st.markdown("<span class='story'>Try one:</span>", unsafe_allow_html=True)
    chips = st.columns(3)
    for i, s in enumerate(SUGGESTIONS):
        if chips[i % 3].button(s, key=f"chip{i}", use_container_width=True):
            st.session_state.queued = s

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.markdown(m["content"])
            else:
                render_result(m["result"])

    with st.form("ask_form", clear_on_submit=True):
        c1, c2 = st.columns([8, 1])
        typed = c1.text_input("q", label_visibility="collapsed",
                              placeholder="e.g. In São Paulo, revenue by product category in 2018")
        sent = c2.form_submit_button("Ask ➤", use_container_width=True)
    q = (typed if (sent and typed) else None) or st.session_state.queued
    if q:
        st.session_state.queued = None
        st.session_state.messages.append({"role": "user", "content": q})
        res = agent.answer(st.session_state.df, q, SCHEMA)
        st.session_state.messages.append({"role": "assistant", "result": res})
        st.rerun()

# ========================== EXPLORE ==========================
with tab_explore:
    fc1, fc2 = st.columns(2)
    states = sorted(df["customer_state"].dropna().unique().tolist())
    years = sorted(int(y) for y in df["purchase_year"].dropna().unique())
    sel_states = fc1.multiselect("Filter by state (blank = all of Brazil)", states, default=[])
    sel_years = fc2.multiselect("Filter by year (blank = all)", years, default=[])
    f = df
    if sel_states:
        f = f[f["customer_state"].isin(sel_states)]
    if sel_years:
        f = f[f["purchase_year"].isin(sel_years)]
    if len(f) == 0:
        st.warning("No orders match those filters.")
    else:
        kpi_row(f)
        st.write("")

        d, fig = explore.revenue_trend(f)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        growth = (d["Revenue"].iloc[-1] - d["Revenue"].iloc[0]) / abs(d["Revenue"].iloc[0]) * 100 if len(d) > 1 and d["Revenue"].iloc[0] else 0
        st.markdown(f"<div class='story'>📈 <b>Growth story:</b> revenue moved {growth:+.0f}% from the first to the last month in view.</div>", unsafe_allow_html=True)

        g1, g2 = st.columns(2)
        d1, f1 = explore.revenue_by_category(f, 10)
        d2, f2 = explore.revenue_by_state(f, 10)
        with g1:
            if f1 is not None:
                st.plotly_chart(f1, use_container_width=True)
            st.markdown(f"<div class='story'>🛍️ <b>{d1.iloc[0]['Category']}</b> is the top category by revenue.</div>", unsafe_allow_html=True)
        with g2:
            if f2 is not None:
                st.plotly_chart(f2, use_container_width=True)
            st.markdown(f"<div class='story'>📍 <b>{d2.iloc[0]['State']}</b> leads all states in revenue.</div>", unsafe_allow_html=True)

        p1, p2 = st.columns(2)
        with p1:
            cats = explore.category_list(f, 12)
            inc_cats = st.multiselect("Categories in pie", cats, default=cats[:8])
            dc, fc = explore.category_share_pie(f, include=inc_cats or None, n=8)
            if fc is not None:
                st.plotly_chart(fc, use_container_width=True)
            st.markdown("<div class='story'>🥧 Revenue concentration across categories — toggle slices above.</div>", unsafe_allow_html=True)
        with p2:
            pts = explore.payment_types(f)
            inc_pts = st.multiselect("Payment methods in pie", pts, default=pts)
            dp, fp = explore.payment_mix_pie(f, include=inc_pts or None)
            if fp is not None:
                st.plotly_chart(fp, use_container_width=True)
            lead_pay = dp.iloc[0]["Payment type"] if len(dp) else "—"
            st.markdown(f"<div class='story'>💳 <b>{lead_pay}</b> drives the most revenue.</div>", unsafe_allow_html=True)

        ds, fs = explore.satisfaction_by_delivery(f)
        if fs is not None:
            st.plotly_chart(fs, use_container_width=True)
        try:
            late = ds.loc[ds.Delivery == "Late", "Avg review"].iloc[0]
            ont = ds.loc[ds.Delivery == "On-time / early", "Avg review"].iloc[0]
            st.markdown(f"<div class='story'>⭐ <b>Satisfaction driver:</b> late orders average {late:.2f}★ vs {ont:.2f}★ when on-time — delivery is the lever.</div>", unsafe_allow_html=True)
        except Exception:
            pass

# ======================== DICTIONARY =========================
with tab_dict:
    st.subheader("Data dictionary")
    st.caption("Ask about any **measure**, broken down by any **dimension**, optionally filtered by a "
               "**Brazilian state** and/or a **time period**. Currency is Brazilian reais (R$).")
    st.dataframe(agent.dictionary_df(), use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Example questions**")
        for q in agent.EXAMPLE_QUESTIONS:
            st.markdown(f"- {q}")
    with c2:
        st.markdown("**Notes**")
        st.markdown(
            "- This is the **Olist** Brazilian e-commerce dataset (99,441 orders, Sep 2016 – Oct 2018).\n"
            "- States are Brazilian — e.g. **SP** São Paulo, **RJ** Rio de Janeiro, **MG** Minas Gerais.\n"
            "- Every chat answer is **independently re-computed** and shown with a ✓ validated badge.\n"
            "- Time phrases like *in 2017*, *January 2018*, or *Q3 2018* filter automatically.")

st.markdown("<div class='foot'>Created by <b>Braden Bourgeois</b> · LSU &nbsp;·&nbsp; "
            "AutoInsight — AI Data Analyst Agent &nbsp;·&nbsp; Data: Olist (Brazil)</div>",
            unsafe_allow_html=True)
