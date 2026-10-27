"""Event loop that runs a Strategy over a universe and period."""
from __future__ import annotations

import copy
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
from .taxes import GRANDFATHER_DATE, TaxBook, TaxModel, asset_class, fy_of

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
    taxes: TaxModel = field(default_factory=TaxModel)


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
        self._rank_cache: tuple[int, np.ndarray] | None = None
        self._sym_pos = {s: k for k, s in enumerate(md.symbols)}
        self.open = md.panel("open")
        self.high = md.panel("high")
        self.low = md.panel("low")
        self.close = md.panel("close")
        self.volume = md.panel("volume")
        sec = md.securities
        classes = {s: asset_class(sec.at[s, "isin"], sec.at[s, "name"], sec.at[s, "industry"])
                   for s in md.symbols}
        gi = md.index_of(GRANDFATHER_DATE)
        def fmv_2018(sym):
            if gi < 0:
                return math.nan
            col = self.high[:gi + 1, self._sym_pos[sym]]
            ok = np.flatnonzero(np.isfinite(col))
            return float(col[ok[-1]]) if len(ok) else math.nan
        self.asset_classes = classes
        self.taxbook = TaxBook(cfg.taxes, classes, fmv_2018)
        self.tax_rows: list[dict] = []
        self.expired: list[dict] = []
        self.sym_pnl: list[tuple] = []
        self._mv_prev: dict[str, float] = {}
        self._fills_seen = 0
        self._rt_seen = 0
        self._tax_today = 0.0

    # ---- helpers used by Context ----
    def universe_mask(self) -> np.ndarray:
        if self._umask_cache is None or self._umask_cache[0] != self.i:
            mask = universe_mask(self.md, self.ev, self.i, self.cfg.universe)
            rank = self.cfg.universe.get("rank")
            if rank:
                mask = mask & self._rank_members(rank)
            self._umask_cache = (self.i, mask)
        return self._umask_cache[1]

    def _rank_members(self, rank: dict) -> np.ndarray:
        """Stocks ranked `from`..`to` by the `by` formula (1 = highest) on the latest refresh
        date. Refresh dates are fixed (every `refresh` sessions from the start), and each
        ranking uses only data up to its own date, so membership never depends on when the
        strategy happens to ask."""
        every = max(int(rank.get("refresh") or 21), 1)
        b = self.i0 + (self.i - self.i0) // every * every
        if self._rank_cache is None or self._rank_cache[0] != b:
            base = universe_mask(self.md, self.ev, b, self.cfg.universe)
            score = np.asarray(self.ev.eval(rank.get("by") or "adv_63d", b), float)
            score = np.where(base & np.isfinite(score), score, -np.inf)
            order = np.argsort(-score, kind="stable")
            lo, hi = max(int(rank.get("from") or 1), 1), int(rank.get("to") or 50)
            chosen = order[lo - 1:hi]
            members = np.zeros(len(self.md.symbols), bool)
            members[chosen[np.isfinite(score[chosen])]] = True
            self._rank_cache = (b, members)
        return self._rank_cache[1]

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
            order.blocked = "no price"
            return None
        side = "buy" if order.qty > 0 else "sell"
        qty = abs(order.qty)
        if side == "sell":
            held = self.pf.positions[order.symbol].qty if order.symbol in self.pf.positions else 0
            qty = min(qty, held)
        vol = self.volume[i, j]
        capped = False
        if self.cfg.max_volume_pct and np.isfinite(vol):
            cap = int(vol * self.cfg.max_volume_pct / 100)
            capped = cap < qty
            qty = min(qty, cap)
            if capped:
                order.blocked = "volume"
        if qty <= 0:
            return None
        px = self.cfg.costs.fill_price(side, float(ref))
        if side == "buy":
            # Never borrow: shrink the buy to what the cash covers after fees.
            affordable = int(self.pf.cash / (px * (1 + 0.003)))
            if affordable < qty:
                order.blocked = "cash"
            qty = min(qty, max(affordable, 0))
            if qty <= 0:
                return None
        return self._make_fill(i, order.symbol, side, qty, float(ref), order.reason, capped)

    def _make_fill(self, i, sym, side, qty, ref, reason, capped=False, slip=True) -> Fill:
        px = self.cfg.costs.fill_price(side, ref) if slip else ref
        value = qty * px
        costs = self.cfg.costs.breakdown(side, value)
        vol = self.volume[i, self._sym_pos[sym]]
        return Fill(self.md.dates[i], sym, side, qty, px, value, sum(costs.values()), reason,
                    costs=costs, slippage=qty * abs(px - ref),
                    participation=qty / vol if np.isfinite(vol) and vol > 0 else math.nan,
                    capped=capped)

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
                net[o.symbol] = Order(o.symbol, o.qty, o.reason, o.created_i, o.ttl, o.blocked)
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
            elif o.qty:
                px = self.close[i, self._sym_pos[o.symbol]]
                self.expired.append({"date": str(self.md.dates[i].date()), "symbol": o.symbol,
                                     "side": "buy" if o.qty > 0 else "sell", "qty": abs(o.qty),
                                     "value": abs(o.qty) * px if np.isfinite(px) else None,
                                     "reason": o.reason, "cause": o.blocked or "unknown"})

    def _volume_cap(self, i: int, j: int) -> int | float:
        vol = self.volume[i, j]
        if not self.cfg.max_volume_pct or not np.isfinite(vol):
            return math.inf
        return int(vol * self.cfg.max_volume_pct / 100)

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
            self.pending = [p for p in self.pending if p.symbol != sym]
            qty, cap = pos.qty, self._volume_cap(i, j)
            if cap < qty:
                # The stop can only sell its share of the session's volume; the rest becomes
                # an ordinary sell order for the following sessions.
                pos.stop = pos.take_profit = pos.trail_pct = None
                self.pending.append(Order(sym, -(qty - cap), reason, i, self.order_ttl,
                                          "volume"))
                qty = cap
            if qty <= 0:
                continue
            f = self._make_fill(i, sym, "sell", qty, float(px), reason, capped=cap < pos.qty)
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
                f = Fill(self.md.dates[i], sym, "sell", pos.qty, px, value, 0.0, "delisted",
                         costs={}, participation=math.nan)
                self.pf.apply_fill(f, i)

    # ---- taxes and attribution ----
    def _book_round_trips(self) -> None:
        rts = self.pf.round_trips
        for rt in rts[self._rt_seen:]:
            self.taxbook.classify(rt)
        self._rt_seen = len(rts)

    def _pay_taxes(self, i: int) -> None:
        """On the first session of a financial year, settle the year just ended. Tax due is
        paid from cash; any shortfall is raised by selling every holding pro rata at the open."""
        if i == self.i0 or fy_of(self.md.dates[i]) == fy_of(self.md.dates[i - 1]):
            return
        row = self.taxbook.settle(fy_of(self.md.dates[i - 1]), self.md.dates[i])
        row["paid"] = self.cfg.taxes.mode == "pay"
        self.tax_rows.append(row)
        if not row["paid"] or row["tax"] <= 0:
            return
        self.pf.cash -= row["tax"]
        self._tax_today += row["tax"]
        if self.pf.cash >= 0:
            return
        need = -self.pf.cash * 1.01
        mv = self.pf.market_value
        for sym, pos in list(self.pf.positions.items()):
            o = self.open[i, self._sym_pos[sym]]
            if not np.isfinite(o) or mv <= 0:
                continue
            j = self._sym_pos[sym]
            qty = min(pos.qty, math.ceil(pos.qty * need / mv), self._volume_cap(i, j))
            if qty <= 0:
                continue
            f = self._make_fill(i, sym, "sell", qty, float(o), "tax")
            self.pf.apply_fill(f, i)
            self.strategy.on_fill(self.ctx, f)

    def _attribute(self, i: int) -> tuple[float, float]:
        """Per-symbol P&L for session i (change in value plus cash from its fills), and
        the session's fees and slippage."""
        flows: dict[str, float] = {}
        fees = slip = 0.0
        for f in self.pf.fills[self._fills_seen:]:
            cash = f.value - f.fees if f.side == "sell" else -(f.value + f.fees)
            flows[f.symbol] = flows.get(f.symbol, 0.0) + cash
            fees += f.fees
            slip += f.slippage
        self._fills_seen = len(self.pf.fills)
        mv = {s: p.market_value for s, p in self.pf.positions.items()}
        d = self.md.dates[i]
        for s in set(mv) | set(flows) | set(self._mv_prev):
            pnl = mv.get(s, 0.0) - self._mv_prev.get(s, 0.0) + flows.get(s, 0.0)
            if pnl:
                self.sym_pnl.append((d, s, pnl))
        self._mv_prev = mv
        return fees, slip

    def _end_taxes(self) -> dict:
        """Tax owed on the unfinished year so far, and if everything were sold at the end."""
        fy = fy_of(self.md.dates[self.i1])
        accrued = self.taxbook.settle(fy, final=False)
        book = copy.deepcopy(self.taxbook)
        c = self.cfg.costs
        held = {s: p for s, p in self.pf.positions.items() if np.isfinite(p.last_price)}
        for sym, pos in held.items():
            px = c.fill_price("sell", pos.last_price)
            costs = c.breakdown("sell", pos.qty * px)
            fee, stt = sum(costs.values()), costs.get("stt", 0.0)
            for lot in pos.lots:
                share = lot.qty / pos.qty
                book.classify({"symbol": sym, "qty": lot.qty, "entry_date": lot.date,
                               "exit_date": self.md.dates[self.i1], "entry_price": lot.price,
                               "exit_price": px, "entry_fees": lot.cost, "entry_stt": lot.stt,
                               "exit_fees": fee * share, "exit_stt": stt * share})
        liq = book.settle(fy, final=False)
        sell_costs = sum(c.fees("sell", p.qty * c.fill_price("sell", p.last_price)) +
                         p.qty * (p.last_price - c.fill_price("sell", p.last_price))
                         for p in held.values())
        return {"fy": accrued["fy"], "accrued_tax": accrued["tax"],
                "liquidation_tax": liq["tax"], "liquidation_costs": sell_costs,
                "liquidation_value": self.pf.equity - sell_costs - liq["tax"],
                "losses_carried_forward": accrued["losses_carried_forward"]}

    # ---- main loop ----
    def run(self) -> dict:
        t0 = time.time()
        rec = []
        self.strategy.initialize(self.ctx)
        n = self.i1 - self.i0 + 1
        for i in range(self.i0, self.i1 + 1):
            self.i = i
            self._tax_today = 0.0
            self._pay_taxes(i)
            self._execute_pending(i)
            self._check_stops(i)
            self._mark(i)
            if self._scheduled(i) and i < self.i1:
                self.strategy.on_bar(self.ctx)
            self._book_round_trips()
            fees, slip = self._attribute(i)
            pf = self.pf
            if i == self.i1 or self.md.dates[i + 1].month != self.md.dates[i].month:
                self._holdings.append({"date": str(self.md.dates[i].date()),
                                       "weights": pf.weights(), "cash": pf.cash / pf.equity})
            rec.append((self.md.dates[i], pf.equity, pf.cash, pf.market_value,
                        len(pf.positions), self.bench_close[i], fees, slip, self._tax_today))
            if self.progress and (i - self.i0) % 50 == 0:
                self.progress((i - self.i0) / n, str(self.md.dates[i].date()))
        self.strategy.on_end(self.ctx)
        self._book_round_trips()
        eq = pd.DataFrame(rec, columns=["date", "equity", "cash", "invested", "positions",
                                        "benchmark", "fees", "slippage", "tax"]).set_index("date")
        return {"equity": eq, "fills": self.pf.fills, "round_trips": self.pf.round_trips,
                "open_positions": self._open_positions(), "logs": self.ctx._log,
                "fees": self.pf.total_fees, "elapsed": time.time() - t0,
                "holdings": self._holdings, "taxes": self.tax_rows,
                "end_taxes": self._end_taxes(), "tax_mode": self.cfg.taxes.mode,
                "expired_orders": self.expired, "symbol_pnl": self.sym_pnl,
                "asset_classes": self.asset_classes}

    def _open_positions(self) -> list[dict]:
        out = []
        for s, p in self.pf.positions.items():
            out.append({"symbol": s, "qty": p.qty, "avg_cost": p.avg_cost,
                        "last_price": p.last_price, "market_value": p.market_value,
                        "unrealized_pnl": p.unrealized_pnl,
                        "entry_date": str(p.entry_date.date()) if p.entry_date else None,
                        "weight": p.market_value / self.pf.equity if self.pf.equity else 0})
        return sorted(out, key=lambda r: -r["market_value"])
