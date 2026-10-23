"""Event loop that runs a Strategy over a universe and period."""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from ..data.store import MarketData
from ..formula import Evaluator
from ..screener import universe_mask
from .context import Context, Fill, Order, Portfolio
from .costs import CostModel
from .strategy import Strategy

log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    start: str
    end: str | None = None
    initial_cash: float = 1_00_00_000.0      # Rs 1 crore
    universe: dict = field(default_factory=lambda: {"type": "all"})
    benchmark: str = "NIFTY50"
    fill: str = "open"                       # "open" | "close" of the next session
    max_volume_pct: float = 10.0             # cap a fill at this % of the session's volume
    order_ttl: int = 5
    delist_after: int = 30                   # sessions without a print -> forced exit
    delist_haircut_pct: float = 0.0          # value lost when force-exiting such a position
    costs: CostModel = field(default_factory=CostModel)


class Engine:
    def __init__(self, md: MarketData, strategy: Strategy, cfg: BacktestConfig,
                 progress: Callable[[float, str], None] | None = None):
        self.md, self.strategy, self.cfg = md, strategy, cfg
        self.progress = progress
        self.ev = Evaluator(md)
        self.i0 = md.index_of(cfg.start, side="left")
        self.i1 = md.index_of(cfg.end) if cfg.end else md.last_index
        if self.i0 >= self.i1:
            raise ValueError("Backtest period is empty for the loaded data")
        self.i = self.i0
        self.pf = Portfolio(cfg.initial_cash)
        self.pending: list[Order] = []
        self.deferred_stops: dict[str, dict] = {}
        self.order_ttl = cfg.order_ttl
        self.ctx = Context(self)
        self._holdings: list[dict] = []
        b = md.benchmarks.get(cfg.benchmark)
        self.bench_close = (b.reindex(md.dates).ffill().to_numpy(float) if b is not None
                            else np.full(len(md.dates), np.nan))
        self._umask_cache: tuple[int, np.ndarray] | None = None
        self._sym_pos = {s: k for k, s in enumerate(md.symbols)}
        self.open = md.panel("open")
        self.high = md.panel("high")
        self.low = md.panel("low")
        self.close = md.panel("close")
        self.volume = md.panel("volume")

    # ---- helpers used by Context ----
    def universe_mask(self) -> np.ndarray:
        if self._umask_cache is None or self._umask_cache[0] != self.i:
            self._umask_cache = (self.i, universe_mask(self.md, self.ev, self.i,
                                                       self.cfg.universe))
        return self._umask_cache[1]

    def queue(self, order: Order) -> None:
        if order.symbol not in self._sym_pos:
            raise KeyError(f"Unknown symbol {order.symbol}")
        self.pending.append(order)

    def attach_stops(self, pos, stop_pct, trail_pct, take_profit_pct, stop_price):
        base = pos.avg_cost
        if stop_price is not None:
            pos.stop = stop_price
        elif stop_pct is not None:
            pos.stop = base * (1 - stop_pct / 100)
        if take_profit_pct is not None:
            pos.take_profit = base * (1 + take_profit_pct / 100)
        if trail_pct is not None:
            pos.trail_pct = trail_pct
            pos.peak = max(pos.peak, base)

    # ---- scheduling ----
    def _scheduled(self, i: int) -> bool:
        sch = self.strategy.schedule
        if i - self.i0 < self.strategy.warmup:
            return False
        if isinstance(sch, int):
            return (i - self.i0 - self.strategy.warmup) % sch == 0
        if sch == "daily":
            return True
        d, prev = self.md.dates[i], self.md.dates[i - 1] if i > 0 else None
        first = i == self.i0 + self.strategy.warmup
        if prev is None or first:
            return True
        if sch == "weekly":
            return d.isocalendar()[1] != prev.isocalendar()[1]
        if sch == "monthly":
            return d.month != prev.month
        if sch == "quarterly":
            return d.quarter != prev.quarter or d.year != prev.year
        if sch == "yearly":
            return d.year != prev.year
        raise ValueError(f"Bad schedule {sch!r}")

    # ---- execution ----
    def _fill(self, order: Order, i: int) -> Fill | None:
        j = self._sym_pos[order.symbol]
        ref = self.open[i, j] if self.cfg.fill == "open" else self.close[i, j]
        if not np.isfinite(ref) or ref <= 0:
            return None
        side = "buy" if order.qty > 0 else "sell"
        qty = abs(order.qty)
        if side == "sell":
            held = self.pf.positions[order.symbol].qty if order.symbol in self.pf.positions else 0
            qty = min(qty, held)
        vol = self.volume[i, j]
        if self.cfg.max_volume_pct and np.isfinite(vol):
            qty = min(qty, int(vol * self.cfg.max_volume_pct / 100))
        if qty <= 0:
            return None
        px = self.cfg.costs.fill_price(side, float(ref))
        if side == "buy":
            # Never borrow: shrink the buy to what the cash covers after fees.
            affordable = int(self.pf.cash / (px * (1 + 0.003)))
            qty = min(qty, max(affordable, 0))
            if qty <= 0:
                return None
        value = qty * px
        fees = self.cfg.costs.fees(side, value)
        return Fill(self.md.dates[i], order.symbol, side, qty, px, value, fees, order.reason)

    def _execute_pending(self, i: int) -> None:
        if not self.pending:
            return
        orders, self.pending = self.pending, []
        # Net orders per symbol, then sells before buys so sale proceeds fund purchases.
        net: dict[str, Order] = {}
        for o in orders:
            if o.symbol in net:
                net[o.symbol].qty += o.qty
                net[o.symbol].reason = o.reason
            else:
                net[o.symbol] = Order(o.symbol, o.qty, o.reason, o.created_i, o.ttl)
        for o in sorted(net.values(), key=lambda o: o.qty):
            if o.qty == 0:
                continue
            f = self._fill(o, i)
            if f is not None:
                self.pf.apply_fill(f, i)
                if f.side == "buy" and o.symbol in self.deferred_stops and \
                        o.symbol in self.pf.positions:
                    self.attach_stops(self.pf.positions[o.symbol],
                                      **self.deferred_stops.pop(o.symbol))
                self.strategy.on_fill(self.ctx, f)
                filled = f.qty if f.side == "buy" else -f.qty
                o.qty -= filled
            if o.qty and i - o.created_i < o.ttl:
                self.pending.append(o)  # partially filled / untradeable: retry next session

    def _check_stops(self, i: int) -> None:
        for sym, pos in list(self.pf.positions.items()):
            if pos.stop is None and pos.take_profit is None and pos.trail_pct is None:
                continue
            j = self._sym_pos[sym]
            o, h, l = self.open[i, j], self.high[i, j], self.low[i, j]
            if not np.isfinite(o):
                continue
            stop = pos.stop
            if pos.trail_pct is not None:
                trail = pos.peak * (1 - pos.trail_pct / 100)
                stop = trail if stop is None else max(stop, trail)
            px, reason = None, None
            if stop is not None and l <= stop:
                px, reason = min(o, stop), "stop"          # gap below the stop fills at open
            elif pos.take_profit is not None and h >= pos.take_profit:
                px, reason = max(o, pos.take_profit), "take-profit"
            if px is None:
                continue
            fill_px = self.cfg.costs.fill_price("sell", float(px))
            value = pos.qty * fill_px
            f = Fill(self.md.dates[i], sym, "sell", pos.qty, fill_px, value,
                     self.cfg.costs.fees("sell", value), reason)
            self.pending = [p for p in self.pending if p.symbol != sym]
            self.pf.apply_fill(f, i)
            self.strategy.on_fill(self.ctx, f)

    def _mark(self, i: int) -> None:
        for sym, pos in list(self.pf.positions.items()):
            j = self._sym_pos[sym]
            c = self.close[i, j]
            if np.isfinite(c):
                pos.last_price = float(c)
                pos.last_trade_i = i
                pos.peak = max(pos.peak, float(c))
            elif i - pos.last_trade_i >= self.cfg.delist_after:
                # Untraded for a long stretch (suspended / delisted): book it at the last
                # known price less a haircut. Decided only from information up to today.
                px = pos.last_price * (1 - self.cfg.delist_haircut_pct / 100)
                value = pos.qty * px
                f = Fill(self.md.dates[i], sym, "sell", pos.qty, px, value, 0.0, "delisted")
                self.pf.apply_fill(f, i)

    # ---- main loop ----
    def run(self) -> dict:
        t0 = time.time()
        rec = []
        self.strategy.initialize(self.ctx)
        n = self.i1 - self.i0 + 1
        for i in range(self.i0, self.i1 + 1):
            self.i = i
            self._execute_pending(i)
            self._check_stops(i)
            self._mark(i)
            if self._scheduled(i) and i < self.i1:
                self.strategy.on_bar(self.ctx)
            pf = self.pf
            if i == self.i1 or self.md.dates[i + 1].month != self.md.dates[i].month:
                self._holdings.append({"date": str(self.md.dates[i].date()),
                                       "weights": pf.weights(), "cash": pf.cash / pf.equity})
            rec.append((self.md.dates[i], pf.equity, pf.cash, pf.market_value,
                        len(pf.positions), self.bench_close[i]))
            if self.progress and (i - self.i0) % 50 == 0:
                self.progress((i - self.i0) / n, str(self.md.dates[i].date()))
        self.strategy.on_end(self.ctx)
        eq = pd.DataFrame(rec, columns=["date", "equity", "cash", "invested", "positions",
                                        "benchmark"]).set_index("date")
        return {"equity": eq, "fills": self.pf.fills, "round_trips": self.pf.round_trips,
                "open_positions": self._open_positions(), "logs": self.ctx._log,
                "fees": self.pf.total_fees, "elapsed": time.time() - t0,
                "holdings": self._holdings}

    def _open_positions(self) -> list[dict]:
        out = []
        for s, p in self.pf.positions.items():
            out.append({"symbol": s, "qty": p.qty, "avg_cost": p.avg_cost,
                        "last_price": p.last_price, "market_value": p.market_value,
                        "unrealized_pnl": p.unrealized_pnl,
                        "entry_date": str(p.entry_date.date()) if p.entry_date else None,
                        "weight": p.market_value / self.pf.equity if self.pf.equity else 0})
        return sorted(out, key=lambda r: -r["market_value"])
