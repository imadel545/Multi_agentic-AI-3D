from __future__ import annotations

import io
import json
import pickle
import sqlite3
import struct
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    RunnableConfig,
)

_SERIALIZATION_MAGIC = b"TSCP\x01"
_TYPE_LENGTH = struct.Struct(">H")
_DEFAULT_MAX_BLOB_BYTES = 32 * 1024 * 1024
_DEFAULT_MAX_WRITES_PER_CHECKPOINT = 10_000
_MAX_RETENTION_BATCH = 1_000


class CheckpointIntegrityError(RuntimeError):
    """Raised when persisted checkpoint state violates storage invariants."""


class _PrimitiveOnlyUnpickler(pickle.Unpickler):
    """Read the historical ``(type, bytes)`` envelope without loading globals."""

    def find_class(self, module: str, name: str) -> Any:
        raise pickle.UnpicklingError(f"legacy pickle global is forbidden: {module}.{name}")


@dataclass(frozen=True)
class CheckpointIntegrityReport:
    quick_check: str
    orphan_writes: int
    legacy_primary_key: bool

    @property
    def ok(self) -> bool:
        return self.quick_check == "ok" and self.orphan_writes == 0


@dataclass(frozen=True)
class CheckpointDeletionResult:
    checkpoints_deleted: int
    writes_deleted: int


@dataclass(frozen=True)
class CheckpointRetentionResult:
    deleted_thread_ids: tuple[str, ...]
    remaining_over_quota: int


@dataclass(frozen=True)
class CheckpointCompactionResult:
    compacted: bool
    reclaimable_bytes: int
    reclaimed_bytes: int


class SqliteCheckpointSaver(BaseCheckpointSaver):
    """Persistent local LangGraph saver with bounded SQLite operations.

    Checkpoints remain complete LangGraph serializer payloads. Retention therefore
    removes complete threads or namespaces; it never cuts an ancestor chain in the
    middle. Historical rows wrapped with primitive-only pickle remain readable,
    while all new rows use a non-executable typed binary envelope.
    """

    def __init__(
        self,
        db_path: Path,
        *,
        busy_timeout_seconds: float = 30.0,
        max_blob_bytes: int = _DEFAULT_MAX_BLOB_BYTES,
        max_writes_per_checkpoint: int = _DEFAULT_MAX_WRITES_PER_CHECKPOINT,
    ) -> None:
        super().__init__()
        if busy_timeout_seconds <= 0:
            raise ValueError("busy_timeout_seconds must be positive")
        if max_blob_bytes <= len(_SERIALIZATION_MAGIC) + _TYPE_LENGTH.size:
            raise ValueError("max_blob_bytes is too small for the typed envelope")
        if max_writes_per_checkpoint <= 0:
            raise ValueError("max_writes_per_checkpoint must be positive")
        self.db_path = db_path
        self.busy_timeout_seconds = busy_timeout_seconds
        self.max_blob_bytes = max_blob_bytes
        self.max_writes_per_checkpoint = max_writes_per_checkpoint
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._legacy_primary_key = False
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=self.busy_timeout_seconds,
            isolation_level="DEFERRED",
        )
        conn.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_seconds * 1000)}")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.create_function("checkpoint_metadata_matches", 2, _metadata_matches)
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    checkpoint_json BLOB NOT NULL,
                    metadata_json TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    created_at_ns INTEGER NOT NULL DEFAULT 0,
                    updated_at_ns INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                )
                """
            )
            checkpoint_columns = {row[1] for row in conn.execute("PRAGMA table_info(checkpoints)")}
            for name, definition in (
                ("checkpoint_ns", "TEXT NOT NULL DEFAULT ''"),
                ("created_at_ns", "INTEGER NOT NULL DEFAULT 0"),
                ("updated_at_ns", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if name not in checkpoint_columns:
                    conn.execute(f"ALTER TABLE checkpoints ADD COLUMN {name} {definition}")

            primary_key = [
                row[1]
                for row in sorted(
                    (row for row in conn.execute("PRAGMA table_info(checkpoints)") if row[5]),
                    key=lambda row: row[5],
                )
            ]
            self._legacy_primary_key = primary_key == ["thread_id", "checkpoint_id"]

            conn.execute("DROP INDEX IF EXISTS idx_checkpoints_thread")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_checkpoints_identity "
                "ON checkpoints (thread_id, checkpoint_ns, checkpoint_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_thread "
                "ON checkpoints (thread_id, checkpoint_ns, checkpoint_id DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_retention "
                "ON checkpoints (updated_at_ns DESC, thread_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    write_index INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    value_blob BLOB NOT NULL,
                    task_path TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        task_id,
                        write_index
                    )
                )
                """
            )
            write_columns = {row[1] for row in conn.execute("PRAGMA table_info(checkpoint_writes)")}
            for name, definition in (
                ("checkpoint_ns", "TEXT NOT NULL DEFAULT ''"),
                ("task_path", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in write_columns:
                    conn.execute(f"ALTER TABLE checkpoint_writes ADD COLUMN {name} {definition}")

            # LangGraph may persist a task's writes before it persists the checkpoint
            # that owns them. A foreign key therefore rejects a valid saver ordering.
            # Ownership is checked after an invocation by integrity_report(), while
            # thread/namespace deletion removes both tables atomically.
            if list(conn.execute("PRAGMA foreign_key_list(checkpoint_writes)")):
                conn.execute("ALTER TABLE checkpoint_writes RENAME TO checkpoint_writes_with_fk")
                conn.execute(
                    """
                    CREATE TABLE checkpoint_writes (
                        thread_id TEXT NOT NULL,
                        checkpoint_ns TEXT NOT NULL DEFAULT '',
                        checkpoint_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        write_index INTEGER NOT NULL,
                        channel TEXT NOT NULL,
                        value_blob BLOB NOT NULL,
                        task_path TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY (
                            thread_id,
                            checkpoint_ns,
                            checkpoint_id,
                            task_id,
                            write_index
                        )
                    )
                    """
                )
                conn.execute(
                    "INSERT OR IGNORE INTO checkpoint_writes "
                    "(thread_id, checkpoint_ns, checkpoint_id, task_id, write_index, "
                    "channel, value_blob, task_path) "
                    "SELECT thread_id, checkpoint_ns, checkpoint_id, task_id, write_index, "
                    "channel, value_blob, task_path FROM checkpoint_writes_with_fk"
                )
                conn.execute("DROP TABLE checkpoint_writes_with_fk")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_owner "
                "ON checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id)"
            )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")
        with self._connect() as conn:
            if checkpoint_id:
                row = conn.execute(
                    "SELECT checkpoint_id, checkpoint_json, metadata_json, "
                    "parent_checkpoint_id FROM checkpoints "
                    "WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ? LIMIT 1",
                    (thread_id, checkpoint_ns, checkpoint_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT checkpoint_id, checkpoint_json, metadata_json, "
                    "parent_checkpoint_id FROM checkpoints "
                    "WHERE thread_id = ? AND checkpoint_ns = ? "
                    "ORDER BY checkpoint_id DESC LIMIT 1",
                    (thread_id, checkpoint_ns),
                ).fetchone()
            if not row:
                return None
            return self._checkpoint_tuple(
                conn,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=row[0],
                checkpoint_blob=row[1],
                metadata_json=row[2],
                parent_checkpoint_id=row[3],
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Any,
    ) -> RunnableConfig:
        del new_versions
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        checkpoint_blob = self._serialize(checkpoint)
        metadata_json = json.dumps(metadata, separators=(",", ":"), sort_keys=True)
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        now_ns = time.time_ns()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self._legacy_primary_key:
                existing = conn.execute(
                    "SELECT checkpoint_ns FROM checkpoints "
                    "WHERE thread_id = ? AND checkpoint_id = ? LIMIT 1",
                    (thread_id, checkpoint_id),
                ).fetchone()
                if existing and existing[0] != checkpoint_ns:
                    raise CheckpointIntegrityError(
                        "legacy checkpoint primary key cannot reuse one checkpoint_id "
                        "across namespaces"
                    )
            conn.execute(
                "INSERT INTO checkpoints "
                "(thread_id, checkpoint_ns, checkpoint_id, checkpoint_json, metadata_json, "
                "parent_checkpoint_id, created_at_ns, updated_at_ns) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT DO UPDATE SET "
                "checkpoint_json = excluded.checkpoint_json, "
                "metadata_json = excluded.metadata_json, "
                "parent_checkpoint_id = excluded.parent_checkpoint_id, "
                "updated_at_ns = excluded.updated_at_ns",
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    checkpoint_blob,
                    metadata_json,
                    parent_checkpoint_id,
                    now_ns,
                    now_ns,
                ),
            )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        encoded_writes = [
            (WRITES_IDX_MAP.get(channel, index), channel, self._serialize(value))
            for index, (channel, value) in enumerate(writes)
        ]
        if len(encoded_writes) > self.max_writes_per_checkpoint:
            raise ValueError("pending writes exceed the per-checkpoint quota")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for write_index, channel, value_blob in encoded_writes:
                statement = "INSERT OR REPLACE" if write_index < 0 else "INSERT OR IGNORE"
                conn.execute(
                    f"{statement} INTO checkpoint_writes "
                    "(thread_id, checkpoint_ns, checkpoint_id, task_id, write_index, "
                    "channel, value_blob, task_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        task_id,
                        write_index,
                        channel,
                        value_blob,
                        task_path,
                    ),
                )
            write_count = conn.execute(
                "SELECT COUNT(*) FROM checkpoint_writes "
                "WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?",
                (thread_id, checkpoint_ns, checkpoint_id),
            ).fetchone()[0]
            if write_count > self.max_writes_per_checkpoint:
                raise ValueError("pending writes exceed the per-checkpoint quota")

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> Iterator[CheckpointTuple]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        configurable = config.get("configurable", {}) if config else {}
        thread_id = configurable.get("thread_id")
        checkpoint_ns = configurable.get("checkpoint_ns")
        checkpoint_id = configurable.get("checkpoint_id")
        before_checkpoint_id = (
            before.get("configurable", {}).get("checkpoint_id") if before else None
        )
        query = (
            "SELECT thread_id, checkpoint_ns, checkpoint_id, checkpoint_json, "
            "metadata_json, parent_checkpoint_id FROM checkpoints"
        )
        clauses: list[str] = []
        parameters: list[Any] = []
        if thread_id is not None:
            clauses.append("thread_id = ?")
            parameters.append(thread_id)
        if checkpoint_ns is not None:
            clauses.append("checkpoint_ns = ?")
            parameters.append(checkpoint_ns)
        if checkpoint_id is not None:
            clauses.append("checkpoint_id = ?")
            parameters.append(checkpoint_id)
        if before_checkpoint_id is not None:
            clauses.append("checkpoint_id < ?")
            parameters.append(before_checkpoint_id)
        if filter is not None:
            clauses.append("checkpoint_metadata_matches(metadata_json, ?) = 1")
            parameters.append(json.dumps(filter, separators=(",", ":"), sort_keys=True))
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY checkpoint_id DESC LIMIT ? OFFSET ?"
        parameters.extend((-1 if limit is None else limit, offset))

        with self._connect() as conn:
            for row in conn.execute(query, parameters):
                yield self._checkpoint_tuple(
                    conn,
                    thread_id=row[0],
                    checkpoint_ns=row[1],
                    checkpoint_id=row[2],
                    checkpoint_blob=row[3],
                    metadata_json=row[4],
                    parent_checkpoint_id=row[5],
                )

    def delete_namespace(self, thread_id: str, checkpoint_ns: str) -> CheckpointDeletionResult:
        """Atomically remove one complete namespace and its serialized writes."""

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return self._delete_scope(conn, thread_id, checkpoint_ns)

    def delete_thread(self, thread_id: str) -> None:
        """Atomically remove a complete thread and every payload owned by it."""

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._delete_scope(conn, thread_id)

    def delete_threads_with_prefix(self, thread_id_prefix: str) -> tuple[str, ...]:
        """Atomically remove every checkpoint thread owned by one workflow."""

        if not thread_id_prefix:
            raise ValueError("thread_id_prefix is required")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT DISTINCT thread_id FROM checkpoints "
                "WHERE substr(thread_id, 1, ?) = ? ORDER BY thread_id",
                (len(thread_id_prefix), thread_id_prefix),
            ).fetchall()
            thread_ids = tuple(str(row[0]) for row in rows)
            for thread_id in thread_ids:
                self._delete_scope(conn, thread_id)
        return thread_ids

    def prune(self, thread_ids: Sequence[str], *, strategy: str = "keep_latest") -> None:
        if strategy != "delete":
            raise NotImplementedError(
                "ancestor chain pruning is intentionally disabled; delete complete threads instead"
            )
        for thread_id in dict.fromkeys(thread_ids):
            self.delete_thread(thread_id)

    def enforce_thread_quota(
        self,
        max_threads: int,
        *,
        max_delete: int = 100,
    ) -> CheckpointRetentionResult:
        """Delete at most ``max_delete`` oldest complete threads beyond the quota."""

        if max_threads < 0:
            raise ValueError("max_threads must be non-negative")
        if not 1 <= max_delete <= _MAX_RETENTION_BATCH:
            raise ValueError(f"max_delete must be between 1 and {_MAX_RETENTION_BATCH}")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            total_threads = conn.execute(
                "SELECT COUNT(*) FROM (SELECT thread_id FROM checkpoints GROUP BY thread_id)"
            ).fetchone()[0]
            excess = max(total_threads - max_threads, 0)
            delete_count = min(excess, max_delete)
            if delete_count == 0:
                return CheckpointRetentionResult((), 0)
            rows = list(
                conn.execute(
                    "SELECT thread_id FROM checkpoints GROUP BY thread_id "
                    "ORDER BY MAX(updated_at_ns) ASC, thread_id ASC LIMIT ? OFFSET 0",
                    (delete_count,),
                )
            )
            thread_ids = tuple(row[0] for row in rows)
            for thread_id in thread_ids:
                self._delete_scope(conn, thread_id)
            return CheckpointRetentionResult(
                deleted_thread_ids=thread_ids,
                remaining_over_quota=max(excess - len(thread_ids), 0),
            )

    def compact_if_needed(
        self,
        *,
        min_reclaim_bytes: int = 64 * 1024 * 1024,
        min_free_ratio: float = 0.25,
    ) -> CheckpointCompactionResult:
        """Return deleted checkpoint pages to disk only after meaningful churn.

        Thread deletion deliberately preserves complete LangGraph chains, but
        SQLite keeps the released pages in its freelist. This bounded startup
        maintenance avoids running ``VACUUM`` for small databases or ordinary
        write churn while preventing a long-lived local studio from retaining
        hundreds of megabytes of deleted checkpoint payloads.
        """

        if min_reclaim_bytes < 0:
            raise ValueError("min_reclaim_bytes must be non-negative")
        if not 0 <= min_free_ratio <= 1:
            raise ValueError("min_free_ratio must be between 0 and 1")
        with self._connect() as conn:
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        reclaimable_bytes = free_pages * page_size
        free_ratio = free_pages / page_count if page_count else 0.0
        if reclaimable_bytes < min_reclaim_bytes or free_ratio < min_free_ratio:
            return CheckpointCompactionResult(
                compacted=False,
                reclaimable_bytes=reclaimable_bytes,
                reclaimed_bytes=0,
            )

        with self._connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        size_before = self.db_path.stat().st_size
        with self._connect() as conn:
            conn.execute("VACUUM")
        with self._connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        size_after = self.db_path.stat().st_size
        return CheckpointCompactionResult(
            compacted=True,
            reclaimable_bytes=reclaimable_bytes,
            reclaimed_bytes=max(size_before - size_after, 0),
        )

    def repair_orphan_writes(self, *, max_delete: int = 100) -> int:
        """Delete a bounded batch of legacy writes whose checkpoint no longer exists."""

        if not 1 <= max_delete <= _MAX_RETENTION_BATCH:
            raise ValueError(f"max_delete must be between 1 and {_MAX_RETENTION_BATCH}")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "DELETE FROM checkpoint_writes WHERE rowid IN ("
                "SELECT writes.rowid FROM checkpoint_writes AS writes "
                "LEFT JOIN checkpoints AS checkpoints "
                "ON checkpoints.thread_id = writes.thread_id "
                "AND checkpoints.checkpoint_ns = writes.checkpoint_ns "
                "AND checkpoints.checkpoint_id = writes.checkpoint_id "
                "WHERE checkpoints.checkpoint_id IS NULL LIMIT ?)",
                (max_delete,),
            )
            return max(cursor.rowcount, 0)

    def integrity_report(self) -> CheckpointIntegrityReport:
        with self._connect() as conn:
            quick_check = conn.execute("PRAGMA quick_check(1)").fetchone()[0]
            orphan_writes = conn.execute(
                "SELECT COUNT(*) FROM checkpoint_writes AS writes "
                "LEFT JOIN checkpoints AS checkpoints "
                "ON checkpoints.thread_id = writes.thread_id "
                "AND checkpoints.checkpoint_ns = writes.checkpoint_ns "
                "AND checkpoints.checkpoint_id = writes.checkpoint_id "
                "WHERE checkpoints.checkpoint_id IS NULL"
            ).fetchone()[0]
        return CheckpointIntegrityReport(
            quick_check=quick_check,
            orphan_writes=orphan_writes,
            legacy_primary_key=self._legacy_primary_key,
        )

    def _checkpoint_tuple(
        self,
        conn: sqlite3.Connection,
        *,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        checkpoint_blob: bytes,
        metadata_json: str,
        parent_checkpoint_id: str | None,
    ) -> CheckpointTuple:
        parent_config = None
        if parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_checkpoint_id,
                }
            }
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint=self._deserialize(checkpoint_blob),
            metadata=json.loads(metadata_json),
            parent_config=parent_config,
            pending_writes=self._pending_writes(
                conn,
                thread_id,
                checkpoint_ns,
                checkpoint_id,
            ),
        )

    def _pending_writes(
        self,
        conn: sqlite3.Connection,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> list[tuple[str, str, Any]]:
        rows = list(
            conn.execute(
                "SELECT task_id, channel, value_blob FROM checkpoint_writes "
                "WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ? "
                "ORDER BY task_id, write_index LIMIT ? OFFSET 0",
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    self.max_writes_per_checkpoint + 1,
                ),
            )
        )
        if len(rows) > self.max_writes_per_checkpoint:
            raise CheckpointIntegrityError("pending writes exceed the configured read quota")
        return [
            (task_id, channel, self._deserialize(value_blob))
            for task_id, channel, value_blob in rows
        ]

    def _delete_scope(
        self,
        conn: sqlite3.Connection,
        thread_id: str,
        checkpoint_ns: str | None = None,
    ) -> CheckpointDeletionResult:
        clause = "thread_id = ?"
        parameters: tuple[str, ...] = (thread_id,)
        if checkpoint_ns is not None:
            clause += " AND checkpoint_ns = ?"
            parameters = (thread_id, checkpoint_ns)
        writes_deleted = conn.execute(
            f"DELETE FROM checkpoint_writes WHERE {clause}", parameters
        ).rowcount
        checkpoints_deleted = conn.execute(
            f"DELETE FROM checkpoints WHERE {clause}", parameters
        ).rowcount
        return CheckpointDeletionResult(
            checkpoints_deleted=max(checkpoints_deleted, 0),
            writes_deleted=max(writes_deleted, 0),
        )

    def _serialize(self, value: Any) -> bytes:
        type_name, payload = self.serde.dumps_typed(value)
        type_bytes = type_name.encode("utf-8")
        payload_bytes = bytes(payload)
        if not type_bytes or len(type_bytes) > 1_024:
            raise ValueError("invalid LangGraph serializer type name")
        blob = (
            _SERIALIZATION_MAGIC + _TYPE_LENGTH.pack(len(type_bytes)) + type_bytes + payload_bytes
        )
        if len(blob) > self.max_blob_bytes:
            raise ValueError("serialized checkpoint payload exceeds max_blob_bytes")
        return blob

    def _deserialize(self, raw_blob: bytes | memoryview) -> Any:
        blob = bytes(raw_blob)
        if len(blob) > self.max_blob_bytes:
            raise CheckpointIntegrityError("persisted payload exceeds max_blob_bytes")
        if blob.startswith(_SERIALIZATION_MAGIC):
            header_end = len(_SERIALIZATION_MAGIC) + _TYPE_LENGTH.size
            if len(blob) < header_end:
                raise CheckpointIntegrityError("truncated typed checkpoint envelope")
            type_length = _TYPE_LENGTH.unpack(blob[len(_SERIALIZATION_MAGIC) : header_end])[0]
            type_end = header_end + type_length
            if type_length == 0 or type_length > 1_024 or type_end > len(blob):
                raise CheckpointIntegrityError("invalid typed checkpoint envelope")
            type_name = blob[header_end:type_end].decode("utf-8")
            return self.serde.loads_typed((type_name, blob[type_end:]))

        try:
            legacy = _PrimitiveOnlyUnpickler(io.BytesIO(blob)).load()
        except (EOFError, pickle.UnpicklingError) as exc:
            raise CheckpointIntegrityError("unsafe or invalid legacy checkpoint envelope") from exc
        if (
            not isinstance(legacy, tuple)
            or len(legacy) != 2
            or not isinstance(legacy[0], str)
            or not isinstance(legacy[1], bytes)
        ):
            raise CheckpointIntegrityError("invalid legacy checkpoint envelope")
        return self.serde.loads_typed(legacy)


def _metadata_matches(metadata_json: str, expected_json: str) -> int:
    try:
        metadata = json.loads(metadata_json)
        expected = json.loads(expected_json)
    except (TypeError, json.JSONDecodeError):
        return 0
    if not isinstance(metadata, dict) or not isinstance(expected, dict):
        return 0
    return int(all(metadata.get(key) == value for key, value in expected.items()))
