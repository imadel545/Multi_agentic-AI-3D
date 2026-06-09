import json
import sqlite3
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
        index_result = self._index_document_pack_memory(
            spec=spec,
            summary=summary,
            qa_report=qa_report,
            fields=fields,
            categories=categories,
            generated_workflow_id=generated_workflow_id,
            created_at=created_at,
        )
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
            self.rag_service.upsert_runtime_document(
                collection="document_pack_memory",
                doc_id=f"memory:document_pack:{spec.pack_id}",
                text=_document_pack_memory_text(payload, fields),
                payload=payload,
            )
        except Exception as exc:
            return {"status": "failed", "errors": [f"{type(exc).__name__}: {exc}"]}
        return {"status": "indexed", "indexed_points": 1, "errors": []}

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
