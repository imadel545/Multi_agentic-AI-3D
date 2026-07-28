from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

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


class MemoryService:
    def __init__(self, db_path: Path, rag_service: RagService | None = None) -> None:
        self.db_path = db_path
        self.rag_service = rag_service
        self._last_index_result = threading.local()
        self._index_result_lock = threading.Lock()
        self._write_lock = threading.RLock()
        self._latest_index_result = MemoryIndexResult(status="not_indexed")
        self.last_index_result = MemoryIndexResult(status="not_indexed")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

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
        compatibility = None
        if self.rag_service is not None:
            stats = self.stats()
            compatibility = self.rag_service.runtime_collection_compatibility(
                source_fingerprint=self._vector_source_fingerprint(),
                source_has_data=bool(
                    stats["design_memory_count"]
                    or stats["error_memory_count"]
                    or stats["document_pack_memory_count"]
                ),
            )
        return {
            "latest_index_result": latest.model_dump(),
            "vector_compatibility": compatibility,
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
        self.last_index_result = self._index_summary(summary, issues, scene)
        if self.last_index_result.status == "indexed" and self.rag_service is not None:
            self.rag_service.update_runtime_source_fingerprint(self._vector_source_fingerprint())
        return summary

    def stats(self) -> dict:
        with self._connect() as conn:
            return {
                "workflow_memory_count": _count(conn, "workflow_memory"),
                "design_memory_count": _count(conn, "design_memory"),
                "error_memory_count": _count(conn, "error_memory"),
                "document_pack_memory_count": _count(conn, "document_pack_memory"),
                "document_pack_issue_memory_count": _count(conn, "document_pack_issue_memory"),
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
        index_result = self._index_document_pack_memory(
            spec=spec,
            summary=summary,
            qa_report=qa_report,
            fields=fields,
            categories=categories,
            generated_workflow_id=generated_workflow_id,
            created_at=created_at,
        )
        if index_result.get("status") == "indexed" and self.rag_service is not None:
            self.rag_service.update_runtime_source_fingerprint(self._vector_source_fingerprint())
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
            documents, source_counts = self._runtime_vector_documents()
            source_fingerprint = self._vector_source_fingerprint()
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
            "candidate_counts": candidate_counts,
            "compacted_points": sum(source_counts.values()) - sum(candidate_counts.values()),
            "source_fingerprint": source_fingerprint,
            "sqlite_preserved": True,
            "legacy_collections_preserved": True,
        }

    def _runtime_vector_documents(
        self,
    ) -> tuple[dict[str, list[RagDocument]], dict[str, int]]:
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
        for row in design_rows:
            scene = SceneSpec.model_validate_json(row["scene_spec_json"])
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
        )

    def _vector_source_fingerprint(self) -> str:
        with self._connect() as conn:
            snapshot = {
                table: _table_vector_snapshot(conn, table)
                for table in ("design_memory", "error_memory", "document_pack_memory")
            }
            snapshot["vector_revision"] = _vector_revision(conn)
        return _stable_payload_hash(snapshot)

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

    def _index_summary(
        self,
        summary: MemorySummary,
        issues: list[ValidationIssue],
        scene: SceneSpec | None,
    ) -> MemoryIndexResult:
        if self.rag_service is None:
            return MemoryIndexResult(status="skipped", errors=["rag_service_not_configured"])
        indexed = {"design_memory": 0, "error_memory": 0}
        errors: list[str] = []
        design_documents = []
        if summary.reusable_pattern and scene is not None:
            signature_payload = _scene_memory_signature(scene)
            payload = _summary_payload(summary) | {
                "technical_signature": _stable_payload_hash(signature_payload),
                "tower_height_m": scene.tower.height_m,
                "azimuths_deg": [sector.azimuth_deg for sector in scene.sectors],
                "install_heights_m": [sector.install_height_m for sector in scene.sectors],
            }
            design_documents.append(
                RagDocument(
                    collection="design_memory",
                    doc_id=f"memory:design:{summary.workflow_id}",
                    text=_design_pattern_text(payload, signature_payload),
                    payload=payload,
                )
            )
        try:
            indexed["design_memory"] = self.rag_service.replace_runtime_documents(
                collection="design_memory",
                owner_filters={"workflow_id": summary.workflow_id},
                documents=design_documents,
            )
        except Exception as exc:
            errors.append(f"design_memory:{type(exc).__name__}:{exc}")

        issue_documents = [
            RagDocument(
                collection="error_memory",
                doc_id=f"memory:error:{summary.workflow_id}:{issue.code}",
                text=_issue_text(summary, issue),
                payload={
                    "type": "memory_issue",
                    "doc_type": "memory_issue",
                    "workflow_id": summary.workflow_id,
                    "network_type": summary.network_type,
                    "tower_type": summary.tower_type,
                    "sector_count": summary.sector_count,
                    "issue_code": issue.code,
                    "severity": issue.severity,
                    "created_at": summary.created_at,
                },
            )
            for issue in issues
        ]
        try:
            indexed["error_memory"] = self.rag_service.replace_runtime_documents(
                collection="error_memory",
                owner_filters={"workflow_id": summary.workflow_id},
                documents=issue_documents,
            )
        except Exception as exc:
            errors.append(f"error_memory:{type(exc).__name__}:{exc}")
        return MemoryIndexResult(
            status=("partial" if errors and sum(indexed.values()) else "failed")
            if errors
            else "indexed",
            indexed_collections=indexed,
            indexed_points=sum(indexed.values()),
            errors=errors,
        )

    def _index_document_pack_memory(
        self,
        *,
        spec: ProjectDesignSpec,
        summary: DocumentPackSummary,
        qa_report: DocumentPackQAReport,
        fields: dict,
        categories: dict,
        generated_workflow_id: str | None,
        created_at: int,
    ) -> dict:
        if self.rag_service is None:
            return {"status": "skipped", "errors": ["rag_service_not_configured"]}
        payload = {
            "type": "document_pack_memory",
            "doc_type": "document_pack_memory",
            "pack_id": spec.pack_id,
            "tower_type": fields.get("tower.tower_type"),
            "sector_count": len(spec.radio_sectors),
            "qa_score": summary.qa_score,
            "ready_to_generate": qa_report.ready_to_generate,
            "source_mode": spec.source_mode,
            "categories": categories,
            "generated_workflow_id": generated_workflow_id,
            "created_at": created_at,
        }
        try:
            indexed_points = self.rag_service.replace_runtime_documents(
                collection="document_pack_memory",
                owner_filters={"pack_id": spec.pack_id},
                documents=[
                    RagDocument(
                        collection="document_pack_memory",
                        doc_id=f"memory:document_pack:{spec.pack_id}",
                        text=_document_pack_memory_text(payload, fields),
                        payload=payload,
                    )
                ],
            )
        except Exception as exc:
            return {"status": "failed", "errors": [f"{type(exc).__name__}: {exc}"]}
        return {"status": "indexed", "indexed_points": indexed_points, "errors": []}

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


def _summary_payload(summary: MemorySummary) -> dict:
    return {
        "type": "memory_summary",
        "doc_type": "memory_summary",
        "workflow_id": summary.workflow_id,
        "network_type": summary.network_type,
        "tower_type": summary.tower_type,
        "sector_count": summary.sector_count,
        "generation_mode": summary.generation_mode,
        "qa_score": summary.qa_score,
        "warnings": summary.warnings,
        "reusable_pattern": summary.reusable_pattern,
        "created_at": summary.created_at,
    }


def _summary_text(summary: MemorySummary) -> str:
    return "\n".join(
        [
            f"workflow_id: {summary.workflow_id}",
            f"network_type: {summary.network_type}",
            f"tower_type: {summary.tower_type}",
            f"sector_count: {summary.sector_count}",
            f"generation_mode: {summary.generation_mode}",
            f"qa_score: {summary.qa_score}",
            f"reusable_pattern: {summary.reusable_pattern}",
        ]
    )


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


def _issue_text(summary: MemorySummary, issue: ValidationIssue) -> str:
    return "\n".join(
        [
            f"workflow_id: {summary.workflow_id}",
            f"network_type: {summary.network_type}",
            f"tower_type: {summary.tower_type}",
            f"sector_count: {summary.sector_count}",
            f"issue_code: {issue.code}",
            f"severity: {issue.severity}",
            f"message: {issue.message}",
        ]
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


def _stable_payload_hash(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
