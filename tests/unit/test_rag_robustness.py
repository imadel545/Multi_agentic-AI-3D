import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from qdrant_client.models import Distance, VectorParams

from core.rag.embeddings import NvidiaEmbeddingProvider
from core.rag.models import RagDocument, RagSearchResult
from core.rag.reranker import NvidiaReranker
from core.rag.service import RagService


class _SwitchableEmbeddingProvider:
    dimensions = 8
    name = "test:batched"

    def __init__(self) -> None:
        self.fail_batch = False
        self.batch_calls = 0

    def embed(self, text: str) -> list[float]:
        return [1.0] + [0.0] * (self.dimensions - 1)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls += 1
        if self.fail_batch:
            raise RuntimeError("simulated embedding failure")
        return [self.embed(text) for text in texts]


def _document() -> RagDocument:
    return RagDocument(
        doc_id="rule-1",
        collection="telecom_rules",
        text="Règle telecom 5G pylône treillis",
        payload={"doc_type": "test_rule"},
    )


def _result(index: int, text: str | None = None) -> RagSearchResult:
    return RagSearchResult(
        collection="telecom_rules",
        doc_id=f"doc-{index}",
        score=float(100 - index),
        text=text if text is not None else f"passage {index}",
        payload={},
    )


def test_runtime_memory_dimension_migration_is_versioned_and_non_destructive(
    tmp_path: Path,
) -> None:
    provider = _SwitchableEmbeddingProvider()
    service = RagService(
        project_root=tmp_path / "project",
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=provider,
        reranker_provider_name="passthrough",
    )
    service.client.create_collection(
        collection_name="design_memory",
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )

    service.upsert_runtime_document(
        collection="design_memory",
        doc_id="memory:design:wf_new",
        text="design 5G quatre secteurs",
        payload={"workflow_id": "wf_new"},
    )

    compatibility = service.runtime_collection_compatibility()
    active = compatibility["collections"]["design_memory"]["active_collection"]
    assert active == "design_memory__test_batched_d8"
    assert service.client.collection_exists("design_memory")
    assert service.client.get_collection("design_memory").config.params.vectors.size == 4
    assert service.client.get_collection(active).config.params.vectors.size == 8
    assert compatibility["status"] == "compatible"
    results = service.search(
        "quatre secteurs",
        collection="design_memory",
        limit=1,
    )
    assert [result.doc_id for result in results] == ["memory:design:wf_new"]
    service.close()


def test_runtime_memory_identity_includes_provider_when_dimensions_match(tmp_path: Path) -> None:
    first_provider = _SwitchableEmbeddingProvider()
    first_provider.name = "provider:first"
    first = RagService(
        project_root=tmp_path / "project",
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=first_provider,
        reranker_provider_name="passthrough",
    )
    first.upsert_runtime_document(
        collection="design_memory",
        doc_id="memory:design:first",
        text="first provider",
        payload={},
    )
    first_collection = first._runtime_collection_name("design_memory")
    first.close()

    second_provider = _SwitchableEmbeddingProvider()
    second_provider.name = "provider:second"
    second = RagService(
        project_root=tmp_path / "project",
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=second_provider,
        reranker_provider_name="passthrough",
    )
    second.upsert_runtime_document(
        collection="design_memory",
        doc_id="memory:design:second",
        text="second provider",
        payload={},
    )
    second_collection = second._runtime_collection_name("design_memory")

    assert first_collection != second_collection
    assert second.client.collection_exists(first_collection)
    assert second.client.collection_exists(second_collection)
    second.close()


def test_runtime_reindex_failure_keeps_last_published_index(tmp_path: Path) -> None:
    provider = _SwitchableEmbeddingProvider()
    service = RagService(
        project_root=tmp_path / "project",
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=provider,
        reranker_provider_name="passthrough",
    )
    documents = {
        "design_memory": [
            RagDocument(
                doc_id="memory:design:stable",
                collection="design_memory",
                text="stable design",
                payload={},
            )
        ],
        "error_memory": [],
        "document_pack_memory": [],
    }
    service.reindex_runtime_documents(documents, source_fingerprint="first")
    state_before = service._read_runtime_index_state()
    assert state_before is not None
    active_before = state_before["physical_collections"]["design_memory"]

    provider.fail_batch = True
    with pytest.raises(RuntimeError, match="simulated embedding failure"):
        service.reindex_runtime_documents(documents, source_fingerprint="second")

    assert service._read_runtime_index_state() == state_before
    assert service.client.collection_exists(active_before)
    assert [
        result.doc_id
        for result in service.search("stable design", collection="design_memory", limit=1)
    ] == ["memory:design:stable"]
    service.close()


def test_rag_health_records_real_embedding_failure(tmp_path: Path) -> None:
    provider = _SwitchableEmbeddingProvider()
    provider.fail_batch = True
    service = RagService(
        project_root=tmp_path / "project",
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=provider,
        reranker_provider_name="passthrough",
    )
    assert service.health_snapshot()["status"] == "unverified"

    with pytest.raises(RuntimeError, match="simulated embedding failure"):
        service.upsert_runtime_document(
            collection="design_memory",
            doc_id="memory:design:failed",
            text="failure",
            payload={},
        )

    health = service.health_snapshot()
    assert health["status"] == "failed"
    assert health["operation"] == "runtime_upsert:design_memory"
    assert "simulated embedding failure" in str(health["error"])
    service.close()


def test_nvidia_embedding_constructor_is_network_free_and_batches(monkeypatch) -> None:
    create_calls: list[dict] = []
    client_options: dict = {}

    class FakeEmbeddings:
        def create(self, **kwargs):
            create_calls.append(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=index, embedding=[float(index)] * 1024)
                    for index, _ in enumerate(kwargs["input"])
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            client_options.update(kwargs)
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    provider = NvidiaEmbeddingProvider(
        api_key="nvidia-test",
        dimensions=1024,
        timeout_s=7.0,
        max_retries=1,
        batch_size=2,
    )

    assert create_calls == []
    assert provider.dimensions == 1024
    assert client_options["timeout"] == 7.0
    assert client_options["max_retries"] == 1

    vectors = provider.embed_many(["a", "b", "c"])
    query_vector = provider.embed("requête")

    assert len(vectors) == 3
    assert len(query_vector) == 1024
    assert [call["input"] for call in create_calls] == [["a", "b"], ["c"], ["requête"]]
    assert [call["extra_body"]["input_type"] for call in create_calls] == [
        "passage",
        "passage",
        "query",
    ]
    assert [call["dimensions"] for call in create_calls] == [1024, 1024, 1024]


def test_rag_service_uses_passage_embeddings_for_index_and_query_embedding_for_search(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class RoleAwareProvider(_SwitchableEmbeddingProvider):
        input_profile = "query_passage_test"

        def __init__(self) -> None:
            super().__init__()
            self.query_calls: list[str] = []
            self.passage_calls: list[list[str]] = []

        def embed_query(self, text: str) -> list[float]:
            self.query_calls.append(text)
            return self.embed(text)

        def embed_passages(self, texts: list[str]) -> list[list[float]]:
            self.passage_calls.append(list(texts))
            return [self.embed(text) for text in texts]

    provider = RoleAwareProvider()
    monkeypatch.setattr("core.rag.service.load_rag_documents", lambda _root: [_document()])
    service = RagService(
        project_root=tmp_path / "project",
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=provider,
        reranker_provider_name="passthrough",
    )

    service.reindex()
    results = service.search("pylône treillis", collection="telecom_rules", limit=1)

    assert results
    assert provider.passage_calls == [["Règle telecom 5G pylône treillis"]]
    assert provider.query_calls == ["pylône treillis"]
    state = json.loads(service._static_index_state_path().read_text(encoding="utf-8"))
    assert state["embedding_input_profile"] == "query_passage_test"
    service.close()


def test_reindex_failure_preserves_previous_active_index(tmp_path: Path, monkeypatch) -> None:
    provider = _SwitchableEmbeddingProvider()
    monkeypatch.setattr("core.rag.service.load_rag_documents", lambda _root: [_document()])
    service = RagService(
        project_root=tmp_path / "project",
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=provider,
        reranker_provider_name="passthrough",
    )

    service.reindex()
    state_path = service._static_index_state_path()
    state_before = json.loads(state_path.read_text(encoding="utf-8"))
    active_before = state_before["physical_collections"]["telecom_rules"]
    provider.fail_batch = True

    with pytest.raises(RuntimeError, match="simulated embedding failure"):
        service.reindex()

    state_after = json.loads(state_path.read_text(encoding="utf-8"))
    collection_names = {
        description.name for description in service.client.get_collections().collections
    }
    assert state_after == state_before
    assert active_before in collection_names
    assert set(state_after["physical_collections"].values()) == collection_names

    results = service.search("pylône treillis", collection="telecom_rules", limit=1)
    assert [result.doc_id for result in results] == ["rule-1"]
    service.close()


def test_concurrent_reindex_is_single_flight(tmp_path: Path, monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    class SlowProvider(_SwitchableEmbeddingProvider):
        def embed_many(self, texts: list[str]) -> list[list[float]]:
            self.batch_calls += 1
            started.set()
            assert release.wait(timeout=2.0)
            return [self.embed(text) for text in texts]

    provider = SlowProvider()
    monkeypatch.setattr("core.rag.service.load_rag_documents", lambda _root: [_document()])
    service = RagService(
        project_root=tmp_path / "project",
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=provider,
        reranker_provider_name="passthrough",
    )
    reports = []
    errors = []

    def run_reindex() -> None:
        try:
            reports.append(service.reindex())
        except Exception as exc:  # pragma: no cover - assertion reports unexpected failures
            errors.append(exc)

    first = threading.Thread(target=run_reindex)
    second = threading.Thread(target=run_reindex)
    first.start()
    assert started.wait(timeout=2.0)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(timeout=3.0)
    second.join(timeout=3.0)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert len(reports) == 2
    assert reports[0] == reports[1]
    assert provider.batch_calls == 1
    service.close()


def test_asset_manifest_change_invalidates_static_index(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    manifests = project_root / "assets" / "manifests"
    manifests.mkdir(parents=True)
    manifest_path = manifests / "TEST_TOWER.json"
    manifest = {
        "asset_id": "TEST_TOWER",
        "type": "tower",
        "file": "test.glb",
        "height_m": 30,
        "compatible_networks": ["5G"],
        "compatible_tower_types": ["lattice_tower"],
        "status": "internal",
        "version": "1.0.0",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    service = RagService(
        project_root=project_root,
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
        reranker_provider_name="passthrough",
    )
    service.reindex()
    first_state = json.loads(service._static_index_state_path().read_text(encoding="utf-8"))

    manifest["version"] = "2.0.0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    results = service.search("TEST_TOWER", collection="asset_manifests", limit=1)
    second_state = json.loads(service._static_index_state_path().read_text(encoding="utf-8"))

    assert results[0].payload["version"] == "2.0.0"
    assert first_state["asset_manifest_hash"] != second_state["asset_manifest_hash"]
    assert first_state["physical_collections"] != second_state["physical_collections"]
    assert second_state["obsolete_collections"] == []
    assert all(
        not service.client.collection_exists(collection)
        for collection in first_state["physical_collections"].values()
    )
    service.close()


def test_missing_physical_collection_forces_complete_rebuild(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("core.rag.service.load_rag_documents", lambda _root: [_document()])
    service = RagService(
        project_root=tmp_path / "project",
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
        reranker_provider_name="passthrough",
    )
    service.reindex()
    state_path = service._static_index_state_path()
    first_state = json.loads(state_path.read_text(encoding="utf-8"))
    missing_collection = first_state["physical_collections"]["validation_cases"]
    service.client.delete_collection(missing_collection)

    results = service.search("pylône", collection="telecom_rules", limit=1)
    second_state = json.loads(state_path.read_text(encoding="utf-8"))

    assert results
    assert first_state["physical_collections"] != second_state["physical_collections"]
    assert all(
        service.client.collection_exists(collection)
        for collection in second_state["physical_collections"].values()
    )
    service.close()


def test_reranker_does_not_retry_alternate_schema_on_server_error() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500, json={"detail": "unavailable"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reranker = NvidiaReranker(api_key="nvidia-test", http_client=client)
    results = [_result(0), _result(1)]

    assert reranker.rerank("query", results, top_k=2) == results
    assert len(requests) == 1
    assert reranker.status == "degraded_passthrough"
    assert reranker.degraded_reason == "nvidia_reranker_http_500"

    assert reranker.rerank("no candidates", [], top_k=1) == []
    assert reranker.status == "not_invoked_no_candidates"
    assert reranker.degraded_reason is None
    client.close()


def test_reranker_retries_legacy_schema_only_after_schema_4xx() -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        if len(payloads) == 1:
            return httpx.Response(422, json={"detail": "schema mismatch"})
        return httpx.Response(200, json={"rankings": [{"index": 1, "score": 0.9}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reranker = NvidiaReranker(api_key="nvidia-test", http_client=client)

    reranked = reranker.rerank("query", [_result(0), _result(1)], top_k=1)

    assert [result.doc_id for result in reranked] == ["doc-1"]
    assert len(payloads) == 2
    assert "passages" in payloads[0]
    assert "documents" in payloads[1]
    client.close()


def test_reranker_schema_retry_respects_one_total_deadline(monkeypatch) -> None:
    monotonic_values = iter([0.0, 0.0, 9.0, 9.0])
    monkeypatch.setattr(
        "core.rag.reranker.time.monotonic",
        lambda: next(monotonic_values, 9.0),
    )

    class SchemaRejectingClient:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def post(self, url: str, **kwargs) -> httpx.Response:
            self.timeouts.append(kwargs["timeout"])
            request = httpx.Request("POST", url)
            return httpx.Response(422, request=request, json={"detail": "schema mismatch"})

    client = SchemaRejectingClient()
    reranker = NvidiaReranker(
        api_key="nvidia-test",
        http_client=client,
        timeout_s=8.0,
    )
    results = [_result(0)]

    assert reranker.rerank("query", results, top_k=1) == results
    assert client.timeouts == [8.0]
    assert reranker.degraded_reason == "nvidia_reranker_timeout"


def test_reranker_caps_candidates_and_text_with_per_call_diagnostics() -> None:
    submitted: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        submitted.update(json.loads(request.content))
        return httpx.Response(200, json={"rankings": [{"index": 2, "score": 0.95}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reranker = NvidiaReranker(
        api_key="nvidia-test",
        http_client=client,
        max_candidates=3,
        max_query_chars=4,
        max_passage_chars=5,
        max_total_passage_chars=12,
    )
    results = [_result(index, "x" * 20) for index in range(10)]

    reranked = reranker.rerank("abcdefgh", results, top_k=2)

    assert [result.doc_id for result in reranked] == ["doc-2", "doc-0"]
    assert submitted["query"] == {"text": "abcd"}
    assert [len(item["text"]) for item in submitted["passages"]] == [5, 5, 2]
    assert reranker.last_diagnostics.input_candidates == 10
    assert reranker.last_diagnostics.submitted_candidates == 3
    assert reranker.last_diagnostics.omitted_candidates == 7
    assert reranker.last_diagnostics.truncated_passages == 3
    assert reranker.last_diagnostics.query_truncated is True
    client.close()


def test_reranker_diagnostics_are_isolated_between_workflow_threads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        query = payload["query"]["text"]
        if query == "bad":
            return httpx.Response(503, json={"detail": "unavailable"})
        return httpx.Response(200, json={"rankings": [{"index": 0, "score": 0.8}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reranker = NvidiaReranker(api_key="nvidia-test", http_client=client)
    observed: dict[str, tuple[str, str | None]] = {}

    def run(query: str) -> None:
        reranker.rerank(query, [_result(0)], top_k=1)
        observed[query] = (reranker.status, reranker.degraded_reason)

    good = threading.Thread(target=run, args=("good",))
    bad = threading.Thread(target=run, args=("bad",))
    good.start()
    bad.start()
    good.join(timeout=2.0)
    bad.join(timeout=2.0)

    assert observed["good"] == ("primary_nvidia_reranker", None)
    assert observed["bad"] == ("degraded_passthrough", "nvidia_reranker_http_503")
    assert reranker.status == "primary_nvidia_reranker"
    assert reranker.degraded_reason is None
    client.close()
