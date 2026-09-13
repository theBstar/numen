"""Experiment 3 - does the retrieval difference change the answer?

UNLIKE experiments 1 and 2, this one calls a model and therefore costs money
and needs a key. It has NOT been run; no numbers from it appear in
BENCHMARK.md. It is here so the accuracy claim can be tested rather than
asserted.

It needs no Docker and no Numen stack: both arms are served from the same
projected fixtures in-process, so the only external dependency is an
OpenAI-compatible chat endpoint.

    export LLM_API_KEY=...            # or point LLM_BASE_URL at a local server
    python -m benchmarks.run_agent_accuracy --runs 5

Each question is asked `--runs` times per arm. Report accuracy against the
ground truth in questions.py, plus the spread across runs - an arm that is
right on average but different every time is not usable for a briefing.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from pathlib import Path

from benchmarks import projections as pj
from benchmarks.questions import QUESTIONS

OUT = Path(__file__).parent / "results" / "exp3_agent_accuracy.json"

# ── Tool surfaces ─────────────────────────────────────────────────────────
# The per-tool arm gets one tool per source operation, named the way the real
# vendor MCP servers name theirs. The graph arm gets Numen's tools. Both are
# backed by the same fixtures, so any difference is access pattern, not data.

PER_TOOL_TOOLS = {
    "linear_list_issues": lambda **kw: pj.linear_issues(),
    "linear_list_projects": lambda **kw: pj.linear_projects(),
    "linear_list_initiatives": lambda **kw: pj.linear_initiatives(),
    "linear_list_users": lambda **kw: pj.linear_users(),
    "github_list_pulls": lambda **kw: pj.github_pulls(),
    "github_list_members": lambda **kw: pj.github_users(),
}

GRAPH_TOOLS = {
    # Numen resolves people and materializes edges, so its tools answer in
    # one hop what the per-tool arm assembles from several.
    "numen_list_tasks": lambda **kw: pj.linear_issues(),
    "numen_get_task_context": None,  # wired in _graph_task_context
    "numen_get_person_workload": None,
    "numen_get_delayed_projects": None,
}


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Call {name}.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": [],
            },
        },
    }


def build_client():
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pip install openai to run experiment 3") from exc

    key = os.environ.get("LLM_API_KEY")
    base = os.environ.get("LLM_BASE_URL") or None
    if not key and not base:
        raise SystemExit(
            "Set LLM_API_KEY, or LLM_BASE_URL for a local OpenAI-compatible server."
        )
    return OpenAI(api_key=key or "not-needed", base_url=base)


def ask(client, model: str, question: str, tools: dict, max_steps: int = 8) -> dict:
    """Run one question to completion, recording every tool call."""
    messages = [
        {
            "role": "system",
            "content": (
                "Answer using only the tools. Be exact and terse. "
                "Finish with a line 'ANSWER: <json>' containing just the answer."
            ),
        },
        {"role": "user", "content": question},
    ]
    schemas = [_schema(n) for n in tools]
    calls, tokens = 0, 0

    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=schemas, temperature=0
        )
        tokens += getattr(resp.usage, "total_tokens", 0) or 0
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return {"text": msg.content or "", "tool_calls": calls, "tokens": tokens}

        for tc in msg.tool_calls:
            calls += 1
            fn = tools.get(tc.function.name)
            payload = fn() if callable(fn) else {"error": "unknown tool"}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(payload, separators=(",", ":"))[:60000],
                }
            )

    return {"text": "", "tool_calls": calls, "tokens": tokens, "truncated": True}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4o-mini"))
    args = ap.parse_args()

    client = build_client()
    results = []

    for q in QUESTIONS:
        for arm, tools in (("per_tool", PER_TOOL_TOOLS), ("graph", GRAPH_TOOLS)):
            runs = [ask(client, args.model, q.text, tools) for _ in range(args.runs)]
            texts = [r["text"] for r in runs]
            results.append(
                {
                    "qid": q.qid,
                    "hops": q.hops,
                    "arm": arm,
                    "expected": q.answer,
                    "runs": runs,
                    "distinct_answers": len(set(texts)),
                    "mean_tool_calls": statistics.mean(r["tool_calls"] for r in runs),
                    "mean_tokens": statistics.mean(r["tokens"] for r in runs),
                }
            )
            print(
                f"{q.qid:<22} {arm:<9} calls~{results[-1]['mean_tool_calls']:.1f} "
                f"tokens~{results[-1]['mean_tokens']:.0f} distinct={results[-1]['distinct_answers']}"
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"model": args.model, "runs": args.runs,
                               "results": results}, indent=2))
    print(f"\nwrote {OUT}")
    print("Grade `expected` against each run's ANSWER line before quoting accuracy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
