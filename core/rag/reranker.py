"""RAG re-rankers.

Re-ranking takes the initial vector/keyword retrieval results and re-orders them
with a cross-encoder that understands query-document relevance much better than
dense similarity alone. This is especially useful for short French telecom queries.

Product default: NVIDIA API reranker.
Bootstrap/test mode: explicit passthrough.
Developer override: local CrossEncoder.
"""

from __future__ import annotations

import contextvars
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from core.rag.models import RagSearchResult

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_NVIDIA_RERANKER_MODEL = "nvidia/llama-nemotron-rerank-1b-v2"
DEFAULT_RERANKER_MODEL = DEFAULT_NVIDIA_RERANKER_MODEL
DEFAULT_RERANKER_TIMEOUT_S = 8.0
DEFAULT_MAX_CANDIDATES = 32
DEFAULT_MAX_QUERY_CHARS = 2_000
DEFAULT_MAX_PASSAGE_CHARS = 4_000
DEFAULT_MAX_TOTAL_PASSAGE_CHARS = 48_000
_SCHEMA_COMPATIBILITY_STATUS_CODES = frozenset({400, 415, 422})


@dataclass(frozen=True, slots=True)
class RerankDiagnostics:
    provider: str
    model_name: str | None
    status: str
    degraded_reason: str | None
    input_candidates: int
    submitted_candidates: int
    omitted_candidates: int
    truncated_passages: int
    query_truncated: bool
    elapsed_ms: int


@dataclass(frozen=True, slots=True)
class RerankOutcome:
    results: tuple[RagSearchResult, ...]
    diagnostics: RerankDiagnostics


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
        timeout_s: float = DEFAULT_RERANKER_TIMEOUT_S,
        max_candidates: int = DEFAULT_MAX_CANDIDATES,
        max_query_chars: int = DEFAULT_MAX_QUERY_CHARS,
        max_passage_chars: int = DEFAULT_MAX_PASSAGE_CHARS,
        max_total_passage_chars: int = DEFAULT_MAX_TOTAL_PASSAGE_CHARS,
        http_client: httpx.Client | None = None,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("NVIDIA reranker timeout must be positive")
        if min(max_candidates, max_query_chars, max_passage_chars, max_total_passage_chars) <= 0:
            raise ValueError("NVIDIA reranker request limits must be positive")
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_candidates = max_candidates
        self.max_query_chars = max_query_chars
        self.max_passage_chars = max_passage_chars
        self.max_total_passage_chars = max_total_passage_chars
        self.name = f"nvidia:{model_name}"
        self.provider = "nvidia"
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_s),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        initial_diagnostics = self._diagnostics(
            status="primary_nvidia_reranker" if api_key else "degraded_passthrough",
            degraded_reason=None if api_key else "missing_nvidia_api_key",
            input_candidates=0,
            submitted_candidates=0,
            omitted_candidates=0,
            truncated_passages=0,
            query_truncated=False,
            started_at=None,
        )
        self._call_diagnostics: contextvars.ContextVar[RerankDiagnostics] = contextvars.ContextVar(
            f"nvidia_reranker_diagnostics_{id(self)}",
            default=initial_diagnostics,
        )

    @property
    def last_diagnostics(self) -> RerankDiagnostics:
        """Diagnostics for the current execution context, never another workflow thread."""
        return self._call_diagnostics.get()

    @property
    def status(self) -> str:
        return self.last_diagnostics.status

    @property
    def degraded_reason(self) -> str | None:
        return self.last_diagnostics.degraded_reason

    def restore_diagnostics(self, diagnostics: RerankDiagnostics) -> None:
        """Restore cached diagnostics inside the current workflow execution context."""
        if diagnostics.provider != self.provider or diagnostics.model_name != self.model_name:
            raise ValueError("Reranker diagnostics do not belong to this provider/model")
        self._call_diagnostics.set(diagnostics)

    def rerank(
        self,
        query: str,
        results: list[RagSearchResult],
        top_k: int,
    ) -> list[RagSearchResult]:
        return list(self.rerank_with_diagnostics(query, results, top_k).results)

    def rerank_with_diagnostics(
        self,
        query: str,
        results: list[RagSearchResult],
        top_k: int,
    ) -> RerankOutcome:
        started_at = time.monotonic()
        requested_top_k = max(0, min(top_k, len(results)))
        query_text = query[: self.max_query_chars]
        query_truncated = len(query_text) != len(query)
        selected_results, passages, truncated_passages = self._prepare_candidates(results)
        common = {
            "input_candidates": len(results),
            "submitted_candidates": len(selected_results),
            "omitted_candidates": len(results) - len(selected_results),
            "truncated_passages": truncated_passages,
            "query_truncated": query_truncated,
            "started_at": started_at,
        }
        if not results or requested_top_k == 0:
            return self._outcome(
                [],
                status="not_invoked_no_candidates",
                degraded_reason=None if self.api_key else "missing_nvidia_api_key",
                **common,
            )
        if not self.api_key:
            return self._outcome(
                results[:requested_top_k],
                status="degraded_passthrough",
                degraded_reason="missing_nvidia_api_key",
                **common,
            )
        try:
            rankings = self._rank(query_text, passages, deadline=started_at + self.timeout_s)
        except Exception as exc:
            logger.warning("NVIDIA reranker failed; using vector order: %s", exc)
            return self._outcome(
                results[:requested_top_k],
                status="degraded_passthrough",
                degraded_reason=_error_reason(exc),
                **common,
            )
        if not rankings:
            return self._outcome(
                results[:requested_top_k],
                status="degraded_passthrough",
                degraded_reason="empty_nvidia_reranker_response",
                **common,
            )
        ranked_results: list[RagSearchResult] = []
        seen_indexes: set[int] = set()
        for index, score in rankings:
            if index < 0 or index >= len(selected_results) or index in seen_indexes:
                continue
            seen_indexes.add(index)
            result = selected_results[index]
            ranked_results.append(result.model_copy(update={"score": float(score)}))
            if len(ranked_results) >= requested_top_k:
                break
        if not ranked_results:
            return self._outcome(
                results[:requested_top_k],
                status="degraded_passthrough",
                degraded_reason="invalid_nvidia_reranker_response",
                **common,
            )
        if len(ranked_results) < requested_top_k:
            ranked_keys = {(result.collection, result.doc_id) for result in ranked_results}
            ranked_results.extend(
                result
                for result in results
                if (result.collection, result.doc_id) not in ranked_keys
            )
        return self._outcome(
            ranked_results[:requested_top_k],
            status="primary_nvidia_reranker",
            degraded_reason=None,
            **common,
        )

    def close(self) -> None:
        if self._owns_http_client:
            self._http_client.close()

    def _prepare_candidates(
        self,
        results: list[RagSearchResult],
    ) -> tuple[list[RagSearchResult], list[str], int]:
        selected: list[RagSearchResult] = []
        passages: list[str] = []
        truncated_count = 0
        remaining_chars = self.max_total_passage_chars
        for result in results[: self.max_candidates]:
            if remaining_chars <= 0:
                break
            allowed_chars = min(self.max_passage_chars, remaining_chars)
            passage = result.text[:allowed_chars]
            if len(passage) != len(result.text):
                truncated_count += 1
            selected.append(result)
            passages.append(passage)
            remaining_chars -= len(passage)
        return selected, passages, truncated_count

    def _outcome(
        self,
        results: list[RagSearchResult],
        *,
        status: str,
        degraded_reason: str | None,
        input_candidates: int,
        submitted_candidates: int,
        omitted_candidates: int,
        truncated_passages: int,
        query_truncated: bool,
        started_at: float,
    ) -> RerankOutcome:
        diagnostics = self._diagnostics(
            status=status,
            degraded_reason=degraded_reason,
            input_candidates=input_candidates,
            submitted_candidates=submitted_candidates,
            omitted_candidates=omitted_candidates,
            truncated_passages=truncated_passages,
            query_truncated=query_truncated,
            started_at=started_at,
        )
        self._call_diagnostics.set(diagnostics)
        return RerankOutcome(results=tuple(results), diagnostics=diagnostics)

    def _diagnostics(
        self,
        *,
        status: str,
        degraded_reason: str | None,
        input_candidates: int,
        submitted_candidates: int,
        omitted_candidates: int,
        truncated_passages: int,
        query_truncated: bool,
        started_at: float | None,
    ) -> RerankDiagnostics:
        elapsed_ms = (
            0 if started_at is None else max(0, round((time.monotonic() - started_at) * 1000))
        )
        return RerankDiagnostics(
            provider=self.provider,
            model_name=self.model_name,
            status=status,
            degraded_reason=degraded_reason,
            input_candidates=input_candidates,
            submitted_candidates=submitted_candidates,
            omitted_candidates=omitted_candidates,
            truncated_passages=truncated_passages,
            query_truncated=query_truncated,
            elapsed_ms=elapsed_ms,
        )

    def _rank(
        self,
        query: str,
        passages: list[str],
        *,
        deadline: float,
    ) -> list[tuple[int, float]]:
        url = self._endpoint()
        official_passages = [{"text": passage} for passage in passages]
        payload_variants = [
            {
                "model": self.model_name,
                "query": {"text": query},
                "passages": official_passages,
                "truncate": "END",
            },
            {
                "model": self.model_name,
                "query": query,
                "documents": passages,
            },
        ]
        for index, payload in enumerate(payload_variants):
            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0:
                raise httpx.TimeoutException("NVIDIA reranker total deadline exceeded")
            try:
                response = self._http_client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                    },
                    timeout=remaining_s,
                )
                response.raise_for_status()
                return _parse_rankings(response.json())
            except httpx.HTTPStatusError as exc:
                if index == 0 and _is_schema_compatibility_error(exc):
                    continue
                raise
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


def _is_schema_compatibility_error(exc: httpx.HTTPStatusError) -> bool:
    return exc.response.status_code in _SCHEMA_COMPATIBILITY_STATUS_CODES


def _error_reason(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "nvidia_reranker_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"nvidia_reranker_http_{exc.response.status_code}"
    return f"nvidia_reranker_error:{type(exc).__name__}"
