# tests/test_evals - eval suite

Synthetic eval set for get_context recall@10 (`test_get_context_recall.py`).

## Status

- 30 synthetic queries across 4 categories (feature_lookup, task_lookup,
  cross_doc, negative). The expected_doc_ids are deterministic UUIDs
  derived from the query text - they exercise the harness math but not
  real retrieval quality.
- To measure real retrieval quality, replace the synthetic set with a
  hand-labeled corpus from your own workspace. Same fixture format; just
  swap expected_doc_ids with real chunk IDs.

## Pass criteria

- aggregate recall@10 >= 0.7
- per-category breakdown surfaced in test output
- negative category: assert NEAR-ZERO recall (no false positives)

## How to run

```
PATH="$PWD/.venv/bin:$PATH" pytest tests/test_evals/ -v
```

## How to add real data

1. Export your Notion/GDocs corpus.
2. Anonymize: replace user names, company names, secret values.
3. Seed FalkorDB with the corpus (one entity per chunk).
4. Hand-label 50+ representative agent prompts -> the chunk_ids you
   would expect to retrieve.
5. Replace `tests/test_evals/fixtures/get_context_recall.json` with the
   real set. The harness assertions don't change.
