"""Portfolio bookkeeping and the `ctx` object strategies talk to."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from ..formula import Evaluator


@dataclass
class Lot:
    qty: int
    price: float          # fill price incl. slippage
    cost: float           # fees paid on entry for this lot
    date: pd.Timestamp
    i: int


@dataclass
class Position:
    symbol: str
    lots: deque[Lot] = field(default_factory=deque)
    last_price: float = math.nan
    stop: float | None = None           # absolute stop price
    take_profit: float | None = None
    trail_pct: float | None = None
    peak: float = 0.0
    last_trade_i: int = 0               # last session with a real print (delisting check)

    @property
    def qty(self) -> int:
        return sum(l.qty for l in self.lots)

    @property
    def avg_cost(self) -> float:
        q = self.qty
        return sum(l.qty * l.price for l in self.lots) / q if q else math.nan

    @property
    def market_value(self) -> float:
        return self.qty * self.last_price if np.isfinite(self.last_price) else 0.0

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - sum(l.qty * l.price for l in self.lots)

    @property
    def entry_date(self) -> pd.Timestamp | None:
        return self.lots[0].date if self.lots else None


@dataclass
class Order:
    symbol: str
    qty: int                 # signed: + buy, - sell
    reason: str = ""
    created_i: int = 0
    ttl: int = 5             # sessions to keep trying if untradeable (no print / volume cap)


@dataclass
class Fill:
    date: pd.Timestamp
    symbol: str
    side: str
    qty: int
    price: float
    value: float
    fees: float
    reason: str
    realized_pnl: float = 0.0


class Portfolio:
    def __init__(self, cash: float):
        self.cash = float(cash)
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self.round_trips: list[dict] = []
        self.total_fees = 0.0

    @property
    def market_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    @property
    def equity(self) -> float:
        return self.cash + self.market_value

    def weights(self) -> dict[str, float]:
        eq = self.equity
        return {s: p.market_value / eq for s, p in self.positions.items()} if eq > 0 else {}

    def apply_fill(self, f: Fill, i: int) -> None:
        self.total_fees += f.fees
        pos = self.positions.setdefault(f.symbol, Position(f.symbol, last_trade_i=i))
        if f.side == "buy":
            self.cash -= f.value + f.fees
            pos.lots.append(Lot(f.qty, f.price, f.fees, f.date, i))
            pos.peak = max(pos.peak, f.price)
        else:
            self.cash += f.value - f.fees
            remaining, realized = f.qty, 0.0
            fee_per_share = f.fees / f.qty
            while remaining > 0 and pos.lots:
                lot = pos.lots[0]
                take = min(lot.qty, remaining)
                entry_fee = lot.cost * take / lot.qty
                pnl = take * (f.price - lot.price) - entry_fee - fee_per_share * take
                realized += pnl
                self.round_trips.append({
                    "symbol": f.symbol, "entry_date": lot.date, "exit_date": f.date,
                    "qty": take, "entry_price": lot.price, "exit_price": f.price,
                    "pnl": pnl, "return_pct": (f.price / lot.price - 1) * 100,
                    "sessions_held": i - lot.i, "exit_reason": f.reason})
                lot.cost -= entry_fee
                lot.qty -= take
                remaining -= take
                if lot.qty == 0:
                    pos.lots.popleft()
            f.realized_pnl = realized
        pos.last_price = f.price if not np.isfinite(pos.last_price) else pos.last_price
        if pos.qty == 0:
            del self.positions[f.symbol]
        self.fills.append(f)


class Context:
    """Everything a strategy may see at the close of session `i` -- and nothing later."""

    def __init__(self, engine):
        self._e = engine
        self._log: list[dict] = []

    # ---- time ----
    @property
    def date(self) -> pd.Timestamp:
        return self._e.md.dates[self._e.i]

    @property
    def session(self) -> int:
        """Sessions elapsed since the backtest started."""
        return self._e.i - self._e.i0

    # ---- universe & data ----
    @property
    def universe(self) -> list[str]:
        """Symbols in the configured universe today (re-evaluated point-in-time)."""
        return list(self._e.md.symbols[self._e.universe_mask()])

    def eval(self, formula: str, symbols: Iterable[str] | None = None) -> pd.Series:
        """Evaluate a formula as of today. Defaults to today's universe."""
        md = self._e.md
        v = self._e.ev.eval(formula, self._e.i)
        s = pd.Series(v, index=md.symbols)
        if symbols is None:
            return s[self._e.universe_mask()]
        return s.reindex(list(symbols))

    metric = eval

    def history(self, field: str = "close", n: int = 252,
                symbols: Iterable[str] | None = None) -> pd.DataFrame:
        """Last n sessions (ending today) of a price field: open/high/low/close/volume/value."""
        md = self._e.md
        w = md.window(field, self._e.i, n)
        dates = md.dates[max(0, self._e.i - n + 1): self._e.i + 1]
        df = pd.DataFrame(w, index=dates, columns=md.symbols)
        cols = list(symbols) if symbols is not None else list(md.symbols[self._e.universe_mask()])
        return df.reindex(columns=cols)

    def price(self, symbol: str) -> float:
        md = self._e.md
        j = md.symbols.get_loc(symbol)
        return float(md.close_ffill[self._e.i, j])

    def benchmark(self, n: int = 252) -> pd.Series:
        b = self._e.bench_close
        lo = max(0, self._e.i - n + 1)
        return pd.Series(b[lo: self._e.i + 1], index=self._e.md.dates[lo: self._e.i + 1])

    def info(self, symbol: str) -> dict:
        r = self._e.md.securities.loc[symbol]
        return {"name": r.get("name"), "sector": r.get("sector"), "industry": r.get("industry")}

    # ---- portfolio state ----
    @property
    def portfolio(self) -> Portfolio:
        return self._e.pf

    @property
    def cash(self) -> float:
        return self._e.pf.cash

    @property
    def equity(self) -> float:
        return self._e.pf.equity

    @property
    def positions(self) -> dict[str, Position]:
        return self._e.pf.positions

    def weight(self, symbol: str) -> float:
        return self._e.pf.weights().get(symbol, 0.0)

    @property
    def pending_orders(self) -> list[Order]:
        return list(self._e.pending)

    # ---- orders (all fill at the next session's open at the earliest) ----
    def order(self, symbol: str, qty: int, reason: str = "") -> None:
        qty = int(qty)
        if qty:
            self._e.queue(Order(symbol, qty, reason or ("buy" if qty > 0 else "sell"),
                                self._e.i, self._e.order_ttl))

    def buy(self, symbol: str, qty: int | None = None, value: float | None = None,
            weight: float | None = None, reason: str = "buy") -> None:
        if qty is None:
            px = self.price(symbol)
            if not np.isfinite(px) or px <= 0:
                return
            value = value if value is not None else (weight or 0) * self.equity
            qty = int(value // px)
        self.order(symbol, qty, reason)

    def sell(self, symbol: str, qty: int | None = None, reason: str = "sell") -> None:
        held = self.positions[symbol].qty if symbol in self.positions else 0
        self.order(symbol, -min(held, qty if qty is not None else held), reason)

    def close_all(self, reason: str = "exit") -> None:
        for s in list(self.positions):
            self.sell(s, reason=reason)

    def cancel_all(self) -> None:
        self._e.pending.clear()

    def order_target_weight(self, symbol: str, weight: float, reason: str = "rebalance"):
        self.rebalance({symbol: weight}, sell_others=False, reason=reason)

    def rebalance(self, weights: dict[str, float], sell_others: bool = True,
                  tolerance: float = 0.0, reason: str = "rebalance") -> None:
        """Trade towards target portfolio weights (fractions of equity).

        tolerance: skip trades whose size is below this fraction of equity (cuts churn).
        Sizes use today's close; fills happen tomorrow, so buys are scaled down at fill
        time if cash runs short.
        """
        self.cancel_all()
        eq = self.equity
        targets = dict(weights)
        if sell_others:
            for s in self.positions:
                targets.setdefault(s, 0.0)
        for s, w in sorted(targets.items(), key=lambda kv: kv[1]):  # sells first
            px = self.price(s)
            if not np.isfinite(px) or px <= 0:
                continue
            cur = self.positions[s].qty if s in self.positions else 0
            tgt = int(max(w, 0) * eq // px)
            if abs(tgt - cur) * px < tolerance * eq and tgt != 0:
                continue
            self.order(s, tgt - cur, reason if tgt else f"{reason}: exit")

    def set_stop(self, symbol: str, stop_pct: float | None = None,
                 trail_pct: float | None = None, take_profit_pct: float | None = None,
                 stop_price: float | None = None) -> None:
        """Resting exits checked against every following session's range.

        Percentages are relative to the position's average cost (trail: to its peak close).
        """
        pos = self.positions.get(symbol)
        if pos is None:
            self._e.deferred_stops[symbol] = dict(stop_pct=stop_pct, trail_pct=trail_pct,
                                                  take_profit_pct=take_profit_pct,
                                                  stop_price=stop_price)
            return
        self._e.attach_stops(pos, stop_pct, trail_pct, take_profit_pct, stop_price)

    def log(self, msg: str) -> None:
        self._log.append({"date": str(self.date.date()), "msg": str(msg)})
