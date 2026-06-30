"""AutoInsight — intent router (deterministic; LLM-optional) with time + state filtering."""
from __future__ import annotations
import re

MEASURE_SYNONYMS = {
    "payment_value": ["revenue", "sales", "payment", "spend", "spent", "amount", "gmv", "money", "value", "made"],
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
              "worst", "lowest", "least", "bottom", "biggest", "largest", "made the most"],
    "segment_compare": ["compare", "breakdown", "across", "difference between", " by "],
    "summary": ["summary", "overview", "describe", "tell me about", "profile", "snapshot"],
}
HELP_PHRASES = ["what can i ask", "what can you do", "data dictionary", "what questions",
                "what columns", "what fields", "what data", "help me ask", "examples",
                "what do you know"]
MEAN_MEASURES = {"review_score", "delivery_days", "delivery_delay_days", "max_installments"}
_ASC_WORDS = ["worst", "lowest", "least", "bottom", "smallest", "fewest", "slowest"]
_AGG_WORDS = {"average": "mean", "avg": "mean", "mean": "mean", "median": "median",
              "total": "sum", "sum": "sum", "count": "count", "number of": "count"}
MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
          "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
          "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
          "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
_MONTH_NAME = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
               7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}


def parse_time_filter(question: str):
    """Detect a year / month / quarter filter in the question. Returns dict or None."""
    q = " " + question.lower() + " "
    year = None
    ym = re.search(r"\b(20\d\d)\b", q)
    if ym:
        year = int(ym.group(1))
    month = None
    for name, num in MONTHS.items():
        if re.search(r"\b" + name + r"\b", q):
            month = num
            break
    qm = re.search(r"\bq([1-4])\b", q)
    quarter = int(qm.group(1)) if qm else None
    if not (year or month or quarter):
        return None
    parts = []
    if quarter:
        parts.append(f"Q{quarter}")
    if month:
        parts.append(_MONTH_NAME[month])
    if year:
        parts.append(str(year))
    return {"year": year, "month": month, "quarter": quarter, "label": " ".join(parts)}


def _find(text, synonyms):
    hits = []
    for canon, syns in synonyms.items():
        for s in [canon.replace("_", " ")] + syns:
            if re.search(r"\b" + re.escape(s) + r"\b", text):
                hits.append((canon, len(s)))
                break
    return [c for c, _ in sorted(hits, key=lambda x: -x[1])]


def parse(question: str, schema: dict) -> dict:
    q = " " + question.lower().strip() + " "
    if any(p in q for p in HELP_PHRASES):
        return {"intent": "help", "params": {}}

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
        min_count = 30 if default_agg == "mean" else 0
        return {"intent": "top_n",
                "params": {"dimension": dim, "measure": measure, "agg": default_agg,
                           "n": n, "ascending": ascending, "min_count": min_count}}

    return {"intent": "summary", "params": {}}


# ---- geographic filtering (Olist = Brazil; 27 states) ----
BR_STATES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}
# ascii lowercase name -> code (so "sao paulo" / "são paulo" both match)
_BR_NAME_TO_CODE = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso do sul": "MS", "mato grosso": "MT", "minas gerais": "MG",
    "para": "PA", "paraiba": "PB", "parana": "PR", "pernambuco": "PE", "piaui": "PI",
    "rio de janeiro": "RJ", "rio grande do norte": "RN", "rio grande do sul": "RS",
    "rondonia": "RO", "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP",
    "sergipe": "SE", "tocantins": "TO",
}
US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "ohio",
    "oklahoma", "oregon", "pennsylvania", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "wisconsin", "wyoming",
}


def _strip_accents(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def parse_state_filter(question: str):
    """Match a Brazilian state (full name or 2-letter code). Flags US states as not-in-data."""
    ql = _strip_accents(question.lower())
    for name in sorted(_BR_NAME_TO_CODE, key=len, reverse=True):
        if re.search(r"\b" + re.escape(name) + r"\b", ql):
            code = _BR_NAME_TO_CODE[name]
            return {"state": code, "name": BR_STATES[code]}
    m = re.search(r"\b(" + "|".join(BR_STATES) + r")\b", question)
    if m:
        code = m.group(1)
        return {"state": code, "name": BR_STATES[code]}
    for us in US_STATES:
        if re.search(r"\b" + re.escape(us) + r"\b", ql):
            return {"unknown_state": us.title()}
    return None
