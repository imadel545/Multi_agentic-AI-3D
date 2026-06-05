import json as json_module

import httpx

from core.llm.groq import GroqStructuredClient


def test_groq_client_uses_gpt_oss_120b_and_strict_schema(monkeypatch) -> None:
    calls = []

    def post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _response(url, _requirements_content())

    monkeypatch.setattr(httpx, "post", post)

    client = GroqStructuredClient(api_key="test-key")
    spec = client.extract_requirements(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°.",
        "high",
    )

    payload = calls[0]["json"]
    assert spec.network_type == "5G"
    assert calls[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert payload["model"] == "openai/gpt-oss-120b"
    assert payload["temperature"] == 0
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True


def test_groq_client_retries_json_object_mode_after_schema_400(monkeypatch) -> None:
    response_formats = []

    def post(url, headers, json, timeout):
        response_formats.append(json["response_format"]["type"])
        if len(response_formats) == 1:
            return httpx.Response(400, request=httpx.Request("POST", url), json={"error": {}})
        return _response(url, _requirements_content())

    monkeypatch.setattr(httpx, "post", post)

    client = GroqStructuredClient(api_key="test-key")
    spec = client.extract_requirements(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°.",
        "high",
    )

    assert spec.sector_count == 3
    assert response_formats == ["json_schema", "json_object"]


def _response(url: str, content: str) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("POST", url),
        json={"choices": [{"message": {"content": content}}]},
    )


def _requirements_content() -> str:
    return json_module.dumps(
        {
            "network_type": "5G",
            "site_type": "telecom_site",
            "tower_type": "lattice_tower",
            "tower_height_m": 30,
            "sector_count": 3,
            "antenna_type": "panel_5g",
            "antenna_install_height_m": 24,
            "azimuths_deg": [0, 120, 240],
            "mechanical_tilt_deg": 3,
            "electrical_tilt_deg": 0,
            "beamwidth_deg": 65,
            "include_rru": True,
            "include_cables": True,
            "include_beams": True,
            "include_labels": True,
            "detail_level": "high",
            "warnings": [],
        }
    )
