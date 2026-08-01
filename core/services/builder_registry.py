from __future__ import annotations

import json
from pathlib import Path

from core.contracts.assembly import BuilderProfileSnapshot, _canonical_sha256


class BuilderRegistry:
    """Versioned deterministic registry for Blender builder capabilities."""

    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._profiles: dict[str, BuilderProfileSnapshot] | None = None

    def resolve(self, profile_id: str) -> BuilderProfileSnapshot:
        profiles = self._load()
        profile = profiles.get(profile_id)
        if profile is None:
            raise ValueError(f"UNKNOWN_BUILDER_PROFILE:{profile_id}")
        return profile

    def list_profiles(self) -> list[BuilderProfileSnapshot]:
        return sorted(self._load().values(), key=lambda profile: profile.profile_id)

    def _load(self) -> dict[str, BuilderProfileSnapshot]:
        if self._profiles is not None:
            return self._profiles
        try:
            payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("BUILDER_PROFILE_CATALOG_INVALID") from exc
        if payload.get("schema_version") != "1.0.0" or not isinstance(
            payload.get("profiles"), list
        ):
            raise ValueError("BUILDER_PROFILE_CATALOG_SCHEMA_UNSUPPORTED")
        profiles: dict[str, BuilderProfileSnapshot] = {}
        for raw in payload["profiles"]:
            if not isinstance(raw, dict):
                raise ValueError("BUILDER_PROFILE_INVALID")
            source = dict(raw)
            source["profile_sha256"] = _canonical_sha256(source)
            profile = BuilderProfileSnapshot.model_validate(source)
            if profile.profile_id in profiles:
                raise ValueError(f"DUPLICATE_BUILDER_PROFILE:{profile.profile_id}")
            profiles[profile.profile_id] = profile
        self._profiles = profiles
        return profiles
