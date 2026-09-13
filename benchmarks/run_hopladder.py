"""Experiment 4 - integrations alone versus integrations plus a context layer.

Experiment 3 replaced the integrations with the graph, which is not how anyone
deploys. Nobody disconnects their Linear MCP server when they add a context
layer. So here the second arm keeps every integration and gains the graph on
top, and the questions climb from one hop to four.

That framing buys a measurement the graph-only arm could not make: when the
raw tools are sitting right there, does the model reach for the graph at all?
Every tool call is attributed to its server.

    python3 -m benchmarks.run_hopladder --runs 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections import Counter
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolUseBlock,
    query,
)

from benchmarks.arms_mcp import ARMS
from benchmarks.hopladder import LADDER
from benchmarks.run_agent_accuracy import SYSTEM, parse_ids

OUT = Path(__file__).parent / "results" / "exp4_hopladder.json"
ARM_NAMES = ("integrations", "integrations_plus_graph")


def _server_of(tool_name: str) -> str:
    # mcp__<server>__<tool>
    parts = tool_name.split("__")
    return parts[1] if len(parts) > 2 else "other"


#: Servers that count as "the context layer" when reporting share of calls.
LAYER_SERVERS = {"numen", "wiki"}


async def run_one(q, arm_name: str, model: str, arms: dict | None = None) -> dict:
    arm = (arms or ARMS)[arm_name]
    opts = ClaudeAgentOptions(
        system_prompt=SYSTEM,
        mcp_servers=arm["servers"],
        allowed_tools=arm["allowed"],
        setting_sources=[],
        permission_mode="bypassPermissions",
        max_turns=16,
        model=model,
    )

    names: list[str] = []
    text, usage, cost, dur = "", {}, None, None
    try:
        async for msg in query(prompt=q.text, options=opts):
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, ToolUseBlock):
                        names.append(b.name)
                    elif getattr(b, "text", None):
                        text += b.text + "\n"
            elif isinstance(msg, ResultMessage):
                usage, cost, dur = msg.usage or {}, msg.total_cost_usd, msg.duration_ms
                if msg.result:
                    text += str(msg.result)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "tool_calls": len(names),
                "tools": names}

    got = parse_ids(text)
    got_set = set(got or [])
    expected = set(q.expected_ids)

    # The CLI defers tool loading, so some calls are ToolSearch rather than a
    # data fetch. Those are harness overhead: counted separately, and kept out
    # of the denominator when asking how often the context layer was used.
    data_calls = [n for n in names if n.startswith("mcp__")]
    overhead = [n for n in names if not n.startswith("mcp__")]
    servers = Counter(_server_of(n) for n in data_calls)

    return {
        "parsed": got is not None,
        "got": sorted(got_set),
        "correct": got is not None and got_set == expected,
        "missing": sorted(expected - got_set),
        "spurious": sorted(got_set - expected),
        "named_distractor": sorted(got_set & set(q.distractor_ids)),
        "tool_calls": len(data_calls),
        "toolsearch_calls": len(overhead),
        "tools": names,
        "calls_by_server": dict(servers),
        "graph_share": round(
            sum(v for k, v in servers.items() if k in LAYER_SERVERS) / len(data_calls), 3
        ) if data_calls else 0.0,
        "billable_input": sum((usage or {}).get(k, 0) or 0 for k in
                              ("input_tokens", "cache_creation_input_tokens",
                               "cache_read_input_tokens")),
        "cost_usd": cost,
        "duration_ms": dur,
    }


async def main_async(runs: int, model: str, only: str | None,
                     ladder=LADDER, arms: dict | None = None,
                     arm_names: tuple[str, ...] = ARM_NAMES,
                     out: Path = OUT) -> int:
    qs = [q for q in ladder if not only or q.qid == only]
    rows = []

    for q in qs:
        for arm in arm_names:
            res = [await run_one(q, arm, model, arms) for _ in range(runs)]
            ok = [r for r in res if not r.get("error")]
            correct = sum(1 for r in ok if r["correct"])
            tool_hist = Counter()
            for r in ok:
                tool_hist.update(r["tools"])
            row = {
                "qid": q.qid, "hops": q.hops, "arm": arm,
                "crosses_identity": getattr(q, "crosses_identity", None),
                "runs": runs, "errors": len(res) - len(ok),
                "correct": correct,
                "accuracy": round(correct / len(ok), 3) if ok else None,
                "distinct_answers": len({json.dumps(r["got"]) for r in ok}),
                "named_distractor_runs": sum(1 for r in ok if r["named_distractor"]),
                "mean_tool_calls": round(statistics.mean([r["tool_calls"] for r in ok]), 2) if ok else None,
                "mean_toolsearch_calls": round(
                    statistics.mean([r.get("toolsearch_calls", 0) for r in ok]), 2) if ok else None,
                "mean_graph_share": round(statistics.mean([r["graph_share"] for r in ok]), 3) if ok else None,
                "mean_cost_usd": round(statistics.mean([r["cost_usd"] or 0 for r in ok]), 4) if ok else None,
                "total_cost_usd": round(sum(r["cost_usd"] or 0 for r in ok), 4),
                "tool_histogram": dict(tool_hist),
                "detail": res,
            }
            rows.append(row)
            share = (f" layer={row['mean_graph_share']:.0%}"
                     if arm not in ("integrations", "docs") else "")
            print(f"{q.qid:<28} h{q.hops} {arm:<24} "
                  f"acc {correct}/{len(ok)}  calls~{row['mean_tool_calls']}  "
                  f"${row['mean_cost_usd']}{share}"
                  + (f"  DISTRACTOR x{row['named_distractor_runs']}" if row["named_distractor_runs"] else "")
                  + (f"  err={row['errors']}" if row["errors"] else ""), flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": model, "runs": runs, "rows": rows}, indent=2))
    print(f"\nwrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    return asyncio.run(main_async(a.runs, a.model, a.only))


if __name__ == "__main__":
    raise SystemExit(main())
