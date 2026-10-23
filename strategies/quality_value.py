"""Fundamental multi-factor: cheap, profitable, low-debt companies.

Fundamentals are point-in-time: a fiscal year's numbers only become visible ~65 days after
the year ends (quarters: ~50 days). Note the Tickertape free tier carries ~5 years of
statements, so this strategy only has data from roughly mid-2022 onwards.
"""
from mbt.engine.strategy import Strategy


class QualityValue(Strategy):
    name = "Quality + Value"
    description = ("Quarterly: among liquid stocks with ROE > 15% and debt/equity < 1, buy "
                   "the N with the best combined rank of earnings yield and ROCE.")
    params = {"top_n": 25, "min_roe": 15, "max_de": 1.0, "min_adv_cr": 2.0}
    schedule = "quarterly"

    def on_bar(self, ctx):
        ok = ctx.eval(f"roe > {self.p.min_roe} and debt_equity < {self.p.max_de} "
                      f"and adv_63d > {self.p.min_adv_cr} and pe > 0")
        score = ctx.eval("rank(earnings_yield) + rank(roce)")[ok.astype(bool)].dropna()
        picks = score.nlargest(self.p.top_n).index
        if len(picks) == 0:
            ctx.log("no candidates (fundamentals not yet available?)")
            return
        ctx.rebalance({s: 1 / len(picks) for s in picks})
