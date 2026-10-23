"""Performance analytics for a finished backtest (strategy vs benchmark).

These run after the backtest on the realised equity curve, so they may look at the whole
period. Regime *labels* are nonetheless computed from trailing data only (e.g. the 200-day
average as it stood that day), so "how did the strategy do in bear markets" uses the same
definition an investor could have applied in real time.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Notable Indian market episodes (dates inclusive).
EPISODES = [
    ("2008 Global Financial Crisis", "2008-01-08", "2009-03-09"),
    ("2009 Recovery rally", "2009-03-10", "2010-11-05"),
    ("2011 Euro crisis / policy paralysis", "2010-11-08", "2011-12-20"),
    ("2013 Taper tantrum", "2013-05-20", "2013-08-28"),
    ("2014 Election rally", "2014-02-01", "2015-03-04"),
    ("2015-16 China scare & slowdown", "2015-03-05", "2016-02-29"),
    ("2016 Demonetisation", "2016-11-08", "2016-12-26"),
    ("2018 IL&FS / small-cap crash", "2018-01-29", "2019-03-01"),
    ("2020 COVID crash", "2020-02-20", "2020-03-23"),
    ("2020-21 Post-COVID bull run", "2020-03-24", "2021-10-19"),
    ("2022 Rate hikes & war", "2021-10-20", "2022-06-17"),
    ("2023-24 Broad rally", "2023-03-28", "2024-09-26"),
    ("2024-25 Correction", "2024-09-27", "2025-03-04"),
]


def _cagr(eq: pd.Series) -> float:
    eq = eq.dropna()
    if len(eq) < 2 or eq.iloc[0] <= 0:
        return math.nan
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    return (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if years > 0 else math.nan


def _drawdown(eq: pd.Series) -> pd.Series:
    return eq / eq.cummax() - 1


def _max_dd_duration(eq: pd.Series) -> int:
    dd = _drawdown(eq)
    longest = cur = 0
    for v in dd.to_numpy():
        cur = cur + 1 if v < 0 else 0
        longest = max(longest, cur)
    return longest


def _ratios(r: pd.Series, rf: float) -> dict:
    r = r.dropna()
    if len(r) < 5:
        return {}
    ex = r - rf / TRADING_DAYS
    vol = r.std() * math.sqrt(TRADING_DAYS)
    down = r[r < 0].std() * math.sqrt(TRADING_DAYS)
    eq = (1 + r).cumprod()
    cagr = _cagr(pd.concat([pd.Series([1.0], index=[r.index[0] - pd.Timedelta(days=1)]), eq]))
    mdd = _drawdown(eq).min()
    monthly = (1 + r).resample("ME").prod() - 1
    return {
        "total_return": eq.iloc[-1] - 1,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": ex.mean() / r.std() * math.sqrt(TRADING_DAYS) if r.std() > 0 else math.nan,
        "sortino": ex.mean() * TRADING_DAYS / down if down > 0 else math.nan,
        "max_drawdown": mdd,
        "max_drawdown_sessions": _max_dd_duration(eq),
        "calmar": cagr / abs(mdd) if mdd < 0 else math.nan,
        "best_day": r.max(), "worst_day": r.min(),
        "best_month": monthly.max(), "worst_month": monthly.min(),
        "positive_months": (monthly > 0).mean(),
        "skew": r.skew(), "kurtosis": r.kurt(),
        "var_95": r.quantile(0.05),
        "cvar_95": r[r <= r.quantile(0.05)].mean(),
    }


def _relative(r: pd.Series, b: pd.Series, rf: float) -> dict:
    df = pd.concat([r, b], axis=1, keys=["s", "b"]).dropna()
    if len(df) < 20:
        return {}
    s, bb = df["s"], df["b"]
    var = bb.var()
    beta = s.cov(bb) / var if var > 0 else math.nan
    alpha = ((s.mean() - rf / TRADING_DAYS) - beta * (bb.mean() - rf / TRADING_DAYS)) \
        * TRADING_DAYS
    active = s - bb
    te = active.std() * math.sqrt(TRADING_DAYS)
    ms = (1 + s).resample("ME").prod() - 1
    mb = (1 + bb).resample("ME").prod() - 1
    up, dn = mb > 0, mb < 0
    return {
        "beta": beta, "alpha": alpha, "correlation": s.corr(bb),
        "tracking_error": te,
        "information_ratio": active.mean() * TRADING_DAYS / te if te > 0 else math.nan,
        "up_capture": ms[up].mean() / mb[up].mean() if up.any() else math.nan,
        "down_capture": ms[dn].mean() / mb[dn].mean() if dn.any() else math.nan,
        "months_beating_benchmark": (ms > mb).mean(),
        "avg_return_benchmark_up_months": ms[up].mean() if up.any() else math.nan,
        "avg_return_benchmark_down_months": ms[dn].mean() if dn.any() else math.nan,
    }


def _top_drawdowns(eq: pd.Series, n: int = 8) -> list[dict]:
    dd = _drawdown(eq)
    out, in_dd, start, prev = [], False, None, dd.index[0]
    for date, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, prev
        if v == 0 and in_dd:
            seg = dd[start:date]
            out.append((start, seg.idxmin(), date, seg.min()))
            in_dd = False
        prev = date
    if in_dd:
        seg = dd[start:]
        out.append((start, seg.idxmin(), None, seg.min()))
    out.sort(key=lambda x: x[3])
    rows = []
    for st, trough, rec, depth in out[:n]:
        rows.append({"start": str(st.date()), "trough": str(trough.date()),
                     "recovery": str(rec.date()) if rec is not None else None,
                     "depth": depth,
                     "sessions_to_trough": int(len(dd[st:trough]) - 1),
                     "sessions_total": int(len(dd[st:rec]) - 1) if rec is not None else None})
    return rows


def _regimes(r: pd.Series, b: pd.Series, bench_px: pd.Series) -> dict:
    """Group daily returns by benchmark regime, each label known on that day."""
    px = bench_px.ffill()
    sma200 = px.rolling(200, min_periods=150).mean()
    slope = sma200 - sma200.shift(20)
    trend = pd.Series("Sideways", index=px.index)
    trend[(px > sma200) & (slope > 0)] = "Bull (above rising 200 DMA)"
    trend[(px < sma200) & (slope < 0)] = "Bear (below falling 200 DMA)"
    trend[sma200.isna()] = None
    trend = trend.reindex(r.index, method="ffill")

    vol21 = px.pct_change().rolling(21).std() * math.sqrt(TRADING_DAYS)
    # Expanding terciles: each day is compared only with volatility seen so far.
    lo = vol21.expanding(126).quantile(1 / 3)
    hi = vol21.expanding(126).quantile(2 / 3)
    volreg = pd.Series("Medium volatility", index=px.index)
    volreg[vol21 <= lo] = "Low volatility"
    volreg[vol21 >= hi] = "High volatility"
    volreg[lo.isna()] = None
    volreg = volreg.reindex(r.index, method="ffill")

    ddb = px / px.cummax() - 1
    ddreg = pd.Series("Near highs (<5% off)", index=px.index)
    ddreg[ddb <= -0.05] = "Pullback (5-10% off)"
    ddreg[ddb <= -0.10] = "Correction (10-20% off)"
    ddreg[ddb <= -0.20] = "Bear market (>20% off)"
    ddreg = ddreg.reindex(r.index, method="ffill")

    order = ["Bull (above rising 200 DMA)", "Sideways", "Bear (below falling 200 DMA)",
             "Near highs (<5% off)", "Pullback (5-10% off)", "Correction (10-20% off)",
             "Bear market (>20% off)", "Low volatility", "Medium volatility", "High volatility"]

    # A day's return is attributed to the regime known at the previous close.
    def table(labels: pd.Series):
        lab = labels.shift(1).reindex(r.index)
        rows = []
        for name, grp in pd.concat([r, b, lab], axis=1, keys=["s", "b", "l"]).dropna(
                subset=["l"]).groupby("l"):
            s, bb = grp["s"].astype(float), grp["b"].astype(float)
            rows.append({
                "regime": name, "sessions": int(len(grp)),
                "share_of_time": len(grp) / max(len(r), 1),
                "strategy_ann_return": s.mean() * TRADING_DAYS,
                "benchmark_ann_return": bb.mean() * TRADING_DAYS,
                "strategy_vol": s.std() * math.sqrt(TRADING_DAYS),
                "benchmark_vol": bb.std() * math.sqrt(TRADING_DAYS),
                "strategy_cum_return": float((1 + s).prod() - 1),
                "benchmark_cum_return": float((1 + bb.fillna(0)).prod() - 1),
                "hit_rate_vs_benchmark": float((s > bb).mean()),
            })
        return sorted(rows, key=lambda x: order.index(x["regime"]))

    timeline = pd.DataFrame({"trend": trend, "volatility": volreg, "drawdown": ddreg},
                            index=r.index)
    return {"trend": table(trend), "volatility": table(volreg), "benchmark_drawdown":
            table(ddreg), "_timeline": timeline}


def _episodes(eq: pd.Series, beq: pd.Series) -> list[dict]:
    rows = []
    for name, a, z in EPISODES:
        s = eq[a:z]
        b = beq[a:z]
        if len(s) < 3:
            continue
        rows.append({"episode": name, "start": a, "end": z,
                     "strategy_return": s.iloc[-1] / s.iloc[0] - 1,
                     "benchmark_return": b.iloc[-1] / b.iloc[0] - 1 if b.notna().all() else None,
                     "strategy_max_dd": float(_drawdown(s).min()),
                     "benchmark_max_dd": float(_drawdown(b.dropna()).min()) if b.notna().any()
                     else None,
                     "partial": s.index[0] > pd.Timestamp(a) + pd.Timedelta(days=7) or
                     s.index[-1] < pd.Timestamp(z) - pd.Timedelta(days=7)})
    return rows


def _rolling(r: pd.Series, b: pd.Series, window: int, rf: float) -> pd.DataFrame:
    df = pd.DataFrame({"s": r, "b": b})
    out = pd.DataFrame(index=df.index)
    out["ret_s"] = (1 + df["s"]).rolling(window).apply(np.prod, raw=True) - 1
    out["ret_b"] = (1 + df["b"]).rolling(window).apply(np.prod, raw=True) - 1
    out["vol_s"] = df["s"].rolling(window).std() * math.sqrt(TRADING_DAYS)
    out["vol_b"] = df["b"].rolling(window).std() * math.sqrt(TRADING_DAYS)
    out["sharpe_s"] = ((df["s"].rolling(window).mean() - rf / TRADING_DAYS) /
                       df["s"].rolling(window).std() * math.sqrt(TRADING_DAYS))
    out["beta"] = df["s"].rolling(window).cov(df["b"]) / df["b"].rolling(window).var()
    return out


def compute(result: dict, sectors: pd.Series | None = None, rf: float = 0.065,
            initial_cash: float | None = None,
            benchmark_history: pd.Series | None = None) -> dict:
    """benchmark_history: the benchmark's full price history, so regime indicators (200-day
    average etc.) are already warmed up when the backtest starts. Labels stay trailing-only."""
    eq_df: pd.DataFrame = result["equity"]
    eq = eq_df["equity"]
    bpx = eq_df["benchmark"].astype(float)
    r = eq.pct_change().fillna(0.0)
    b = bpx.pct_change()
    has_bench = bpx.notna().sum() > 20
    beq = (bpx / bpx.dropna().iloc[0] * eq.iloc[0]) if has_bench else pd.Series(np.nan,
                                                                                 index=eq.index)

    strat = _ratios(r, rf)
    bench = _ratios(b.fillna(0.0), rf) if has_bench else {}
    rel = _relative(r, b, rf) if has_bench else {}

    rt = pd.DataFrame(result["round_trips"])
    fills = pd.DataFrame([f.__dict__ for f in result["fills"]])
    trade_stats = {}
    if not rt.empty:
        wins, losses = rt[rt["pnl"] > 0], rt[rt["pnl"] <= 0]
        trade_stats = {
            "round_trips": int(len(rt)), "win_rate": len(wins) / len(rt),
            "avg_win_pct": wins["return_pct"].mean() if len(wins) else math.nan,
            "avg_loss_pct": losses["return_pct"].mean() if len(losses) else math.nan,
            "profit_factor": wins["pnl"].sum() / -losses["pnl"].sum()
            if losses["pnl"].sum() < 0 else math.nan,
            "avg_sessions_held": rt["sessions_held"].mean(),
            "median_sessions_held": rt["sessions_held"].median(),
            "best_trade_pct": rt["return_pct"].max(), "worst_trade_pct": rt["return_pct"].min(),
            "exit_reasons": rt["exit_reason"].value_counts().to_dict(),
        }
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    traded = fills["value"].sum() if not fills.empty else 0.0
    exposure = (eq_df["invested"] / eq_df["equity"]).replace([np.inf, -np.inf], np.nan)
    portfolio_stats = {
        "start": str(eq.index[0].date()), "end": str(eq.index[-1].date()),
        "initial_equity": float(eq.iloc[0] if initial_cash is None else initial_cash),
        "final_equity": float(eq.iloc[-1]),
        "total_fees": float(result["fees"]),
        "fees_pct_of_initial": float(result["fees"]) / float(initial_cash or eq.iloc[0]),
        "annual_turnover": traded / 2 / eq.mean() / years,
        "avg_exposure": float(exposure.mean()),
        "avg_positions": float(eq_df["positions"].mean()),
        "max_positions": int(eq_df["positions"].max()),
        "orders_filled": int(len(fills)),
    }

    # Per-symbol P&L contribution (realised + open).
    contrib = {}
    if not rt.empty:
        contrib = rt.groupby("symbol")["pnl"].sum().to_dict()
    for p in result["open_positions"]:
        contrib[p["symbol"]] = contrib.get(p["symbol"], 0.0) + p["unrealized_pnl"]
    contrib_s = pd.Series(contrib, dtype=float).sort_values()

    # Calendar tables
    m_s = (1 + r).resample("ME").prod() - 1
    m_b = (1 + b.fillna(0)).resample("ME").prod() - 1 if has_bench else None
    monthly = [{"year": d.year, "month": d.month, "strategy": v,
                "benchmark": None if m_b is None else m_b.get(d)} for d, v in m_s.items()]
    y_s = (1 + r).resample("YE").prod() - 1
    y_b = (1 + b.fillna(0)).resample("YE").prod() - 1 if has_bench else None
    yearly = [{"year": d.year, "strategy": v,
               "benchmark": None if y_b is None else y_b.get(d)} for d, v in y_s.items()]

    hist = bpx
    if benchmark_history is not None:
        hist = benchmark_history[benchmark_history.index <= eq.index[-1]]
        hist = pd.concat([hist, bpx[~bpx.index.isin(hist.index)].dropna()]).sort_index()
    regimes = _regimes(r, b, hist) if has_bench else {}
    timeline = regimes.pop("_timeline", None) if regimes else None
    roll = _rolling(r, b, TRADING_DAYS, rf)

    # Sector exposure at month ends
    sector_exposure = []
    if sectors is not None:
        for h in result["holdings"]:
            agg: dict[str, float] = {}
            for s, w in h["weights"].items():
                sec = sectors.get(s, "Unclassified") or "Unclassified"
                agg[sec] = agg.get(sec, 0.0) + w
            sector_exposure.append({"date": h["date"], "cash": h["cash"], **agg})

    step = max(1, len(eq) // 1500)  # keep charts light
    def series(s: pd.Series):
        s = s.iloc[::step] if step > 1 else s
        return [[str(d.date()), None if not np.isfinite(v) else float(v)]
                for d, v in s.items()]

    charts = {
        "equity": series(eq), "benchmark_equity": series(beq),
        "drawdown": series(_drawdown(eq)),
        "benchmark_drawdown": series(_drawdown(beq.dropna())) if has_bench else [],
        "relative": series(eq / beq) if has_bench else [],
        "exposure": series(exposure), "positions": series(eq_df["positions"].astype(float)),
        "rolling_return": series(roll["ret_s"]), "rolling_return_benchmark":
            series(roll["ret_b"]),
        "rolling_vol": series(roll["vol_s"]), "rolling_vol_benchmark": series(roll["vol_b"]),
        "rolling_sharpe": series(roll["sharpe_s"]), "rolling_beta": series(roll["beta"]),
        "daily_returns": [float(x) for x in r.iloc[1:].to_numpy()],
        "trade_returns": [float(x) for x in rt["return_pct"]] if not rt.empty else [],
    }
    if timeline is not None:
        tl = timeline.reindex(eq.index)
        charts["regime_timeline"] = [[str(d.date()), t] for d, t in
                                     tl["trend"].iloc[::step].items()]

    return {
        "summary": {"strategy": strat, "benchmark": bench, "relative": rel,
                    "trades": trade_stats, "portfolio": portfolio_stats},
        "charts": charts,
        "monthly": monthly, "yearly": yearly,
        "drawdowns": _top_drawdowns(eq),
        "benchmark_drawdowns": _top_drawdowns(beq.dropna()) if has_bench else [],
        "regimes": regimes,
        "episodes": _episodes(eq, beq) if has_bench else [],
        "contributors": {"top": [{"symbol": k, "pnl": v} for k, v in
                                 contrib_s.iloc[::-1].head(15).items()],
                         "bottom": [{"symbol": k, "pnl": v} for k, v in
                                    contrib_s.head(15).items()]},
        "sector_exposure": sector_exposure,
    }
