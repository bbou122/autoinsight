"""
AutoInsight — interactive Explore charts.

Each function returns (aggregated DataFrame, Plotly figure). The DataFrame is the
testable substance; the figure is built only when plotly is available. The charts
are sequenced to tell a story: growth -> where the money is -> how people pay ->
what drives satisfaction.
"""
from __future__ import annotations
import pandas as pd

try:
    import plotly.express as px
    import plotly.graph_objects as go
    _HAS_PX = True
except Exception:
    px = go = None
    _HAS_PX = False

PALETTE = ["#2563eb", "#0ea5e9", "#14b8a6", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#84cc16"]
_LAYOUT = dict(template="plotly_white", font=dict(family="Inter, system-ui, sans-serif", size=13),
               margin=dict(l=10, r=10, t=48, b=10), title_font_size=16, colorway=PALETTE, height=360)


def payment_types(df):
    return sorted(df["main_payment_type"].dropna().unique().tolist())


def category_list(df, n=12):
    return (df.groupby("main_category")["payment_value"].sum()
            .sort_values(ascending=False).head(n).index.tolist())


def revenue_trend(df):
    s = (df.dropna(subset=["order_purchase_timestamp"])
         .set_index("order_purchase_timestamp")["payment_value"]
         .resample("MS").sum().dropna())
    d = s.reset_index(); d.columns = ["Month", "Revenue"]
    fig = None
    if _HAS_PX and len(d):
        fig = px.area(d, x="Month", y="Revenue", title="Revenue over time")
        fig.update_traces(line_color=PALETTE[0], fillcolor="rgba(37,99,235,0.12)")
        fig.update_layout(**_LAYOUT)
    return d, fig


def revenue_by_category(df, n=10):
    s = df.groupby("main_category")["payment_value"].sum().sort_values(ascending=False).head(n)
    d = s.reset_index(); d.columns = ["Category", "Revenue"]
    fig = None
    if _HAS_PX and len(d):
        fig = px.bar(d, x="Revenue", y="Category", orientation="h", title=f"Top {n} categories by revenue")
        fig.update_layout(**_LAYOUT, yaxis=dict(autorange="reversed"))
        fig.update_traces(marker_color=PALETTE[0])
    return d, fig


def category_share_pie(df, include=None, n=8):
    rev = df.groupby("main_category")["payment_value"].sum().sort_values(ascending=False)
    if include:
        rev = rev[rev.index.isin(include)]
    else:
        top = rev.head(n)
        other = rev.iloc[n:].sum()
        rev = top.copy()
        if other > 0:
            rev["other"] = other
    d = rev.reset_index(); d.columns = ["Category", "Revenue"]
    fig = None
    if _HAS_PX and len(d):
        fig = px.pie(d, names="Category", values="Revenue", hole=0.45,
                     title="Revenue share by category")
        fig.update_layout(**_LAYOUT)
        fig.update_traces(textposition="inside", textinfo="percent")
    return d, fig


def payment_mix_pie(df, include=None):
    f = df if not include else df[df["main_payment_type"].isin(include)]
    s = f.groupby("main_payment_type")["payment_value"].sum().sort_values(ascending=False)
    d = s.reset_index(); d.columns = ["Payment type", "Revenue"]
    fig = None
    if _HAS_PX and len(d):
        fig = px.pie(d, names="Payment type", values="Revenue", hole=0.45,
                     title="Revenue share by payment method")
        fig.update_layout(**_LAYOUT)
        fig.update_traces(textposition="inside", textinfo="percent")
    return d, fig


def satisfaction_by_delivery(df):
    f = df.dropna(subset=["on_time", "review_score"]).copy()
    f["Delivery"] = f["on_time"].map({True: "On-time / early", False: "Late"})
    s = f.groupby("Delivery")["review_score"].mean()
    d = s.reset_index(); d.columns = ["Delivery", "Avg review"]
    fig = None
    if _HAS_PX and len(d):
        fig = px.bar(d, x="Delivery", y="Avg review", title="Late deliveries hurt reviews",
                     range_y=[0, 5], color="Delivery",
                     color_discrete_map={"On-time / early": PALETTE[2], "Late": PALETTE[4]})
        fig.update_layout(**_LAYOUT, showlegend=False)
    return d, fig


def revenue_by_state(df, n=10):
    s = df.groupby("customer_state")["payment_value"].sum().sort_values(ascending=False).head(n)
    d = s.reset_index(); d.columns = ["State", "Revenue"]
    fig = None
    if _HAS_PX and len(d):
        fig = px.bar(d, x="State", y="Revenue", title=f"Top {n} states by revenue")
        fig.update_layout(**_LAYOUT)
        fig.update_traces(marker_color=PALETTE[1])
    return d, fig
