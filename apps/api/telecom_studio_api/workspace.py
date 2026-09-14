"""Persistent organization only; design artifacts and conversation journals stay authoritative."""

import sqlite3
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Annotated

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from core.contracts.identifiers import (
    DOCUMENT_PACK_ID_PATTERN,
    WORKFLOW_ID_PATTERN,
)


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()


class ChatInput(ProjectInput):
    workflow_id: str | None = Field(default=None, pattern=WORKFLOW_ID_PATTERN)
    draft_prompt: str = Field(default="", max_length=5000)


class ChatUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, Field(min_length=1, max_length=120)] | SkipJsonSchema[None] = None
    draft_prompt: Annotated[str, Field(max_length=5000)] | SkipJsonSchema[None] = None
    workflow_id: str | None = Field(default=None, pattern=WORKFLOW_ID_PATTERN)
    document_pack_id: str | None = Field(default=None, pattern=DOCUMENT_PACK_ID_PATTERN)

    @field_validator("title")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()

    @field_validator("draft_prompt")
    @classmethod
    def draft_not_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("draft must be text")
        return value


class ProjectView(ProjectInput):
    project_id: str
    created_at: str
    updated_at: str


class ChatView(ProjectView):
    chat_id: str
    draft_prompt: str
    workflow_id: str | None
    document_pack_id: str | None


class WorkspaceStore:
    def __init__(
        self,
        path: Path,
        workflow_exists: Callable[[str], object],
        pack_exists: Callable[[str], object],
    ):
        self.creation_lock = RLock()
        self.path = path
        self.workflow_exists = workflow_exists
        self.pack_exists = pack_exists
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS studio_projects (
                    project_id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS studio_chats (
                    chat_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES studio_projects(project_id)
                        ON DELETE CASCADE,
                    title TEXT NOT NULL, draft_prompt TEXT NOT NULL DEFAULT '',
                    workflow_id TEXT UNIQUE, document_pack_id TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS studio_chats_project_updated_idx
                    ON studio_chats(project_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS studio_pending_pack_links (
                    chat_id TEXT PRIMARY KEY REFERENCES studio_chats(chat_id)
                        ON DELETE RESTRICT,
                    started_at TEXT NOT NULL);
                DELETE FROM studio_pending_pack_links;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def require(self, db, table: str, key: str, value: str):
        row = db.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone()
        if row is None:
            raise HTTPException(404, "Projet ou conversation introuvable.")
        return dict(row)

    def validate_reference(self, callback, value):
        if value is None:
            return
        try:
            result = callback(value)
            if result is False or result is None:
                raise KeyError(value)
        except (KeyError, FileNotFoundError, ValueError) as exc:
            raise HTTPException(
                422, "Le design ou les pièces jointes ne sont pas disponibles."
            ) from exc

    def get_chat(self, chat_id: str) -> dict:
        with self.connection() as db:
            return self.require(db, "studio_chats", "chat_id", chat_id)

    def linked_workflow_ids(self) -> list[str]:
        with self.connection() as db:
            return [
                row["workflow_id"]
                for row in db.execute(
                    "SELECT workflow_id FROM studio_chats "
                    "WHERE workflow_id IS NOT NULL ORDER BY updated_at DESC"
                )
            ]

    def workflow_is_linked(self, workflow_id: str) -> bool:
        with self.connection() as db:
            return (
                db.execute(
                    "SELECT 1 FROM studio_chats WHERE workflow_id=? LIMIT 1",
                    (workflow_id,),
                ).fetchone()
                is not None
            )

    def attach_document_pack(self, chat_id: str, pack_id: str) -> dict:
        """Persist an ingested pack before its successful response reaches the client."""
        return self.update_chat(
            chat_id,
            ChatUpdate(document_pack_id=pack_id),
        )

    def begin_document_pack_ingest(self, chat_id: str) -> None:
        with self.creation_lock, self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require(db, "studio_chats", "chat_id", chat_id)
            try:
                db.execute(
                    "INSERT INTO studio_pending_pack_links VALUES (?,?)",
                    (chat_id, now()),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(409, "Un import de pièces jointes est déjà en cours.") from exc

    def cancel_document_pack_ingest(self, chat_id: str) -> None:
        with self.creation_lock, self.connection() as db:
            db.execute(
                "DELETE FROM studio_pending_pack_links WHERE chat_id=?",
                (chat_id,),
            )

    def complete_document_pack_ingest(self, chat_id: str, pack_id: str) -> dict:
        self.validate_reference(self.pack_exists, pack_id)
        with self.creation_lock, self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.require(db, "studio_chats", "chat_id", chat_id)
            reservation = db.execute(
                "SELECT 1 FROM studio_pending_pack_links WHERE chat_id=?",
                (chat_id,),
            ).fetchone()
            if reservation is None:
                raise HTTPException(409, "L’import des pièces jointes doit être relancé.")
            stamp = now()
            db.execute(
                "UPDATE studio_chats SET document_pack_id=?,updated_at=? WHERE chat_id=?",
                (pack_id, stamp, chat_id),
            )
            db.execute(
                "DELETE FROM studio_pending_pack_links WHERE chat_id=?",
                (chat_id,),
            )
            self.touch_project(db, current["project_id"], stamp)
            return self.require(db, "studio_chats", "chat_id", chat_id)

    @staticmethod
    def touch_project(db: sqlite3.Connection, project_id: str, stamp: str) -> None:
        db.execute(
            "UPDATE studio_projects SET updated_at=? WHERE project_id=?",
            (stamp, project_id),
        )

    def create_for_chat(
        self,
        chat_id: str,
        create: Callable[[], dict],
        *,
        document_pack_id: str | None = None,
    ) -> dict:
        """Bind a real accepted workflow before returning creation to the browser.

        A lost HTTP response can be reconciled by reading the chat. Workflow
        artifacts remain recoverable independently if the process crashes.
        """
        with self.creation_lock:
            with self.connection() as db:
                chat = self.require(db, "studio_chats", "chat_id", chat_id)
            if chat["workflow_id"]:
                raise HTTPException(409, "Cette conversation possède déjà un design.")
            self.validate_reference(self.pack_exists, document_pack_id)
            result = create()
            workflow_id = result.get("workflow_id")
            if workflow_id:
                binding = {
                    "workflow_id": workflow_id,
                    "draft_prompt": "",
                }
                if document_pack_id is not None:
                    binding["document_pack_id"] = document_pack_id
                self.update_chat(
                    chat_id,
                    ChatUpdate.model_validate(binding),
                )
            return result

    def update_chat(self, chat_id: str, patch: ChatUpdate):
        with self.creation_lock:
            return self._update_chat(chat_id, patch)

    def _update_chat(self, chat_id: str, patch: ChatUpdate):
        fields = patch.model_dump(exclude_unset=True)
        # Keep the primary resource semantics stable: an unknown chat is a 404
        # even when a supplied external reference is unavailable too.
        with self.connection() as db:
            self.require(db, "studio_chats", "chat_id", chat_id)
        if "workflow_id" in fields:
            self.validate_reference(self.workflow_exists, fields["workflow_id"])
        if "document_pack_id" in fields:
            self.validate_reference(self.pack_exists, fields["document_pack_id"])
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.require(db, "studio_chats", "chat_id", chat_id)
            if (
                "workflow_id" in fields
                and current["workflow_id"]
                and fields["workflow_id"] != current["workflow_id"]
            ):
                raise HTTPException(
                    409,
                    "Cette conversation possède déjà un design. Créez une nouvelle conversation.",
                )
            if fields:
                stamp = now()
                fields["updated_at"] = stamp
                try:
                    db.execute(
                        f"UPDATE studio_chats SET {','.join(k + '=?' for k in fields)} "
                        "WHERE chat_id=?",
                        (*fields.values(), chat_id),
                    )
                except sqlite3.IntegrityError as exc:
                    raise HTTPException(
                        409, "Ce design appartient déjà à une conversation."
                    ) from exc
                self.touch_project(db, current["project_id"], stamp)
            return self.require(db, "studio_chats", "chat_id", chat_id)


def now() -> str:
    return datetime.now(UTC).isoformat()


def create_workspace_router(store: WorkspaceStore) -> APIRouter:
    router = APIRouter(prefix="/workspace", tags=["workspace"])

    @router.get("/projects", response_model=list[ProjectView])
    def projects():
        with store.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM studio_projects ORDER BY updated_at DESC, project_id"
                )
            ]

    @router.post("/projects", response_model=ProjectView, status_code=201)
    def create_project(payload: ProjectInput):
        identity, stamp = "project_" + uuid.uuid4().hex, now()
        with store.connection() as db:
            db.execute(
                "INSERT INTO studio_projects VALUES (?,?,?,?)",
                (identity, payload.title, stamp, stamp),
            )
            return store.require(db, "studio_projects", "project_id", identity)

    @router.get("/linked-workflow-ids", response_model=list[str])
    def linked_workflow_ids():
        return store.linked_workflow_ids()

    @router.patch("/projects/{project_id}", response_model=ProjectView)
    def rename_project(project_id: str, payload: ProjectInput):
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            store.require(db, "studio_projects", "project_id", project_id)
            db.execute(
                "UPDATE studio_projects SET title=?,updated_at=? WHERE project_id=?",
                (payload.title, now(), project_id),
            )
            return store.require(db, "studio_projects", "project_id", project_id)

    @router.delete("/projects/{project_id}", status_code=204)
    def delete_project(project_id: str):
        try:
            with store.creation_lock, store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                store.require(db, "studio_projects", "project_id", project_id)
                db.execute("DELETE FROM studio_projects WHERE project_id=?", (project_id,))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Attendez la fin de l’import des pièces jointes.") from exc
        return Response(status_code=204)

    @router.get("/projects/{project_id}/chats", response_model=list[ChatView])
    def chats(project_id: str):
        with store.connection() as db:
            store.require(db, "studio_projects", "project_id", project_id)
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM studio_chats WHERE project_id=? "
                    "ORDER BY updated_at DESC,chat_id",
                    (project_id,),
                )
            ]

    @router.post("/projects/{project_id}/chats", response_model=ChatView, status_code=201)
    def create_chat(project_id: str, payload: ChatInput):
        with store.creation_lock:
            store.validate_reference(store.workflow_exists, payload.workflow_id)
            identity, stamp = "chat_" + uuid.uuid4().hex, now()
            with store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                store.require(db, "studio_projects", "project_id", project_id)
                try:
                    db.execute(
                        "INSERT INTO studio_chats VALUES (?,?,?,?,?,NULL,?,?)",
                        (
                            identity,
                            project_id,
                            payload.title,
                            payload.draft_prompt,
                            payload.workflow_id,
                            stamp,
                            stamp,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise HTTPException(
                        409, "Ce design appartient déjà à une conversation."
                    ) from exc
                store.touch_project(db, project_id, stamp)
                return store.require(db, "studio_chats", "chat_id", identity)

    @router.get("/chats/{chat_id}", response_model=ChatView)
    def chat(chat_id: str):
        with store.connection() as db:
            return store.require(db, "studio_chats", "chat_id", chat_id)

    @router.patch("/chats/{chat_id}", response_model=ChatView)
    def update_chat(chat_id: str, payload: ChatUpdate):
        return store.update_chat(chat_id, payload)

    @router.delete("/chats/{chat_id}", status_code=204)
    def delete_chat(chat_id: str):
        try:
            with store.creation_lock, store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                current = store.require(db, "studio_chats", "chat_id", chat_id)
                db.execute("DELETE FROM studio_chats WHERE chat_id=?", (chat_id,))
                store.touch_project(db, current["project_id"], now())
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Attendez la fin de l’import des pièces jointes.") from exc
        return Response(status_code=204)

    return router
