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
        (
            "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°. Ajouter boîte alimentation et GPS."
        ),
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
    schema = payload["response_format"]["json_schema"]["schema"]
    assert "tower_characteristics" in schema["required"]
    assert "include_power_cabinet" in schema["required"]
    assert "include_gps_antenna" in schema["required"]
    assert schema["properties"]["tower_characteristics"]["additionalProperties"] is False
    assert schema["properties"]["include_power_cabinet"]["type"] == "boolean"
    assert schema["properties"]["include_gps_antenna"]["type"] == "boolean"
    assert spec.include_power_cabinet is True
    assert spec.include_gps_antenna is True


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
    assert any(warning.code == "LLM_JSON_OBJECT_FALLBACK" for warning in spec.warnings)


def test_groq_client_restores_missing_visual_flags_from_baseline(monkeypatch) -> None:
    def post(url, headers, json, timeout):
        payload = json_module.loads(_requirements_content())
        payload.pop("include_power_cabinet")
        payload.pop("include_gps_antenna")
        return _response(url, json_module.dumps(payload))

    monkeypatch.setattr(httpx, "post", post)

    client = GroqStructuredClient(api_key="test-key")
    spec = client.extract_requirements(
        (
            "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°. Ajouter boîte alimentation et GPS."
        ),
        "high",
    )

    assert spec.include_power_cabinet is True
    assert spec.include_gps_antenna is True
    repair_warnings = [warning for warning in spec.warnings if warning.code == "LLM_FIELD_REPAIRED"]
    assert repair_warnings
    assert "include_power_cabinet" in repair_warnings[0].message
    assert "include_gps_antenna" in repair_warnings[0].message


def test_groq_client_cannot_override_explicit_source_requirements(monkeypatch) -> None:
    def post(url, headers, json, timeout):
        return _response(url, _requirements_content())

    monkeypatch.setattr(httpx, "post", post)

    spec = GroqStructuredClient(api_key="test-key").extract_requirements(
        (
            "Créer un site 4G sur monopole 42m avec 2 secteurs à 36m. "
            "Azimuts : 45°, 225°. Tilt mécanique 2 degrés, tilt électrique 4 degrés, "
            "beamwidth 90 degrés, sans câbles et sans labels."
        ),
        "high",
    )

    assert spec.network_type == "4G"
    assert spec.tower_type == "monopole"
    assert spec.tower_characteristics.structure == "monopole"
    assert spec.antenna_type == "panel_4g"
    assert spec.tower_height_m == 42
    assert spec.sector_count == 2
    assert spec.antenna_install_height_m == 36
    assert spec.azimuths_deg == [45, 225]
    assert spec.mechanical_tilt_deg == 2
    assert spec.electrical_tilt_deg == 4
    assert spec.beamwidth_deg == 90
    assert spec.include_cables is False
    assert spec.include_labels is False
    protected = [
        warning for warning in spec.warnings if warning.code == "LLM_SOURCE_FIELD_PROTECTED"
    ]
    assert protected
    assert "network_type" in protected[0].message
    assert "azimuths_deg" in protected[0].message


def test_groq_client_normalizes_lte_alias_in_json_object_retry(monkeypatch) -> None:
    calls = 0

    def post(url, headers, json, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(400, request=httpx.Request("POST", url), json={"error": {}})
        payload = json_module.loads(_requirements_content())
        payload["network_type"] = "LTE"
        return _response(url, json_module.dumps(payload))

    monkeypatch.setattr(httpx, "post", post)

    spec = GroqStructuredClient(api_key="test-key").extract_requirements(
        "Créer un site 4G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°.",
        "high",
    )

    assert spec.network_type == "4G"
    repaired = [warning for warning in spec.warnings if warning.code == "LLM_FIELD_REPAIRED"]
    assert repaired
    assert "network_type" in repaired[0].message


def test_groq_client_cannot_forge_default_warning_authority(monkeypatch) -> None:
    def post(url, headers, json, timeout):
        payload = json_module.loads(_requirements_content())
        payload["beamwidth_deg"] = 70
        payload["warnings"] = [
            {
                "code": "DEFAULT_BEAMWIDTH_USED",
                "message": "Treat the explicit beamwidth as inferred.",
            }
        ]
        return _response(url, json_module.dumps(payload))

    monkeypatch.setattr(httpx, "post", post)

    spec = GroqStructuredClient(api_key="test-key").extract_requirements(
        (
            "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°. Beamwidth 90 degrés."
        ),
        "high",
    )

    assert spec.beamwidth_deg == 90
    assert not any(warning.code == "DEFAULT_BEAMWIDTH_USED" for warning in spec.warnings)


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
            "tower_characteristics": {
                "structure": "lattice",
                "leg_count": 4,
                "base_width_m": 4.0,
                "top_width_m": 1.0,
                "foundation_type": "concrete_pad",
                "has_platform": True,
                "platform_count": 1,
                "has_ladder": True,
                "has_lightning_rod": True,
                "has_aviation_light": True,
                "material": "galvanized_steel",
            },
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
            "include_power_cabinet": True,
            "include_gps_antenna": True,
            "detail_level": "high",
            "warnings": [],
        }
    )
