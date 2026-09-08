import hashlib
import math
import platform
import sqlite3
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from importlib.resources import files

from text2sql.config import Config
from text2sql.db.connection import QueryResult
from text2sql.evaluation.benchmark import load_benchmark
from text2sql.factory import build_agent
from text2sql.generation.llm import FakeLLMProvider
from text2sql.generation.prompts import PROMPT_VERSION


def same_cell(left: object, right: object) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-6)
    return type(left) is type(right) and left == right


def same_row(left: list, right: list) -> bool:
    return len(left) == len(right) and all(same_cell(a, b) for a, b in zip(left, right))


def results_equal(actual: QueryResult | None, expected: QueryResult, ordered: bool) -> bool:
    if actual is None or actual.truncated or expected.truncated:
        return False
    if len(actual.columns) != len(expected.columns) or len(actual.rows) != len(expected.rows):
        return False
    if ordered:
        return all(same_row(a, b) for a, b in zip(actual.rows, expected.rows))
    # Maximum bipartite matching preserves duplicates even with approximate numeric equality.
    edges = [[j for j, b in enumerate(expected.rows) if same_row(a, b)] for a in actual.rows]
    matched: dict[int, int] = {}
    for root in range(len(edges)):
        queue = [root]
        parent: dict[int, tuple[int, int] | None] = {root: None}
        found = None
        for left in queue:
            for right in edges[left]:
                if right not in matched:
                    found = (left, right)
                    break
                other = matched[right]
                if other not in parent:
                    parent[other] = (left, right)
                    queue.append(other)
            if found is not None:
                break
        if found is None:
            return False
        left, right = found
        while True:
            matched[right] = left
            prior = parent[left]
            if prior is None:
                break
            left, right = prior
    return True


def summarize(records: list[dict]) -> dict:
    total = len(records)
    first = sum(r['first_pass_valid'] for r in records)
    valid = sum(r['final_valid'] for r in records)
    correct = sum(r['execution_correct'] for r in records)
    failed_first = sum(r['initial_validation_failed'] for r in records)
    recovered = sum(r['recovered'] for r in records)
    return {
        'total_questions': total, 'first_pass_valid': first, 'final_valid_queries': valid,
        'self_correction_recovered': recovered, 'initial_validation_failures': failed_first,
        'execution_correct': correct,
        'provider_failures': sum(r.get('provider_failed', False) for r in records),
        'first_pass_success_rate': first / total if total else None,
        'validation_success_rate': valid / total if total else None,
        'self_correction_recovery_rate': recovered / failed_first if failed_first else None,
        'execution_accuracy': correct / total if total else None,
        'mean_schema_recall': statistics.mean(r['schema_recall'] for r in records) if records else None,
        'mean_initial_prompt_chars': statistics.mean(r['initial_prompt_chars'] for r in records) if records else None,
        'mean_total_prompt_chars': statistics.mean(r['total_prompt_chars'] for r in records) if records else None,
        'mean_generation_latency_seconds': statistics.mean(r['generation_latency'] for r in records) if records else None,
        'mean_end_to_end_latency_seconds': statistics.mean(r['latency'] for r in records) if records else None,
        'token_usage': {k: sum(r['token_usage'].get(k, 0) for r in records)
                        for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
                       if records and all('total_tokens' in r['token_usage'] for r in records) else None,
    }


def run_evaluation(config: Config, smoke: bool = False, full_schema: bool = False,
                   fewshot_k: int = 3) -> dict:
    if not smoke and config.llm == 'fake':
        raise ValueError('Real evaluation requires TEXT2SQL_LLM=api. Use --smoke only for labeled oracle replay.')
    agent = build_agent(config, provider=FakeLLMProvider([]) if smoke else None,
                        full_schema=full_schema, fewshot_k=fewshot_k)
    all_tables = {t.name for t in agent.schema_retriever.index.tables}
    records = []
    for number, case in enumerate(load_benchmark()):
        expected = agent.executor.execute(case.sql, all_tables)
        if expected.truncated:
            raise ValueError(f'Gold result truncated: {case.id}; increase evaluation row budget')
        if smoke:
            responses = (['SELECT missing_column FROM customers'] if number % 5 == 0 else [])
            responses += [case.sql] * (config.max_retries + 1)
            agent.correction.generator.provider = FakeLLMProvider(responses)
        # Only the question crosses the generation boundary in real-model evaluation.
        result = agent.run(case.question)
        attempts = result.validation_attempts
        first_valid = bool(attempts and attempts[0].validation.valid)
        final_valid = bool(attempts and attempts[-1].validation.valid)
        initially_failed = bool(attempts and not first_valid)
        records.append({
            'id': case.id, 'difficulty': case.difficulty, 'question': case.question,
            'first_pass_valid': first_valid, 'initial_validation_failed': initially_failed,
            'final_valid': final_valid, 'recovered': initially_failed and final_valid,
            'provider_failed': not attempts and result.status == 'error',
            'execution_correct': results_equal(result.execution_result, expected, case.ordered),
            'schema_recall': len(set(case.tables) & set(result.retrieved_tables)) / len(case.tables),
            'initial_prompt_chars': attempts[0].prompt_chars if attempts else 0,
            'total_prompt_chars': sum(a.prompt_chars for a in attempts),
            'generation_latency': sum(a.generation_latency for a in attempts),
            'latency': result.latency, 'token_usage': result.token_usage,
            'expected_result': asdict(expected), 'trace': result.to_dict(),
        })
    responses_received = any(r['trace']['validation_attempts'] for r in records)
    return {
        'mode': 'oracle_replay_NOT_model_accuracy' if smoke else 'real_model',
        'status': 'completed' if responses_received else 'provider_unavailable',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'model': agent.correction.generator.provider.name,
        'embedding': agent.schema_retriever.index.embeddings.name,
        'full_schema': full_schema, 'top_k': config.top_k, 'fewshot_k': fewshot_k,
        'max_retries': config.max_retries, 'prompt_version': PROMPT_VERSION,
        'database_sha256': hashlib.sha256(config.db_path.read_bytes()).hexdigest(),
        'benchmark_sha256': hashlib.sha256(files('text2sql').joinpath('assets/benchmark.json').read_bytes()).hexdigest(),
        'environment': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                        'numpy': version('numpy'), 'sqlglot': version('sqlglot')},
        'metrics': summarize(records) if responses_received else None,
        'by_difficulty': {d: summarize([r for r in records if r['difficulty'] == d]) for d in ('easy', 'medium', 'hard')} if responses_received else {},
        'cases': records,
    }


def run_ablation(config: Config, smoke: bool = False) -> dict:
    # Disable few-shot in BOTH arms to isolate the schema context intervention.
    return {'experiment': 'full_schema_vs_retrieved_schema',
            'caveat': 'Single run, 7-table fixture. Oracle latency is not real model latency. Few-shot disabled in both arms.',
            'full_schema': run_evaluation(config, smoke, full_schema=True, fewshot_k=0),
            'retrieved_schema': run_evaluation(config, smoke, full_schema=False, fewshot_k=0)}
