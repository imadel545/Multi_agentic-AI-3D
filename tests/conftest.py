import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TEST_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="telecom-studio-pytest-"))
atexit.register(shutil.rmtree, _TEST_RUNTIME_ROOT, ignore_errors=True)

# API modules construct local-first services at import time. Force every mutable
# store into a session-scoped temporary directory before importing settings so a
# unit test can never write into product data or call NVIDIA implicitly.
os.environ["TELECOM_STUDIO_OUTPUTS_DIR"] = str(_TEST_RUNTIME_ROOT / "outputs")
os.environ["TELECOM_STUDIO_QDRANT_PATH"] = str(_TEST_RUNTIME_ROOT / "qdrant")
os.environ["TELECOM_STUDIO_SQLITE_PATH"] = str(_TEST_RUNTIME_ROOT / "sqlite" / "studio.db")
os.environ["TELECOM_STUDIO_EMBEDDING_PROVIDER"] = "deterministic"
os.environ["TELECOM_STUDIO_RERANKER_PROVIDER"] = "passthrough"
os.environ["TELECOM_STUDIO_ENABLE_GROQ_EXTRACTION"] = "false"
os.environ["TELECOM_STUDIO_ENABLE_GROQ_PLANNING_DECISION"] = "false"

from apps.api.telecom_studio_api.config import settings  # noqa: E402
from core.rag.embeddings import DEFAULT_MODEL, build_embedding_provider  # noqa: E402


@pytest.fixture(scope="session")
def nvidia_embedding_provider():
    return build_embedding_provider(
        "nvidia",
        DEFAULT_MODEL,
        api_key=settings.resolved_nvidia_api_key,
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    del session
    mutable_paths = {
        settings.temp_outputs_dir,
        settings.local_qdrant_path,
        settings.local_sqlite_path,
    }
    if not all(path.is_relative_to(_TEST_RUNTIME_ROOT) for path in mutable_paths):
        raise RuntimeError("pytest mutable stores must be isolated from product data")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    # Several API tests intentionally use TestClient without entering its
    # lifespan. Close import-time local services so executor threads cannot
    # keep the pytest process alive after results are complete.
    try:
        from apps.api.telecom_studio_api.main import rag_service, workflow_service
    except ImportError:
        return
    workflow_service.shutdown(wait=True)
    rag_service.close()
