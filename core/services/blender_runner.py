import json
import os
import shutil
import subprocess
import time
import zlib
from binascii import crc32
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

    def generate(self, scene: SceneSpec, output_dir: Path) -> GenerationResult:
        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        scene_spec_path = output_dir / "scene_spec.json"
        scene_spec_path.write_text(
            json.dumps(scene.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
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

        command = [
            str(blender_path),
            "-b",
            "--python",
            str(self.worker_script),
            "--",
            str(scene_spec_path),
            str(output_dir),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
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
            self._write_fallback_artifacts(output_dir, scene, mode="fallback_blender_error")
            return self._result(
                started,
                output_dir,
                "fallback",
                "fallback_blender_error",
                True,
                blender_path=str(blender_path),
                error=(completed.stderr or completed.stdout).strip()[-2000:] or "Blender failed.",
            )
        if not _artifacts_valid(output_dir):
            error_output = (completed.stderr or completed.stdout).strip()[-2000:]
            self._write_fallback_artifacts(
                output_dir, scene, mode="fallback_blender_missing_artifacts"
            )
            return self._result(
                started,
                output_dir,
                "fallback",
                "fallback_blender_missing_artifacts",
                True,
                blender_path=str(blender_path),
                error=error_output or "Blender completed without required artifacts.",
            )
        return self._result(
            started,
            output_dir,
            "generated",
            "real_blender",
            True,
            blender_path=str(blender_path),
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
                    "/Applications/Blender.app/Contents/MacOS/Blender",
                    "/Applications/Blender 4.5.app/Contents/MacOS/Blender",
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
            },
            error=error,
            install_hint=install_hint,
        )

    @staticmethod
    def _write_fallback_artifacts(output_dir: Path, scene: SceneSpec, mode: str) -> None:
        (output_dir / "design.glb").write_bytes(
            b"glTF fallback artifact generated from validated SceneSpec: " + scene.scene_id.encode()
        )
        width, height = scene.preview.resolution
        (output_dir / "preview.png").write_bytes(_minimal_png(width, height))
        (output_dir / "scene_metadata.json").write_text(
            json.dumps(
                {
                    "scene_id": scene.scene_id,
                    "schema_version": scene.schema_version,
                    "generation_mode": mode,
                    "assets_used": _assets_used(scene),
                    "procedural_objects_created": _procedural_objects(scene),
                    "sector_count": len(scene.sectors),
                    "network_type": scene.network_type,
                    "azimuths_deg": [sector.azimuth_deg for sector in scene.sectors],
                    "antenna_heights_m": [sector.install_height_m for sector in scene.sectors],
                    "warnings": [_blender_install_hint()],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _minimal_png(width: int, height: int) -> bytes:
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = crc32(chunk_type + payload) & 0xFFFFFFFF
        return len(payload).to_bytes(4, "big") + chunk_type + payload + checksum.to_bytes(4, "big")

    header = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    row = b"\x00" + (b"\xff\xff\xff" * width)
    image = zlib.compress(row * height, level=9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", image) + chunk(
        b"IEND", b""
    )


def _assets_used(scene: SceneSpec) -> list[str]:
    assets = [scene.tower.asset_id]
    for sector in scene.sectors:
        assets.append(sector.antenna_asset_id)
        if sector.radio_asset_id:
            assets.append(sector.radio_asset_id)
    return sorted(set(assets))


def _procedural_objects(scene: SceneSpec) -> list[str]:
    objects = ["tower"]
    objects.extend(f"antenna:{sector.sector_id}" for sector in scene.sectors)
    objects.extend(f"radio:{sector.sector_id}" for sector in scene.sectors if sector.radio_asset_id)
    objects.extend(f"cable:{sector.sector_id}" for sector in scene.sectors if sector.include_cable)
    if scene.visual_elements.include_sector_beams:
        objects.extend(f"beam:{sector.sector_id}" for sector in scene.sectors)
    if scene.visual_elements.include_azimuth_arrows:
        objects.extend(f"azimuth_arrow:{sector.sector_id}" for sector in scene.sectors)
    if scene.visual_elements.include_height_markers:
        objects.append("height_marker")
    if scene.visual_elements.include_labels:
        objects.append("labels_metadata")
    return objects


def _blender_install_hint() -> str:
    return (
        "Blender executable not found. Install Blender 4.5 LTS, add it to PATH as "
        "`blender`, set BLENDER_BINARY, or set TELECOM_STUDIO_BLENDER_BINARY."
    )


def _artifacts_valid(output_dir: Path) -> bool:
    required = [
        output_dir / "design.glb",
        output_dir / "preview.png",
        output_dir / "scene_metadata.json",
    ]
    return all(path.exists() and path.stat().st_size > 32 for path in required)
