"""Cross-sectional formula language used by the screener and by strategies.

A formula is a Python-like expression evaluated *as of* a trading-day index i, producing one
value per symbol. Example:

    roe > 15 and pe < sector_median(pe) and ret_6m > 0 and rank(-pe) > 50

Grammar (parsed with `ast`, whitelist only -- no attribute access, no arbitrary calls):
  numbers, strings, + - * / ** %, comparisons, and/or/not (element-wise), `x if c else y`,
  metric names (see METRICS / `describe()`), and the functions in FUNCTIONS.

Time-series functions such as sma(close, 50) or lag(pe, 63) evaluate their argument at
earlier indices only; nothing can read beyond i.
"""
from __future__ import annotations

import ast
import math
import warnings
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .data.store import PRICE_FIELDS, QUARTERLY_INCOME, MarketData

Arr = np.ndarray
# Windows over not-yet-listed / suspended stocks are legitimately all-NaN.
warnings.filterwarnings("ignore", category=RuntimeWarning, module=r"mbt\.formula")


# --------------------------------------------------------------------------- metrics

@dataclass(frozen=True)
class Metric:
    name: str
    category: str
    description: str
    fn: Callable[["Evaluator", int], Arr]
    unit: str = ""


METRICS: dict[str, Metric] = {}


def metric(name, category, description, unit=""):
    def deco(fn):
        METRICS[name] = Metric(name, category, description, fn, unit)
        return fn
    return deco


def _safe_div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.asarray(a, float) / np.asarray(b, float)
    out[~np.isfinite(out)] = np.nan
    return out


def _ret(ev, i, n):
    c = ev.md.close_ffill
    if i - n < 0:
        return np.full(c.shape[1], np.nan)
    return (_safe_div(c[i], c[i - n]) - 1) * 100


# Price & volume
for _f in PRICE_FIELDS:
    METRICS[_f] = Metric(_f, "Price & Volume",
                         {"value": "Traded value today (Rs)",
                          "volume": "Shares traded today"}.get(_f, f"Today's {_f} (adjusted)"),
                         (lambda f: lambda ev, i: ev.md.panel(f)[i].astype(float))(_f),
                         "Rs" if _f != "volume" else "")

for _n, _d in {"1d": 1, "1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756,
               "5y": 1260}.items():
    METRICS[f"ret_{_n}"] = Metric(f"ret_{_n}", "Returns", f"Price return over {_n} (%)",
                                  (lambda n: lambda ev, i: _ret(ev, i, n))(_d), "%")


@metric("ret_12m_1m", "Returns", "12-month return skipping the latest month (momentum, %)", "%")
def _mom(ev, i):
    c = ev.md.close_ffill
    if i - 252 < 0:
        return np.full(c.shape[1], np.nan)
    return (_safe_div(c[i - 21], c[i - 252]) - 1) * 100


@metric("vol_1y", "Risk", "Annualised volatility of daily returns, 1y (%)", "%")
def _vol(ev, i):
    w = ev.md.window("close_ffill", i, 253).astype(float)
    r = np.diff(np.log(w), axis=0)
    ok = np.isfinite(r).sum(0) >= 150
    with np.errstate(invalid="ignore"):
        v = np.nanstd(r, axis=0) * math.sqrt(252) * 100
    return np.where(ok, v, np.nan)


@metric("beta_1y", "Risk", "Beta vs NIFTY 50 over 1y of daily returns")
def _beta(ev, i):
    b = ev.benchmark_close("NIFTY50")
    w = ev.md.window("close_ffill", i, 253).astype(float)
    if b is None or len(w) < 100:
        return np.full(w.shape[1], np.nan)
    bw = b[max(0, i - 252): i + 1]
    r = np.diff(np.log(w), axis=0)
    rb = np.diff(np.log(bw))[:, None]
    m = np.isfinite(r) & np.isfinite(rb)
    rbm = np.where(m, rb, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = np.nanmean((r - np.nanmean(np.where(m, r, np.nan), 0)) *
                         (rbm - np.nanmean(rbm, 0)), 0)
        var = np.nanvar(rbm, 0)
    out = cov / var
    out[m.sum(0) < 150] = np.nan
    return out


@metric("high_52w", "Price & Volume", "52-week high (Rs)", "Rs")
def _h52(ev, i):
    with np.errstate(all="ignore"):
        return np.nanmax(ev.md.window("high", i, 252), axis=0).astype(float)


@metric("low_52w", "Price & Volume", "52-week low (Rs)", "Rs")
def _l52(ev, i):
    with np.errstate(all="ignore"):
        return np.nanmin(ev.md.window("low", i, 252), axis=0).astype(float)


@metric("pct_from_52w_high", "Price & Volume", "% below the 52-week high (0 = at high)", "%")
def _p52(ev, i):
    return (_safe_div(ev.md.close_ffill[i], _h52(ev, i)) - 1) * 100


@metric("adv_20d", "Liquidity", "Average daily traded value, 20 sessions (Rs crore)", "Cr")
def _adv20(ev, i):
    with np.errstate(all="ignore"):
        return np.nanmean(ev.md.window("value", i, 20), axis=0) / 1e7


@metric("adv_63d", "Liquidity", "Average daily traded value, 63 sessions (Rs crore)", "Cr")
def _adv63(ev, i):
    with np.errstate(all="ignore"):
        return np.nanmean(ev.md.window("value", i, 63), axis=0) / 1e7


@metric("days_traded_63d", "Liquidity", "Sessions traded out of the last 63")
def _dt63(ev, i):
    return np.isfinite(ev.md.window("close", i, 63)).sum(0).astype(float)


@metric("rsi_14", "Technical", "Wilder RSI(14) on close")
def _rsi14(ev, i):
    return _rsi(ev, i, 14)


@metric("age_days", "Liquidity", "Sessions since first trade on NSE (within loaded history)")
def _age(ev, i):
    c = np.isfinite(ev.md.panel("close")[: i + 1])
    first = np.where(c.any(0), c.argmax(0), i + 1)
    return (i - first).astype(float)


# Fundamentals (point in time). Statement items are added dynamically in Evaluator.
FUNDAMENTAL_DOCS = {
    "revenue": "Revenue, TTM where 4 quarters known else last FY (Rs Cr)",
    "ebitda": "EBITDA, TTM/last FY (Rs Cr)", "ebit": "EBIT, TTM/last FY (Rs Cr)",
    "net_income": "Net profit, TTM/last FY (Rs Cr)", "eps": "EPS, TTM/last FY (Rs)",
    "pbt": "Profit before tax, TTM/last FY (Rs Cr)", "dps": "Dividend per share, last FY (Rs)",
    "interest": "Interest expense, last FY (Rs Cr)", "tax": "Tax, last FY (Rs Cr)",
    "depreciation": "D&A, last FY (Rs Cr)",
    "total_assets": "Total assets (Rs Cr)", "total_equity": "Shareholders' equity (Rs Cr)",
    "total_debt": "Total debt (Rs Cr)", "cash": "Cash & short-term investments (Rs Cr)",
    "current_assets": "Current assets (Rs Cr)", "current_liabilities": "Current liabilities",
    "shares": "Shares outstanding (crore)", "minority_interest": "Minority interest (Rs Cr)",
    "total_liabilities": "Total liabilities (Rs Cr)", "receivables": "Receivables (Rs Cr)",
    "inventory": "Inventory (Rs Cr)", "net_ppe": "Net PP&E (Rs Cr)",
    "cfo": "Cash from operations, last FY (Rs Cr)", "capex": "Capex, last FY (Rs Cr)",
    "cfi": "Cash from investing (Rs Cr)", "cff": "Cash from financing (Rs Cr)",
    "fcf": "Free cash flow, last FY (Rs Cr)", "dividends_paid": "Dividends paid (Rs Cr)",
    "revenue_growth": "Revenue growth, last FY vs prior FY (%)",
    "net_income_growth": "Net profit growth, last FY vs prior FY (%)",
    "eps_growth": "EPS growth, last FY vs prior FY (%)",
    "ebitda_growth": "EBITDA growth, last FY vs prior FY (%)",
}


for _q in QUARTERLY_INCOME.values():
    FUNDAMENTAL_DOCS[f"q_{_q}"] = f"Latest quarter {_q.replace('_', ' ')} (Rs Cr)"
    FUNDAMENTAL_DOCS[f"q_{_q}_yoy"] = f"Latest quarter {_q.replace('_', ' ')} vs same quarter " \
                                      "last year (%)"


def _f(ev, i, name):
    return ev.md.fundamental(name, i)


@metric("mcap", "Valuation", "Market cap (Rs Cr) = close x shares", "Cr")
def _mcap(ev, i):
    sh = _f(ev, i, "shares")
    alt = _safe_div(_f(ev, i, "net_income"), _f(ev, i, "eps"))
    sh = np.where(np.isfinite(sh) & (sh > 0), sh, alt)
    return ev.md.close_ffill[i] * sh


def _ratio(name, cat, desc, num, den, scale=1.0, positive_den=True, unit=""):
    def fn(ev, i):
        n = num(ev, i)
        d = den(ev, i)
        if positive_den:
            d = np.where(d > 0, d, np.nan)
        return _safe_div(n, d) * scale
    METRICS[name] = Metric(name, cat, desc, fn, unit)


F = lambda n: (lambda ev, i: _f(ev, i, n))  # noqa: E731
_ev_fn = lambda ev, i: _mcap(ev, i) + np.nan_to_num(_f(ev, i, "total_debt")) \
    - np.nan_to_num(_f(ev, i, "cash"))  # noqa: E731
METRICS["ev"] = Metric("ev", "Valuation", "Enterprise value = mcap + debt - cash (Rs Cr)",
                       _ev_fn, "Cr")
_ratio("pe", "Valuation", "Price / earnings (TTM)", _mcap, F("net_income"))
_ratio("pb", "Valuation", "Price / book", _mcap, F("total_equity"))
_ratio("ps", "Valuation", "Price / sales (TTM)", _mcap, F("revenue"))
_ratio("ev_ebitda", "Valuation", "EV / EBITDA (TTM)", _ev_fn, F("ebitda"))
_ratio("ev_sales", "Valuation", "EV / sales (TTM)", _ev_fn, F("revenue"))
_ratio("p_fcf", "Valuation", "Price / free cash flow", _mcap, F("fcf"))
_ratio("earnings_yield", "Valuation", "Net income / mcap (%)", F("net_income"), _mcap, 100,
       unit="%")
_ratio("fcf_yield", "Valuation", "FCF / mcap (%)", F("fcf"), _mcap, 100, unit="%")
_ratio("div_yield", "Valuation", "Dividend per share / price (%)", F("dps"),
       lambda ev, i: ev.md.close_ffill[i], 100, unit="%")
_ratio("roe", "Profitability", "Net income / equity (%)", F("net_income"), F("total_equity"),
       100, unit="%")
_ratio("roa", "Profitability", "Net income / total assets (%)", F("net_income"),
       F("total_assets"), 100, unit="%")
_ratio("roce", "Profitability", "EBIT / (assets - current liabilities) (%)", F("ebit"),
       lambda ev, i: _f(ev, i, "total_assets") - np.nan_to_num(_f(ev, i, "current_liabilities")),
       100, unit="%")
_ratio("net_margin", "Profitability", "Net income / revenue (%)", F("net_income"),
       F("revenue"), 100, unit="%")
_ratio("ebitda_margin", "Profitability", "EBITDA / revenue (%)", F("ebitda"), F("revenue"),
       100, unit="%")
_ratio("debt_equity", "Financial health", "Total debt / equity", F("total_debt"),
       F("total_equity"))
_ratio("current_ratio", "Financial health", "Current assets / current liabilities",
       F("current_assets"), F("current_liabilities"))
_ratio("interest_cover", "Financial health", "EBIT / interest", F("ebit"), F("interest"))
_ratio("asset_turnover", "Efficiency", "Revenue / total assets", F("revenue"),
       F("total_assets"))
_ratio("cfo_to_profit", "Quality", "Cash from operations / net income", F("cfo"),
       F("net_income"))
_ratio("payout_ratio", "Quality", "Dividends per share / EPS (%)", F("dps"), F("eps"), 100,
       unit="%")


# --------------------------------------------------------------------------- functions

def _rsi(ev, i, n):
    w = ev.md.window("close_ffill", i, n * 6).astype(float)
    d = np.diff(w, axis=0)
    if len(d) < n:
        return np.full(w.shape[1], np.nan)
    up, dn = np.clip(d, 0, None), np.clip(-d, 0, None)
    up, dn = np.nan_to_num(up), np.nan_to_num(dn)
    au, ad = up[:n].mean(0), dn[:n].mean(0)
    for k in range(n, len(d)):
        au = (au * (n - 1) + up[k]) / n
        ad = (ad * (n - 1) + dn[k]) / n
    rs = _safe_div(au, ad)
    out = 100 - 100 / (1 + rs)
    out[(ad == 0) & (au > 0)] = 100
    out[np.isfinite(w).sum(0) < n + 1] = np.nan
    return out


def _xs_rank(x):
    s = pd.Series(np.asarray(x, float))
    return (s.rank(pct=True) * 100).to_numpy()


def _xs_z(x):
    x = np.asarray(x, float)
    with np.errstate(invalid="ignore"):
        return (x - np.nanmean(x)) / np.nanstd(x)


class FormulaError(ValueError):
    pass


class Evaluator:
    """Evaluates formulas at index i over the given symbol mask."""

    TS_FUNCS = {"sma", "ema", "std", "highest", "lowest", "lag", "change", "pct_change",
                "sum", "mean_n"}

    def __init__(self, md: MarketData, extra: dict[str, Arr] | None = None):
        self.md = md
        self.extra = extra or {}       # e.g. live Tickertape fields (screener "today" only)
        self._cache: dict[tuple, Arr] = {}
        self._parsed: dict[str, ast.AST] = {}

    def benchmark_close(self, name: str):
        s = self.md.benchmarks.get(name)
        if s is None:
            return None
        return s.reindex(self.md.dates).ffill().to_numpy(float)

    # ---- public ----
    def names(self) -> set[str]:
        return set(METRICS) | set(FUNDAMENTAL_DOCS) | set(self.md.fundamental_fields) | \
            set(self.extra) | {"sector", "industry", "symbol"}

    def eval(self, formula: str, i: int) -> Arr:
        tree = self._parse(formula)
        out = self._ev(tree.body, i)
        if np.isscalar(out) or np.ndim(out) == 0:
            out = np.full(len(self.md.symbols), out)
        return out

    def validate(self, formula: str) -> None:
        tree = self._parse(formula)
        funcs = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and id(node) not in funcs and \
                    node.id not in self.names() and node.id not in ("True", "False", "nan"):
                raise FormulaError(f"Unknown metric '{node.id}'")

    # ---- internals ----
    def _parse(self, formula: str) -> ast.Expression:
        if formula not in self._parsed:
            try:
                tree = ast.parse(formula.strip(), mode="eval")
            except SyntaxError as e:
                raise FormulaError(f"Syntax error: {e.msg} at col {e.offset}") from None
            for node in ast.walk(tree):
                if not isinstance(node, _ALLOWED_NODES):
                    raise FormulaError(f"'{type(node).__name__}' is not allowed in formulas")
                if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or
                                                   node.func.id not in FUNCTIONS):
                    fname = getattr(node.func, "id", "?")
                    raise FormulaError(f"Unknown function '{fname}'. Available: "
                                       + ", ".join(sorted(FUNCTIONS)))
            self._parsed[formula] = tree
        return self._parsed[formula]

    def name_value(self, name: str, i: int):
        key = (name, i)
        if key in self._cache:
            return self._cache[key]
        if name in self.extra:
            v = self.extra[name]
        elif name in ("sector", "industry"):
            v = self.md.securities[name].to_numpy(object)
        elif name == "symbol":
            v = self.md.symbols.to_numpy(object)
        elif name in METRICS:
            v = METRICS[name].fn(self, i)
        elif name in self.md.fundamental_fields or name in FUNDAMENTAL_DOCS:
            v = self.md.fundamental(name, i)  # all-NaN until the data exists
        else:
            raise FormulaError(f"Unknown metric '{name}'")
        if len(self._cache) > 4000:
            self._cache.clear()
        self._cache[key] = v
        return v

    def _ev(self, node, i):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, str, bool)):
                return node.value
            raise FormulaError("Unsupported constant")
        if isinstance(node, ast.Name):
            if node.id in ("True", "False"):
                return node.id == "True"
            if node.id == "nan":
                return np.nan
            return self.name_value(node.id, i)
        if isinstance(node, ast.BinOp):
            a, b = self._ev(node.left, i), self._ev(node.right, i)
            with np.errstate(all="ignore"):
                if isinstance(node.op, ast.Div):
                    return _safe_div(a, b)
                return _BINOPS[type(node.op)](np.asarray(a, float), np.asarray(b, float))
        if isinstance(node, ast.UnaryOp):
            v = self._ev(node.operand, i)
            if isinstance(node.op, ast.Not):
                return ~_truthy(v)
            return -np.asarray(v, float) if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BoolOp):
            vals = [_truthy(self._ev(v, i)) for v in node.values]
            out = vals[0]
            for v in vals[1:]:
                out = (out & v) if isinstance(node.op, ast.And) else (out | v)
            return out
        if isinstance(node, ast.Compare):
            left = self._ev(node.left, i)
            out = None
            for op, comp in zip(node.ops, node.comparators):
                right = self._ev(comp, i)
                r = _compare(op, left, right)
                out = r if out is None else out & r
                left = right
            return out
        if isinstance(node, (ast.Tuple, ast.List)):
            return [self._ev(e, i) for e in node.elts]
        if isinstance(node, ast.IfExp):
            c = _truthy(self._ev(node.test, i))
            return np.where(c, self._ev(node.body, i), self._ev(node.orelse, i))
        if isinstance(node, ast.Call):
            name = node.func.id
            if name in self.TS_FUNCS:
                return self._ts(name, node.args, i)
            if name == "rsi":
                n = int(self._const(node.args[1])) if len(node.args) > 1 else 14
                return _rsi(self, i, n)
            if name in ("sector_rank", "industry_rank", "sector_median", "industry_median",
                        "sector_mean", "industry_mean"):
                return self._group(name, self._ev(node.args[0], i), i)
            args = [self._ev(a, i) for a in node.args]
            return FUNCTIONS[name](*args)
        raise FormulaError(f"Unsupported expression {type(node).__name__}")

    def _const(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self._const(node.operand)
        raise FormulaError("Window lengths must be numeric constants")

    def _ts(self, name, args, i):
        if len(args) != 2:
            raise FormulaError(f"{name}(x, n) takes 2 arguments")
        n = int(self._const(args[1]))
        if n < 1 or n > 5000:
            raise FormulaError("Window must be between 1 and 5000")
        x = args[0]
        if name in ("lag", "change", "pct_change"):
            if i - n < 0:
                return np.full(len(self.md.symbols), np.nan)
            now, then = self._ev(x, i), self._ev(x, i - n)
            if name == "lag":
                return then
            if name == "change":
                return np.asarray(now, float) - np.asarray(then, float)
            return (_safe_div(now, then) - 1) * 100
        # windowed aggregates: fast path for raw price panels, generic path otherwise
        if isinstance(x, ast.Name) and x.id in PRICE_FIELDS:
            w = self.md.window("close_ffill" if x.id == "close" else x.id, i, n).astype(float)
        else:
            w = np.vstack([np.asarray(self._ev(x, j), float)
                           for j in range(max(0, i - n + 1), i + 1)])
        with np.errstate(all="ignore"):
            if len(w) < n and name != "ema":
                return np.full(w.shape[1], np.nan)
            if name in ("sma", "mean_n"):
                return np.nanmean(w, 0)
            if name == "sum":
                return np.nansum(w, 0)
            if name == "std":
                return np.nanstd(w, 0, ddof=1)
            if name == "highest":
                return np.nanmax(w, 0)
            if name == "lowest":
                return np.nanmin(w, 0)
            if name == "ema":
                # seed with enough history for the EMA to converge (~4n bars)
                if isinstance(x, ast.Name) and x.id in PRICE_FIELDS:
                    w = self.md.window("close_ffill" if x.id == "close" else x.id, i,
                                       4 * n).astype(float)
                a = 2 / (n + 1)
                e = w[0].copy()
                for row in w[1:]:
                    e = np.where(np.isfinite(row), np.where(np.isfinite(e), a * row +
                                                            (1 - a) * e, row), e)
                return e
        raise FormulaError(name)

    def _group(self, name, x, i):
        col = "sector" if name.startswith("sector") else "industry"
        g = self.md.securities[col].to_numpy(object)
        s = pd.Series(np.asarray(x, float))
        grp = s.groupby(g)
        if name.endswith("rank"):
            return (grp.rank(pct=True) * 100).to_numpy()
        return grp.transform("median" if name.endswith("median") else "mean").to_numpy()


def _truthy(v):
    a = np.asarray(v)
    if a.dtype == bool:
        return a
    with np.errstate(invalid="ignore"):
        return np.nan_to_num(a.astype(float)) != 0


def _compare(op, a, b):
    if isinstance(a, str) or isinstance(b, str) or \
            (isinstance(a, np.ndarray) and a.dtype == object) or \
            (isinstance(b, np.ndarray) and b.dtype == object):
        a, b = np.asarray(a, object), np.asarray(b, object)
        if isinstance(op, ast.Eq):
            return a == b
        if isinstance(op, ast.NotEq):
            return a != b
        if isinstance(op, ast.In):
            return np.isin(a, list(np.atleast_1d(b)))
        raise FormulaError("Only == / != work on text fields")
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(invalid="ignore"):
        return _CMPOPS[type(op)](a, b) & np.isfinite(a) & np.isfinite(b)


_BINOPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply,
           ast.Pow: np.power, ast.Mod: np.mod, ast.FloorDiv: np.floor_divide}
_CMPOPS = {ast.Gt: np.greater, ast.GtE: np.greater_equal, ast.Lt: np.less,
           ast.LtE: np.less_equal, ast.Eq: np.equal, ast.NotEq: np.not_equal}
_ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
                  ast.Call, ast.Name, ast.Constant, ast.Load, ast.And, ast.Or, ast.Not,
                  ast.USub, ast.UAdd, *_BINOPS, *_CMPOPS, ast.Div, ast.In, ast.Tuple,
                  ast.List)

FUNCTIONS: dict[str, Callable] = {
    "abs": lambda x: np.abs(np.asarray(x, float)),
    "log": lambda x: np.log(np.where(np.asarray(x, float) > 0, x, np.nan)),
    "sqrt": lambda x: np.sqrt(np.where(np.asarray(x, float) >= 0, x, np.nan)),
    "min": lambda *a: np.fmin.reduce([np.asarray(x, float) for x in a]),
    "max": lambda *a: np.fmax.reduce([np.asarray(x, float) for x in a]),
    "clip": lambda x, lo, hi: np.clip(np.asarray(x, float), lo, hi),
    "fillna": lambda x, v: np.where(np.isfinite(np.asarray(x, float)), x, v),
    "isnan": lambda x: ~np.isfinite(np.asarray(x, float)),
    "where": lambda c, a, b: np.where(_truthy(c), a, b),
    "rank": _xs_rank,
    "zscore": _xs_z,
    # These are dispatched inside Evaluator but must be listed here to pass validation:
    **{k: None for k in ("sma", "ema", "std", "highest", "lowest", "lag", "change",
                         "pct_change", "sum", "mean_n", "rsi", "sector_rank", "industry_rank",
                         "sector_median", "industry_median", "sector_mean", "industry_mean")},
}

FUNCTION_DOCS = {
    "abs(x)": "Absolute value", "log(x)": "Natural log", "sqrt(x)": "Square root",
    "min(a, b, ...)": "Element-wise minimum", "max(a, b, ...)": "Element-wise maximum",
    "clip(x, lo, hi)": "Bound x to [lo, hi]", "fillna(x, v)": "Replace missing with v",
    "isnan(x)": "True where x is missing", "where(cond, a, b)": "a where cond else b",
    "rank(x)": "Cross-sectional percentile rank 0-100 (100 = highest)",
    "zscore(x)": "Cross-sectional z-score",
    "sector_rank(x)": "Percentile rank within sector", "industry_rank(x)": "Rank in industry",
    "sector_median(x)": "Sector median of x", "industry_median(x)": "Industry median of x",
    "sector_mean(x)": "Sector mean of x", "industry_mean(x)": "Industry mean of x",
    "sma(x, n)": "Mean of x over the last n sessions", "ema(x, n)": "Exponential average",
    "std(x, n)": "Std-dev over n sessions", "highest(x, n)": "Max over n sessions",
    "lowest(x, n)": "Min over n sessions", "sum(x, n)": "Sum over n sessions",
    "lag(x, n)": "x as it was n sessions ago", "change(x, n)": "x - lag(x, n)",
    "pct_change(x, n)": "% change of x over n sessions", "rsi(close, n)": "Wilder RSI",
}


def describe(md: MarketData | None = None) -> dict:
    ms = [{"name": m.name, "category": m.category, "description": m.description,
           "unit": m.unit} for m in METRICS.values()]
    if md is not None:
        for f in sorted(set(md.fundamental_fields) | set(FUNDAMENTAL_DOCS)):
            if f not in METRICS:
                cat = "Quarterly" if f.startswith("q_") else "Fundamentals"
                ms.append({"name": f, "category": cat,
                           "description": FUNDAMENTAL_DOCS.get(f, f.replace("_", " ")),
                           "unit": "%" if f.endswith(("growth", "yoy")) else ""})
    ms += [{"name": "sector", "category": "Classification", "description": "Sector (text)",
            "unit": ""},
           {"name": "industry", "category": "Classification",
            "description": "Sub-sector (text)", "unit": ""}]
    return {"metrics": ms, "functions": [{"signature": k, "description": v}
                                         for k, v in FUNCTION_DOCS.items()]}
