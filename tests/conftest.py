import pytest

from apps.api.telecom_studio_api.config import settings
from core.rag.embeddings import DEFAULT_MODEL, build_embedding_provider


@pytest.fixture(scope="session")
def nvidia_embedding_provider():
    return build_embedding_provider("nvidia", DEFAULT_MODEL, api_key=settings.nvidia_api_key)
