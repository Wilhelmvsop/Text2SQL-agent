# Implementation Record

Work was implemented and exercised incrementally in the requested order.

| Phase | Delivered | Verification / outcome |
|---|---|---|
| 1 | Architecture and technology decisions | Protocol boundaries and SQLite security controls reviewed against primary documentation |
| 2 | Seven-table seed and introspection | 3 database tests; fixed connection cleanup warning |
| 3 | Embedding providers, index and cosine retriever | Ranking, normalization, Top-K and invalid vector tests |
| 4 | Few-shot store and schema-compatible retrieval | Subset filtering and retrieval tests |
| 5 | LLM abstraction, prompts and generator | Fake-provider generation/correction payload tests |
| 6 | Output normalization and AST policy | 5 initial safety/structure tests |
| 7 | EXPLAIN and protected execution | Unknown/ambiguous identifiers, functions, truncation and runtime-budget tests |
| 8 | Bounded correction | Recovery, three total failures, immediate unsafe rejection |
| 9 | Full agent and JSONL observability | Fixed SQLite COUNT(*) authorizer database=None behavior; end-to-end tests |
| 10 | CLI and scripted demo | Detected hashing noise/collisions; fixed lexical baseline before benchmark development; demo returned five rows |
| 11 | Broader offline tests | 28 tests including CLI/trace and API response mocks |
| 12 | 25-case benchmark and evaluator | Gold SQL executed; bag/order/tolerance and denominator tests |
| 13 | Integration and regression verification | 33 final local tests passed; editable package installed; CI matrix added but not run remotely |
| 14 | Actual evaluation attempts | Oracle retrieval and schema ablation executed; real API probe reached provider but returned HTTP 401 |
| 15 | Evidence-based README and interview guide | Actual oracle results labeled; real-model metrics explicitly unavailable |

Phase 14's real-model capability evaluation remains blocked by provider authentication.
This is not equivalent to completing a real LLM benchmark. No neural embedding evaluation
has been run. Checked-in reports retain all cases, including two retrieval failures.

The latest local test invocation was `python3 -m unittest discover -v` on Python 3.13.13.
Reference database creation uses seed 42 and refuses to replace existing files.
