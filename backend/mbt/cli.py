"""Command line: `uv run mbt ingest prices|indices|snapshot|fundamentals|all`, `uv run mbt serve`."""
from __future__ import annotations

import argparse
import logging
import sys


def main(argv=None):
    p = argparse.ArgumentParser("mbt")
    sub = p.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="download / refresh data")
    ing.add_argument("steps", nargs="+", choices=["snapshot", "corporate_actions", "prices",
                                                  "indices", "fundamentals", "all"])
    ing.add_argument("--start", default=None, help="first date for prices (YYYY-MM-DD)")
    srv = sub.add_parser("serve", help="run the web app")
    srv.add_argument("--port", type=int, default=8000)
    srv.add_argument("--reload", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if a.cmd == "ingest":
        from . import ingest
        steps = list(ingest.STEPS) if "all" in a.steps else a.steps
        for s in steps:
            last = [-1.0]

            def prog(frac, msg, s=s):
                if frac - last[0] >= 0.02:
                    last[0] = frac
                    print(f"[{s}] {frac:5.0%} {msg}", flush=True)
            print(s, ingest.run_step(s, a.start, prog))
    elif a.cmd == "serve":
        import uvicorn
        uvicorn.run("mbt.api:app", host="127.0.0.1", port=a.port, reload=a.reload)


if __name__ == "__main__":
    sys.exit(main())
