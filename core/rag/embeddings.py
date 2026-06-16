"""Embedding providers.

Primary: NVIDIA API for BAAI/bge-m3 (fast, no local GPU/VRAM needed).
Emergency fallback: deterministic hash embedding for tests and bootstrap only.

The product path is API-first. Local sentence-transformers is only an explicit
developer override; it is never used as an automatic fallback for the NVIDIA API.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "baai/bge-m3"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


@runtime_checkable
class EmbeddingProvider(Protocol):
    dimensions: int
    name: str

    def embed(self, text: str) -> list[float]: ...


class HashEmbeddingProvider:
    """Deterministic hash embedding. No external dependency. Test / emergency fallback only."""

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions
        self.name = f"hashing-{dimensions}"

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class NvidiaEmbeddingProvider:
    """NVIDIA API provider for BAAI/bge-m3. OpenAI-compatible endpoint."""

    def __init__(self, model_name: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
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
        self.client = OpenAI(api_key=self.api_key, base_url=NVIDIA_BASE_URL)
        self.name = f"nvidia:{model_name}"
        sample = self.embed("dimension probe")
        self.dimensions = len(sample)

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            input=[text],
            model=self.model_name,
            encoding_format="float",
            extra_body={"truncate": "NONE"},
        )
        return response.data[0].embedding


class SentenceTransformersProvider:
    """Local sentence-transformers provider. Default model: BAAI/bge-m3."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name, trust_remote_code=False)
        self.name = f"sentence-transformers:{model_name}"
        self.dimensions = self.model.get_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        return self.model.encode(text, convert_to_numpy=True).tolist()


def _strict_quality_mode() -> bool:
    return os.getenv("TELECOM_STUDIO_EMBEDDING_STRICT_QUALITY", "").lower() in {"1", "true", "yes"}


def _local_model_cache_dir() -> Path | None:
    """Return the Hugging Face cache directory for BAAI/bge-m3 if it exists."""
    try:
        hf_home = Path(os.path.expanduser(os.getenv("HF_HOME", "~/.cache/huggingface")))
        candidate = hf_home / "hub" / "models--BAAI--bge-m3"
        return candidate if candidate.exists() else None
    except Exception:
        return None


def _remove_local_model_cache(model_name: str) -> None:
    """Remove the local model cache to free disk space when API is used."""
    if model_name != DEFAULT_MODEL:
        return
    cache_dir = _local_model_cache_dir()
    if cache_dir and cache_dir.exists():
        logger.info("Removing local embedding model cache to free disk space: %s", cache_dir)
        shutil.rmtree(cache_dir, ignore_errors=True)


def build_embedding_provider(
    provider_name: str,
    model_name: str,
    *,
    api_key: str | None = None,
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
        return HashEmbeddingProvider()

    if provider_name == "nvidia":
        try:
            provider = NvidiaEmbeddingProvider(model_name, api_key=api_key)
            logger.info("Using NVIDIA API embedding provider: %s", provider.name)
            _remove_local_model_cache(model_name)
            return provider
        except Exception as exc:
            raise RuntimeError(
                "NVIDIA API embedding provider is required for TELECOM_STUDIO_EMBEDDING_PROVIDER="
                "nvidia. Configure NVIDIA_API_KEY or TELECOM_STUDIO_NVIDIA_API_KEY, or use "
                "TELECOM_STUDIO_EMBEDDING_PROVIDER=deterministic only for tests/bootstrap."
            ) from exc
    if provider_name == "auto":
        try:
            provider = NvidiaEmbeddingProvider(model_name, api_key=api_key)
            logger.info("Using NVIDIA API embedding provider: %s", provider.name)
            _remove_local_model_cache(model_name)
            return provider
        except Exception as exc:
            if _strict_quality_mode():
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
