import hashlib
import json
import shutil
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from core.contracts.document_pack import (
    DocumentExtractionStatus,
    DocumentPackCapabilities,
    DocumentPackCorrection,
    DocumentPackQACheck,
    DocumentPackQAReport,
    DocumentPackSummary,
    DocumentReference,
    ProjectDesignSpec,
    RequirementMappingResult,
    SourceEvidence,
)
from core.document_pack.cad import extract_cad_text_pages
from core.document_pack.classifier import classify_document, reclassify_document
from core.document_pack.extractor import (
    FieldCandidate,
    consolidate_candidates,
    extract_field_candidates,
)
from core.document_pack.groq_extractor import GroqDocumentExtractor
from core.document_pack.mapper import ProjectDesignSpecMapper
from core.document_pack.orchestrator import DocumentPackOrchestrator, DocumentPackWorkflowState
from core.document_pack.text_extractor import extract_text_result
from core.document_pack.tooling import detect_document_pack_capabilities

if TYPE_CHECKING:
    from core.llm import GroqStructuredClient
    from core.memory import MemoryService

MAX_MEMBER_SIZE_BYTES = 15 * 1024 * 1024
MAX_PACK_SIZE_BYTES = 80 * 1024 * 1024
MAX_MEMBER_COUNT = 256
MAX_UNCOMPRESSED_SIZE_BYTES = 200 * 1024 * 1024


class DocumentPackService:
    def __init__(
        self,
        outputs_dir: Path,
        *,
        groq_client: "GroqStructuredClient | None" = None,
        groq_provider_name: str | None = None,
        groq_bounded_extraction_enabled: bool = False,
        memory_service: "MemoryService | None" = None,
    ) -> None:
        self.outputs_dir = outputs_dir
        self.memory_service = memory_service
        self.groq_extractor = GroqDocumentExtractor(
            groq_client,
            provider_name=groq_provider_name,
            enabled=groq_bounded_extraction_enabled and groq_client is not None,
        )
        self.groq_bounded_extraction_enabled = self.groq_extractor.enabled
        self.orchestrator = DocumentPackOrchestrator(self)

    @property
    def packs_dir(self) -> Path:
        return self.outputs_dir / "document_packs"

    def ingest_zip(self, content: bytes, filename: str | None = None) -> DocumentPackSummary:
        _validate_zip_archive(content)
        capabilities = self.capabilities()
        tool_status = capabilities.status_map()
        pack_id = f"pack_{uuid.uuid4().hex[:12]}"
        pack_dir = self.packs_dir / pack_id
        pack_dir.mkdir(parents=True, exist_ok=False)
        try:
            state = self.orchestrator.run(
                {
                    "pack_id": pack_id,
                    "pack_dir": pack_dir,
                    "content": content,
                    "filename": filename,
                    "capabilities": capabilities,
                    "tool_status": tool_status,
                }
            )
            return DocumentPackSummary.model_validate(state["summary"])
        except zipfile.BadZipFile as exc:
            shutil.rmtree(pack_dir, ignore_errors=True)
            raise ValueError("invalid ZIP archive") from exc
        except Exception:
            shutil.rmtree(pack_dir, ignore_errors=True)
            raise

    def archive_limits(self) -> dict[str, int]:
        return {
            "max_zip_size_bytes": MAX_PACK_SIZE_BYTES,
            "max_member_size_bytes": MAX_MEMBER_SIZE_BYTES,
            "max_member_count": MAX_MEMBER_COUNT,
            "max_uncompressed_size_bytes": MAX_UNCOMPRESSED_SIZE_BYTES,
        }

    def capabilities(self) -> DocumentPackCapabilities:
        return detect_document_pack_capabilities(
            groq_bounded_extraction_enabled=self.groq_bounded_extraction_enabled
        )

    def index(self, state: DocumentPackWorkflowState) -> dict:
        started = time.perf_counter()
        with zipfile.ZipFile(BytesIO(state["content"])) as archive:
            member_count = sum(
                1
                for info in archive.infolist()
                if not info.is_dir() and not _unsafe_zip_path(info.filename)
            )
        return _node_update(
            state,
            "index",
            f"{member_count} candidate files",
            started,
            event_type="document_pack_indexed",
            event_payload={"member_count": member_count},
        )

    def extract_pdf_ocr_cad(self, state: DocumentPackWorkflowState) -> dict:
        started = time.perf_counter()
        documents: list[DocumentReference] = []
        candidates: list[FieldCandidate] = []
        pages_by_document = {}
        processing_warnings: list[str] = []
        seen_hashes: dict[str, str] = {}
        with zipfile.ZipFile(BytesIO(state["content"])) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                if info.is_dir() or _unsafe_zip_path(info.filename):
                    continue
                payload = archive.read(info)
                digest = hashlib.sha256(payload).hexdigest()
                duplicate_of = seen_hashes.get(digest)
                document = classify_document(info.filename, payload, duplicate_of=duplicate_of)
                seen_hashes.setdefault(digest, document.document_id)
                pages = []
                text_result = extract_text_result(document, payload)
                pages.extend(text_result.pages)
                cad_result = extract_cad_text_pages(document, payload)
                pages.extend(cad_result.pages)
                tools = sorted({*text_result.tools, *cad_result.tools})
                warnings = [*text_result.warnings, *cad_result.warnings]
                extraction_status = _combined_extraction_status(
                    text_result.extraction_status,
                    cad_result.extraction_status,
                    document.extractability,
                )
                document = reclassify_document(
                    document,
                    "\n".join(page.text for page in pages if page.text.strip()),
                ).model_copy(
                    update={
                        "cad_status": cad_result.cad_status
                        if document.extractability == "cad"
                        else document.cad_status,
                        "extraction_status": extraction_status,
                        "processing_tools": tools,
                        "processing_warnings": warnings,
                    }
                )
                documents.append(document)
                pages_by_document[document.document_id] = pages
                if document.used_for_design:
                    candidates.extend(extract_field_candidates(document, pages))
                processing_warnings.extend(f"{document.path}: {warning}" for warning in warnings)
        update = {
            "documents": documents,
            "pages_by_document": pages_by_document,
            "candidates": candidates,
            "processing_warnings": processing_warnings,
        }
        return update | _node_update(
            state,
            "extract_pdf_ocr_cad",
            f"{len(candidates)} deterministic candidates",
            started,
            event_type="document_pack_extracted",
            event_payload={
                "document_count": len(documents),
                "candidate_count": len(candidates),
                "warning_count": len(processing_warnings),
            },
        )

    def groq_extract(self, state: DocumentPackWorkflowState) -> dict:
        started = time.perf_counter()
        outcome = self.groq_extractor.extract(
            state["documents"],  # type: ignore[arg-type]
            state["pages_by_document"],  # type: ignore[arg-type]
        )
        warnings = [
            *state.get("processing_warnings", []),
            *[f"groq: {warning}" for warning in outcome.warnings],
        ]
        update = {
            "candidates": [*state.get("candidates", []), *outcome.candidates],
            "processing_warnings": warnings,
            "groq_rejected_fields": outcome.rejected_fields,
            "groq_provider": outcome.provider,
            "groq_fallback_used": outcome.fallback_used,
        }
        return update | _node_update(
            state,
            "groq_extract",
            f"{len(outcome.candidates)} candidates, {len(outcome.rejected_fields)} rejected",
            started,
            status="skipped" if not self.groq_extractor.enabled else "passed",
            event_type="document_pack_groq_extracted",
            event_payload={
                "candidate_count": len(outcome.candidates),
                "rejected_count": len(outcome.rejected_fields),
                "provider": outcome.provider,
                "fallback_used": outcome.fallback_used,
                "chunk_count": len(outcome.chunks),
            },
        )

    def consolidate(self, state: DocumentPackWorkflowState) -> dict:
        started = time.perf_counter()
        spec = ProjectDesignSpec.model_validate(
            consolidate_candidates(
                state["pack_id"],
                state["documents"],  # type: ignore[arg-type]
                state["candidates"],  # type: ignore[arg-type]
                processing_capabilities=state["tool_status"],
                processing_warnings=state.get("processing_warnings", []),
                groq_rejected_fields=state.get("groq_rejected_fields", []),
                llm_provider=state.get("groq_provider"),
                llm_fallback_used=state.get("groq_fallback_used"),
            )
        )
        summary = _summary(spec, correction_count=0)
        return {"spec": spec, "summary": summary} | _node_update(
            state,
            "consolidate",
            f"{spec.confidence_summary.get('confirmed_field_count', 0)} confirmed fields",
            started,
            event_type="document_pack_consolidated",
            event_payload={
                "source_mode": spec.source_mode,
                "missing_fields": len(spec.missing_fields),
                "conflicts": len(spec.conflicts),
            },
        )

    def qa(self, state: DocumentPackWorkflowState) -> dict:
        started = time.perf_counter()
        qa_report = _qa_report(state["spec"])  # type: ignore[arg-type]
        return {"qa_report": qa_report} | _node_update(
            state,
            "qa",
            qa_report.status,
            started,
            status=qa_report.status,
            event_type="document_pack_qa_completed",
            event_payload={
                "status": qa_report.status,
                "score": qa_report.score,
                "ready_to_generate": qa_report.ready_to_generate,
            },
        )

    def write_artifacts(self, state: DocumentPackWorkflowState) -> dict:
        started = time.perf_counter()
        pack_dir = Path(state["pack_dir"])  # type: ignore[arg-type]
        spec = state["spec"]  # type: ignore[assignment]
        summary = state["summary"]  # type: ignore[assignment]
        capabilities = state["capabilities"]  # type: ignore[assignment]
        _write_json(pack_dir / "index.json", [doc.model_dump() for doc in state["documents"]])
        _write_json(
            pack_dir / "extractions.json",
            [_candidate_json(candidate) for candidate in state["candidates"]],
        )
        _write_json(pack_dir / "consolidated_spec.json", spec.model_dump())
        _write_json(pack_dir / "summary.json", summary.model_dump())
        _write_json(pack_dir / "corrections.json", [])
        _write_json(pack_dir / "qa_report.json", state["qa_report"].model_dump())
        _write_json(
            pack_dir / "source.json",
            {
                "filename": state.get("filename"),
                "stored_original_zip": False,
                "capabilities": capabilities.model_dump(),
                "tool_status": state["tool_status"],
            },
        )
        _write_json(pack_dir / "processing_report.json", _processing_report(spec, capabilities))
        _write_json(pack_dir / "memory_summary.json", _memory_summary(spec, summary))
        _write_json(pack_dir / "trace.json", state.get("trace", []))
        _write_json(pack_dir / "events.json", state.get("events", []))
        return _node_update(
            state,
            "write_artifacts",
            "document pack artifacts written",
            started,
            event_type="document_pack_artifacts_written",
            event_payload={"artifact_count": 9},
        )

    def memory_writeback(self, state: DocumentPackWorkflowState) -> dict:
        started = time.perf_counter()
        if self.memory_service is None:
            writeback = {"status": "skipped", "reason": "memory_service_not_configured"}
        else:
            try:
                writeback = self.memory_service.write_document_pack_summary(
                    spec=state["spec"],  # type: ignore[arg-type]
                    summary=state["summary"],  # type: ignore[arg-type]
                    qa_report=state["qa_report"],  # type: ignore[arg-type]
                    corrections=[],
                    generated_workflow_id=None,
                )
            except Exception as exc:
                writeback = {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
        pack_dir = Path(state["pack_dir"])  # type: ignore[arg-type]
        qa_report = state["qa_report"].model_copy(update={"memory_writeback": writeback})
        summary = state["summary"].model_copy(update={"memory_summary_available": True})
        _write_json(pack_dir / "qa_report.json", qa_report.model_dump())
        _write_json(pack_dir / "summary.json", summary.model_dump())
        _write_json(pack_dir / "memory_summary.json", _memory_summary(state["spec"], summary))
        _write_json(
            pack_dir / "processing_report.json",
            _processing_report(state["spec"], state["capabilities"], memory_writeback=writeback),
        )
        update = {"qa_report": qa_report, "summary": summary, "memory_writeback": writeback}
        node_update = _node_update(
            state,
            "memory_writeback",
            writeback.get("status", "unknown"),
            started,
            status="failed" if writeback.get("status") == "failed" else "passed",
            event_type="document_pack_memory_writeback",
            event_payload=writeback,
        )
        _write_json(pack_dir / "trace.json", node_update["trace"])
        _write_json(pack_dir / "events.json", node_update["events"])
        return update | node_update

    def list_packs(self) -> list[dict]:
        if not self.packs_dir.exists():
            return []
        packs = []
        for pack_dir in sorted(
            self.packs_dir.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True
        ):
            summary_path = pack_dir / "summary.json"
            if summary_path.exists():
                packs.append(self.get_summary(pack_dir.name))
        return packs

    def get_summary(self, pack_id: str) -> dict:
        pack_dir = self._pack_dir(pack_id)
        persisted = DocumentPackSummary.model_validate(_read_json(pack_dir / "summary.json"))
        qa_report, _mapping, ready = _evaluate_generation_readiness(self.get_spec(pack_id))
        return persisted.model_copy(
            update={
                "can_generate_design": ready,
                "qa_score": qa_report.score,
                "missing_blocking_count": len(qa_report.blocking_issues),
                "blocking_fields": qa_report.blocking_issues,
            }
        ).model_dump()

    def get_documents(self, pack_id: str) -> list[dict]:
        return _read_json(self._pack_dir(pack_id) / "index.json")

    def get_extractions(self, pack_id: str) -> list[dict]:
        return _read_json(self._pack_dir(pack_id) / "extractions.json")

    def get_spec(self, pack_id: str) -> ProjectDesignSpec:
        return ProjectDesignSpec.model_validate(
            _read_json(self._pack_dir(pack_id) / "consolidated_spec.json")
        )

    def get_conflicts(self, pack_id: str) -> list[dict]:
        return [field.model_dump() for field in self.get_spec(pack_id).conflicts]

    def get_missing_fields(self, pack_id: str) -> list[dict]:
        return [field.model_dump() for field in self.get_spec(pack_id).missing_fields]

    def get_provenance(self, pack_id: str) -> dict:
        return {
            field: [source.model_dump() for source in sources]
            for field, sources in self.get_spec(pack_id).provenance_map.items()
        }

    def get_qa_report(self, pack_id: str) -> dict:
        pack_dir = self._pack_dir(pack_id)
        persisted = DocumentPackQAReport.model_validate(_read_json(pack_dir / "qa_report.json"))
        qa_report, _mapping, _ready = _evaluate_generation_readiness(self.get_spec(pack_id))
        return qa_report.model_copy(
            update={"memory_writeback": persisted.memory_writeback}
        ).model_dump()

    def get_processing_report(self, pack_id: str) -> dict:
        return _read_json(self._pack_dir(pack_id) / "processing_report.json")

    def get_memory_summary(self, pack_id: str) -> dict:
        payload = _read_json(self._pack_dir(pack_id) / "memory_summary.json")
        payload["can_generate_design"] = self.get_summary(pack_id)["can_generate_design"]
        return payload

    def get_generation_readiness(
        self,
        pack_id: str,
    ) -> tuple[ProjectDesignSpec, DocumentPackQAReport, RequirementMappingResult, bool]:
        spec = self.get_spec(pack_id)
        qa_report, mapping, ready = _evaluate_generation_readiness(spec)
        return spec, qa_report, mapping, ready

    def apply_correction(
        self,
        pack_id: str,
        correction: DocumentPackCorrection,
    ) -> DocumentPackSummary:
        pack_dir = self._pack_dir(pack_id)
        corrections = _read_json(pack_dir / "corrections.json")
        corrections.append(correction.model_dump())
        documents = _read_json(pack_dir / "index.json")
        candidates = _load_candidates(pack_dir / "extractions.json")
        candidates.extend(_correction_candidates(corrections))
        current_spec = self.get_spec(pack_id)
        spec = ProjectDesignSpec.model_validate(
            consolidate_candidates(
                pack_id,
                documents,
                candidates,
                processing_capabilities=current_spec.processing_capabilities,
                processing_warnings=current_spec.processing_warnings,
                groq_rejected_fields=current_spec.groq_rejected_fields,
                llm_provider=current_spec.llm_provider,
                llm_fallback_used=current_spec.llm_fallback_used,
            )
        )
        summary = _summary(spec, correction_count=len(corrections))
        qa_report = _qa_report(spec)
        memory_writeback = self._write_document_memory(
            spec=spec,
            summary=summary,
            qa_report=qa_report,
            corrections=corrections,
            generated_workflow_id=None,
        )
        qa_report = qa_report.model_copy(update={"memory_writeback": memory_writeback})
        _write_json(pack_dir / "corrections.json", corrections)
        _write_json(pack_dir / "consolidated_spec.json", spec.model_dump())
        _write_json(pack_dir / "summary.json", summary.model_dump())
        _write_json(pack_dir / "qa_report.json", qa_report.model_dump())
        _write_json(
            pack_dir / "processing_report.json",
            _processing_report(spec, self.capabilities(), memory_writeback=memory_writeback),
        )
        _write_json(pack_dir / "memory_summary.json", _memory_summary(spec, summary))
        _append_document_pack_event(
            pack_dir,
            pack_id=pack_id,
            event_type="document_pack_corrected",
            node="correction",
            detail=correction.field,
            payload={
                "field": correction.field,
                "correction_count": len(corrections),
                "can_generate_design": summary.can_generate_design,
            },
        )
        return summary

    def get_trace(self, pack_id: str) -> list[dict]:
        return _read_json(self._pack_dir(pack_id) / "trace.json")

    def get_events(self, pack_id: str) -> list[dict]:
        events = _read_json(self._pack_dir(pack_id) / "events.json")
        if not isinstance(events, list):
            return []
        return [
            _public_document_pack_event(pack_id, event, index)
            for index, event in enumerate(events)
            if isinstance(event, dict)
        ]

    def mark_generated_workflow(self, pack_id: str, workflow_id: str) -> dict:
        pack_dir = self._pack_dir(pack_id)
        spec = self.get_spec(pack_id)
        summary = DocumentPackSummary.model_validate(_read_json(pack_dir / "summary.json"))
        qa_report = DocumentPackQAReport.model_validate(_read_json(pack_dir / "qa_report.json"))
        corrections = _read_json(pack_dir / "corrections.json")
        memory_writeback = self._write_document_memory(
            spec=spec,
            summary=summary,
            qa_report=qa_report,
            corrections=corrections,
            generated_workflow_id=workflow_id,
        )
        _write_json(
            pack_dir / "processing_report.json",
            _processing_report(spec, self.capabilities(), memory_writeback=memory_writeback),
        )
        _write_json(
            pack_dir / "qa_report.json",
            qa_report.model_copy(update={"memory_writeback": memory_writeback}).model_dump(),
        )
        _append_document_pack_event(
            pack_dir,
            pack_id=pack_id,
            event_type="document_pack_design_generation_started",
            node="generate_design",
            detail=workflow_id,
            payload={"workflow_id": workflow_id},
        )
        return memory_writeback

    def _write_document_memory(
        self,
        *,
        spec: ProjectDesignSpec,
        summary: DocumentPackSummary,
        qa_report: DocumentPackQAReport,
        corrections: list[dict],
        generated_workflow_id: str | None,
    ) -> dict:
        if self.memory_service is None:
            return {"status": "skipped", "reason": "memory_service_not_configured"}
        try:
            return self.memory_service.write_document_pack_summary(
                spec=spec,
                summary=summary,
                qa_report=qa_report,
                corrections=corrections,
                generated_workflow_id=generated_workflow_id,
            )
        except Exception as exc:
            return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    def _pack_dir(self, pack_id: str) -> Path:
        pack_dir = self.packs_dir / pack_id
        if not pack_dir.exists():
            raise KeyError(pack_id)
        return pack_dir


def _summary(spec: ProjectDesignSpec, correction_count: int) -> DocumentPackSummary:
    cad_status: dict[str, int] = {}
    for document in spec.document_references:
        cad_status[document.cad_status] = cad_status.get(document.cad_status, 0) + 1
    qa, _mapping, ready = _evaluate_generation_readiness(spec)
    return DocumentPackSummary(
        pack_id=spec.pack_id,
        status="processed",
        document_count=len(spec.document_references),
        high_priority_count=sum(1 for doc in spec.document_references if doc.priority == "high"),
        missing_blocking_count=len(qa.blocking_issues),
        blocking_fields=qa.blocking_issues,
        conflict_count=len(spec.conflicts),
        can_generate_design=ready,
        cad_status=cad_status,
        qa_score=qa.score,
        correction_count=correction_count,
        processing_warning_count=len(spec.processing_warnings),
        tool_status=spec.processing_capabilities,
        memory_summary_available=True,
    )


def _qa_report(
    spec: ProjectDesignSpec,
    mapping: RequirementMappingResult | None = None,
) -> DocumentPackQAReport:
    mapping = mapping or ProjectDesignSpecMapper().map_to_requirements(spec)
    checks = [
        DocumentPackQACheck(
            name="critical_fields_have_sources",
            passed=_critical_fields_have_sources(spec),
            reason="Confirmed critical fields must include source evidence.",
        ),
        DocumentPackQACheck(
            name="no_blocking_missing_fields",
            passed=not [field for field in spec.missing_fields if field.severity == "blocking"],
            reason="Blocking missing fields prevent pack-to-design mapping.",
        ),
        DocumentPackQACheck(
            name="conflicts_resolved",
            passed=not spec.conflicts,
            reason="Unresolved conflicts require user review or correction.",
        ),
        DocumentPackQACheck(
            name="average_confidence_reasonable",
            passed=float(spec.confidence_summary.get("average_confidence", 0.0)) >= 0.65,
            reason="Average extracted-field confidence should be at least 0.65 for MVP mapping.",
        ),
        DocumentPackQACheck(
            name="useful_documents_present",
            passed=any(doc.used_for_design for doc in spec.document_references),
            reason="At least one high/medium priority document should support the design.",
        ),
        DocumentPackQACheck(
            name="numeric_values_plausible",
            passed=_numeric_values_plausible(spec),
            reason="Tower height, HBA, and azimuth values must be in plausible ranges.",
        ),
        DocumentPackQACheck(
            name="no_confirmed_field_without_evidence",
            passed=_no_confirmed_field_without_evidence(spec),
            reason="No confirmed field may be accepted without provenance.",
        ),
        DocumentPackQACheck(
            name="processing_limits_visible",
            passed=_processing_limits_visible(spec),
            reason="Unsupported or unavailable OCR/PDF/CAD processing must be visible.",
        ),
        DocumentPackQACheck(
            name="coordinate_conversion_status_visible",
            passed=_coordinate_conversion_status_visible(spec),
            reason=(
                "Coordinate conversion must be confirmed, unavailable, or unsupported explicitly."
            ),
        ),
        DocumentPackQACheck(
            name="hba_not_above_tower_height",
            passed=_hba_not_above_tower_height(spec),
            reason="Antenna HBA cannot exceed the extracted tower height.",
        ),
        DocumentPackQACheck(
            name="sector_count_matches_azimuths",
            passed=_sector_count_matches_azimuths(spec),
            reason="Sector count must match the number of extracted azimuths.",
        ),
        DocumentPackQACheck(
            name="selected_ocr_documents_handled",
            passed=_selected_ocr_documents_handled(spec),
            reason="High-value scanned PDFs/images must be OCR processed or expose OCR limits.",
        ),
        DocumentPackQACheck(
            name="groq_fields_have_valid_evidence",
            passed=not spec.groq_rejected_fields,
            reason="Groq fields without valid document/page/evidence must be rejected visibly.",
        ),
        DocumentPackQACheck(
            name="requirements_mapping_representable",
            passed=mapping.status == "mapped",
            reason=(
                "Document values must map to RequirementSpec without flattening sector values "
                "or inventing a radio network type."
            ),
        ),
    ]
    passed_count = sum(1 for check in checks if check.passed)
    score = round(passed_count / len(checks), 3)
    status = "passed" if score == 1 else "warning" if score >= 0.7 else "failed"
    warnings = [check.name for check in checks if not check.passed]
    blocking = list(
        dict.fromkeys(
            [
                *(field.field for field in spec.missing_fields if field.severity == "blocking"),
                *(field.field for field in spec.conflicts),
                *mapping.blocking_fields,
            ]
        )
    )
    return DocumentPackQAReport(
        pack_id=spec.pack_id,
        status=status,
        score=score,
        checks=checks,
        warnings=warnings,
        blocking_issues=blocking,
        ready_to_generate=not blocking and status != "failed" and mapping.status == "mapped",
        ready_confidence=score if not blocking else min(score, 0.49),
        recommended_user_actions=_recommended_user_actions(spec, warnings, mapping),
        tool_failures=_tool_failures(spec),
    )


def _evaluate_generation_readiness(
    spec: ProjectDesignSpec,
) -> tuple[DocumentPackQAReport, RequirementMappingResult, bool]:
    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)
    qa_report = _qa_report(spec, mapping)
    ready = qa_report.ready_to_generate and mapping.status == "mapped"
    return qa_report, mapping, ready


def _unsafe_zip_path(path: str) -> bool:
    candidate = Path(path)
    return candidate.is_absolute() or ".." in candidate.parts


def _validate_zip_archive(content: bytes) -> None:
    if len(content) > MAX_PACK_SIZE_BYTES:
        raise ValueError("document pack exceeds the 80 MB compressed size limit")
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid ZIP archive") from exc
    if not infos:
        raise ValueError("document pack ZIP contains no files")
    if len(infos) > MAX_MEMBER_COUNT:
        raise ValueError(f"document pack exceeds the {MAX_MEMBER_COUNT} file limit")
    unsafe_paths = [info.filename for info in infos if _unsafe_zip_path(info.filename)]
    if unsafe_paths:
        raise ValueError("document pack contains an unsafe ZIP member path")
    encrypted = [info.filename for info in infos if info.flag_bits & 0x1]
    if encrypted:
        raise ValueError("encrypted ZIP members are not supported")
    oversized = [info.filename for info in infos if info.file_size > MAX_MEMBER_SIZE_BYTES]
    if oversized:
        raise ValueError("document pack contains a file exceeding the 15 MB member limit")
    total_uncompressed = sum(info.file_size for info in infos)
    if total_uncompressed > MAX_UNCOMPRESSED_SIZE_BYTES:
        raise ValueError("document pack exceeds the 200 MB uncompressed size limit")


def _combined_extraction_status(
    text_status: DocumentExtractionStatus,
    cad_status: DocumentExtractionStatus,
    extractability: str,
) -> DocumentExtractionStatus:
    if text_status == "extracted" or cad_status == "extracted":
        return "extracted"
    if extractability == "cad":
        return cad_status
    if text_status != "not_attempted":
        return text_status
    return cad_status


def _node_update(
    state: DocumentPackWorkflowState,
    node: str,
    detail: str,
    started: float,
    *,
    status: str = "passed",
    event_type: str,
    event_payload: dict,
) -> dict:
    duration_ms = round((time.perf_counter() - started) * 1000)
    event_payload = _normalized_document_pack_event_payload(
        node=node,
        status=status,
        detail=detail,
        duration_ms=duration_ms,
        payload=event_payload,
    )
    trace = state.get("trace", []) + [
        {
            "node": node,
            "status": status,
            "detail": detail,
            "duration_ms": duration_ms,
        }
    ]
    events = state.get("events", []) + [
        {
            "event_id": f"evt_pack_{uuid.uuid4().hex[:12]}",
            "pack_id": state["pack_id"],
            "event_type": event_type,
            "event_source": "document_pack_json",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "node": node,
            "status": status,
            "duration_ms": duration_ms,
            "payload": event_payload,
        }
    ]
    return {"trace": trace, "events": events}


def _append_document_pack_event(
    pack_dir: Path,
    *,
    pack_id: str,
    event_type: str,
    node: str,
    detail: str,
    payload: dict,
    status: str = "passed",
) -> None:
    events_path = pack_dir / "events.json"
    try:
        events = _read_json(events_path)
        if not isinstance(events, list):
            events = []
    except (OSError, json.JSONDecodeError):
        events = []
    event_payload = _normalized_document_pack_event_payload(
        node=node,
        status=status,
        detail=detail,
        duration_ms=0,
        payload=payload,
    )
    events.append(
        {
            "event_id": f"evt_pack_{uuid.uuid4().hex[:12]}",
            "pack_id": pack_id,
            "event_type": event_type,
            "event_source": "document_pack_json",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "node": node,
            "status": status,
            "duration_ms": 0,
            "payload": event_payload,
        }
    )
    _write_json(events_path, events)


def _public_document_pack_event(pack_id: str, event: dict, index: int) -> dict:
    raw_payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    node = str(event.get("node") or raw_payload.get("node") or "documents")
    status = str(event.get("status") or raw_payload.get("status") or "passed")
    detail = str(raw_payload.get("detail") or event.get("detail") or node)
    duration_ms = int(event.get("duration_ms") or raw_payload.get("duration_ms") or 0)
    payload = _normalized_document_pack_event_payload(
        node=node,
        status=status,
        detail=detail,
        duration_ms=duration_ms,
        payload=raw_payload,
    )
    return {
        **event,
        "event_id": event.get("event_id") or f"evt_pack_legacy_{index:04d}",
        "pack_id": event.get("pack_id") or pack_id,
        "event_source": event.get("event_source") or "document_pack_json",
        "timestamp": event.get("timestamp") or "1970-01-01T00:00:00Z",
        "node": node,
        "status": status,
        "duration_ms": duration_ms,
        "payload": payload,
    }


def _normalized_document_pack_event_payload(
    *,
    node: str,
    status: str,
    detail: str,
    duration_ms: int,
    payload: dict,
) -> dict:
    normalized = dict(payload)
    normalized.setdefault("node", node)
    normalized.setdefault("phase", _document_pack_phase(node))
    normalized.setdefault("status", status)
    normalized.setdefault("detail", detail)
    normalized.setdefault("duration_ms", duration_ms)
    normalized.setdefault("warnings", [])
    normalized.setdefault("errors", [])
    normalized.setdefault("artifact_refs", [])
    normalized.setdefault("human_label", _document_pack_human_label(node))
    normalized.setdefault(
        "progress_message",
        _document_pack_progress_message(node, status, detail),
    )
    return normalized


def _document_pack_phase(node: str) -> str:
    return {
        "index": "documents",
        "extract_pdf_ocr_cad": "extraction",
        "groq_extract": "extraction",
        "consolidate": "consolidation",
        "qa": "qa",
        "write_artifacts": "artifacts",
        "memory_writeback": "memory",
        "correction": "correction",
        "generate_design": "generation",
    }.get(node, "documents")


def _document_pack_human_label(node: str) -> str:
    return {
        "index": "Inventaire du pack documentaire",
        "extract_pdf_ocr_cad": "Extraction PDF/OCR/CAD",
        "groq_extract": "Extraction structurée Groq",
        "consolidate": "Consolidation des exigences",
        "qa": "Validation du pack documentaire",
        "write_artifacts": "Écriture des artefacts documentaires",
        "memory_writeback": "Écriture mémoire documentaire",
        "correction": "Correction utilisateur",
        "generate_design": "Lancement de la génération 3D",
    }.get(node, node.replace("_", " ").capitalize())


def _document_pack_progress_message(node: str, status: str, detail: str) -> str:
    if status == "failed":
        return f"Échec pendant : {_document_pack_human_label(node)}."
    return f"{_document_pack_human_label(node)} : {detail}."


def _processing_report(
    spec: ProjectDesignSpec,
    capabilities: DocumentPackCapabilities,
    memory_writeback: dict | None = None,
) -> dict:
    return {
        "pack_id": spec.pack_id,
        "capabilities": capabilities.model_dump(),
        "tool_status": capabilities.status_map(),
        "source_mode": spec.source_mode,
        "llm_provider": spec.llm_provider,
        "llm_fallback_used": spec.llm_fallback_used,
        "groq_rejected_fields": spec.groq_rejected_fields,
        "memory_writeback": memory_writeback or {},
        "documents": [
            {
                "document_id": document.document_id,
                "path": document.path,
                "extension": document.extension,
                "category": document.category,
                "extractability": document.extractability,
                "extraction_status": document.extraction_status,
                "cad_status": document.cad_status,
                "processing_tools": document.processing_tools,
                "processing_warnings": document.processing_warnings,
            }
            for document in spec.document_references
        ],
        "warnings": spec.processing_warnings,
    }


def _memory_summary(spec: ProjectDesignSpec, summary: DocumentPackSummary) -> dict:
    tower_type = spec.tower_spec.get("tower_type")
    tower_height = spec.tower_spec.get("tower_height_m")
    azimuths = [
        sector.azimuth_deg.value
        for sector in spec.radio_sectors
        if sector.azimuth_deg.status == "confirmed"
    ]
    hba_values = [
        sector.hba_m.value for sector in spec.radio_sectors if sector.hba_m.status == "confirmed"
    ]
    return {
        "type": "document_pack_memory_summary",
        "pack_id": spec.pack_id,
        "can_generate_design": summary.can_generate_design,
        "qa_score": summary.qa_score,
        "correction_count": summary.correction_count,
        "source_mode": spec.source_mode,
        "tower_type": tower_type.value if tower_type else None,
        "tower_height_m": tower_height.value if tower_height else None,
        "sector_count": len(spec.radio_sectors),
        "azimuths_deg": azimuths,
        "hba_m": hba_values,
        "missing_fields": [field.field for field in spec.missing_fields],
        "conflicts": [field.field for field in spec.conflicts],
        "document_categories": _category_counts(spec),
        "processing_capabilities": spec.processing_capabilities,
        "processing_warning_count": summary.processing_warning_count,
    }


def _category_counts(spec: ProjectDesignSpec) -> dict[str, int]:
    counts: dict[str, int] = {}
    for document in spec.document_references:
        counts[document.category] = counts.get(document.category, 0) + 1
    return counts


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path):
    if not path.exists():
        raise KeyError(path.name)
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_json(candidate) -> dict:
    return {
        "field": candidate.field,
        "value": candidate.value,
        "confidence": candidate.confidence,
        "source": candidate.source.model_dump(),
    }


def _load_candidates(path: Path) -> list[FieldCandidate]:
    return [
        FieldCandidate(
            field=payload["field"],
            value=payload["value"],
            confidence=payload["confidence"],
            source=SourceEvidence.model_validate(payload["source"]),
        )
        for payload in _read_json(path)
    ]


def _correction_candidates(corrections: list[dict]) -> list[FieldCandidate]:
    candidates = []
    for payload in corrections:
        correction = DocumentPackCorrection.model_validate(payload)
        candidates.append(
            FieldCandidate(
                field=correction.field,
                value=correction.value,
                confidence=correction.confidence,
                source=SourceEvidence(
                    document_id="user_correction",
                    file="user_correction",
                    source_type="user_correction",
                    confidence=correction.confidence,
                    evidence=(
                        f"{correction.corrected_by} corrected {correction.field}: "
                        f"{correction.reason}"
                    ),
                ),
            )
        )
    return candidates


def _critical_fields_have_sources(spec: ProjectDesignSpec) -> bool:
    critical_fields = [
        spec.tower_spec.get("tower_type"),
        spec.tower_spec.get("tower_height_m"),
        *[sector.azimuth_deg for sector in spec.radio_sectors],
        *[sector.hba_m for sector in spec.radio_sectors],
    ]
    return all(
        field is not None and field.status == "confirmed" and bool(field.sources)
        for field in critical_fields
    )


def _numeric_values_plausible(spec: ProjectDesignSpec) -> bool:
    tower_height = spec.tower_spec.get("tower_height_m")
    if tower_height and isinstance(tower_height.value, float | int):
        if not 3 <= float(tower_height.value) <= 150:
            return False
    for sector in spec.radio_sectors:
        azimuth = sector.azimuth_deg.value
        hba = sector.hba_m.value
        if not isinstance(azimuth, float | int) or not 0 <= float(azimuth) < 360:
            return False
        if not isinstance(hba, float | int) or not 0 < float(hba) <= 150:
            return False
    return True


def _processing_limits_visible(spec: ProjectDesignSpec) -> bool:
    for document in spec.document_references:
        if document.duplicate_of:
            continue
        requires_visible_limit = document.extractability in {"cad", "image"} or (
            document.extension == "pdf" and document.extraction_status != "extracted"
        )
        if requires_visible_limit and not document.processing_warnings:
            return False
        if (
            document.extraction_status == "not_attempted"
            and document.extractability != "unsupported"
        ):
            return False
    return True


def _coordinate_conversion_status_visible(spec: ProjectDesignSpec) -> bool:
    coordinate_keys = {
        key
        for key in spec.coordinate_info
        if key not in {"altitude_m", "z", "conversion_available", "conversion_status"}
    }
    if not coordinate_keys:
        return True
    status = spec.coordinate_info.get("conversion_status")
    available = spec.coordinate_info.get("conversion_available")
    return bool(
        status
        and status.status == "confirmed"
        and available
        and available.status == "confirmed"
        and available.sources
    )


def _hba_not_above_tower_height(spec: ProjectDesignSpec) -> bool:
    tower_height = spec.tower_spec.get("tower_height_m")
    if not tower_height or not isinstance(tower_height.value, float | int):
        return True
    height = float(tower_height.value)
    for sector in spec.radio_sectors:
        hba = sector.hba_m.value
        if isinstance(hba, float | int) and float(hba) > height:
            return False
    return True


def _sector_count_matches_azimuths(spec: ProjectDesignSpec) -> bool:
    radio_sector_count = len(spec.radio_sectors)
    azimuths = [
        sector.azimuth_deg.value
        for sector in spec.radio_sectors
        if sector.azimuth_deg.status == "confirmed"
    ]
    if radio_sector_count == 0:
        return not any(field.field == "radio.azimuths_deg" for field in spec.conflicts)
    if len(azimuths) != radio_sector_count:
        return False
    return True


def _selected_ocr_documents_handled(spec: ProjectDesignSpec) -> bool:
    ocr_available = spec.processing_capabilities.get("ocr") == "available"
    for document in spec.document_references:
        if document.priority not in {"high", "medium"} or document.duplicate_of:
            continue
        scanned_candidate = document.extension in {"pdf", "jpg", "jpeg", "png", "webp"}
        if not scanned_candidate:
            continue
        if document.extraction_status == "extracted":
            continue
        if ocr_available:
            has_ocr_warning = any(
                "OCR" in warning or "ocr" in warning.lower()
                for warning in document.processing_warnings
            )
            if not has_ocr_warning:
                return False
        elif not document.processing_warnings:
            return False
    return True


def _tool_failures(spec: ProjectDesignSpec) -> list[str]:
    failures: list[str] = []
    for document in spec.document_references:
        for warning in document.processing_warnings:
            lowered = warning.lower()
            if any(token in lowered for token in ["failed", "unavailable", "missing"]):
                failures.append(f"{document.path}: {warning}")
    for field in spec.groq_rejected_fields:
        failures.append(f"groq_rejected:{field.get('field')}:{field.get('reason')}")
    return failures


def _recommended_user_actions(
    spec: ProjectDesignSpec,
    warnings: list[str],
    mapping: RequirementMappingResult,
) -> list[str]:
    actions: list[str] = []
    blocking_missing = [
        field.field for field in spec.missing_fields if field.severity == "blocking"
    ]
    if blocking_missing:
        actions.append("Corriger ou ajouter les champs bloquants: " + ", ".join(blocking_missing))
    if spec.conflicts:
        actions.append(
            "Résoudre les conflits avant génération: "
            + ", ".join(field.field for field in spec.conflicts)
        )
    if "selected_ocr_documents_handled" in warnings:
        actions.append(
            "Vérifier les documents scannés ou fournir une version PDF texte/OCR lisible."
        )
    if "groq_fields_have_valid_evidence" in warnings:
        actions.append("Revoir les champs Groq rejetés; aucun champ sans preuve n'est accepté.")
    if "hba_not_above_tower_height" in warnings:
        actions.append(
            "Corriger HBA ou hauteur pylône: HBA ne peut pas dépasser la hauteur pylône."
        )
    if "radio.network_type" in mapping.blocking_fields:
        actions.append(
            "Confirmer un type radio supporté (4G, 5G ou MW) avec une preuve documentaire."
        )
    if "foundation.foundation_type" in mapping.blocking_fields:
        actions.append("Confirmer une fondation compatible avec le support avant la génération 3D.")
    sector_fields = [
        field
        for field in mapping.blocking_fields
        if field
        in {
            "radio.hba_m",
            "radio.mechanical_tilt_deg",
            "radio.electrical_tilt_deg",
        }
    ]
    if sector_fields:
        actions.append(
            "Les valeurs sectorielles suivantes diffèrent ou sont partielles et ne peuvent pas "
            "être aplaties sans perte: " + ", ".join(sector_fields)
        )
    return actions


def _no_confirmed_field_without_evidence(spec: ProjectDesignSpec) -> bool:
    fields = []
    fields.extend(spec.site_info.values())
    fields.extend(spec.coordinate_info.values())
    fields.extend(spec.tower_spec.values())
    fields.extend(spec.foundation_spec.values())
    fields.extend(spec.cabling_spec.values())
    fields.extend(spec.grounding_spec.values())
    fields.extend(spec.compound_spec.values())
    for sector in spec.radio_sectors:
        fields.extend(
            [
                sector.azimuth_deg,
                sector.hba_m,
                sector.antenna_model,
                sector.bands,
                sector.mechanical_tilt_deg,
                sector.electrical_tilt_deg,
                sector.rru,
            ]
        )
    return all(
        field is None or field.status != "confirmed" or bool(field.sources) for field in fields
    )
