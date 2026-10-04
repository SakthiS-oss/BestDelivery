#!/usr/bin/env python3
"""Replay the planner three days before past disasters and print a summary.

The default run reads the local hazard and news files. Pass --live to leave
USE_MOCK_DATA as it is in the environment. Results are written to
data/backtest_report.json for the backtest page.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical replay of past disaster corridors.")
    parser.add_argument("--events", type=int, default=5, help="How many past disasters to review.")
    parser.add_argument("--routes", type=int, default=5, help="Sample corridors through each affected area.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Do not force local files. Scoring then follows USE_MOCK_DATA.",
    )
    parser.add_argument("--output", type=Path, default=None, help="JSON report path.")
    args = parser.parse_args()
    if not args.live:
        os.environ["USE_MOCK_DATA"] = "true"

    from backtest import REPORT_PATH, format_table, run_backtest, write_report

    report = run_backtest(events=args.events, routes_per_event=args.routes)
    path = write_report(report, args.output or REPORT_PATH)
    print(format_table(report))
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
