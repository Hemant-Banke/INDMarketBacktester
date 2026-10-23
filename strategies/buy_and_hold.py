"""Equal-weight buy & hold of the chosen universe (useful with a manual stock list)."""
from mbt.engine.strategy import Strategy


class EqualWeightHold(Strategy):
    name = "Equal-weight buy & hold"
    description = ("Buys every stock in the universe equally on day one (the max_stocks most traded "
                   "if the universe is larger). Optionally "
                   "re-balances back to equal weights every N months (0 = never).")
    params = {"rebalance_months": 0, "max_stocks": 50}
    schedule = "monthly"

    def initialize(self, ctx):
        self.months = 0

    def on_bar(self, ctx):
        first = self.months == 0
        self.months += 1
        due = self.p.rebalance_months and (self.months - 1) % self.p.rebalance_months == 0
        if not (first or due):
            return
        # A large universe is cut to its most traded stocks, not the alphabetically first.
        u = ctx.universe
        if len(u) > self.p.max_stocks:
            liq = ctx.eval("adv_63d")
            if liq.notna().sum() < self.p.max_stocks:  # not enough history yet
                liq = ctx.history("value", 1).iloc[-1].reindex(u)
            u = list(liq.dropna().nlargest(self.p.max_stocks).index)
        if u:
            ctx.rebalance({s: 1 / len(u) for s in u})
