"""Experiment 5 - documents alone versus documents plus the wiki graph.

Same runner as experiment 4, pointed at the product wiki. Arm one is the
integrations plus a document search-and-fetch server, which is what a team
with Notion or Google Docs connected already has. Arm two adds Numen's wiki
layer on top.

    python3 -m benchmarks.run_wikiladder --runs 3
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from benchmarks.run_hopladder import main_async
from benchmarks.wiki_arms import WIKI_ARMS
from benchmarks.wikiladder import WIKI_LADDER

OUT = Path(__file__).parent / "results" / "exp5_wikiladder.json"
ARM_NAMES = ("docs", "docs_plus_wiki")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    return asyncio.run(
        main_async(a.runs, a.model, a.only, ladder=WIKI_LADDER,
                   arms=WIKI_ARMS, arm_names=ARM_NAMES, out=OUT)
    )


if __name__ == "__main__":
    raise SystemExit(main())
