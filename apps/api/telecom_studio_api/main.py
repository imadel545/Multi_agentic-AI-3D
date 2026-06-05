from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from apps.api.telecom_studio_api.config import settings
from apps.api.telecom_studio_api.models import (
    CreateDesignRequest,
    CreateDesignResponse,
    RagSearchResponse,
    WorkflowStatus,
)
from apps.api.telecom_studio_api.workflow import WorkflowService
from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationReport
from core.llm import GroqStructuredClient
from core.memory import MemoryService
from core.orchestration import DesignOrchestrator
from core.rag import RagService
from core.services.asset_inventory import AssetInventoryService
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    rag_service.close()


app = FastAPI(
    title="Agentic AI 3D Telecom Design Studio",
    version="0.1.0",
    lifespan=lifespan,
)

registry = AssetRegistry(settings.manifests_dir)
asset_inventory_service = AssetInventoryService(settings.project_root, registry)
rag_service = RagService(
    project_root=settings.project_root,
    qdrant_path=settings.local_qdrant_path,
    qdrant_url=settings.qdrant_url,
    embedding_provider_name=settings.embedding_provider,
    embedding_model=settings.embedding_model,
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
orchestrator = DesignOrchestrator(
    registry=registry,
    extractor=requirement_extractor,
    rag_service=rag_service,
    memory_service=memory_service,
    blender_runner=blender_runner,
)
workflow_service = WorkflowService(
    registry=registry,
    outputs_dir=settings.temp_outputs_dir,
    orchestrator=orchestrator,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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


@app.get("/designs/{workflow_id}/download")
def download_design(workflow_id: str) -> FileResponse:
    try:
        path = workflow_service.archive_path(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow artifacts not found") from exc
    return FileResponse(path=path, filename=f"{workflow_id}_artifacts.zip")


@app.post("/scene-spec/validate", response_model=ValidationReport)
def validate_scene_spec_endpoint(scene: SceneSpec) -> ValidationReport:
    return workflow_service.validate_scene(scene)


@app.get("/assets")
def list_assets() -> list[dict]:
    return [asset.model_dump() for asset in registry.list_assets()]


@app.get("/assets/inventory")
def asset_inventory() -> dict:
    return asset_inventory_service.inspect()


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
