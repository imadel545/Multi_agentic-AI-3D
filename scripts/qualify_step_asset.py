"""Create local qualification evidence for one STEP telecom candidate.

The command is a product-facing evidence boundary, not a catalogue publisher.
It reads a neutral STEP source, preserves its source hash and hierarchy, creates
real Blender/GLB evidence, measures the persisted GLB in a fresh Blender
process, and records bounded visual checks.  The resulting record always keeps
``generation_eligible`` false until a separate rights and engineering review
admits the asset.

Example::

    python -m scripts.qualify_step_asset /path/to/6001124.step \
        --output /tmp/6001124-evidence \
        --manufacturer 'Sierra Wireless / Semtech' --reference 6001124 \
        --semantic-role lte_mimo_panel_antenna \
        --connector-summary 'Two SMA plugs and two 3 m RG174 cables (datasheet)' \
        --mounting-summary 'Bolt mount with 18 mm mounting hole (datasheet)'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import time
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from core.services.blender_runner import BlenderRunner
from core.services.step_mesh_extraction import extract_step_mesh

_PREVIEW_FILES = {
    "perspective": "preview.png",
    "front": "preview_front.png",
    "side": "preview_side.png",
    "top": "preview_top.png",
    "closeup": "preview_closeup.png",
}


def qualify(
    source: Path,
    output: Path,
    *,
    manufacturer: str | None = None,
    reference: str | None = None,
    semantic_role: str | None = None,
    source_url: str | None = None,
    datasheet_url: str | None = None,
    connector_summaries: list[str] | None = None,
    mounting_summaries: list[str] | None = None,
    blender: str = "blender",
    linear_deflection_m: float = 0.00015,
) -> dict:
    """Run bounded STEP, Blender, post-Blender and preview qualification checks."""

    source = source.resolve(strict=True)
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "Qualification output must be new or empty; existing evidence is preserved."
        )
    output.mkdir(parents=True, exist_ok=True)
    source_hash = _hash(source)
    started = time.monotonic()
    report: dict = {
        "schema_version": "professional_asset_qualification.v1",
        "status": "inspecting",
        "professional_asset_admission": False,
        "generation_eligible": False,
        "identity": {
            "manufacturer": manufacturer,
            "reference": reference,
            "semantic_role": semantic_role,
        },
        "provenance": {
            "source_file_name": source.name,
            "source_file_sha256": source_hash,
            "source_format": "step",
            "source_url": source_url,
            "datasheet_url": datasheet_url,
        },
        "rights": {
            "status": "review_required",
            "redistribution_authorized": False,
            "notice": "Source terms must be accepted and reviewed before any catalogue admission.",
        },
    }
    try:
        extraction = extract_step_mesh(
            source,
            linear_deflection_m=linear_deflection_m,
        )
        extraction_path = output / "extraction.json"
        extraction_path.write_text(json.dumps(extraction, indent=2) + "\n", encoding="utf-8")
        report["source_units"] = extraction["source_units"]
        report["hierarchy"] = {
            "preserved": extraction["qualification"]["hierarchy_preserved"],
            "counts": extraction["counts"],
            "components": [
                {
                    "name": node["name"],
                    "occurrence_name": node.get("occurrence_name"),
                    "definition_entry": node.get("definition_entry"),
                    "entity_handle": node.get("entity_handle"),
                    "kind": node["kind"],
                    "source_face_count": node.get("source_face_count"),
                    "triangle_count": node.get("triangle_count"),
                    "bounding_box_m": node.get("bounding_box_m"),
                }
                for node in extraction["nodes"]
            ],
        }
        report["dimensions"] = {
            "extracted_assembly": {
                "bounding_box_m": extraction["bounding_box_m"],
                "dimensions_m": extraction["dimensions_m"],
            },
            "interpretation": "Overall extents include every extracted part, including cable runs.",
        }
        report["connectors"] = {
            "summaries": list(connector_summaries or []),
            "status": "unverified",
            "anchor_coordinates": "unverified",
            "mating_fit": "unverified",
        }
        report["mounting"] = {
            "summaries": list(mounting_summaries or []),
            "status": "unverified",
            "anchor_coordinates": "unverified",
        }

        root = Path(__file__).resolve().parents[1]
        binary = BlenderRunner(root, blender)._resolve_blender_binary()
        if binary is None:
            raise ValueError("Blender is required; no placeholder output is generated.")
        blender_log = output / "blender.log"
        with blender_log.open("wb") as log:
            subprocess.run(
                [
                    str(binary),
                    "--background",
                    "--factory-startup",
                    "--python-exit-code",
                    "1",
                    "--python",
                    str(root / "tools" / "import_native_cad_mesh.py"),
                    "--",
                    str(extraction_path),
                    str(output),
                ],
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=180,
            )
        blender_validation = json.loads(
            (output / "blender_validation.json").read_text(encoding="utf-8")
        )
        if not blender_validation.get("geometry_roundtrip", {}).get("passed"):
            raise ValueError("Blender geometry roundtrip failed.")
        report["blender"] = blender_validation

        post_report_path = output / "post_blender_measurement.json"
        post_log = output / "post_blender.log"
        with post_log.open("wb") as log:
            subprocess.run(
                [
                    str(binary),
                    "--background",
                    "--factory-startup",
                    "--python-exit-code",
                    "1",
                    "--python",
                    str(root / "scripts" / "inspect_exported_glb.py"),
                    "--",
                    str(output / "source_mesh.glb"),
                    str(post_report_path),
                ],
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=120,
            )
        post_blender = json.loads(post_report_path.read_text(encoding="utf-8"))
        report["post_blender"] = post_blender
        report["fidelity"] = {
            "source_geometry": extraction["qualification"]["geometry_fidelity"],
            "roundtrip_passed": blender_validation["geometry_roundtrip"]["passed"],
            "maximum_vertex_error_m": blender_validation["geometry_roundtrip"][
                "maximum_vertex_error_m"
            ],
            "post_blender_mesh_count": post_blender["mesh_count"],
            "post_blender_vertex_count": post_blender["vertex_count"],
            "post_blender_triangle_count": post_blender["triangle_count"],
            "identity_count": post_blender["component_identity_count"],
        }
        report["visual_quality"] = _inspect_previews(output)
        report["adaptation_boundaries"] = {
            "source_geometry_editable": False,
            "source_materials_editable": False,
            "scale_editable": False,
            "anchors_usable": False,
            "allowed_product_action": "reference_only_review",
            "limitations": [
                (
                    "The current evidence can be inspected and compared, but it cannot be "
                    "reused in generation."
                ),
                (
                    "A future admission must independently qualify stable anchors, connector "
                    "fit, orientation and rights."
                ),
            ],
        }
        visual_passed = report["visual_quality"]["all_structural_checks_passed"]
        report["status"] = (
            "reference_only_local_review" if visual_passed else "reference_only_with_qa_issues"
        )
        report["artifacts"] = {
            name: _artifact_record(output / name)
            for name in (
                "extraction.json",
                "source_mesh.glb",
                "source_mesh.blend",
                "preview.png",
                "preview_front.png",
                "preview_side.png",
                "preview_top.png",
                "preview_closeup.png",
                "blender_validation.json",
                "post_blender_measurement.json",
            )
        }
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        raise
    finally:
        report["duration_s"] = round(time.monotonic() - started, 3)
        report["source_unchanged"] = _hash(source) == source_hash
        if not report["source_unchanged"]:
            report["status"] = "failed"
            report["error"] = "Source changed during qualification; evidence is invalid."
        (output / "qualification_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if report["status"] == "failed":
        raise ValueError(report["error"])
    return report


def _inspect_previews(output: Path) -> dict:
    views = {}
    for view, filename in _PREVIEW_FILES.items():
        views[view] = _inspect_preview(output / filename)
    return {
        "method": "bounded_png_observation_v1",
        "views": views,
        "all_structural_checks_passed": bool(views) and all(
            item["passed"] for item in views.values()
        ),
        "interpretation": (
            "Structural framing and contrast evidence; no visual AI or engineering certification."
        ),
    }


def _inspect_preview(path: Path) -> dict:
    result = {
        "file": path.name,
        "exists": path.is_file(),
        "passed": False,
        "checks": {},
    }
    if not path.is_file():
        result["checks"]["file_exists"] = False
        return result
    try:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            pixels = rgb.load()
            stride = max(1, math.ceil(math.sqrt((width * height) / 250_000)))
            sampled = [
                (x, y, *pixels[x, y])
                for y in range(0, height, stride)
                for x in range(0, width, stride)
            ]
            border = [
                (red, green, blue)
                for x, y, red, green, blue in sampled
                if x <= round(width * 0.035)
                or x >= width - round(width * 0.035)
                or y <= round(height * 0.035)
                or y >= height - round(height * 0.035)
            ]
            background = tuple(
                statistics.median(pixel[channel] for pixel in border) for channel in range(3)
            )
            foreground = [
                (
                    x,
                    y,
                    abs(red - background[0])
                    + abs(green - background[1])
                    + abs(blue - background[2]),
                )
                for x, y, red, green, blue in sampled
                if (
                    abs(red - background[0])
                    + abs(green - background[1])
                    + abs(blue - background[2])
                    >= 48
                )
            ]
            if foreground:
                xs = [item[0] for item in foreground]
                ys = [item[1] for item in foreground]
                bbox_width = (max(xs) - min(xs) + 1) / max(width, 1)
                bbox_height = (max(ys) - min(ys) + 1) / max(height, 1)
                center_x = ((min(xs) + max(xs)) / 2) / max(width - 1, 1)
                margins = (
                    min(xs) / max(width - 1, 1),
                    (width - 1 - max(xs)) / max(width - 1, 1),
                    min(ys) / max(height - 1, 1),
                    (height - 1 - max(ys)) / max(height - 1, 1),
                )
                contrast = sum(item[2] for item in foreground) / len(foreground)
            else:
                bbox_width = bbox_height = center_x = contrast = 0.0
                margins = (0.0, 0.0, 0.0, 0.0)
            luminance = [
                (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
                for _, _, red, green, blue in sampled
            ]
            mean = sum(luminance) / max(len(luminance), 1)
            variance = sum((value - mean) ** 2 for value in luminance) / max(len(luminance), 1)
            foreground_ratio = len(foreground) / max(len(sampled), 1)
            checks = {
                "file_exists": True,
                "png_format": image.format == "PNG",
                "resolution": width >= 640 and height >= 480,
                "visible_subject": foreground_ratio >= 0.005,
                "contrast": contrast >= 20,
                "not_clipped": min(margins) >= 0.01,
                "centered": 0.10 <= center_x <= 0.90,
                "occupancy": bbox_width >= 0.10 or bbox_height >= 0.10,
            }
            result.update(
                {
                    "width_px": width,
                    "height_px": height,
                    "luminance_mean": round(mean, 3),
                    "luminance_stddev": round(math.sqrt(variance), 3),
                    "foreground_ratio": round(foreground_ratio, 4),
                    "subject_bbox_width_ratio": round(bbox_width, 4),
                    "subject_bbox_height_ratio": round(bbox_height, 4),
                    "subject_center_x_ratio": round(center_x, 4),
                    "subject_min_edge_margin_ratio": round(min(margins), 4),
                    "subject_contrast_mean": round(contrast, 3),
                    "checks": checks,
                    "passed": all(checks.values()),
                }
            )
    except (OSError, UnidentifiedImageError, ValueError, IndexError):
        result["checks"]["png_parse"] = False
    return result


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_record(path: Path) -> dict:
    return {"file": path.name, "size_bytes": path.stat().st_size, "sha256": _hash(path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manufacturer")
    parser.add_argument("--reference")
    parser.add_argument("--semantic-role")
    parser.add_argument("--source-url")
    parser.add_argument("--datasheet-url")
    parser.add_argument("--connector-summary", action="append", default=[])
    parser.add_argument("--mounting-summary", action="append", default=[])
    parser.add_argument("--blender", default="blender")
    parser.add_argument("--linear-deflection-m", type=float, default=0.00015)
    args = parser.parse_args()
    result = qualify(
        args.source,
        args.output,
        manufacturer=args.manufacturer,
        reference=args.reference,
        semantic_role=args.semantic_role,
        source_url=args.source_url,
        datasheet_url=args.datasheet_url,
        connector_summaries=args.connector_summary,
        mounting_summaries=args.mounting_summary,
        blender=args.blender,
        linear_deflection_m=args.linear_deflection_m,
    )
    print(
        json.dumps(
            {"status": result["status"], "report": str(args.output / "qualification_report.json")}
        )
    )


if __name__ == "__main__":
    main()
