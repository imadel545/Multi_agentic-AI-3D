from pathlib import Path

from langgraph.checkpoint.base import Checkpoint

from core.services.checkpoint_saver import SqliteCheckpointSaver


def test_checkpoint_saver_put_and_get(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    saver = SqliteCheckpointSaver(db)
    config = {"configurable": {"thread_id": "wf_test"}}
    checkpoint: Checkpoint = {
        "v": 1,
        "id": "chk_1",
        "ts": "2024-01-01T00:00:00Z",
        "channel_values": {"key": "value"},
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": None,
    }
    saver.put(config, checkpoint, {"step": 1}, {})
    result = saver.get_tuple(config)
    assert result is not None
    assert result.checkpoint["id"] == "chk_1"


def test_checkpoint_saver_list(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    saver = SqliteCheckpointSaver(db)
    config = {"configurable": {"thread_id": "wf_test"}}
    for i in range(3):
        chk: Checkpoint = {
            "v": 1,
            "id": f"chk_{i}",
            "ts": f"2024-01-0{i + 1}T00:00:00Z",
            "channel_values": {},
            "channel_versions": {},
            "versions_seen": {},
            "updated_channels": None,
        }
        saver.put(config, chk, {"step": i}, {})
    results = list(saver.list(config))
    assert len(results) == 3
