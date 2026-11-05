"""Concurrent local SQLite cache. Only validated outputs are persisted."""
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class ResponseCache:
    def __init__(self, directory: Path, ttl_seconds: int):
        self.directory, self.ttl_seconds = Path(directory), ttl_seconds

    @contextmanager
    def _connect(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.directory / "responses.sqlite3", timeout=5)
        try:
            with connection:
                connection.execute("CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, output TEXT NOT NULL, created REAL NOT NULL)")
                connection.execute("CREATE INDEX IF NOT EXISTS response_expiry ON responses(created)")
                yield connection
        finally:
            connection.close()

    def get(self, key: str) -> str | None:
        try:
            with self._connect() as connection:
                row = connection.execute("SELECT output, created FROM responses WHERE key = ?", (key,)).fetchone()
                if row and row[1] > time.time() - self.ttl_seconds:
                    return row[0]
        except (OSError, sqlite3.Error):
            logger.warning("LLM cache unavailable; continuing without cached output.")
        return None

    def put(self, key: str, output: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM responses WHERE created <= ?", (time.time() - self.ttl_seconds,))
                connection.execute("INSERT OR REPLACE INTO responses VALUES (?, ?, ?)", (key, output, time.time()))
        except (OSError, sqlite3.Error):
            logger.warning("Could not save LLM cache; generated reports remain available.")
