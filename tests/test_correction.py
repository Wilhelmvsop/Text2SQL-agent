from tests.helpers import DatabaseTest
from text2sql.agent.correction import CorrectionLoop
from text2sql.generation.llm import FakeLLMProvider
from text2sql.generation.sql_generator import SQLGenerator
from text2sql.validation.validator import SQLValidator


class CorrectionTests(DatabaseTest):
    def test_recovery(self):
        fake = FakeLLMProvider(['SELECT bogus FROM customers', 'SELECT name FROM customers'])
        loop = CorrectionLoop(SQLGenerator(fake), SQLValidator(self.db))
        attempts = []
        sql = loop.run('List customer names', self.tables, [], attempts)
        self.assertEqual(sql, 'SELECT name FROM customers')
        self.assertEqual(len(attempts), 2)
        self.assertIn('no such column', fake.calls[1][1]['content'])

    def test_three_total_failures_terminate(self):
        fake = FakeLLMProvider(['SELECT bogus FROM customers'] * 3)
        attempts = []
        sql = CorrectionLoop(SQLGenerator(fake), SQLValidator(self.db), max_retries=2).run('q', self.tables, [], attempts)
        self.assertIsNone(sql)
        self.assertEqual(len(fake.calls), 3)

    def test_unsafe_does_not_retry(self):
        fake = FakeLLMProvider(['DROP TABLE customers', 'SELECT 1'])
        attempts = []
        self.assertIsNone(CorrectionLoop(SQLGenerator(fake), SQLValidator(self.db)).run('q', self.tables, [], attempts))
        self.assertEqual(len(fake.calls), 1)
