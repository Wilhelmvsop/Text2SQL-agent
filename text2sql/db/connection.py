import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

from text2sql.db.schema import Column, ForeignKey, TableSchema
from text2sql.errors import DatabaseValidationError, ExecutionError

SAFE_FUNCTIONS = frozenset({
    "abs", "avg", "coalesce", "count", "date", "datetime", "strftime", "julianday",
    "ifnull", "nullif", "lower", "upper", "length", "min", "max", "round", "sum",
    "total", "substr", "substring", "trim", "ltrim", "rtrim", "replace", "like", "glob",
    "group_concat", "row_number", "rank", "dense_rank", "lag", "lead", "ntile",
    "first_value", "last_value", "nth_value", "percent_rank", "cume_dist", "iif",
})


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[object]]
    truncated: bool = False


class Database(Protocol):
    dialect: str

    def introspect(self) -> list[TableSchema]: ...
    def explain(self, sql: str, allowed_tables: set[str]) -> None: ...
    def execute_readonly(self, sql: str, allowed_tables: set[str]) -> QueryResult: ...


class SQLiteDatabase:
    dialect = "sqlite"

    def __init__(self, path: Path, descriptions: dict[str, str] | None = None,
                 max_rows: int = 1000, timeout: float = 2.0, max_steps: int = 2_000_000):
        if max_rows < 1 or timeout <= 0 or max_steps < 1:
            raise ValueError("Execution budgets must be positive")
        self.path = path.resolve()
        self.descriptions = descriptions or {}
        self.max_rows, self.timeout, self.max_steps = max_rows, timeout, max_steps

    @contextmanager
    def connect(self, allowed_tables: set[str] | None = None) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=self.timeout)
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA trusted_schema=OFF")
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 100_000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 200)
            conn.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
            if allowed_tables is not None:
                allowed = {t.casefold() for t in allowed_tables}

                def authorize(action: int, arg1: str | None, arg2: str | None,
                              database: str | None, source: str | None) -> int:
                    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
                        return sqlite3.SQLITE_OK
                    # SQLite reports COUNT(*) reads with column='' and database=None.
                    main_read = database == "main" or (database is None and arg2 == '')
                    if action == sqlite3.SQLITE_READ and main_read and (arg1 or "").casefold() in allowed:
                        return sqlite3.SQLITE_OK
                    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").casefold() in SAFE_FUNCTIONS:
                        return sqlite3.SQLITE_OK
                    return sqlite3.SQLITE_DENY

                conn.set_authorizer(authorize)
            deadline = time.monotonic() + self.timeout
            steps = 0

            def progress() -> int:
                nonlocal steps
                steps += 100
                return int(steps >= self.max_steps or time.monotonic() > deadline)

            conn.set_progress_handler(progress, 100)
            yield conn
        finally:
            conn.close()

    def introspect(self) -> list[TableSchema]:
        with self.connect() as conn:
            names = [row[0] for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            tables = []
            for name in names:
                quoted = '"' + name.replace('"', '""') + '"'
                cols = tuple(Column(r[1], r[2], bool(r[5]), not bool(r[3] or r[5]))
                             for r in conn.execute(f"PRAGMA table_info({quoted})"))
                fks = tuple(ForeignKey(r[3], r[2], r[4])
                            for r in conn.execute(f"PRAGMA foreign_key_list({quoted})"))
                tables.append(TableSchema(name, cols, fks, self.descriptions.get(name, "")))
            return tables

    def explain(self, sql: str, allowed_tables: set[str]) -> None:
        try:
            with self.connect(allowed_tables) as conn:
                conn.execute("EXPLAIN " + sql).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseValidationError(str(exc)) from exc

    def execute_readonly(self, sql: str, allowed_tables: set[str]) -> QueryResult:
        try:
            with self.connect(allowed_tables) as conn:
                cursor = conn.execute(sql)
                rows = cursor.fetchmany(self.max_rows + 1)
                return QueryResult([c[0] for c in cursor.description],
                                   [list(r) for r in rows[:self.max_rows]], len(rows) > self.max_rows)
        except sqlite3.Error as exc:
            raise ExecutionError(str(exc)) from exc
