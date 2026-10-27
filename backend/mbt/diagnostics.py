"""Where the money went (costs and tax) and whether the result is robust or luck.

Costs: every charge by type and by year, and what CAGR would have been before costs and
before tax (each day's costs added back as a return on the previous day's equity).

Robustness: how concentrated the profit was (top names, asset types, sectors, single
years), CAGR with the biggest winners' daily P&L removed, statistical confidence (Sharpe
t-stat, probabilistic Sharpe, alpha t-stat, block bootstrap), sub-period and rolling-window
consistency, and how realistic the fills were (share of volume, orders that never filled).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252
COST_KEYS = ["brokerage", "stt", "exchange", "sebi", "gst", "stamp", "dp"]


def _cagr_from_returns(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 2:
        return math.nan
    years = (r.index[-1] - r.index[0]).days / 365.25
    growth = float(np.prod(1 + r.to_numpy()))
    return growth ** (1 / years) - 1 if years > 0 and growth > 0 else math.nan


def _prev_equity(eq_df: pd.DataFrame, initial: float) -> pd.Series:
    return eq_df["equity"].shift(1).fillna(initial)


# ------------------------------------------------------------------ costs and tax

def costs_report(result: dict, initial: float) -> dict:
    eq_df: pd.DataFrame = result["equity"]
    eq = eq_df["equity"]
    prev = _prev_equity(eq_df, initial)
    r = eq / prev - 1
    fills = pd.DataFrame([{"date": f.date, "side": f.side, "value": f.value, "fees": f.fees,
                           "slippage": f.slippage, **(f.costs or {})}
                          for f in result["fills"]])
    pay = result.get("tax_mode", "pay") == "pay"
    tax_rows = result.get("taxes", [])
    due = pd.Series({pd.Timestamp(t["paid_on"]): t["tax"] for t in tax_rows if t["paid_on"]},
                    dtype=float).reindex(eq.index).fillna(0.0)

    trade_cost = (eq_df["fees"] + eq_df["slippage"]) / prev
    if pay:
        r_pre_tax = r + eq_df["tax"] / prev
        r_after_tax = r
    else:
        r_pre_tax = r
        r_after_tax = r - due / prev
    r_gross = r_pre_tax + trade_cost

    components = {k: float(fills[k].sum()) if k in fills else 0.0 for k in COST_KEYS}
    components["slippage"] = float(eq_df["slippage"].sum())
    total_trading = sum(components.values())
    tax_total = float(due.sum())
    traded = float(fills["value"].sum()) if not fills.empty else 0.0

    by_year = []
    years = eq.index.year
    fy = fills.set_index("date") if not fills.empty else None
    for y in sorted(set(years)):
        m = years == y
        avg_eq = float(eq[m].mean())
        fz = fy[fy.index.year == y] if fy is not None else pd.DataFrame()
        fees = float(eq_df["fees"][m].sum())
        slip = float(eq_df["slippage"][m].sum())
        tax = float(eq_df["tax"][m].sum()) if pay else float(due[m].sum())
        tv = float(fz["value"].sum()) if len(fz) else 0.0
        by_year.append({"year": int(y), "avg_equity": avg_eq, "traded": tv,
                        "turnover": tv / 2 / avg_eq if avg_eq else math.nan,
                        "fees": fees, "slippage": slip, "tax": tax,
                        "trading_cost_pct": (fees + slip) / avg_eq if avg_eq else math.nan,
                        "tax_pct": tax / avg_eq if avg_eq else math.nan,
                        "return_pre_cost": float(np.prod(1 + r_gross[m]) - 1),
                        "return_after_cost": float(np.prod(1 + r_pre_tax[m]) - 1),
                        "return_after_tax": float(np.prod(1 + r_after_tax[m]) - 1)})

    rt = pd.DataFrame(result["round_trips"])
    per_trade = {}
    if not rt.empty:
        rt_cost = rt["entry_fees"] + rt["exit_fees"]
        rt_value = rt["qty"] * rt["entry_price"]
        per_trade = {
            "avg_round_trip_cost_bps": float(rt_cost.sum() / rt_value.sum() * 1e4
                                             + 2 * _slip_bps(result)),
            "avg_gross_trade_return_pct": float(rt["return_pct"].mean()),
            "median_gross_trade_return_pct": float(rt["return_pct"].median()),
            "avg_trade_value": float(rt_value.mean()),
        }
    tax_classes = []
    if not rt.empty and "tax_class" in rt:
        for k, g in rt.groupby("tax_class"):
            tax_classes.append({"class": k, "round_trips": int(len(g)),
                                "gains": float(g["taxable_gain"].clip(lower=0).sum()),
                                "losses": float(-g["taxable_gain"].clip(upper=0).sum()),
                                "net": float(g["taxable_gain"].sum()),
                                "median_sessions_held": float(g["sessions_held"].median())})

    end = dict(result.get("end_taxes") or {})
    if end and not pay:
        end["liquidation_value"] -= tax_total      # past years' tax was never deducted
    final_after_tax = end.get("liquidation_value")
    years_n = (eq.index[-1] - eq.index[0]).days / 365.25
    return {
        "tax_mode": result.get("tax_mode", "pay"),
        "components": components, "total_trading_costs": total_trading,
        "total_tax": tax_total, "traded_value": traded,
        "cost_pct_of_traded_bps": total_trading / traded * 1e4 if traded else math.nan,
        "cagr_before_costs": _cagr_from_returns(r_gross),
        "cagr_after_costs": _cagr_from_returns(r_pre_tax),
        "cagr_after_tax": _cagr_from_returns(r_after_tax),
        "final_after_tax_liquidation": final_after_tax,
        "cagr_after_tax_liquidation": (final_after_tax / initial) ** (1 / years_n) - 1
        if final_after_tax and final_after_tax > 0 and years_n > 0 else math.nan,
        "end_taxes": end,
        "by_year": by_year, "per_trade": per_trade, "tax_years": tax_rows,
        "tax_classes": tax_classes,
        "charts": {"cum_fees": _series(eq_df["fees"].cumsum()),
                   "cum_slippage": _series(eq_df["slippage"].cumsum()),
                   "cum_tax": _series((eq_df["tax"] if pay else due).cumsum()),
                   "equity_gross": _series(initial * (1 + r_gross).cumprod()),
                   "equity_pre_tax": _series(initial * (1 + r_pre_tax).cumprod()),
                   "equity_after_tax": _series(initial * (1 + r_after_tax).cumprod())},
    }


def _slip_bps(result) -> float:
    fills = result["fills"]
    v = sum(f.value for f in fills)
    return sum(f.slippage for f in fills) / v * 1e4 if v else 0.0


def _series(s: pd.Series, max_points: int = 1500):
    step = max(1, len(s) // max_points)
    s = s.iloc[::step]
    return [[str(d.date()), float(v) if np.isfinite(v) else None] for d, v in s.items()]


# ------------------------------------------------------------------ robustness

ASSET_LABEL = {"stock": "Stocks", "equity": "Equity ETFs / funds",
               "other": "Gold, silver, foreign ETFs", "debt": "Debt / liquid ETFs"}


def robustness_report(result: dict, initial: float, securities: pd.DataFrame | None,
                      rf: float = 0.065) -> dict:
    eq_df: pd.DataFrame = result["equity"]
    eq = eq_df["equity"]
    prev = _prev_equity(eq_df, initial)
    r = eq / prev - 1
    bpx = eq_df["benchmark"].astype(float)
    b = bpx.pct_change()
    has_bench = bpx.notna().sum() > 20

    sp = pd.DataFrame(result.get("symbol_pnl", []), columns=["date", "symbol", "pnl"])
    out: dict = {}
    if not sp.empty:
        out.update(_concentration(sp, r, prev, eq, result, securities))
    out["significance"] = _significance(r, b if has_bench else None, rf)
    out["bootstrap"] = _bootstrap(r, b if has_bench else None)
    out["subperiods"] = _subperiods(eq, bpx if has_bench else None)
    out["rolling_consistency"] = _rolling_consistency(r, b if has_bench else None)
    out["execution"] = _execution(result, eq)
    rt = pd.DataFrame(result["round_trips"])
    if not rt.empty:
        rt["year"] = pd.to_datetime(rt["exit_date"]).dt.year
        out["trades_by_year"] = [
            {"year": int(y), "round_trips": int(len(g)), "win_rate": float((g["pnl"] > 0).mean()),
             "avg_return_pct": float(g["return_pct"].mean()),
             "profit_factor": float(g.loc[g.pnl > 0, "pnl"].sum() / -g.loc[g.pnl <= 0, "pnl"].sum())
             if (g.pnl <= 0).any() and g.loc[g.pnl <= 0, "pnl"].sum() < 0 else None}
            for y, g in rt.groupby("year")]
    return out


def _asset_type(sym: str, result: dict, securities) -> str:
    cls = result.get("asset_classes", {}).get(sym, "equity")
    isin = ""
    if securities is not None and sym in securities.index:
        isin = str(securities.at[sym, "isin"] or "")
    if cls == "equity" and not isin.startswith("INF"):
        return "stock"
    return cls


def _concentration(sp, r, prev, eq, result, securities) -> dict:
    total = sp.groupby("symbol")["pnl"].sum().sort_values(ascending=False)
    net = float(total.sum())
    gross_profit = float(total[total > 0].sum())
    daily = sp.pivot_table(index="date", columns="symbol", values="pnl", aggfunc="sum") \
        .reindex(eq.index).fillna(0.0)
    base_cagr = _cagr_from_returns(r)

    def without(symbols) -> float:
        cols = [s for s in symbols if s in daily]
        adj = r - daily[cols].sum(axis=1) / prev
        return _cagr_from_returns(adj)

    winners = list(total.index)
    excl = []
    for k in (1, 3, 5, 10, 20):
        if k <= len(winners):
            excl.append({"removed": k, "symbols": winners[:k], "cagr": without(winners[:k])})
    n_profitable = int((total > 0).sum())
    # Profit share: how many names it takes to make half / 80% of all profits.
    cum = total[total > 0].cumsum() / gross_profit if gross_profit > 0 else pd.Series(dtype=float)
    names_for = {f"{int(q * 100)}%": int((cum < q).sum() + 1) if len(cum) else None
                 for q in (0.5, 0.8)}

    types = pd.Series({s: _asset_type(s, result, securities) for s in total.index})
    by_type = []
    for t, syms in types.groupby(types):
        pnl = total[syms.index]
        by_type.append({"type": ASSET_LABEL.get(t, t), "symbols": int(len(pnl)),
                        "pnl": float(pnl.sum()),
                        "share_of_net": float(pnl.sum() / net) if net else math.nan,
                        "cagr_without": without(list(syms.index))})
    by_sector = []
    if securities is not None and "sector" in securities:
        sec = securities["sector"].reindex(total.index).fillna("Unclassified")
        for name, pnl in total.groupby(sec):
            by_sector.append({"sector": name, "symbols": int(len(pnl)), "pnl": float(pnl.sum()),
                              "share_of_net": float(pnl.sum() / net) if net else math.nan,
                              "best": pnl.idxmax(), "best_pnl": float(pnl.max())})
        by_sector.sort(key=lambda x: -x["pnl"])

    by_year = []
    yr = daily.groupby(daily.index.year).sum()
    for y, row in yr.iterrows():
        row = row[row != 0].sort_values(ascending=False)
        if row.empty:
            continue
        yr_net = float(row.sum())
        pos = row[row > 0]
        ry = r[r.index.year == y]
        by_year.append({"year": int(y), "return": float(np.prod(1 + ry) - 1), "pnl": yr_net,
                        "symbols": int(len(row)), "top": row.index[0],
                        "top_pnl": float(row.iloc[0]),
                        "top_share_of_profits": float(row.iloc[0] / pos.sum()) if len(pos) else None,
                        "top5_share_of_profits": float(pos.head(5).sum() / pos.sum())
                        if len(pos) else None,
                        "worst": row.index[-1], "worst_pnl": float(row.iloc[-1])})
    top = [{"symbol": s, "pnl": float(v), "share_of_net": float(v / net) if net else None,
            "type": ASSET_LABEL.get(types[s], types[s])} for s, v in total.head(25).items()]
    return {"concentration": {
        "net_pnl": net, "gross_profit": gross_profit, "symbols_traded": int(len(total)),
        "symbols_profitable": n_profitable,
        "top1_share": float(total.iloc[0] / net) if net else None,
        "top5_share": float(total.head(5).sum() / net) if net else None,
        "top10_share": float(total.head(10).sum() / net) if net else None,
        "names_for_profit_share": names_for, "base_cagr": base_cagr,
        "cagr_excluding_top": excl, "by_asset_type": by_type, "by_sector": by_sector,
        "by_year": by_year, "top": top}}


def _significance(r: pd.Series, b: pd.Series | None, rf: float) -> dict:
    x = r.iloc[1:].dropna()
    ex = x - rf / TRADING_DAYS
    n = len(ex)
    sd = ex.std()
    sr = ex.mean() / sd if sd > 0 else math.nan       # per-session Sharpe
    skew, kurt = float(x.skew()), float(x.kurt()) + 3
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    psr = _norm_cdf(sr * math.sqrt(n - 1) / math.sqrt(denom)) if denom > 0 else math.nan
    out = {"sessions": n, "sharpe_t_stat": sr * math.sqrt(n) if np.isfinite(sr) else math.nan,
           "probabilistic_sharpe": psr,
           "sharpe_ci95": [(sr - 1.96 * math.sqrt(denom / (n - 1))) * math.sqrt(TRADING_DAYS),
                           (sr + 1.96 * math.sqrt(denom / (n - 1))) * math.sqrt(TRADING_DAYS)]
           if denom > 0 else None,
           "mean_daily_return_t_stat": float(x.mean() / x.std() * math.sqrt(n))}
    if b is not None:
        df = pd.concat([r, b], axis=1, keys=["s", "b"]).iloc[1:].dropna()
        y = df["s"] - rf / TRADING_DAYS
        X = np.column_stack([np.ones(len(df)), df["b"] - rf / TRADING_DAYS])
        coef, *_ = np.linalg.lstsq(X, y.to_numpy(), rcond=None)
        resid = y.to_numpy() - X @ coef
        s2 = resid @ resid / (len(df) - 2)
        cov = s2 * np.linalg.inv(X.T @ X)
        out["alpha_annual"] = float(coef[0] * TRADING_DAYS)
        out["alpha_t_stat"] = float(coef[0] / math.sqrt(cov[0, 0]))
        act = df["s"] - df["b"]
        out["active_return_t_stat"] = float(act.mean() / act.std() * math.sqrt(len(act)))
    return out


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _bootstrap(r: pd.Series, b: pd.Series | None, n_boot: int = 1000, block: int = 21,
               seed: int = 7) -> dict:
    """Moving-block bootstrap: rebuild the history from random 21-session blocks of actual
    (strategy, benchmark) days, keeping short-run autocorrelation and the pairing."""
    s = r.iloc[1:].fillna(0).to_numpy()
    bb = b.iloc[1:].fillna(0).to_numpy() if b is not None else None
    n = len(s)
    if n < block * 4:
        return {}
    rng = np.random.default_rng(seed)
    k = math.ceil(n / block)
    starts = rng.integers(0, n - block, size=(n_boot, k))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n_boot, -1)[:, :n]
    years = n / TRADING_DAYS
    ls = np.log1p(s)[idx]
    cagr = np.exp(ls.sum(1) / years) - 1
    path = np.cumsum(ls, axis=1)
    mdd = (path - np.maximum.accumulate(path, axis=1)).min(1)
    out = {"n": n_boot, "block_sessions": block,
           "cagr_p5": float(np.percentile(cagr, 5)), "cagr_p50": float(np.median(cagr)),
           "cagr_p95": float(np.percentile(cagr, 95)),
           "max_dd_p50": float(np.expm1(np.median(mdd))),
           "max_dd_p5": float(np.expm1(np.percentile(mdd, 5))),
           "prob_cagr_below_0": float((cagr < 0).mean()),
           "prob_cagr_below_15": float((cagr < 0.15).mean())}
    if bb is not None:
        bc = np.exp(np.log1p(bb)[idx].sum(1) / years) - 1
        out["prob_beats_benchmark"] = float((cagr > bc).mean())
        out["excess_cagr_p5"] = float(np.percentile(cagr - bc, 5))
        out["excess_cagr_p50"] = float(np.median(cagr - bc))
    return out


def _subperiods(eq: pd.Series, bpx: pd.Series | None, parts: int = 3) -> list[dict]:
    rows = []
    edges = np.linspace(0, len(eq) - 1, parts + 1).astype(int)
    for a, z in zip(edges[:-1], edges[1:]):
        seg = eq.iloc[a:z + 1]
        r = seg.pct_change().dropna()
        yrs = (seg.index[-1] - seg.index[0]).days / 365.25
        row = {"start": str(seg.index[0].date()), "end": str(seg.index[-1].date()),
               "cagr": (seg.iloc[-1] / seg.iloc[0]) ** (1 / yrs) - 1,
               "sharpe": (r.mean() - 0.065 / TRADING_DAYS) / r.std() * math.sqrt(TRADING_DAYS)
               if r.std() > 0 else math.nan,
               "max_drawdown": float((seg / seg.cummax() - 1).min())}
        if bpx is not None:
            bs = bpx.iloc[a:z + 1].dropna()
            row["benchmark_cagr"] = (bs.iloc[-1] / bs.iloc[0]) ** (1 / yrs) - 1 \
                if len(bs) > 1 else math.nan
        rows.append(row)
    return rows


def _rolling_consistency(r: pd.Series, b: pd.Series | None) -> list[dict]:
    rows = []
    ls = np.log1p(r.fillna(0))
    lb = np.log1p(b.fillna(0)) if b is not None else None
    for yrs in (1, 3, 5):
        w = TRADING_DAYS * yrs
        if len(r) <= w + 1:
            continue
        cs = np.expm1(ls.rolling(w).sum() / yrs).dropna()
        row = {"years": yrs, "windows": int(len(cs)), "positive": float((cs > 0).mean()),
               "worst_cagr": float(cs.min()), "median_cagr": float(cs.median()),
               "best_cagr": float(cs.max())}
        if lb is not None:
            cb = np.expm1(lb.rolling(w).sum() / yrs).reindex(cs.index)
            row["beat_benchmark"] = float((cs > cb).mean())
            row["worst_excess"] = float((cs - cb).min())
        rows.append(row)
    return rows


def _group(rows: list[dict], keys: tuple[str, ...]) -> dict:
    out: dict = {}
    for row in rows:
        out.setdefault(tuple(row.get(k) for k in keys), []).append(row)
    return out


def _execution(result: dict, eq: pd.Series) -> dict:
    fills = result["fills"]
    part = np.array([f.participation for f in fills
                     if f.reason != "delisted" and np.isfinite(f.participation)])
    expired = result.get("expired_orders", [])
    exp_val = sum(e["value"] or 0 for e in expired)
    exp_buy = [e for e in expired if e["side"] == "buy"]
    exp_sell = [e for e in expired if e["side"] == "sell"]
    delisted = [f for f in fills if f.reason == "delisted"]
    return {
        "fills": len(fills),
        "participation_median": float(np.median(part)) if len(part) else None,
        "participation_p95": float(np.percentile(part, 95)) if len(part) else None,
        "participation_max": float(part.max()) if len(part) else None,
        "fills_over_1pct_volume": float((part > 0.01).mean()) if len(part) else None,
        "fills_capped": int(sum(f.capped for f in fills)),
        "expired_orders": len(expired), "expired_buys": len(exp_buy),
        "expired_sells": len(exp_sell), "expired_value": exp_val,
        "expired_value_pct_of_avg_equity": exp_val / float(eq.mean()) if len(eq) else None,
        "expired_by_cause": [{"cause": c, "side": sd, "orders": len(g),
                              "value": float(sum(e["value"] or 0 for e in g))}
                             for (c, sd), g in _group(expired, ("cause", "side")).items()],
        "delisted_exits": len(delisted),
        "delisted_value": float(sum(f.value for f in delisted)),
        "expired_sample": sorted(expired, key=lambda e: -(e["value"] or 0))[:30],
    }
