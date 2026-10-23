"""Cross-sectional momentum: hold the strongest stocks, rebalance monthly."""
from mbt.engine.strategy import Strategy


class Momentum(Strategy):
    name = "12-1 Momentum"
    description = ("Every month, rank liquid stocks by 12-month return excluding the last "
                   "month and hold the top N equally weighted.")
    params = {"top_n": 20, "min_adv_cr": 5.0, "min_price": 20, "tolerance": 0.01}
    schedule = "monthly"

    def on_bar(self, ctx):
        f = f"adv_63d > {self.p.min_adv_cr} and close > {self.p.min_price}"
        liquid = ctx.eval(f)
        score = ctx.eval("ret_12m_1m")[liquid.astype(bool)].dropna()
        picks = score.nlargest(self.p.top_n).index
        if len(picks) == 0:
            return
        ctx.rebalance({s: 1 / len(picks) for s in picks}, tolerance=self.p.tolerance)
