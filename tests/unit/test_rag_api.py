from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api import main as api_main
from core.rag.embeddings import HashEmbeddingProvider
from core.rag.reranker import PassthroughReranker
from core.rag.service import RagIndexCompatibilityError


def test_rag_api_reindex_and_search(tmp_path: Path) -> None:
    original_provider = api_main.rag_service.embedding_provider
    original_reranker = api_main.rag_service._reranker
    original_path = api_main.rag_service.qdrant_path
    original_client = api_main.rag_service._client
    api_main.rag_service.embedding_provider = HashEmbeddingProvider()
    api_main.rag_service._reranker = PassthroughReranker()
    api_main.rag_service.qdrant_path = tmp_path / "qdrant"
    api_main.rag_service._client = None
    client = TestClient(api_main.app)
    try:
        reindex_response = client.post("/rag/reindex")
        assert reindex_response.status_code == 200
        assert reindex_response.json()["status"] == "indexed"

        search_response = client.get(
            "/rag/search",
            params={"q": "5G lattice tower 3 sectors", "limit": 5},
        )
        assert search_response.status_code == 200
        payload = search_response.json()
        assert payload["query"] == "5G lattice tower 3 sectors"
        assert payload["results"]

        filtered_response = client.get(
            "/rag/search",
            params={
                "q": "microwave dish lattice",
                "collection": "asset_manifests",
                "network_type": "MW",
                "tower_type": "lattice_tower",
                "doc_type": "asset_manifest",
            },
        )
        assert filtered_response.status_code == 200
        assert filtered_response.json()["results"]
    finally:
        api_main.rag_service.embedding_provider = original_provider
        api_main.rag_service._reranker = original_reranker
        api_main.rag_service.qdrant_path = original_path
        api_main.rag_service._client = original_client


def test_rag_api_reports_dimension_mismatch(monkeypatch) -> None:
    def _raise_dimension_mismatch(*args, **kwargs):
        raise RagIndexCompatibilityError("RAG index vector dimension is incompatible.")

    monkeypatch.setattr(api_main.rag_service, "search", _raise_dimension_mismatch)
    client = TestClient(api_main.app)

    response = client.get("/rag/search", params={"q": "pylône treillis 5G"})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "RAG_INDEX_DIMENSION_MISMATCH"
    assert "POST /rag/reindex" in detail["recommended_action"]


def test_rag_api_sanitizes_legacy_absolute_source_paths(monkeypatch) -> None:
    absolute_source = str(api_main.settings.project_root / "docs" / "RAG_STRATEGY.md")

    def _legacy_search(*args, **kwargs):
        return [
            SimpleNamespace(
                model_dump=lambda: {
                    "collection": "design_patterns",
                    "doc_id": "legacy",
                    "score": 1.0,
                    "text": "legacy indexed context",
                    "payload": {
                        "source_path": absolute_source,
                        "filename": "RAG_STRATEGY.md",
                    },
                }
            )
        ]

    monkeypatch.setattr(api_main.rag_service, "search", _legacy_search)
    client = TestClient(api_main.app)

    response = client.get("/rag/search", params={"q": "pylône treillis 5G"})

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["payload"]["source_path"] == "docs/RAG_STRATEGY.md"
    assert "/Users/" not in str(result)
