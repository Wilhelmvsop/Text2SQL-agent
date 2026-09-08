import unittest

from text2sql.errors import SafetyError
from text2sql.validation.safety import check_static, normalize_sql
from tests.helpers import DatabaseTest
from text2sql.db.connection import SQLiteDatabase
from text2sql.db.executor import SafeExecutor
from text2sql.errors import ExecutionError
from text2sql.validation.validator import SQLValidator


class StaticTests(unittest.TestCase):
    def test_normalization(self):
        for raw in ['```sql\nSELECT 1;\n```', 'Here is the SQL:\nSELECT 1;', ' SELECT 1; ']:
            self.assertEqual(normalize_sql(raw), 'SELECT 1;')
        for raw in ['', '```sql\nSELECT 1\n```\nDROP TABLE customers', '```SQL SELECT 1``` explanation']:
            with self.assertRaises(SafetyError):
                normalize_sql(raw)

    def test_unsafe_and_multiple(self):
        for sql in ['DROP TABLE users', 'SELECT 1; SELECT 2', 'DELETE FROM customers',
                    'PRAGMA table_info(customers)', "ATTACH 'evil.db' AS evil",
                    'WITH x AS (SELECT 1) DELETE FROM customers', 'SELECT 1 INTO customers']:
            with self.subTest(sql=sql), self.assertRaises((SafetyError, ValueError)):
                check_static(sql, {'customers'})

    def test_strings_and_comments_are_not_keywords(self):
        check_static("SELECT 'DROP TABLE x; UPDATE' AS note -- DELETE\n", set())

    def test_schema_and_join_policy(self):
        for sql in ['SELECT name FROM payments', 'SELECT c.name FROM customers c, customers d',
                    'SELECT * FROM customers', 'SELECT name FROM main.customers']:
            with self.subTest(sql=sql), self.assertRaises((SafetyError, ValueError)):
                check_static(sql, {'customers'})

    def test_cte_and_union(self):
        check_static('WITH x AS (SELECT name FROM customers) SELECT name FROM x UNION SELECT name FROM customers', {'customers'})

    def test_parser_nesting_budget(self):
        with self.assertRaises(SafetyError):
            check_static('SELECT ' + '(' * 65 + '1' + ')' * 65, set())


class ExplainTests(DatabaseTest):
    def test_unknown_and_ambiguous_columns(self):
        validator = SQLValidator(self.db)
        unknown = validator.validate('SELECT nonexistent FROM customers', {'customers'})
        self.assertEqual(unknown.error_type, 'unknown_column')
        self.assertEqual(unknown.stage, 'explain')
        ambiguous = validator.validate('SELECT customer_id FROM customers c JOIN orders o ON c.customer_id=o.customer_id', {'customers', 'orders'})
        self.assertEqual(ambiguous.error_type, 'ambiguous_column')
        self.assertFalse(validator.validate('SELECT bogus(name) FROM customers', {'customers'}).valid)

    def test_functions_and_metadata_blocked(self):
        for sql in ["SELECT load_extension('evil')", 'SELECT name FROM sqlite_schema',
                    "SELECT name FROM pragma_table_info('customers')", 'SELECT randomblob(9999999)',
                    'WITH customers AS (SELECT name FROM sqlite_schema) SELECT name FROM customers',
                    'SELECT COUNT(*) FROM payments']:
            with self.subTest(sql=sql):
                self.assertFalse(SQLValidator(self.db).validate(sql, {'customers'}).valid)

    def test_safe_execution_and_truncation(self):
        executor = SafeExecutor(SQLiteDatabase(self.path, max_rows=2))
        result = executor.execute('SELECT name FROM customers ORDER BY customer_id', {'customers'})
        self.assertEqual(len(result.rows), 2)
        self.assertTrue(result.truncated)
        with self.assertRaises(SafetyError):
            executor.execute('DROP TABLE customers', {'customers'})

    def test_execution_budget(self):
        db = SQLiteDatabase(self.path, max_steps=1000)
        sql = 'WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT SUM(n) FROM x'
        self.assertTrue(SQLValidator(db).validate(sql, set()).valid)
        with self.assertRaises(ExecutionError):
            SafeExecutor(db).execute(sql, set())
