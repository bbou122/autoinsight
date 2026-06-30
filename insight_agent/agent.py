"""AutoInsight — orchestrator: time + state filtering, help/dictionary, validation."""
from __future__ import annotations
import os
import pandas as pd
from . import tools, router
from .ingest import SCHEMA

FIELDS = [
    ("payment_value", "measure", "Total amount paid per order (R$ Brazilian reais)", "revenue / sales / money"),
    ("total_price", "measure", "Product price subtotal per order (R$)", "price"),
    ("total_freight", "measure", "Shipping cost per order (R$)", "freight / shipping cost"),
    ("delivery_days", "measure", "Days from purchase to delivery", "delivery time"),
    ("delivery_delay_days", "measure", "Days late vs. estimate (+ = late)", "delay / lateness"),
    ("review_score", "measure", "Customer rating, 1-5 stars", "review / rating"),
    ("n_items", "measure", "Items per order", "items / basket size"),
    ("max_installments", "measure", "Payment installments", "installments"),
    ("customer_state", "dimension", "Brazilian state: SP, RJ, MG ... (full names work too)", "state / region"),
    ("main_category", "dimension", "Product category (English)", "category / product"),
    ("main_payment_type", "dimension", "credit_card, boleto, voucher, debit", "payment method"),
    ("order_status", "dimension", "delivered, shipped, canceled, ...", "status"),
    ("purchase_year / month / day-of-week", "time", "When the order was placed (2016-2018)", "year / month / weekday"),
]
EXAMPLE_QUESTIONS = [
    "Top 5 states by revenue",
    "Which product categories have the worst review scores?",
    "Show revenue trends over time",
    "Are there anomalies in monthly revenue?",
    "Does delivery delay affect review score?",
    "In São Paulo, revenue by product category",
    "What state made the most revenue in January 2018?",
    "Top categories by revenue in 2017",
]


def dictionary_df() -> pd.DataFrame:
    return pd.DataFrame(FIELDS, columns=["Field", "Type", "Description", "Ask using words like"])


def _result(intent, head, table=None, fig=None, ok=True, detail="reference", params=None):
    return tools.Result(intent, head, table if table is not None else pd.DataFrame(),
                        fig, {"passed": ok, "detail": detail}, params or {})


def _help_result() -> tools.Result:
    head = ("**Here's what I can analyze.** Pick any **measure**, break it down by any "
            "**dimension**, and (optionally) filter by a **Brazilian state** and/or a **time period** "
            "— e.g. *\"In São Paulo, revenue by category in 2018\"*.")
    return _result("help", head, dictionary_df())


def _apply_time_filter(df, tf):
    ts = df["order_purchase_timestamp"]
    m = pd.Series(True, index=df.index)
    if tf.get("year"):
        m &= ts.dt.year == tf["year"]
    if tf.get("month"):
        m &= ts.dt.month == tf["month"]
    if tf.get("quarter"):
        m &= ts.dt.quarter == tf["quarter"]
    return df[m]


def _summary(df) -> tools.Result:
    rev = df["payment_value"].sum()
    kpis = pd.DataFrame({
        "Metric": ["Orders", "Revenue", "Avg order value", "Avg review",
                   "Avg delivery", "On-time %", "Categories", "States"],
        "Value": [
            f"{len(df):,}", f"R${rev:,.0f}", f"R${df['payment_value'].mean():,.0f}",
            f"{df['review_score'].mean():.2f} stars", f"{df['delivery_days'].mean():.1f} days",
            f"{df['on_time'].mean()*100:.0f}%", f"{df['main_category'].nunique()}",
            f"{df['customer_state'].nunique()}",
        ],
    })
    res = tools.trend(df, "payment_value", "sum")
    res.intent = "summary"
    res.table = kpis
    res.headline = (f"**{len(df):,} orders**, **R${rev:,.0f}** revenue, avg review "
                    f"**{df['review_score'].mean():.2f} stars**, **{df['on_time'].mean()*100:.0f}%** on-time. "
                    "Ask about trends, anomalies, categories, states, delivery, reviews "
                    "— or type *what can I ask?*")
    return res


_DISPATCH = {
    "top_n": tools.top_n, "trend": tools.trend, "anomaly": tools.anomaly,
    "correlation": tools.correlation, "segment_compare": tools.segment_compare,
}


def answer(df: pd.DataFrame, question: str, schema: dict = SCHEMA) -> tools.Result:
    plan = router.parse(question, schema)
    intent, params = plan["intent"], plan["params"]
    if intent == "help":
        return _help_result()

    work, parts = df, []

    # geographic filter
    sf = router.parse_state_filter(question)
    if sf and sf.get("unknown_state"):
        return _result("summary",
                       f"**{sf['unknown_state']}** isn't in this dataset — Olist covers **27 Brazilian "
                       "states** (e.g. **SP** São Paulo, **RJ** Rio de Janeiro, **MG** Minas Gerais). "
                       "Try one of those, or ask *compare revenue by state* to see them all.")
    if sf and sf.get("state"):
        work = work[work["customer_state"] == sf["state"]]
        parts.append(f"{sf['name']} ({sf['state']})")

    # time filter
    tf = router.parse_time_filter(question)
    if tf:
        work = _apply_time_filter(work, tf)
        parts.append(tf["label"])

    if ((sf and sf.get("state")) or tf) and len(work) == 0:
        return _result("summary",
                       f"No orders found for **{' · '.join(parts)}**. The data covers 27 Brazilian "
                       "states, Sep 2016 - Oct 2018.")
    prefix = f"In {' · '.join(parts)}: " if parts else ""

    if intent == "summary":
        res = _summary(work)
        res.headline = prefix + res.headline if prefix else res.headline
        return res
    try:
        res = _DISPATCH[intent](work, **params)
    except Exception as e:
        res = _summary(work)
        res.headline = (f"I couldn't compute that one cleanly ({type(e).__name__}). "
                        "Here's an overview — try a measure (revenue, review, delivery) and a "
                        "dimension (state, category). Type *what can I ask?* for options.")
        res.check = {"passed": False, "detail": str(e)}
        return res
    res.headline = prefix + res.headline
    res.headline = _maybe_llm(question, res) or res.headline
    return res


def _maybe_llm(question: str, res: tools.Result):
    """Upgrade the narrative with an LLM if a key is present. Safe no-op otherwise."""
    key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        facts = res.table.head(8).to_string(index=False)
        prompt = (f"You are a senior data analyst. Question: {question}\n"
                  f"Verified result: {res.headline}\nData:\n{facts}\n"
                  "Write 2 concise sentences of business insight. Use only these numbers.")
        if os.getenv("GROQ_API_KEY"):
            from groq import Groq
            c = Groq(api_key=os.getenv("GROQ_API_KEY"))
            r = c.chat.completions.create(model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=160)
        else:
            from openai import OpenAI
            c = OpenAI()
            r = c.chat.completions.create(model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=160)
        return r.choices[0].message.content.strip()
    except Exception:
        return None  # never break the answer on LLM failure
