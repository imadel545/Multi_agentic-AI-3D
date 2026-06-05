import json
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING

from core.contracts.memory import MemoryIndexResult, MemoryRecallResult, MemorySummary
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport
from core.services.blender_runner import GenerationResult

if TYPE_CHECKING:
    from core.rag import RagService

HIGH_QA_THRESHOLD = 0.95


class MemoryService:
    def __init__(self, db_path: Path, rag_service: "RagService | None" = None) -> None:
        self.db_path = db_path
        self.rag_service = rag_service
        self.last_index_result = MemoryIndexResult(status="not_indexed")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

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
        if requirements is None:
            self.last_index_result = MemoryIndexResult(
                status="skipped", errors=["requirements_missing"]
            )
            return None
        generation_mode = generation.mode if generation else "not_run"
        qa_score = report.score
        reusable_pattern = report.status == "passed" and qa_score >= HIGH_QA_THRESHOLD
        created_at = int(time.time())
        warnings = [warning.model_dump() for warning in report.warnings]
        summary = MemorySummary(
            workflow_id=workflow_id,
            network_type=requirements.network_type,
            tower_type=requirements.tower_type,
            sector_count=requirements.sector_count,
            generation_mode=generation_mode,
            qa_score=qa_score,
            warnings=warnings,
            scene_spec_path=str(scene_spec_path),
            validation_report_path=str(validation_report_path),
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
            if scene is not None:
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
            for issue in [*report.warnings, *report.errors]:
                _insert_issue_memory(
                    conn=conn,
                    workflow_id=workflow_id,
                    network_type=requirements.network_type,
                    tower_type=requirements.tower_type,
                    issue=issue,
                    created_at=created_at,
                )
        self.last_index_result = self._index_summary(summary, [*report.warnings, *report.errors])
        return summary

    def stats(self) -> dict:
        with self._connect() as conn:
            return {
                "workflow_memory_count": _count(conn, "workflow_memory"),
                "design_memory_count": _count(conn, "design_memory"),
                "error_memory_count": _count(conn, "error_memory"),
            }

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
                "CREATE INDEX IF NOT EXISTS idx_error_memory_lookup "
                "ON error_memory(network_type, tower_type, created_at)"
            )

    def _index_summary(
        self,
        summary: MemorySummary,
        issues: list[ValidationIssue],
    ) -> MemoryIndexResult:
        if self.rag_service is None:
            return MemoryIndexResult(status="skipped", errors=["rag_service_not_configured"])
        indexed = {"design_memory": 0, "error_memory": 0}
        errors: list[str] = []
        try:
            self.rag_service.upsert_runtime_document(
                collection="design_memory",
                doc_id=f"memory:design:{summary.workflow_id}",
                text=_summary_text(summary),
                payload=_summary_payload(summary),
            )
            indexed["design_memory"] = 1
        except Exception as exc:
            errors.append(f"design_memory:{type(exc).__name__}:{exc}")
        for issue in issues:
            try:
                self.rag_service.upsert_runtime_document(
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
                indexed["error_memory"] += 1
            except Exception as exc:
                errors.append(f"error_memory:{issue.code}:{type(exc).__name__}:{exc}")
        return MemoryIndexResult(
            status="failed" if errors else "indexed",
            indexed_collections=indexed,
            indexed_points=sum(indexed.values()),
            errors=errors,
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
    columns = {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


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


def _decode_workflow_row(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["warnings"] = json.loads(payload.pop("warnings_json") or "[]")
    payload["reusable_pattern"] = bool(payload["reusable_pattern"])
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
        "scene_spec_path": summary.scene_spec_path,
        "validation_report_path": summary.validation_report_path,
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
            f"scene_spec_path: {summary.scene_spec_path}",
            f"validation_report_path: {summary.validation_report_path}",
        ]
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
