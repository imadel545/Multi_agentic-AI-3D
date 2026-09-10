"""Inspect real native CAD faces in Blender without promoting the source asset.

Example: python -m scripts.inspect_native_cad drawing.dwg --output /tmp/cad-proof
Requires document-intel dependencies, LibreDWG for DWG, and local Blender.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from core.services.blender_runner import BlenderRunner
from core.services.cad_conversion import verify_polyface_conversion
from core.services.cad_mesh_extraction import extract_dxf_mesh


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(source: Path, output: Path, *, units: str | None = None, blender: str = "blender"):
    source = source.resolve(strict=True)
    output = output.resolve()
    if source.suffix.lower() not in {".dwg", ".dxf"}:
        raise ValueError("Only native DWG polyfaces and supported DXF faces are accepted.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Inspection output must be new or empty; existing evidence is preserved.")
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    source_hash = _hash(source)
    report = {
        "source": {"path": str(source), "sha256": source_hash},
        "status": "inspecting",
        "generation_eligible": False,
        "professional_qualified": False,
    }
    try:
        dxf_path = source
        if source.suffix.lower() == ".dwg":
            import ezdxf

            raw_path = output / "source_dwg.json"
            with raw_path.open("wb") as stream, (output / "dwgread.log").open("wb") as log:
                subprocess.run(
                    ["dwgread", "-O", "JSON", str(source)],
                    stdout=stream,
                    stderr=log,
                    check=True,
                    timeout=45,
                )
            source_document = json.loads(raw_path.read_bytes().decode("latin1").replace("\x00", ""))
            dxf_path = output / "converted.dxf"
            with (output / "conversion.log").open("wb") as log:
                subprocess.run(
                    ["dwg2dxf", "-o", str(dxf_path), str(source)],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=45,
                )
            document = ezdxf.readfile(dxf_path)
            report["conversion"] = verify_polyface_conversion(source_document, document)
            report["converted_dxf_sha256"] = _hash(dxf_path)
            dxf_path = output / "normalized.dxf"
            document.saveas(dxf_path)
        extraction = extract_dxf_mesh(dxf_path, units=units)
        extraction_path = output / "extraction.json"
        extraction_path.write_text(json.dumps(extraction, indent=2) + "\n")
        root = Path(__file__).resolve().parents[1]
        binary = BlenderRunner(root, blender)._resolve_blender_binary()
        if binary is None:
            raise ValueError("Blender is required; no placeholder output is generated.")
        with (output / "blender.log").open("wb") as log:
            subprocess.run(
                [
                    str(binary),
                    "--background",
                    "--factory-startup",
                    "--python-exit-code",
                    "1",
                    "--python",
                    str(root / "tools/import_native_cad_mesh.py"),
                    "--",
                    str(extraction_path),
                    str(output),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=150,
            )
        report["blender"] = json.loads((output / "blender_validation.json").read_text())
        if not report["blender"]["geometry_roundtrip"]["passed"]:
            raise ValueError("Blender geometry roundtrip failed.")
        report["extraction_counts"] = extraction["counts"]
        report["source_units"] = extraction["source_units"]
        report["status"] = "geometry_inspected_not_qualified"
        report["artifacts"] = {
            name: {"path": str(output / name), "sha256": _hash(output / name)}
            for name in (
                "extraction.json",
                "source_mesh.glb",
                "source_mesh.blend",
                "preview.png",
                "preview_front.png",
                "blender_validation.json",
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
            report["error"] = "Source changed during inspection; evidence is invalid."
        (output / "inspection_report.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] == "failed":
        raise ValueError(report["error"])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--units", help="Explicit unit for a unitless DXF only; never a scale guess."
    )
    parser.add_argument("--blender", default="blender")
    args = parser.parse_args()
    result = inspect(args.source, args.output, units=args.units, blender=args.blender)
    print(
        json.dumps(
            {"status": result["status"], "report": str(args.output / "inspection_report.json")}
        )
    )


if __name__ == "__main__":
    main()
