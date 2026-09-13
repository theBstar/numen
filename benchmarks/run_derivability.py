"""Experiment 1 - can a per-tool agent recover cross-source identity at all?

Deterministic. No model, no network, no API key. It asks a structural
question: given only the attributes GitHub, Linear and Slack return on the
objects an agent fetches, which cross-source identity links are *derivable*?

A link that is not derivable is not a model-quality problem. No amount of
reasoning recovers a join whose evidence is absent from the responses.

Run under three assumptions about email exposure so the headline number can
be checked against its own weakest premise.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from benchmarks.baseline_resolver import (
    AGGRESSIVE,
    CONSERVATIVE,
    components,
    node_owner,
    propose_links,
)
from benchmarks.identities import SOURCES
from benchmarks.scenarios import SCENARIOS

OUT = Path(__file__).parent / "results" / "exp1_derivability.json"


def score(identities, strategies=AGGRESSIVE) -> dict:
    owner = node_owner(identities)
    links = propose_links(identities, strategies)
    clusters = components(links)

    truth: set[frozenset] = set()
    for ident in identities:
        nodes = [(s, getattr(ident, s).handle) for s in SOURCES if getattr(ident, s)]
        for a, b in combinations(nodes, 2):
            truth.add(frozenset([a, b]))

    predicted: set[frozenset] = set()
    for cluster in clusters:
        for a, b in combinations(sorted(cluster), 2):
            if a[0] != b[0]:
                predicted.add(frozenset([a, b]))

    tp, fp, fn = predicted & truth, predicted - truth, truth - predicted

    false_merges = []
    for cluster in clusters:
        people = {owner[n] for n in cluster}
        if len(people) > 1:
            false_merges.append(
                {"cluster": sorted(f"{s}:{h}" for s, h in cluster), "people": sorted(people)}
            )

    per_person = []
    for ident in identities:
        nodes = [(s, getattr(ident, s).handle) for s in SOURCES if getattr(ident, s)]
        pairs = [frozenset([a, b]) for a, b in combinations(nodes, 2)]
        found = sum(1 for p in pairs if p in predicted)
        per_person.append(
            {
                "person": ident.key,
                "name": ident.real_name,
                "links_true": len(pairs),
                "links_recovered": found,
                "complete": found == len(pairs),
                "note": ident.note,
            }
        )

    return {
        "links_true": len(truth),
        "links_predicted": len(predicted),
        "true_positives": len(tp),
        "false_positives": len(fp),
        "false_negatives": len(fn),
        "recall": round(len(tp) / len(truth), 4) if truth else 0.0,
        "precision": round(len(tp) / len(predicted), 4) if predicted else 0.0,
        "people_fully_resolved": sum(1 for p in per_person if p["complete"]),
        "people": len(per_person),
        "false_merges": false_merges,
        "underivable_links": sorted(
            "  <->  ".join(sorted(f"{s}:{h}" for s, h in pair)) for pair in fn
        ),
        "per_person": per_person,
    }


def run() -> dict:
    return {
        "experiment": "cross-source identity derivability",
        "method": (
            "Four linking strategies (exact email, exact display name, normalized handle "
            "equality, handle-as-name-form), plus transitive closure over everything they "
            "find. Applied only to attributes the source APIs return on fetched objects. "
            "The baseline is given every strategy at once, which is more than a real agent "
            "would reliably apply."
        ),
        "modes": {
            "aggressive": "every strategy, including fuzzy handle-to-name matching",
            "conservative": "high-confidence strategies only; declines to guess",
        },
        "scenarios": {
            name: {
                "aggressive": score(fn(), AGGRESSIVE),
                "conservative": score(fn(), CONSERVATIVE),
            }
            for name, fn in SCENARIOS.items()
        },
    }


if __name__ == "__main__":
    r = run()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(r, indent=2))

    print("Experiment 1 - cross-source identity derivability")
    print("=" * 72)
    print(
        f"  {'scenario':<18} {'mode':<13} {'recall':>7} {'prec':>7} {'resolved':>10} {'merges':>8}"
    )
    for name, modes in r["scenarios"].items():
        for mode, s in modes.items():
            print(
                f"  {name:<18} {mode:<13} {s['recall']:>6.0%} {s['precision']:>7.0%} "
                f"{s['people_fully_resolved']:>7}/{s['people']} {len(s['false_merges']):>8}"
            )

    base = r["scenarios"]["as_authored"]["aggressive"]
    print()
    print("  Realistic scenario, per person:")
    for p in base["per_person"]:
        mark = "ok  " if p["complete"] else "MISS"
        print(f"    {mark} {p['person']:<8} {p['links_recovered']}/{p['links_true']}  {p['note'][:54]}")
    if base["false_merges"]:
        print()
        print("  False merges (two people believed to be one):")
        for fm in base["false_merges"]:
            print(f"    {' + '.join(fm['people'])}")
            print(f"      {', '.join(fm['cluster'])}")
    print()
    print(f"  wrote {OUT.relative_to(Path(__file__).parent.parent)}")
