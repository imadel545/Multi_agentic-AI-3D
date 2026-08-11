import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.llm.groq_policy import normalize_groq_base_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TELECOM_STUDIO_", env_file=".env", extra="ignore")

    project_root: Path = Path(__file__).resolve().parents[3]
    asset_manifests_dir: Path | None = None
    asset_library_path: Path | None = None
    outputs_dir: Path | None = None
    qdrant_url: str | None = None
    qdrant_path: Path | None = None
    sqlite_path: Path | None = None
    groq_api_key: str | None = Field(default=None, repr=False, exclude=True)
    groq_api_keys: str | None = Field(default=None, repr=False, exclude=True)
    external_providers_enabled: bool = True
    groq_model: str = "openai/gpt-oss-120b"
    groq_text_model: str | None = None
    groq_vision_model: str = "qwen/qwen3.6-27b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    enable_groq_extraction: bool = True
    enable_groq_planning_decision: bool = True
    enable_groq_asset_selection: bool = True
    enable_groq_geometry_program: bool = True
    enable_groq_vision: bool = False
    enable_groq_visual_design_critic: bool = False
    groq_vision_consent_mode: Literal["per_project_opt_in"] = "per_project_opt_in"
    groq_extraction_timeout_s: float = Field(default=30.0, ge=3.0, le=120.0)
    groq_extraction_max_completion_tokens: int = Field(default=4096, ge=128, le=8192)
    groq_extraction_reasoning_effort: Literal["low", "medium", "high"] = "medium"
    groq_planning_timeout_s: float = Field(default=15.0, ge=3.0, le=60.0)
    groq_planning_max_completion_tokens: int = Field(default=2048, ge=128, le=2048)
    groq_planning_reasoning_effort: Literal["low", "medium", "high"] = "medium"
    groq_asset_selection_timeout_s: float = Field(default=15.0, ge=3.0, le=60.0)
    groq_asset_selection_max_completion_tokens: int = Field(default=1024, ge=128, le=2048)
    groq_asset_selection_reasoning_effort: Literal["low", "medium", "high"] = "medium"
    groq_geometry_timeout_s: float = Field(default=90.0, ge=10.0, le=180.0)
    groq_geometry_max_completion_tokens: int = Field(default=8192, ge=1024, le=16_384)
    groq_geometry_reasoning_effort: Literal["low", "medium", "high"] = "medium"
    groq_vision_timeout_s: float = Field(default=45.0, ge=3.0, le=120.0)
    groq_vision_max_completion_tokens: int = Field(default=2048, ge=128, le=8192)
    groq_vision_max_images: int = Field(default=3, ge=1, le=3)
    groq_vision_max_image_bytes: int = Field(default=20_000_000, ge=1, le=20_000_000)
    groq_vision_max_pixels: int = Field(default=16_000_000, ge=1_000_000, le=16_000_000)
    groq_vision_max_edge_px: int = Field(default=4096, ge=512, le=8192)
    groq_transport_max_retries: int = Field(default=2, ge=0, le=5)
    groq_retry_after_cap_s: float = Field(default=3600.0, ge=1.0, le=86_400.0)
    groq_rate_limit_default_cooldown_s: float = Field(default=60.0, ge=1.0, le=3600.0)
    groq_max_in_flight_per_credential: int = Field(default=2, ge=1, le=16)
    groq_pool_acquire_timeout_s: float = Field(default=10.0, ge=0.1, le=60.0)
    groq_circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    groq_circuit_reset_s: float = Field(default=30.0, ge=1.0, le=600.0)
    blender_binary: str = "blender"
    blender_timeout_s: int = 180
    max_concurrent_workflows: int = Field(default=2, ge=1, le=8)
    max_pending_workflows: int = Field(default=4, ge=0, le=64)
    min_free_disk_mb: int = Field(default=256, ge=64, le=16_384)
    checkpoint_retention_threads: int = Field(default=16, ge=0, le=4096)
    embedding_provider: str = "nvidia"
    embedding_model: str = "nvidia/llama-nemotron-embed-1b-v2"
    embedding_dimensions: int = Field(default=1024, ge=128, le=4096)
    embedding_strict_quality: bool = False
    nvidia_api_key: str | None = Field(default=None, repr=False, exclude=True)
    reranker_provider: str = "nvidia"
    reranker_model: str = "nvidia/llama-nemotron-rerank-1b-v2"
    reranker_base_url: str = "https://ai.api.nvidia.com/v1"
    allow_blender_fallback: bool = False
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    trusted_hosts: str = "127.0.0.1,localhost,testserver"

    @field_validator("groq_model")
    @classmethod
    def validate_groq_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("groq_model must not be empty")
        return normalized

    @field_validator("groq_text_model")
    @classmethod
    def validate_optional_groq_text_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("groq_text_model must not be empty when configured")
        return normalized

    @field_validator("groq_vision_model")
    @classmethod
    def validate_groq_vision_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("groq_vision_model must not be empty")
        return normalized

    @field_validator("groq_base_url")
    @classmethod
    def validate_groq_base_url(cls, value: str) -> str:
        return normalize_groq_base_url(value)

    @property
    def manifests_dir(self) -> Path:
        return self.asset_manifests_dir or self.project_root / "assets" / "manifests"

    @property
    def asset_library_dir(self) -> Path:
        return self.asset_library_path or self.project_root / "assets" / "library"

    @property
    def temp_outputs_dir(self) -> Path:
        return self.outputs_dir or self.project_root / "outputs" / "temp"

    @property
    def local_qdrant_path(self) -> Path:
        return self.qdrant_path or self.project_root / "data" / "qdrant"

    @property
    def local_sqlite_path(self) -> Path:
        return self.sqlite_path or self.project_root / "data" / "sqlite" / "telecom_studio.db"

    @property
    def resolved_groq_api_keys(self) -> tuple[str, ...]:
        if not self.external_providers_enabled:
            return ()
        primary = (
            self.groq_api_key
            or os.getenv("TELECOM_STUDIO_GROQ_API_KEY")
            or os.getenv("GROQ_API_KEY")
            or _read_env_file_value(self.project_root / ".env", ["GROQ_API_KEY", "groq_api"])
        )
        additional = (
            self.groq_api_keys
            or os.getenv("TELECOM_STUDIO_GROQ_API_KEYS")
            or os.getenv("GROQ_API_KEYS")
            or _read_env_file_value(
                self.project_root / ".env",
                ["TELECOM_STUDIO_GROQ_API_KEYS", "GROQ_API_KEYS"],
            )
        )
        ordered = [primary] if primary else []
        ordered.extend(_split_secret_list(additional))
        return tuple(dict.fromkeys(value.strip() for value in ordered if value and value.strip()))

    @property
    def resolved_groq_api_key(self) -> str | None:
        """Compatibility alias for clients whose transport owns credential selection."""

        keys = self.resolved_groq_api_keys
        return keys[0] if keys else None

    @property
    def resolved_groq_text_model(self) -> str:
        """New capability-specific name with compatibility for GROQ_MODEL."""

        return self.groq_text_model or self.groq_model

    @property
    def resolved_nvidia_api_key(self) -> str | None:
        if not self.external_providers_enabled:
            return None
        return (
            self.nvidia_api_key
            or os.getenv("TELECOM_STUDIO_NVIDIA_API_KEY")
            or os.getenv("NVIDIA_API_KEY")
            or _read_env_file_value(
                self.project_root / ".env",
                ["NVIDIA_API_KEY", "TELECOM_STUDIO_NVIDIA_API_KEY", "nvidia_api"],
            )
        )

    @property
    def resolved_blender_binary(self) -> str:
        return os.getenv("BLENDER_BINARY") or self.blender_binary

    @property
    def resolved_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]


def _read_env_file_value(path: Path, names: list[str]) -> str | None:
    if not path.exists():
        return None
    wanted = set(names)
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        if key.strip() in wanted:
            return value.strip().strip('"').strip("'") or None
    return None


def _split_secret_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,;\n]", value) if item.strip()]


settings = Settings()
