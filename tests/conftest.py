import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TEST_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="telecom-studio-pytest-"))
_LIVE_PROVIDERS = os.getenv("TELECOM_STUDIO_TEST_LIVE_PROVIDERS") == "1"
atexit.register(shutil.rmtree, _TEST_RUNTIME_ROOT, ignore_errors=True)

# API modules construct local-first services at import time. Force every mutable
# store into a session-scoped temporary directory before importing settings so a
# unit test can never write into product data or call NVIDIA implicitly.
os.environ["TELECOM_STUDIO_OUTPUTS_DIR"] = str(_TEST_RUNTIME_ROOT / "outputs")
os.environ["TELECOM_STUDIO_QDRANT_PATH"] = str(_TEST_RUNTIME_ROOT / "qdrant")
os.environ["TELECOM_STUDIO_SQLITE_PATH"] = str(_TEST_RUNTIME_ROOT / "sqlite" / "studio.db")
os.environ["TELECOM_STUDIO_ASSET_LIBRARY_PATH"] = str(_TEST_RUNTIME_ROOT / "asset-library")
os.environ["TELECOM_STUDIO_RUNTIME_ORIGIN"] = "TEST"
# Legacy endpoint tests exercise their own API contracts. Authentication has a
# dedicated isolated suite and must be opted into explicitly there.
os.environ["TELECOM_STUDIO_AUTH_ENABLED"] = "false"
if not _LIVE_PROVIDERS:
    os.environ["TELECOM_STUDIO_EMBEDDING_PROVIDER"] = "deterministic"
    os.environ["TELECOM_STUDIO_RERANKER_PROVIDER"] = "passthrough"
    os.environ["TELECOM_STUDIO_EXTERNAL_PROVIDERS_ENABLED"] = "false"
    os.environ["TELECOM_STUDIO_ENABLE_GROQ_EXTRACTION"] = "false"
    os.environ["TELECOM_STUDIO_ENABLE_GROQ_PLANNING_DECISION"] = "false"
    os.environ["TELECOM_STUDIO_ENABLE_GROQ_ASSET_SELECTION"] = "false"
    os.environ["TELECOM_STUDIO_ENABLE_GROQ_GEOMETRY_PROGRAM"] = "false"
    os.environ["TELECOM_STUDIO_ENABLE_GROQ_VISION"] = "false"
    os.environ["TELECOM_STUDIO_ENABLE_GROQ_VISUAL_DESIGN_CRITIC"] = "false"

from apps.api.telecom_studio_api import product as product_module  # noqa: E402
from apps.api.telecom_studio_api.config import settings  # noqa: E402
from core.services.blender_runner import BlenderRunner  # noqa: E402


@pytest.fixture(autouse=True)
def reject_unmarked_real_blender(request: pytest.FixtureRequest, monkeypatch) -> None:
    """Keep the fast gate honest at both real Blender subprocess boundaries."""

    original_generation = BlenderRunner._run_blender_command
    original_probe = product_module._run_blender_probe

    def runtime_is_explicit() -> bool:
        return any(
            request.node.get_closest_marker(marker) is not None
            for marker in ("blender_runtime", "provider_live")
        )

    def guarded(self: BlenderRunner, command: list[str]):
        if not runtime_is_explicit():
            pytest.fail(
                "real Blender subprocess requires a blender_runtime or provider_live marker",
                pytrace=False,
            )
        return original_generation(self, command)

    def guarded_probe(command: list[str]):
        if not runtime_is_explicit():
            pytest.fail(
                "real Blender readiness probe requires a blender_runtime or provider_live marker",
                pytrace=False,
            )
        return original_probe(command)

    monkeypatch.setattr(BlenderRunner, "_run_blender_command", guarded)
    monkeypatch.setattr(product_module, "_run_blender_probe", guarded_probe)


def pytest_sessionstart(session: pytest.Session) -> None:
    del session
    mutable_paths = {
        settings.temp_outputs_dir,
        settings.local_qdrant_path,
        settings.local_sqlite_path,
    }
    if not all(path.is_relative_to(_TEST_RUNTIME_ROOT) for path in mutable_paths):
        raise RuntimeError("pytest mutable stores must be isolated from product data")
    if not _LIVE_PROVIDERS and (settings.resolved_groq_api_key or settings.resolved_nvidia_api_key):
        raise RuntimeError("pytest must not resolve external provider credentials")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    # Several API tests intentionally use TestClient without entering its
    # lifespan. Close import-time local services so executor threads cannot
    # keep the pytest process alive after results are complete.
    try:
        from apps.api.telecom_studio_api.main import (
            memory_service,
            rag_service,
            workflow_service,
        )
    except ImportError:
        return
    workflow_service.shutdown(wait=True)
    memory_service.close()
    rag_service.close()
