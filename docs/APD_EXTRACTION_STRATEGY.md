# APD Extraction Strategy

## Implemented

The document-pack engine extracts APD-style telecom values from generic text evidence, not from a
SOLER-specific folder structure.

Supported deterministic fields include:

- site code, name, address, commune;
- coordinate system, X/Y/Z, latitude/longitude, altitude, conversion status;
- tower type and height;
- foundation, RAL, ladder, lightning rod, aviation light;
- azimuths, sector count, HBA/HMA, bands, RRU, tilt;
- cables, GPS, power cabinet, grounding, ENEDIS/FT/FO signals.

All confirmed critical fields require provenance. Missing HBA, azimuths, tower type, tower height,
or sector count block mapping to `RequirementSpec`.

## Available With Fallback

- Text-like APD documents are extracted deterministically.
- PDFs use local PyMuPDF text extraction and `pdfplumber` table extraction when available.
- Scanned APD/elevation/antenna PDFs can use selected Tesseract OCR with page/confidence
  provenance.
- DXF evidence can feed APD-style radio/tower fields when `ezdxf` parses useful layer text.
- Groq bounded extraction can add candidates when configured, but only with valid evidence.
- Manual corrections can resolve missing/conflicting fields and are stored as `user_correction`
  provenance.

## Known Limitations

- APD parsing is pattern-based and conservative.
- It does not infer critical fields from low-priority photos or photomontages.
- Docling layout is not enabled by default.
- DWG remains unsupported without local conversion.
- CAD geometry is not yet normalized into typed mount zones.

## Future

- Add table-aware extraction for equipment lists.
- Add memory recall for recurring APD conflict and correction patterns.
