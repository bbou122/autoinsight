"""
AutoInsight — orchestrator (the LangGraph-style flow, dependency-light).

answer() runs: route -> execute tool -> VALIDATE (independent recompute inside
each tool) -> optional LLM narrative. If validation fails the answer is flagged
rather than shown as trusted. Works with zero API keys; an LLM key only upgrades
the narrative wording.
"""

from __future__ import annotations
import os
import pandas as pd
from . import tools, router
from .ingest import SCHEMA


def _summary(df) -> tools.Result:
    rev = df["payment_value"].sum()
    kpis = pd.DataFrame({
        "Metric": ["Orders", "Revenue", "Avg order value", "Avg review",
                   "Avg delivery", "On-time %", "Categories", "States"],
        "Value": [
            f"{len(df):,}", f"R${rev:,.0f}",
            f"R${df['payment_value'].mean():,.0f}",
            f"{df['review_score'].mean():.2f}★",
            f"{df['delivery_days'].mean():.1f} days",
            f"{df['on_time'].mean()*100:.0f}%",
            f"{df['main_category'].nunique()}",
            f"{df['customer_state'].nunique()}",
        ],
    })
    res = tools.trend(df, "payment_value", "sum")
    res.intent = "summary"
    res.table = kpis
    res.headline = (f"**{len(df):,} orders**, **R${rev:,.0f}** revenue, avg review "
                    f"**{df['review_score'].mean():.2f}★**, **{df['on_time'].mean()*100:.0f}%** on-time. "
                    "Ask me about trends, anomalies, categories, states, delivery, or reviews.")
    return res


_DISPATCH = {
    "top_n": tools.top_n,
    "trend": tools.trend,
    "anomaly": tools.anomaly,
    "correlation": tools.correlation,
    "segment_compare": tools.segment_compare,
}


def answer(df: pd.DataFrame, question: str, schema: dict = SCHEMA) -> tools.Result:
    plan = router.parse(question, schema)
    intent, params = plan["intent"], plan["params"]
    if intent == "summary":
        return _summary(df)
    try:
        res = _DISPATCH[intent](df, **params)
    except Exception as e:
        res = _summary(df)
        res.headline = (f"I couldn't compute that one cleanly ({type(e).__name__}). "
                        "Here's an overview instead — try naming a measure (revenue, "
                        "review, delivery) and a dimension (state, category).")
        res.check = {"passed": False, "detail": str(e)}
        return res
    res.headline = _maybe_llm(question, res) or res.headline
    return res


def _maybe_llm(question: str, res: tools.Result) -> str | None:
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
            r = c.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=160)
        else:
            from openai import OpenAI
            c = OpenAI()
            r = c.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=160)
        return r.choices[0].message.content.strip()
    except Exception:
        return None  # never break the answer on LLM failure
