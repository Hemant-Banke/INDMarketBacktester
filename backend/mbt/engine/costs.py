"""Indian equity delivery transaction costs."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class CostModel:
    brokerage_pct: float = 0.0      # most discount brokers: zero brokerage on delivery
    brokerage_max: float = 20.0     # Rs cap per order when brokerage_pct > 0
    stt_pct: float = 0.1            # securities transaction tax, buy and sell (delivery)
    exchange_pct: float = 0.00297   # NSE transaction charge
    sebi_pct: float = 0.0001        # Rs 10 per crore
    stamp_buy_pct: float = 0.015    # stamp duty, buy side only
    gst_pct: float = 18.0           # on brokerage + exchange + SEBI fees
    dp_per_sell: float = 15.93      # depository charge per scrip per sell
    slippage_bps: float = 10.0      # price impact, applied to the fill price

    def fees(self, side: str, value: float) -> float:
        brokerage = min(value * self.brokerage_pct / 100, self.brokerage_max) \
            if self.brokerage_pct else 0.0
        exch = value * self.exchange_pct / 100
        sebi = value * self.sebi_pct / 100
        fee = brokerage + exch + sebi + value * self.stt_pct / 100
        fee += (brokerage + exch + sebi) * self.gst_pct / 100
        if side == "buy":
            fee += value * self.stamp_buy_pct / 100
        else:
            fee += self.dp_per_sell
        return fee

    def fill_price(self, side: str, px: float) -> float:
        s = self.slippage_bps / 1e4
        return px * (1 + s) if side == "buy" else px * (1 - s)

    def to_dict(self):
        return asdict(self)
