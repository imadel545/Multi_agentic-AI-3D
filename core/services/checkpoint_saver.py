import json
import pickle
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    RunnableConfig,
)


class SqliteCheckpointSaver(BaseCheckpointSaver):
    """Minimal persistent checkpoint saver using SQLite."""

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    PRIMARY KEY (thread_id, checkpoint_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_checkpoints_thread
                ON checkpoints (thread_id, checkpoint_id)
                """
            )
            conn.commit()

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")
        with sqlite3.connect(str(self.db_path)) as conn:
            if checkpoint_id:
                row = conn.execute(
                    "SELECT checkpoint_json, metadata_json, parent_checkpoint_id "
                    "FROM checkpoints WHERE thread_id = ? AND checkpoint_id = ?",
                    (thread_id, checkpoint_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT checkpoint_json, metadata_json, parent_checkpoint_id "
                    "FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id DESC LIMIT 1",
                    (thread_id,),
                ).fetchone()
            if not row:
                return None
            checkpoint = self.serde.loads_typed(pickle.loads(row[0]))
            metadata = json.loads(row[1])
            parent_config = None
            if row[2]:
                parent_config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": row[2],
                    }
                }
            return CheckpointTuple(
                config=config,
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Any,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        checkpoint_bytes = pickle.dumps(self.serde.dumps_typed(checkpoint))
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO checkpoints "
                "(thread_id, checkpoint_id, checkpoint_json, metadata_json, "
                "parent_checkpoint_id) VALUES (?, ?, ?, ?, ?)",
                (
                    thread_id,
                    checkpoint_id,
                    checkpoint_bytes,
                    json.dumps(metadata),
                    parent_checkpoint_id,
                ),
            )
            conn.commit()
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        pass

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"] if config else None
        with sqlite3.connect(str(self.db_path)) as conn:
            if thread_id:
                rows = conn.execute(
                    "SELECT thread_id, checkpoint_id, checkpoint_json, "
                    "metadata_json, parent_checkpoint_id "
                    "FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id",
                    (thread_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT thread_id, checkpoint_id, checkpoint_json, metadata_json, "
                    "parent_checkpoint_id FROM checkpoints ORDER BY checkpoint_id"
                ).fetchall()
            for row in rows:
                checkpoint = self.serde.loads_typed(pickle.loads(row[2]))
                metadata = json.loads(row[3])
                c_config = {
                    "configurable": {
                        "thread_id": row[0],
                        "checkpoint_id": row[1],
                    }
                }
                parent_config = None
                if row[4]:
                    parent_config = {
                        "configurable": {
                            "thread_id": row[0],
                            "checkpoint_id": row[4],
                        }
                    }
                yield CheckpointTuple(
                    config=c_config,
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=parent_config,
                )
