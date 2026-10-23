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


@pytest.mark.parametrize("sid", ["momentum:Momentum", "trend_breakout:TrendBreakout",
                                 "quality_value:QualityValue"])
def test_truncated_history_gives_identical_trades(md, sid):
    cls = runner.discover()[sid]["cls"]
    n = len(md.dates)
    start = md.dates[max(0, n - 600)]
    cut = n - 150                       # truncate 150 sessions before the end
    full = Engine(md, cls(), BacktestConfig(start=str(start.date()))).run()
    short_md = md.truncated(cut)
    short = Engine(short_md, cls(), BacktestConfig(start=str(start.date()))).run()
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
             "q_revenue_yoy", "ema(close, 20)"]
    a, b = Evaluator(md), Evaluator(short)
    for e in exprs:
        x, y = a.eval(e, k), b.eval(e, k)
        pd.testing.assert_series_equal(pd.Series(x, dtype=float), pd.Series(y, dtype=float),
                                       check_names=False, obj=e)
