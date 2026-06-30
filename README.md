# AutoInsight — Conversational AI Data Analyst Agent

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-app-ff4b4b.svg)](https://streamlit.io/)
[![Checks](https://img.shields.io/badge/self--checks-passing-brightgreen.svg)](tests/selfcheck.py)

Ask a dataset questions in plain English and get **verified** answers with charts.
AutoInsight interprets the question, writes and executes the analysis, generates a
visualization, and **independently re-computes every headline number before showing
it** — so the answers are auditable, not hallucinated.

> **Live demo:** _add your https://….streamlit.app link here after deploying_

**Sample dataset:** Olist Brazilian e-commerce — 99,441 orders, Sept 2016 → Oct 2018,
27 states, 74 product categories (joined from 9 raw tables).

---

## What it does

Open the app, click **Try sample data**, and ask things like:

- "What are the top 5 states by revenue?"
- "Which product categories have the worst review scores?"
- "Show revenue trends over time"
- "Are there anomalies in monthly revenue?"
- "Does delivery delay affect review score?"

Each answer returns a plain-language insight, an interactive Plotly chart, the
underlying table, and a **✓ validated** badge showing the independent recompute.

## Why it's different from a chatbot

| Production concern | How AutoInsight handles it |
|---|---|
| **Hallucinated numbers** | A validator recomputes every headline via a *separate code path*; mismatches are flagged, not shown as trusted. |
| **Works without paid APIs** | A deterministic intent router answers top-N / trend / anomaly / correlation / segment questions with **zero API keys**. An LLM key only upgrades the narrative wording. |
| **Data integrity** | Ingestion self-checks assert row counts, join totals (item price & payments reconcile to the raw files to the cent), and value ranges before anything is served. |
| **Memory** | Conversation + loaded data persist in session state for follow-up questions. |

## Architecture

```
User question
   │
   ▼
Intent Router ──► Analyst Node ──► Execute (pandas) ──► Validator ──► Narrative ──► Chart ──► Answer
(deterministic        (top-N, trend,                    (independent
 + LLM-optional)       anomaly, corr,                    recompute;
                       segment)                          flag on mismatch)
```

Full diagram: [`docs/architecture.mermaid`](docs/architecture.mermaid).
Design rationale (LangGraph vs CrewAI): [`docs/ADR-001-orchestration.md`](docs/ADR-001-orchestration.md).

## Data pipeline

`insight_agent/ingest.py` joins the 9 raw Olist tables into one order-level master
table. Engineered features turn a transactional dump into an analytical surface:

- `delivery_days`, `delivery_delay_days`, `on_time` (order vs. delivery vs. estimate)
- order-level `total_price`, `total_freight`, `payment_value`, `n_items`, `max_installments`
- `main_category` (English), `main_payment_type`, `review_score`
- time features: year, month, quarter, day-of-week

**Self-checks (run on every build):** row count == distinct orders; summed item
price and payment value reconcile to the raw files; review scores in [1, 5];
timestamps fully parsed.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The cleaned sample table is bundled in `sample_data/`, so it runs out of the box.
To rebuild it from the raw Olist CSVs:

```bash
python insight_agent/ingest.py /path/to/olist_csvs sample_data/olist_master.csv.gz
```

## Verify

```bash
python tests/selfcheck.py
```

Runs a battery of natural-language questions and cross-checks each agent answer
against an independent pandas ground truth (top revenue state, worst-review
category, delay↔review correlation). Exits non-zero on any mismatch.

## Deploy (Streamlit Community Cloud — free)

1. Push this folder to a public GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** → pick the repo,
   branch `main`, main file `app.py`.
3. Click **Deploy**. You get a public `https://<name>.streamlit.app` URL — no login
   required for visitors.
4. *(Optional)* To enable richer LLM narration, add a secret in the app's
   **Settings → Secrets**:
   ```toml
   GROQ_API_KEY = "your_free_groq_key"
   ```

## Tech

Python · pandas · NumPy · Plotly · Streamlit · deterministic intent routing with
optional Groq/OpenAI LLM layer · validation-gated agent flow.

## Limitations & roadmap

- Orders spanning multiple categories use the dominant category (documented simplification).
- Upload path expects the prepared master schema; arbitrary-CSV profiling is a roadmap item.
- Next: LangGraph checkpointed memory, an eval suite scoring insight quality +
  hallucination rate, and cost/latency logging.
