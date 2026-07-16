import shutil
from pathlib import Path

import pytest

from core.agents.requirement_extractor import RequirementExtractor
from core.memory import MemoryService
from core.orchestration import DesignOrchestrator
from core.rag import RagService
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner


@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is required to evaluate truthful successful workflow memory",
)
def test_memory_eval_successful_5g_lattice_design_recalled_for_next_similar_query(
    tmp_path: Path,
) -> None:
    rag_service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
    )
    memory_service = MemoryService(tmp_path / "memory.db", rag_service=rag_service)
    orchestrator = DesignOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        memory_service=memory_service,
        blender_runner=BlenderRunner(project_root=Path.cwd()),
        allow_blender_fallback=True,
    )

    first = orchestrator.run(
        workflow_id="wf_memory_eval_seed",
        requirements_text=(
            "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles et faisceaux."
        ),
        detail_level="high",
        output_dir=tmp_path / "seed",
        use_llm=False,
    )
    second = orchestrator.run(
        workflow_id="wf_memory_eval_next",
        requirements_text=(
            "Préparer un nouveau design 5G lattice tower 30m, three sectors at 24m, "
            "azimuths 0, 120, 240 with RRU and beams."
        ),
        detail_level="high",
        output_dir=tmp_path / "next",
        use_llm=False,
    )

    assert first.status == "completed"
    assert second.status == "completed"
    assert second.memory_recall is not None
    assert second.memory_recall.memory_context_count >= 1
    assert second.memory_recall.similar_workflows[0]["workflow_id"] == "wf_memory_eval_seed"
    assert memory_service.last_index_result.status == "indexed"
