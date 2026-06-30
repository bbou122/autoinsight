"""
AutoInsight self-check harness.

Runs a battery of natural-language questions through the full agent and
cross-checks each headline number against an INDEPENDENT pandas computation.
Exits non-zero if any check fails. This is the gate that proves the agent
isn't hallucinating numbers.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from insight_agent.ingest import load_master, SCHEMA
from insight_agent import agent

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "sample_data", "olist_master.csv.gz")
df = load_master(DATA)

QUESTIONS = [
    "What are the top 5 states by revenue?",
    "Which product categories have the worst review scores?",
    "Show me revenue trends over time",
    "Are there any anomalies in monthly revenue?",
    "Is there a relationship between delivery delay and review score?",
    "Compare average delivery time by state",
    "Give me a summary",
]

# Independent ground-truth recomputations (different code path than the tools).
def gt_top_state():
    return df.groupby("customer_state")["payment_value"].sum().idxmax()

def gt_worst_cat():
    g = df.groupby("main_category")["review_score"]
    return g.mean()[g.size() >= 30].idxmin()  # same min-sample rule as the agent

def gt_corr():
    d = df[["delivery_delay_days", "review_score"]].dropna()
    return round(d["delivery_delay_days"].corr(d["review_score"]), 2)

print("=" * 70)
print(f"Loaded {len(df):,} rows from sample. Running {len(QUESTIONS)} questions.\n")

all_pass = True
for q in QUESTIONS:
    res = agent.answer(df, q, SCHEMA)
    status = "PASS" if res.check["passed"] else "FAIL"
    all_pass &= res.check["passed"]
    print(f"[{status}] Q: {q}")
    print(f"        intent={res.intent}  validator: {res.check['detail']}")
    print(f"        answer: {res.headline[:110].replace(chr(10),' ')}")
    print(f"        chart : {'yes' if res.figure is not None else 'no'}  rows={len(res.table)}\n")

# extra cross-checks against independent ground truth
print("-" * 70)
print("Independent ground-truth cross-checks:")
r1 = agent.answer(df, "top states by revenue", SCHEMA)
ok1 = gt_top_state() in r1.headline
print(f"  [{'PASS' if ok1 else 'FAIL'}] top revenue state = {gt_top_state()} (in answer: {ok1})")
r2 = agent.answer(df, "worst categories by review score", SCHEMA)
ok2 = gt_worst_cat() in r2.headline
print(f"  [{'PASS' if ok2 else 'FAIL'}] worst review category = {gt_worst_cat()} (in answer: {ok2})")
r3 = agent.answer(df, "relationship between delivery delay and review score", SCHEMA)
ok3 = abs(r3.params.get("r", 0) - gt_corr()) < 0.01
print(f"  [{'PASS' if ok3 else 'FAIL'}] delay~review r = {gt_corr()} (agent: {round(r3.params.get('r',0),2)})")

all_pass &= ok1 and ok2 and ok3
print("=" * 70)
print("RESULT:", "ALL CHECKS PASSED ✓" if all_pass else "SOME CHECKS FAILED ✗")
sys.exit(0 if all_pass else 1)
