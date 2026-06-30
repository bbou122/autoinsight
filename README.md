# AutoInsight — Conversational + Interactive AI Data Analyst

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-app-ff4b4b.svg)](https://streamlit.io/)
[![Checks](https://img.shields.io/badge/self--checks-passing-brightgreen.svg)](tests/selfcheck.py)

<<<<<<< HEAD
**Created by Braden Bourgeois · LSU**

Ask a dataset questions in plain English **or** explore it through an interactive
dashboard. AutoInsight interprets each question, writes and executes the analysis,
generates a visualization, and **independently re-computes every headline number
before showing it** — so answers are auditable, not hallucinated.
=======
Ask a dataset questions in and get **verified** answers with charts.
AutoInsight interprets the question, writes and executes the analysis, generates a
visualization, and **independently re-computes every headline number before showing
it** — so the answers are auditable, not hallucinated.
>>>>>>> 58f142c0707f12ccd22a54218d6a7c041f058a04

> **Live demo:** https://autoinsight-pzhffkyupktlcevo2xbk32.streamlit.app/

**Sample dataset:** Olist Brazilian e-commerce — 99,441 orders, Sep 2016 → Oct 2018,
27 states, 74 product categories (joined from 9 raw tables). Currency is Brazilian reais (R$).

---

## Three ways to use it

**💬 Ask the agent** — type a question and get a verified answer, chart, and table:

- "Top 5 states by revenue"
- "Which product categories have the worst review scores?"
- "In São Paulo, revenue by product category in 2018"
- "What state made the most revenue in January 2018?"
- "Does delivery delay affect review score?"

It understands **measures**, **dimensions**, **Brazilian states** (code or full name,
e.g. `SP` / *São Paulo*), and **time periods** (`in 2017`, `January 2018`, `Q3 2018`).
Ask a US state and it tells you the data is Brazilian instead of silently ignoring it.

**📊 Explore dashboard** — filter by state and year, then read the story in the data
through linked charts: revenue growth over time, top categories and states, two
**filterable pie charts** (category share and payment mix), and a satisfaction chart
showing how late deliveries crush review scores (2.35★ late vs 4.29★ on-time).

**📖 Data dictionary** — a clean reference of every field, what it means, the words to
use, and example questions.

## Why it's different from a chatbot

| Production concern | How AutoInsight handles it |
|---|---|
| **Hallucinated numbers** | A validator recomputes every headline via a *separate code path*; the chat shows a ✓ validated badge with the recomputed value. |
| **Works without paid APIs** | A deterministic router answers top-N / trend / anomaly / correlation / segment questions with **zero API keys**. An LLM key only upgrades the wording. |
| **Data integrity** | Ingestion self-checks assert row counts, join totals (item price & payments reconcile to the raw files to the cent), and value ranges before anything is served. |
| **Charts are tested too** | Every Explore chart's aggregation is cross-checked against an independent pandas computation in `tests/selfcheck.py`. |

## Architecture

```
User question
   │
   ▼
Intent Router ──► State/Time filter ──► Analyst Node ──► Execute (pandas) ──► Validator ──► Chart ──► Answer
(deterministic                          (top-N, trend,                       (independent
 + LLM-optional)                         anomaly, corr,                       recompute;
                                         segment)                             flag on mismatch)
```

Diagram: [`docs/architecture.mermaid`](docs/architecture.mermaid) ·
Design rationale (LangGraph vs CrewAI): [`docs/ADR-001-orchestration.md`](docs/ADR-001-orchestration.md).

## Project layout

```
app.py                       Streamlit app (Ask / Explore / Dictionary tabs)
insight_agent/
  ingest.py                  joins 9 Olist tables -> order-level master (+ self-checks)
  tools.py                   analysis primitives w/ independent validation
  router.py                  NL -> intent, + time & Brazilian-state parsing
  agent.py                   orchestration, filters, data dictionary
  explore.py                 interactive dashboard charts (story-sequenced)
tests/selfcheck.py           verifies answers AND chart aggregations vs ground truth
sample_data/olist_master.csv.gz
docs/                        ADR + architecture diagram
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The cleaned sample table is bundled, so it loads automatically. To rebuild it from
the raw Olist CSVs: `python insight_agent/ingest.py /path/to/olist_csvs sample_data/olist_master.csv.gz`

## Verify

```bash
python tests/selfcheck.py
```

Runs the agent over a battery of questions (including state and time filters) and
cross-checks each answer **and** each Explore chart against an independent pandas
ground truth. Exits non-zero on any mismatch.

## Deploy (Streamlit Community Cloud — free)

1. Push this folder to a public GitHub repo.
2. [share.streamlit.io](https://share.streamlit.io) → **New app** → pick the repo, branch `main`, main file `app.py` → **Deploy**.
3. You get a public `https://<name>.streamlit.app` URL — no login required for visitors.
4. *(Optional)* richer narration: add `GROQ_API_KEY = "..."` under the app's **Settings → Secrets**.

## Tech

Python · pandas · NumPy · Plotly · Streamlit · deterministic intent routing with
optional Groq/OpenAI LLM layer · validation-gated agent flow.

## Limitations & roadmap

- Orders spanning multiple categories use the dominant category (documented simplification).
- Upload path expects the prepared master schema; arbitrary-CSV profiling is a roadmap item.
<<<<<<< HEAD
- Next: LangGraph checkpointed memory and an eval suite scoring insight quality + hallucination rate.

---

*Built by Braden Bourgeois (LSU) as an analytics portfolio project. Data © Olist, CC BY-NC-SA 4.0.*
=======
- Next: LangGraph checkpointed memory, an eval suite scoring insight quality +
  hallucination rate, and cost/latency logging.
  
## Thank you, Braden Bourgeois
>>>>>>> 58f142c0707f12ccd22a54218d6a7c041f058a04
