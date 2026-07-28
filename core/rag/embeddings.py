"""Embedding providers.

Primary: NVIDIA API for a configured multilingual retrieval model.
Emergency fallback: deterministic hash embedding for tests and bootstrap only.

The product path is API-first. Local sentence-transformers is only an explicit
developer override; it is never used as an automatic fallback for the NVIDIA API.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from core.rag.text import normalized_tokens

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "nvidia/llama-nemotron-embed-1b-v2"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_TIMEOUT_S = 8.0
DEFAULT_NVIDIA_MAX_RETRIES = 1
DEFAULT_NVIDIA_BATCH_SIZE = 32
NVIDIA_INPUT_PROFILE = "query_passage_v1"

# NVIDIA publishes these dimensions for the supported Retriever embedding NIMs.
# Keeping them local prevents a network probe during application import/startup.
NVIDIA_MODEL_DIMENSIONS = {
    "baai/bge-m3": 1024,
    "nvidia/nv-embedqa-e5-v5": 1024,
    "nvidia/llama-nemotron-embed-1b-v2": 2048,
}


@runtime_checkable
class EmbeddingProvider(Protocol):
    dimensions: int
    name: str

    def embed(self, text: str) -> list[float]: ...

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """Deterministic hash embedding. No external dependency. Test / emergency fallback only."""

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions
        self.name = f"hashing-{dimensions}"
        self.input_profile = "symmetric_v1"

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = normalized_tokens(text)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed(text)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embed_many(texts)


class NvidiaEmbeddingProvider:
    """NVIDIA API provider for BAAI/bge-m3. OpenAI-compatible endpoint."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        api_key: str | None = None,
        *,
        dimensions: int | None = None,
        timeout_s: float = DEFAULT_NVIDIA_TIMEOUT_S,
        max_retries: int = DEFAULT_NVIDIA_MAX_RETRIES,
        batch_size: int = DEFAULT_NVIDIA_BATCH_SIZE,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is not installed") from exc

        self.model_name = model_name
        self.api_key = (
            api_key or os.getenv("NVIDIA_API_KEY") or os.getenv("TELECOM_STUDIO_NVIDIA_API_KEY")
        )
        if not self.api_key:
            raise RuntimeError("NVIDIA API key is required")
        native_dimensions = NVIDIA_MODEL_DIMENSIONS.get(model_name)
        resolved_dimensions = dimensions or native_dimensions
        if resolved_dimensions is None:
            raise RuntimeError(
                f"Embedding dimensions are unknown for NVIDIA model {model_name!r}; "
                "configure an explicit dimension instead of probing the network at startup."
            )
        if timeout_s <= 0:
            raise ValueError("NVIDIA embedding timeout must be positive")
        if max_retries < 0:
            raise ValueError("NVIDIA embedding max_retries cannot be negative")
        if batch_size <= 0:
            raise ValueError("NVIDIA embedding batch_size must be positive")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=NVIDIA_BASE_URL,
            timeout=timeout_s,
            max_retries=max_retries,
        )
        self.name = f"nvidia:{model_name}"
        self.dimensions = resolved_dimensions
        self.request_dimensions = (
            resolved_dimensions
            if dimensions is not None and resolved_dimensions != native_dimensions
            else None
        )
        self.batch_size = batch_size
        self.input_profile = NVIDIA_INPUT_PROFILE

    def embed(self, text: str) -> list[float]:
        return self.embed_query(text)

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embed_passages(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text], input_type="query")[0]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed_batch(texts, input_type="passage")

    def _embed_batch(
        self,
        texts: Sequence[str],
        *,
        input_type: str,
    ) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            request: dict[str, object] = {
                "input": batch,
                "model": self.model_name,
                "encoding_format": "float",
                "extra_body": {"input_type": input_type, "truncate": "NONE"},
            }
            if self.request_dimensions is not None:
                request["dimensions"] = self.request_dimensions
            response = self.client.embeddings.create(
                **request,
            )
            ordered = sorted(response.data, key=lambda item: getattr(item, "index", 0))
            batch_vectors = [list(item.embedding) for item in ordered]
            if len(batch_vectors) != len(batch):
                raise RuntimeError(
                    "NVIDIA embedding response count does not match the submitted batch"
                )
            for vector in batch_vectors:
                if len(vector) != self.dimensions:
                    raise RuntimeError(
                        "NVIDIA embedding response dimension does not match the configured model"
                    )
            vectors.extend(batch_vectors)
        return vectors


class SentenceTransformersProvider:
    """Local sentence-transformers provider. Default model: BAAI/bge-m3."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name, trust_remote_code=False)
        self.name = f"sentence-transformers:{model_name}"
        self.dimensions = self.model.get_embedding_dimension()
        self.input_profile = "symmetric_v1"

    def embed(self, text: str) -> list[float]:
        return self.model.encode(text, convert_to_numpy=True).tolist()

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        encoded = self.model.encode(list(texts), convert_to_numpy=True)
        return encoded.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed(text)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embed_many(texts)


def _strict_quality_mode() -> bool:
    return os.getenv("TELECOM_STUDIO_EMBEDDING_STRICT_QUALITY", "").lower() in {"1", "true", "yes"}


def build_embedding_provider(
    provider_name: str,
    model_name: str,
    *,
    api_key: str | None = None,
    dimensions: int | None = None,
    strict_quality: bool | None = None,
) -> EmbeddingProvider:
    """Build the embedding provider.

    Strategy:
    - "nvidia": require NVIDIA API.
    - "auto": try NVIDIA API first, then deterministic hash for bootstrap only.
    - "sentence-transformers": explicit developer override only.
    - "deterministic": hash fallback explicitly for tests/bootstrap.

    The NVIDIA product path does not silently load local sentence-transformers.
    """
    provider_name = provider_name.strip().lower()
    requested = f"{provider_name}:{model_name}"

    if provider_name in {"deterministic", "hash", "hashing"}:
        logger.info("Using deterministic hash embedding as requested: %s", requested)
        return HashEmbeddingProvider(dimensions=dimensions or 1024)

    if provider_name == "nvidia":
        try:
            provider = NvidiaEmbeddingProvider(
                model_name,
                api_key=api_key,
                dimensions=dimensions,
            )
            logger.info("Using NVIDIA API embedding provider: %s", provider.name)
            return provider
        except Exception as exc:
            raise RuntimeError(
                "NVIDIA API embedding provider is required for TELECOM_STUDIO_EMBEDDING_PROVIDER="
                "nvidia. Configure NVIDIA_API_KEY or TELECOM_STUDIO_NVIDIA_API_KEY, or use "
                "TELECOM_STUDIO_EMBEDDING_PROVIDER=deterministic only for tests/bootstrap."
            ) from exc
    if provider_name == "auto":
        try:
            provider = NvidiaEmbeddingProvider(
                model_name,
                api_key=api_key,
                dimensions=dimensions,
            )
            logger.info("Using NVIDIA API embedding provider: %s", provider.name)
            return provider
        except Exception as exc:
            strict = _strict_quality_mode() if strict_quality is None else strict_quality
            if strict:
                raise
            logger.warning(
                "NVIDIA API embedding provider failed (%s). Falling back to deterministic hash "
                "embedding for bootstrap only.",
                exc,
            )
            return HashEmbeddingProvider()
    elif provider_name != "sentence-transformers":
        raise RuntimeError(
            "Unsupported embedding provider "
            f"{provider_name!r}. Use nvidia, auto, sentence-transformers, or deterministic."
        )

    try:
        provider = SentenceTransformersProvider(model_name)
        logger.info("Using explicit local sentence-transformers provider: %s", provider.name)
        return provider
    except Exception as exc:
        raise RuntimeError(
            f"Explicit local embedding provider sentence-transformers failed to load {model_name}. "
            "Use TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia for the product path or "
            "TELECOM_STUDIO_EMBEDDING_PROVIDER=deterministic for tests/bootstrap."
        ) from exc
