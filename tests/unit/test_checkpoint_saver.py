import os
import pickle
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from langgraph.checkpoint.base import Checkpoint

from core.services.checkpoint_saver import (
    CheckpointIntegrityError,
    SqliteCheckpointSaver,
)


def _checkpoint(checkpoint_id: str, *, value: object | None = None) -> Checkpoint:
    return {
        "v": 1,
        "id": checkpoint_id,
        "ts": "2024-01-01T00:00:00Z",
        "channel_values": {} if value is None else {"value": value},
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": None,
    }


def _config(thread_id: str, namespace: str = "") -> dict:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": namespace}}


def test_checkpoint_saver_put_and_get(tmp_path: Path) -> None:
    saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db")
    config = _config("wf_test")

    saved_config = saver.put(config, _checkpoint("chk_1", value="value"), {"step": 1}, {})
    result = saver.get_tuple(config)

    assert result is not None
    assert result.config == saved_config
    assert result.checkpoint["id"] == "chk_1"
    assert result.checkpoint["channel_values"] == {"value": "value"}


def test_checkpoint_saver_list_applies_filter_limit_and_offset_in_sql(tmp_path: Path) -> None:
    saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db")
    config = _config("wf_filters", "initial")
    for index, stage in enumerate(("target", "skip", "target", "target"), start=1):
        saver.put(config, _checkpoint(f"chk_{index}"), {"stage": stage}, {})

    results = list(saver.list(config, filter={"stage": "target"}, limit=1, offset=1))
    before = list(
        saver.list(
            config,
            before={"configurable": {**config["configurable"], "checkpoint_id": "chk_3"}},
            limit=1,
        )
    )

    assert [item.checkpoint["id"] for item in results] == ["chk_3"]
    assert [item.checkpoint["id"] for item in before] == ["chk_2"]
    with pytest.raises(ValueError, match="limit"):
        list(saver.list(config, limit=-1))
    with pytest.raises(ValueError, match="offset"):
        list(saver.list(config, offset=-1))


def test_checkpoint_saver_isolates_namespaces(tmp_path: Path) -> None:
    saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db")
    saver.put(_config("wf_ns", "initial"), _checkpoint("chk_1"), {"stage": "initial"}, {})
    saver.put(_config("wf_ns", "revision"), _checkpoint("chk_2"), {"stage": "revision"}, {})

    initial = list(saver.list(_config("wf_ns", "initial")))
    revision = list(saver.list(_config("wf_ns", "revision")))

    assert [item.checkpoint["id"] for item in initial] == ["chk_1"]
    assert [item.checkpoint["id"] for item in revision] == ["chk_2"]


def test_checkpoint_saver_persists_pending_writes(tmp_path: Path) -> None:
    saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db")
    saved_config = saver.put(
        _config("wf_writes", "revision-v1"),
        _checkpoint("chk_writes"),
        {"step": 1},
        {},
    )
    saver.put_writes(
        saved_config,
        [("result", {"status": "running"}), ("__error__", "first")],
        "task-1",
    )
    saver.put_writes(saved_config, [("__error__", "latest")], "task-1")

    result = saver.get_tuple(saved_config)

    assert result is not None
    assert result.pending_writes is not None
    assert ("task-1", "result", {"status": "running"}) in result.pending_writes
    assert ("task-1", "__error__", "latest") in result.pending_writes
    assert ("task-1", "__error__", "first") not in result.pending_writes


def test_pending_writes_can_precede_owner_and_respect_quota(tmp_path: Path) -> None:
    saver = SqliteCheckpointSaver(
        tmp_path / "checkpoints.db",
        max_writes_per_checkpoint=2,
    )
    missing = {
        "configurable": {
            "thread_id": "wf_missing",
            "checkpoint_ns": "",
            "checkpoint_id": "missing",
        }
    }
    saver.put_writes(missing, [("value", 1)], "task")
    assert saver.integrity_report().orphan_writes == 1
    saver.put(_config("wf_missing"), _checkpoint("missing"), {}, {})
    attached = saver.get_tuple(missing)
    assert attached is not None
    assert attached.pending_writes == [("task", "value", 1)]
    assert saver.integrity_report().ok

    saved = saver.put(_config("wf_quota"), _checkpoint("chk_quota"), {}, {})
    saver.put_writes(saved, [("one", 1), ("two", 2)], "task")
    with pytest.raises(ValueError, match="quota"):
        saver.put_writes(saved, [("three", 3)], "another-task")

    result = saver.get_tuple(saved)
    assert result is not None
    assert len(result.pending_writes or ()) == 2


def test_delete_namespace_and_thread_remove_owned_payloads(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    saver = SqliteCheckpointSaver(db)
    first = saver.put(_config("wf_delete", "initial"), _checkpoint("chk_1"), {}, {})
    second = saver.put(_config("wf_delete", "revision"), _checkpoint("chk_2"), {}, {})
    other = saver.put(_config("wf_keep", "initial"), _checkpoint("chk_3"), {}, {})
    for config in (first, second, other):
        saver.put_writes(config, [("value", config["configurable"]["checkpoint_id"])], "task")

    deleted = saver.delete_namespace("wf_delete", "initial")
    saver.delete_thread("wf_delete")

    assert deleted.checkpoints_deleted == 1
    assert deleted.writes_deleted == 1
    assert saver.get_tuple(_config("wf_delete", "initial")) is None
    assert saver.get_tuple(_config("wf_delete", "revision")) is None
    assert saver.get_tuple(_config("wf_keep", "initial")) is not None
    with sqlite3.connect(db) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM checkpoint_writes WHERE thread_id = 'wf_delete'"
            ).fetchone()[0]
            == 0
        )
    assert saver.integrity_report().ok


def test_thread_quota_deletes_bounded_oldest_complete_threads(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    saver = SqliteCheckpointSaver(db)
    for index in range(5):
        saved = saver.put(_config(f"wf_{index}"), _checkpoint(f"chk_{index}"), {}, {})
        saver.put_writes(saved, [("value", index)], "task")
    with sqlite3.connect(db) as conn:
        for index in range(5):
            conn.execute(
                "UPDATE checkpoints SET updated_at_ns = ? WHERE thread_id = ?",
                (index, f"wf_{index}"),
            )

    first = saver.enforce_thread_quota(2, max_delete=2)
    second = saver.enforce_thread_quota(2, max_delete=2)

    assert first.deleted_thread_ids == ("wf_0", "wf_1")
    assert first.remaining_over_quota == 1
    assert second.deleted_thread_ids == ("wf_2",)
    assert second.remaining_over_quota == 0
    assert {item.config["configurable"]["thread_id"] for item in saver.list(None)} == {
        "wf_3",
        "wf_4",
    }
    assert saver.integrity_report().ok


def test_compaction_reclaims_deleted_checkpoint_pages(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    saver = SqliteCheckpointSaver(db)
    payload = "x" * 200_000
    for index in range(12):
        saver.put(
            _config("wf_compact"),
            _checkpoint(f"chk_{index:03d}", value=f"{payload}{index}"),
            {},
            {},
        )
    size_before_delete = sum(
        path.stat().st_size for path in (db, db.with_name(f"{db.name}-wal")) if path.exists()
    )

    saver.delete_thread("wf_compact")
    result = saver.compact_if_needed(min_reclaim_bytes=1, min_free_ratio=0)

    assert result.compacted is True
    assert result.reclaimable_bytes > 0
    assert result.reclaimed_bytes > 0
    assert db.stat().st_size < size_before_delete
    assert saver.integrity_report().ok


def test_compaction_skips_small_freelist_and_validates_thresholds(tmp_path: Path) -> None:
    saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db")

    result = saver.compact_if_needed(min_reclaim_bytes=1)

    assert result.compacted is False
    assert result.reclaimed_bytes == 0
    with pytest.raises(ValueError, match="min_reclaim_bytes"):
        saver.compact_if_needed(min_reclaim_bytes=-1)
    with pytest.raises(ValueError, match="min_free_ratio"):
        saver.compact_if_needed(min_free_ratio=1.1)


def test_orphan_repair_is_bounded(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    saver = SqliteCheckpointSaver(db)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        for index in range(3):
            conn.execute(
                "INSERT INTO checkpoint_writes "
                "(thread_id, checkpoint_ns, checkpoint_id, task_id, write_index, "
                "channel, value_blob, task_path) VALUES (?, '', ?, 'task', 0, 'value', ?, '')",
                (f"missing_{index}", f"chk_{index}", b"invalid"),
            )

    assert saver.integrity_report().orphan_writes == 3
    assert saver.repair_orphan_writes(max_delete=2) == 2
    assert saver.integrity_report().orphan_writes == 1
    assert saver.repair_orphan_writes(max_delete=2) == 1
    assert saver.integrity_report().ok


def test_new_envelope_is_non_pickle_and_legacy_primitive_envelope_is_readable(
    tmp_path: Path,
) -> None:
    db = tmp_path / "checkpoints.db"
    saver = SqliteCheckpointSaver(db)
    saved = saver.put(_config("wf_safe"), _checkpoint("chk_safe"), {}, {})
    with sqlite3.connect(db) as conn:
        new_blob = conn.execute(
            "SELECT checkpoint_json FROM checkpoints WHERE thread_id = 'wf_safe'"
        ).fetchone()[0]
    assert bytes(new_blob).startswith(b"TSCP\x01")

    legacy_checkpoint = _checkpoint("chk_legacy", value={"typed": True})
    legacy_blob = pickle.dumps(saver.serde.dumps_typed(legacy_checkpoint))
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, checkpoint_json, metadata_json) "
            "VALUES ('wf_legacy', '', 'chk_legacy', ?, '{}')",
            (legacy_blob,),
        )
    result = saver.get_tuple(
        {
            "configurable": {
                **saved["configurable"],
                "thread_id": "wf_legacy",
                "checkpoint_id": "chk_legacy",
            }
        }
    )
    assert result is not None
    assert result.checkpoint["channel_values"] == {"value": {"typed": True}}


def test_legacy_pickle_cannot_resolve_globals(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    saver = SqliteCheckpointSaver(db)
    malicious_blob = pickle.dumps(os.system)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, checkpoint_json, metadata_json) "
            "VALUES ('wf_unsafe', '', 'chk_unsafe', ?, '{}')",
            (malicious_blob,),
        )

    with pytest.raises(CheckpointIntegrityError, match="unsafe or invalid"):
        saver.get_tuple(
            {
                "configurable": {
                    "thread_id": "wf_unsafe",
                    "checkpoint_ns": "",
                    "checkpoint_id": "chk_unsafe",
                }
            }
        )


def test_legacy_schema_is_extended_without_rewriting_payloads(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    serializer_owner = SqliteCheckpointSaver(tmp_path / "serializer.db")
    legacy_blob = pickle.dumps(serializer_owner.serde.dumps_typed(_checkpoint("chk_legacy")))
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE checkpoints ("
            "thread_id TEXT NOT NULL, checkpoint_id TEXT NOT NULL, "
            "checkpoint_json TEXT NOT NULL, metadata_json TEXT NOT NULL, "
            "parent_checkpoint_id TEXT, PRIMARY KEY (thread_id, checkpoint_id))"
        )
        conn.execute(
            "INSERT INTO checkpoints VALUES ('wf_legacy', 'chk_legacy', ?, '{}', NULL)",
            (legacy_blob,),
        )

    saver = SqliteCheckpointSaver(db)
    result = saver.get_tuple(
        {
            "configurable": {
                "thread_id": "wf_legacy",
                "checkpoint_ns": "",
                "checkpoint_id": "chk_legacy",
            }
        }
    )

    assert result is not None
    assert result.checkpoint["id"] == "chk_legacy"
    assert saver.integrity_report().legacy_primary_key is True
    with sqlite3.connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(checkpoints)")}
    assert {"checkpoint_ns", "created_at_ns", "updated_at_ns"} <= columns


def test_payload_size_is_bounded(tmp_path: Path) -> None:
    saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db", max_blob_bytes=256)

    with pytest.raises(ValueError, match="max_blob_bytes"):
        saver.put(_config("wf_large"), _checkpoint("chk_large", value="x" * 1_000), {}, {})


def test_concurrent_writers_preserve_sqlite_integrity(tmp_path: Path) -> None:
    saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db")

    def persist(index: int) -> None:
        saved = saver.put(
            _config("wf_concurrent", "initial"),
            _checkpoint(f"chk_{index:03d}", value=index),
            {"index": index},
            {},
        )
        saver.put_writes(saved, [("result", {"index": index})], f"task-{index}")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(persist, range(32)))

    results = list(saver.list(_config("wf_concurrent", "initial"), limit=32))
    assert len(results) == 32
    assert all(len(item.pending_writes or ()) == 1 for item in results)
    assert saver.integrity_report().ok


def test_mid_chain_pruning_is_explicitly_refused(tmp_path: Path) -> None:
    saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db")

    with pytest.raises(NotImplementedError, match="ancestor chain"):
        saver.prune(["wf_test"])
