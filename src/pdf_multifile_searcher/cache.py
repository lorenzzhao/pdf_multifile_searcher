"""Text cache (FR-CACHE).

Extracted page text is stored in a SQLite database in the user's cache directory, keyed by
the resolved file path, its modification time and its size. A cached file is never opened
again while it is unchanged (FR-CACHE-03). Match rectangles are not stored: matches keep
character offsets, and the viewer turns them into rectangles when it shows the page.

Only one writer may use the cache at a time (FR-CACHE-07). Search workers open it
read-only; the search runner in the main process writes. Any cache problem degrades to
"not cached" and never stops a search (FR-CACHE-06).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import zlib
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from pdf_multifile_searcher import APP_ID

log = logging.getLogger(__name__)

FORMAT_VERSION = 1


def default_cache_path() -> Path:
    return Path(platformdirs.user_cache_dir(APP_ID, appauthor=False)) / "text-cache.sqlite3"


@dataclass(frozen=True)
class FileKey:
    path: str  # resolved path
    mtime_ns: int
    size: int

    @classmethod
    def for_file(cls, path: str) -> FileKey:
        real = os.path.realpath(path)
        st = os.stat(real)
        return cls(real, st.st_mtime_ns, st.st_size)


@dataclass(frozen=True)
class CachedText:
    pages: list[str] | None  # None when the file could not be opened
    error: str | None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    backend TEXT NOT NULL,
    error TEXT,
    pages BLOB
);
"""


def _encode(pages: list[str]) -> bytes:
    return zlib.compress(json.dumps(pages, ensure_ascii=False).encode("utf-8"), 6)


def _decode(blob: bytes) -> list[str]:
    data = json.loads(zlib.decompress(blob).decode("utf-8"))
    if not isinstance(data, list) or not all(isinstance(p, str) for p in data):
        raise ValueError("unexpected cache content")
    return data


class TextCache:
    """Access to the cache database. Not thread-safe: use one instance per thread."""

    def __init__(self, path: Path, backend_id: str, readonly: bool = False) -> None:
        self.path = path
        self.backend_id = backend_id
        self.readonly = readonly
        self._conn: sqlite3.Connection | None = None
        self._broken = False
        self._rebuilt = False

    # -- connection handling -------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection | None:
        if self._conn is not None:
            return self._conn
        if self._broken:
            return None
        try:
            if self.readonly:
                if not self.path.exists():
                    return None
                conn = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=2.0)
            else:
                self._create_private_file()
                conn = sqlite3.connect(self.path, timeout=5.0)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(_SCHEMA)
                self._check_format(conn)
            self._conn = conn
            return conn
        except (sqlite3.Error, OSError) as exc:
            self._fail(exc, rebuild=not self.readonly)
            return self._conn

    def _create_private_file(self) -> None:
        """Create the database readable by the user only (NFR-SEC-04)."""
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)

    def _check_format(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT value FROM meta WHERE key='format'").fetchone()
        if row is None or row[0] != str(FORMAT_VERSION):
            with conn:
                conn.execute("DELETE FROM files")
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES ('format', ?)",
                    (str(FORMAT_VERSION),),
                )

    def _fail(self, exc: BaseException, rebuild: bool) -> None:
        log.warning("Text cache unavailable (%s): %s", self.path, exc)
        self.close()
        if rebuild and not self._rebuilt:
            # One attempt per session to rebuild a corrupt cache from scratch (FR-CACHE-06).
            self._rebuilt = True
            try:
                self._delete_files()
            except OSError as exc2:
                log.warning("Could not rebuild text cache: %s", exc2)
                self._broken = True
                return
            self._connect()
        else:
            self._broken = True

    def _delete_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                candidate.unlink()

    def close(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(sqlite3.Error):
                self._conn.close()
            self._conn = None

    # -- operations ----------------------------------------------------------------------

    def lookup(self, key: FileKey) -> CachedText | None:
        conn = self._connect()
        if conn is None:
            return None
        try:
            row = conn.execute(
                "SELECT mtime_ns, size, backend, error, pages FROM files WHERE path=?",
                (key.path,),
            ).fetchone()
        except sqlite3.Error as exc:
            self._fail(exc, rebuild=False)
            return None
        if row is None:
            return None
        mtime_ns, size, backend, error, blob = row
        if mtime_ns != key.mtime_ns or size != key.size or backend != self.backend_id:
            return None
        if error is not None:
            return CachedText(None, error)
        try:
            return CachedText(_decode(blob), None)
        except (ValueError, zlib.error, TypeError):
            return None

    def store(self, key: FileKey, pages: list[str] | None, error: str | None) -> None:
        if self.readonly:
            raise RuntimeError("read-only cache")
        conn = self._connect()
        if conn is None:
            return
        blob = _encode(pages) if pages is not None else None
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO files(path, mtime_ns, size, backend, error, pages) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (key.path, key.mtime_ns, key.size, self.backend_id, error, blob),
                )
        except sqlite3.Error as exc:
            self._fail(exc, rebuild=True)

    def prune(self, roots: list[str]) -> int:
        """Remove entries for files that no longer exist below one of `roots` (FR-CACHE-05).

        Entries outside the given roots are kept, so files on an unmounted drive are not
        forgotten just because the drive is missing.
        """
        conn = self._connect()
        if conn is None:
            return 0
        prefixes = []
        for root in roots:
            real = os.path.realpath(root)
            if os.path.isdir(real):
                prefixes.append(real.rstrip(os.sep) + os.sep)
        if not prefixes:
            return 0
        try:
            rows = conn.execute("SELECT path FROM files").fetchall()
            stale = [
                (p,)
                for (p,) in rows
                if any(p.startswith(prefix) for prefix in prefixes) and not os.path.exists(p)
            ]
            if stale:
                with conn:
                    conn.executemany("DELETE FROM files WHERE path=?", stale)
            return len(stale)
        except sqlite3.Error as exc:
            self._fail(exc, rebuild=True)
            return 0

    def clear(self) -> None:
        """Delete the cache completely (NFR-SEC-04)."""
        self.close()
        try:
            self._delete_files()
        except OSError as exc:
            log.warning("Could not delete text cache: %s", exc)
        self._broken = False
        self._rebuilt = False

    def size_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            with contextlib.suppress(OSError):
                total += Path(f"{self.path}{suffix}").stat().st_size
        return total
