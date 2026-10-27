"""Indian capital-gains tax on listed shares and ETFs, as the law stood on each sale date.

Equity (shares and domestic equity ETFs, STT paid), sections 111A / 112A:
  short term (held 12 months or less): 10% to Mar 2008, 15% to 22 Jul 2024, 20% after.
  long term: exempt to Mar 2018; then 10%, 12.5% from 23 Jul 2024, on gains above
  Rs 1 lakh a financial year (Rs 1.25 lakh from FY 2024-25). Shares bought by 31 Jan 2018
  use that day's highest price as cost when it is higher (grandfathering).
Other ETFs (gold, silver, debt, liquid, foreign equity):
  sold before 23 Jul 2024: long term after 36 months at 20% on an inflation-indexed cost,
  short term at the slab rate. Since then: long term after 12 months at 12.5%, no indexation.
  Units bought from 1 Apr 2023 are taxed at the slab rate whatever the holding period
  (section 50AA): debt funds always, gold and foreign funds when sold before Apr 2025.

Gains are netted per financial year (April-March): short-term losses offset any gains,
long-term losses only long-term gains, unused losses carry forward 8 years. STT is not
deductible; brokerage, exchange, stamp and the other charges are. Tax plus surcharge and
cess is paid on the first session of the next financial year. Surcharge depends on total
income, so it is a setting (0 by default); the slab rate is too (30% by default).
"""
from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass

import pandas as pd

D = pd.Timestamp
BUDGET_2024 = D("2024-07-23")
GRANDFATHER_DATE = D("2018-01-31")
LTCG_START = D("2018-04-01")
SPECIFIED_FUND_START = D("2023-04-01")

# Cost inflation index by financial year (keyed by the year it starts in), base 2001-02.
CII = {2001: 100, 2002: 105, 2003: 109, 2004: 113, 2005: 117, 2006: 122, 2007: 129,
       2008: 137, 2009: 148, 2010: 167, 2011: 184, 2012: 200, 2013: 220, 2014: 240,
       2015: 254, 2016: 264, 2017: 272, 2018: 280, 2019: 289, 2020: 301, 2021: 317,
       2022: 331, 2023: 348, 2024: 363, 2025: 376}

_NON_EQUITY = re.compile(
    r"gold|silver|liquid|gilt|g-?sec|bond|sdl|overnight|money market|1d rate|debt|"
    r"nasdaq|s&p|hang seng|fang|nyse|global|international|us tech|world|china", re.I)


def fy_of(d: pd.Timestamp) -> int:
    """Financial year as the calendar year it starts in (FY 2024-25 -> 2024)."""
    return d.year if d.month >= 4 else d.year - 1


def fy_label(fy: int) -> str:
    return f"{fy}-{(fy + 1) % 100:02d}"


def asset_class(isin: str, name: str, industry: str) -> str:
    """'equity' (shares, domestic equity ETFs), 'debt', or 'other' (gold, silver, foreign)."""
    if not str(isin or "").startswith("INF"):
        return "equity"
    text = f"{name or ''} {industry or ''}"
    if re.search(r"liquid|gilt|g-?sec|bond|sdl|overnight|money market|1d rate|debt", text, re.I):
        return "debt"
    return "other" if _NON_EQUITY.search(text) else "equity"


@dataclass
class TaxModel:
    mode: str = "pay"            # "pay": deduct from cash each April; "report": compute only
    slab_pct: float = 30.0       # income-tax slab rate for gains taxed as ordinary income
    surcharge_pct: float = 0.0   # depends on total income; 15% max on equity gains
    carry_forward_years: int = 8

    def to_dict(self):
        return asdict(self)


def _cess(fy: int) -> float:
    return 4.0 if fy >= 2018 else 3.0 if fy >= 2007 else 2.0


def _exemption(fy: int) -> float:
    return 125_000.0 if fy >= 2024 else 100_000.0 if fy >= 2018 else 0.0


class TaxBook:
    """Classifies each closed lot when it is sold and settles a financial year's tax."""

    def __init__(self, model: TaxModel, classes: dict[str, str], fmv_2018):
        self.m = model
        self.classes = classes
        self.fmv_2018 = fmv_2018          # symbol -> highest price on 31 Jan 2018 (or nan)
        self.years: dict[int, dict] = {}  # fy -> {"buckets": {(term, rate, s112a): amt}, ...}
        self.carry: list[list] = []       # [fy_origin, "ST"|"LT", amount], oldest first
        self.settled: list[dict] = []

    def _year(self, fy: int) -> dict:
        return self.years.setdefault(fy, {"buckets": {}, "st_loss": 0.0, "lt_loss": 0.0,
                                          "exempt_gain": 0.0, "gross_st": 0.0,
                                          "gross_lt": 0.0})

    def classify(self, rt: dict) -> None:
        """Adds the closed lot to its financial year and labels the round trip."""
        sym, qty = rt["symbol"], rt["qty"]
        buy, sell = pd.Timestamp(rt["entry_date"]), pd.Timestamp(rt["exit_date"])
        cls = self.classes.get(sym, "equity")
        over12 = sell > buy + pd.DateOffset(years=1)
        over36 = sell > buy + pd.DateOffset(years=3)
        proceeds = qty * rt["exit_price"] - (rt["exit_fees"] - rt["exit_stt"])
        basis_px = rt["entry_price"]
        expenses = rt["entry_fees"] - rt["entry_stt"]
        s112a = False
        if cls == "equity":
            if over12:
                term = "LT"
                rate = 0.0 if sell < LTCG_START else 10.0 if sell < BUDGET_2024 else 12.5
                s112a = True
                fmv = self.fmv_2018(sym)
                if buy <= GRANDFATHER_DATE and rate and fmv == fmv:
                    basis_px = max(basis_px, min(fmv, rt["exit_price"]))
                label = "LTCG (equity)" if rate else "LTCG (equity, exempt)"
            else:
                term = "ST"
                rate = 10.0 if sell < D("2008-04-01") else 15.0 if sell < BUDGET_2024 else 20.0
                label = "STCG (equity)"
        else:
            specified = buy >= SPECIFIED_FUND_START and (
                cls == "debt" or sell < D("2025-04-01"))
            long = over12 if sell >= BUDGET_2024 else over36
            if specified or not long:
                term, rate, label = "ST", self.m.slab_pct, "Short term (slab rate)"
            else:
                term = "LT"
                rate = 12.5 if sell >= BUDGET_2024 else 20.0
                label = "LTCG (non-equity)"
                if sell < BUDGET_2024:
                    expenses *= CII[fy_of(sell)] / CII[fy_of(buy)]
                    basis_px *= CII[fy_of(sell)] / CII[fy_of(buy)]
                    label = "LTCG (non-equity, indexed)"
        gain = proceeds - qty * basis_px - expenses
        rt["tax_class"] = label
        rt["taxable_gain"] = gain
        y = self._year(fy_of(sell))
        if term == "LT" and rate == 0.0:
            y["exempt_gain"] += gain       # neither taxed nor allowed as a loss
            return
        if gain >= 0:
            key = (term, rate, s112a)
            y["buckets"][key] = y["buckets"].get(key, 0.0) + gain
            y["gross_st" if term == "ST" else "gross_lt"] += gain
        else:
            y["st_loss" if term == "ST" else "lt_loss"] += -gain

    @staticmethod
    def _absorb(buckets: dict, terms: tuple[str, ...], loss: float) -> float:
        """Uses `loss` against gains of the given terms, highest rate first. Returns rest."""
        for key in sorted((k for k in buckets if k[0] in terms), key=lambda k: -k[1]):
            take = min(buckets[key], loss)
            buckets[key] -= take
            loss -= take
            if loss <= 0:
                break
        return max(loss, 0.0)

    def settle(self, fy: int, date=None, final: bool = True) -> dict:
        """Tax for financial year `fy`. With final=False the carried losses are not
        consumed (used for estimates of a year still running)."""
        y = self._year(fy)
        b = dict(y["buckets"])
        carry = copy.deepcopy(self.carry)
        lt_left = self._absorb(b, ("LT",), y["lt_loss"])
        st_left = self._absorb(b, ("ST", "LT"), y["st_loss"])
        carry = [c for c in carry if fy - c[0] <= self.m.carry_forward_years]
        before = sum(c[2] for c in carry)
        for c in carry:
            c[2] = self._absorb(b, ("ST", "LT") if c[1] == "ST" else ("LT",), c[2])
        carried_used = before - sum(c[2] for c in carry)
        carry = [c for c in carry if c[2] > 1e-6]
        if lt_left > 0:
            carry.append([fy, "LT", lt_left])
        if st_left > 0:
            carry.append([fy, "ST", st_left])
        ex = _exemption(fy)
        ex_used = 0.0
        for key in sorted((k for k in b if k[2]), key=lambda k: -k[1]):
            take = min(b[key], ex - ex_used)
            b[key] -= take
            ex_used += take
        base = sum(amt * rate / 100 for (term, rate, _), amt in b.items())
        tax = base * (1 + self.m.surcharge_pct / 100) * (1 + _cess(fy) / 100)
        row = {"fy": fy_label(fy), "paid_on": str(date.date()) if date is not None else None,
               "stcg": y["gross_st"], "ltcg": y["gross_lt"], "st_losses": y["st_loss"],
               "lt_losses": y["lt_loss"], "exempt_ltcg": y["exempt_gain"],
               "carried_losses_used": carried_used, "ltcg_exemption_used": ex_used,
               "taxable_st": sum(v for k, v in b.items() if k[0] == "ST"),
               "taxable_lt": sum(v for k, v in b.items() if k[0] == "LT"),
               "tax": tax, "losses_carried_forward": sum(c[2] for c in carry)}
        if final:
            self.carry = carry
            self.settled.append(row)
        return row
