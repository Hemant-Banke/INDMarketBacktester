"""Per-stock trend following with explicit inventory management.

Shows the event-driven style: individual entries and exits, a cap on open positions,
fixed-fraction sizing, a protective stop and a trailing stop per position.
"""
from mbt.engine.strategy import Strategy


class TrendBreakout(Strategy):
    name = "52-week-high breakout"
    description = ("Daily: buy stocks closing at a 52-week high above a rising 200-day "
                   "average; exit on a trailing stop or when price falls under the 200 DMA. "
                   "Max N positions, each sized at a fixed % of equity.")
    params = {"max_positions": 15, "position_pct": 6.0, "stop_pct": 12.0,
              "trail_pct": 20.0, "min_adv_cr": 5.0}
    schedule = "daily"
    warmup = 0

    def on_bar(self, ctx):
        # Exits: trend broken
        held = list(ctx.positions)
        if held:
            below = ctx.eval("close < sma(close, 200)", held)
            for s in below[below.astype(bool)].index:
                ctx.sell(s, reason="below 200 DMA")

        # Entries: fill free slots with the strongest breakouts
        slots = self.p.max_positions - len(ctx.positions) + \
            sum(1 for o in ctx.pending_orders if o.qty < 0)
        if slots <= 0:
            return
        signal = ctx.eval(
            f"close >= highest(high, 252) * 0.995 and close > sma(close, 200) "
            f"and sma(close, 200) > lag(sma(close, 200), 20) and adv_63d > {self.p.min_adv_cr}")
        cands = signal[signal.astype(bool)].index.difference(list(ctx.positions))
        if len(cands) == 0:
            return
        strength = ctx.eval("ret_6m", cands).sort_values(ascending=False)
        for s in strength.index[:slots]:
            ctx.buy(s, weight=self.p.position_pct / 100, reason="breakout")
            ctx.set_stop(s, stop_pct=self.p.stop_pct, trail_pct=self.p.trail_pct)
