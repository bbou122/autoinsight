"""
AutoInsight — Olist ingestion layer.

Joins the 9 raw Olist CSVs into ONE order-level analytical table and runs
self-check assertions so we never build on silently-broken data.

Grain: one row per order_id.
Why order-level: payments and reviews are per-order, items are per-item. Joining
everything at item grain would double-count payment_value and review_score. We
aggregate items up to the order, so every measure is additive and safe to sum.

Public API:
    build_master(raw_dir) -> (pd.DataFrame, dict report)   # builds + self-checks
    load_master(path) -> pd.DataFrame                       # fast load for the app
    SCHEMA                                                  # column roles for the agent
"""

from __future__ import annotations
import os
import pandas as pd

SCHEMA = {
    "date_col": "order_purchase_timestamp",
    "categorical": [
        "customer_state", "main_category", "main_payment_type",
        "order_status", "purchase_year", "purchase_month_name", "purchase_dow",
    ],
    "measures": [
        "total_price", "total_freight", "payment_value", "n_items",
        "delivery_days", "delivery_delay_days", "review_score", "max_installments",
    ],
    "primary_measure": "payment_value",
}

_FILES = {
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "cat_translation": "product_category_name_translation.csv",
}


def _read(raw_dir: str, key: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(raw_dir, _FILES[key]), encoding="utf-8-sig")


def build_master(raw_dir: str):
    """Join raw Olist tables into the order-level master table + a profile report."""
    orders = _read(raw_dir, "orders")
    items = _read(raw_dir, "items")
    payments = _read(raw_dir, "payments")
    reviews = _read(raw_dir, "reviews")
    products = _read(raw_dir, "products")
    customers = _read(raw_dir, "customers")
    cat_tr = _read(raw_dir, "cat_translation")

    raw_counts = {"orders": len(orders), "items": len(items),
                  "payments": len(payments), "reviews": len(reviews)}
    raw_item_price_sum = round(float(items["price"].sum()), 2)
    raw_payment_sum = round(float(payments["payment_value"].sum()), 2)

    for c in ["order_purchase_timestamp", "order_delivered_customer_date",
              "order_estimated_delivery_date"]:
        orders[c] = pd.to_datetime(orders[c], errors="coerce")

    products = products.merge(cat_tr, on="product_category_name", how="left")
    products["category_en"] = (
        products["product_category_name_english"]
        .fillna(products["product_category_name"]).fillna("uncategorized")
    )

    items = items.merge(products[["product_id", "category_en"]], on="product_id", how="left")
    items_agg = items.groupby("order_id").agg(
        total_price=("price", "sum"),
        total_freight=("freight_value", "sum"),
        n_items=("order_item_id", "count"),
    ).reset_index()
    # dominant category per order (vectorized: most frequent, ties -> alphabetical)
    cat_counts = (
        items.dropna(subset=["category_en"])
        .groupby(["order_id", "category_en"]).size().reset_index(name="n")
        .sort_values(["order_id", "n", "category_en"], ascending=[True, False, True])
    )
    main_cat = (cat_counts.drop_duplicates("order_id")[["order_id", "category_en"]]
                .rename(columns={"category_en": "main_category"}))

    pay_agg = payments.groupby("order_id").agg(
        payment_value=("payment_value", "sum"),
        max_installments=("payment_installments", "max"),
    ).reset_index()
    main_pay = (payments.sort_values("payment_value", ascending=False)
                .drop_duplicates("order_id")[["order_id", "payment_type"]]
                .rename(columns={"payment_type": "main_payment_type"}))

    rev_agg = reviews.groupby("order_id").agg(review_score=("review_score", "mean")).reset_index()

    m = orders.merge(customers[["customer_id", "customer_state"]], on="customer_id", how="left")
    for piece in (items_agg, main_cat, pay_agg, main_pay, rev_agg):
        m = m.merge(piece, on="order_id", how="left")

    m["delivery_days"] = (m["order_delivered_customer_date"] - m["order_purchase_timestamp"]).dt.total_seconds() / 86400
    m["delivery_delay_days"] = (m["order_delivered_customer_date"] - m["order_estimated_delivery_date"]).dt.total_seconds() / 86400
    m["on_time"] = m["delivery_delay_days"] <= 0

    ts = m["order_purchase_timestamp"]
    m["purchase_year"] = ts.dt.year
    m["purchase_month"] = ts.dt.to_period("M").astype(str)
    m["purchase_month_name"] = ts.dt.month_name()
    m["purchase_quarter"] = ts.dt.year.astype("Int64").astype(str) + "-Q" + ts.dt.quarter.astype("Int64").astype(str)
    m["purchase_dow"] = ts.dt.day_name()

    m["main_category"] = m["main_category"].fillna("uncategorized").replace("unknown", "uncategorized")
    m["main_payment_type"] = m["main_payment_type"].fillna("unknown")

    report = _profile(m, raw_counts, raw_item_price_sum, raw_payment_sum)
    return m, report


def _profile(m, raw_counts, raw_item_price_sum, raw_payment_sum) -> dict:
    """Profile + SELF-CHECK assertions. Raises AssertionError if data is wrong."""
    checks = []

    def check(name, passed, detail=""):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    check("row count == distinct orders",
          len(m) == m["order_id"].nunique() == raw_counts["orders"],
          f"rows={len(m)} distinct={m['order_id'].nunique()} raw_orders={raw_counts['orders']}")
    joined_price = round(float(m["total_price"].sum()), 2)
    check("summed item price matches raw", abs(joined_price - raw_item_price_sum) < 1.0,
          f"joined={joined_price} raw={raw_item_price_sum}")
    joined_pay = round(float(m["payment_value"].sum()), 2)
    check("summed payment matches raw", abs(joined_pay - raw_payment_sum) < 1.0,
          f"joined={joined_pay} raw={raw_payment_sum}")
    rs = m["review_score"].dropna()
    check("review_score in [1,5]", rs.between(1, 5).all(), f"min={rs.min()} max={rs.max()}")
    check("purchase timestamp parsed", m["order_purchase_timestamp"].notna().all(),
          f"nulls={int(m['order_purchase_timestamp'].isna().sum())}")

    failed = [c for c in checks if not c["passed"]]
    report = {
        "rows": len(m),
        "date_range": [str(m["order_purchase_timestamp"].min()), str(m["order_purchase_timestamp"].max())],
        "n_states": int(m["customer_state"].nunique()),
        "n_categories": int(m["main_category"].nunique()),
        "delivered_orders": int(m["delivery_days"].notna().sum()),
        "null_pct": {c: round(float(m[c].isna().mean() * 100), 1) for c in SCHEMA["measures"]},
        "checks": checks,
        "all_checks_passed": len(failed) == 0,
    }
    if failed:
        raise AssertionError(f"Ingestion self-check FAILED: {failed}")
    return report


def load_master(path: str) -> pd.DataFrame:
    """Load the prebuilt master. Supports .csv.gz (default) or .parquet."""
    if path.endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, compression="infer")
        df["order_purchase_timestamp"] = pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
    if "main_category" in df.columns:
        df["main_category"] = df["main_category"].replace("unknown", "uncategorized")
    return df


if __name__ == "__main__":
    import json, sys
    raw = sys.argv[1] if len(sys.argv) > 1 else "."
    out = sys.argv[2] if len(sys.argv) > 2 else "olist_master.csv.gz"
    master, rep = build_master(raw)
    master.to_csv(out, index=False, compression="gzip")
    print(json.dumps(rep, indent=2))
    print(f"\nSaved {len(master):,} rows -> {out}")
