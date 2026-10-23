"""FastAPI app: screener, universes, strategies, backtests and data management."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, ingest, runner, screener
from .data import indices
from .data.store import get_market_data
from .formula import Evaluator, FormulaError, describe
from .runner import _clean

app = FastAPI(title="Markets Backtester")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


def _md():
    try:
        return get_market_data()
    except FileNotFoundError:
        raise HTTPException(503, "No price data yet. Run an ingest from the Data page "
                                 "or `uv run mbt ingest prices`.")


# ------------------------------------------------------------------ data

@app.get("/api/status")
def status():
    out = {"ingest": ingest.last_runs(), "jobs": list(ingest.JOBS.values()),
           "benchmarks": indices.available(),
           "report_lag_days": {"quarterly": config.QUARTERLY_REPORT_LAG_DAYS,
                               "annual": config.ANNUAL_REPORT_LAG_DAYS},
           "tickertape_cookie": bool(config.TICKERTAPE_COOKIE)}
    try:
        md = get_market_data()
    except FileNotFoundError:
        return {**out, "loaded": False}
    listed = md.listed_mask(md.last_index, include_sme=True)
    fund = {}
    for f in ("revenue", "net_income", "total_equity", "q_revenue"):
        if f in md.fundamental_fields:
            ff = md._fund[f]
            fund[f] = {"first_available": str(md.dates[int(ff.avail_idx.min())].date()),
                       "companies": int(len(np.unique(ff.sym_idx)))}
    return {**out, "loaded": True, "start": str(md.dates[0].date()),
            "end": str(md.dates[-1].date()), "sessions": len(md.dates),
            "symbols_total": len(md.symbols), "listed_now": int(listed.sum()),
            "delisted_or_inactive": int(len(md.symbols) - listed.sum()),
            "fundamentals": fund}


@app.post("/api/ingest")
def start_ingest(steps: list[str] = Body(...), start: str | None = Body(None)):
    bad = set(steps) - set(ingest.STEPS)
    if bad:
        raise HTTPException(400, f"Unknown steps {bad}")
    try:
        return {"job": ingest.start_job(steps, start)}
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if job_id not in ingest.JOBS:
        raise HTTPException(404)
    return ingest.JOBS[job_id]


# ------------------------------------------------------------------ metrics & screener

@app.get("/api/metrics")
def metrics():
    md = _md()
    d = describe(md)
    d["metrics"] += screener.live_fields()
    return d


@app.post("/api/formula/validate")
def validate(formula: str = Body(..., embed=True), live: bool = Body(False, embed=True)):
    md = _md()
    ev = screener.evaluator(md, md.last_index, live)
    try:
        ev.validate(formula)
        v = np.asarray(ev.eval(formula, md.last_index))
        listed = md.listed_mask(md.last_index, include_sme=True)
        if v.dtype == bool:
            return {"ok": True, "passing": int((v & listed).sum())}
        if v.dtype == object:
            return {"ok": True}
        return {"ok": True, "non_missing": int((np.isfinite(v.astype(float)) & listed).sum())}
    except FormulaError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # numeric edge cases in user formulas
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@app.post("/api/screen")
def screen(spec: dict = Body(...)):
    md = _md()
    try:
        res = screener.run_screen(md, spec.get("screen", {}), spec.get("as_of"),
                                  bool(spec.get("live")))
    except FormulaError as e:
        raise HTTPException(400, str(e))
    t = res.table.replace([np.inf, -np.inf], np.nan)
    return _clean({"date": str(res.date.date()), "count": int(res.mask.sum()),
                   "columns": list(t.columns),
                   "rows": t.astype(object).where(t.notna(), None).to_dict("records")})


for _kind in ("screens", "universes"):
    def _make(kind):
        @app.get(f"/api/{kind}", name=f"list_{kind}")
        def _list():
            return screener.list_items(kind)

        @app.post(f"/api/{kind}", name=f"save_{kind}")
        def _save(item: dict = Body(...)):
            return screener.save_item(kind, item)

        @app.delete(f"/api/{kind}/{{item_id}}", name=f"delete_{kind}")
        def _delete(item_id: str):
            screener.delete_item(kind, item_id)
            return {"ok": True}
    _make(_kind)


@app.get("/api/symbols")
def symbols(q: str = "", limit: int = 20):
    md = _md()
    sec = md.securities
    listed = md.listed_mask(md.last_index, include_sme=True)
    df = pd.DataFrame({"symbol": md.symbols, "name": sec["name"].to_numpy(object),
                       "sector": sec["sector"].to_numpy(object), "listed": listed})
    if q:
        ql = q.lower()
        hit = df["symbol"].str.lower().str.startswith(ql) | \
            df["name"].fillna("").str.lower().str.contains(re.escape(ql))
        df = df[hit].assign(_exact=df["symbol"].str.lower() != ql,
                            _listed=~df["listed"]).sort_values(["_exact", "_listed", "symbol"])
    return df.head(limit)[["symbol", "name", "sector", "listed"]].to_dict("records")


@app.get("/api/stock/{symbol}")
def stock(symbol: str, start: str | None = None):
    md = _md()
    if symbol not in md.symbols:
        raise HTTPException(404, "Unknown symbol")
    j = md.symbols.get_loc(symbol)
    i0 = md.index_of(start, "left") if start else 0
    c = md.panel("close")[i0:, j]
    v = md.panel("volume")[i0:, j]
    ok = np.isfinite(c)
    dates = md.dates[i0:][ok]
    ev = Evaluator(md)
    i = md.last_index
    keys = ["mcap", "pe", "pb", "ps", "ev_ebitda", "roe", "roce", "net_margin", "debt_equity",
            "div_yield", "revenue", "net_income", "revenue_growth", "eps_growth", "ret_1m",
            "ret_6m", "ret_1y", "vol_1y", "beta_1y", "adv_20d", "pct_from_52w_high"]
    snap = {k: float(np.asarray(ev.eval(k, i))[j]) for k in keys}
    sec = md.securities.loc[symbol]
    return _clean({"symbol": symbol, "name": sec.get("name"), "sector": sec.get("sector"),
                   "industry": sec.get("industry"),
                   "prices": [[str(d.date()), float(x), float(y)] for d, x, y in
                              zip(dates, c[ok], np.nan_to_num(v[ok]))],
                   "metrics": snap})


@app.get("/api/benchmarks")
def benchmarks():
    return indices.available()


# ------------------------------------------------------------------ strategies

TEMPLATE = '''"""Describe your strategy here."""
from mbt.engine.strategy import Strategy


class MyStrategy(Strategy):
    name = "My strategy"
    description = "Buys the top N stocks by a score every month."
    params = {"top_n": 20, "score": "ret_12m_1m"}
    schedule = "monthly"

    def on_bar(self, ctx):
        score = ctx.eval(self.p.score).dropna()
        picks = score.nlargest(self.p.top_n).index
        ctx.rebalance({s: 1 / len(picks) for s in picks} if len(picks) else {})
'''


def _strategy_path(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z_][\w]*\.py", name):
        raise HTTPException(400, "File name must look like my_strategy.py")
    return config.STRATEGY_DIR / name


@app.get("/api/strategies")
def strategies():
    return runner.describe_strategies()


@app.get("/api/strategies/{file}/source")
def strategy_source(file: str):
    p = _strategy_path(file)
    if not p.exists():
        raise HTTPException(404)
    return {"file": file, "source": p.read_text()}


@app.put("/api/strategies/{file}/source")
def save_strategy(file: str, source: str = Body(..., embed=True)):
    p = _strategy_path(file)
    try:
        compile(source, file, "exec")
    except SyntaxError as e:
        raise HTTPException(400, f"Syntax error line {e.lineno}: {e.msg}")
    p.write_text(source)
    return {"ok": True}


@app.post("/api/strategies/{file}")
def new_strategy(file: str):
    p = _strategy_path(file)
    if p.exists():
        raise HTTPException(409, "File exists")
    p.write_text(TEMPLATE)
    return {"ok": True}


@app.get("/api/strategy-guide")
def strategy_guide():
    from .engine import context, strategy
    import inspect
    methods = []
    for name, fn in inspect.getmembers(context.Context):
        if name.startswith("_"):
            continue
        doc = inspect.getdoc(fn) or ""
        sig = ""
        if inspect.isfunction(fn):
            sig = str(inspect.signature(fn)).replace("self, ", "").replace("(self)", "()")
        methods.append({"name": name, "signature": sig, "doc": doc})
    return {"overview": inspect.getdoc(strategy), "ctx": methods}


# ------------------------------------------------------------------ backtests

@app.post("/api/backtests")
def start_backtest(req: dict = Body(...)):
    try:
        run_id = runner.start_run(req["strategy_id"], req.get("params") or {},
                                  dict(req.get("config") or {}))
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(400, str(e))
    return {"id": run_id}


@app.get("/api/backtests")
def backtests():
    return runner.list_runs()


@app.get("/api/backtests/{run_id}")
def backtest_status(run_id: str):
    try:
        return runner.run_status(run_id)
    except KeyError:
        raise HTTPException(404)


@app.get("/api/backtests/{run_id}/result")
def backtest_result(run_id: str):
    try:
        return Response(runner.run_result(run_id), media_type="application/json")
    except KeyError:
        raise HTTPException(404)


@app.delete("/api/backtests/{run_id}")
def delete_backtest(run_id: str):
    runner.delete_run(run_id)
    return {"ok": True}


# ------------------------------------------------------------------ frontend (built)

_DIST = config.ROOT / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _DIST / path
        return FileResponse(f if path and f.is_file() else _DIST / "index.html")
