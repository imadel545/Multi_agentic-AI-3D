from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.api.telecom_studio_api.config import Settings


def test_manifest_catalog_must_match_the_project_canonical_catalog(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    expected = project_root / "assets" / "manifests"

    configured = Settings(
        _env_file=None,
        project_root=project_root,
        asset_manifests_dir=expected,
    )

    assert configured.manifests_dir.resolve() == expected.resolve()
    with pytest.raises(
        ValidationError,
        match="asset_manifests_dir must resolve to project_root/assets/manifests",
    ):
        Settings(
            _env_file=None,
            project_root=project_root,
            asset_manifests_dir=tmp_path / "external-catalog",
        )


def test_embedding_strict_quality_is_part_of_typed_settings(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_STUDIO_EMBEDDING_STRICT_QUALITY", "true")

    settings = Settings(_env_file=None)

    assert settings.embedding_strict_quality is True


def test_product_embedding_defaults_to_multilingual_nemotron_3() -> None:
    settings = Settings(_env_file=None)

    assert settings.embedding_model == "nvidia/nemotron-3-embed-1b"
    assert settings.embedding_dimensions == 2048
    assert settings.embedding_timeout_s == 30.0
    assert settings.reranker_provider == "passthrough"


def test_groq_defaults_match_bounded_gpt_oss_runtime_policy() -> None:
    settings = Settings(_env_file=None)

    assert settings.groq_model == "openai/gpt-oss-120b"
    assert settings.groq_base_url == "https://api.groq.com/openai/v1"
    assert settings.groq_extraction_reasoning_effort == "medium"
    assert settings.groq_planning_reasoning_effort == "medium"
    assert settings.groq_asset_selection_reasoning_effort == "medium"
    assert settings.resolved_groq_text_model == "openai/gpt-oss-120b"
    assert settings.groq_vision_model == "qwen/qwen3.6-27b"
    assert settings.enable_groq_vision is False
    assert settings.enable_groq_visual_design_critic is False
    assert settings.groq_vision_consent_mode == "per_project_opt_in"
    assert settings.groq_vision_max_images == 3
    assert settings.groq_vision_max_image_bytes == 20_000_000


def test_capability_specific_text_model_overrides_legacy_model() -> None:
    settings = Settings(
        _env_file=None,
        groq_model="legacy/text-model",
        groq_text_model="preferred/text-model",
    )

    assert settings.groq_model == "legacy/text-model"
    assert settings.resolved_groq_text_model == "preferred/text-model"


def test_external_provider_kill_switch_hides_all_credentials(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "must-not-be-resolved")
    monkeypatch.setenv("TELECOM_STUDIO_GROQ_API_KEYS", "also-hidden-1,also-hidden-2")
    monkeypatch.setenv("NVIDIA_API_KEY", "must-not-be-resolved")

    settings = Settings(_env_file=None, external_providers_enabled=False)

    assert settings.resolved_groq_api_key is None
    assert settings.resolved_groq_api_keys == ()
    assert settings.resolved_nvidia_api_key is None


def test_groq_credential_pool_keeps_legacy_primary_and_deduplicates(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "primary-key")
    monkeypatch.setenv(
        "TELECOM_STUDIO_GROQ_API_KEYS",
        "secondary-key, primary-key ; tertiary-key",
    )

    settings = Settings(_env_file=None, external_providers_enabled=True)

    assert settings.resolved_groq_api_key == "primary-key"
    assert settings.resolved_groq_api_keys == (
        "primary-key",
        "secondary-key",
        "tertiary-key",
    )


def test_explicit_groq_pool_is_secret_in_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        groq_api_key="primary-secret",
        groq_api_keys="secondary-secret",
    )

    rendered = repr(settings)

    assert "primary-secret" not in rendered
    assert "secondary-secret" not in rendered
    dumped = settings.model_dump()
    assert "groq_api_key" not in dumped
    assert "groq_api_keys" not in dumped


def test_groq_remote_base_url_must_use_https() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(_env_file=None, groq_base_url="http://api.groq.com/openai/v1")


def test_local_http_boundary_defaults_are_explicit(monkeypatch) -> None:
    monkeypatch.delenv("TELECOM_STUDIO_AUTH_ENABLED")
    settings = Settings(_env_file=None)

    assert settings.resolved_cors_origins == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    assert settings.resolved_trusted_hosts == ["127.0.0.1", "localhost", "testserver"]
    assert settings.auth_enabled is True
    assert settings.auth_cookie_name == "telecom_studio_session"
    assert settings.auth_session_ttl_seconds == 28_800


def test_auth_cookie_name_rejects_cookie_header_metacharacters() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_cookie_name="studio; Path=/")


def test_trusted_hosts_can_be_configured_for_a_local_dns_name() -> None:
    settings = Settings(
        _env_file=None,
        trusted_hosts="127.0.0.1, studio.internal.test ",
    )

    assert settings.resolved_trusted_hosts == ["127.0.0.1", "studio.internal.test"]
