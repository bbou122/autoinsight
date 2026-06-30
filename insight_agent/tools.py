"""
AutoInsight — analysis tool layer.

Each tool takes the master DataFrame + parsed params and returns a Result:
a table, a Plotly figure, a plain-language headline, AND an independent
recompute used by the validator. The recompute deliberately uses a DIFFERENT
code path than the displayed answer so a bug in one is caught by the other.

Plotly is optional: all numbers + validation run without it (figure=None);
charts are built only when plotly is installed (i.e. in the deployed app).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

try:
    import plotly.express as px
    _HAS_PX = True
except Exception:
    px = None
    _HAS_PX = False

PALETTE = ["#2563eb", "#0ea5e9", "#14b8a6", "#f59e0b", "#ef4444", "#8b5cf6"]
_LAYOUT = dict(template="plotly_white", font=dict(family="Inter, system-ui, sans-serif", size=13),
               margin=dict(l=10, r=10, t=50, b=10), title_font_size=17, colorway=PALETTE, height=420)

# pandas 3.0 removed the "M" resample alias in favor of "ME"; pick whatever is valid.
try:
    pd.tseries.frequencies.to_offset("ME")
    _MONTH = "ME"
except Exception:
    _MONTH = "M"


@dataclass
class Result:
    intent: str
    headline: str
    table: pd.DataFrame
    figure: object = None
    check: dict = field(default_factory=lambda: {"passed": True, "detail": "n/a"})
    params: dict = field(default_factory=dict)


def _fmt(v, measure):
    if measure in {"payment_value", "total_price", "total_freight"}:
        return f"R${v:,.0f}"
    if measure == "review_score":
        return f"{v:.2f} stars"
    if "days" in measure:
        return f"{v:.1f} days"
    return f"{v:,.1f}"


def _label(col):
    return col.replace("_", " ").title()


def top_n(df, dimension, measure, agg="sum", n=10, ascending=False, min_count=0):
    grp = df.groupby(dimension)[measure]
    g = grp.agg(agg)
    if min_count:
        g = g[grp.size() >= min_count]  # drop tiny-sample groups for fair ranking
    g = g.sort_values(ascending=ascending)
    top = g.head(n).reset_index()
    top.columns = [_label(dimension), _label(measure)]
    lead_key = g.index[0]
    indep = df.loc[df[dimension] == lead_key, measure].agg(agg)  # independent recompute
    passed = abs(float(indep) - float(g.iloc[0])) < 1e-6
    fig = None
    if _HAS_PX:
        fig = px.bar(top, x=_label(measure), y=_label(dimension), orientation="h",
                     title=f"{'Bottom' if ascending else 'Top'} {n} {_label(dimension)} by {agg} {_label(measure)}")
        fig.update_layout(**_LAYOUT, yaxis=dict(autorange="reversed"))
    rank = "lowest" if ascending else "highest"
    head = f"**{lead_key}** has the {rank} {agg} {_label(measure).lower()} at {_fmt(g.iloc[0], measure)}."
    return Result("top_n", head, top, fig,
                  {"passed": passed, "detail": f"displayed={g.iloc[0]:.4f} recomputed={indep:.4f}"},
                  {"dimension": dimension, "measure": measure, "agg": agg, "n": n,
                   "ascending": ascending, "min_count": min_count})


def trend(df, measure, agg="sum", freq=_MONTH):
    t = df.dropna(subset=["order_purchase_timestamp"]).set_index("order_purchase_timestamp")
    s = t[measure].resample(freq).agg(agg).dropna()
    out = s.reset_index()
    out.columns = ["Period", _label(measure)]
    lp = s.index[-1].to_period("M")
    mask = (df["order_purchase_timestamp"] >= lp.start_time) & \
           (df["order_purchase_timestamp"] <= lp.end_time)
    indep = df.loc[mask, measure].agg(agg)  # independent recompute of last period
    passed = abs(float(indep) - float(s.iloc[-1])) < 1e-6
    fig = None
    if _HAS_PX:
        fig = px.line(out, x="Period", y=_label(measure), markers=True,
                      title=f"{agg.title()} {_label(measure)} over time")
        fig.update_layout(**_LAYOUT)
        fig.update_traces(line_color=PALETTE[0])
    pct = (s.iloc[-1] - s.iloc[0]) / abs(s.iloc[0]) * 100 if s.iloc[0] else 0
    head = f"{_label(measure)} went from {_fmt(s.iloc[0], measure)} to {_fmt(s.iloc[-1], measure)} ({pct:+.0f}%) across the period."
    return Result("trend", head, out, fig,
                  {"passed": passed, "detail": f"last={s.iloc[-1]:.4f} recomputed={indep:.4f}"},
                  {"measure": measure, "agg": agg, "freq": freq})


def anomaly(df, measure, agg="sum", freq=_MONTH, z=2.0):
    t = df.dropna(subset=["order_purchase_timestamp"]).set_index("order_purchase_timestamp")
    s = t[measure].resample(freq).agg(agg).dropna()
    mu, sd = s.mean(), s.std()
    zs = (s - mu) / sd
    out = pd.DataFrame({"Period": s.index, _label(measure): s.values,
                        "Z-score": zs.values, "Anomaly": abs(zs.values) >= z})
    an = out[out["Anomaly"]]
    indep_count = int(np.sum(np.abs((s.values - s.values.mean()) / s.values.std(ddof=1)) >= z))
    passed = indep_count == int(out["Anomaly"].sum())
    fig = None
    if _HAS_PX:
        fig = px.line(out, x="Period", y=_label(measure), title=f"Anomalies in {agg} {_label(measure)} (|z|>={z})")
        if len(an):
            fig.add_scatter(x=an["Period"], y=an[_label(measure)], mode="markers",
                            marker=dict(color=PALETTE[4], size=12, symbol="circle-open", line=dict(width=3)), name="anomaly")
        fig.update_layout(**_LAYOUT)
    if len(an):
        worst = an.iloc[abs(an["Z-score"]).argmax()]
        head = (f"Found **{len(an)} anomalous period(s)**. Most extreme: "
                f"{worst['Period'].strftime('%b %Y')} at {_fmt(worst[_label(measure)], measure)} "
                f"({worst['Z-score']:+.1f} sigma from the mean).")
    else:
        head = f"No periods exceeded |z|>={z} for {agg} {_label(measure).lower()} — the series is stable."
    return Result("anomaly", head, out, fig,
                  {"passed": passed, "detail": f"displayed={int(out['Anomaly'].sum())} recomputed={indep_count}"},
                  {"measure": measure, "agg": agg, "freq": freq, "z": z})


def correlation(df, measure_a, measure_b):
    d = df[[measure_a, measure_b]].dropna()
    r = d[measure_a].corr(d[measure_b])
    indep = float(np.corrcoef(d[measure_a], d[measure_b])[0, 1])  # independent recompute
    passed = abs(indep - r) < 1e-6
    fig = None
    if _HAS_PX:
        samp = d.sample(min(4000, len(d)), random_state=0)
        fig = px.scatter(samp, x=measure_a, y=measure_b, opacity=0.35,
                         title=f"{_label(measure_a)} vs {_label(measure_b)} (r={r:.2f})",
                         labels={measure_a: _label(measure_a), measure_b: _label(measure_b)})
        fig.update_traces(marker_color=PALETTE[1])
        m_, b_ = np.polyfit(d[measure_a], d[measure_b], 1)
        xs = np.linspace(d[measure_a].min(), d[measure_a].max(), 50)
        fig.add_scatter(x=xs, y=m_ * xs + b_, mode="lines", line=dict(color=PALETTE[4], width=2), name="fit")
        fig.update_layout(**_LAYOUT)
    strength = ("strong" if abs(r) > 0.5 else "moderate" if abs(r) > 0.3 else "weak" if abs(r) > 0.1 else "negligible")
    direction = "positive" if r > 0 else "negative"
    head = f"{_label(measure_a)} and {_label(measure_b)} show a **{strength} {direction}** correlation (r = {r:.2f}, n = {len(d):,})."
    return Result("correlation", head, d.head(0), fig,
                  {"passed": passed, "detail": f"pandas_r={r:.6f} numpy_r={indep:.6f}"},
                  {"measure_a": measure_a, "measure_b": measure_b, "r": round(float(r), 4)})


def segment_compare(df, dimension, measure, agg="mean"):
    g = df.groupby(dimension)[measure].agg([agg, "count"]).sort_values(agg, ascending=False)
    out = g.reset_index()
    out.columns = [_label(dimension), f"{agg} {_label(measure)}", "Orders"]
    hi, lo = g.index[0], g.index[-1]
    indep_hi = df.loc[df[dimension] == hi, measure].agg(agg)  # independent recompute
    passed = abs(float(indep_hi) - float(g[agg].iloc[0])) < 1e-6
    fig = None
    if _HAS_PX:
        fig = px.bar(out, x=_label(dimension), y=f"{agg} {_label(measure)}",
                     title=f"{agg.title()} {_label(measure)} by {_label(dimension)}")
        fig.update_layout(**_LAYOUT, xaxis={"categoryorder": "total descending"})
    head = (f"By {_label(dimension).lower()}, **{hi}** leads ({_fmt(g[agg].iloc[0], measure)}) "
            f"and **{lo}** trails ({_fmt(g[agg].iloc[-1], measure)}).")
    return Result("segment_compare", head, out, fig,
                  {"passed": passed, "detail": f"displayed={g[agg].iloc[0]:.4f} recomputed={indep_hi:.4f}"},
                  {"dimension": dimension, "measure": measure, "agg": agg})
