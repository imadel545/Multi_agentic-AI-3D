"""RAG re-rankers.

Re-ranking takes the initial vector/keyword retrieval results and re-orders them
with a cross-encoder that understands query-document relevance much better than
dense similarity alone. This is especially useful for short French telecom queries.

Product default: NVIDIA API reranker.
Bootstrap/test mode: explicit passthrough.
Developer override: local CrossEncoder.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

import httpx

from core.rag.models import RagSearchResult

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_NVIDIA_RERANKER_MODEL = "nvidia/llama-nemotron-rerank-1b-v2"
DEFAULT_RERANKER_MODEL = DEFAULT_NVIDIA_RERANKER_MODEL


@runtime_checkable
class Reranker(Protocol):
    name: str
    provider: str
    model_name: str | None
    status: str
    degraded_reason: str | None

    def rerank(
        self, query: str, results: list[RagSearchResult], top_k: int
    ) -> list[RagSearchResult]: ...


class PassthroughReranker:
    """No-op re-ranker. Used when the local model is not available."""

    def __init__(
        self,
        *,
        provider: str = "passthrough",
        model_name: str | None = None,
        degraded_reason: str | None = None,
    ) -> None:
        self.name = "passthrough"
        self.provider = provider
        self.model_name = model_name
        self.status = "passthrough_no_rerank"
        self.degraded_reason = degraded_reason

    def rerank(
        self,
        query: str,
        results: list[RagSearchResult],
        top_k: int,
    ) -> list[RagSearchResult]:
        return results[:top_k]


class CrossEncoderReranker:
    """Local cross-encoder re-ranker. Default model: BAAI/bge-reranker-v2-m3."""

    def __init__(
        self,
        model_name: str = DEFAULT_LOCAL_RERANKER_MODEL,
        *,
        device: str = "cpu",
        max_length: int = 512,
    ) -> None:
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        # Cross-encoders are memory-hungry; default to CPU and a conservative
        # max_length to avoid OOM on consumer GPUs/MPS while keeping latency low.
        self.model = CrossEncoder(
            model_name,
            trust_remote_code=False,
            device=device,
            max_length=max_length,
        )
        self.name = f"cross-encoder:{model_name}"
        self.provider = "local"
        self.status = "explicit_local_reranker"
        self.degraded_reason = None

    def rerank(
        self,
        query: str,
        results: list[RagSearchResult],
        top_k: int,
    ) -> list[RagSearchResult]:
        if not results:
            return []

        pairs = [(query, result.text) for result in results]
        scores = self.model.predict(pairs)
        scored = sorted(
            zip(results, scores, strict=False),
            key=lambda item: float(item[1]),
            reverse=True,
        )
        return [result for result, _ in scored[:top_k]]


class NvidiaReranker:
    """NVIDIA API reranker.

    This client is intentionally small and fail-open: the product API exposes
    degraded status when the remote reranker cannot be reached, while retrieval
    still returns vector-ranked results instead of silently claiming reranking.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_NVIDIA_RERANKER_MODEL,
        *,
        api_key: str | None,
        base_url: str = "https://ai.api.nvidia.com/v1",
        timeout_s: float = 20.0,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.name = f"nvidia:{model_name}"
        self.provider = "nvidia"
        self.status = "primary_nvidia_reranker" if api_key else "degraded_passthrough"
        self.degraded_reason = None if api_key else "missing_nvidia_api_key"

    def rerank(
        self,
        query: str,
        results: list[RagSearchResult],
        top_k: int,
    ) -> list[RagSearchResult]:
        if not results:
            return []
        if not self.api_key:
            return results[:top_k]
        try:
            rankings = self._rank(query, results)
        except Exception as exc:
            self.status = "degraded_passthrough"
            self.degraded_reason = f"nvidia_reranker_error:{type(exc).__name__}"
            logger.warning("NVIDIA reranker failed; using vector order: %s", exc)
            return results[:top_k]
        if not rankings:
            self.status = "degraded_passthrough"
            self.degraded_reason = "empty_nvidia_reranker_response"
            return results[:top_k]
        self.status = "primary_nvidia_reranker"
        self.degraded_reason = None
        ranked_results = []
        seen_indexes: set[int] = set()
        for index, score in rankings:
            if index < 0 or index >= len(results) or index in seen_indexes:
                continue
            seen_indexes.add(index)
            result = results[index]
            ranked_results.append(result.model_copy(update={"score": float(score)}))
            if len(ranked_results) >= top_k:
                break
        if len(ranked_results) < top_k:
            ranked_results.extend(
                result for i, result in enumerate(results) if i not in seen_indexes
            )
        return ranked_results[:top_k]

    def _rank(self, query: str, results: list[RagSearchResult]) -> list[tuple[int, float]]:
        url = self._endpoint()
        passages = [{"text": result.text} for result in results]
        payload_variants = [
            {
                "model": self.model_name,
                "query": {"text": query},
                "passages": passages,
                "truncate": "END",
            },
            {
                "model": self.model_name,
                "query": query,
                "documents": [result.text for result in results],
            },
        ]
        last_error: Exception | None = None
        for payload in payload_variants:
            try:
                response = httpx.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                    },
                    timeout=self.timeout_s,
                )
                response.raise_for_status()
                return _parse_rankings(response.json())
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        return []

    def _endpoint(self) -> str:
        model_path = self.model_name
        if model_path.startswith("nvidia/"):
            model_path = model_path.split("/", 1)[1]
        return f"{self.base_url}/retrieval/nvidia/{model_path}/reranking"


def build_reranker(
    model_name: str = DEFAULT_RERANKER_MODEL,
    *,
    provider_name: str = "passthrough",
    api_key: str | None = None,
    base_url: str = "https://ai.api.nvidia.com/v1",
) -> Reranker:
    """Build the configured re-ranker.

    The product path avoids hidden local model downloads/loads. Use
    provider_name="local" only when the developer explicitly wants the
    local cross-encoder.
    """
    provider_name = provider_name.strip().lower()
    if provider_name in {"", "none", "passthrough", "disabled"}:
        return PassthroughReranker(provider=provider_name or "passthrough", model_name=model_name)
    if provider_name == "nvidia":
        return NvidiaReranker(model_name, api_key=api_key, base_url=base_url)
    if provider_name != "local":
        raise RuntimeError(
            f"Unsupported reranker provider {provider_name!r}. Use nvidia, passthrough, or local."
        )
    try:
        reranker = CrossEncoderReranker(model_name)
        logger.info("Using local cross-encoder re-ranker: %s", reranker.name)
        return reranker
    except Exception as exc:
        logger.warning(
            "Cross-encoder re-ranker %s failed to load (%s); using passthrough.",
            model_name,
            exc,
        )
        return PassthroughReranker(
            provider="local",
            model_name=model_name,
            degraded_reason=f"local_reranker_load_error:{type(exc).__name__}",
        )


def _parse_rankings(payload: dict[str, Any]) -> list[tuple[int, float]]:
    raw_items = (
        payload.get("rankings")
        or payload.get("results")
        or payload.get("data")
        or payload.get("reranked_passages")
        or []
    )
    parsed: list[tuple[int, float]] = []
    if not isinstance(raw_items, list):
        return parsed
    for fallback_index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        index = (
            item.get("index")
            if item.get("index") is not None
            else item.get("passage_index")
            if item.get("passage_index") is not None
            else item.get("document_index")
            if item.get("document_index") is not None
            else item.get("id")
        )
        score = (
            item.get("score")
            if item.get("score") is not None
            else item.get("relevance_score")
            if item.get("relevance_score") is not None
            else item.get("logit")
        )
        try:
            parsed.append((int(index if index is not None else fallback_index), float(score)))
        except (TypeError, ValueError):
            continue
    return sorted(parsed, key=lambda item: item[1], reverse=True)
