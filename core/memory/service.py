from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from core.contracts.document_pack import (
    DocumentPackQAReport,
    DocumentPackSummary,
    ProjectDesignSpec,
)
from core.contracts.memory import MemoryIndexResult, MemoryRecallResult, MemorySummary
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport
from core.rag.models import RagDocument

if TYPE_CHECKING:
    from core.rag import RagService
    from core.services.blender_runner import GenerationResult

HIGH_QA_THRESHOLD = 0.95
MAX_MEMORY_ISSUES_PER_WORKFLOW = 32
MAX_OUTBOX_ERROR_LENGTH = 512
OUTBOX_OPERATION_KEY = "runtime_memory_projection"
OUTBOX_COLLECTION_TARGET = "design_memory,error_memory,document_pack_memory"
OUTBOX_PENDING_STATES = ("pending", "attempt", "failed")

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(
        self,
        db_path: Path,
        rag_service: RagService | None = None,
        *,
        auto_reconcile: bool = True,
        reconcile_retry_initial_s: float = 1.0,
        reconcile_retry_max_s: float = 30.0,
    ) -> None:
        if reconcile_retry_initial_s <= 0:
            raise ValueError("reconcile_retry_initial_s must be positive")
        if reconcile_retry_max_s < reconcile_retry_initial_s:
            raise ValueError(
                "reconcile_retry_max_s must be greater than or equal to the initial delay"
            )
        self.db_path = db_path
        self.rag_service = rag_service
        self._auto_reconcile = auto_reconcile
        self._reconcile_retry_initial_s = reconcile_retry_initial_s
        self._reconcile_retry_max_s = reconcile_retry_max_s
        self._last_index_result = threading.local()
        self._index_result_lock = threading.Lock()
        self._write_lock = threading.RLock()
        self._reconcile_lock = threading.Lock()
        self._reconcile_thread_lock = threading.Lock()
        self._reconcile_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._latest_index_result = MemoryIndexResult(status="not_indexed")
        self.last_index_result = MemoryIndexResult(status="not_indexed")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._recover_interrupted_outbox_attempts()
        self._restore_outbox_index_result()
        self._schedule_reconciliation()

    @property
    def last_index_result(self) -> MemoryIndexResult:
        return getattr(
            self._last_index_result,
            "value",
            MemoryIndexResult(status="not_indexed"),
        )

    @last_index_result.setter
    def last_index_result(self, value: MemoryIndexResult) -> None:
        self._last_index_result.value = value
        with self._index_result_lock:
            self._latest_index_result = value

    def index_health(self) -> dict:
        with self._index_result_lock:
            latest = self._latest_index_result.model_copy(deep=True)
        outbox = self.vector_outbox_status()
        compatibility = None
        if self.rag_service is not None:
            try:
                stats = self.stats()
                compatibility = self.rag_service.runtime_collection_compatibility(
                    source_fingerprint=self._vector_source_fingerprint(),
                    source_has_data=bool(
                        stats["design_memory_count"]
                        or stats["error_memory_count"]
                        or stats["document_pack_memory_count"]
                    ),
                )
            except Exception as exc:
                compatibility = {
                    "status": "unavailable",
                    "degraded": True,
                    "error_code": type(exc).__name__,
                }
        return {
            "latest_index_result": latest.model_dump(),
            "vector_compatibility": compatibility,
            "vector_outbox": outbox,
        }

    def recall(self, requirements: RequirementSpec, limit: int = 5) -> MemoryRecallResult:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workflow_id, network_type, tower_type, sector_count, generation_mode,
                       qa_score, warnings_json, scene_spec_path, validation_report_path,
                       reusable_pattern, created_at
                FROM workflow_memory
                WHERE network_type = ?
                  AND tower_type = ?
                  AND sector_count = ?
                  AND qa_score >= ?
                  AND reusable_pattern = 1
                ORDER BY qa_score DESC, created_at DESC
                LIMIT ?
                """,
                (
                    requirements.network_type,
                    requirements.tower_type,
                    requirements.sector_count,
                    HIGH_QA_THRESHOLD,
                    limit,
                ),
            ).fetchall()
            errors = conn.execute(
                """
                SELECT workflow_id, network_type, tower_type, issue_code, message, severity,
                       created_at
                FROM error_memory
                WHERE network_type = ? OR tower_type = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (requirements.network_type, requirements.tower_type, limit),
            ).fetchall()
        similar = [_decode_workflow_row(row) for row in rows]
        error_patterns = [dict(row) for row in errors]
        memory_context_count = len(similar) + len(error_patterns)
        return MemoryRecallResult(
            similar_workflows=similar,
            reusable_patterns=[row for row in similar if row.get("reusable_pattern")],
            error_patterns=error_patterns,
            memory_hits=memory_context_count,
            memory_context_count=memory_context_count,
        )

    def write_workflow_summary(
        self,
        workflow_id: str,
        requirements: RequirementSpec | None,
        scene: SceneSpec | None,
        report: ValidationReport,
        generation: GenerationResult | None,
        scene_spec_path: Path,
        validation_report_path: Path,
    ) -> MemorySummary | None:
        with self._write_lock:
            return self._write_workflow_summary(
                workflow_id=workflow_id,
                requirements=requirements,
                scene=scene,
                report=report,
                generation=generation,
                scene_spec_path=scene_spec_path,
                validation_report_path=validation_report_path,
            )

    def _write_workflow_summary(
        self,
        workflow_id: str,
        requirements: RequirementSpec | None,
        scene: SceneSpec | None,
        report: ValidationReport,
        generation: GenerationResult | None,
        scene_spec_path: Path,
        validation_report_path: Path,
    ) -> MemorySummary | None:
        if requirements is None:
            self.last_index_result = MemoryIndexResult(
                status="skipped", errors=["requirements_missing"]
            )
            return None
        generation_mode = generation.mode if generation else "not_run"
        qa_score = report.score
        reusable_pattern = _is_reusable_workflow(report, generation)
        created_at = int(time.time())
        issues = _unique_issues([*report.warnings, *report.errors])
        warnings = [warning.model_dump() for warning in _unique_issues(report.warnings)]
        portable_scene_path = scene_spec_path.name
        portable_validation_path = validation_report_path.name
        summary = MemorySummary(
            workflow_id=workflow_id,
            network_type=requirements.network_type,
            tower_type=requirements.tower_type,
            sector_count=requirements.sector_count,
            generation_mode=generation_mode,
            qa_score=qa_score,
            warnings=warnings,
            scene_spec_path=portable_scene_path,
            validation_report_path=portable_validation_path,
            reusable_pattern=reusable_pattern,
            created_at=created_at,
        )
        with self._connect() as conn:
            conn.execute("DELETE FROM error_memory WHERE workflow_id = ?", (workflow_id,))
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_memory (
                    workflow_id, network_type, tower_type, sector_count, generation_mode,
                    qa_score, warnings_json, scene_spec_path, validation_report_path,
                    reusable_pattern, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.workflow_id,
                    summary.network_type,
                    summary.tower_type,
                    summary.sector_count,
                    summary.generation_mode,
                    summary.qa_score,
                    json.dumps(summary.warnings),
                    summary.scene_spec_path,
                    summary.validation_report_path,
                    int(reusable_pattern),
                    created_at,
                ),
            )
            if scene is not None and reusable_pattern:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO design_memory (
                        workflow_id, scene_id, network_type, tower_type, scene_spec_json,
                        validation_report_json, qa_score, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workflow_id,
                        scene.scene_id,
                        scene.network_type,
                        requirements.tower_type,
                        scene.model_dump_json(),
                        report.model_dump_json(),
                        qa_score,
                        created_at,
                    ),
                )
            else:
                conn.execute("DELETE FROM design_memory WHERE workflow_id = ?", (workflow_id,))
            for issue in issues:
                _insert_issue_memory(
                    conn=conn,
                    workflow_id=workflow_id,
                    network_type=requirements.network_type,
                    tower_type=requirements.tower_type,
                    issue=issue,
                    created_at=created_at,
                )
            _bump_vector_revision(conn)
            outbox_enqueued = self._enqueue_vector_projection(conn, created_at=created_at)
        if outbox_enqueued:
            self.last_index_result = MemoryIndexResult(status="pending")
            self._schedule_reconciliation()
        else:
            self.last_index_result = MemoryIndexResult(
                status="skipped", errors=["rag_service_not_configured"]
            )
        return summary

    def stats(self) -> dict:
        with self._connect() as conn:
            stats = {
                "workflow_memory_count": _count(conn, "workflow_memory"),
                "design_memory_count": _count(conn, "design_memory"),
                "error_memory_count": _count(conn, "error_memory"),
                "document_pack_memory_count": _count(conn, "document_pack_memory"),
                "document_pack_issue_memory_count": _count(conn, "document_pack_issue_memory"),
            }
        return stats | {"vector_outbox": self.vector_outbox_status()}

    def purge_workflow(self, workflow_id: str) -> dict:
        """Forget one workflow in canonical memory and invalidate its vector projection."""

        if not workflow_id or not workflow_id.strip():
            raise ValueError("workflow_id is required")
        with self._write_lock:
            with self._connect() as conn:
                counts = {
                    "workflow_memory": conn.execute(
                        "SELECT COUNT(*) FROM workflow_memory WHERE workflow_id = ?",
                        (workflow_id,),
                    ).fetchone()[0],
                    "design_memory": conn.execute(
                        "SELECT COUNT(*) FROM design_memory WHERE workflow_id = ?",
                        (workflow_id,),
                    ).fetchone()[0],
                    "error_memory": conn.execute(
                        "SELECT COUNT(*) FROM error_memory WHERE workflow_id = ?",
                        (workflow_id,),
                    ).fetchone()[0],
                    "document_pack_links": conn.execute(
                        "SELECT COUNT(*) FROM document_pack_memory WHERE generated_workflow_id = ?",
                        (workflow_id,),
                    ).fetchone()[0],
                }
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "DELETE FROM workflow_memory WHERE workflow_id = ?",
                    (workflow_id,),
                )
                conn.execute(
                    "DELETE FROM design_memory WHERE workflow_id = ?",
                    (workflow_id,),
                )
                conn.execute(
                    "DELETE FROM error_memory WHERE workflow_id = ?",
                    (workflow_id,),
                )
                conn.execute(
                    "UPDATE document_pack_memory SET generated_workflow_id = NULL "
                    "WHERE generated_workflow_id = ?",
                    (workflow_id,),
                )
                if any(counts.values()):
                    _bump_vector_revision(conn)
                    outbox_enqueued = self._enqueue_vector_projection(
                        conn,
                        created_at=int(time.time()),
                    )
                else:
                    outbox_enqueued = False
        if outbox_enqueued:
            self.last_index_result = MemoryIndexResult(status="pending")
            self._schedule_reconciliation()
            vector_projection = self.vector_outbox_status()
        else:
            vector_projection = self.vector_outbox_status()
        return {
            "status": "purged",
            "workflow_id": workflow_id,
            "deleted": counts,
            "vector_projection": vector_projection,
        }

    def write_document_pack_summary(
        self,
        *,
        spec: ProjectDesignSpec,
        summary: DocumentPackSummary,
        qa_report: DocumentPackQAReport,
        corrections: list[dict],
        generated_workflow_id: str | None,
    ) -> dict:
        with self._write_lock:
            return self._write_document_pack_summary(
                spec=spec,
                summary=summary,
                qa_report=qa_report,
                corrections=corrections,
                generated_workflow_id=generated_workflow_id,
            )

    def _write_document_pack_summary(
        self,
        *,
        spec: ProjectDesignSpec,
        summary: DocumentPackSummary,
        qa_report: DocumentPackQAReport,
        corrections: list[dict],
        generated_workflow_id: str | None,
    ) -> dict:
        created_at = int(time.time())
        fields = _document_pack_fields(spec)
        categories = _document_pack_categories(spec)
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM document_pack_issue_memory WHERE pack_id = ?",
                (spec.pack_id,),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO document_pack_memory (
                    pack_id, site_code, tower_type, tower_height_m, sector_count, qa_score,
                    ready_to_generate, source_mode, categories_json, fields_json,
                    corrections_json, conflicts_json, missing_fields_json,
                    generated_workflow_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    spec.pack_id,
                    fields.get("site.site_code"),
                    fields.get("tower.tower_type"),
                    fields.get("tower.tower_height_m"),
                    len(spec.radio_sectors),
                    summary.qa_score or 0.0,
                    int(qa_report.ready_to_generate),
                    spec.source_mode,
                    json.dumps(categories),
                    json.dumps(fields),
                    json.dumps(corrections),
                    json.dumps([field.model_dump() for field in spec.conflicts]),
                    json.dumps([field.model_dump() for field in spec.missing_fields]),
                    generated_workflow_id,
                    created_at,
                ),
            )
            for check in qa_report.checks:
                if check.passed:
                    continue
                conn.execute(
                    """
                    INSERT INTO document_pack_issue_memory (
                        pack_id, issue_code, message, severity, field, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        spec.pack_id,
                        check.name,
                        check.reason,
                        "warning",
                        check.name,
                        created_at,
                    ),
                )
            _bump_vector_revision(conn)
            outbox_enqueued = self._enqueue_vector_projection(conn, created_at=created_at)
        if outbox_enqueued:
            self.last_index_result = MemoryIndexResult(status="pending")
            self._schedule_reconciliation()
            index_result = self.vector_outbox_status()
        else:
            index_result = {"status": "skipped", "errors": ["rag_service_not_configured"]}
        return {
            "status": "written",
            "pack_id": spec.pack_id,
            "generated_workflow_id": generated_workflow_id,
            "sqlite": {
                "document_pack_memory_count": self.stats()["document_pack_memory_count"],
                "document_pack_issue_memory_count": self.stats()[
                    "document_pack_issue_memory_count"
                ],
            },
            "qdrant": index_result,
        }

    def reindex_vector_memory(self) -> dict:
        """Rebuild the derived Qdrant memory projection from canonical SQLite rows."""
        if self.rag_service is None:
            return {
                "status": "skipped",
                "errors": ["rag_service_not_configured"],
            }
        with self._write_lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._enqueue_vector_projection(conn, created_at=int(time.time()))
        reconciliation = self.reconcile_vector_outbox()
        projection = reconciliation.get("projection")
        if reconciliation.get("status") != "succeeded" or not isinstance(projection, dict):
            self._schedule_reconciliation()
            raise RuntimeError("Runtime memory vector reindex did not complete")
        return projection

    def reconcile_vector_outbox(self) -> dict:
        """Try one durable projection operation without holding the SQLite write boundary."""

        if self.rag_service is None:
            return {
                "status": "skipped",
                "errors": ["rag_service_not_configured"],
                "outbox": self.vector_outbox_status(),
            }
        with self._reconcile_lock:
            operation = self._claim_vector_projection()
            if operation is None:
                return {"status": "idle", "outbox": self.vector_outbox_status()}

            with self._write_lock:
                documents, source_counts, skipped_source_counts = self._runtime_vector_documents()
                source_fingerprint = self._vector_source_fingerprint()
                claim_is_current = self._refresh_claimed_projection_identity(
                    operation_id=int(operation["id"]),
                    source_fingerprint=source_fingerprint,
                )
            if not claim_is_current:
                self.last_index_result = MemoryIndexResult(status="pending")
                return {
                    "status": "pending",
                    "reason": "newer_projection_operation_pending",
                    "outbox": self.vector_outbox_status(),
                }
            try:
                projection = self._rebuild_vector_projection(
                    documents=documents,
                    source_counts=source_counts,
                    skipped_source_counts=skipped_source_counts,
                    source_fingerprint=source_fingerprint,
                )
            except Exception as exc:
                marked_failed = self._mark_vector_projection_failed(
                    operation_id=int(operation["id"]),
                    source_fingerprint=source_fingerprint,
                    error=exc,
                )
                if not marked_failed:
                    self.last_index_result = MemoryIndexResult(status="pending")
                    return {
                        "status": "pending",
                        "reason": "newer_projection_operation_pending",
                        "outbox": self.vector_outbox_status(),
                    }
                error_code = type(exc).__name__
                self.last_index_result = MemoryIndexResult(
                    status="failed",
                    errors=[f"vector_projection:{error_code}"],
                )
                return {
                    "status": "failed",
                    "error_code": error_code,
                    "outbox": self.vector_outbox_status(),
                }

            with self._write_lock:
                current_fingerprint = self._vector_source_fingerprint()
                if current_fingerprint != source_fingerprint:
                    with self._connect() as conn:
                        conn.execute("BEGIN IMMEDIATE")
                        self._enqueue_vector_projection(conn, created_at=int(time.time()))
                    self.last_index_result = MemoryIndexResult(status="pending")
                    return {
                        "status": "pending",
                        "reason": "sqlite_source_changed_during_projection",
                        "outbox": self.vector_outbox_status(),
                    }
                marked_succeeded = self._mark_vector_projection_succeeded(
                    operation_id=int(operation["id"]),
                    source_fingerprint=source_fingerprint,
                )
            if not marked_succeeded:
                self.last_index_result = MemoryIndexResult(status="pending")
                return {
                    "status": "pending",
                    "reason": "newer_projection_operation_pending",
                    "outbox": self.vector_outbox_status(),
                }

            candidate_counts = projection["candidate_counts"]
            self.last_index_result = MemoryIndexResult(
                status="indexed",
                indexed_collections=candidate_counts,
                indexed_points=sum(candidate_counts.values()),
            )
            return {
                "status": "succeeded",
                "projection": projection,
                "outbox": self.vector_outbox_status(),
            }

    def vector_outbox_status(self) -> dict:
        """Return a bounded, API-safe summary of the recoverable Qdrant projection."""

        if self.rag_service is None:
            return {
                "status": "not_configured",
                "degraded": False,
                "reindex_required": False,
                "pending_count": 0,
                "failed_count": 0,
                "attempt_count": 0,
                "retry_count": 0,
                "last_error_code": None,
            }
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT status, retry_count, last_error_code, embedding_provider,
                       embedding_model, embedding_dimensions, collection_target,
                       source_fingerprint, updated_at, attempted_at, succeeded_at
                FROM memory_vector_outbox
                WHERE operation_key = ?
                """,
                (OUTBOX_OPERATION_KEY,),
            ).fetchone()
            counts = {
                str(status): int(count)
                for status, count in conn.execute(
                    "SELECT status, COUNT(*) FROM memory_vector_outbox GROUP BY status"
                ).fetchall()
            }
        if row is None:
            return {
                "status": "idle",
                "degraded": False,
                "reindex_required": False,
                "pending_count": 0,
                "failed_count": 0,
                "attempt_count": 0,
                "retry_count": 0,
                "last_error_code": None,
            }
        status = str(row["status"])
        return {
            "status": status,
            "degraded": status in OUTBOX_PENDING_STATES,
            "reindex_required": status in OUTBOX_PENDING_STATES,
            "pending_count": counts.get("pending", 0),
            "failed_count": counts.get("failed", 0),
            "attempt_count": counts.get("attempt", 0),
            "retry_count": int(row["retry_count"]),
            "last_error_code": row["last_error_code"],
            "embedding_provider": row["embedding_provider"],
            "embedding_model": row["embedding_model"],
            "embedding_dimensions": int(row["embedding_dimensions"]),
            "collection": row["collection_target"],
            "source_fingerprint": row["source_fingerprint"],
            "updated_at": int(row["updated_at"]),
            "attempted_at": int(row["attempted_at"]) if row["attempted_at"] else None,
            "succeeded_at": int(row["succeeded_at"]) if row["succeeded_at"] else None,
        }

    def close(self, *, timeout_s: float = 10.0) -> None:
        """Stop background reconciliation before its Qdrant dependency is closed."""

        self._shutdown_event.set()
        with self._reconcile_thread_lock:
            thread = self._reconcile_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout_s))

    def start(self) -> None:
        """Re-enable reconciliation when a local ASGI lifespan is entered again."""

        self._shutdown_event.clear()
        self._schedule_reconciliation()

    def _rebuild_vector_projection(
        self,
        *,
        documents: dict[str, list[RagDocument]],
        source_counts: dict[str, int],
        skipped_source_counts: dict[str, int],
        source_fingerprint: str,
    ) -> dict:
        if self.rag_service is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("rag_service_not_configured")
        report = self.rag_service.reindex_runtime_documents(
            documents,
            source_fingerprint=source_fingerprint,
        )
        candidate_counts = {
            collection: len(collection_documents)
            for collection, collection_documents in documents.items()
        }
        return {
            **report.model_dump(),
            "embedding_dimensions": self.rag_service.embedding_provider.dimensions,
            "source_counts": source_counts,
            "skipped_source_counts": skipped_source_counts,
            "candidate_counts": candidate_counts,
            "compacted_points": (
                sum(source_counts.values())
                - sum(skipped_source_counts.values())
                - sum(candidate_counts.values())
            ),
            "source_fingerprint": source_fingerprint,
            "sqlite_preserved": True,
            "legacy_collections_preserved": True,
        }

    def _schedule_reconciliation(self) -> None:
        if (
            not self._auto_reconcile
            or self.rag_service is None
            or self._shutdown_event.is_set()
            or not self._has_reconcilable_projection()
        ):
            return
        with self._reconcile_thread_lock:
            if self._reconcile_thread is not None and self._reconcile_thread.is_alive():
                return
            self._reconcile_thread = threading.Thread(
                target=self._reconciliation_worker,
                name="memory-vector-outbox",
                daemon=True,
            )
            self._reconcile_thread.start()

    def _reconciliation_worker(self) -> None:
        retry_delay = self._reconcile_retry_initial_s
        try:
            while not self._shutdown_event.is_set():
                result = self.reconcile_vector_outbox()
                status = result.get("status")
                if status in {"succeeded", "pending"}:
                    retry_delay = self._reconcile_retry_initial_s
                    if not self._has_reconcilable_projection():
                        return
                    continue
                if status == "failed":
                    if self._shutdown_event.wait(retry_delay):
                        return
                    retry_delay = min(retry_delay * 2, self._reconcile_retry_max_s)
                    continue
                return
        except Exception:
            logger.exception("Memory vector outbox reconciliation stopped unexpectedly")
        finally:
            with self._reconcile_thread_lock:
                if self._reconcile_thread is threading.current_thread():
                    self._reconcile_thread = None
            if not self._shutdown_event.is_set():
                try:
                    self._schedule_reconciliation()
                except Exception:
                    logger.exception("Memory vector outbox reconciliation could not be rescheduled")

    def _has_reconcilable_projection(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM memory_vector_outbox
                WHERE operation_key = ? AND status IN ('pending', 'failed')
                """,
                (OUTBOX_OPERATION_KEY,),
            ).fetchone()
        return row is not None

    def _claim_vector_projection(self) -> sqlite3.Row | None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM memory_vector_outbox
                WHERE operation_key = ? AND status IN ('pending', 'failed')
                """,
                (OUTBOX_OPERATION_KEY,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE memory_vector_outbox
                SET status = 'attempt', retry_count = retry_count + 1,
                    last_error = NULL, last_error_code = NULL,
                    attempted_at = ?, updated_at = ?
                WHERE id = ? AND status IN ('pending', 'failed')
                """,
                (now, now, int(row["id"])),
            )
            return conn.execute(
                "SELECT * FROM memory_vector_outbox WHERE id = ?",
                (int(row["id"]),),
            ).fetchone()

    def _refresh_claimed_projection_identity(
        self,
        *,
        operation_id: int,
        source_fingerprint: str,
    ) -> bool:
        provider, model, dimensions, input_profile = self._embedding_identity()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE memory_vector_outbox
                SET embedding_provider = ?, embedding_model = ?, embedding_dimensions = ?,
                    embedding_input_profile = ?, source_fingerprint = ?, updated_at = ?
                WHERE id = ? AND status = 'attempt'
                """,
                (
                    provider,
                    model,
                    dimensions,
                    input_profile,
                    source_fingerprint,
                    int(time.time()),
                    operation_id,
                ),
            )
        return cursor.rowcount == 1

    def _mark_vector_projection_failed(
        self,
        *,
        operation_id: int,
        source_fingerprint: str,
        error: BaseException,
    ) -> bool:
        error_text = _bounded_outbox_error(error)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE memory_vector_outbox
                SET status = 'failed', last_error = ?, last_error_code = ?, updated_at = ?
                WHERE id = ? AND status = 'attempt' AND source_fingerprint = ?
                """,
                (
                    error_text,
                    type(error).__name__[:128],
                    int(time.time()),
                    operation_id,
                    source_fingerprint,
                ),
            )
        return cursor.rowcount == 1

    def _mark_vector_projection_succeeded(
        self,
        *,
        operation_id: int,
        source_fingerprint: str,
    ) -> bool:
        now = int(time.time())
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE memory_vector_outbox
                SET status = 'succeeded', last_error = NULL, last_error_code = NULL,
                    succeeded_at = ?, updated_at = ?
                WHERE id = ? AND status = 'attempt' AND source_fingerprint = ?
                """,
                (now, now, operation_id, source_fingerprint),
            )
        return cursor.rowcount == 1

    def _enqueue_vector_projection(
        self,
        conn: sqlite3.Connection,
        *,
        created_at: int,
    ) -> bool:
        if self.rag_service is None:
            return False
        provider, model, dimensions, input_profile = self._embedding_identity()
        source_fingerprint = _vector_source_fingerprint_conn(conn)
        conn.execute(
            """
            INSERT INTO memory_vector_outbox (
                operation_key, operation_type, collection_target, status, retry_count,
                last_error, last_error_code, embedding_provider, embedding_model,
                embedding_dimensions, embedding_input_profile, source_fingerprint,
                created_at, updated_at, attempted_at, succeeded_at
            ) VALUES (?, 'reindex', ?, 'pending', 0, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            ON CONFLICT(operation_key) DO UPDATE SET
                operation_type = excluded.operation_type,
                collection_target = excluded.collection_target,
                status = 'pending',
                retry_count = CASE
                    WHEN memory_vector_outbox.source_fingerprint = excluded.source_fingerprint
                    THEN memory_vector_outbox.retry_count
                    ELSE 0
                END,
                last_error = NULL,
                last_error_code = NULL,
                embedding_provider = excluded.embedding_provider,
                embedding_model = excluded.embedding_model,
                embedding_dimensions = excluded.embedding_dimensions,
                embedding_input_profile = excluded.embedding_input_profile,
                source_fingerprint = excluded.source_fingerprint,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                attempted_at = NULL,
                succeeded_at = NULL
            """,
            (
                OUTBOX_OPERATION_KEY,
                OUTBOX_COLLECTION_TARGET,
                provider,
                model,
                dimensions,
                input_profile,
                source_fingerprint,
                created_at,
                created_at,
            ),
        )
        return True

    def _embedding_identity(self) -> tuple[str, str, int, str]:
        if self.rag_service is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("rag_service_not_configured")
        embedding_provider = self.rag_service.embedding_provider
        provider_name = str(embedding_provider.name)
        provider = provider_name.split(":", 1)[0]
        model = str(getattr(embedding_provider, "model_name", provider_name))
        dimensions = int(embedding_provider.dimensions)
        input_profile = str(getattr(embedding_provider, "input_profile", "legacy_generic_v1"))
        return provider, model, dimensions, input_profile

    def _recover_interrupted_outbox_attempts(self) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memory_vector_outbox
                SET status = 'pending', last_error = ?, last_error_code = ?, updated_at = ?
                WHERE status = 'attempt'
                """,
                (
                    "Projection attempt interrupted before a terminal acknowledgement",
                    "InterruptedProjectionAttempt",
                    now,
                ),
            )

    def _restore_outbox_index_result(self) -> None:
        outbox = self.vector_outbox_status()
        status = outbox.get("status")
        if status == "failed":
            error_code = str(outbox.get("last_error_code") or "ProjectionFailure")
            self.last_index_result = MemoryIndexResult(
                status="failed",
                errors=[f"vector_projection:{error_code}"],
            )
        elif status in {"pending", "attempt"}:
            self.last_index_result = MemoryIndexResult(status=str(status))
        elif status == "succeeded":
            self.last_index_result = MemoryIndexResult(status="indexed")

    def _runtime_vector_documents(
        self,
    ) -> tuple[dict[str, list[RagDocument]], dict[str, int], dict[str, int]]:
        with self._connect() as conn:
            design_rows = conn.execute(
                """
                SELECT workflow_id, tower_type, scene_spec_json, qa_score, created_at
                FROM design_memory
                ORDER BY created_at DESC, workflow_id DESC
                """
            ).fetchall()
            error_rows = conn.execute(
                """
                SELECT network_type, tower_type, issue_code, message, severity,
                       COUNT(*) AS occurrence_count, MAX(created_at) AS last_seen_at,
                       MAX(workflow_id) AS representative_workflow_id
                FROM error_memory
                GROUP BY network_type, tower_type, issue_code, message, severity
                ORDER BY last_seen_at DESC, issue_code
                """
            ).fetchall()
            document_pack_rows = conn.execute(
                """
                SELECT pack_id, tower_type, sector_count, qa_score, ready_to_generate,
                       source_mode, categories_json, fields_json, generated_workflow_id,
                       created_at
                FROM document_pack_memory
                ORDER BY created_at DESC, pack_id DESC
                """
            ).fetchall()

        design_documents: dict[str, RagDocument] = {}
        design_occurrences: dict[str, int] = {}
        skipped_design_rows = 0
        for row in design_rows:
            try:
                scene = SceneSpec.model_validate_json(row["scene_spec_json"])
            except ValidationError:
                skipped_design_rows += 1
                logger.warning(
                    "Skipping invalid persisted design memory row during vector projection: %s",
                    row["workflow_id"],
                )
                continue
            signature_payload = _scene_memory_signature(scene)
            signature = _stable_payload_hash(signature_payload)
            design_occurrences[signature] = design_occurrences.get(signature, 0) + 1
            if signature in design_documents:
                continue
            payload = {
                "type": "design_memory_pattern",
                "doc_type": "design_memory_pattern",
                "technical_signature": signature,
                "representative_workflow_id": row["workflow_id"],
                "network_type": scene.network_type,
                "tower_type": row["tower_type"],
                "tower_height_m": scene.tower.height_m,
                "sector_count": len(scene.sectors),
                "azimuths_deg": [sector.azimuth_deg for sector in scene.sectors],
                "install_heights_m": [sector.install_height_m for sector in scene.sectors],
                "qa_score": row["qa_score"],
                "last_seen_at": row["created_at"],
            }
            design_documents[signature] = RagDocument(
                doc_id=f"memory:design_pattern:{signature}",
                collection="design_memory",
                text=_design_pattern_text(payload, signature_payload),
                payload=payload,
            )
        for signature, document in design_documents.items():
            document.payload["occurrence_count"] = design_occurrences[signature]

        error_documents: list[RagDocument] = []
        for row in error_rows:
            identity = {
                "network_type": row["network_type"],
                "tower_type": row["tower_type"],
                "issue_code": row["issue_code"],
                "message": row["message"],
                "severity": row["severity"],
            }
            signature = _stable_payload_hash(identity)
            payload = {
                "type": "memory_issue_pattern",
                "doc_type": "memory_issue_pattern",
                **identity,
                "occurrence_count": row["occurrence_count"],
                "last_seen_at": row["last_seen_at"],
                "representative_workflow_id": row["representative_workflow_id"],
            }
            error_documents.append(
                RagDocument(
                    doc_id=f"memory:error_pattern:{signature}",
                    collection="error_memory",
                    text=_error_pattern_text(payload),
                    payload=payload,
                )
            )

        document_pack_documents: list[RagDocument] = []
        for row in document_pack_rows:
            fields = json.loads(row["fields_json"] or "{}")
            categories = json.loads(row["categories_json"] or "{}")
            payload = {
                "type": "document_pack_memory",
                "doc_type": "document_pack_memory",
                "pack_id": row["pack_id"],
                "tower_type": row["tower_type"],
                "sector_count": row["sector_count"],
                "qa_score": row["qa_score"],
                "ready_to_generate": bool(row["ready_to_generate"]),
                "source_mode": row["source_mode"],
                "categories": categories,
                "generated_workflow_id": row["generated_workflow_id"],
                "created_at": row["created_at"],
            }
            document_pack_documents.append(
                RagDocument(
                    doc_id=f"memory:document_pack:{row['pack_id']}",
                    collection="document_pack_memory",
                    text=_document_pack_memory_text(payload, fields),
                    payload=payload,
                )
            )

        return (
            {
                "design_memory": list(design_documents.values()),
                "error_memory": error_documents,
                "document_pack_memory": document_pack_documents,
            },
            {
                "design_memory": len(design_rows),
                "error_memory": sum(int(row["occurrence_count"]) for row in error_rows),
                "document_pack_memory": len(document_pack_rows),
            },
            {
                "design_memory": skipped_design_rows,
                "error_memory": 0,
                "document_pack_memory": 0,
            },
        )

    def _vector_source_fingerprint(self) -> str:
        with self._connect() as conn:
            return _vector_source_fingerprint_conn(conn)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_memory (
                    workflow_id TEXT PRIMARY KEY,
                    network_type TEXT NOT NULL,
                    tower_type TEXT NOT NULL,
                    sector_count INTEGER NOT NULL,
                    generation_mode TEXT NOT NULL,
                    qa_score REAL NOT NULL,
                    warnings_json TEXT NOT NULL,
                    scene_spec_path TEXT NOT NULL,
                    validation_report_path TEXT NOT NULL DEFAULT '',
                    reusable_pattern INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS design_memory (
                    workflow_id TEXT PRIMARY KEY,
                    scene_id TEXT NOT NULL,
                    network_type TEXT NOT NULL,
                    tower_type TEXT NOT NULL,
                    scene_spec_json TEXT NOT NULL,
                    validation_report_json TEXT NOT NULL,
                    qa_score REAL NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS error_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    network_type TEXT,
                    tower_type TEXT,
                    issue_code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'warning',
                    created_at INTEGER NOT NULL
                )
                """
            )
            _ensure_column(
                conn,
                "workflow_memory",
                "validation_report_path",
                "validation_report_path TEXT NOT NULL DEFAULT ''",
            )
            _ensure_column(
                conn,
                "error_memory",
                "issue_code",
                "issue_code TEXT NOT NULL DEFAULT 'UNKNOWN'",
            )
            _ensure_column(
                conn,
                "error_memory",
                "severity",
                "severity TEXT NOT NULL DEFAULT 'warning'",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_memory_lookup "
                "ON workflow_memory(network_type, tower_type, sector_count, qa_score, "
                "reusable_pattern)"
            )
            conn.execute(
                "UPDATE workflow_memory SET reusable_pattern = 0 "
                "WHERE generation_mode != 'real_blender'"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_error_memory_lookup "
                "ON error_memory(network_type, tower_type, created_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_pack_memory (
                    pack_id TEXT PRIMARY KEY,
                    site_code TEXT,
                    tower_type TEXT,
                    tower_height_m REAL,
                    sector_count INTEGER NOT NULL,
                    qa_score REAL NOT NULL,
                    ready_to_generate INTEGER NOT NULL,
                    source_mode TEXT NOT NULL,
                    categories_json TEXT NOT NULL,
                    fields_json TEXT NOT NULL,
                    corrections_json TEXT NOT NULL,
                    conflicts_json TEXT NOT NULL,
                    missing_fields_json TEXT NOT NULL,
                    generated_workflow_id TEXT,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_pack_issue_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pack_id TEXT NOT NULL,
                    issue_code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    field TEXT,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_document_pack_memory_lookup "
                "ON document_pack_memory(tower_type, sector_count, qa_score, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_document_pack_issue_lookup "
                "ON document_pack_issue_memory(pack_id, issue_code, created_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_metadata (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO memory_metadata(key, value) VALUES ('vector_revision', 0)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_vector_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_key TEXT NOT NULL UNIQUE,
                    operation_type TEXT NOT NULL CHECK (operation_type IN ('reindex')),
                    collection_target TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (status IN ('pending', 'attempt', 'succeeded', 'failed')),
                    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
                    last_error TEXT,
                    last_error_code TEXT,
                    embedding_provider TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dimensions INTEGER NOT NULL CHECK (embedding_dimensions > 0),
                    embedding_input_profile TEXT NOT NULL,
                    source_fingerprint TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    attempted_at INTEGER,
                    succeeded_at INTEGER
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_vector_outbox_status "
                "ON memory_vector_outbox(status, updated_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _insert_issue_memory(
    conn: sqlite3.Connection,
    workflow_id: str,
    network_type: str,
    tower_type: str,
    issue: ValidationIssue,
    created_at: int,
) -> None:
    columns = _table_columns(conn, "error_memory")
    if "warning_code" in columns:
        conn.execute(
            """
            INSERT INTO error_memory (
                workflow_id, network_type, tower_type, warning_code, issue_code, message,
                severity, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                network_type,
                tower_type,
                issue.code,
                issue.code,
                issue.message,
                issue.severity,
                created_at,
            ),
        )
        return
    conn.execute(
        """
        INSERT INTO error_memory (
            workflow_id, network_type, tower_type, issue_code, message, severity, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workflow_id,
            network_type,
            tower_type,
            issue.code,
            issue.message,
            issue.severity,
            created_at,
        ),
    )


def _unique_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    unique: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        identity = (issue.code, issue.message, issue.severity)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(issue)
        if len(unique) >= MAX_MEMORY_ISSUES_PER_WORKFLOW:
            break
    return unique


def _decode_workflow_row(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["warnings"] = json.loads(payload.pop("warnings_json") or "[]")
    payload["reusable_pattern"] = bool(payload["reusable_pattern"])
    payload.pop("scene_spec_path", None)
    payload.pop("validation_report_path", None)
    return payload


def _is_reusable_workflow(
    report: ValidationReport,
    generation: GenerationResult | None,
) -> bool:
    return bool(
        generation is not None
        and generation.status == "generated"
        and generation.mode == "real_blender"
        and generation.blender_available
        and report.status == "passed"
        and report.score >= HIGH_QA_THRESHOLD
    )


def _document_pack_fields(spec: ProjectDesignSpec) -> dict:
    fields: dict[str, object] = {}
    for section_name in [
        "site_info",
        "coordinate_info",
        "tower_spec",
        "foundation_spec",
        "cabling_spec",
        "grounding_spec",
        "compound_spec",
    ]:
        section = getattr(spec, section_name)
        prefix = {
            "site_info": "site",
            "coordinate_info": "coordinates",
            "tower_spec": "tower",
            "foundation_spec": "foundation",
            "cabling_spec": "cabling",
            "grounding_spec": "grounding",
            "compound_spec": "compound",
        }[section_name]
        for key, field in section.items():
            if field.status == "confirmed":
                fields[f"{prefix}.{key}"] = field.value
    if spec.radio_sectors:
        fields["radio.sector_count"] = len(spec.radio_sectors)
        fields["radio.azimuths_deg"] = [sector.azimuth_deg.value for sector in spec.radio_sectors]
        fields["radio.hba_m"] = [sector.hba_m.value for sector in spec.radio_sectors]
    return fields


def _document_pack_categories(spec: ProjectDesignSpec) -> dict[str, int]:
    categories: dict[str, int] = {}
    for document in spec.document_references:
        categories[document.category] = categories.get(document.category, 0) + 1
    return categories


def _document_pack_memory_text(payload: dict, fields: dict) -> str:
    return "\n".join(
        [
            f"pack_id: {payload.get('pack_id')}",
            f"tower_type: {payload.get('tower_type')}",
            f"sector_count: {payload.get('sector_count')}",
            f"qa_score: {payload.get('qa_score')}",
            f"ready_to_generate: {payload.get('ready_to_generate')}",
            f"source_mode: {payload.get('source_mode')}",
            f"generated_workflow_id: {payload.get('generated_workflow_id')}",
            "fields: " + json.dumps(fields, ensure_ascii=False, sort_keys=True),
        ]
    )


def _scene_memory_signature(scene: SceneSpec) -> dict:
    return {
        "network_type": scene.network_type,
        "tower": {
            "asset_id": scene.tower.asset_id,
            "height_m": scene.tower.height_m,
            "characteristics": scene.tower.characteristics.model_dump(mode="json"),
            "generation_strategy": scene.tower.generation_strategy,
            "geometry_source": scene.tower.geometry_source,
        },
        "sectors": [
            {
                "antenna_asset_id": sector.antenna_asset_id,
                "radio_asset_id": sector.radio_asset_id,
                "install_height_m": sector.install_height_m,
                "azimuth_deg": sector.azimuth_deg,
                "mechanical_tilt_deg": sector.mechanical_tilt_deg,
                "electrical_tilt_deg": sector.electrical_tilt_deg,
                "beamwidth_deg": sector.beamwidth_deg,
                "include_cable": sector.include_cable,
            }
            for sector in sorted(scene.sectors, key=lambda item: item.azimuth_deg)
        ],
        "visual_elements": scene.visual_elements.model_dump(mode="json"),
        "accessories": [
            {
                "asset_id": accessory.asset_id,
                "asset_type": accessory.asset_type,
                "position": accessory.position,
                "rotation_deg": accessory.rotation_deg,
                "scale": accessory.scale,
                "generation_strategy": accessory.generation_strategy,
            }
            for accessory in scene.accessory_assets
        ],
    }


def _design_pattern_text(payload: dict, signature_payload: dict) -> str:
    return "\n".join(
        [
            "Validated reusable telecom design pattern",
            f"network_type: {payload.get('network_type')}",
            f"tower_type: {payload.get('tower_type')}",
            f"tower_search_terms: {_tower_type_search_terms(payload.get('tower_type'))}",
            f"tower_height_m: {payload.get('tower_height_m')}",
            f"sector_count: {payload.get('sector_count')}",
            f"azimuths_deg: {payload.get('azimuths_deg')}",
            f"install_heights_m: {payload.get('install_heights_m')}",
            "technical_configuration: "
            + json.dumps(signature_payload, ensure_ascii=False, sort_keys=True),
        ]
    )


def _error_pattern_text(payload: dict) -> str:
    return "\n".join(
        [
            "Observed telecom validation issue pattern",
            f"network_type: {payload.get('network_type')}",
            f"tower_type: {payload.get('tower_type')}",
            f"issue_code: {payload.get('issue_code')}",
            f"severity: {payload.get('severity')}",
            f"message: {payload.get('message')}",
            f"occurrence_count: {payload.get('occurrence_count')}",
        ]
    )


def _tower_type_search_terms(tower_type: object) -> str:
    terms = {
        "lattice_tower": "pylône treillis lattice tower",
        "monopole": "pylône monopole monotube pole",
        "rooftop_mast": "mât toiture rooftop mast",
        "small_cell_pole": "poteau small cell mobilier urbain",
    }
    normalized = str(tower_type or "")
    return terms.get(normalized, normalized)


def _table_vector_snapshot(conn: sqlite3.Connection, table: str) -> dict[str, int]:
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS row_count,
               COALESCE(MAX(created_at), 0) AS max_created_at,
               COALESCE(SUM(created_at), 0) AS sum_created_at,
               COALESCE(MAX(rowid), 0) AS max_rowid
        FROM {table}
        """
    ).fetchone()
    return {
        "row_count": int(row["row_count"]),
        "max_created_at": int(row["max_created_at"]),
        "sum_created_at": int(row["sum_created_at"]),
        "max_rowid": int(row["max_rowid"]),
    }


def _vector_revision(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM memory_metadata WHERE key = 'vector_revision'").fetchone()
    return int(row[0]) if row is not None else 0


def _bump_vector_revision(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE memory_metadata SET value = value + 1 WHERE key = 'vector_revision'")


def _vector_source_fingerprint_conn(conn: sqlite3.Connection) -> str:
    snapshot = {
        table: _table_vector_snapshot(conn, table)
        for table in ("design_memory", "error_memory", "document_pack_memory")
    }
    snapshot["vector_revision"] = _vector_revision(conn)
    return _stable_payload_hash(snapshot)


def _bounded_outbox_error(error: BaseException) -> str:
    message = " ".join(str(error).split())
    rendered = f"{type(error).__name__}: {message}" if message else type(error).__name__
    return rendered[:MAX_OUTBOX_ERROR_LENGTH]


def _stable_payload_hash(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
