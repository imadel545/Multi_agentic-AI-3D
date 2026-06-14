from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api import main as api_main
from core.rag.embeddings import HashEmbeddingProvider


def test_rag_api_reindex_and_search(tmp_path: Path) -> None:
    original_provider = api_main.rag_service.embedding_provider
    original_path = api_main.rag_service.qdrant_path
    original_client = api_main.rag_service._client
    api_main.rag_service.embedding_provider = HashEmbeddingProvider()
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
        api_main.rag_service.qdrant_path = original_path
        api_main.rag_service._client = original_client
