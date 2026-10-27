"""Per-stock trend following with explicit inventory management.

Shows the event-driven style: individual entries and exits, a cap on open positions,
fixed-fraction sizing, a protective stop and a trailing stop per position.
"""
from mbt.engine.strategy import Strategy


class TrendBreakout(Strategy):
    name = "52-week-high breakout"
    description = ("Each bar (daily or weekly): buy stocks closing at a high_bars high above "
                   "a rising trend_sma average (rising over slope_bars); exit on a trailing "
                   "stop or when price falls under the average. Max N positions, each sized "
                   "at a fixed % of equity. For weekly, try high_bars 52, trend_sma 40, "
                   "slope_bars 4.")
    params = {"max_positions": 15, "position_pct": 6.0, "stop_pct": 12.0,
              "trail_pct": 20.0, "min_adv_cr": 5.0, "high_bars": 252, "trend_sma": 200,
              "slope_bars": 20, "timeframe": "daily"}
    schedule = "daily"
    warmup = 0

    def on_bar(self, ctx):
        p = self.p
        if not ctx.bar_closed(p.timeframe):
            return
        trend = f"sma(close, {p.trend_sma})"
        # Exits: trend broken
        held = list(ctx.positions)
        if held:
            below = ctx.eval(self.bars(f"close < {trend}"), held)
            for s in below[below.astype(bool)].index:
                ctx.sell(s, reason="below trend average")

        # Entries: fill free slots with the strongest breakouts
        slots = self.p.max_positions - len(ctx.positions) + \
            sum(1 for o in ctx.pending_orders if o.qty < 0)
        if slots <= 0:
            return
        signal = ctx.eval(self.bars(
            f"close >= highest(high, {p.high_bars}) * 0.995 and close > {trend} "
            f"and {trend} > lag({trend}, {p.slope_bars}) and adv_63d > {p.min_adv_cr}"))
        cands = signal[signal.astype(bool)].index.difference(list(ctx.positions))
        if len(cands) == 0:
            return
        strength = ctx.eval("ret_6m", cands).sort_values(ascending=False)
        for s in strength.index[:slots]:
            ctx.buy(s, weight=self.p.position_pct / 100, reason="breakout")
            ctx.set_stop(s, stop_pct=self.p.stop_pct, trail_pct=self.p.trail_pct)
