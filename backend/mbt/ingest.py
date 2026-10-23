"""Data refresh jobs (run from the CLI or the web UI)."""
from __future__ import annotations

import datetime as dt
import json
import threading
import traceback
from datetime import datetime

import pandas as pd

from . import config
from .data import indices, nse, tickertape, yahoo
from .data.store import get_market_data

JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
STEPS = ("snapshot", "corporate_actions", "prices", "indices", "fundamentals")


def _status_file():
    return config.DATA_DIR / "ingest_status.json"


def last_runs() -> dict:
    p = _status_file()
    return json.loads(p.read_text()) if p.exists() else {}


def _record(step: str, info: dict):
    s = last_runs()
    s[step] = {"at": datetime.now().isoformat(timespec="seconds"), **info}
    _status_file().write_text(json.dumps(s, indent=1, default=str))


def run_step(step: str, start: str | None = None, progress=None) -> dict:
    progress = progress or (lambda *a: None)
    if step == "prices":
        first = pd.Timestamp(start or "2005-01-01").date()
        stats = nse.download(first, dt.date.today(),
                             progress=lambda i, n, m: progress(i / n * 0.8, m))
        progress(0.85, "building adjusted price panels")
        info = {**nse.build(), "download": stats}
    elif step == "corporate_actions":
        tt = tickertape.fetch_corporate_actions(
            progress=lambda i, n, m: progress(i / n * 0.4, m))
        sec = nse.securities() if (config.PRICES_DIR / "securities.parquet").exists() else None
        syms = sorted(set(tt["symbol"]) | (set(sec) if sec is not None else set()))
        ya = yahoo.fetch_splits(syms, progress=lambda i, n, m: progress(0.4 + i / n * 0.6, m))
        info = {"tickertape_events": len(tt), "yahoo_events": len(ya),
                "note": "re-run the prices step to apply them"}
    elif step == "indices":
        info = {"rows": indices.download()}
    elif step == "snapshot":
        df = tickertape.fetch_snapshot(lambda i, n, m: progress(i / n, m))
        info = {"stocks": len(df), "fields": df.shape[1]}
    elif step == "fundamentals":
        snap = tickertape.fetch_snapshot()
        syms = snap[snap["sector"].fillna("") != "ETF"]["symbol"].dropna().tolist()
        df = tickertape.fetch_fundamentals(syms, progress=lambda i, n, m: progress(i / n, m))
        info = {"rows": len(df), "companies": int(df["symbol"].nunique())}
    else:
        raise ValueError(f"unknown step {step}")
    _record(step, info)
    return info


def start_job(steps: list[str], start: str | None = None) -> str:
    job_id = datetime.now().strftime("%H%M%S")
    job = {"id": job_id, "steps": steps, "status": "running", "step": None, "progress": 0.0,
           "message": "", "results": {}}
    with _LOCK:
        if any(j["status"] == "running" for j in JOBS.values()):
            raise RuntimeError("An ingest job is already running")
        JOBS[job_id] = job

    def work():
        try:
            for s in steps:
                job["step"] = s
                job["results"][s] = run_step(
                    s, start, lambda p, m: job.update(progress=round(p, 3), message=m))
            get_market_data(reload=True)
            job["status"] = "done"
        except Exception:
            job.update(status="error", message=traceback.format_exc(limit=6))

    threading.Thread(target=work, daemon=True).start()
    return job_id
