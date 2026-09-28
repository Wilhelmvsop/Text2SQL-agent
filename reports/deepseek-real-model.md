# DeepSeek Real-Model Text-to-SQL Evaluation

## Summary

This run completed an end-to-end evaluation of `deepseek-flash` on 25 Text-to-SQL
questions. Each generated query passed through the project's safety validator, ran
against the same SQLite database as its reference query, and was scored by complete
execution-result agreement.

Overall execution accuracy was **92.00% (23/25)**. Easy and medium questions both
reached 100%; hard-question accuracy was 77.78%. Twenty-four questions produced a
final valid query, and 23 produced the correct result.

## Configuration

| Item | Value |
|---|---|
| Timestamp (UTC) | 2026-09-28T00:22:00.095339+00:00 |
| Evaluation mode | `real_model` |
| Model | `deepseek-flash` |
| API | DeepSeek OpenAI-compatible Chat Completions |
| Embedding | `hashing-8192-v1` |
| Schema strategy | Top-K retrieval, `top_k=4` |
| Maximum few-shot examples | 3 |
| Maximum corrections | 3 after the first attempt |
| Prompt version | `schema-grounded-v1` |
| Database | `data/evaluation.db` |
| Python / SQLite | 3.13.13 / 3.51.2 |
| NumPy / SQLGlot | 2.4.6 / 30.8.0 |
| Database SHA-256 | `efd6077d72dc435c7ed136c2ea2b7f5f161237630f38021fa227a784c4ae1411` |
| Benchmark SHA-256 | `5a1703a7397fc48cfe01a9eff851bd5bcb62ed42be09310f38398a7ec620f66a` |

```bash
set -a
source .env
set +a
.venv/bin/python -m text2sql.cli \
  --evaluate \
  --db data/evaluation.db \
  --output reports/deepseek-real-model.json
```

The run did not use `--smoke`, so it was not a reference-query replay.

## Overall Results

| Metric | Result |
|---|---:|
| Questions | 25 |
| Valid on first attempt | 23/25 (92.00%) |
| Valid after correction | 24/25 (96.00%) |
| Correct execution result | 23/25 (92.00%) |
| Initial validation failures | 1 |
| Validation recovery | 1/1 (100.00%) |
| Provider failures | 1 |
| Mean schema recall | 96.67% |
| Mean initial prompt characters | 2,976.8 |
| Mean total prompt characters | 3,115.52 |
| Mean generation latency | 1.668 seconds |
| Mean end-to-end latency | 2.033 seconds |

Validation recovery means the corrected SQL passed validation; it does not by itself
establish semantic correctness. Case `h04` recovered validation but returned a result
that did not match the reference.

## Results by Difficulty

| Difficulty | Questions | First valid | Final valid | Correct | Accuracy | Mean schema recall |
|---|---:|---:|---:|---:|---:|---:|
| Easy | 8 | 8 | 8 | 8 | 100.00% | 100.00% |
| Medium | 8 | 8 | 8 | 8 | 100.00% | 100.00% |
| Hard | 9 | 7 | 8 | 7 | 77.78% | 90.74% |

Both non-passing cases were hard questions whose retrieved context omitted a required
table.

## Case Details

### h01: Truncated Model Output

The question asks for the five highest-revenue customers in 2025 while excluding
refunded orders. Schema recall was 66.67%, with `order_items` absent. The provider
reported `Model output was truncated`, so the case produced no query for validation or
execution.

### h04: Valid Query with an Incorrect Result

The question asks for products that have never been ordered. Schema recall was 50%,
with `order_items` absent. The first query attempted to use that unavailable table and
was rejected. The corrected query was:

```sql
SELECT p.product_id, p.name
FROM products AS p
WHERE 0
ORDER BY p.product_id
```

The query passed syntax, safety, and SQLite `EXPLAIN` checks but returned no rows. The
reference result contains five products, `Product 076` through `Product 080`.

## Tokens and Latency

The 24 completed provider responses reported the following usage:

| Item | Known usage |
|---|---:|
| Prompt tokens | 18,940 |
| Completion tokens | 4,372 |
| Total tokens | 23,312 |

Case `h01` returned no complete token usage. The table therefore reports known usage,
not an exact total for the run. End-to-end latency across all 25 cases was approximately
50.817 seconds and includes retrieval, generation, validation, and execution.

## Measurement Scope

The run uses one database, 25 questions, and one model pass. Its 92% execution accuracy
describes this exact `deepseek-flash`, hashing-retrieval, Top-K=4 configuration.

## Artifacts

- Machine-readable case results: `reports/deepseek-real-model.json`
- This report: `reports/deepseek-real-model.md`
- Query-level traces: `traces/queries.jsonl`
