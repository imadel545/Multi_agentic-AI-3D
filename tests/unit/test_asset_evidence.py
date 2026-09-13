from __future__ import annotations

import hashlib
import json
import shutil
import struct
import zlib
from pathlib import Path

import pytest

from core.contracts.assets import (
    AssetAnchor,
    AssetBoundingBoxM,
    AssetCompatibilityRules,
    AssetConnector,
    AssetManifest,
    AssetPreview,
    AssetQaEvidence,
    AssetQualification,
    AssetRepresentation,
    AssetTransformPermissions,
    AssetUsageRights,
    DimensionsM,
)
from core.services.asset_evidence import ProfessionalAssetVerifier
from core.services.asset_inventory import inspect_asset_manifest


def test_professional_evidence_requires_real_untampered_bytes(tmp_path: Path) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    verifier = ProfessionalAssetVerifier(tmp_path)

    verified = verifier.verify(manifest)
    admitted = verifier.verify_generation_admission(manifest)

    assert verified.eligible is True
    assert verified.failures == ()
    assert admitted.eligible is True

    (tmp_path / manifest.viewer_representation.file).write_bytes(b"tampered")  # type: ignore[union-attr]
    tampered = verifier.verify(manifest)

    assert tampered.eligible is False
    assert "Viewer representation hash does not match its published SHA-256." in tampered.failures
    assert "Viewer representation is not a valid GLB with mesh geometry." in tampered.failures


def test_professional_review_uses_effective_evidence_and_verified_preview_actions(
    tmp_path: Path,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    verifier = ProfessionalAssetVerifier(tmp_path)
    published_previews = [
        {
            "view": preview.view,
            "url": f"/assets/{manifest.asset_id}/previews/{preview.view}",
            "available": True,
            "qa_status": "passed",
        }
        for preview in manifest.preview_set
    ]

    review = verifier.qualification_review(
        manifest,
        published_previews=published_previews,
    )

    assert review["status"] == "admitted"
    assert review["blockers"] == []
    assert all(check["status"] == "passed" for check in review["checks"])
    assert {
        action["action_id"] for action in review["available_actions"]
    } == {
        "view_verified_preview:front",
        "view_verified_preview:side",
        "view_verified_preview:top",
        "view_verified_preview:perspective",
        "view_verified_preview:closeup",
    }
    assert {action["kind"] for action in review["available_actions"]} == {
        "internal_preview"
    }
    assert not any(
        action["action_id"] == "start_design_with_asset"
        for action in review["available_actions"]
    )


def test_professional_review_exposes_declared_but_invalid_evidence(
    tmp_path: Path,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    assert manifest.viewer_representation is not None
    (tmp_path / manifest.viewer_representation.file).write_bytes(b"tampered")

    review = ProfessionalAssetVerifier(tmp_path).qualification_review(manifest)

    assert review["status"] == "evidence_invalid"
    assert review["blockers"]
    assert next(
        check
        for check in review["checks"]
        if check["check_id"] == "master_viewer_lineage"
    )["status"] == "incomplete"
    assert review["available_actions"] == []


def test_professional_review_never_marks_failed_geometry_or_anchors_as_verified(
    tmp_path: Path,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    payload = manifest.model_dump(mode="json")
    payload["bounding_box_m"]["maximum"][0] = 9.0
    payload["bounding_box_m"]["minimum"][1] = 0.1
    payload["bounding_box_m"]["maximum"][1] = 0.3
    invalid = AssetManifest.model_validate(payload)

    review = ProfessionalAssetVerifier(tmp_path).qualification_review(invalid)
    checks = {check["check_id"]: check["status"] for check in review["checks"]}

    assert checks["geometry_scale"] == "incomplete"
    assert checks["anchors_connectors"] == "incomplete"


@pytest.mark.parametrize("failed_check", ["dimensions", "orientation", "pivot", "mesh_integrity"])
def test_professional_review_does_not_trust_declarations_over_failed_report(
    tmp_path: Path, failed_check: str,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    assert manifest.qa_evidence.report_file is not None
    report_path = tmp_path / manifest.qa_evidence.report_file
    report = json.loads(report_path.read_text())
    report["checks"][failed_check] = False
    report_path.write_text(json.dumps(report))
    manifest = manifest.model_copy(update={
        "qa_evidence": manifest.qa_evidence.model_copy(update={
            "report_sha256": _sha256(report_path),
        }),
    })

    review = ProfessionalAssetVerifier(tmp_path).qualification_review(manifest)
    checks = {check["check_id"]: check["status"] for check in review["checks"]}

    assert review["status"] == "evidence_invalid"
    assert checks["geometry_scale"] == "incomplete"
    assert checks["pivot_orientation"] == "incomplete"
    assert checks["professional_qa"] == "incomplete"


@pytest.mark.parametrize("invalid_image", ["not_png", "wrong_dimensions"])
def test_professional_review_withholds_invalid_preview_even_with_matching_hash(
    tmp_path: Path, invalid_image: str,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    preview = manifest.preview_set[0]
    preview_path = tmp_path / preview.file
    if invalid_image == "not_png":
        preview_path.write_bytes(b"not a PNG image")
    else:
        _write_png(preview_path, width=32, height=64)
    manifest = manifest.model_copy(update={
        "preview_set": [
            preview.model_copy(update={"sha256": _sha256(preview_path)}),
            *manifest.preview_set[1:],
        ],
    })
    verifier = ProfessionalAssetVerifier(tmp_path)

    inventory = inspect_asset_manifest(tmp_path, manifest, verifier)
    review = verifier.qualification_review(
        manifest, published_previews=inventory["preview_set"],
    )

    assert inventory["preview_set"][0]["available"] is False
    assert all(item["available"] for item in inventory["preview_set"][1:])
    assert next(check for check in review["checks"]
                if check["check_id"] == "qualification_previews")["status"] == "incomplete"
    assert not any(action["action_id"] == f"view_verified_preview:{preview.view}"
                   for action in review["available_actions"])
    assert len(review["available_actions"]) == 4


def test_professional_manifest_rejects_non_http_source_actions(tmp_path: Path) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    payload = manifest.model_dump(mode="json")
    payload["original_url"] = "javascript:alert(document.domain)"

    with pytest.raises(ValueError, match="absolute HTTP"):
        AssetManifest.model_validate(payload)


def test_professional_evidence_rejects_missing_qa_report_and_bad_preview(
    tmp_path: Path,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    verifier = ProfessionalAssetVerifier(tmp_path)
    assert manifest.qa_evidence.report_file is not None
    (tmp_path / manifest.qa_evidence.report_file).unlink()
    first_preview = manifest.preview_set[0]
    (tmp_path / first_preview.file).write_bytes(b"not-a-png")

    result = verifier.verify(manifest)

    assert result.eligible is False
    assert "Professional QA report file is missing." in result.failures
    assert "Qualification preview hash does not match: front." in result.failures
    assert "Qualification preview is not a valid PNG: front." in result.failures


def test_declared_paths_without_files_never_become_professional_evidence(
    tmp_path: Path,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    shutil.rmtree(tmp_path / "assets" / "qualified")

    result = ProfessionalAssetVerifier(tmp_path).verify(manifest)

    assert manifest.milestone_evidence_declaration_failures == []
    assert result.eligible is False
    assert "Master representation file is missing." in result.failures
    assert "Viewer representation file is missing." in result.failures
    assert "Professional QA report file is missing." in result.failures


def _professional_contract_fixture(project_root: Path) -> AssetManifest:
    qualified = project_root / "assets" / "qualified"
    previews_dir = qualified / "previews"
    previews_dir.mkdir(parents=True)

    master_path = qualified / "panel.step"
    master_path.write_bytes(b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;")
    viewer_path = qualified / "panel.glb"
    shutil.copy2(Path("assets/antennas/ant_panel_4g_001.glb"), viewer_path)
    report_path = qualified / "panel-qa.json"

    previews: list[AssetPreview] = []
    for view in ("front", "side", "top", "perspective", "closeup"):
        preview_path = previews_dir / f"panel-{view}.png"
        _write_png(preview_path, width=64, height=64)
        previews.append(
            AssetPreview(
                view=view,
                file=str(preview_path.relative_to(project_root)),
                sha256=_sha256(preview_path),
                width_px=64,
                height_px=64,
                qa_status="passed",
            )
        )

    master = AssetRepresentation(
        representation_id="master_step",
        role="master",
        format="step",
        file=str(master_path.relative_to(project_root)),
        sha256=_sha256(master_path),
        units="millimeters",
    )
    viewer = AssetRepresentation(
        representation_id="viewer_glb",
        role="viewer",
        format="glb",
        file=str(viewer_path.relative_to(project_root)),
        sha256=_sha256(viewer_path),
        units="meters",
        derived_from_representation_id="master_step",
        tessellation_tolerance_m=0.0005,
    )
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "professional_asset_qa.v1",
                "asset_id": "PROFESSIONAL_PANEL_CONTRACT_FIXTURE",
                "qualification_version": "m1.contract-test",
                "status": "passed",
                "representations": {
                    "master_sha256": master.sha256,
                    "viewer_sha256": viewer.sha256,
                },
                "checks": {
                    "mesh_integrity": True,
                    "dimensions": True,
                    "pivot": True,
                    "orientation": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return AssetManifest(
        asset_id="PROFESSIONAL_PANEL_CONTRACT_FIXTURE",
        type="antenna",
        file=viewer.file,
        family="sector_panel",
        manufacturer="Authorized manufacturer",
        reference="PANEL-001",
        source="vendor_supplied",
        source_provenance="Authorized STEP AP242 export from the source assembly.",
        source_format="step",
        source_file_sha256=master.sha256,
        geometry_status="neutral_format_conversion",
        conversion_method="Controlled STEP tessellation contract fixture",
        geometry_fidelity="vendor_qualified",
        license="Project-authorized engineering use",
        usage_rights=AssetUsageRights(
            status="project_authorized",
            project_use_authorized=True,
            derivative_use_authorized=True,
            redistribution_authorized=False,
            evidence="Project contract fixture authorization record.",
        ),
        master_representation=master,
        viewer_representation=viewer,
        dimensions_m=DimensionsM(width=0.42, depth=0.18, height=1.4),
        bounding_box_m=AssetBoundingBoxM(
            minimum=(-0.21, -0.09, 0.0),
            maximum=(0.21, 0.09, 1.4),
        ),
        preview_set=previews,
        compatible_networks=["4G", "5G"],
        compatible_tower_types=["lattice_tower", "monopole"],
        compatibility_rules=AssetCompatibilityRules(
            compatible_roles=["sector_antenna"],
            required_connector_kinds=["mechanical"],
        ),
        builder_profile_id="sector_panel_v1",
        anchors=[
            AssetAnchor(
                anchor_id="rear_mount",
                position_m=(0.0, -0.09, 0.7),
                normal=(0.0, -1.0, 0.0),
                roles=["tower_mount"],
            )
        ],
        connectors=[
            AssetConnector(
                connector_id="rear_mount_mechanical",
                kind="mechanical",
                anchor_id="rear_mount",
                compatible_connector_kinds=["mechanical"],
            )
        ],
        transform_permissions=AssetTransformPermissions(
            translation_axes=["x", "y", "z"],
            rotation_axes=["z"],
            maximum_translation_m=100.0,
            maximum_rotation_deg=360.0,
        ),
        import_fallback_allowed=False,
        qa_evidence=AssetQaEvidence(
            status="passed",
            report_file=str(report_path.relative_to(project_root)),
            report_sha256=_sha256(report_path),
            checks=["mesh_integrity", "dimensions", "pivot", "orientation"],
        ),
        qualification_version="m1.contract-test",
        qualification=AssetQualification(
            status="qualified_for_generation",
            allowed_generation_modes=["imported_glb_exact"],
            verified_file_sha256=viewer.sha256,
            mesh_integrity_verified=True,
            dimensions_verified=True,
            pivot_verified=True,
            orientation_verified=True,
        ),
    )


def test_professional_evidence_rejects_status_only_report_even_when_hash_matches(
    tmp_path: Path,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    assert manifest.qa_evidence.report_file is not None
    report_path = tmp_path / manifest.qa_evidence.report_file
    report_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    manifest = manifest.model_copy(
        update={
            "qa_evidence": manifest.qa_evidence.model_copy(
                update={"report_sha256": _sha256(report_path)}
            )
        }
    )

    result = ProfessionalAssetVerifier(tmp_path).verify(manifest)

    assert result.eligible is False
    assert "Professional QA report schema is missing or unsupported." in result.failures
    assert "Professional QA report asset identity does not match the manifest." in result.failures
    assert "Professional QA report representation bindings are incomplete." in result.failures
    assert "Professional QA report checks are not a structured result map." in result.failures


def test_professional_claim_cannot_use_technical_qualification_as_admission(
    tmp_path: Path,
) -> None:
    manifest = AssetManifest.model_validate_json(
        Path("assets/manifests/ANT_PANEL_4G_001.json").read_text(encoding="utf-8")
    ).model_copy(
        update={
            "asset_id": "UNVERIFIED_VENDOR_PANEL",
            "source": "vendor_supplied",
            "manufacturer": "Unverified manufacturer",
            "reference": "UNVERIFIED-001",
            "geometry_fidelity": "vendor_qualified",
        }
    )

    result = ProfessionalAssetVerifier(tmp_path).verify_generation_admission(manifest)

    assert manifest.is_generation_eligible is True
    assert result.eligible is False
    assert "Master and viewer representations are not both published." in result.failures
    assert "Professional asset QA evidence is incomplete or has not passed." in result.failures


def test_professional_claim_cannot_execute_a_generic_parametric_builder(
    tmp_path: Path,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    manifest = manifest.model_copy(
        update={
            "qualification": manifest.qualification.model_copy(
                update={
                    "allowed_generation_modes": ["parametric_generated"],
                    "mesh_integrity_verified": False,
                    "dimensions_verified": False,
                    "pivot_verified": False,
                    "orientation_verified": False,
                }
            )
        }
    )

    result = ProfessionalAssetVerifier(tmp_path).verify_generation_admission(manifest)

    assert result.eligible is False
    assert (
        "Professional identity is admitted only for the exact qualified viewer import."
        in result.failures
    )
    assert "Professional exact-import qualification checks are incomplete." in result.failures


def test_professional_evidence_rejects_report_rebound_to_other_evidence(
    tmp_path: Path,
) -> None:
    manifest = _professional_contract_fixture(tmp_path)
    assert manifest.qa_evidence.report_file is not None
    report_path = tmp_path / manifest.qa_evidence.report_file
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["asset_id"] = "OTHER_ASSET"
    report["qualification_version"] = "other-version"
    report["representations"]["viewer_sha256"] = "0" * 64
    report["checks"]["orientation"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")
    manifest = manifest.model_copy(
        update={
            "qa_evidence": manifest.qa_evidence.model_copy(
                update={"report_sha256": _sha256(report_path)}
            )
        }
    )

    result = ProfessionalAssetVerifier(tmp_path).verify(manifest)

    assert result.eligible is False
    assert "Professional QA report asset identity does not match the manifest." in result.failures
    assert (
        "Professional QA report qualification version does not match the manifest."
        in result.failures
    )
    assert "Professional QA report viewer hash does not match the manifest." in result.failures
    assert "Professional QA report has missing or failed checks: orientation." in result.failures


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_png(path: Path, *, width: int, height: int) -> None:
    signature = b"\x89PNG\r\n\x1a\n"
    raw = b"".join(b"\x00" + (b"\x80\x80\x80" * width) for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    path.write_bytes(
        signature
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
