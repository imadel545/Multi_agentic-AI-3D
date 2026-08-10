import pytest
from pydantic import ValidationError

from apps.api.telecom_studio_api.config import Settings


def test_embedding_strict_quality_is_part_of_typed_settings(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_STUDIO_EMBEDDING_STRICT_QUALITY", "true")

    settings = Settings(_env_file=None)

    assert settings.embedding_strict_quality is True


def test_product_embedding_defaults_to_multilingual_nemotron_1024() -> None:
    settings = Settings(_env_file=None)

    assert settings.embedding_model == "nvidia/llama-nemotron-embed-1b-v2"
    assert settings.embedding_dimensions == 1024


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


def test_groq_remote_base_url_must_use_https() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(_env_file=None, groq_base_url="http://api.groq.com/openai/v1")
