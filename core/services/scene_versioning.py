import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from pydantic import ValidationError

from core.agents.blueprint_composer import design_blueprint_hash
from core.contracts.completion import CompletionCertificate
from core.contracts.design_blueprint import DesignBlueprint
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.versioning import SceneVersion
from core.performance import scene_spec_hash

_CERTIFIED_ARTIFACTS = {"glb", "preview", "metadata", "build_lock"}
_CRITICAL_REPORT_FILES = (
    ("qa_report", "qa_report.json"),
    ("geometry_validation", "geometry_validation.json"),
    ("glb_inspection", "glb_inspection.json"),
    ("requirement_coverage", "requirement_coverage.json"),
    ("design_blueprint", "design_blueprint.json"),
    ("blueprint_requirement_coverage", "blueprint_requirement_coverage.json"),
    ("blueprint_scene_coverage", "blueprint_scene_coverage.json"),
    ("quality_gates", "quality_gates.json"),
)
_REQUIRED_CRITICAL_REPORTS_V1 = {
    "qa_report",
    "geometry_validation",
    "glb_inspection",
}
_REQUIRED_CRITICAL_REPORTS_V1_1 = {
    *_REQUIRED_CRITICAL_REPORTS_V1,
    "design_blueprint",
    "blueprint_requirement_coverage",
    "blueprint_scene_coverage",
}
_REPORT_PROOF_FILE = "critical_reports.proof.json"
_REPORT_PROOF_PROFILE = "critical-reports-v1"
_REQUIRED_COMPLETION_CHECKS_V1 = {
    "requirements_present",
    "scene_spec_present",
    "requirement_coverage_passed",
    "pre_blender_gate_passed",
    "real_blender_generation",
    "required_artifacts_regular_files",
    "artifact_hashes_recorded",
    "qa_report_passed",
    "glb_binary_integrity_passed",
    "semantic_mesh_coverage_complete",
    "geometry_validation_passed",
    "mesh_qa_passed",
    "preview_qa_passed",
    "post_blender_gate_passed",
    "no_critical_fallback",
}
_REQUIRED_COMPLETION_CHECKS_V1_1 = {
    *_REQUIRED_COMPLETION_CHECKS_V1,
    "design_blueprint_present",
    "blueprint_requirement_coverage_passed",
    "blueprint_scene_coverage_passed",
}


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
        if self._active_design_path(workflow_id).exists():
            return self.get_verified_active_version(workflow_id)
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

    def get_verified_active_version(self, workflow_id: str) -> SceneVersion | None:
        """Return the active version only when its scene and certified artifact agree."""

        manifest = self.active_design_manifest(workflow_id)
        if manifest is None:
            return None
        version_id = manifest["version_id"]
        target = self.get_version(workflow_id, version_id)
        if target is None or target.status != "completed" or not target.artifact_dir:
            raise ValueError("ACTIVE_DESIGN_VERSION_INVALID")
        workflow_dir = (self.outputs_dir / workflow_id).resolve()
        manifest_artifact_dir = (workflow_dir / manifest.get("artifact_dir", "")).resolve()
        target_artifact_dir = Path(target.artifact_dir).resolve()
        try:
            manifest_artifact_dir.relative_to(workflow_dir)
            target_artifact_dir.relative_to(workflow_dir)
        except ValueError as exc:
            raise ValueError("ACTIVE_VERSION_ARTIFACT_DIR_OUTSIDE_WORKFLOW") from exc
        if target_artifact_dir != manifest_artifact_dir:
            raise ValueError("ACTIVE_DESIGN_VERSION_ARTIFACT_DIR_MISMATCH")
        self.verified_active_status_path(workflow_id)
        return target.model_copy(update={"active": True})

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
        evidence = verify_persisted_version(
            artifact_dir,
            workflow_id=workflow_id,
            expected_scene=target.scene,
            require_report_proof=False,
        )
        build_lock_schema = _build_lock_schema(artifact_dir)
        report_proof = None
        if build_lock_schema == "1.1.0":
            report_proof = _write_critical_report_proof(artifact_dir)
        status_path = artifact_dir / "status.json"
        manifest = {
            "schema_version": "1.1.0" if report_proof is not None else "1.0.0",
            "workflow_id": workflow_id,
            "version_id": version_id,
            "artifact_dir": str(relative_artifact_dir),
            "committed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status_sha256": _sha256(status_path),
            "completion_certificate_sha256": _sha256(artifact_dir / "completion_certificate.json"),
            "certified_artifacts": evidence,
        }
        if report_proof is not None:
            manifest.update(
                {
                    "evidence_profile": _REPORT_PROOF_PROFILE,
                    "critical_reports_proof_sha256": _sha256(artifact_dir / _REPORT_PROOF_FILE),
                    "critical_reports": report_proof["artifacts"],
                }
            )
        # active_version.json is a compatibility projection. The verified
        # active_design.json manifest remains the final canonical commit marker.
        self._set_active_version(workflow_id, version_id)
        _atomic_write_text(
            self._active_design_path(workflow_id),
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )
        return target.model_copy(update={"active": True})

    def verified_active_status_path(self, workflow_id: str) -> Path:
        """Resolve and fully revalidate the currently published design."""

        manifest = self.active_design_manifest(workflow_id)
        if manifest is None:
            raise ValueError("ACTIVE_DESIGN_MANIFEST_INVALID")
        workflow_dir = (self.outputs_dir / workflow_id).resolve()
        artifact_dir = (workflow_dir / manifest.get("artifact_dir", "")).resolve()
        try:
            artifact_dir.relative_to(workflow_dir)
        except ValueError as exc:
            raise ValueError("ACTIVE_VERSION_ARTIFACT_DIR_OUTSIDE_WORKFLOW") from exc
        target = self.get_version(workflow_id, manifest["version_id"])
        if target is None or target.status != "completed" or not target.artifact_dir:
            raise ValueError("ACTIVE_DESIGN_VERSION_INVALID")
        if Path(target.artifact_dir).resolve() != artifact_dir:
            raise ValueError("ACTIVE_DESIGN_VERSION_ARTIFACT_DIR_MISMATCH")
        evidence = verify_persisted_version(
            artifact_dir,
            workflow_id=workflow_id,
            expected_scene=target.scene,
        )
        status_path = artifact_dir / "status.json"
        certificate_path = artifact_dir / "completion_certificate.json"
        if manifest.get("status_sha256") != _sha256(status_path):
            raise ValueError("ACTIVE_DESIGN_STATUS_HASH_MISMATCH")
        if manifest.get("completion_certificate_sha256") != _sha256(certificate_path):
            raise ValueError("ACTIVE_DESIGN_COMPLETION_CERTIFICATE_HASH_MISMATCH")
        if manifest.get("certified_artifacts") != evidence:
            raise ValueError("ACTIVE_DESIGN_CERTIFIED_ARTIFACTS_MISMATCH")
        schema_version = manifest.get("schema_version")
        if schema_version == "1.1.0":
            report_proof = _verify_critical_report_proof(artifact_dir)
            if manifest.get("evidence_profile") != _REPORT_PROOF_PROFILE:
                raise ValueError("ACTIVE_DESIGN_EVIDENCE_PROFILE_INVALID")
            if manifest.get("critical_reports_proof_sha256") != _sha256(
                artifact_dir / _REPORT_PROOF_FILE
            ):
                raise ValueError("ACTIVE_DESIGN_CRITICAL_REPORT_PROOF_HASH_MISMATCH")
            if manifest.get("critical_reports") != report_proof["artifacts"]:
                raise ValueError("ACTIVE_DESIGN_CRITICAL_REPORTS_MISMATCH")
        elif schema_version != "1.0.0":
            raise ValueError("ACTIVE_DESIGN_SCHEMA_UNSUPPORTED")
        return status_path

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
        _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_persisted_version(
    artifact_dir: Path,
    *,
    workflow_id: str,
    expected_scene: SceneSpec | None = None,
    require_report_proof: bool = True,
) -> list[dict]:
    """Fail closed unless a persisted Blender result proves its full completion chain."""

    if not artifact_dir.is_dir():
        raise ValueError("ACTIVE_VERSION_ARTIFACT_DIR_MISSING")
    certificate_path = artifact_dir / "completion_certificate.json"
    try:
        certificate = CompletionCertificate.model_validate_json(
            certificate_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise ValueError("ACTIVE_VERSION_COMPLETION_CERTIFICATE_INVALID") from exc
    if certificate.workflow_id != workflow_id:
        raise ValueError("ACTIVE_VERSION_COMPLETION_CERTIFICATE_WORKFLOW_MISMATCH")
    if certificate.status != "issued":
        raise ValueError("ACTIVE_VERSION_COMPLETION_CERTIFICATE_NOT_ISSUED")
    if certificate.generation_mode != "real_blender":
        raise ValueError("ACTIVE_VERSION_COMPLETION_MODE_INVALID")
    if certificate.blockers:
        raise ValueError("ACTIVE_VERSION_COMPLETION_BLOCKERS_PRESENT")
    required_checks = (
        _REQUIRED_COMPLETION_CHECKS_V1_1
        if certificate.schema_version == "1.1.0"
        else _REQUIRED_COMPLETION_CHECKS_V1
    )
    if set(certificate.checks) != required_checks or not all(certificate.checks.values()):
        raise ValueError("ACTIVE_VERSION_COMPLETION_CHECKS_INVALID")

    _read_model(
        artifact_dir / "requirements_spec.json",
        RequirementSpec,
        "ACTIVE_VERSION_REQUIREMENTS_INVALID",
    )
    scene = _read_model(
        artifact_dir / "scene_spec.json",
        SceneSpec,
        "ACTIVE_VERSION_SCENE_SPEC_INVALID",
    )
    blueprint = (
        _read_model(
            artifact_dir / "design_blueprint.json",
            DesignBlueprint,
            "ACTIVE_VERSION_DESIGN_BLUEPRINT_INVALID",
        )
        if certificate.schema_version == "1.1.0"
        else None
    )
    if certificate.requirements_sha256 != _persisted_json_hash(
        artifact_dir / "requirements_spec.json",
        exclude={"warnings", "repair_events"},
    ):
        raise ValueError("ACTIVE_VERSION_REQUIREMENTS_HASH_MISMATCH")
    if certificate.scene_spec_sha256 != _persisted_json_hash(artifact_dir / "scene_spec.json"):
        raise ValueError("ACTIVE_VERSION_SCENE_SPEC_HASH_MISMATCH")
    if blueprint is not None and (
        certificate.design_blueprint_sha256 != design_blueprint_hash(blueprint)
    ):
        raise ValueError("ACTIVE_VERSION_DESIGN_BLUEPRINT_HASH_MISMATCH")
    if expected_scene is not None and scene_spec_hash(expected_scene) != scene_spec_hash(scene):
        raise ValueError("ACTIVE_VERSION_SCENE_VERSION_MISMATCH")

    evidence: list[dict] = []
    logical_names: set[str] = set()
    for item in certificate.artifacts:
        logical_name = item.logical_name
        path = (artifact_dir / item.file_name).resolve()
        try:
            path.relative_to(artifact_dir.resolve())
        except ValueError as exc:
            raise ValueError("ACTIVE_VERSION_CERTIFIED_ARTIFACT_OUTSIDE_VERSION") from exc
        if (
            not path.is_file()
            or item.size_bytes != path.stat().st_size
            or item.sha256 != _sha256(path)
        ):
            raise ValueError(f"ACTIVE_VERSION_ARTIFACT_HASH_MISMATCH:{logical_name}")
        logical_names.add(logical_name)
        evidence.append(
            {
                "logical_name": logical_name,
                "file_name": item.file_name,
                "size_bytes": path.stat().st_size,
                "sha256": item.sha256,
            }
        )
    if logical_names != _CERTIFIED_ARTIFACTS:
        raise ValueError("ACTIVE_VERSION_CERTIFIED_ARTIFACT_SET_INCOMPLETE")
    build_lock_schema = _verify_build_lock(artifact_dir, scene=scene)
    if require_report_proof and build_lock_schema == "1.1.0":
        _verify_critical_report_proof(artifact_dir)
    _verify_terminal_status(artifact_dir / "status.json", workflow_id=workflow_id)
    return sorted(evidence, key=lambda item: item["logical_name"])


def _read_model(path: Path, model_type, error_code: str):
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ValueError(error_code) from exc


def _persisted_json_hash(path: Path, *, exclude: set[str] | None = None) -> str:
    """Hash the JSON fields that were actually certified and persisted.

    Re-serializing a persisted payload through a newer Pydantic model would inject
    newly introduced default fields and invalidate an otherwise unchanged historic
    certificate. Validation still uses the current model, while the digest remains
    tied to the exact logical JSON payload that the issuing runtime observed.
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("ACTIVE_VERSION_CERTIFIED_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("ACTIVE_VERSION_CERTIFIED_JSON_INVALID")
    for field_name in exclude or set():
        payload.pop(field_name, None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_lock_schema(artifact_dir: Path) -> str:
    try:
        payload = json.loads((artifact_dir / "build.lock.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_INVALID") from exc
    schema_version = payload.get("schema_version")
    if schema_version not in {"1.0.0", "1.1.0"}:
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_SCHEMA_UNSUPPORTED")
    return schema_version


def _critical_report_evidence(artifact_dir: Path) -> list[dict]:
    evidence: list[dict] = []
    for logical_name, file_name in _CRITICAL_REPORT_FILES:
        path = artifact_dir / file_name
        if not path.is_file():
            continue
        evidence.append(
            {
                "logical_name": logical_name,
                "file_name": file_name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return evidence


def _write_critical_report_proof(artifact_dir: Path) -> dict:
    evidence = _critical_report_evidence(artifact_dir)
    logical_names = {item["logical_name"] for item in evidence}
    missing = sorted(_REQUIRED_CRITICAL_REPORTS_V1_1 - logical_names)
    if missing:
        raise ValueError("ACTIVE_VERSION_CRITICAL_REPORTS_MISSING:" + ",".join(missing))
    payload = {
        "schema_version": "1.1.0",
        "evidence_profile": _REPORT_PROOF_PROFILE,
        "artifacts": evidence,
    }
    _atomic_write_text(
        artifact_dir / _REPORT_PROOF_FILE,
        json.dumps(payload, indent=2, ensure_ascii=False),
    )
    return payload


def _verify_critical_report_proof(artifact_dir: Path) -> dict:
    proof_path = artifact_dir / _REPORT_PROOF_FILE
    try:
        payload = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("ACTIVE_VERSION_CRITICAL_REPORT_PROOF_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") not in {"1.0.0", "1.1.0"}
        or payload.get("evidence_profile") != _REPORT_PROOF_PROFILE
        or not isinstance(payload.get("artifacts"), list)
    ):
        raise ValueError("ACTIVE_VERSION_CRITICAL_REPORT_PROOF_INVALID")
    expected = _critical_report_evidence(artifact_dir)
    if payload["artifacts"] != expected:
        raise ValueError("ACTIVE_VERSION_CRITICAL_REPORT_HASH_MISMATCH")
    logical_names = {
        item.get("logical_name") for item in payload["artifacts"] if isinstance(item, dict)
    }
    required_reports = (
        _REQUIRED_CRITICAL_REPORTS_V1_1
        if payload.get("schema_version") == "1.1.0"
        else _REQUIRED_CRITICAL_REPORTS_V1
    )
    if not required_reports.issubset(logical_names):
        raise ValueError("ACTIVE_VERSION_CRITICAL_REPORT_SET_INCOMPLETE")
    return payload


def _verify_build_lock(artifact_dir: Path, *, scene: SceneSpec) -> str:
    lock_path = artifact_dir / "build.lock.json"
    scene_path = artifact_dir / "scene_spec.json"
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_INVALID") from exc
    schema_version = _build_lock_schema(artifact_dir)
    if payload.get("scene_id") != scene.scene_id:
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_SCENE_ID_MISMATCH")
    if payload.get("scene_spec_sha256") != _sha256(scene_path):
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_SCENE_HASH_MISMATCH")
    if not isinstance(payload.get("build_id"), str) or not isinstance(
        payload.get("attempt_id"), str
    ):
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_IDENTITY_INVALID")
    worker_hash = payload.get("worker_script_sha256")
    if not isinstance(worker_hash, str) or len(worker_hash) != 64:
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_WORKER_IDENTITY_INVALID")
    if schema_version == "1.1.0":
        bundle = payload.get("worker_bundle")
        if not _valid_worker_bundle(bundle):
            raise ValueError("ACTIVE_VERSION_BUILD_LOCK_WORKER_BUNDLE_INVALID")
    if payload.get("command_profile") != {
        "background": True,
        "factory_startup": True,
        "python_exit_code": 97,
    }:
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_COMMAND_PROFILE_INVALID")
    runtime = payload.get("blender_runtime")
    if (
        not isinstance(runtime, dict)
        or not isinstance(runtime.get("version"), str)
        or not runtime["version"]
        or runtime.get("background") is not True
        or runtime.get("factory_startup") is not True
    ):
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_RUNTIME_INVALID")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("ACTIVE_VERSION_BUILD_LOCK_ARTIFACTS_INVALID")
    for name in ("design.glb", "preview.png", "scene_metadata.json"):
        item = artifacts.get(name)
        path = artifact_dir / name
        if (
            not isinstance(item, dict)
            or not path.is_file()
            or item.get("size_bytes") != path.stat().st_size
            or item.get("sha256") != _sha256(path)
        ):
            raise ValueError(f"ACTIVE_VERSION_BUILD_LOCK_ARTIFACT_MISMATCH:{name}")
    return schema_version


def _valid_worker_bundle(bundle: object) -> bool:
    if not isinstance(bundle, dict):
        return False
    files = bundle.get("files")
    digest = bundle.get("sha256")
    if (
        not isinstance(files, dict)
        or not files
        or not isinstance(digest, str)
        or len(digest) != 64
        or not all(
            isinstance(name, str) and name and isinstance(value, str) and len(value) == 64
            for name, value in files.items()
        )
    ):
        return False
    return (
        digest
        == hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )


def _verify_terminal_status(status_path: Path, *, workflow_id: str) -> None:
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("ACTIVE_VERSION_STATUS_INVALID") from exc
    if (
        payload.get("workflow_id") != workflow_id
        or payload.get("status") != "completed"
        or payload.get("completion_certificate_status") != "issued"
        or payload.get("generation_mode") != "real_blender"
    ):
        raise ValueError("ACTIVE_VERSION_STATUS_NOT_CERTIFIED")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
