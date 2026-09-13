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
| Experiment 3 - agent answer accuracy | **Run.** Claude Sonnet 5 via the Claude Agent SDK, 3 runs per question per arm, 42 sessions, $4.53. |

Experiments 1 and 2 are reproducible with `make bench` - no network, no key,
no Docker. Experiment 3 needs the Claude Agent SDK and spends usage.

**Experiment 3 contradicts part of experiment 2.** That is the most useful
thing in this document and it is dealt with directly below rather than buried.

## The headline, stated fairly

**A context graph does not make your data fresher, and it did not make
anything cheaper once the per-tool servers were allowed to filter. What it
bought was fewer round trips and one clearly better answer on the deepest
question.**

The modelled prediction was that the graph pulls about 3x fewer bytes. Run
against a real model, the graph arm cost **1.9x more** than the per-tool arm.
Section "Experiment 3" explains why, and it is a fault in the graph's tool
design rather than in the idea.

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
| 1 | 1 | 2 / 1 | 6,558 / 697 | 9.41x |
| 2 | 2 | 8 / 2 | 15,987 / 7,013 | 2.28x |
| 3 | 2 | 9 / 2 | 23,945 / 4,861 | 4.93x |
| **all** | **7** | **21 / 7** | **51,336 / 17,417** | **2.95x** |

**At zero hops the two are identical** - byte for byte, because both are one
filtered call against one source. The graph adds nothing to "what are the
urgent tickets", and at that tier the per-tool arm is strictly better, because
it is live and the graph is as fresh as its last sync.

**The crossover is the first cross-source hop.** "Which pull request implements
ENG-4501" costs 9.4x more bytes through per-tool MCPs, because GitHub has no
index on Linear keys: the only way to find the link is to pull every pull
request and scan titles and branches locally. The graph stores that edge.

The projected GitHub branches carry the Linear key (`eng-4501/feat/oauth-pkce`),
which is the convention Linear's own GitHub integration expects. An earlier
draft of these fixtures omitted it, which made the link undiscoverable from
GitHub at all and inflated this row to 18x. Putting the key back is the
generous reading and the honest one.

Per-question detail is in `benchmarks/results/exp2_retrieval_cost.json`, and
every plan is written out in `benchmarks/questions.py` so it can be argued
with.

## Experiment 3 - does any of this change the answer?

**Method.** The same seven questions, the same model (Claude Sonnet 5), three
runs per question per arm, 42 agent sessions in total. Both arms are served
in-process from the identical projected fixtures through the Claude Agent
SDK, so the only variable is the shape of the tools. Grading is set equality
against a fixed answer key - no judge model, no partial credit.

The per-tool arm's list endpoints take the same server-side filters the real
Linear and GitHub MCP servers support. An earlier version of the harness left
them argument-less, so the baseline dumped all sixty issues on every call;
those numbers were discarded rather than published.

**Results.**

| | Per-tool MCP | Context graph |
|---|---|---|
| Accuracy | 18/20 (90%) | 20/21 (95%) |
| Total cost | **$1.59** | $2.95 |
| Tool calls, summed means | 51.2 | **30.7** |
| Runs that crashed | 1 | 0 |

Three things to take from that.

**The cost prediction was wrong.** Experiment 2 said the graph pulls 2.95x
fewer bytes; in practice it cost 1.9x more. The reason is a real design fault:
the graph's tools are coarse. `numen_get_person_workload` returns every task
*and* every pull request for a person whether or not the question needs both,
while `linear_list_issues(assignee: alice.chen)` returns nine issues and
nothing else. Once the per-tool endpoints can filter server side, "the graph
pulls less" stops being true. Experiment 2 assumed a minimal joined subgraph
on one side and whole collections on the other, and that assumption does not
survive contact with filters. The fix is finer-grained graph tools that
project only requested fields - not a different benchmark.

**Round trips did hold up.** 30.7 versus 51.2. On the two join-heavy questions
the gap is wide: finding the pull request for a ticket took the per-tool arm
14.5 calls against 4.67, and one run spent 68 tool calls and hit the turn
limit without answering. Fewer round trips means lower latency and fewer
chances to go wrong, even when the token bill is higher.

**Accuracy barely separated, except once.** 90% against 95% at three runs per
cell is not a real difference. The exception is the question that matters:

> Which company initiative is exposed if ENG-4501 slips?

The per-tool arm answered `goal-platform-reliability` in two runs of three.
That is not a refusal or a hedge - it is a specific, confident, wrong
initiative, and nothing in the answer signals doubt. The graph arm got
`goal-enterprise` three times out of three. This is the failure experiment 1
predicts showing up in prose.

The graph is not immune: on one run of the review-queue question it returned
an empty list where the answer was two pull requests.

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
make bench                                    # experiments 1 and 2, deterministic
python3 -m benchmarks.run_agent_accuracy --runs 3   # experiment 3, needs the SDK
```

The parts most open to challenge, and where to change them:

- identity messiness - `benchmarks/identities.py`
- what each API exposes - `benchmarks/scenarios.py`
- how charitable the baseline resolver is - `benchmarks/baseline_resolver.py`
- the oracle plans - `benchmarks/questions.py`

If a plan is unfair, change it and open a pull request with the new numbers.
A benchmark whose author picks both sides is worth exactly as much as its
willingness to publish the tiers where it loses.
