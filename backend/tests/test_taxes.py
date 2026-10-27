"""Capital-gains rules: rates by sale date, holding period, grandfathering, set-off order,
the LTCG exemption and loss carry-forward."""
import math

import pytest

from mbt.engine.taxes import TaxBook, TaxModel, asset_class


def rt(sym, buy, sell, qty, buy_px, sell_px):
    return {"symbol": sym, "qty": qty, "entry_date": buy, "exit_date": sell,
            "entry_price": buy_px, "exit_price": sell_px, "entry_fees": 0.0, "exit_fees": 0.0,
            "entry_stt": 0.0, "exit_stt": 0.0}


def book(classes=None, fmv=math.nan):
    return TaxBook(TaxModel(), classes or {}, lambda s: fmv)


def test_equity_short_term_rate_changes_on_budget_day():
    b = book()
    b.classify(rt("A", "2024-01-01", "2024-07-22", 100, 100, 200))   # 15%
    b.classify(rt("A", "2024-01-01", "2024-07-23", 100, 100, 200))   # 20%
    row = b.settle(2024)
    assert row["tax"] == pytest.approx((10_000 * 0.15 + 10_000 * 0.20) * 1.04)


def test_long_term_needs_more_than_twelve_months_and_gets_exemption():
    b = book()
    b.classify(rt("A", "2023-01-02", "2024-01-02", 1000, 100, 400))  # exactly 12 months: ST
    b.classify(rt("A", "2022-01-03", "2024-01-03", 1000, 100, 400))  # LT 10% over 1 lakh
    row = b.settle(2023)
    assert row["tax"] == pytest.approx((300_000 * 0.15 + 200_000 * 0.10) * 1.04)


def test_ltcg_exempt_before_april_2018_and_grandfathered_after():
    b = book(fmv=300.0)
    b.classify(rt("A", "2015-01-01", "2018-03-28", 1000, 100, 350))
    assert b.settle(2017)["tax"] == 0
    b.classify(rt("A", "2015-01-01", "2018-06-01", 1000, 100, 350))  # cost = FMV 300
    assert b.settle(2018)["tax"] == pytest.approx((50_000 - 50_000) * 0.10 * 1.04)
    b.classify(rt("A", "2015-01-01", "2018-06-01", 2000, 100, 250))  # cost = min(FMV, sale)
    assert b.settle(2018)["taxable_lt"] == 0


def test_losses_set_off_and_carry_forward():
    b = book()
    b.classify(rt("A", "2020-05-01", "2020-06-01", 100, 1000, 500))   # ST loss 50k
    b.classify(rt("B", "2018-05-01", "2020-07-01", 100, 100, 1600))   # LT gain 150k
    row = b.settle(2020)
    # The short-term loss offsets the long-term gain before the 1 lakh exemption.
    assert row["taxable_lt"] == 0 and row["tax"] == 0
    b.classify(rt("C", "2020-05-01", "2021-05-03", 100, 1000, 0))     # LT loss 100k
    b.settle(2021)
    b.classify(rt("D", "2022-05-01", "2022-06-01", 100, 100, 1100))   # ST gain 100k
    row = b.settle(2022)
    assert row["tax"] == pytest.approx(100_000 * 0.15 * 1.04)          # LT loss can't offset ST
    assert row["losses_carried_forward"] == pytest.approx(100_000)


def test_gold_etf_rules():
    b = book({"G": "other"})
    b.classify(rt("G", "2019-01-01", "2021-01-01", 100, 100, 200))    # < 36 months: slab
    assert b.settle(2020)["tax"] == pytest.approx(10_000 * 0.30 * 1.04)
    b = book({"G": "other"})
    b.classify(rt("G", "2015-04-01", "2020-04-01", 100, 100, 200))    # indexed, 20%
    expected = (20_000 - 10_000 * 301 / 254) * 0.20 * 1.04
    assert b.settle(2020)["tax"] == pytest.approx(expected)
    b = book({"G": "other"})
    b.classify(rt("G", "2023-05-01", "2025-01-01", 100, 100, 200))    # 50AA: slab
    b.classify(rt("G", "2023-05-01", "2025-06-01", 100, 100, 200))    # after Apr 2025: 12.5%
    assert b.settle(2024)["tax"] == pytest.approx(10_000 * 0.30 * 1.04)
    assert b.settle(2025)["tax"] == pytest.approx(10_000 * 0.125 * 1.04)


def test_asset_classes():
    assert asset_class("INE002A01018", "Reliance", "Oil") == "equity"
    assert asset_class("INF204KB17I5", "Nippon India ETF Gold BeES", "Gold") == "other"
    assert asset_class("INF109KC18O0", "ICICI Pru Nifty 10 yr Benchmark G-sec ETF", "Equity") == "debt"
    assert asset_class("INF204KB15I9", "Nippon India ETF Nifty Bank BeES", "Equity") == "equity"
