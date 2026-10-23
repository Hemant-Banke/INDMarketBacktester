"""Paths and global settings."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("MBT_DATA_DIR", ROOT / "data"))
RAW_BHAV_DIR = DATA_DIR / "raw" / "bhavcopy"
PRICES_DIR = DATA_DIR / "prices"
FUND_DIR = DATA_DIR / "fundamentals"
INDEX_DIR = DATA_DIR / "indices"
USER_DIR = DATA_DIR / "user"
RUNS_DIR = DATA_DIR / "runs"
STRATEGY_DIR = Path(os.environ.get("MBT_STRATEGY_DIR", ROOT / "strategies"))

# Optional: paste your logged-in tickertape.in Cookie header here (or in env) to unlock
# premium-only screener fields. Free endpoints work without it.
TICKERTAPE_COOKIE = os.environ.get("TICKERTAPE_COOKIE", "")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# Point-in-time lag between a reporting period's end and the date its numbers are assumed
# public. SEBI LODR: quarterly results within 45 days, Q4/annual within 60 days. We add a
# small buffer so a backtest never uses numbers before they could have been known.
QUARTERLY_REPORT_LAG_DAYS = int(os.environ.get("MBT_Q_LAG", 50))
ANNUAL_REPORT_LAG_DAYS = int(os.environ.get("MBT_A_LAG", 65))

for _d in (RAW_BHAV_DIR, PRICES_DIR, FUND_DIR, INDEX_DIR, USER_DIR, RUNS_DIR, STRATEGY_DIR):
    _d.mkdir(parents=True, exist_ok=True)
