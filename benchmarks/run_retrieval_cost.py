"""Experiment 2 - what does it cost to get the facts into context?

Deterministic. No model, no network, no API key. Both arms follow an oracle
plan (see benchmarks/questions.py), so this measures the structural cost of
each access pattern rather than how well an agent explores.

Three numbers per question:

  calls    round trips before the answer can be formed
  bytes    JSON actually pulled across those calls
  waste    bytes pulled per byte of answer - how much of the context window
           is spent carrying material the answer does not use
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from benchmarks import projections as pj
from benchmarks.questions import QUESTIONS

OUT = Path(__file__).parent / "results" / "exp2_retrieval_cost.json"


def run() -> dict:
    rows = []
    for q in QUESTIONS:
        ans_bytes = max(pj.size(q.answer), 1)
        pt_bytes = sum(c.bytes for c in q.per_tool)
        g_bytes = sum(c.bytes for c in q.graph)
        rows.append(
            {
                "qid": q.qid,
                "hops": q.hops,
                "question": q.text,
                "needs_identity_join": q.needs_identity_join,
                "note": q.note,
                "answer_bytes": ans_bytes,
                "per_tool": {
                    "calls": len(q.per_tool),
                    "bytes": pt_bytes,
                    "waste": round(pt_bytes / ans_bytes, 1),
                    "plan": [f"{c.source}.{c.op}" for c in q.per_tool],
                },
                "graph": {
                    "calls": len(q.graph),
                    "bytes": g_bytes,
                    "waste": round(g_bytes / ans_bytes, 1),
                    "plan": [f"{c.source}.{c.op}" for c in q.graph],
                },
                "calls_ratio": round(len(q.per_tool) / max(len(q.graph), 1), 2),
                "bytes_ratio": round(pt_bytes / max(g_bytes, 1), 2),
            }
        )

    by_tier = defaultdict(lambda: {"n": 0, "pt_calls": 0, "g_calls": 0, "pt_bytes": 0, "g_bytes": 0})
    for r in rows:
        t = by_tier[r["hops"]]
        t["n"] += 1
        t["pt_calls"] += r["per_tool"]["calls"]
        t["g_calls"] += r["graph"]["calls"]
        t["pt_bytes"] += r["per_tool"]["bytes"]
        t["g_bytes"] += r["graph"]["bytes"]

    tiers = {}
    for hops, t in sorted(by_tier.items()):
        tiers[str(hops)] = {
            "questions": t["n"],
            "per_tool_calls": t["pt_calls"],
            "graph_calls": t["g_calls"],
            "per_tool_bytes": t["pt_bytes"],
            "graph_bytes": t["g_bytes"],
            "calls_ratio": round(t["pt_calls"] / max(t["g_calls"], 1), 2),
            "bytes_ratio": round(t["pt_bytes"] / max(t["g_bytes"], 1), 2),
        }

    return {
        "experiment": "retrieval cost under oracle planning",
        "method": (
            "Both arms follow a hand-written optimal plan. Payloads are the real demo "
            "fixtures projected into each vendor's response shape. Linear is modelled as "
            "GraphQL, so it is credited for nested within-source fetches; goals are "
            "modelled as Linear initiatives rather than Numen-only data. Both choices "
            "favour the per-tool arm."
        ),
        "totals": {
            "per_tool_calls": sum(r["per_tool"]["calls"] for r in rows),
            "graph_calls": sum(r["graph"]["calls"] for r in rows),
            "per_tool_bytes": sum(r["per_tool"]["bytes"] for r in rows),
            "graph_bytes": sum(r["graph"]["bytes"] for r in rows),
        },
        "by_hop_tier": tiers,
        "questions": rows,
    }


if __name__ == "__main__":
    r = run()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(r, indent=2))

    print("Experiment 2 - retrieval cost under oracle planning")
    print("=" * 78)
    print(f"  {'question':<22} {'hops':>4} {'id':>3} {'calls (pt/g)':>14} {'bytes (pt/g)':>16} {'x':>6}")
    for row in r["questions"]:
        idj = "y" if row["needs_identity_join"] else "-"
        print(
            f"  {row['qid']:<22} {row['hops']:>4} {idj:>3} "
            f"{row['per_tool']['calls']:>6} /{row['graph']['calls']:>5} "
            f"{row['per_tool']['bytes']:>8} /{row['graph']['bytes']:>6} "
            f"{row['bytes_ratio']:>6.1f}"
        )
    print()
    print("  By hop tier:")
    print(f"    {'hops':<6} {'n':>3} {'calls pt/g':>14} {'bytes pt/g':>18} {'bytes x':>9}")
    for hops, t in r["by_hop_tier"].items():
        print(
            f"    {hops:<6} {t['questions']:>3} "
            f"{t['per_tool_calls']:>6} /{t['graph_calls']:>6} "
            f"{t['per_tool_bytes']:>9} /{t['graph_bytes']:>7} "
            f"{t['bytes_ratio']:>9.2f}"
        )
    tot = r["totals"]
    print()
    print(
        f"  Totals: {tot['per_tool_calls']} calls / {tot['per_tool_bytes']:,} bytes  (per-tool)"
        f"   vs  {tot['graph_calls']} calls / {tot['graph_bytes']:,} bytes  (graph)"
    )
    print(f"  wrote {OUT.relative_to(Path(__file__).parent.parent)}")
