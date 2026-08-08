from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


def _load_snapshot_module():
    script = Path(__file__).resolve().parents[2] / "infra" / "docker" / "sqlite_snapshot.py"
    spec = importlib.util.spec_from_file_location("sqlite_snapshot", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snapshot = _load_snapshot_module()


def _create_database(path: Path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE proof (value TEXT NOT NULL)")
        connection.execute("INSERT INTO proof(value) VALUES (?)", (value,))


def _snapshot_value(path: Path) -> str:
    with sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True) as connection:
        row = connection.execute("SELECT value FROM proof").fetchone()
    assert row is not None
    return str(row[0])


def test_publish_once_creates_consistent_read_only_snapshots(tmp_path: Path) -> None:
    source = tmp_path / "source"
    preview = tmp_path / "preview"
    source.mkdir()
    _create_database(source / "telecom_studio.db", "memory")
    _create_database(source / "checkpoints.db", "checkpoint")
    stale_sidecar = preview / ".telecom_studio.db.abandoned.tmp-shm"
    preview.mkdir()
    stale_sidecar.write_bytes(b"stale")

    assert snapshot.publish_once(source, preview) is True
    assert _snapshot_value(preview / "telecom_studio.db") == "memory"
    assert _snapshot_value(preview / "checkpoints.db") == "checkpoint"
    assert snapshot.check_snapshot(preview, max_age_s=30) == 0
    assert (preview / "telecom_studio.db").stat().st_mode & 0o222 == 0
    assert not stale_sidecar.exists()
    assert not list(preview.glob(".*.tmp*"))

    status = json.loads((preview / "snapshot_status.json").read_text(encoding="utf-8"))
    assert status["complete"] is True
    assert status["errors"] == []
    assert {item["database"] for item in status["snapshots"]} == {
        "telecom_studio.db",
        "checkpoints.db",
    }


def test_failed_refresh_preserves_last_good_snapshot_and_degrades_health(tmp_path: Path) -> None:
    source = tmp_path / "source"
    preview = tmp_path / "preview"
    source.mkdir()
    _create_database(source / "telecom_studio.db", "last-good")
    _create_database(source / "checkpoints.db", "checkpoint")
    assert snapshot.publish_once(source, preview) is True

    (source / "telecom_studio.db").write_bytes(b"not a sqlite database")

    assert snapshot.publish_once(source, preview) is False
    assert _snapshot_value(preview / "telecom_studio.db") == "last-good"
    assert snapshot.check_snapshot(preview, max_age_s=30) == 1
    status = json.loads((preview / "snapshot_status.json").read_text(encoding="utf-8"))
    assert status["complete"] is False
    assert status["last_success_at"]
    assert any("telecom_studio.db" in error for error in status["errors"])
