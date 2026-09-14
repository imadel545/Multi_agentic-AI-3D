"""Pure-stdlib professional asset admission guard for the isolated Blender worker."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from collections.abc import Mapping
from pathlib import Path


def claims_professional_identity(manifest: Mapping[str, object]) -> bool:
    """Return whether a manifest makes a claim that needs professional evidence."""

    return bool(
        manifest.get("source") == "vendor_supplied"
        or manifest.get("geometry_fidelity") == "vendor_qualified"
        or manifest.get("manufacturer")
        or manifest.get("reference")
    )


def professional_generation_admission_failures(
    manifest: Mapping[str, object],
    project_root: Path,
) -> tuple[str, ...]:
    """Revalidate immutable professional evidence without project dependencies.

    Blender executes a hashed snapshot of this module with its bundled Python,
    which does not contain the application's Pydantic environment. The backend
    performs additional typed and deep GLB validation before planning.
    """

    qualification = _mapping(manifest.get("qualification"))
    base_eligible = (
        manifest.get("status") == "validated"
        and qualification.get("status") == "qualified_for_generation"
    )
    if not base_eligible:
        return ("Asset is not qualified for generation.",)
    if not claims_professional_identity(manifest):
        return ()
    return professional_evidence_failures(manifest, project_root)


def professional_evidence_failures(
    manifest: Mapping[str, object],
    project_root: Path,
) -> tuple[str, ...]:
    """Verify the complete professional evidence contract for any manifest."""

    failures: list[str] = []
    qualification = _mapping(manifest.get("qualification"))
    master = _mapping(manifest.get("master_representation"))
    viewer = _mapping(manifest.get("viewer_representation"))
    qa = _mapping(manifest.get("qa_evidence"))
    rights = _mapping(manifest.get("usage_rights"))

    if not (
        manifest.get("status") == "validated"
        and qualification.get("status") == "qualified_for_generation"
    ):
        failures.append("Asset is not qualified for generation.")
    if manifest.get("source") == "internal_test_minimal":
        failures.append("Internal test-minimal geometry is excluded from milestone evidence.")

    allowed_modes = qualification.get("allowed_generation_modes")
    if (
        not isinstance(allowed_modes, list)
        or any(not isinstance(mode, str) for mode in allowed_modes)
        or set(allowed_modes) != {"imported_glb_exact"}
    ):
        failures.append(
            "Professional identity is admitted only for the exact qualified viewer import."
        )
    required_geometry_checks = (
        "mesh_integrity_verified",
        "dimensions_verified",
        "pivot_verified",
        "orientation_verified",
    )
    if any(qualification.get(check) is not True for check in required_geometry_checks):
        failures.append("Professional exact-import qualification checks are incomplete.")

    if not manifest.get("source_provenance"):
        failures.append("Source provenance is not explicitly documented.")
    if not manifest.get("source_file_sha256"):
        failures.append("Original source hash is not explicitly documented.")
    if not manifest.get("license"):
        failures.append("Asset licence is not explicitly documented.")
    if not (
        rights.get("status") == "project_authorized"
        and rights.get("project_use_authorized") is True
        and rights.get("evidence")
    ):
        failures.append("Project asset usage rights are not explicitly authorized.")
    if manifest.get("geometry_fidelity") != "vendor_qualified":
        failures.append("Geometry fidelity is not vendor-qualified.")
    if not master or not viewer:
        failures.append("Master and viewer representations are not both published.")
    else:
        if master.get("format") not in {"brep", "iges", "step"}:
            failures.append("Professional master representation is not a neutral CAD format.")
        if viewer.get("format") != "glb":
            failures.append("Professional viewer representation is not a GLB.")
        if viewer.get("file") != manifest.get("file"):
            failures.append("Manifest runtime file does not match the viewer representation.")
        if qualification.get("verified_file_sha256") != viewer.get("sha256"):
            failures.append("Qualified runtime hash does not match the viewer representation.")
        if viewer.get("derived_from_representation_id") != master.get("representation_id"):
            failures.append("Viewer representation lineage does not reference the master.")

    dimensions = _mapping(manifest.get("dimensions_m"))
    bounds = _mapping(manifest.get("bounding_box_m"))
    if not dimensions or not bounds:
        failures.append("Qualified dimensions and bounding box are incomplete.")
    anchors = manifest.get("anchors")
    connectors = manifest.get("connectors")
    if (
        not isinstance(anchors, list)
        or not anchors
        or not isinstance(connectors, list)
        or not connectors
    ):
        failures.append("Qualified anchors and connectors are incomplete.")

    previews = manifest.get("preview_set")
    expected_views = {"front", "side", "top", "perspective", "closeup"}
    if not isinstance(previews, list):
        previews = []
    published_views = {
        str(preview.get("view"))
        for item in previews
        if (preview := _mapping(item))
        and preview.get("qa_status") == "passed"
        and isinstance(preview.get("view"), str)
    }
    if published_views != expected_views or len(previews) != len(expected_views):
        failures.append("Five QA-passed qualification previews are not published.")
    if (
        qa.get("status") != "passed"
        or not qa.get("report_file")
        or not qa.get("report_sha256")
        or not isinstance(qa.get("checks"), list)
        or not qa.get("checks")
    ):
        failures.append("Professional asset QA evidence is incomplete or has not passed.")
    if not manifest.get("qualification_version"):
        failures.append("Qualification version is not published.")

    root = project_root.resolve()
    master_path = _evidence_path(root, master.get("file"), "Master representation", failures)
    viewer_path = _evidence_path(root, viewer.get("file"), "Viewer representation", failures)
    if master_path is not None:
        _verify_hash(
            master_path,
            master.get("sha256"),
            "Master representation hash does not match its published SHA-256.",
            failures,
        )
    if viewer_path is not None:
        _verify_hash(
            viewer_path,
            viewer.get("sha256"),
            "Viewer representation hash does not match its published SHA-256.",
            failures,
        )
        if not _has_glb_mesh(viewer_path):
            failures.append("Viewer representation is not a valid GLB with mesh geometry.")

    for item in previews:
        preview = _mapping(item)
        view = str(preview.get("view") or "unknown")
        preview_path = _evidence_path(
            root,
            preview.get("file"),
            f"Qualification preview ({view})",
            failures,
        )
        if preview_path is None:
            continue
        _verify_hash(
            preview_path,
            preview.get("sha256"),
            f"Qualification preview hash does not match: {view}.",
            failures,
        )
        png_dimensions = _inspect_png(preview_path)
        if png_dimensions is None:
            failures.append(f"Qualification preview is not a valid PNG: {view}.")
        elif png_dimensions != (preview.get("width_px"), preview.get("height_px")):
            failures.append(f"Qualification preview dimensions do not match: {view}.")

    report_path = _evidence_path(root, qa.get("report_file"), "Professional QA report", failures)
    if report_path is not None:
        _verify_hash(
            report_path,
            qa.get("report_sha256"),
            "Professional QA report hash does not match its published SHA-256.",
            failures,
        )
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            report = None
        _verify_report(root, manifest, master, viewer, qa, report, failures)

    _verify_dimensions_and_anchors(dimensions, bounds, anchors, failures)
    return tuple(dict.fromkeys(failures))


def _verify_report(
    root: Path,
    manifest: Mapping[str, object],
    master: Mapping[str, object],
    viewer: Mapping[str, object],
    qa: Mapping[str, object],
    report: object,
    failures: list[str],
) -> None:
    if not isinstance(report, dict):
        failures.append("Professional QA report is not a readable structured report.")
        return
    if report.get("schema_version") != "professional_asset_qa.v1":
        failures.append("Professional QA report schema is missing or unsupported.")
    if report.get("asset_id") != manifest.get("asset_id"):
        failures.append("Professional QA report asset identity does not match the manifest.")
    if report.get("qualification_version") != manifest.get("qualification_version"):
        failures.append("Professional QA report qualification version does not match the manifest.")
    if report.get("status") != "passed":
        failures.append("Professional QA report does not contain a passed verdict.")
    representations = _mapping(report.get("representations"))
    if not representations:
        failures.append("Professional QA report representation bindings are incomplete.")
    else:
        source_sha256 = manifest.get("source_file_sha256")
        master_sha256 = master.get("sha256")
        report_source_sha256 = representations.get("source_sha256")
        if source_sha256 != master_sha256:
            if report_source_sha256 != source_sha256:
                failures.append("Professional QA report source hash does not match the manifest.")
            source_file = representations.get("source_file")
            if not isinstance(source_file, str) or not source_file:
                failures.append("Professional QA report original source file is missing.")
            elif Path(source_file).is_absolute():
                failures.append("Original source representation path must be relative.")
            else:
                source_path = _evidence_path(
                    root,
                    source_file,
                    "Original source representation",
                    failures,
                )
                if source_path is not None:
                    _verify_hash(
                        source_path,
                        source_sha256,
                        "Original source representation hash does not match the manifest.",
                        failures,
                    )
        elif report_source_sha256 is not None and report_source_sha256 != source_sha256:
            failures.append("Professional QA report source hash does not match the manifest.")
        if representations.get("master_sha256") != master.get("sha256"):
            failures.append("Professional QA report master hash does not match the manifest.")
        if representations.get("viewer_sha256") != viewer.get("sha256"):
            failures.append("Professional QA report viewer hash does not match the manifest.")
    checks = _mapping(report.get("checks"))
    if not checks:
        failures.append("Professional QA report checks are not a structured result map.")
        return
    required = {"mesh_integrity", "dimensions", "pivot", "orientation"}
    declared_checks = qa.get("checks")
    if isinstance(declared_checks, list):
        required.update(str(check) for check in declared_checks)
    failed = sorted(check for check in required if checks.get(check) is not True)
    if failed:
        failures.append(
            "Professional QA report has missing or failed checks: " + ", ".join(failed) + "."
        )


def _verify_dimensions_and_anchors(
    dimensions: Mapping[str, object],
    bounds: Mapping[str, object],
    anchors: object,
    failures: list[str],
) -> None:
    minimum = bounds.get("minimum")
    maximum = bounds.get("maximum")
    if not (
        isinstance(minimum, list)
        and len(minimum) == 3
        and isinstance(maximum, list)
        and len(maximum) == 3
    ):
        return
    declared = [dimensions.get("width"), dimensions.get("depth"), dimensions.get("height")]
    try:
        extents = [float(maximum[index]) - float(minimum[index]) for index in range(3)]
        if any(abs(extents[index] - float(declared[index])) > 1e-6 for index in range(3)):
            failures.append("Qualified dimensions do not match the published bounding box.")
    except (TypeError, ValueError):
        failures.append("Qualified dimensions and bounding box are incomplete.")
        return
    if not isinstance(anchors, list):
        return
    for item in anchors:
        anchor = _mapping(item)
        position = anchor.get("position_m")
        if not isinstance(position, list) or len(position) != 3:
            continue
        try:
            outside = any(
                float(position[index]) < float(minimum[index]) - 1e-6
                or float(position[index]) > float(maximum[index]) + 1e-6
                for index in range(3)
            )
        except (TypeError, ValueError):
            outside = True
        if outside:
            failures.append(
                f"Qualified anchor is outside the bounding box: {anchor.get('anchor_id')}."
            )


def _evidence_path(
    root: Path,
    relative_path: object,
    label: str,
    failures: list[str],
) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path:
        return None
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        failures.append(f"{label} path escapes the project evidence root.")
        return None
    if not candidate.is_file():
        failures.append(f"{label} file is missing.")
        return None
    return candidate


def _verify_hash(path: Path, expected: object, failure: str, failures: list[str]) -> None:
    if not isinstance(expected, str) or _sha256(path) != expected:
        failures.append(failure)


def _has_glb_mesh(path: Path) -> bool:
    try:
        raw = path.read_bytes()
        if len(raw) < 20 or raw[:4] != b"glTF" or struct.unpack_from("<I", raw, 8)[0] != len(raw):
            return False
        json_length = struct.unpack_from("<I", raw, 12)[0]
        if raw[16:20] != b"JSON" or 20 + json_length > len(raw):
            return False
        document = json.loads(raw[20 : 20 + json_length].decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, struct.error):
        return False
    if not isinstance(document, dict) or not isinstance(document.get("meshes"), list):
        return False
    return any(
        isinstance(primitive, dict) and "POSITION" in _mapping(primitive.get("attributes"))
        for mesh in document.get("meshes", [])
        if isinstance(mesh, dict)
        for primitive in mesh.get("primitives", [])
        if isinstance(mesh.get("primitives"), list)
    )


def _inspect_png(path: Path) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    width = height = None
    idat = bytearray()
    found_end = False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        kind = data[offset : offset + 4]
        offset += 4
        if offset + length + 4 > len(data):
            return None
        payload = data[offset : offset + length]
        offset += length
        checksum = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != checksum:
            return None
        if kind == b"IHDR":
            if length != 13:
                return None
            width, height = struct.unpack_from(">II", payload, 0)
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            found_end = True
            break
    if not width or not height or not idat or not found_end:
        return None
    try:
        if not zlib.decompress(bytes(idat)):
            return None
    except zlib.error:
        return None
    return width, height


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
