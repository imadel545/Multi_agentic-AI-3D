"""Canonical memory admission policy; migrations never infer historical origin."""

from __future__ import annotations

import sqlite3

from core.contracts.memory import MemoryOrigin

MEMORY_TABLES = (
    "workflow_memory",
    "design_memory",
    "error_memory",
    "document_pack_memory",
    "document_pack_issue_memory",
)
PROVENANCE_POLICY_VERSION = 1


class MemoryOriginConflict(ValueError):
    """An existing identity cannot be reassigned by normal writeback."""


def migrate_provenance(conn: sqlite3.Connection) -> None:
    """Idempotently preserve legacy rows, keeping them outside product recall."""
    for table in MEMORY_TABLES:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "origin" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN origin TEXT NOT NULL DEFAULT 'UNKNOWN' "
                "CHECK (origin IN ('PRODUCT','TEST','EVALUATION','IMPORT','MIGRATION','UNKNOWN'))"
            )
        if "recall_eligible" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN recall_eligible INTEGER NOT NULL DEFAULT 0 "
                "CHECK (recall_eligible IN (0, 1))"
            )


def ensure_origin_ownership(
    conn: sqlite3.Connection,
    tables: tuple[str, ...],
    key: str,
    value: str,
    origin: MemoryOrigin,
) -> None:
    """A write cannot silently relabel existing product, test or legacy records."""
    for table in tables:
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE {key} = ? AND origin != ? LIMIT 1",
            (value, origin.value),
        ).fetchone()
        if row is not None:
            raise MemoryOriginConflict("memory identity already belongs to another origin")


def provenance_snapshot(conn: sqlite3.Connection) -> dict:
    # IDs participate: swapping eligibility between equal-time rows must invalidate
    # the projection even if row counts, timestamps and revision did not change.
    return {
        "policy_version": PROVENANCE_POLICY_VERSION,
        "rows": {
            table: [
                tuple(row)
                for row in conn.execute(
                    f"SELECT rowid, origin, recall_eligible FROM {table} ORDER BY rowid"
                )
            ]
            for table in MEMORY_TABLES
        },
    }
