"""
AutoInsight — intent router.

Maps a natural-language question to a tool call. Deterministic by default
(works with NO API key), so the demo never hard-fails. If GROQ_API_KEY or
OPENAI_API_KEY is set, the agent layer can additionally use an LLM for narrative.
"""
from __future__ import annotations
import re

MEASURE_SYNONYMS = {
    "payment_value": ["revenue", "sales", "payment", "spend", "spent", "amount", "gmv", "money", "value"],
    "total_price": ["price", "product price", "item price"],
    "total_freight": ["freight", "shipping cost", "delivery cost", "shipping fee"],
    "delivery_days": ["delivery time", "delivery speed", "shipping time", "days to deliver", "how long", "delivery days"],
    "delivery_delay_days": ["delay", "late", "lateness", "behind schedule", "delivery delay"],
    "review_score": ["review", "rating", "ratings", "score", "satisfaction", "stars", "reviews"],
    "n_items": ["items", "basket size", "quantity", "number of items", "order size"],
    "max_installments": ["installments", "installment"],
}
DIM_SYNONYMS = {
    "customer_state": ["state", "states", "region", "regions", "geography", "location", "where"],
    "main_category": ["category", "categories", "product type", "product category", "products"],
    "main_payment_type": ["payment type", "payment method", "payment types", "how they paid"],
    "order_status": ["status", "order status"],
    "purchase_year": ["year", "yearly", "annual"],
    "purchase_dow": ["day of week", "weekday", "day of the week"],
}
INTENT_KEYWORDS = {
    "trend": ["trend", "over time", "monthly", "by month", "timeline", "time series",
              "growth", "seasonality", "each month", "per month", "trajectory", "evolution"],
    "anomaly": ["anomaly", "anomalies", "outlier", "outliers", "unusual", "spike",
                "abnormal", "strange", "weird", "irregular"],
    "correlation": ["correlat", "relationship", "related", "driver", "drives", "predict",
                    "associat", "versus", " vs ", "affect", "impact", "influence"],
    "top_n": ["top", "best", "highest", "most", "leading", "rank", "ranking",
              "worst", "lowest", "least", "bottom", "biggest", "largest"],
    "segment_compare": ["compare", "breakdown", "across", "difference between", " by "],
    "summary": ["summary", "overview", "describe", "tell me about", "profile", "snapshot"],
}
# measures that should default to MEAN (not SUM) when ranking/comparing
MEAN_MEASURES = {"review_score", "delivery_days", "delivery_delay_days", "max_installments"}
_ASC_WORDS = ["worst", "lowest", "least", "bottom", "smallest", "fewest", "slowest"]
_AGG_WORDS = {"average": "mean", "avg": "mean", "mean": "mean", "median": "median",
              "total": "sum", "sum": "sum", "count": "count", "number of": "count"}


def _find(text, synonyms):
    """Return canonical keys whose synonyms appear in text, longest match first."""
    hits = []
    for canon, syns in synonyms.items():
        for s in [canon.replace("_", " ")] + syns:
            if re.search(r"\b" + re.escape(s) + r"\b", text):
                hits.append((canon, len(s)))
                break
    return [c for c, _ in sorted(hits, key=lambda x: -x[1])]


def parse(question: str, schema: dict) -> dict:
    q = " " + question.lower().strip() + " "
    measures = _find(q, MEASURE_SYNONYMS)
    dims = _find(q, DIM_SYNONYMS)

    agg = None
    for w, a in _AGG_WORDS.items():
        if w in q:
            agg = a
            break

    intent = None
    for it in ["correlation", "anomaly", "trend", "top_n", "segment_compare", "summary"]:
        if any(k in q for k in INTENT_KEYWORDS[it]):
            intent = it
            break

    primary = schema.get("primary_measure", "payment_value")
    measure = measures[0] if measures else primary

    if intent == "correlation":
        a = measures[0] if len(measures) >= 1 else "delivery_days"
        b = measures[1] if len(measures) >= 2 else "review_score"
        if a == b:
            b = "review_score" if a != "review_score" else "delivery_days"
        return {"intent": "correlation", "params": {"measure_a": a, "measure_b": b}}

    default_agg = agg or ("mean" if measure in MEAN_MEASURES else "sum")

    if intent in ("anomaly", "trend"):
        return {"intent": intent, "params": {"measure": measure, "agg": default_agg}}

    if intent in ("top_n", "segment_compare") or (dims and not intent):
        dim = dims[0] if dims else "main_category"
        ascending = any(w in q for w in _ASC_WORDS)
        n = 10
        mnum = re.search(r"\btop (\d+)|\bbottom (\d+)|\b(\d+) (?:states|categories|products)", q)
        if mnum:
            n = int(next(g for g in mnum.groups() if g))
        chosen = intent or "top_n"
        if chosen == "segment_compare":
            return {"intent": "segment_compare",
                    "params": {"dimension": dim, "measure": measure, "agg": default_agg}}
        # require a minimum sample per group when ranking by an average
        min_count = 30 if default_agg == "mean" else 0
        return {"intent": "top_n",
                "params": {"dimension": dim, "measure": measure, "agg": default_agg,
                           "n": n, "ascending": ascending, "min_count": min_count}}

    return {"intent": "summary", "params": {}}
