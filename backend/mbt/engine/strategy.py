"""The Strategy base class every backtest runs.

Subclass it in a file under `strategies/`:

    from mbt.engine.strategy import Strategy

    class Momentum(Strategy):
        name = "12-1 momentum, top 20"
        params = {"top_n": 20}
        schedule = "monthly"

        def on_bar(self, ctx):
            score = ctx.eval("ret_12m_1m").dropna()
            picks = score.nlargest(self.p.top_n).index
            ctx.rebalance({s: 1 / len(picks) for s in picks})

Lifecycle (one trading session):
  1. open:  orders queued yesterday fill at today's open (+ slippage, costs, volume cap)
  2. intraday: resting stop-loss / take-profit / trailing stops trigger on today's range
  3. close: the portfolio is marked to today's close
  4. if today is scheduled, `on_bar(ctx)` runs with data up to and including today's close;
     anything it orders fills at the *next* session's open.
So a decision can never trade at a price it has already seen, and no accessor on `ctx`
returns data after today.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .context import Context, Fill


class Strategy:
    name: str = "Unnamed strategy"
    description: str = ""
    # Default parameter values; the UI shows them as editable inputs.
    params: dict[str, Any] = {}
    # "daily" | "weekly" | "monthly" | "quarterly" | "yearly" | int (every N sessions)
    schedule: str | int = "monthly"
    # Sessions of history the strategy needs before its first decision (indicator warm-up).
    warmup: int = 0

    def __init__(self, **overrides):
        unknown = set(overrides) - set(self.params)
        if unknown:
            raise ValueError(f"Unknown params: {sorted(unknown)}")
        self.p = SimpleNamespace(**{**self.params, **overrides})
        tf = getattr(self.p, "timeframe", "daily")
        if tf not in ("daily", "weekly"):
            raise ValueError(f"timeframe must be 'daily' or 'weekly', not {tf!r}")

    # ---- helpers ----
    def bars(self, formula: str) -> str:
        """Make a formula's windows (sma, ema, lag, highest, rsi, ...) count bars of this
        strategy's `timeframe` param: weekly wraps it in weekly(...)."""
        return f"weekly({formula})" if getattr(self.p, "timeframe", "daily") == "weekly" \
            else formula

    # ---- hooks ----
    def initialize(self, ctx: "Context") -> None:
        """Called once before the first session."""

    def on_bar(self, ctx: "Context") -> None:
        """Called after the close of every scheduled session. Place orders here."""

    def on_fill(self, ctx: "Context", fill: "Fill") -> None:
        """Called whenever an order (or a stop) fills."""

    def on_end(self, ctx: "Context") -> None:
        """Called after the last session."""
