# Asset Attributions

## Implemented External Assets

| asset_id | source | license | attribution_required | original_url | author | status |
| --- | --- | --- | --- | --- | --- | --- |
| `TOWER_LATTICE_30M` | GetGLB | CC Attribution | yes | https://www.getglb.com/architecture/cell-tower-replica/ | poly by google | integrated MVP GLB |

Source file retained:

- `assets/source_downloads/getglb/cell_tower_replica/Radio-tower_2_by_get3dmodels.glb`

Normalized output:

- `assets/towers/tower_lattice_30m.glb`

Known limitation:

- This model is acceptable for the MVP asset pipeline and frontend readiness, but it is not a
  vendor-grade telecom tower. The frontend must display the CC-BY attribution and non-vendor-grade
  warning.

## Internal Project Assets

These assets are project-authored internal GLBs. They are useful for import-path validation and MVP
visuals, but they must not be presented as vendor-grade models.

| asset_id | source | license | status |
| --- | --- | --- | --- |
| `ANT_PANEL_4G_001` | `internal_cleaned` | `internal_project_generated` | integrated |
| `ANT_MICROWAVE_DISH_001` | `internal_cleaned` | `internal_project_generated` | integrated |
| `POWER_CABINET_001` | `internal_cleaned` | `internal_project_generated` | inventory-ready |
| `GPS_ANTENNA_001` | `internal_cleaned` | `internal_project_generated` | inventory-ready |
| `MOUNTING_BRACKET_001` | `internal_cleaned` | `internal_project_generated` | inventory-ready |
| `CABLE_TRAY_001` | `internal_cleaned` | `internal_project_generated` | inventory-ready |
| `ANT_PANEL_5G_001` | `internal_test_minimal` | `internal_project_generated` | integrated |
| `RRU_SMALL_001` | `internal_test_minimal` | `internal_project_generated` | integrated |

## Rejected Or Manual Review Sources

| candidate | source | decision | reason |
| --- | --- | --- | --- |
| 5G Antenna by DINOX86 | Sketchfab | manual review | CC Attribution shown, but anonymous API download requires authentication in this session. |
| Radio Tower by Gunnar Correa | Sketchfab | manual review | CC Attribution shown, but anonymous API download requires authentication in this session. |
| BTS Antennas Asset | Sketchfab | manual review | Telecom relevance and CC Attribution were visible in search results, but direct download requires authenticated review. |
| Satellite dish SVG | SVG Repo | rejected | CC0 page found, but it is a 2D SVG and download was blocked by a security checkpoint. |
| Low Poly Satellite | GetGLB | rejected | CC Attribution and GLB are available, but the model is a space satellite, not a telecom ground/mast asset. |
| Exterior Aircon Unit | Poly Haven / itch.io | rejected | CC0, but not a telecom power cabinet and too large for the MVP asset pack. |
| Free3D / Free3D.tech dish pages | Free3D | rejected | Login/token requirements and unclear downloadable license for automatic integration. |

## Frontend Display Rules

- Show external attribution when `attribution_required = true`.
- Show `source`, `license`, `original_url`, and `original_author` in the asset inventory panel.
- Mark `cc_by`, `internal_cleaned`, and `internal_test_minimal` as non-vendor-grade.
- Never label procedural fallback geometry as imported GLB.
