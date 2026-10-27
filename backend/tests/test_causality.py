"""A backtest on data that physically ends at day T must trade exactly like a backtest on
the full history, up to T. Any look-ahead (in the engine, the formula language, the
fundamentals' availability dates or a strategy helper) breaks this equality."""
import pandas as pd
import pytest

from mbt import runner
from mbt.data.store import get_market_data
from mbt.engine.engine import BacktestConfig, Engine


def _fills(res, upto):
    return [(f.date, f.symbol, f.side, f.qty, round(f.price, 6)) for f in res["fills"]
            if f.date <= upto]


@pytest.fixture(scope="module")
def md():
    try:
        return get_market_data()
    except FileNotFoundError:
        pytest.skip("no market data ingested")


# A size slice of the universe is re-ranked on fixed dates from data up to that date only.
MIDCAPS = {"type": "all", "rank": {"by": "adv_63d", "from": 101, "to": 250, "refresh": 21}}


WEEKLY = {"timeframe": "weekly"}


@pytest.mark.parametrize("sid,universe,params", [
    ("momentum:Momentum", None, {}), ("trend_breakout:TrendBreakout", None, {}),
    ("quality_value:QualityValue", None, {}), ("hb_sma_cross:HbSmaCross", MIDCAPS, {}),
    ("hb_mean_reversion:HbMeanReversion", MIDCAPS, {}), ("hb_ma_cross:HbMaCross", MIDCAPS, {}),
    # Weekly bars: the in-progress week and the week-close decision must not peek ahead.
    ("hb_sma_cross:HbSmaCross", MIDCAPS, WEEKLY), ("hb_ma_cross:HbMaCross", MIDCAPS, WEEKLY),
    ("trend_breakout:TrendBreakout", None,
     {**WEEKLY, "high_bars": 52, "trend_sma": 40, "slope_bars": 4}),
])
def test_truncated_history_gives_identical_trades(md, sid, universe, params):
    found = runner.discover()
    if sid not in found:
        pytest.skip(f"{sid} not present (private strategies are not in git)")
    cls = found[sid]["cls"]
    n = len(md.dates)
    start = md.dates[max(0, n - 600)]
    cut = n - 150                       # truncate 150 sessions before the end
    cfg = dict(start=str(start.date()), **({"universe": universe} if universe else {}))
    full = Engine(md, cls(**params), BacktestConfig(**cfg)).run()
    short_md = md.truncated(cut)
    short = Engine(short_md, cls(**params), BacktestConfig(**cfg)).run()
    upto = md.dates[cut]
    assert _fills(full, upto) == _fills(short, upto)
    eq_full = full["equity"]["equity"][:upto]
    pd.testing.assert_series_equal(eq_full, short["equity"]["equity"][:upto])


def test_formulas_never_read_the_future(md):
    from mbt.formula import Evaluator
    k = len(md.dates) - 100
    short = md.truncated(k)
    exprs = ["ret_1y", "sma(close, 50) / close", "rsi_14", "pe", "roe", "lag(mcap, 21)",
             "highest(high, 252)", "beta_1y", "rank(ret_6m) + sector_rank(-pe)",
             "q_revenue_yoy", "ema(close, 20)", "weekly(sma(close, 50))",
             "weekly(lag(sma(close, 10), 1))", "weekly(highest(high, 52))",
             "weekly(ema(close, 20))", "weekly(rsi(close, 14))", "weekly(sma(volume, 10))"]
    a, b = Evaluator(md), Evaluator(short)
    for e in exprs:
        x, y = a.eval(e, k), b.eval(e, k)
        pd.testing.assert_series_equal(pd.Series(x, dtype=float), pd.Series(y, dtype=float),
                                       check_names=False, obj=e)
