import json
import time
import uuid
from pathlib import Path

from core.contracts.scene import SceneSpec
from core.contracts.versioning import SceneVersion


class SceneVersioningService:
    def __init__(self, outputs_dir: Path) -> None:
        self.outputs_dir = outputs_dir

    def _versions_dir(self, workflow_id: str) -> Path:
        return self.outputs_dir / workflow_id / "versions"

    def _active_version_path(self, workflow_id: str) -> Path:
        return self.outputs_dir / workflow_id / "active_version.json"

    def save_version(
        self,
        workflow_id: str,
        scene: SceneSpec,
        parent_version_id: str | None = None,
        edit_description: str | None = None,
        diff_summary: dict | None = None,
        status: str = "pending",
        artifact_dir: str | None = None,
        artifacts: dict[str, str] | None = None,
        qa_score: float | None = None,
        generation_mode: str | None = None,
        activate: bool = True,
    ) -> SceneVersion:
        version_id = f"v{uuid.uuid4().hex[:8]}"
        version = SceneVersion(
            version_id=version_id,
            workflow_id=workflow_id,
            parent_version_id=parent_version_id,
            scene=scene,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            edit_description=edit_description,
            diff_summary=diff_summary or {},
            status=status,
            artifact_dir=artifact_dir,
            artifacts=artifacts or {},
            qa_score=qa_score,
            generation_mode=generation_mode,
            active=activate,
        )
        self._write_version(version)
        if activate:
            self._set_active_version(workflow_id, version_id)
        return version

    def version_artifacts_dir(self, workflow_id: str, version_id: str) -> Path:
        return self._versions_dir(workflow_id) / f"{version_id}_artifacts"

    def update_version(
        self,
        workflow_id: str,
        version_id: str,
        **updates,
    ) -> SceneVersion | None:
        version = self.get_version(workflow_id, version_id)
        if version is None:
            return None
        updated = version.model_copy(update=updates)
        self._write_version(updated)
        return updated

    def get_active_version(self, workflow_id: str) -> SceneVersion | None:
        av_path = self._active_version_path(workflow_id)
        if not av_path.exists():
            # Fallback to scene_spec.json if exists (initial creation)
            spec_path = self.outputs_dir / workflow_id / "scene_spec.json"
            if spec_path.exists():
                scene = SceneSpec.model_validate_json(spec_path.read_text(encoding="utf-8"))
                return SceneVersion(
                    version_id="v_initial",
                    workflow_id=workflow_id,
                    parent_version_id=None,
                    scene=scene,
                    created_at="unknown",
                    edit_description="initial",
                    active=True,
                )
            return None
        active = json.loads(av_path.read_text(encoding="utf-8"))
        version_id = active["version_id"]
        vpath = self._versions_dir(workflow_id) / f"{version_id}.json"
        if not vpath.exists():
            return None
        return SceneVersion.model_validate_json(vpath.read_text(encoding="utf-8"))

    def get_version(self, workflow_id: str, version_id: str) -> SceneVersion | None:
        vpath = self._versions_dir(workflow_id) / f"{version_id}.json"
        if not vpath.exists():
            return None
        return SceneVersion.model_validate_json(vpath.read_text(encoding="utf-8"))

    def list_versions(self, workflow_id: str) -> list[SceneVersion]:
        vdir = self._versions_dir(workflow_id)
        if not vdir.exists():
            return []
        active_id = self.active_version_id(workflow_id)
        versions = []
        for path in sorted(vdir.iterdir()):
            if path.suffix == ".json":
                try:
                    version = SceneVersion.model_validate_json(path.read_text(encoding="utf-8"))
                    versions.append(
                        version.model_copy(update={"active": version.version_id == active_id})
                    )
                except Exception:
                    continue
        return sorted(
            versions,
            key=lambda version: (
                version.created_at,
                version.parent_version_id is not None,
                version.version_id,
            ),
        )

    def rollback(self, workflow_id: str, version_id: str) -> SceneVersion | None:
        target = self.get_version(workflow_id, version_id)
        if target is None:
            return None
        self._set_active_version(workflow_id, version_id)
        return target.model_copy(update={"active": True})

    def active_version_id(self, workflow_id: str) -> str | None:
        av_path = self._active_version_path(workflow_id)
        if not av_path.exists():
            return None
        active = json.loads(av_path.read_text(encoding="utf-8"))
        return active.get("version_id")

    def _write_version(self, version: SceneVersion) -> None:
        vdir = self._versions_dir(version.workflow_id)
        vdir.mkdir(parents=True, exist_ok=True)
        vpath = vdir / f"{version.version_id}.json"
        vpath.write_text(
            json.dumps(version.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _set_active_version(self, workflow_id: str, version_id: str) -> None:
        av_path = self._active_version_path(workflow_id)
        av_path.write_text(
            json.dumps({"version_id": version_id}, ensure_ascii=False), encoding="utf-8"
        )
