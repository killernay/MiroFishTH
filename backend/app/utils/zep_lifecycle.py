"""Process-local lifecycle coordination for Zep Cloud graphs.

The lock is intentionally keyed by graph ID so graph deletion/reset and a new
simulation updater claim cannot pass each other between validation and their
Cloud mutation.  It complements (but does not replace) a distributed lock in
multi-worker deployments.
"""

import os
import sqlite3
import threading
import time


_graph_locks: dict[str, threading.RLock] = {}
_graph_locks_guard = threading.Lock()
_lease_db = os.environ.get(
    "MIROFISH_GRAPH_LEASE_DB",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../uploads/.graph_read_leases.sqlite3")),
)


class PersistentGraphReadLeaseStore:
    """SQLite adapter so reader leases survive worker boundaries and restarts."""

    def __init__(self, path: str = _lease_db):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS graph_read_leases ("
                "graph_id TEXT NOT NULL, reader_id TEXT NOT NULL, expires_at REAL NOT NULL, "
                "PRIMARY KEY (graph_id, reader_id))"
            )

    def register(self, graph_id: str, reader_id: str, expires_at: float) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM graph_read_leases WHERE expires_at <= ?", (time.time(),))
            conn.execute(
                "INSERT OR REPLACE INTO graph_read_leases(graph_id, reader_id, expires_at) VALUES (?, ?, ?)",
                (graph_id, reader_id, expires_at),
            )

    def unregister(self, graph_id: str, reader_id: str) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM graph_read_leases WHERE graph_id = ? AND reader_id = ?", (graph_id, reader_id))

    def readers(self, graph_id: str) -> list[str]:
        with sqlite3.connect(self.path) as conn:
            now = time.time()
            conn.execute("DELETE FROM graph_read_leases WHERE expires_at <= ?", (now,))
            return [row[0] for row in conn.execute(
                "SELECT reader_id FROM graph_read_leases WHERE graph_id = ? ORDER BY reader_id", (graph_id,)
            )]


_lease_store = PersistentGraphReadLeaseStore()


def graph_lifecycle_lock(graph_id: str) -> threading.RLock:
    """Return the process-local re-entrant lifecycle lock for ``graph_id``."""

    if not graph_id:
        raise ValueError("graph_id is required for lifecycle locking")
    with _graph_locks_guard:
        return _graph_locks.setdefault(graph_id, threading.RLock())


def register_graph_reader(graph_id: str, reader_id: str, ttl_seconds: float = 3600.0) -> None:
    """Register a long-running read lease under the graph lifecycle lock."""

    if not reader_id:
        raise ValueError("reader_id is required")
    with graph_lifecycle_lock(graph_id):
        _lease_store.register(graph_id, reader_id, time.time() + ttl_seconds)


def unregister_graph_reader(graph_id: str, reader_id: str) -> None:
    """Release a previously registered graph read lease."""

    with graph_lifecycle_lock(graph_id):
        _lease_store.unregister(graph_id, reader_id)


def get_graph_readers(graph_id: str) -> list[str]:
    """Return active reader IDs while serializing with lifecycle mutations."""

    with graph_lifecycle_lock(graph_id):
        return _lease_store.readers(graph_id)
