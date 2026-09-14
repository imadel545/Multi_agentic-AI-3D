import re
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, rag_service, workflow_service


def test_workspace_mutations_reach_api_in_both_frontend_servers() -> None:
    root = Path(__file__).resolve().parents[2]
    vite = (root / "apps/frontend/vite.config.ts").read_text()
    nginx = (root / "infra/docker/nginx.conf").read_text()
    assert '"/workspace"' in vite.split("proxy:", 1)[1]
    route = re.search(r"location ~ (\^/\(studio[^ ]+) \{", nginx)
    assert route is not None
    for path in (
        "/workspace/projects",
        "/workspace/projects/project_abc/chats",
        "/workspace/chats/chat_abc",
    ):
        assert re.match(route.group(1), path), path


def _install_reindex_probe(monkeypatch):
    calls: list[None] = []

    def reindex():
        calls.append(None)
        return SimpleNamespace(model_dump=lambda: {"collections": [], "indexed_documents": 0})

    monkeypatch.setattr(rag_service, "reindex", reindex)
    return calls


def test_hostile_origin_is_rejected_before_rag_reindex(monkeypatch) -> None:
    calls = _install_reindex_probe(monkeypatch)

    response = TestClient(app).post(
        "/rag/reindex",
        headers={"Origin": "https://example.invalid"},
        data={"trigger": "reindex"},
    )

    assert response.status_code == 403
    assert calls == []
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]


def test_allowed_local_origin_can_reindex(monkeypatch) -> None:
    calls = _install_reindex_probe(monkeypatch)

    response = TestClient(app).post(
        "/rag/reindex",
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_cli_request_without_origin_can_reindex(monkeypatch) -> None:
    calls = _install_reindex_probe(monkeypatch)

    response = TestClient(app).post("/rag/reindex")

    assert response.status_code == 200
    assert len(calls) == 1


def test_untrusted_host_is_rejected_before_health_handler() -> None:
    response = TestClient(app).get("/health", headers={"Host": "attacker.invalid"})

    assert response.status_code == 400


def test_health_keeps_local_access_and_has_honest_security_headers() -> None:
    response = TestClient(app).get(
        "/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["content-security-policy"] == (
        "frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
    )
    assert response.headers["permissions-policy"] == ("camera=(), microphone=(), geolocation=()")
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["access-control-expose-headers"] == "X-Request-ID"
    assert "strict-transport-security" not in response.headers


def test_cors_preflight_advertises_only_required_surface() -> None:
    response = TestClient(app).options(
        "/designs",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-filename,x-request-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-methods"] == "GET, POST, PATCH, DELETE"
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "x-chat-id" in allowed_headers
    assert "content-type" in allowed_headers
    assert "x-filename" in allowed_headers
    assert "x-request-id" in allowed_headers
    assert "access-control-allow-credentials" not in response.headers


def test_sse_route_still_streams_terminal_event(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    workflow_id = "wf_5ec0017aa001"
    (tmp_path / workflow_id).mkdir(parents=True)
    workflow_service._sync_output_services()
    workflow_service._emit_workflow_event(
        workflow_id,
        "workflow_completed",
        {"status": "completed"},
    )
    try:
        with TestClient(app).stream(
            "GET",
            f"/designs/{workflow_id}/events/stream",
            headers={"Origin": "http://127.0.0.1:5173"},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache, no-transform"
            assert response.headers["access-control-allow-origin"] == ("http://127.0.0.1:5173")
            body = "".join(response.iter_text())
    finally:
        workflow_service.outputs_dir = original_outputs
        workflow_service._sync_output_services()

    assert "event: workflow_completed" in body
