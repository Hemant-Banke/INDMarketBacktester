"""Equal-weight buy & hold of the chosen universe (useful with a manual stock list)."""
from mbt.engine.strategy import Strategy


class EqualWeightHold(Strategy):
    name = "Equal-weight buy & hold"
    description = ("Buys every stock in the universe equally on day one. Optionally "
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
        u = ctx.universe[: self.p.max_stocks]
        if u:
            ctx.rebalance({s: 1 / len(u) for s in u})
