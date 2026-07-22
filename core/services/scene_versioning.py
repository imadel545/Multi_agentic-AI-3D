import hashlib
import json
import os
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

    def _active_design_path(self, workflow_id: str) -> Path:
        return self.outputs_dir / workflow_id / "active_design.json"

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
        version_id = self.active_version_id(workflow_id)
        if version_id is not None:
            return self.get_version(workflow_id, version_id)
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
        return None

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

    def commit_active_version(self, workflow_id: str, version_id: str) -> SceneVersion:
        """Publish a completed, hash-verified version as the canonical active design."""

        target = self.get_version(workflow_id, version_id)
        if target is None or target.status != "completed" or not target.artifact_dir:
            raise ValueError("ACTIVE_VERSION_NOT_COMPLETED")
        workflow_dir = (self.outputs_dir / workflow_id).resolve()
        artifact_dir = Path(target.artifact_dir).resolve()
        try:
            relative_artifact_dir = artifact_dir.relative_to(workflow_dir)
        except ValueError as exc:
            raise ValueError("ACTIVE_VERSION_ARTIFACT_DIR_OUTSIDE_WORKFLOW") from exc
        evidence = _verified_completion_evidence(artifact_dir)
        status_path = artifact_dir / "status.json"
        if not status_path.is_file():
            raise ValueError("ACTIVE_VERSION_STATUS_MISSING")
        manifest = {
            "schema_version": "1.0.0",
            "workflow_id": workflow_id,
            "version_id": version_id,
            "artifact_dir": str(relative_artifact_dir),
            "committed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status_sha256": _sha256(status_path),
            "completion_certificate_sha256": _sha256(artifact_dir / "completion_certificate.json"),
            "certified_artifacts": evidence,
        }
        _atomic_write_text(
            self._active_design_path(workflow_id),
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )
        self._set_active_version(workflow_id, version_id)
        return target.model_copy(update={"active": True})

    def active_design_manifest(self, workflow_id: str) -> dict | None:
        path = self._active_design_path(workflow_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("workflow_id") != workflow_id or not isinstance(
            payload.get("version_id"), str
        ):
            return None
        return payload

    def active_version_id(self, workflow_id: str) -> str | None:
        manifest = self.active_design_manifest(workflow_id)
        if manifest is not None:
            return manifest["version_id"]
        av_path = self._active_version_path(workflow_id)
        if not av_path.exists():
            return None
        active = json.loads(av_path.read_text(encoding="utf-8"))
        return active.get("version_id")

    def _write_version(self, version: SceneVersion) -> None:
        vdir = self._versions_dir(version.workflow_id)
        vdir.mkdir(parents=True, exist_ok=True)
        vpath = vdir / f"{version.version_id}.json"
        _atomic_write_text(
            vpath,
            json.dumps(version.model_dump(), indent=2, ensure_ascii=False),
        )

    def _set_active_version(self, workflow_id: str, version_id: str) -> None:
        av_path = self._active_version_path(workflow_id)
        av_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(
            av_path,
            json.dumps({"version_id": version_id}, ensure_ascii=False),
        )


def _atomic_write_text(path: Path, content: str) -> None:
    """Publish a complete JSON document without exposing a partially written file."""

    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _verified_completion_evidence(artifact_dir: Path) -> list[dict]:
    certificate_path = artifact_dir / "completion_certificate.json"
    try:
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("ACTIVE_VERSION_COMPLETION_CERTIFICATE_INVALID") from exc
    if certificate.get("status") != "issued":
        raise ValueError("ACTIVE_VERSION_COMPLETION_CERTIFICATE_NOT_ISSUED")
    artifacts = certificate.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("ACTIVE_VERSION_CERTIFIED_ARTIFACTS_INVALID")
    expected_names = {"glb", "preview", "metadata", "build_lock"}
    evidence: list[dict] = []
    logical_names: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("ACTIVE_VERSION_CERTIFIED_ARTIFACT_INVALID")
        logical_name = item.get("logical_name")
        file_name = item.get("file_name")
        if logical_name not in expected_names or not isinstance(file_name, str):
            raise ValueError("ACTIVE_VERSION_CERTIFIED_ARTIFACT_INVALID")
        path = artifact_dir / file_name
        if (
            not path.is_file()
            or item.get("size_bytes") != path.stat().st_size
            or item.get("sha256") != _sha256(path)
        ):
            raise ValueError(f"ACTIVE_VERSION_ARTIFACT_HASH_MISMATCH:{logical_name}")
        logical_names.add(logical_name)
        evidence.append(
            {
                "logical_name": logical_name,
                "file_name": file_name,
                "size_bytes": path.stat().st_size,
                "sha256": item["sha256"],
            }
        )
    if logical_names != expected_names:
        raise ValueError("ACTIVE_VERSION_CERTIFIED_ARTIFACT_SET_INCOMPLETE")
    return sorted(evidence, key=lambda item: item["logical_name"])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
