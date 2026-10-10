import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import AsyncIterator

UPLOAD_LIMIT = 200 * 1024 * 1024
SQLITE_HEADER = b'SQLite format 3\x00'


class UploadError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def upload_target(directory: Path, filename: str) -> Path:
    """A fresh path inside the uploads folder; the client's name is only used as a readable label."""
    stem = re.sub(r'[^A-Za-z0-9_-]+', '_', Path(filename.replace('\\', '/')).stem)[:60].strip('_')
    return directory / f'{stem or "database"}-{uuid.uuid4().hex[:8]}.db'


async def receive(chunks: AsyncIterator[bytes], target: Path, limit: int | None = None) -> int:
    """Stream the request body to target, stopping as soon as it passes the size limit."""
    limit = UPLOAD_LIMIT if limit is None else limit
    size = 0
    with target.open('xb') as out:
        async for chunk in chunks:
            size += len(chunk)
            if size > limit:
                raise UploadError(f'The file is larger than the {limit // (1024 * 1024)} MB limit', 413)
            out.write(chunk)
    if size == 0:
        raise UploadError('The uploaded file is empty')
    return size


def prepare(path: Path) -> int:
    """Check the upload is a usable SQLite database and make it a standalone file; returns its table count."""
    with path.open('rb') as file:
        if file.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
            raise UploadError('This is not a SQLite database file. Upload a .db, .sqlite, or .sqlite3 file.')
    try:
        with closing(sqlite3.connect(path)) as conn:
            conn.execute('PRAGMA trusted_schema=OFF')
            # A WAL-mode file cannot be opened read-only on its own, so switch this private copy to a rollback journal.
            conn.execute('PRAGMA journal_mode=DELETE')
            check = conn.execute('PRAGMA quick_check').fetchone()[0]
            if check != 'ok':
                raise UploadError(f'The database file is damaged: {check}')
            tables = conn.execute("SELECT COUNT(*) FROM sqlite_schema "
                                  "WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        raise UploadError(f'The database could not be opened: {exc}') from exc
    if tables == 0:
        raise UploadError('The database has no tables to query')
    return tables
