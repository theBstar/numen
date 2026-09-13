# Context graph vs per-tool MCP servers

If your agent can already connect to Linear, GitHub and Slack through their own
MCP servers, what does routing through a context graph buy you?

This is an attempt to answer that with measurements rather than assertion,
including the cases where the answer is "nothing".

## What was and was not measured

| | Status |
|---|---|
| Experiment 1 - identity derivability | **Run.** Deterministic, no model. |
| Experiment 2 - retrieval cost | **Run.** Deterministic, no model. |
| Experiment 3 - agent answer accuracy | **Not run.** Harness only - it needs an API key and spends money. No number in this document comes from it. |

Everything below is reproducible with `make bench`. No network, no key, no
Docker.

## The headline, stated fairly

**A context graph does not make your data fresher. It makes cross-source
questions cheaper and identity reliable - and only when your estate is
messy.**

Freshness is the graph's weakness, not its strength. A live Notion MCP call
sees the document edited ten seconds ago; a synced graph does not. In this
repository only Linear, GitHub, Slack and Jira take webhooks - Notion and
Google Docs are poll-only. Any claim that the graph is "more up to date" is
false for those sources and should not be made.

## Experiment 1 - can a per-tool agent work out who is who?

An agent holding three per-tool MCP connections sees three unrelated user
records and must decide which refer to the same human. It has no shared key.

**Method.** Thirteen people across GitHub, Linear and Slack, giving 39 true
cross-source identity links. The baseline gets four linking strategies at
once - exact email, exact display name, normalized handle equality, and
handle-as-name-form - plus transitive closure over everything they find. That
is more than a real agent reliably does, deliberately.

The identity fixtures were rewritten for this benchmark. The ones shipped in
`src/demo/fixtures.py` give everyone matching identifiers (`Alice Chen` /
`alice-chen` / `alice@...`), which naive string matching solves perfectly.
Real estates are not like that. Five of the thirteen people here are still
easy cases the baseline should win.

**Results.**

| Estate | Resolver | Recall | Precision | Fully resolved | False merges |
|---|---|---|---|---|---|
| Realistic | aggressive | 59% | 92% | 5/13 | 1 |
| Realistic | conservative | 56% | 100% | 5/13 | 0 |
| Email everywhere | aggressive | 100% | 87% | 13/13 | 1 |
| Email everywhere | conservative | **100%** | **100%** | **13/13** | 0 |
| No emails | aggressive | 59% | 92% | 5/13 | 1 |
| No emails | conservative | 56% | 100% | 5/13 | 0 |

Two findings, and the second is the more important one.

**In a messy estate the per-tool agent recovers a bit over half the links, and
the failure is not graceful.** Being aggressive buys three points of recall
and merges two different people: `achen` (Alice Chen) and `achen-2` (Andrew
Chen) collapse into one cluster, so any workload or ownership answer about
either is confidently wrong. Being careful avoids that and still misses 17 of
39 links. There is no setting that gets both.

**If every system exposes a consistent corporate email, the problem
disappears.** 100% recall, 100% precision, no merges. This cuts against the
pitch and belongs in it: if your directory is clean and every tool surfaces
the same email, you do not need a graph for identity resolution.

Removing emails entirely changes nothing versus the realistic case, because
the emails present in that scenario belong to people the baseline already
resolves by name.

## Experiment 2 - what does it cost to get the facts into context?

**Method.** Seven questions, stratified by how many cross-source hops the
answer requires. Both arms follow a hand-written *oracle* plan: no wasted
calls, no wrong turns. That removes agent skill and leaves the structural cost
of the access pattern. Payloads are the real demo fixtures projected into each
vendor's response shape, measured as JSON bytes on the wire.

Two modelling choices deliberately favour the per-tool arm: Linear is treated
as GraphQL, so it gets credit for nested within-source fetches, and goals are
modelled as Linear initiatives rather than Numen-only data, so the baseline
can answer goal questions at all.

**Results.**

| Hops | Questions | Calls (per-tool / graph) | Bytes (per-tool / graph) | Bytes ratio |
|---|---|---|---|---|
| 0 | 2 | 2 / 2 | 4,846 / 4,846 | **1.00x** |
| 1 | 1 | 2 / 1 | 6,396 / 354 | 18.07x |
| 2 | 2 | 8 / 2 | 15,780 / 6,625 | 2.38x |
| 3 | 2 | 9 / 2 | 23,783 / 4,861 | 4.89x |
| **all** | **7** | **21 / 7** | **50,805 / 16,686** | **3.04x** |

**At zero hops the two are identical** - byte for byte, because both are one
filtered call against one source. The graph adds nothing to "what are the
urgent tickets", and at that tier the per-tool arm is strictly better, because
it is live and the graph is as fresh as its last sync.

**The crossover is the first cross-source hop.** "Which pull request
implements ENG-4501" costs 18x more bytes through per-tool MCPs, because
GitHub has no index on Linear keys: the only way to find the link is to pull
every pull request and scan titles and branches locally. The graph stores that
edge.

Per-question detail is in `benchmarks/results/exp2_retrieval_cost.json`, and
every plan is written out in `benchmarks/questions.py` so it can be argued
with.

## Where the two experiments meet

Hop count alone does not predict difficulty. What predicts it is whether a hop
crosses an identity boundary.

Four of the seven questions need a person linked across two systems. Those
inherit experiment 1's error rate - and experiment 2 charges them nothing for
it, because the oracle plan assumes the join succeeds. For a person like Igor
or Bob it does not succeed at all. The honest reading is that the cost numbers
above are a floor for the per-tool arm, not an estimate.

## What this does not show

- **Nothing about answer quality.** Experiment 3 is unrun. Fewer bytes is not
  the same as a better answer, and the claim that it leads to one is untested.
- **Nothing about freshness.** The graph loses here; it was not measured.
- **Nothing about setup cost.** Per-tool MCPs are zero infrastructure. Numen is
  Postgres, Redis, FalkorDB and sync workers. For a small clean estate asking
  single-source questions, that trade is bad.
- **One synthetic estate.** Thirteen people, sixty tickets, twenty pull
  requests, one shape of messiness. Your estate may be cleaner or worse.

## Reproducing and arguing with it

```bash
make bench
```

The parts most open to challenge, and where to change them:

- identity messiness - `benchmarks/identities.py`
- what each API exposes - `benchmarks/scenarios.py`
- how charitable the baseline resolver is - `benchmarks/baseline_resolver.py`
- the oracle plans - `benchmarks/questions.py`

If a plan is unfair, change it and open a pull request with the new numbers.
A benchmark whose author picks both sides is worth exactly as much as its
willingness to publish the tiers where it loses.
