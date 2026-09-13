"""Experiment 3 - does the retrieval difference change the answer?

Runs the same questions through the same model twice: once with per-tool MCP
servers, once with Numen's graph tools. Both surfaces are backed by identical
fixtures, so the only variable is the shape of the tools.

Grading is set equality against `expected_ids` in questions.py. No judge
model, no partial credit for prose that sounds right. Naming a
`distractor_id` is scored separately, because that is what a false identity
merge looks like in an answer rather than in a metric.

    python -m benchmarks.run_agent_accuracy --runs 3

Uses the Claude Agent SDK, which authenticates through the local Claude Code
installation - no API key needed. It does consume usage.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolUseBlock,
    query,
)

from benchmarks.arms_mcp import ARMS
from benchmarks.questions import QUESTIONS

OUT = Path(__file__).parent / "results" / "exp3_agent_accuracy.json"

SYSTEM = (
    "You answer questions about an engineering organization using only the tools "
    "provided. Do not guess or use outside knowledge. Work efficiently: fetch what "
    "you need and stop.\n\n"
    "Finish your reply with exactly one line:\n"
    "ANSWER: {\"ids\": [\"...\", \"...\"]}\n\n"
    "`ids` must contain every identifier the question asks for and nothing else - "
    "Linear keys like ENG-4501, pull request numbers as strings like \"301\", or "
    "initiative ids. If you cannot determine the answer, use an empty list."
)

ANSWER_RE = re.compile(r"ANSWER:\s*(\{.*?\})\s*$", re.S | re.M)


def parse_ids(text: str) -> list[str] | None:
    m = ANSWER_RE.search(text or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    ids = obj.get("ids")
    if not isinstance(ids, list):
        return None
    return [str(x).strip() for x in ids]


async def run_one(question, arm_name: str, model: str) -> dict:
    arm = ARMS[arm_name]
    opts = ClaudeAgentOptions(
        system_prompt=SYSTEM,
        mcp_servers=arm["servers"],
        allowed_tools=arm["allowed"],
        # Nothing from the host project leaks into the run.
        setting_sources=[],
        permission_mode="bypassPermissions",
        max_turns=14,
        model=model,
    )

    tool_calls, text, usage, cost, dur = 0, "", {}, None, None
    try:
        async for msg in query(prompt=question.text, options=opts):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        tool_calls += 1
                    elif getattr(block, "text", None):
                        text += block.text + "\n"
            elif isinstance(msg, ResultMessage):
                usage = msg.usage or {}
                cost = msg.total_cost_usd
                dur = msg.duration_ms
                if msg.result:
                    text += str(msg.result)
    except Exception as exc:  # noqa: BLE001 - a crashed run is a datapoint
        return {"error": f"{type(exc).__name__}: {exc}", "tool_calls": tool_calls}

    got = parse_ids(text)
    expected = set(question.expected_ids)
    distractors = set(question.distractor_ids)
    got_set = set(got or [])

    return {
        "parsed": got is not None,
        "got": sorted(got_set),
        "correct": got is not None and got_set == expected,
        "missing": sorted(expected - got_set),
        "spurious": sorted(got_set - expected),
        "named_distractor": sorted(got_set & distractors),
        "tool_calls": tool_calls,
        # `input_tokens` alone excludes cache reads and writes, which is where
        # a large tool payload actually lands. Keep the whole usage record and
        # lead on cost, which prices all of it.
        "usage": dict(usage or {}),
        "billable_input": sum(
            (usage or {}).get(k, 0) or 0
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        ),
        "output_tokens": (usage or {}).get("output_tokens"),
        "cost_usd": cost,
        "duration_ms": dur,
    }


async def main_async(runs: int, model: str, only: str | None) -> int:
    qs = [q for q in QUESTIONS if not only or q.qid == only]
    rows = []

    for question in qs:
        for arm in ("per_tool", "graph"):
            results = []
            for _ in range(runs):
                results.append(await run_one(question, arm, model))
            ok = [r for r in results if not r.get("error")]
            correct = sum(1 for r in ok if r["correct"])
            answers = {json.dumps(r["got"]) for r in ok}
            row = {
                "qid": question.qid,
                "hops": question.hops,
                "needs_identity_join": question.needs_identity_join,
                "arm": arm,
                "runs": runs,
                "errors": len(results) - len(ok),
                "correct": correct,
                "accuracy": round(correct / len(ok), 3) if ok else None,
                "distinct_answers": len(answers),
                "named_distractor_runs": sum(1 for r in ok if r["named_distractor"]),
                "mean_tool_calls": round(statistics.mean([r["tool_calls"] for r in ok]), 2) if ok else None,
                "mean_billable_input": round(statistics.mean(
                    [r["billable_input"] or 0 for r in ok])) if ok else None,
                "mean_cost_usd": round(statistics.mean(
                    [r["cost_usd"] or 0 for r in ok]), 4) if ok else None,
                "total_cost_usd": round(sum(r["cost_usd"] or 0 for r in ok), 4),
                "detail": results,
            }
            rows.append(row)
            print(
                f"{question.qid:<22} {arm:<9} "
                f"acc {correct}/{len(ok)}  calls~{row['mean_tool_calls']}  "
                f"in~{row['mean_billable_input']}  ${row['mean_cost_usd']}  "
                f"distinct={row['distinct_answers']}"
                + (f"  DISTRACTOR x{row['named_distractor_runs']}" if row["named_distractor_runs"] else "")
                + (f"  errors={row['errors']}" if row["errors"] else ""),
                flush=True,
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"model": model, "runs": runs, "rows": rows}, indent=2))
    print(f"\nwrote {OUT}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--only", default=None, help="run a single qid")
    a = ap.parse_args()
    return asyncio.run(main_async(a.runs, a.model, a.only))


if __name__ == "__main__":
    raise SystemExit(main())
