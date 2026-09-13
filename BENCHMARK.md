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
| Experiment 4 - hop ladder, work graph | **Run.** Integrations alone against integrations plus the graph. 24 sessions, $2.26. |
| Experiment 5 - hop ladder, product wiki | **Run.** Documents alone against documents plus the wiki graph. 30 sessions, $1.82. |

Experiments 1 and 2 are reproducible with `make bench` - no network, no key,
no Docker. Experiment 3 needs the Claude Agent SDK and spends usage.

**Experiments 3, 4 and 5 each contradict something earlier in the sequence.**
Those contradictions are the most useful thing in this document, so they are
dealt with directly rather than buried.

The single clearest result, from experiments 4 and 5 together:

> A context layer earned nothing over the work graph, where Linear already
> models dependencies natively. It earned a great deal over the product wiki,
> where no source system records which ticket implements which spec.

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

> **Qualified by experiment 4.** These figures measure *mechanical* matching.
> A reading model does better: in experiment 4 the integrations arm resolved
> Igor Popov to the GitHub login `ipopov-dev` in three runs of three, by
> pulling the member roster and reading it - a link the four strategies below
> score as underivable. Treat 56-59% as a floor for string matching, not a
> ceiling for an agent.

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

## Experiments 4 and 5 - the deployment people actually have

Experiment 3 replaced the integrations with the graph. Nobody deploys that
way: you do not disconnect your Linear MCP server when you add a context
layer. So both of these give the second arm **every integration plus the
layer on top**, and climb from one hop to four.

That framing buys a measurement the graph-only arm could not make. When the
raw tools are sitting right there, does the model reach for the layer at all?

### Experiment 4 - the work graph

Four rungs: what is one person working on (one source, no identity work);
whose pull requests await a named person's review (two sources, one identity
hop); is that person holding anyone up, counting both blocked tickets and a
review queue (three hops, two systems unioned on a person); and which
initiatives that blocking exposes (four hops).

| | Integrations | Integrations + graph |
|---|---|---|
| Accuracy | **12/12 (100%)** | 11/12 (92%) |
| Cost | $1.16 | $1.10 |
| Data-tool calls | 45 | 44 |
| Calls to the layer | - | 52% |

**The integrations answered everything, including the four-hop question.**
Adding the layer cost one answer and saved no round trips.

**Adoption tracked depth exactly.** The model used the graph for 0% of data
calls at one and two hops, and around 70% at three and four. It reaches for a
context layer precisely when the question deepens, which validates the design
intent even though the outcome did not improve.

**A second server doubled tool-selection overhead**, from 16 ToolSearch calls
to 33. That is a real cost of bolting on a layer, separate from fetching data.

Why did the baseline sweep it? Because **Linear already models the
relationship**. It exposes `blocks` and `blockedBy` natively, so the
dependency walk the question needs is a first-class feature of the source
system. A graph over data that is already a graph adds a hop, not a
capability.

### Experiment 5 - the product wiki

The same ladder asked of product documentation: which document specifies a
fix; who wrote it; who is implementing the feature it describes; which
initiatives that work serves; and which two documents contradict each other
on retry policy.

| | Documents | Documents + wiki |
|---|---|---|
| Accuracy | 13/15 (87%) | **15/15 (100%)** |
| Cost | $1.10 | **$0.72** |
| Data-tool calls | 49 | **34** |
| Calls to the layer | - | 26% |

**Here the layer earned its keep.** More accurate, 35% cheaper, and a third
fewer calls.

The sharpest single result is rung three - *who is implementing the feature
specified in PRD-004?* The document arm spent 16 data calls across six
different tools: search the docs, fetch the document, list issues, list
users, list projects, list initiatives, and stitch it together. The wiki arm
called one tool, `wiki_feature_for_document`, three times. $0.136 against
$0.039.

Rung four is the failure that matters. Asked which initiatives the work in
PRD-002 serves, the document arm answered `goal-bob-connectors` and
`goal-integrations` in two runs of three - confidently wrong, following the
word "connector" in the prose rather than the tickets that implement it. The
wiki arm got it three times out of three.

Rung five is an honest negative: both arms found the contradicting retry
policies three times out of three, and the wiki arm used the layer 0% of the
time to do it. The structural hint that two documents describe one feature
was not needed; search found both.

### What separates the two results

Documents record no relationships. No source system knows which ticket
implements which specification, who owns a described capability, or which
goal a written feature serves. A wiki graph is the only place that
information exists, so querying it is not a shortcut - it is the only route.

Linear, by contrast, already knows what blocks what. The value of a context
layer is concentrated exactly where the source systems have no native
representation of the relationship you need.

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
- **One synthetic estate, and a small one.** Thirteen people, sixty tickets,
  twenty pull requests. That fits comfortably in a context window, which is
  very likely why the integrations arm swept experiment 4 - it could simply
  fetch everything and reason over it. A context layer should earn its keep
  when the estate does *not* fit, and this one does. Nothing here tests that,
  and it is the single biggest limitation of the whole benchmark.

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
