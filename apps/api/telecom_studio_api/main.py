import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from apps.api.telecom_studio_api.config import settings
from apps.api.telecom_studio_api.models import (
    CreateDesignRequest,
    CreateDesignResponse,
    CurrentOperation,
    EditDesignRequest,
    EditDesignResponse,
    ParseRequirementsRequest,
    ParseRequirementsResponse,
    RagSearchResponse,
    StudioSummary,
    TimelineSummary,
    UserIssuesResponse,
    UserSummary,
    ViewerBundle,
    WorkflowStatus,
)
from apps.api.telecom_studio_api.product import ProductNotFound, ProductService
from apps.api.telecom_studio_api.workflow import WorkflowService
from core.agents.requirement_extractor import RequirementExtractor
from core.agents.scene_edit_agent import SceneEditAgent
from core.contracts.document_pack import DocumentPackCorrection
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationReport
from core.document_pack import DocumentPackService, ProjectDesignSpecMapper
from core.llm import GroqStructuredClient
from core.memory import MemoryService
from core.orchestration import DesignOrchestrator
from core.rag import RagService
from core.rag.embeddings import build_embedding_provider
from core.services.asset_inventory import AssetInventoryService
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner
from core.services.checkpoint_saver import SqliteCheckpointSaver


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    rag_service.close()


app = FastAPI(
    title="Agentic AI 3D Telecom Design Studio",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
project_spec_mapper = ProjectDesignSpecMapper()
rag_embedding_provider = build_embedding_provider(
    settings.embedding_provider,
    settings.embedding_model,
    api_key=settings.nvidia_api_key,
)
rag_service = RagService(
    project_root=settings.project_root,
    qdrant_path=settings.local_qdrant_path,
    qdrant_url=settings.qdrant_url,
    embedding_provider=rag_embedding_provider,
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
orchestrator = DesignOrchestrator(
    registry=registry,
    extractor=requirement_extractor,
    rag_service=rag_service,
    memory_service=memory_service,
    blender_runner=blender_runner,
    checkpoint_saver=checkpoint_saver,
)
scene_edit_agent = SceneEditAgent(groq_client=groq_client)
workflow_service = WorkflowService(
    registry=registry,
    outputs_dir=settings.temp_outputs_dir,
    orchestrator=orchestrator,
    scene_edit_agent=scene_edit_agent,
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
    return workflow_service.create_design(
        requirements_text=request.requirements_text,
        detail_level=request.options.detail_level,
        use_llm=request.options.use_llm,
    )


@app.get("/designs/{workflow_id}", response_model=WorkflowStatus)
def get_design(workflow_id: str) -> dict:
    try:
        return workflow_service.get_status(workflow_id)
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


@app.get("/designs")
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
    result = workflow_service.edit_design(workflow_id, request.edit_prompt)
    return {
        "workflow_id": result.workflow_id,
        "edit_id": result.edit_id,
        "status": result.status,
        "version_id": result.version_id,
        "diff_summary": result.diff_summary,
        "patch": result.patch.model_dump() if result.patch else None,
        "validation_report": result.validation_report.model_dump()
        if result.validation_report
        else None,
        "artifacts": result.artifacts,
        "generation_mode": result.generation_mode,
        "qa_score": result.qa_score,
        "llm_provider": result.llm_provider,
        "llm_fallback_used": result.llm_fallback_used,
        "errors": [e.model_dump() for e in result.errors],
        "warnings": [w.model_dump() for w in result.warnings],
    }


@app.get("/designs/{workflow_id}/versions")
def list_versions(workflow_id: str) -> list[dict]:
    return workflow_service.list_versions(workflow_id)


@app.post("/designs/{workflow_id}/versions/{version_id}/rollback")
def rollback_version(workflow_id: str, version_id: str) -> dict:
    try:
        return workflow_service.rollback_version(workflow_id, version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc


@app.get("/designs/{workflow_id}/events")
def get_events(workflow_id: str) -> list[dict]:
    return workflow_service.get_events(workflow_id)


@app.get("/designs/{workflow_id}/events/stream")
def stream_events(workflow_id: str):
    if not workflow_service.workflow_exists(workflow_id):
        raise HTTPException(status_code=404, detail="workflow not found")

    def event_generator():
        import json
        import time

        seen = 0
        idle_ticks = 0
        max_idle_ticks = 300
        while True:
            events = workflow_service.get_events(workflow_id)
            for event in events[seen:]:
                yield f"data: {json.dumps(event)}\n\n"
                seen += 1
                idle_ticks = 0
            # If workflow completed or failed, send one more update then close
            if events and events[-1].get("event_type") in (
                "workflow_completed",
                "workflow_failed",
            ):
                break
            idle_ticks += 1
            if idle_ticks >= max_idle_ticks:
                yield 'event: timeout\ndata: {"detail":"event stream timeout"}\n\n'
                break
            time.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/assets")
def list_assets() -> list[dict]:
    return [asset.model_dump() for asset in registry.list_assets()]


@app.get("/assets/inventory")
def asset_inventory() -> dict:
    return asset_inventory_service.inspect()


@app.get("/assets/{asset_id}")
def get_asset(asset_id: str) -> dict:
    try:
        return registry.get(asset_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="asset not found") from exc


@app.post("/document-packs")
async def create_document_pack(request: Request) -> dict:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=422, detail="empty document pack body")
    filename = request.headers.get("x-filename")
    try:
        return document_pack_service.ingest_zip(content, filename=filename).model_dump()
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/document-packs")
def list_document_packs() -> list[dict]:
    return document_pack_service.list_packs()


@app.get("/document-packs/capabilities")
def get_document_pack_capabilities() -> dict:
    return document_pack_service.capabilities().model_dump()


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


@app.post("/document-packs/{pack_id}/generate-design")
def generate_design_from_document_pack(pack_id: str) -> dict:
    try:
        spec = document_pack_service.get_spec(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document pack not found") from exc
    mapping = project_spec_mapper.map_to_requirements(spec)
    if mapping.status != "mapped":
        return {
            "pack_id": pack_id,
            "status": "blocked",
            "mapping": mapping.model_dump(),
        }
    requirements = RequirementSpec.model_validate(mapping.requirements)
    design = workflow_service.create_design_from_requirements(
        requirements=requirements,
        detail_level="high",
        source_label="project_design_spec",
    )
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
    q: str,
    limit: int = 5,
    collection: str | None = None,
    network_type: str | None = None,
    tower_type: str | None = None,
    doc_type: str | None = None,
) -> dict:
    if limit < 1 or limit > 25:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 25")
    return {
        "query": q,
        "results": [
            result.model_dump()
            for result in rag_service.search(
                query=q,
                limit=limit,
                collection=collection,
                filters={
                    "network_type": network_type,
                    "tower_type": tower_type,
                    "doc_type": doc_type,
                },
            )
        ],
    }
