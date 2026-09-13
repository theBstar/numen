# benchmarks - context graph vs per-tool MCP servers

Results and interpretation live in [BENCHMARK.md](../BENCHMARK.md). This file
is about the code.

## Run it

```bash
make bench                                # experiments 1 and 2
python3 -m benchmarks.run_derivability    # just experiment 1
python3 -m benchmarks.run_retrieval_cost  # just experiment 2
```

No network, no API key, no Docker, no database. Both experiments are
deterministic: same input, same numbers, every time. Results are written to
`benchmarks/results/*.json`.

Experiment 3 calls a model and is **not** part of `make bench`:

```bash
pip install claude-agent-sdk
python3 -m benchmarks.run_agent_accuracy --runs 3    # exp 3: graph instead of integrations
python3 -m benchmarks.run_hopladder --runs 3         # exp 4: integrations, +/- the graph
python3 -m benchmarks.run_wikiladder --runs 3        # exp 5: documents, +/- the wiki graph
```

It authenticates through the local Claude Code installation, so it needs no
API key, but it does spend usage - the published run was 42 sessions for
$4.53.

## Layout

| File | What it is |
|---|---|
| `identities.py` | Thirteen people with realistic cross-source identifiers. The demo fixtures give everyone matching handles; these do not. |
| `scenarios.py` | Alternative assumptions about which APIs expose an email. Brackets the main premise. |
| `baseline_resolver.py` | The identity matching a per-tool agent can do. Four strategies plus transitive closure, in aggressive and conservative modes. |
| `projections.py` | The demo fixtures rendered as each vendor's API would return them. |
| `questions.py` | Seven questions by hop count, each with a hand-written oracle plan per arm. |
| `run_derivability.py` | Experiment 1. |
| `run_retrieval_cost.py` | Experiment 2. |
| `arms_mcp.py` | The two tool surfaces as in-process MCP servers, for experiment 3. |
| `run_agent_accuracy.py` | Experiment 3. Claude Agent SDK, graded by set equality. |
| `hopladder.py` | Experiment 4 questions: one hop to four over the work graph. |
| `run_hopladder.py` | Experiment 4. Also the shared runner for experiment 5. |
| `wiki_fixtures.py` | Six PRDs and the feature graph over them. Authored - `src/demo/` seeds no documentation. |
| `wiki_arms.py` | Experiment 5 surfaces: document search/fetch, and the wiki graph. |
| `wikiladder.py` | Experiment 5 questions, including one deliberate contradiction. |
| `run_wikiladder.py` | Experiment 5. |

## Design rules

**Be charitable to the baseline.** It gets every linking strategy at once,
oracle retrieval plans, Linear modelled as GraphQL so nested fetches are free,
and goals modelled as Linear initiatives so it can answer goal questions at
all. A benchmark that beats a strawman proves nothing.

**Keep the easy cases.** Five of thirteen people are cleanly resolvable and
two of seven questions are single-source. The baseline wins those, and it
should.

**Publish the losses.** Zero-hop parity and the email-everywhere result both
argue against needing a graph. They are in the headline table, not a footnote.

**Keep tool parity.** Both arms get the filters their real counterparts
support. An early version left the per-tool list endpoints argument-less, so
the baseline dumped sixty issues per call; those numbers were thrown away.

**Publish contradictions.** Experiment 3 refuted experiment 2's cost
prediction, experiment 4 found the context layer earning nothing at all, and
experiment 4 also showed experiment 1's resolver understates a reading model.
All three are in the headline of BENCHMARK.md, not a footnote.

**Count harness overhead separately.** The CLI defers tool loading, so some
tool calls are `ToolSearch` rather than a data fetch. Those are reported apart
from data calls and excluded from the "how often was the layer used"
denominator.

## Changing it

The contestable choices are isolated on purpose:

- how messy identities are - `identities.py`
- what each API exposes - `scenarios.py`
- how clever the baseline is - `baseline_resolver.py`
- what the arms are allowed to do - `questions.py`

Change one, rerun, open a pull request with the new numbers.
