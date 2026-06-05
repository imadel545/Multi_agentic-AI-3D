import hashlib
import math
import re
from typing import Protocol


class EmbeddingProvider(Protocol):
    dimensions: int
    name: str

    def embed(self, text: str) -> list[float]: ...


class HashEmbeddingProvider:
    """Small deterministic embedding provider for local smoke RAG without model downloads."""

    def __init__(self, dimensions: int = 384) -> None:
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


class FastEmbedProvider:
    def __init__(self, model_name: str) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError("fastembed is not installed") from exc
        self.model_name = model_name
        self.model = TextEmbedding(model_name=model_name)
        self.name = f"fastembed:{model_name}"
        sample = self.embed("dimension probe")
        self.dimensions = len(sample)

    def embed(self, text: str) -> list[float]:
        return list(next(self.model.embed([text])))


def build_embedding_provider(provider_name: str, model_name: str) -> EmbeddingProvider:
    if provider_name == "fastembed":
        try:
            return FastEmbedProvider(model_name)
        except RuntimeError:
            return HashEmbeddingProvider()
    return HashEmbeddingProvider()
