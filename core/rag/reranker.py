"""RAG re-ranker using BAAI/bge-reranker-v2-m3.

Re-ranking takes the initial vector/keyword retrieval results and re-orders them
with a cross-encoder that understands query-document relevance much better than
dense similarity alone. This is especially useful for short French telecom queries.

Default: passthrough (keep original ranking).
Explicit local override: CrossEncoder with BAAI/bge-reranker-v2-m3.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from core.rag.models import RagSearchResult

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self, query: str, results: list[RagSearchResult], top_k: int
    ) -> list[RagSearchResult]: ...


class PassthroughReranker:
    """No-op re-ranker. Used when the local model is not available."""

    def __init__(self) -> None:
        self.name = "passthrough"

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
        model_name: str = DEFAULT_RERANKER_MODEL,
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


def build_reranker(
    model_name: str = DEFAULT_RERANKER_MODEL,
    *,
    provider_name: str = "passthrough",
) -> Reranker:
    """Build the configured re-ranker.

    The product path avoids hidden local model downloads/loads. Use
    provider_name="local" only when the developer explicitly wants the
    local cross-encoder.
    """
    provider_name = provider_name.strip().lower()
    if provider_name in {"", "none", "passthrough", "disabled"}:
        return PassthroughReranker()
    if provider_name != "local":
        raise RuntimeError(
            f"Unsupported reranker provider {provider_name!r}. Use passthrough or local."
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
        return PassthroughReranker()
