import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from core.contracts.scene import SceneSpec


class GenerationResult(BaseModel):
    status: str
    mode: str
    blender_available: bool
    blender_path: str | None = None
    duration_ms: int
    artifacts: dict[str, str]
    error: str | None = None
    install_hint: str | None = None


class BlenderRunner:
    def __init__(
        self,
        project_root: Path,
        blender_binary: str = "blender",
        timeout_s: int = 180,
    ) -> None:
        self.project_root = project_root
        self.blender_binary = blender_binary
        self.timeout_s = timeout_s
        self.worker_script = project_root / "apps" / "blender_worker" / "generate_scene.py"
        self.worker_sources = tuple(sorted((project_root / "apps" / "blender_worker").glob("*.py")))

    def generate(self, scene: SceneSpec, output_dir: Path) -> GenerationResult:
        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        scene_spec_path = output_dir / "scene_spec.json"
        _atomic_write_text(
            scene_spec_path,
            json.dumps(scene.model_dump(), indent=2, ensure_ascii=False),
        )
        blender_path = self._resolve_blender_binary()
        if blender_path is None:
            self._write_fallback_artifacts(output_dir, scene, mode="fallback_no_blender")
            return self._result(
                started,
                output_dir,
                "fallback",
                "fallback_no_blender",
                False,
                install_hint=_blender_install_hint(),
            )

        completed: subprocess.CompletedProcess[str] | None = None
        attempt_errors: list[str] = []
        for attempt in range(1, 4):
            build_id = f"build_{uuid.uuid4().hex}"
            attempt_id = f"{build_id}_attempt_{attempt}"
            staging_dir = Path(tempfile.mkdtemp(prefix=f".blender-{attempt_id}-", dir=output_dir))
            snapshot_script, worker_bundle_snapshot = _snapshot_worker_sources(
                self.worker_sources,
                staging_dir,
                entry_script_name=self.worker_script.name,
            )
            worker_script_sha256 = worker_bundle_snapshot["files"].get(self.worker_script.name)
            if worker_script_sha256 is None:
                shutil.rmtree(staging_dir, ignore_errors=True)
                attempt_errors.append(f"attempt_{attempt}: BLENDER_WORKER_SCRIPT_NOT_IN_BUNDLE")
                continue
            command = [
                str(blender_path),
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "97",
                "--python",
                str(snapshot_script),
                "--",
                str(scene_spec_path),
                str(staging_dir),
            ]
            try:
                completed = self._run_blender_command(command)
            except subprocess.TimeoutExpired as exc:
                shutil.rmtree(staging_dir, ignore_errors=True)
                self._write_fallback_artifacts(output_dir, scene, mode="fallback_blender_timeout")
                return self._result(
                    started,
                    output_dir,
                    "fallback",
                    "fallback_blender_timeout",
                    True,
                    blender_path=str(blender_path),
                    error=str(exc),
                )
            if completed.returncode != 0:
                raw_error = _command_failure_details(completed)
                attempt_errors.append(
                    f"attempt_{attempt}: {raw_error or f'exit_code={completed.returncode}'}"
                )
                shutil.rmtree(staging_dir, ignore_errors=True)
                if attempt < 3:
                    time.sleep(attempt)
                continue

            validation_error = _validate_staged_artifacts(staging_dir, scene)
            if validation_error:
                raw_error = _combined_command_output(completed)[-2000:]
                attempt_errors.append(
                    f"attempt_{attempt}: {validation_error}"
                    + (f"; {raw_error}" if raw_error else "")
                )
                shutil.rmtree(staging_dir, ignore_errors=True)
                if attempt < 3:
                    time.sleep(attempt)
                continue

            _write_build_lock(
                staging_dir=staging_dir,
                scene_spec_path=scene_spec_path,
                worker_script_sha256=worker_script_sha256,
                worker_bundle_snapshot=worker_bundle_snapshot,
                blender_path=blender_path,
                build_id=build_id,
                attempt_id=attempt_id,
                attempt_number=attempt,
            )
            lock_error = _validate_build_lock(
                staging_dir,
                scene_spec_path,
                worker_script_sha256,
                worker_bundle_snapshot,
            )
            if lock_error:
                attempt_errors.append(f"attempt_{attempt}: {lock_error}")
                shutil.rmtree(staging_dir, ignore_errors=True)
                if attempt < 3:
                    time.sleep(attempt)
                continue
            _promote_staged_artifacts(staging_dir, output_dir)
            return self._result(
                started,
                output_dir,
                "generated",
                "real_blender",
                True,
                blender_path=str(blender_path),
            )

        if completed is None or completed.returncode != 0 or attempt_errors:
            self._write_fallback_artifacts(output_dir, scene, mode="fallback_blender_error")
            return self._result(
                started,
                output_dir,
                "fallback",
                "fallback_blender_error",
                True,
                blender_path=str(blender_path),
                error="\n".join(attempt_errors)[-2000:] or "Blender failed.",
            )
        raise RuntimeError("unreachable Blender runner state")

    def _run_blender_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            check=False,
        )

    def _resolve_blender_binary(self) -> Path | None:
        candidates = [
            os.getenv("BLENDER_BINARY"),
            self.blender_binary,
        ]
        if self.blender_binary == "blender":
            candidates.extend(
                [
                    shutil.which("blender"),
                    "/Applications/Blender 4.5 LTS.app/Contents/MacOS/Blender",
                    "/Applications/Blender 4.5.app/Contents/MacOS/Blender",
                    "/Applications/Blender.app/Contents/MacOS/Blender",
                    "/Applications/Blender 4.4.app/Contents/MacOS/Blender",
                    "/Applications/Blender 4.3.app/Contents/MacOS/Blender",
                ]
            )
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if path.exists() and os.access(path, os.X_OK):
                return path
            resolved = shutil.which(str(candidate))
            if resolved:
                return Path(resolved)
        return None

    def _result(
        self,
        started: float,
        output_dir: Path,
        status: str,
        mode: str,
        blender_available: bool,
        blender_path: str | None = None,
        error: str | None = None,
        install_hint: str | None = None,
    ) -> GenerationResult:
        return GenerationResult(
            status=status,
            mode=mode,
            blender_available=blender_available,
            blender_path=blender_path,
            duration_ms=round((time.perf_counter() - started) * 1000),
            artifacts={
                "glb": str(output_dir / "design.glb"),
                "preview": str(output_dir / "preview.png"),
                "metadata": str(output_dir / "scene_metadata.json"),
                "build_lock": str(output_dir / "build.lock.json"),
            },
            error=error,
            install_hint=install_hint,
        )

    def _write_fallback_artifacts(self, output_dir: Path, scene: SceneSpec, mode: str) -> None:
        _clear_generated_artifacts(output_dir)
        asset_imports = _fallback_asset_imports(scene, self.project_root)
        warnings = _unique_strings(
            [
                _blender_install_hint(),
                *[
                    f"{warning}:{record['asset_id']}"
                    for record in asset_imports
                    for warning in record.get("warnings", [])
                ],
            ]
        )
        (output_dir / "scene_metadata.json").write_text(
            json.dumps(
                {
                    "scene_id": scene.scene_id,
                    "schema_version": scene.schema_version,
                    "generation_mode": mode,
                    "assets_used": _assets_used(scene),
                    "procedural_objects_created": _procedural_objects(scene),
                    "asset_imports": asset_imports,
                    "asset_import_summary": _asset_import_summary(asset_imports),
                    "sector_count": len(scene.sectors),
                    "network_type": scene.network_type,
                    "tower_height_m": scene.tower.height_m,
                    "tower_characteristics": scene.tower.characteristics.model_dump(),
                    "azimuths_deg": [sector.azimuth_deg for sector in scene.sectors],
                    "antenna_heights_m": [sector.install_height_m for sector in scene.sectors],
                    "mechanical_tilts_deg": [
                        sector.mechanical_tilt_deg for sector in scene.sectors
                    ],
                    "visual_elements": scene.visual_elements.model_dump(),
                    "accessory_assets": [
                        accessory.model_dump() for accessory in scene.accessory_assets
                    ],
                    "preview_camera": _preview_camera_metadata(scene),
                    "artifacts_available": {
                        "glb": False,
                        "preview": False,
                    },
                    "warnings": warnings,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _assets_used(scene: SceneSpec) -> list[str]:
    assets = [scene.tower.asset_id]
    for sector in scene.sectors:
        assets.append(sector.antenna_asset_id)
        if sector.radio_asset_id:
            assets.append(sector.radio_asset_id)
    for accessory in scene.accessory_assets:
        assets.append(accessory.asset_id)
    return sorted(set(assets))


def _procedural_objects(scene: SceneSpec) -> list[str]:
    objects = ["tower"]
    if scene.tower.characteristics.foundation_type == "concrete_pad":
        objects.append("foundation_concrete_pad")
    if scene.tower.characteristics.has_platform:
        objects.extend(
            f"tower_platform:{index + 1}"
            for index in range(scene.tower.characteristics.platform_count)
        )
    if scene.tower.characteristics.has_ladder:
        objects.append("tower_ladder")
    if scene.tower.characteristics.has_lightning_rod:
        objects.append("tower_lightning_rod")
    if scene.tower.characteristics.has_aviation_light:
        objects.append("tower_aviation_light")
    objects.extend(f"antenna:{sector.sector_id}" for sector in scene.sectors)
    objects.extend(f"radio:{sector.sector_id}" for sector in scene.sectors if sector.radio_asset_id)
    objects.extend(f"cable:{sector.sector_id}" for sector in scene.sectors if sector.include_cable)
    if scene.visual_elements.include_sector_beams:
        objects.extend(f"beam:{sector.sector_id}" for sector in scene.sectors)
    if scene.visual_elements.include_azimuth_arrows:
        objects.extend(f"azimuth_arrow:{sector.sector_id}" for sector in scene.sectors)
    if scene.visual_elements.include_height_markers:
        objects.append("height_marker")
    if scene.visual_elements.include_power_cabinet:
        objects.append("power_cabinet")
    if scene.visual_elements.include_gps_antenna:
        objects.append("gps_antenna")
    if scene.visual_elements.include_labels:
        objects.extend(
            f"label:{sector.sector_id}" for sector in scene.sectors if sector.include_label
        )
        if scene.visual_elements.include_power_cabinet:
            objects.append("label:power_cabinet")
        if scene.visual_elements.include_gps_antenna:
            objects.append("label:gps_antenna")
    return objects


def _fallback_asset_imports(scene: SceneSpec, project_root: Path) -> list[dict]:
    records = [
        _fallback_asset_import_record(
            project_root=project_root,
            asset_id=scene.tower.asset_id,
            asset_file=scene.tower.asset_file,
            asset_source=scene.tower.asset_source,
            asset_metadata=scene.tower.asset_metadata.model_dump(),
            object_role="tower",
            object_name=f"tower_{scene.tower.asset_id}",
            fallback_allowed=scene.tower.import_fallback_allowed,
            dimensions=scene.tower.dimensions_m.model_dump()
            if scene.tower.dimensions_m
            else {
                "height": scene.tower.height_m,
                "width": scene.tower.characteristics.base_width_m,
                "depth": scene.tower.characteristics.base_width_m,
            },
        )
    ]
    for sector in scene.sectors:
        records.append(
            _fallback_asset_import_record(
                project_root=project_root,
                asset_id=sector.antenna_asset_id,
                asset_file=sector.antenna_asset_file,
                asset_source=sector.antenna_asset_source,
                asset_metadata=sector.antenna_asset_metadata.model_dump(),
                object_role="antenna",
                object_name=f"antenna_{sector.sector_id}_{sector.antenna_asset_id}",
                fallback_allowed=sector.antenna_import_fallback_allowed,
                dimensions=sector.antenna_dimensions_m.model_dump()
                if sector.antenna_dimensions_m
                else None,
            )
        )
        if sector.radio_asset_id:
            records.append(
                _fallback_asset_import_record(
                    project_root=project_root,
                    asset_id=sector.radio_asset_id,
                    asset_file=sector.radio_asset_file,
                    asset_source=sector.radio_asset_source,
                    asset_metadata=sector.radio_asset_metadata.model_dump(),
                    object_role="radio",
                    object_name=f"radio_{sector.sector_id}_{sector.radio_asset_id}",
                    fallback_allowed=sector.radio_import_fallback_allowed,
                    dimensions=sector.radio_dimensions_m.model_dump()
                    if sector.radio_dimensions_m
                    else None,
                )
            )
    for accessory in scene.accessory_assets:
        records.append(
            _fallback_asset_import_record(
                project_root=project_root,
                asset_id=accessory.asset_id,
                asset_file=accessory.asset_file,
                asset_source=accessory.asset_source,
                asset_metadata=accessory.asset_metadata.model_dump(),
                object_role=accessory.asset_type,
                object_name=f"{accessory.asset_type}_{accessory.asset_id}",
                fallback_allowed=accessory.import_fallback_allowed,
                dimensions=accessory.dimensions_m.model_dump() if accessory.dimensions_m else None,
            )
        )
    return records


def _fallback_asset_import_record(
    *,
    project_root: Path,
    asset_id: str,
    asset_file: str | None,
    asset_source: str | None,
    asset_metadata: dict | None,
    object_role: str,
    object_name: str,
    fallback_allowed: bool,
    dimensions: dict | None,
) -> dict:
    path = _resolve_asset_path(project_root, asset_file)
    file_exists = bool(path and path.exists())
    mode = "procedural_fallback" if fallback_allowed else "missing_file"
    warnings = ["BLENDER_FALLBACK_ASSET_IMPORT_SKIPPED"]
    if not file_exists:
        warnings.append("ASSET_FILE_MISSING")
    warnings.extend(_asset_source_warnings(asset_source, asset_metadata))
    if not fallback_allowed:
        warnings.append("PROCEDURAL_FALLBACK_NOT_ALLOWED")
    return {
        "asset_id": asset_id,
        "asset_file": asset_file,
        "asset_source": asset_source or "vendor_expected",
        "asset_metadata": asset_metadata or {},
        "object_role": object_role,
        "object_name": object_name,
        "resolved_path": str(path) if path else None,
        "asset_file_exists": file_exists,
        "asset_import_success": False,
        "asset_dimensions_checked": False,
        "manifest_dimensions_m": dimensions,
        "import_fallback_allowed": fallback_allowed,
        "import_mode": mode,
        "effective_generation_mode": mode,
        "imported_object_count": 0,
        "imported_object_names": [],
        "warnings": warnings,
    }


def _resolve_asset_path(project_root: Path, asset_file: str | None) -> Path | None:
    if not asset_file:
        return None
    path = Path(asset_file)
    if path.is_absolute():
        return path
    return project_root / path


def _asset_import_summary(asset_imports: list[dict]) -> dict:
    modes: dict[str, int] = {}
    for record in asset_imports:
        mode = str(record.get("import_mode") or "unknown")
        modes[mode] = modes.get(mode, 0) + 1
    return {
        "asset_count": len(asset_imports),
        "imported_glb_count": modes.get("imported_glb", 0),
        "procedural_fallback_count": modes.get("procedural_fallback", 0),
        "missing_file_count": modes.get("missing_file", 0),
        "import_success_count": sum(
            1 for record in asset_imports if record.get("asset_import_success") is True
        ),
        "asset_file_exists_count": sum(
            1 for record in asset_imports if record.get("asset_file_exists") is True
        ),
        "modes": modes,
    }


def _asset_source_warnings(asset_source: str | None, asset_metadata: dict | None) -> list[str]:
    warnings = []
    if asset_source == "internal_test_minimal":
        warnings.append("INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE")
    if asset_source == "internal_cleaned":
        warnings.append("INTERNAL_CLEANED_ASSET_NOT_VENDOR_GRADE")
    if asset_source == "internal_project_generated":
        warnings.append("INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE")
    if asset_source == "cc_by":
        warnings.append("CC_BY_ASSET_NOT_VENDOR_GRADE")
    if isinstance(asset_metadata, dict) and asset_metadata.get("attribution_required"):
        warnings.append("ATTRIBUTION_REQUIRED")
    return warnings


def _unique_strings(values: list[str]) -> list[str]:
    unique = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _preview_camera_metadata(scene: SceneSpec) -> dict:
    tower_height = scene.tower.height_m
    return {
        "camera": "not_rendered",
        "camera_type": "not_rendered",
        "requested_camera": scene.preview.camera,
        "target": [0.0, 0.0, round(tower_height * 0.52, 3)],
        "ortho_scale": round(max(tower_height * 1.28, 18.0), 3),
        "background": "not_rendered",
    }


def _blender_install_hint() -> str:
    return (
        "Blender executable not found. Install Blender 4.5 LTS, add it to PATH as "
        "`blender`, set BLENDER_BINARY, or set TELECOM_STUDIO_BLENDER_BINARY."
    )


def _combined_command_output(completed: subprocess.CompletedProcess[str]) -> str:
    streams = [
        value.strip() for value in (completed.stdout or "", completed.stderr or "") if value.strip()
    ]
    return "\n".join(streams)


def _command_failure_details(completed: subprocess.CompletedProcess[str]) -> str:
    if completed.returncode < 0:
        try:
            signal_name = signal.Signals(-completed.returncode).name
        except ValueError:
            signal_name = f"SIGNAL_{-completed.returncode}"
        prefix = f"process_terminated_by={signal_name}"
    else:
        prefix = f"exit_code={completed.returncode}"
    output = _combined_command_output(completed)
    return f"{prefix}\n{output}" if output else prefix


def _validate_staged_artifacts(output_dir: Path, scene: SceneSpec) -> str | None:
    # Imported lazily to avoid the qa package's GenerationResult dependency cycle.
    from core.qa.glb_inspector import GLBInspector
    from core.qa.preview_inspector import PreviewInspector

    glb_path = output_dir / "design.glb"
    preview_path = output_dir / "preview.png"
    metadata_path = output_dir / "scene_metadata.json"
    if not metadata_path.exists():
        return "BLENDER_METADATA_MISSING"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "BLENDER_METADATA_INVALID"
    if metadata.get("scene_id") != scene.scene_id:
        return "BLENDER_METADATA_SCENE_ID_MISMATCH"
    if metadata.get("generation_mode") != "real_blender":
        return "BLENDER_METADATA_MODE_INVALID"
    glb_report = GLBInspector().inspect(glb_path, scene, metadata_path)
    if not glb_report.structural_qa_passed:
        return "BLENDER_GLB_INVALID:" + ",".join(glb_report.critical_errors)
    preview_report = PreviewInspector().inspect(preview_path, scene)
    if not preview_report.preview_qa_passed:
        return "BLENDER_PREVIEW_INVALID:" + ",".join(preview_report.critical_errors)
    return None


def _promote_staged_artifacts(staging_dir: Path, output_dir: Path) -> None:
    # The lock is the commit marker: publish it last, after every payload file
    # has been atomically projected into the candidate output directory.
    names = ("design.glb", "preview.png", "scene_metadata.json", "design.blend")
    for name in names:
        source = staging_dir / name
        if source.exists():
            _atomic_copy(source, output_dir / name)
    _atomic_copy(staging_dir / "build.lock.json", output_dir / "build.lock.json")
    shutil.rmtree(staging_dir, ignore_errors=True)


def _clear_generated_artifacts(output_dir: Path) -> None:
    for name in (
        "design.glb",
        "preview.png",
        "scene_metadata.json",
        "design.blend",
        "build.lock.json",
    ):
        path = output_dir / name
        if path.exists():
            path.unlink()


def _write_build_lock(
    *,
    staging_dir: Path,
    scene_spec_path: Path,
    worker_script_sha256: str,
    worker_bundle_snapshot: dict,
    blender_path: Path,
    build_id: str,
    attempt_id: str,
    attempt_number: int,
) -> None:
    metadata_path = staging_dir / "scene_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    artifact_hashes = {
        name: {
            "sha256": _sha256(staging_dir / name),
            "size_bytes": (staging_dir / name).stat().st_size,
        }
        for name in ("design.glb", "preview.png", "scene_metadata.json")
    }
    payload = {
        "schema_version": "1.1.0",
        "build_id": build_id,
        "attempt_id": attempt_id,
        "attempt_number": attempt_number,
        "created_at": datetime.now(UTC).isoformat(),
        "scene_id": metadata.get("scene_id"),
        "scene_spec_sha256": _sha256(scene_spec_path),
        "worker_script_sha256": worker_script_sha256,
        "worker_bundle": worker_bundle_snapshot,
        "blender_binary": str(blender_path),
        "blender_runtime": metadata.get("blender_runtime"),
        "command_profile": {
            "background": True,
            "factory_startup": True,
            "python_exit_code": 97,
        },
        "artifacts": artifact_hashes,
    }
    _atomic_write_text(
        staging_dir / "build.lock.json",
        json.dumps(payload, indent=2, ensure_ascii=False),
    )


def _validate_build_lock(
    output_dir: Path,
    scene_spec_path: Path,
    worker_script_sha256: str,
    worker_bundle_snapshot: dict,
) -> str | None:
    lock_path = output_dir / "build.lock.json"
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "BLENDER_BUILD_LOCK_INVALID"
    try:
        scene_payload = json.loads(scene_spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "BLENDER_BUILD_LOCK_SCENE_INVALID"
    if payload.get("scene_id") != scene_payload.get("scene_id"):
        return "BLENDER_BUILD_LOCK_SCENE_ID_MISMATCH"
    if not isinstance(payload.get("build_id"), str) or not isinstance(
        payload.get("attempt_id"), str
    ):
        return "BLENDER_BUILD_LOCK_IDENTITY_INVALID"
    if payload.get("scene_spec_sha256") != _sha256(scene_spec_path):
        return "BLENDER_BUILD_LOCK_SCENE_MISMATCH"
    if payload.get("worker_script_sha256") != worker_script_sha256:
        return "BLENDER_BUILD_LOCK_WORKER_MISMATCH"
    if payload.get("worker_bundle") != worker_bundle_snapshot:
        return "BLENDER_BUILD_LOCK_WORKER_BUNDLE_MISMATCH"
    command_profile = payload.get("command_profile")
    if command_profile != {
        "background": True,
        "factory_startup": True,
        "python_exit_code": 97,
    }:
        return "BLENDER_BUILD_LOCK_COMMAND_PROFILE_INVALID"
    blender_runtime = payload.get("blender_runtime")
    if (
        not isinstance(blender_runtime, dict)
        or not isinstance(blender_runtime.get("version"), str)
        or not blender_runtime["version"]
        or blender_runtime.get("background") is not True
        or blender_runtime.get("factory_startup") is not True
    ):
        return "BLENDER_BUILD_LOCK_RUNTIME_INVALID"
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return "BLENDER_BUILD_LOCK_ARTIFACTS_INVALID"
    for name in ("design.glb", "preview.png", "scene_metadata.json"):
        evidence = artifacts.get(name)
        path = output_dir / name
        if (
            not isinstance(evidence, dict)
            or not path.is_file()
            or evidence.get("size_bytes") != path.stat().st_size
            or evidence.get("sha256") != _sha256(path)
        ):
            return f"BLENDER_BUILD_LOCK_ARTIFACT_MISMATCH:{name}"
    return None


def _worker_bundle(worker_sources: tuple[Path, ...]) -> dict:
    files = {
        path.name: _sha256(path)
        for path in worker_sources
        if path.is_file() and path.suffix == ".py"
    }
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"files": files, "sha256": digest}


def _snapshot_worker_sources(
    worker_sources: tuple[Path, ...],
    staging_dir: Path,
    *,
    entry_script_name: str,
) -> tuple[Path, dict]:
    """Copy and hash the exact worker source bundle that Blender will execute."""

    snapshot_dir = staging_dir / ".worker_source"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    copied_sources: list[Path] = []
    for source in worker_sources:
        if not source.is_file() or source.suffix != ".py":
            continue
        target = snapshot_dir / source.name
        _atomic_copy(source, target)
        copied_sources.append(target)
    snapshot_script = snapshot_dir / entry_script_name
    if not snapshot_script.is_file():
        raise ValueError("BLENDER_WORKER_SCRIPT_NOT_IN_BUNDLE")
    snapshot = _worker_bundle(tuple(copied_sources))
    return snapshot_script, snapshot


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_copy(source: Path, target: Path) -> None:
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
