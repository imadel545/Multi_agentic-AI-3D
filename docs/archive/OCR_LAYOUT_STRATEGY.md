# OCR And Layout Strategy

## Implemented

- PyMuPDF extracts selectable PDF text.
- `pdfplumber` extracts table-like PDF text when tables are detectable.
- Selected OCR runs for high/medium priority scanned PDFs and relevant images only.
- OCR uses local Tesseract through `pytesseract` and `PIL`.
- PDF OCR renders selected pages at 200 DPI.
- OCR is capped at 8 pages per document.
- Each OCR evidence page records `source_type = ocr`, page, mean confidence, and low-confidence
  warnings.
- Tesseract calls use a bounded timeout to prevent silent hangs.
- Docling is installed and used as a fallback when PyMuPDF, pdfplumber, and OCR produce no evidence.
- Dependency packaging keeps Docling in the separate `document-layout` extra; `document-intel`
  contains the lighter PDF/OCR/CAD/coordinate stack.

## Available With Fallback

- If PyMuPDF is missing, PDFs are classified but text extraction is unavailable.
- If `pdfplumber` is missing, table fields are not extracted unless they appear in selectable text.
- If Tesseract, `pytesseract`, or `PIL` is missing, OCR is unavailable and the pack reports that
  limit explicitly.
- If OCR produces no text or low confidence, the warning is stored in `processing_warnings`.
- If Docling is unavailable or fails on a file, deterministic PDF/OCR extraction remains visible and
  the fallback warning is stored.

## Known Limitations

- OCR does not yet produce layout bounding boxes or region-level provenance.
- OCR is not run for low-priority photos/photomontages unless filename signals technical evidence.
- Docling fallback can be heavier than PyMuPDF/Tesseract and may hydrate local model cache on first
  use.
- Table extraction is text-based; equipment table schema normalization is still basic.

## Future

- Add artifact-level Docling duration/cost reporting.
- Add page-region provenance for APD/elevation plans.
- Add equipment-list table normalization for antenna/RRU/cabinet inventories.
- Add OCR quality metrics per page to frontend timeline.
