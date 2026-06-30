"""AutoInsight self-check — agent answers + Explore charts vs independent pandas truth."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from insight_agent.ingest import load_master, SCHEMA
from insight_agent import agent, explore

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "sample_data", "olist_master.csv.gz")
df = load_master(DATA)
all_pass = True

print("=" * 72)
QUESTIONS = [
    "What are the top 5 states by revenue?",
    "Which product categories have the worst review scores?",
    "Show me revenue trends over time",
    "Are there any anomalies in monthly revenue?",
    "Is there a relationship between delivery delay and review score?",
    "In São Paulo, revenue by product category",
    "What state made the most revenue in January 2018?",
    "In Oklahoma what was their revenue by product category",
    "what can I ask?",
    "Give me a summary",
]
print(f"AGENT — {len(QUESTIONS)} questions on {len(df):,} rows\n")
for q in QUESTIONS:
    res = agent.answer(df, q, SCHEMA)
    ok = res.check["passed"]; all_pass &= ok
    print(f"[{'PASS' if ok else 'FAIL'}] {q}")
    print(f"        intent={res.intent} | {res.headline[:115].replace(chr(10),' ')}")

print("-" * 72)
print("AGENT ground-truth cross-checks:")
sp = df[df.customer_state == "SP"]
gt_sp_cat = sp.groupby("main_category")["payment_value"].sum().idxmax()
a_sp = agent.answer(df, "In São Paulo, revenue by product category")
ok = gt_sp_cat in a_sp.headline and "SP" in a_sp.headline; all_pass &= ok
print(f"  [{'PASS' if ok else 'FAIL'}] SP top category = {gt_sp_cat}")
a_ok = agent.answer(df, "In Oklahoma what was their revenue by product category")
ok = "Oklahoma" in a_ok.headline and "Brazilian" in a_ok.headline; all_pass &= ok
print(f"  [{'PASS' if ok else 'FAIL'}] Oklahoma -> not-in-dataset message")
a_c = agent.answer(df, "In SP, top categories by revenue in January 2018")
ok = ("SP" in a_c.headline and "January 2018" in a_c.headline); all_pass &= ok
print(f"  [{'PASS' if ok else 'FAIL'}] combined SP + Jan 2018")

print("-" * 72)
print("EXPLORE charts vs ground truth:")
d, _ = explore.revenue_by_category(df, 10)
ok = d.iloc[0]["Category"] == df.groupby("main_category")["payment_value"].sum().idxmax(); all_pass &= ok
print(f"  [{'PASS' if ok else 'FAIL'}] revenue_by_category top = {d.iloc[0]['Category']}")
d, _ = explore.payment_mix_pie(df)
ok = abs(d["Revenue"].sum() - df["payment_value"].sum()) < 1; all_pass &= ok
print(f"  [{'PASS' if ok else 'FAIL'}] payment_mix_pie sums to total revenue")
d, _ = explore.category_share_pie(df, n=8)
ok = abs(d["Revenue"].sum() - df["payment_value"].sum()) < 1; all_pass &= ok
print(f"  [{'PASS' if ok else 'FAIL'}] category_share_pie (top8+other) sums to total")
d, _ = explore.satisfaction_by_delivery(df)
late = d.loc[d.Delivery == "Late", "Avg review"].iloc[0]
ont = d.loc[d.Delivery == "On-time / early", "Avg review"].iloc[0]
ok = late < ont; all_pass &= ok
print(f"  [{'PASS' if ok else 'FAIL'}] late reviews ({late:.2f}) < on-time ({ont:.2f})")

print("=" * 72)
print("RESULT:", "ALL CHECKS PASSED" if all_pass else "SOME CHECKS FAILED")
sys.exit(0 if all_pass else 1)
