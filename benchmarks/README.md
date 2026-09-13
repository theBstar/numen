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
export LLM_API_KEY=...          # or LLM_BASE_URL for a local server
python3 -m benchmarks.run_agent_accuracy --runs 5
```

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
| `run_agent_accuracy.py` | Experiment 3 harness. Unrun. |

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

**No number without a run.** Experiment 3 is unrun, so no accuracy figure
appears anywhere.

## Changing it

The contestable choices are isolated on purpose:

- how messy identities are - `identities.py`
- what each API exposes - `scenarios.py`
- how clever the baseline is - `baseline_resolver.py`
- what the arms are allowed to do - `questions.py`

Change one, rerun, open a pull request with the new numbers.
