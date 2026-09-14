import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api import main as api_main
from core.contracts.document_pack import (
    DocumentReference,
    ExtractedField,
    ProjectDesignSpec,
    RadioSectorDesign,
    SourceEvidence,
)
from core.document_pack.prompt_context import build_document_prompt_context

CHAT_ID = "chat_" + "a" * 32


def _confirmed_tower_height_spec(height_m: float) -> ProjectDesignSpec:
    return ProjectDesignSpec(
        pack_id="pack_attachment_contract",
        tower_spec={
            "tower_height_m": ExtractedField(
                field="tower.tower_height_m",
                value=height_m,
                status="confirmed",
                confidence=0.99,
                sources=[
                    SourceEvidence(
                        document_id="doc_height",
                        file="elevation.pdf",
                        page=2,
                        evidence=f"Hauteur du pylône : {height_m:g} m",
                    )
                ],
            )
        },
    )


@pytest.mark.parametrize("endpoint", ["/requirements/parse", "/designs"])
@pytest.mark.parametrize("with_document_pack", [False, True])
def test_written_request_is_required_even_with_an_attached_document_pack(
    endpoint: str,
    with_document_pack: bool,
) -> None:
    payload: dict[str, object] = {"requirements_text": " \t\n "}
    if with_document_pack:
        payload.update(
            {
                "chat_id": CHAT_ID,
                "document_pack_id": "pack_" + "b" * 12,
            }
        )

    response = TestClient(api_main.app).post(endpoint, json=payload)

    assert response.status_code == 422
    assert any(
        error["loc"][-1] == "requirements_text" and "written request" in error["msg"]
        for error in response.json()["detail"]
    )


def test_deterministic_analysis_applies_confirmed_attached_document_facts(
    monkeypatch,
) -> None:
    """A local fallback must not silently ignore the attachment context."""

    spec = _confirmed_tower_height_spec(42.0)
    monkeypatch.setattr(api_main.document_pack_service, "get_spec", lambda _pack_id: spec)
    monkeypatch.setattr(
        api_main.workspace_store,
        "get_chat",
        lambda chat_id: {
            "chat_id": chat_id,
            "document_pack_id": spec.pack_id,
        },
    )

    response = TestClient(api_main.app).post(
        "/requirements/parse",
        json={
            "chat_id": CHAT_ID,
            "requirements_text": "Créer un pylône pour ce site.",
            "document_pack_id": spec.pack_id,
            "use_llm": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requirements"] is not None
    assert payload["requirements"]["tower_height_m"] == 42.0
    assert payload["requirements"]["field_evidence"]["tower_height_m"]["explicit"] is True


def test_analysis_rejects_pack_not_attached_to_chat(monkeypatch) -> None:
    """A stale browser cannot analyze a pack now owned by another chat."""

    attached_pack_id = "pack_" + "b" * 12
    requested_pack_id = "pack_" + "c" * 12
    monkeypatch.setattr(
        api_main.workspace_store,
        "get_chat",
        lambda chat_id: {
            "chat_id": chat_id,
            "document_pack_id": attached_pack_id,
        },
    )
    monkeypatch.setattr(
        api_main.workflow_service,
        "parse_requirements",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("workflow parsing must not run for a mismatched pack")
        ),
    )

    response = TestClient(api_main.app).post(
        "/requirements/parse",
        json={
            "chat_id": CHAT_ID,
            "requirements_text": "Créer le site.",
            "document_pack_id": requested_pack_id,
            "use_llm": False,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Les pièces jointes de cette conversation ont changé. "
        "Rechargez la conversation avant de continuer."
    )


def test_design_rejects_omitted_pack_when_chat_still_has_an_attachment(monkeypatch) -> None:
    """Generation must use the same attachment state that the user analyzed."""

    attached_pack_id = "pack_" + "d" * 12
    monkeypatch.setattr(
        api_main.workspace_store,
        "get_chat",
        lambda chat_id: {
            "chat_id": chat_id,
            "document_pack_id": attached_pack_id,
        },
    )
    monkeypatch.setattr(
        api_main.workspace_store,
        "create_for_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("generation must not start with stale attachment state")
        ),
    )

    response = TestClient(api_main.app).post(
        "/designs",
        json={
            "chat_id": CHAT_ID,
            "requirements_text": "Créer le site.",
        },
    )

    assert response.status_code == 409


def test_document_context_digest_changes_when_attached_file_content_changes() -> None:
    """The context receipt must bind the source file identity, not only its display name."""

    def spec_with_digest(digest: str) -> ProjectDesignSpec:
        spec = _confirmed_tower_height_spec(42.0)
        return spec.model_copy(
            update={
                "document_references": [
                    DocumentReference(
                        document_id="doc_height",
                        path="elevation.pdf",
                        filename="elevation.pdf",
                        extension=".pdf",
                        size_bytes=120,
                        sha256=digest,
                        category="elevation_plan",
                        relevance_score=0.95,
                        reason="Plan d’élévation",
                        extractability="text",
                        priority="high",
                        purpose="needed_for_design",
                        used_for_design=True,
                        extraction_status="extracted",
                    )
                ]
            }
        )

    first = build_document_prompt_context(spec_with_digest("a" * 64))
    second = build_document_prompt_context(spec_with_digest("b" * 64))

    assert first.sha256 != second.sha256


def test_context_limit_keeps_critical_site_facts_ahead_of_inventory_details() -> None:
    """A large inventory must not evict the tower facts needed by local analysis."""

    spec = _confirmed_tower_height_spec(42.0)
    source = SourceEvidence(
        document_id="doc_inventory",
        file="inventory.xlsx",
        sheet="Antennes",
        evidence="Inventaire matériel",
    )
    inventory = [
        {
            f"numeric_detail_{index}": ExtractedField(
                field=f"antenna.{index}.numeric_detail",
                value=index,
                status="confirmed",
                confidence=0.9,
                sources=[source],
            )
        }
        for index in range(80)
    ]

    context = build_document_prompt_context(
        spec.model_copy(update={"antenna_inventory": inventory})
    )

    assert "Hauteur du pylône : 42 m." in context.text


@pytest.mark.parametrize(
    ("tower_type", "expected_label"),
    [
        ("lattice_tower", "pylône treillis"),
        ("monopole", "monopole"),
        ("rooftop_mast", "mât de toiture"),
        ("small_cell_pole", "poteau small-cell"),
    ],
)
def test_context_preserves_each_supported_tower_type(
    tower_type: str,
    expected_label: str,
) -> None:
    source = SourceEvidence(
        document_id="doc_rooftop",
        file="roof-plan.pdf",
        page=1,
        evidence="Mât de toiture",
    )
    spec = _confirmed_tower_height_spec(12.0)
    tower_spec = dict(spec.tower_spec)
    tower_spec["tower_type"] = ExtractedField(
        field="tower.tower_type",
        value=tower_type,
        status="confirmed",
        confidence=0.97,
        sources=[source],
    )

    context = build_document_prompt_context(spec.model_copy(update={"tower_spec": tower_spec}))

    assert f"Type de pylône : {expected_label}." in context.text


@pytest.mark.parametrize(
    ("bands", "expected_network"),
    [
        (["L1800"], "4G"),
        (["LTE"], "4G"),
        (["NR700", "NR3500"], "5G"),
        (["5G"], "5G"),
        (["MW"], "MW"),
    ],
)
def test_context_maps_supported_bands_to_network_type(
    bands: list[str],
    expected_network: str,
) -> None:
    source = SourceEvidence(
        document_id="doc_radio",
        file="radio-plan.pdf",
        page=4,
        evidence="Secteur A : L1800",
    )
    spec = _confirmed_tower_height_spec(30.0).model_copy(
        update={
            "radio_sectors": [
                RadioSectorDesign(
                    sector_id="A",
                    azimuth_deg=ExtractedField(
                        field="radio.azimuths_deg",
                        value=0.0,
                        status="confirmed",
                        confidence=0.95,
                        sources=[source],
                    ),
                    hba_m=ExtractedField(
                        field="radio.hba_m",
                        value=24.0,
                        status="confirmed",
                        confidence=0.95,
                        sources=[source],
                    ),
                    bands=ExtractedField(
                        field="radio.bands",
                        value=bands,
                        status="confirmed",
                        confidence=0.95,
                        sources=[source],
                    ),
                )
            ]
        }
    )

    context = build_document_prompt_context(spec)

    assert f"Technologie radio : {expected_network}." in context.text
