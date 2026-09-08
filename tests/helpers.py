import tempfile
import unittest
from pathlib import Path

from text2sql.db.connection import SQLiteDatabase
from text2sql.db.seed import DESCRIPTIONS, seed_database


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.db"
        self.counts = seed_database(self.path)
        self.db = SQLiteDatabase(self.path, DESCRIPTIONS)
        self.tables = self.db.introspect()
