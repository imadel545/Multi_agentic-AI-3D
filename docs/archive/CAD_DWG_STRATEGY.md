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
- `dwgread` from LibreDWG can convert DWG bytes to DXF before the same `ezdxf` parser runs.

## Available With Fallback

- Valid DXF + `ezdxf` available: parsed as CAD evidence.
- Invalid DXF + `ezdxf` available: parsing failure is visible and file remains inventory-only.
- DXF without `ezdxf`: inventory-only.
- DWG with no local converter: unsupported.
- DWG with local `dwgread`: conversion to DXF is attempted locally, then parsed with `ezdxf`.

## Known Limitations

- Invalid/proprietary DWG files can fail `dwgread` conversion and remain inventory-only.
- CAD geometry is not yet converted into final scene geometry or mount zones.
- DXF block conventions are not normalized into typed telecom CAD contracts yet.

## Future

- Add ODA/FreeCAD adapters for DWG variants that LibreDWG cannot convert.
- Add typed CAD evidence contracts for mount zones, antenna levels, cable trays, and compound layout.
- Add CAD QA comparing extracted CAD levels/azimuths against `ProjectDesignSpec`.
- Add frontend CAD evidence display by layer/source.
