import sqlite3

from tests.helpers import DatabaseTest


class DatabaseTests(DatabaseTest):
    def test_seed_and_introspection(self):
        self.assertEqual(len(self.tables), 7)
        self.assertEqual(self.counts['orders'], 360)
        self.assertGreater(self.counts['order_items'], 1000)
        orders = next(t for t in self.tables if t.name == 'orders')
        self.assertEqual(orders.foreign_keys[0].target_table, 'customers')
        with self.db.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_seed_never_overwrites(self):
        from text2sql.db.seed import seed_database
        with self.assertRaises(FileExistsError):
            seed_database(self.path)

    def test_readonly_authorizer(self):
        with self.db.connect({'customers'}) as conn:
            with self.assertRaises(sqlite3.Error):
                conn.execute('DELETE FROM customers')
            with self.assertRaises(sqlite3.Error):
                conn.execute('SELECT * FROM payments')
