import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SUMMARY_FIELDS = ('id', 'kind', 'parent_id', 'question', 'status', 'error_type', 'final_sql',
                  'row_count', 'latency', 'starred', 'created_at')

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('agent', 'manual')),
    parent_id TEXT REFERENCES queries(id) ON DELETE SET NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    error_type TEXT,
    final_sql TEXT,
    result TEXT,
    row_count INTEGER,
    latency REAL NOT NULL DEFAULT 0,
    trace TEXT,
    starred INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS queries_created ON queries(created_at DESC);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class AppStore:
    """Query history and settings, kept apart from the read-only business database."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA journal_mode=WAL')
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add(self, *, kind: str, question: str, status: str, error: str | None = None,
            error_type: str | None = None, final_sql: str | None = None, result: dict | None = None,
            latency: float = 0., trace: dict | None = None, parent_id: str | None = None) -> dict:
        record = {'id': uuid.uuid4().hex, 'kind': kind, 'parent_id': parent_id, 'question': question,
                  'status': status, 'error': error, 'error_type': error_type, 'final_sql': final_sql,
                  'result': result, 'row_count': len(result['rows']) if result else None,
                  'latency': latency, 'trace': trace, 'starred': False,
                  'created_at': datetime.now(timezone.utc).isoformat()}
        with self.connect() as conn:
            if parent_id is not None and conn.execute('SELECT 1 FROM queries WHERE id=?', (parent_id,)).fetchone() is None:
                record['parent_id'] = parent_id = None
            conn.execute(
                'INSERT INTO queries VALUES (:id, :kind, :parent_id, :question, :status, :error, :error_type, '
                ':final_sql, :result, :row_count, :latency, :trace, :starred, :created_at)',
                {**record, 'result': _dump(result), 'trace': _dump(trace), 'starred': 0})
        return record

    def get(self, query_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM queries WHERE id=?', (query_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        record['result'] = json.loads(record['result']) if record['result'] else None
        record['trace'] = json.loads(record['trace']) if record['trace'] else None
        record['starred'] = bool(record['starred'])
        return record

    def list(self, search: str = '', status: str | None = None, starred: bool | None = None,
             limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        clauses, params = [], []
        if search:
            escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("(question LIKE ? ESCAPE '\\' OR final_sql LIKE ? ESCAPE '\\')")
            params += [f'%{escaped}%'] * 2
        if status == 'failed':
            clauses.append("status <> 'success'")
        elif status:
            clauses.append('status = ?')
            params.append(status)
        if starred is not None:
            clauses.append('starred = ?')
            params.append(int(starred))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
        with self.connect() as conn:
            total = conn.execute(f'SELECT COUNT(*) FROM queries {where}', params).fetchone()[0]
            rows = conn.execute(f"SELECT {', '.join(SUMMARY_FIELDS)} FROM queries {where} "
                                'ORDER BY created_at DESC LIMIT ? OFFSET ?', [*params, limit, offset]).fetchall()
        return [{**dict(r), 'starred': bool(r['starred'])} for r in rows], total

    def set_starred(self, query_id: str, starred: bool) -> bool:
        with self.connect() as conn:
            return conn.execute('UPDATE queries SET starred=? WHERE id=?', (int(starred), query_id)).rowcount > 0

    def settings(self) -> dict:
        with self.connect() as conn:
            return {r['key']: json.loads(r['value']) for r in conn.execute('SELECT key, value FROM settings')}

    def save_settings(self, values: dict) -> None:
        with self.connect() as conn:
            conn.execute('DELETE FROM settings')
            conn.executemany('INSERT INTO settings VALUES (?, ?)',
                             [(k, json.dumps(v)) for k, v in values.items()])

    def delete(self, query_id: str) -> bool:
        with self.connect() as conn:
            return conn.execute('DELETE FROM queries WHERE id=?', (query_id,)).rowcount > 0


def _dump(value: dict | None) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)
