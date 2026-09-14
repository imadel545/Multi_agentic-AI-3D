from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.workspace import WorkspaceStore, create_workspace_router

WORKFLOW_ID = "wf_1234567890ab"
PACK_ID = "pack_1234567890ab"


def client_for(path: Path):
    store = WorkspaceStore(path, lambda value: value == WORKFLOW_ID, lambda value: value == PACK_ID)
    app = FastAPI()
    app.include_router(create_workspace_router(store))
    return TestClient(app)


def test_workspace_survives_restart_and_deletion_preserves_external_design(tmp_path):
    path = tmp_path / "state.sqlite"
    client = client_for(path)
    project = client.post("/workspace/projects", json={"title": "Site nord"}).json()
    pid = project["project_id"]
    chat = client.post(
        f"/workspace/projects/{pid}/chats", json={"title": "Secteur", "workflow_id": WORKFLOW_ID}
    ).json()
    cid = chat["chat_id"]
    assert (
        client.patch(
            f"/workspace/chats/{cid}",
            json={"draft_prompt": "Ajouter une radio", "document_pack_id": PACK_ID},
        ).status_code
        == 200
    )
    restarted = client_for(path)
    assert restarted.get(f"/workspace/chats/{cid}").json()["draft_prompt"] == "Ajouter une radio"
    assert restarted.get(f"/workspace/chats/{cid}").json()["document_pack_id"] == PACK_ID
    assert restarted.delete(f"/workspace/projects/{pid}").status_code == 204
    assert restarted.get(f"/workspace/chats/{cid}").status_code == 404
    # Organization deletion leaves workflow authority untouched: it can be linked again.
    pid = restarted.post("/workspace/projects", json={"title": "Récupération"}).json()["project_id"]
    assert (
        restarted.post(
            f"/workspace/projects/{pid}/chats",
            json={"title": "Retrouvé", "workflow_id": WORKFLOW_ID},
        ).status_code
        == 201
    )


def test_workspace_rejects_missing_sources_and_replacement(tmp_path):
    client = client_for(tmp_path / "state.sqlite")
    assert client.post("/workspace/projects", json={"title": "   "}).status_code == 422
    pid = client.post("/workspace/projects", json={"title": "Projet"}).json()["project_id"]
    endpoint = f"/workspace/projects/{pid}/chats"
    assert (
        client.post(
            endpoint, json={"title": "Invalide", "workflow_id": "wf_000000000000"}
        ).status_code
        == 422
    )
    cid = client.post(endpoint, json={"title": "Valide", "workflow_id": WORKFLOW_ID}).json()[
        "chat_id"
    ]
    assert (
        client.post(endpoint, json={"title": "Doublon", "workflow_id": WORKFLOW_ID}).status_code
        == 409
    )
    assert client.patch(f"/workspace/chats/{cid}", json={"workflow_id": None}).status_code == 409
    assert (
        client.patch(
            f"/workspace/chats/{cid}", json={"document_pack_id": "pack_000000000000"}
        ).status_code
        == 422
    )
    assert client.patch(f"/workspace/chats/{cid}", json={"title": None}).status_code == 422
    assert client.patch(f"/workspace/chats/{cid}", json={"draft_prompt": None}).status_code == 422


def test_creation_binds_before_response_and_rejects_second_design(tmp_path):
    import pytest
    from fastapi import HTTPException

    path = tmp_path / "state.sqlite"
    client = client_for(path)
    pid = client.post("/workspace/projects", json={"title": "Projet"}).json()["project_id"]
    cid = client.post(f"/workspace/projects/{pid}/chats", json={"title": "Brief"}).json()["chat_id"]
    store = WorkspaceStore(path, lambda value: value == WORKFLOW_ID, lambda _: True)
    result = store.create_for_chat(cid, lambda: {"workflow_id": WORKFLOW_ID, "status": "pending"})
    assert result["workflow_id"] == WORKFLOW_ID
    linked = client_for(path).get(f"/workspace/chats/{cid}").json()
    assert linked["workflow_id"] == WORKFLOW_ID
    assert linked["draft_prompt"] == ""
    with pytest.raises(HTTPException) as error:
        store.create_for_chat(cid, lambda: pytest.fail("Must not run a second generation"))
    assert error.value.status_code == 409


def test_workspace_uses_canonical_external_ids_and_missing_chat_is_404(tmp_path):
    client = client_for(tmp_path / "state.sqlite")
    pid = client.post("/workspace/projects", json={"title": "Projet"}).json()["project_id"]
    endpoint = f"/workspace/projects/{pid}/chats"

    assert (
        client.post(endpoint, json={"title": "Brief", "workflow_id": "wf_REAL"}).status_code == 422
    )
    missing_chat = "chat_" + "0" * 32
    response = client.patch(
        f"/workspace/chats/{missing_chat}",
        json={"document_pack_id": "pack_000000000000"},
    )
    assert response.status_code == 404


def test_document_pack_creation_binds_source_and_touches_project(tmp_path):
    path = tmp_path / "state.sqlite"
    client = client_for(path)
    project = client.post("/workspace/projects", json={"title": "Projet"}).json()
    pid = project["project_id"]
    chat = client.post(f"/workspace/projects/{pid}/chats", json={"title": "Documents"}).json()

    store = WorkspaceStore(
        path,
        lambda value: value == WORKFLOW_ID,
        lambda value: value == PACK_ID,
    )
    result = store.create_for_chat(
        chat["chat_id"],
        lambda: {"workflow_id": WORKFLOW_ID, "status": "pending"},
        document_pack_id=PACK_ID,
    )

    assert result["workflow_id"] == WORKFLOW_ID
    restarted = client_for(path)
    bound = restarted.get(f"/workspace/chats/{chat['chat_id']}").json()
    refreshed_project = restarted.get("/workspace/projects").json()[0]
    assert bound["workflow_id"] == WORKFLOW_ID
    assert bound["document_pack_id"] == PACK_ID
    assert bound["draft_prompt"] == ""
    assert refreshed_project["updated_at"] == bound["updated_at"]


def test_creation_preserves_existing_pack_and_blocked_result_preserves_draft(tmp_path):
    path = tmp_path / "state.sqlite"
    client = client_for(path)
    pid = client.post("/workspace/projects", json={"title": "Projet"}).json()["project_id"]
    first = client.post(
        f"/workspace/projects/{pid}/chats",
        json={"title": "Premier"},
    ).json()
    second = client.post(
        f"/workspace/projects/{pid}/chats",
        json={"title": "Second"},
    ).json()
    for chat, draft in ((first, "Créer le site"), (second, "Analyser les documents")):
        response = client.patch(
            f"/workspace/chats/{chat['chat_id']}",
            json={"draft_prompt": draft, "document_pack_id": PACK_ID},
        )
        assert response.status_code == 200

    store = WorkspaceStore(
        path,
        lambda value: value == WORKFLOW_ID,
        lambda value: value == PACK_ID,
    )
    store.create_for_chat(
        first["chat_id"],
        lambda: {"workflow_id": WORKFLOW_ID, "status": "pending"},
    )
    blocked = store.create_for_chat(
        second["chat_id"],
        lambda: {"status": "blocked", "workflow_id": None},
        document_pack_id=PACK_ID,
    )

    assert blocked["status"] == "blocked"
    restarted = client_for(path)
    first_bound = restarted.get(f"/workspace/chats/{first['chat_id']}").json()
    second_unchanged = restarted.get(f"/workspace/chats/{second['chat_id']}").json()
    assert first_bound["document_pack_id"] == PACK_ID
    assert first_bound["draft_prompt"] == ""
    assert second_unchanged["workflow_id"] is None
    assert second_unchanged["document_pack_id"] == PACK_ID
    assert second_unchanged["draft_prompt"] == "Analyser les documents"
    assert (
        restarted.get(f"/workspace/projects/{pid}/chats").json()[0]["chat_id"] == first["chat_id"]
    )


def test_chat_creation_can_carry_failed_draft_and_lists_linked_workflows(tmp_path):
    client = client_for(tmp_path / "state.sqlite")
    project_id = client.post("/workspace/projects", json={"title": "Projet"}).json()["project_id"]

    response = client.post(
        f"/workspace/projects/{project_id}/chats",
        json={
            "title": "Reprise",
            "workflow_id": WORKFLOW_ID,
            "draft_prompt": "Corriger la hauteur et relancer",
        },
    )

    assert response.status_code == 201
    assert response.json()["draft_prompt"] == "Corriger la hauteur et relancer"
    assert client.get("/workspace/linked-workflow-ids").json() == [WORKFLOW_ID]


def test_document_pack_reservation_blocks_chat_deletion_until_link_completes(tmp_path):
    path = tmp_path / "state.sqlite"
    client = client_for(path)
    project_id = client.post("/workspace/projects", json={"title": "Projet"}).json()["project_id"]
    chat_id = client.post(
        f"/workspace/projects/{project_id}/chats",
        json={"title": "Import"},
    ).json()["chat_id"]
    store = WorkspaceStore(path, lambda _: True, lambda _: True)

    store.begin_document_pack_ingest(chat_id)
    assert client.delete(f"/workspace/chats/{chat_id}").status_code == 409
    linked = store.complete_document_pack_ingest(chat_id, PACK_ID)

    assert linked["document_pack_id"] == PACK_ID
    assert client.delete(f"/workspace/chats/{chat_id}").status_code == 204
