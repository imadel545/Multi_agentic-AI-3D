import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TELECOM_STUDIO_", env_file=".env", extra="ignore")

    project_root: Path = Path(__file__).resolve().parents[3]
    asset_manifests_dir: Path | None = None
    asset_library_path: Path | None = None
    outputs_dir: Path | None = None
    qdrant_url: str | None = None
    qdrant_path: Path | None = None
    sqlite_path: Path | None = None
    groq_api_key: str | None = Field(default=None, repr=False)
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    enable_groq_extraction: bool = True
    enable_groq_planning_decision: bool = True
    groq_planning_timeout_s: float = Field(default=15.0, ge=3.0, le=60.0)
    groq_planning_max_completion_tokens: int = Field(default=2048, ge=128, le=2048)
    use_langgraph: bool = True
    blender_binary: str = "blender"
    blender_timeout_s: int = 180
    max_concurrent_workflows: int = Field(default=2, ge=1, le=8)
    max_pending_workflows: int = Field(default=4, ge=0, le=64)
    min_free_disk_mb: int = Field(default=256, ge=64, le=16_384)
    checkpoint_retention_threads: int = Field(default=16, ge=0, le=4096)
    embedding_provider: str = "nvidia"
    embedding_model: str = "baai/bge-m3"
    embedding_strict_quality: bool = False
    nvidia_api_key: str | None = Field(default=None, repr=False)
    reranker_provider: str = "nvidia"
    reranker_model: str = "nvidia/llama-nemotron-rerank-1b-v2"
    reranker_base_url: str = "https://ai.api.nvidia.com/v1"
    allow_blender_fallback: bool = False
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

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
    def resolved_groq_api_key(self) -> str | None:
        return (
            self.groq_api_key
            or os.getenv("TELECOM_STUDIO_GROQ_API_KEY")
            or os.getenv("GROQ_API_KEY")
            or _read_env_file_value(self.project_root / ".env", ["GROQ_API_KEY", "groq_api"])
        )

    @property
    def resolved_nvidia_api_key(self) -> str | None:
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


settings = Settings()
