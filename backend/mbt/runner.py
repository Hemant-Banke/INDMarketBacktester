"""Strategy discovery and backtest run management (background threads + JSON results)."""
from __future__ import annotations

import importlib.util
import inspect
import json
import math
import sys
import threading
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime

import numpy as np
import pandas as pd

from . import analytics, config
from .data.store import get_market_data
from .engine.costs import CostModel
from .engine.engine import BacktestConfig, Engine
from .engine.strategy import Strategy
from .engine.taxes import TaxModel

_RUNS: dict[str, dict] = {}   # in-flight status
_LOCK = threading.Lock()


# ------------------------------------------------------------------ strategies

def _load_module(path):
    name = f"mbt_user_strategies.{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def discover() -> dict[str, dict]:
    """{id: {cls, file, error}} for every Strategy subclass in strategies/*.py."""
    out = {}
    for path in sorted(config.STRATEGY_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            mod = _load_module(path)
        except Exception:
            out[f"{path.stem}:?"] = {"cls": None, "file": path.name,
                                     "error": traceback.format_exc(limit=3)}
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if issubclass(cls, Strategy) and cls is not Strategy and \
                    cls.__module__ == mod.__name__:
                out[f"{path.stem}:{cls.__name__}"] = {"cls": cls, "file": path.name,
                                                      "error": None}
    return out


def describe_strategies() -> list[dict]:
    rows = []
    for sid, info in discover().items():
        cls = info["cls"]
        rows.append({
            "id": sid, "file": info["file"], "error": info["error"],
            "name": getattr(cls, "name", sid) if cls else sid,
            "description": inspect.cleandoc(cls.description or cls.__doc__ or "") if cls else "",
            "params": dict(cls.params) if cls else {},
            "schedule": cls.schedule if cls else None,
        })
    return rows


# ------------------------------------------------------------------ runs

def _clean(o):
    """JSON-safe: NaN/inf -> None, numpy/pandas scalars -> python."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return str(o.date()) if hasattr(o, "date") else str(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def start_run(strategy_id: str, params: dict, cfg: dict) -> str:
    strategies = discover()
    if strategy_id not in strategies or strategies[strategy_id]["cls"] is None:
        raise KeyError(f"Strategy {strategy_id} not found or failed to import")
    cls = strategies[strategy_id]["cls"]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    costs = CostModel(**(cfg.pop("costs", None) or {}))
    taxes = TaxModel(**(cfg.pop("taxes", None) or {}))
    if taxes.mode not in ("pay", "report"):
        raise ValueError("taxes.mode must be 'pay' or 'report'")
    bcfg = BacktestConfig(**cfg, costs=costs, taxes=taxes)
    meta = {"id": run_id, "strategy_id": strategy_id, "strategy_name": cls.name,
            "params": {**cls.params, **params}, "config": _clean(asdict(bcfg)),
            "created": datetime.now().isoformat(timespec="seconds"), "status": "running",
            "progress": 0.0, "message": "starting"}
    with _LOCK:
        _RUNS[run_id] = meta
    threading.Thread(target=_run, args=(run_id, cls, params, bcfg), daemon=True).start()
    return run_id


def _run(run_id, cls, params, bcfg: BacktestConfig):
    meta = _RUNS[run_id]
    d = config.RUNS_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)

    def progress(p, msg):
        meta["progress"], meta["message"] = round(p, 3), msg

    try:
        md = get_market_data()
        strat = cls(**params)
        res = Engine(md, strat, bcfg, progress).run()
        progress(0.99, "analytics")
        an = analytics.compute(res, md.securities["sector"], initial_cash=bcfg.initial_cash,
                               benchmark_history=md.benchmarks.get(bcfg.benchmark),
                               securities=md.securities)
        fills = [{**f.__dict__, "date": str(f.date.date())} for f in res["fills"]]
        out = {**an, "fills": fills, "round_trips": res["round_trips"],
               "open_positions": res["open_positions"], "logs": res["logs"][-2000:],
               "holdings": res["holdings"]}
        (d / "result.json").write_text(json.dumps(_clean(out)))
        meta.update(status="done", progress=1.0, message=f"done in {res['elapsed']:.1f}s",
                    headline=_clean({k: an["summary"]["strategy"].get(k) for k in
                                     ("cagr", "sharpe", "max_drawdown", "total_return")} |
                                    {"benchmark_cagr": an["summary"]["benchmark"].get("cagr"),
                                     "cagr_after_tax": an["costs"].get("cagr_after_tax")}))
    except Exception:
        meta.update(status="error", message=traceback.format_exc(limit=8))
    (d / "meta.json").write_text(json.dumps(_clean(meta), indent=1))


def run_status(run_id: str) -> dict:
    if run_id in _RUNS:
        return _RUNS[run_id]
    p = config.RUNS_DIR / run_id / "meta.json"
    if not p.exists():
        raise KeyError(run_id)
    return json.loads(p.read_text())


def run_result(run_id: str) -> str:
    p = config.RUNS_DIR / run_id / "result.json"
    if not p.exists():
        raise KeyError(run_id)
    return p.read_text()


def list_runs() -> list[dict]:
    runs = {}
    for p in config.RUNS_DIR.glob("*/meta.json"):
        try:
            m = json.loads(p.read_text())
            runs[m["id"]] = m
        except (OSError, ValueError):
            continue
    runs.update({k: v for k, v in _RUNS.items()})
    return sorted(runs.values(), key=lambda m: m["id"], reverse=True)


def delete_run(run_id: str) -> None:
    import shutil
    if "/" in run_id or ".." in run_id:
        raise ValueError("bad id")
    _RUNS.pop(run_id, None)
    shutil.rmtree(config.RUNS_DIR / run_id, ignore_errors=True)
