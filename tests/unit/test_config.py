from apps.api.telecom_studio_api.config import Settings


def test_embedding_strict_quality_is_part_of_typed_settings(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_STUDIO_EMBEDDING_STRICT_QUALITY", "true")

    settings = Settings(_env_file=None)

    assert settings.embedding_strict_quality is True


def test_product_embedding_defaults_to_multilingual_nemotron_1024() -> None:
    settings = Settings(_env_file=None)

    assert settings.embedding_model == "nvidia/llama-nemotron-embed-1b-v2"
    assert settings.embedding_dimensions == 1024
