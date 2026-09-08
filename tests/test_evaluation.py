import unittest

from tests.helpers import DatabaseTest
from text2sql.db.connection import QueryResult
from text2sql.db.executor import SafeExecutor
from text2sql.evaluation.benchmark import load_benchmark
from text2sql.evaluation.evaluator import results_equal, summarize
from text2sql.retrieval.fewshot import load_examples


class ComparisonTests(unittest.TestCase):
    def test_bag_order_null_and_tolerance(self):
        a = QueryResult(['a'], [[1.0], [None], [1.0]])
        b = QueryResult(['alias'], [[None], [1.00000001], [1]])
        self.assertTrue(results_equal(a, b, False))
        self.assertFalse(results_equal(a, b, True))
        self.assertFalse(results_equal(a, QueryResult(['a'], [[1], [None]]), False))
        self.assertFalse(results_equal(a, QueryResult(['a'], [[1], [None], [None]]), False))
        self.assertFalse(results_equal(QueryResult(['a'], [[1]], True), QueryResult(['a'], [[1]]), False))
        self.assertFalse(results_equal(QueryResult(['a','b'], []), QueryResult(['a'], []), False))

    def test_metric_denominators(self):
        records = [dict(first_pass_valid=False, final_valid=True, initial_validation_failed=True,
                        recovered=True, execution_correct=False, schema_recall=1., initial_prompt_chars=10,
                        total_prompt_chars=30, generation_latency=.1, latency=.2, token_usage={}),
                   dict(first_pass_valid=True, final_valid=True, initial_validation_failed=False,
                        recovered=False, execution_correct=True, schema_recall=1., initial_prompt_chars=10,
                        total_prompt_chars=10, generation_latency=.1, latency=.2, token_usage={})]
        metrics = summarize(records)
        self.assertEqual(metrics['execution_accuracy'], .5)
        self.assertEqual(metrics['self_correction_recovery_rate'], 1.)
        self.assertIsNone(metrics['token_usage'])


class BenchmarkTests(DatabaseTest):
    def test_fewshot_queries_are_grounded(self):
        executor = SafeExecutor(self.db)
        for example in load_examples():
            with self.subTest(example=example.id):
                self.assertFalse(executor.execute(example.sql, set(example.tables)).truncated)

    def test_gold_queries_and_split(self):
        benchmark = load_benchmark()
        self.assertEqual(len(benchmark), 25)
        self.assertEqual(len({c.id for c in benchmark}), 25)
        self.assertFalse({c.question for c in benchmark} & {e.question for e in load_examples()})
        executor = SafeExecutor(self.db)
        for case in benchmark:
            with self.subTest(case=case.id):
                result = executor.execute(case.sql, set(case.tables))
                self.assertFalse(result.truncated)
                self.assertGreater(len(result.rows), 0)
