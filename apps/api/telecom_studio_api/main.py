import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from apps.api.telecom_studio_api.config import settings
from apps.api.telecom_studio_api.models import (
    AssetInventoryResponse,
    AssetLibraryProbeResponse,
    AssetLibrarySearchResponse,
    AssetLibrarySummaryResponse,
    CreateDesignRequest,
    CreateDesignResponse,
    CurrentOperation,
    DesignListSummary,
    DocumentPackCapabilitiesView,
    DocumentPackGenerateDesignResponse,
    EditDesignRequest,
    EditDesignResponse,
    ParseRequirementsRequest,
    ParseRequirementsResponse,
    PublicVersionInfo,
    RagSearchResponse,
    RollbackVersionResponse,
    StudioSummary,
    TimelineSummary,
    UserIssuesResponse,
    UserSummary,
    ViewerBundle,
    WorkflowEventView,
    WorkflowStatus,
)
from apps.api.telecom_studio_api.product import ProductNotFound, ProductService
from apps.api.telecom_studio_api.workflow import (
    WorkflowBusyError,
    WorkflowService,
    WorkflowStorageError,
)
from core.agents.requirement_extractor import RequirementExtractor
from core.agents.scene_edit_agent import SceneEditAgent
from core.contracts.document_pack import DocumentPackCorrection
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationReport
from core.document_pack import DocumentPackService
from core.llm import GroqStructuredClient
from core.llm.planning_decision import GroqPlanningDecisionClient
from core.memory import MemoryService
from core.orchestration import DesignOrchestrator
from core.performance import requirements_hash as compute_requirements_hash
from core.rag import RagService
from core.rag.embeddings import build_embedding_provider
from core.rag.reranker import build_reranker
from core.rag.service import RagIndexCompatibilityError
from core.services.asset_inventory import AssetInventoryService
from core.services.asset_library import AssetLibraryError, AssetLibraryNotFound, AssetLibraryService
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner
from core.services.checkpoint_saver import SqliteCheckpointSaver


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        workflow_service.reconcile_interrupted_workflows()
        yield
    finally:
        workflow_service.shutdown()
        rag_service.close()


app = FastAPI(
    title="Agentic AI 3D Telecom Design Studio",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.resolved_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": request_id,
            "type": type(exc).__name__,
        },
        headers={"x-request-id": request_id},
    )


registry = AssetRegistry(settings.manifests_dir)
asset_inventory_service = AssetInventoryService(settings.project_root, registry)
asset_library_service = AssetLibraryService(settings.asset_library_dir)
rag_embedding_provider = build_embedding_provider(
    settings.embedding_provider,
    settings.embedding_model,
    api_key=settings.resolved_nvidia_api_key,
)
rag_reranker = build_reranker(
    settings.reranker_model,
    provider_name=settings.reranker_provider,
    api_key=settings.resolved_nvidia_api_key,
    base_url=settings.reranker_base_url,
)
rag_service = RagService(
    project_root=settings.project_root,
    qdrant_path=settings.local_qdrant_path,
    qdrant_url=settings.qdrant_url,
    embedding_provider=rag_embedding_provider,
    reranker=rag_reranker,
    reranker_provider_name=settings.reranker_provider,
    reranker_model=settings.reranker_model,
    reranker_api_key=settings.resolved_nvidia_api_key,
    reranker_base_url=settings.reranker_base_url,
)
memory_service = MemoryService(settings.local_sqlite_path, rag_service=rag_service)
groq_client = (
    GroqStructuredClient(
        api_key=settings.resolved_groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
    )
    if settings.resolved_groq_api_key
    else None
)
planning_decision_client = (
    GroqPlanningDecisionClient(
        api_key=settings.resolved_groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_s=settings.groq_planning_timeout_s,
        max_completion_tokens=settings.groq_planning_max_completion_tokens,
    )
    if settings.resolved_groq_api_key and settings.enable_groq_planning_decision
    else None
)
document_pack_service = DocumentPackService(
    settings.temp_outputs_dir,
    groq_client=groq_client,
    groq_provider_name=f"groq:{settings.groq_model}" if groq_client else None,
    groq_bounded_extraction_enabled=settings.enable_groq_extraction,
    memory_service=memory_service,
)
requirement_extractor = RequirementExtractor(
    provider=groq_client,
    provider_name=f"groq:{settings.groq_model}",
    enabled=settings.enable_groq_extraction,
)
blender_runner = BlenderRunner(
    project_root=settings.project_root,
    blender_binary=settings.resolved_blender_binary,
    timeout_s=settings.blender_timeout_s,
)
checkpoint_saver = SqliteCheckpointSaver(settings.local_sqlite_path.with_name("checkpoints.db"))
while True:
    checkpoint_retention = checkpoint_saver.enforce_thread_quota(
        settings.checkpoint_retention_threads,
        max_delete=1000,
    )
    if checkpoint_retention.remaining_over_quota == 0:
        break
orchestrator = DesignOrchestrator(
    registry=registry,
    extractor=requirement_extractor,
    rag_service=rag_service,
    memory_service=memory_service,
    blender_runner=blender_runner,
    checkpoint_saver=checkpoint_saver,
    planning_decision_client=planning_decision_client,
    allow_blender_fallback=settings.allow_blender_fallback,
)
scene_edit_agent = SceneEditAgent(groq_client=groq_client)
workflow_service = WorkflowService(
    registry=registry,
    outputs_dir=settings.temp_outputs_dir,
    orchestrator=orchestrator,
    scene_edit_agent=scene_edit_agent,
    max_concurrent_workflows=settings.max_concurrent_workflows,
    max_pending_workflows=settings.max_pending_workflows,
    min_free_disk_mb=settings.min_free_disk_mb,
)
product_service = ProductService(workflow_service, asset_inventory_service)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.2.0"}


@app.get("/studio/summary", response_model=StudioSummary)
def get_studio_summary() -> dict:
    return product_service.studio_summary()


@app.post("/designs", response_model=CreateDesignResponse)
def create_design(request: CreateDesignRequest) -> dict:
    try:
        if request.confirmed_requirements is not None:
            actual_hash = compute_requirements_hash(request.confirmed_requirements)
            if actual_hash != request.confirmed_requirements_hash:
                raise HTTPException(
                    status_code=422,
                    detail="confirmed RequirementSpec hash does not match its payload",
                )
            return workflow_service.create_design_from_requirements(
                request.confirmed_requirements,
                detail_level=request.options.detail_level,
                source_label="confirmed_requirement_spec",
                source_text=request.requirements_text,
            )
        return workflow_service.create_design(
            requirements_text=request.requirements_text,
            detail_level=request.options.detail_level,
            use_llm=request.options.use_llm,
        )
    except WorkflowBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "5"},
        ) from exc
    except WorkflowStorageError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc


@app.get("/designs/{workflow_id}", response_model=WorkflowStatus)
def get_design(workflow_id: str) -> dict:
    try:
        return workflow_service.get_public_status(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc


@app.get("/designs/{workflow_id}/user-summary", response_model=UserSummary)
def get_user_summary(workflow_id: str) -> dict:
    try:
        return product_service.user_summary(workflow_id)
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc


@app.get("/designs/{workflow_id}/current-operation", response_model=CurrentOperation)
def get_current_operation(workflow_id: str) -> dict:
    try:
        return product_service.current_operation(workflow_id)
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc


@app.get("/designs/{workflow_id}/user-issues", response_model=UserIssuesResponse)
def get_user_issues(workflow_id: str) -> dict:
    try:
        return product_service.user_issues(workflow_id)
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc


@app.get("/designs/{workflow_id}/viewer-bundle", response_model=ViewerBundle)
def get_viewer_bundle(workflow_id: str) -> dict:
    try:
        return product_service.viewer_bundle(workflow_id)
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc


@app.get("/designs/{workflow_id}/timeline-summary", response_model=TimelineSummary)
def get_timeline_summary(workflow_id: str) -> dict:
    try:
        return product_service.timeline_summary(workflow_id)
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc


@app.get("/designs/{workflow_id}/download")
def download_design(workflow_id: str) -> FileResponse:
    try:
        path = workflow_service.archive_path(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow artifacts not found") from exc
    return FileResponse(path=path, filename=f"{workflow_id}_artifacts.zip")


@app.get("/designs/{workflow_id}/artifacts/{artifact_name}")
def get_design_artifact(
    workflow_id: str,
    artifact_name: str,
    version_id: str | None = None,
) -> FileResponse:
    try:
        path = workflow_service.artifact_path(workflow_id, artifact_name, version_id=version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    return FileResponse(path=path, filename=path.name)


@app.post("/scene-spec/validate", response_model=ValidationReport)
def validate_scene_spec_endpoint(scene: SceneSpec) -> ValidationReport:
    return workflow_service.validate_scene(scene)


@app.get("/designs", response_model=list[DesignListSummary])
def list_designs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    return workflow_service.list_designs(limit=limit, offset=offset)


@app.delete("/designs/{workflow_id}")
def delete_design(workflow_id: str) -> dict:
    try:
        workflow_service.delete_design(workflow_id)
        return {"workflow_id": workflow_id, "deleted": True}
    except WorkflowBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc


@app.post("/requirements/parse", response_model=ParseRequirementsResponse)
def parse_requirements(request: ParseRequirementsRequest) -> dict:
    result = workflow_service.parse_requirements(
        requirements_text=request.requirements_text,
        detail_level=request.detail_level,
        use_llm=request.use_llm,
    )
    return result


@app.post("/designs/{workflow_id}/edit", response_model=EditDesignResponse)
def edit_design(workflow_id: str, request: EditDesignRequest) -> dict:
    try:
        result = workflow_service.edit_design(workflow_id, request.edit_prompt)
    except WorkflowBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkflowStorageError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    return workflow_service.public_edit_response(result)


@app.get("/designs/{workflow_id}/versions", response_model=list[PublicVersionInfo])
def list_versions(workflow_id: str) -> list[dict]:
    return workflow_service.list_versions_public(workflow_id)


@app.post(
    "/designs/{workflow_id}/versions/{version_id}/rollback",
    response_model=RollbackVersionResponse,
)
def rollback_version(workflow_id: str, version_id: str) -> dict:
    try:
        return workflow_service.rollback_version(workflow_id, version_id)
    except WorkflowBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc


@app.get("/designs/{workflow_id}/events", response_model=list[WorkflowEventView])
def get_events(workflow_id: str) -> list[dict]:
    return workflow_service.get_events(workflow_id)


@app.get("/designs/{workflow_id}/events/stream")
def stream_events(workflow_id: str, after_event_id: str | None = None):
    if not workflow_service.workflow_exists(workflow_id):
        raise HTTPException(status_code=404, detail="workflow not found")

    def event_generator():
        import json

        for event in workflow_service.stream_events(
            workflow_id,
            after_event_id=after_event_id,
        ):
            event_type = event.get("event_type", "workflow_event")
            yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/assets")
def list_assets() -> list[dict]:
    return [asset.model_dump() for asset in registry.list_assets()]


@app.get("/assets/inventory", response_model=AssetInventoryResponse)
def asset_inventory() -> dict:
    return asset_inventory_service.inspect()


@app.get("/assets/library/summary", response_model=AssetLibrarySummaryResponse)
def asset_library_summary() -> dict:
    return asset_library_service.summary()


@app.get("/assets/library/search", response_model=AssetLibrarySearchResponse)
def asset_library_search(
    q: str = Query(min_length=1, max_length=240),
    claimed_dimension: str | None = Query(default=None, pattern="^(2d|3d|unspecified)$"),
    extension: str | None = Query(default=None, min_length=1, max_length=12),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    try:
        return asset_library_service.search(
            q,
            claimed_dimension=claimed_dimension,
            extension=extension,
            limit=limit,
        )
    except AssetLibraryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/assets/library/{file_id}/probe", response_model=AssetLibraryProbeResponse)
def asset_library_probe(file_id: str) -> dict:
    try:
        return asset_library_service.probe(file_id)
    except AssetLibraryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssetLibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/assets/{asset_id}")
def get_asset(asset_id: str) -> dict:
    try:
        return registry.get(asset_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="asset not found") from exc


@app.post("/document-packs")
async def create_document_pack(request: Request) -> dict:
    limits = document_pack_service.archive_limits()
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limits["max_zip_size_bytes"]:
                raise HTTPException(status_code=422, detail="document pack exceeds ZIP size limit")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid content-length header") from exc
    content = await _read_limited_request_body(request, limits["max_zip_size_bytes"])
    if not content:
        raise HTTPException(status_code=422, detail="empty document pack body")
    filename = request.headers.get("x-filename")
    try:
        summary = await run_in_threadpool(
            document_pack_service.ingest_zip,
            content,
            filename=filename,
        )
        return summary.model_dump()
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _read_limited_request_body(request: Request, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=422, detail="document pack exceeds ZIP size limit")
        chunks.append(chunk)
    return b"".join(chunks)


@app.get("/document-packs")
def list_document_packs() -> list[dict]:
    return document_pack_service.list_packs()


@app.get("/document-packs/capabilities", response_model=DocumentPackCapabilitiesView)
def get_document_pack_capabilities() -> dict:
    capabilities = document_pack_service.capabilities()
    archive_limits = document_pack_service.archive_limits()
    payload = capabilities.model_dump()
    status_map = capabilities.status_map()
    available_tools = [
        name
        for name, tool_status in status_map.items()
        if tool_status in {"available", "conversion_available"}
    ]
    disabled_tools = [
        name
        for name, tool_status in status_map.items()
        if tool_status not in {"available", "conversion_available"}
    ]
    payload.update(
        {
            "document_pack_status": "limited",
            "supported_upload_format": "zip",
            "supported_inputs": {
                "upload": "zip",
                "extensions": [
                    ".pdf",
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".tif",
                    ".tiff",
                    ".dxf",
                    ".dwg",
                    ".txt",
                    ".csv",
                    ".xlsx",
                ],
                "notes": [
                    "Les fichiers doivent être groupés dans un ZIP.",
                    "Le traitement est local et synchrone.",
                ],
            },
            "supported_extensions": [
                ".pdf",
                ".png",
                ".jpg",
                ".jpeg",
                ".tif",
                ".tiff",
                ".dxf",
                ".dwg",
                ".txt",
                ".csv",
                ".xlsx",
            ],
            "limits": {
                "max_zip_size_mb": archive_limits["max_zip_size_bytes"] // (1024 * 1024),
                "max_member_size_mb": archive_limits["max_member_size_bytes"] // (1024 * 1024),
                "max_member_count": archive_limits["max_member_count"],
                "max_uncompressed_size_mb": archive_limits["max_uncompressed_size_bytes"]
                // (1024 * 1024),
                "processing_mode": "synchronous_local",
                "execution": "thread_offloaded",
            },
            "max_size": {
                "zip_mb": archive_limits["max_zip_size_bytes"] // (1024 * 1024),
                "member_mb": archive_limits["max_member_size_bytes"] // (1024 * 1024),
                "uncompressed_mb": archive_limits["max_uncompressed_size_bytes"] // (1024 * 1024),
                "member_count": archive_limits["max_member_count"],
            },
            "available_tools": available_tools,
            "disabled_tools": disabled_tools,
            "limitations": [
                "Document-pack est limité et synchrone.",
                "Docling est détecté en import seulement, pas actif par défaut.",
                "OCR dépend de Tesseract et des langues installées localement.",
                "DXF extrait texte/couches ; DWG exige un convertisseur local.",
                "La génération depuis pack peut rester bloquée si des champs essentiels manquent.",
            ],
            "truth": {
                "advanced_ingestion": False,
                "docling_default_enabled": False,
                "ocr_requires_local_tesseract_languages": True,
                "dwg_requires_local_converter": True,
                "processing_mode": "synchronous_local",
                "generation_from_pack": "available_when_qa_ready_and_mapping_mapped",
            },
            "next_action": (
                "Uploader un ZIP de documents techniques, vérifier les champs manquants, "
                "corriger si nécessaire, puis générer le design."
            ),
            "capabilities": payload.copy(),
        }
    )
    return payload


@app.get("/document-packs/{pack_id}")
def get_document_pack(pack_id: str) -> dict:
    try:
        return document_pack_service.get_summary(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/documents")
def get_document_pack_documents(pack_id: str) -> list[dict]:
    try:
        return document_pack_service.get_documents(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/extractions")
def get_document_pack_extractions(pack_id: str) -> list[dict]:
    try:
        return document_pack_service.get_extractions(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/consolidated-spec")
def get_document_pack_consolidated_spec(pack_id: str) -> dict:
    try:
        return document_pack_service.get_spec(pack_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/conflicts")
def get_document_pack_conflicts(pack_id: str) -> list[dict]:
    try:
        return document_pack_service.get_conflicts(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/missing-fields")
def get_document_pack_missing_fields(pack_id: str) -> list[dict]:
    try:
        return document_pack_service.get_missing_fields(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/provenance")
def get_document_pack_provenance(pack_id: str) -> dict:
    try:
        return document_pack_service.get_provenance(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/qa")
def get_document_pack_qa(pack_id: str) -> dict:
    try:
        return document_pack_service.get_qa_report(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/processing")
def get_document_pack_processing(pack_id: str) -> dict:
    try:
        return document_pack_service.get_processing_report(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/trace")
def get_document_pack_trace(pack_id: str) -> list[dict]:
    try:
        return document_pack_service.get_trace(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/events")
def get_document_pack_events(pack_id: str) -> list[dict]:
    try:
        return document_pack_service.get_events(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.get("/document-packs/{pack_id}/memory-summary")
def get_document_pack_memory_summary(pack_id: str) -> dict:
    try:
        return document_pack_service.get_memory_summary(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.post("/document-packs/{pack_id}/corrections")
def apply_document_pack_correction(pack_id: str, correction: DocumentPackCorrection) -> dict:
    try:
        return document_pack_service.apply_correction(pack_id, correction).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc


@app.post(
    "/document-packs/{pack_id}/generate-design",
    response_model=DocumentPackGenerateDesignResponse,
)
def generate_design_from_document_pack(pack_id: str) -> dict:
    try:
        _spec, qa_report, mapping, ready = document_pack_service.get_generation_readiness(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc
    if not ready:
        return {
            "pack_id": pack_id,
            "status": "blocked",
            "mapping": mapping.model_dump(),
            "extraction_report": {
                "source": "project_design_spec",
                "prompt_text_reparse": False,
                "qa_status": qa_report.status,
                "qa_ready_to_generate": qa_report.ready_to_generate,
                "qa_blocking_issues": qa_report.blocking_issues,
                "mapping_loss_report": mapping.mapping_loss_report,
            },
        }
    requirements = RequirementSpec.model_validate(mapping.requirements)
    try:
        design = workflow_service.create_design_from_requirements(
            requirements=requirements,
            detail_level="high",
            source_label="project_design_spec",
        )
    except WorkflowBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "5"},
        ) from exc
    if design.get("workflow_id"):
        document_pack_service.mark_generated_workflow(pack_id, design["workflow_id"])
    return {
        "pack_id": pack_id,
        "status": "pending",
        "mapping": mapping.model_dump(),
        "extraction_report": {
            "source": "project_design_spec",
            "prompt_text_reparse": False,
            "provider": "project_design_spec",
            "fallback_used": False,
            "mapping_loss_report": mapping.mapping_loss_report,
        },
        **design,
    }


@app.get("/memory/stats")
def memory_stats() -> dict:
    return memory_service.stats()


@app.post("/rag/reindex")
def rag_reindex() -> dict:
    return rag_service.reindex().model_dump()


@app.get("/rag/search", response_model=RagSearchResponse)
def rag_search(
    q: str = Query(min_length=1, max_length=1000),
    limit: int = Query(5, ge=1, le=25),
    collection: str | None = None,
    network_type: str | None = None,
    tower_type: str | None = None,
    doc_type: str | None = None,
) -> dict:
    try:
        results = rag_service.search(
            query=q,
            limit=limit,
            collection=collection,
            filters={
                "network_type": network_type,
                "tower_type": tower_type,
                "doc_type": doc_type,
            },
        )
    except RagIndexCompatibilityError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RAG_INDEX_DIMENSION_MISMATCH",
                "message": str(exc),
                "recommended_action": "Run POST /rag/reindex with the active embedding provider.",
            },
        ) from exc
    return {
        "query": q,
        "results": [_public_rag_search_result(result.model_dump()) for result in results],
    }


def _public_rag_search_result(result: dict) -> dict:
    payload = result.get("payload")
    if not isinstance(payload, dict):
        return result
    result = dict(result)
    result["payload"] = dict(payload)
    result["payload"]["source_path"] = _public_source_path(payload.get("source_path"))
    return result


def _public_source_path(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        return value
    try:
        return str(path.resolve().relative_to(settings.project_root.resolve()))
    except ValueError:
        return path.name
