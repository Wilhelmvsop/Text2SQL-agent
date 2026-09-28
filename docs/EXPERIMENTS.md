# Experiment Record

This document contains only completed experiments, run configurations, metric
definitions, and measured results. The raw JSON artifacts retain case-level retrieval,
generated SQL, validation, execution, and timing data.

## 1. Evaluation Data

The evaluation database is reproducible from random seed 42. It contains seven
e-commerce tables and 1,939 records:

| Table | Rows | Contents |
|---|---:|---|
| `customers` | 60 | Customer identity and country |
| `categories` | 5 | Product categories |
| `suppliers` | 8 | Product suppliers |
| `products` | 80 | Products, stock, and current price |
| `orders` | 360 | Orders and statuses from 2024 through 2026 |
| `order_items` | 1,060 | Quantities and historical transaction prices |
| `payments` | 366 | Payment method, date, and amount |

The benchmark contains 25 authored questions: eight easy, eight medium, and nine hard.
Generated and reference SQL run against the same database, and their complete results
are compared.

## 2. Metric Definitions

| Metric | Definition |
|---|---|
| Execution accuracy | Questions whose complete generated result matches the reference / all questions |
| Validation success rate | Final generated queries that pass safety and database validation / all questions |
| First-pass success rate | First generated queries that pass validation / all questions |
| Self-correction recovery rate | Initially invalid queries later corrected / initially invalid queries |
| Schema recall | Required reference tables retrieved / all required reference tables, macro-averaged |

Result comparison preserves duplicate rows, verifies column count and projection order,
distinguishes `NULL`, and uses `rel_tol=1e-9` and `abs_tol=1e-6` for numeric values.
Order-sensitive questions verify row order; unordered results use matching. Truncated
results cannot pass.

## 3. DeepSeek Real-Model Evaluation

Artifacts: [raw JSON](../reports/deepseek-real-model.json) and
[readable report](../reports/deepseek-real-model.md).

### Configuration

| Item | Value |
|---|---|
| Timestamp (UTC) | 2026-09-28T00:22:00.095339+00:00 |
| Model | `deepseek-flash` |
| API | OpenAI-compatible Chat Completions |
| Embedding | `hashing-8192-v1` |
| Schema scope | Top-K retrieval, `top_k=4` |
| Maximum few-shot examples | 3 |
| Maximum corrections | 3 after the first attempt |
| Prompt version | `schema-grounded-v1` |
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

The run did not use `--smoke`; the model did not receive benchmark reference SQL.

### Overall Results

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

### Results by Difficulty

| Difficulty | Questions | First valid | Final valid | Correct | Accuracy |
|---|---:|---:|---:|---:|---:|
| Easy | 8 | 8 | 8 | 8 | 100.00% |
| Medium | 8 | 8 | 8 | 8 | 100.00% |
| Hard | 9 | 7 | 8 | 7 | 77.78% |

### Tokens and Latency

The 24 completed provider responses reported 18,940 prompt tokens and 4,372 completion
tokens, or 23,312 known tokens. One case returned no complete usage record, so these
figures are known usage rather than an exact run total. End-to-end latency across all
25 cases was approximately 50.817 seconds.

### Non-Passing Cases

- `h01`: schema recall was 66.67%, with `order_items` missing. The provider reported
  a truncated model output, so no query reached validation or execution.
- `h04`: schema recall was 50%, with `order_items` missing. A corrected query passed
  validation but returned an empty result instead of the five unsold products in the
  reference result.

This is one run on a single database and 25 questions. The metrics describe the
measured behavior of this exact configuration.

## 4. Oracle Pipeline Evaluation

Artifact: [oracle-retrieval.json](../reports/oracle-retrieval.json). This run replays
reference SQL to exercise retrieval, validation, correction, execution, and scoring.
It is a pipeline evaluation, not a model-capability score.

| Metric | Result |
|---|---:|
| Questions | 25 |
| Valid on first attempt | 18/25 (72%) |
| Valid after correction | 23/25 (92%) |
| Validation recovery | 5/7 (71.43%) |
| Execution agreement | 23/25 (92%) |
| Mean schema recall | 96.67% |

```bash
python -m text2sql.cli \
  --evaluate --smoke \
  --db data/evaluation.db \
  --output reports/local-oracle.json
```

## 5. Schema-Scope Comparison

Artifact: [oracle-ablation.json](../reports/oracle-ablation.json). Both arms disable
few-shot examples and use the same questions, database, hashing embedding, and retry
policy.

| Metric | Full schema | Top-K=4 schema |
|---|---:|---:|
| Mean initial prompt characters | 3,271.0 | 2,396.6 |
| Mean total prompt characters | 3,965.0 | 3,559.84 |
| Execution agreement | 25/25 | 23/25 |

On this seven-table dataset, Top-K retrieval reduced the initial prompt character count
by approximately 26.7%. Two cases did not agree because required tables were absent.
The run uses scripted replay, so its latency is not model-inference latency.

```bash
python -m text2sql.cli \
  --ablation --smoke \
  --db data/evaluation.db \
  --output reports/local-ablation.json
```

## 6. Automated Verification

```bash
python -m unittest discover -v
```

The recorded run passed all 33 tests. Coverage includes database setup, schema and
few-shot retrieval, prompt construction, provider response handling, SQL safety,
SQLite `EXPLAIN`, execution budgets, correction, the complete pipeline, CLI output,
tracing, and evaluation metrics.

## 7. Historical API Connectivity Record

[real-model-status.json](../reports/real-model-status.json) records a September 7, 2026
connectivity probe for `gpt-4.1-mini`. The service returned HTTP 401, so that benchmark
did not run. The later DeepSeek experiment completed the real-model evaluation.
