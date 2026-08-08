#!/usr/bin/env python3
"""Publish consistent, read-only SQLite snapshots for Adminer."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

DATABASE_NAMES = ("telecom_studio.db", "checkpoints.db")
STATUS_NAME = "snapshot_status.json"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.chmod(0o444)
    os.replace(temporary, path)


def _integrity_check(path: Path) -> None:
    uri = f"file:{path}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True, timeout=10) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError(f"integrity_check failed for {path.name}: {result!r}")


def _cleanup_abandoned_temporary_files(target_dir: Path) -> None:
    for path in target_dir.glob(".*.tmp*"):
        if path.is_file():
            path.unlink(missing_ok=True)


def _backup_database(source: Path, target: Path) -> dict[str, object]:
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        source_uri = f"{source.resolve().as_uri()}?mode=rw"
        with sqlite3.connect(source_uri, uri=True, timeout=30) as source_connection:
            source_connection.execute("PRAGMA query_only = ON")
            source_connection.execute("PRAGMA busy_timeout = 30000")
            with sqlite3.connect(temporary, timeout=30) as target_connection:
                source_connection.backup(target_connection, pages=256, sleep=0.05)
                journal_mode = target_connection.execute("PRAGMA journal_mode=DELETE").fetchone()
                if not journal_mode or str(journal_mode[0]).lower() != "delete":
                    raise RuntimeError("snapshot journal mode could not be normalized")
        _integrity_check(temporary)
        temporary.chmod(0o444)
        os.replace(temporary, target)
    finally:
        for suffix in ("", "-journal", "-shm", "-wal"):
            temporary.with_name(f"{temporary.name}{suffix}").unlink(missing_ok=True)
    return {
        "database": source.name,
        "source_size_bytes": source.stat().st_size,
        "snapshot_size_bytes": target.stat().st_size,
    }


def publish_once(source_dir: Path, target_dir: Path) -> bool:
    target_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_abandoned_temporary_files(target_dir)
    previous_status = _read_status(target_dir / STATUS_NAME)
    snapshots: list[dict[str, object]] = []
    errors: list[str] = []
    for name in DATABASE_NAMES:
        source = source_dir / name
        if not source.is_file():
            errors.append(f"{name}: source database is not available yet")
            continue
        try:
            snapshots.append(_backup_database(source, target_dir / name))
        except (OSError, sqlite3.Error, RuntimeError) as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    complete = len(snapshots) == len(DATABASE_NAMES) and not errors
    status: dict[str, object] = {
        "schema_version": "1.0.0",
        "attempted_at": _utc_now(),
        "complete": complete,
        "snapshots": snapshots,
        "errors": errors,
        "last_success_at": (_utc_now() if complete else previous_status.get("last_success_at")),
    }
    _atomic_json(target_dir / STATUS_NAME, status)
    return complete


def _read_status(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def check_snapshot(target_dir: Path, max_age_s: float) -> int:
    status_path = target_dir / STATUS_NAME
    status = _read_status(status_path)
    if status.get("complete") is not True:
        return 1
    last_success = status.get("last_success_at")
    if not isinstance(last_success, str):
        return 1
    try:
        age_s = (datetime.now(UTC) - datetime.fromisoformat(last_success)).total_seconds()
    except ValueError:
        return 1
    if age_s < 0 or age_s > max_age_s:
        return 1
    try:
        for name in DATABASE_NAMES:
            path = target_dir / name
            if not path.is_file():
                return 1
            _integrity_check(path)
    except (OSError, sqlite3.Error, RuntimeError):
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source_dir = Path(os.getenv("SQLITE_SNAPSHOT_SOURCE_DIR", "/source"))
    target_dir = Path(os.getenv("SQLITE_SNAPSHOT_TARGET_DIR", "/preview"))
    interval_s = max(1.0, float(os.getenv("SQLITE_SNAPSHOT_INTERVAL_S", "5")))
    max_age_s = max(interval_s * 2, float(os.getenv("SQLITE_SNAPSHOT_MAX_AGE_S", "30")))
    if args.check:
        return check_snapshot(target_dir, max_age_s)

    while True:
        complete = publish_once(source_dir, target_dir)
        stream = sys.stdout if complete else sys.stderr
        print(
            f"{_utc_now()} sqlite snapshot {'published' if complete else 'degraded'}",
            file=stream,
            flush=True,
        )
        time.sleep(interval_s)


if __name__ == "__main__":
    raise SystemExit(main())
