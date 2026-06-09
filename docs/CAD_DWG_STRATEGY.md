# CAD, DXF, And DWG Strategy

## Implemented

- CAD files are classified as `cad_dxf` or `cad_dwg`.
- Each CAD document exposes `cad_status`, `extraction_status`, `processing_tools`, and warnings.
- `ezdxf` is installed and used for DXF parsing when available.
- DXF extraction records:
  - layer names;
  - TEXT;
  - MTEXT;
  - INSERT;
  - DIMENSION;
  - POINT;
  - LINE;
  - LWPOLYLINE coordinates.
- CAD evidence is emitted as `TextPage(source_type="cad", layer=...)` and then passes through the
  same deterministic extractor and `ProjectDesignSpec` consolidation as PDF/text/OCR.
- CAD-derived fields never bypass provenance, missing/conflict detection, user correction, or QA.

## Available With Fallback

- Valid DXF + `ezdxf` available: parsed as CAD evidence.
- Invalid DXF + `ezdxf` available: parsing failure is visible and file remains inventory-only.
- DXF without `ezdxf`: inventory-only.
- DWG with no local converter: unsupported.
- DWG with a local converter detected: recorded as conversion-capable inventory, but conversion is
  not executed automatically yet.

## Known Limitations

- No ODA/FreeCAD/dwgread converter is currently detected on the machine.
- DWG parsing is therefore not claimed.
- CAD geometry is not yet converted into final scene geometry or mount zones.
- DXF block conventions are not normalized into typed telecom CAD contracts yet.

## Future

- Add mockable local DWG-to-DXF conversion when a converter is installed.
- Add typed CAD evidence contracts for mount zones, antenna levels, cable trays, and compound layout.
- Add CAD QA comparing extracted CAD levels/azimuths against `ProjectDesignSpec`.
- Add frontend CAD evidence display by layer/source.
