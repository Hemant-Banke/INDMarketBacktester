"""Screens and universes.

A *screen* is a set of formula filters (ANDed), optional extra columns and an optional
sort/limit. A *universe* is what a backtest trades:
  {"type": "manual", "symbols": [...]}           fixed list
  {"type": "all", "include_sme": false}          every listed stock that day
  {"type": "screen", "screen": {...}}            screen re-evaluated point-in-time
  {"type": "screen", "screen_id": "..."}         a saved screen
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config
from .data.store import MarketData
from .formula import Evaluator, FormulaError, _truthy

DEFAULT_COLUMNS = ["close", "mcap", "pe", "pb", "roe", "ret_1m", "ret_1y", "adv_20d"]


@dataclass
class ScreenResult:
    date: pd.Timestamp
    mask: np.ndarray
    table: pd.DataFrame


def _live_extra(md: MarketData) -> dict[str, np.ndarray]:
    """Today's Tickertape screener fields as tt_<label>. Only valid for the latest date."""
    path = config.FUND_DIR / "tt_snapshot.parquet"
    if not path.exists():
        return {}
    snap = (pd.read_parquet(path).dropna(subset=["symbol"]).drop_duplicates("symbol")
            .set_index("symbol").reindex(md.symbols))
    out = {}
    for c in snap.columns:
        if c in ("sid", "tt_name", "sector", "industry", "snapshot_date"):
            continue
        col = pd.to_numeric(snap[c], errors="coerce")
        if col.notna().any():
            out["tt_" + re.sub(r"\W", "_", c)] = col.to_numpy(float)
    return out


def live_fields() -> list[dict]:
    path = config.FUND_DIR / "tt_filters.parquet"
    if not path.exists():
        return []
    f = pd.read_parquet(path)
    return [{"name": "tt_" + re.sub(r"\W", "_", r.label), "category": f"Tickertape · {r.category}",
             "description": f"{r.name} (live snapshot only)" + (" [premium]" if r.premium else ""),
             "unit": r.unit if isinstance(r.unit, str) else ""} for r in f.itertuples()]


def evaluator(md: MarketData, i: int, live: bool) -> Evaluator:
    if live and i != md.last_index:
        raise FormulaError("Live Tickertape fields are only available for the latest date")
    return Evaluator(md, _live_extra(md) if live else None)


def base_mask(md: MarketData, i: int, base: dict | None) -> np.ndarray:
    base = base or {}
    return md.listed_mask(i, include_sme=bool(base.get("include_sme", False)))


def screen_mask(ev: Evaluator, i: int, screen: dict) -> np.ndarray:
    md = ev.md
    mask = base_mask(md, i, screen.get("base"))
    for f in screen.get("filters", []):
        expr = f["formula"] if isinstance(f, dict) else f
        if not expr or not str(expr).strip() or (isinstance(f, dict) and
                                                 f.get("enabled") is False):
            continue
        mask &= _truthy(ev.eval(expr, i))
    sort = screen.get("sort") or {}
    limit = screen.get("limit")
    if sort.get("by") and limit:
        key = np.asarray(ev.eval(sort["by"], i), float)
        key = np.where(mask & np.isfinite(key), key, np.nan)
        order = np.argsort(-key if sort.get("desc", True) else key, kind="stable")
        order = [j for j in order if np.isfinite(key[j])][: int(limit)]
        m = np.zeros_like(mask)
        m[order] = True
        mask = m
    return mask


def run_screen(md: MarketData, screen: dict, as_of=None, live: bool = False,
               max_rows: int = 2000) -> ScreenResult:
    i = md.last_index if as_of is None else md.index_of(as_of)
    if i < 0:
        raise FormulaError("Date is before the start of loaded data")
    ev = evaluator(md, i, live)
    mask = screen_mask(ev, i, screen)
    idx = np.flatnonzero(mask)
    cols = screen.get("columns") or [{"name": c, "formula": c} for c in DEFAULT_COLUMNS]
    sec = md.securities
    table = pd.DataFrame({"symbol": md.symbols[idx],
                          "name": sec["name"].to_numpy(object)[idx],
                          "sector": sec["sector"].to_numpy(object)[idx],
                          "industry": sec["industry"].to_numpy(object)[idx]})
    for c in cols:
        name, expr = (c["name"], c["formula"]) if isinstance(c, dict) else (c, c)
        try:
            v = np.asarray(ev.eval(expr, i))[idx]
        except FormulaError as e:
            raise FormulaError(f"Column '{name}': {e}") from None
        table[name] = v.astype(float) if v.dtype != object else v
    sort = screen.get("sort") or {}
    if sort.get("by"):
        key = np.asarray(ev.eval(sort["by"], i), float)[idx]
        table = table.assign(_k=key).sort_values("_k", ascending=not sort.get("desc", True),
                                                 na_position="last").drop(columns="_k")
    return ScreenResult(md.dates[i], mask, table.head(max_rows))


def universe_mask(md: MarketData, ev: Evaluator, i: int, universe: dict) -> np.ndarray:
    kind = universe.get("type", "all")
    if kind == "manual":
        wanted = np.isin(md.symbols, universe.get("symbols", []))
        return wanted & md.listed_mask(i, include_sme=True)
    if kind == "all":
        return base_mask(md, i, universe)
    if kind == "screen":
        screen = universe.get("screen") or load_item("screens", universe["screen_id"])
        return screen_mask(ev, i, screen)
    raise FormulaError(f"Unknown universe type {kind}")


# ---------------------------------------------------------------- saved items (json files)

def _dir(kind: str):
    d = config.USER_DIR / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_items(kind: str) -> list[dict]:
    items = [json.loads(p.read_text()) for p in sorted(_dir(kind).glob("*.json"))]
    return sorted(items, key=lambda x: x.get("name", ""))


def load_item(kind: str, item_id: str) -> dict:
    p = _dir(kind) / f"{item_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"{kind[:-1]} {item_id} not found")
    return json.loads(p.read_text())


def save_item(kind: str, item: dict) -> dict:
    item = dict(item)
    item.setdefault("id", uuid.uuid4().hex[:10])
    if not re.fullmatch(r"[\w-]+", item["id"]):
        raise ValueError("bad id")
    (_dir(kind) / f"{item['id']}.json").write_text(json.dumps(item, indent=1))
    return item


def delete_item(kind: str, item_id: str) -> None:
    if re.fullmatch(r"[\w-]+", item_id):
        (_dir(kind) / f"{item_id}.json").unlink(missing_ok=True)
