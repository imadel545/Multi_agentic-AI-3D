from dataclasses import dataclass
from io import BytesIO

from core.contracts.document_pack import DocumentExtractionStatus, DocumentReference

MAX_OCR_PAGES_PER_DOCUMENT = 8
OCR_DPI = 200
OCR_TIMEOUT_S = 10
OCR_CANDIDATE_CATEGORIES = {
    "apd_plan",
    "antenna_plan",
    "elevation_plan",
    "mass_plan",
    "equipment_list",
    "technical_sheet",
}
OCR_FILENAME_HINTS = {
    "apd",
    "antenne",
    "antenna",
    "azimut",
    "hba",
    "hma",
    "elevation",
    "coupe",
    "mass",
    "masse",
    "equipment",
    "equipement",
}


@dataclass(frozen=True)
class TextPage:
    page: int | None
    text: str
    source_type: str = "text"
    confidence: float | None = None
    layer: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TextExtractionResult:
    pages: list[TextPage]
    extraction_status: DocumentExtractionStatus
    tools: list[str]
    warnings: list[str]


def extract_text_pages(document: DocumentReference, content: bytes) -> list[TextPage]:
    return extract_text_result(document, content).pages


def extract_text_result(document: DocumentReference, content: bytes) -> TextExtractionResult:
    if document.duplicate_of:
        return TextExtractionResult([], "not_attempted", [], ["Duplicate file skipped."])
    if document.extractability == "image":
        return extract_image_ocr_result(document, content)
    if document.extractability != "text":
        return _unsupported_non_text(document)
    if document.extension == "pdf":
        return _extract_pdf_text(document, content)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="ignore")
    if not text.strip():
        return TextExtractionResult([], "no_text", ["plain_text"], ["Text document is empty."])
    return TextExtractionResult(
        [TextPage(page=None, text=text, source_type="text", confidence=0.95)],
        "extracted",
        ["plain_text"],
        [],
    )


def _extract_pdf_text(document: DocumentReference, content: bytes) -> TextExtractionResult:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        table_pages, table_warnings = _extract_pdf_table_text(content)
        if table_pages:
            return TextExtractionResult(
                table_pages,
                "extracted",
                ["pdfplumber"],
                ["PyMuPDF/fitz is not installed; only pdfplumber table text was extracted."]
                + table_warnings,
            )
        return TextExtractionResult(
            [],
            "unavailable",
            [],
            [
                "PyMuPDF/fitz is not installed; PDF text extraction was not attempted.",
                *table_warnings,
            ],
        )
    pages = []
    warnings = []
    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            for index, page in enumerate(doc, start=1):
                text = page.get_text("text")
                if text.strip():
                    pages.append(TextPage(page=index, text=text))
    except Exception:
        return TextExtractionResult(
            [],
            "failed",
            ["fitz"],
            ["PyMuPDF failed to read this PDF; no text evidence was extracted."],
        )
    table_pages, table_warnings = _extract_pdf_table_text(content)
    pages.extend(table_pages)
    warnings.extend(table_warnings)
    if pages:
        return TextExtractionResult(pages, "extracted", _pdf_tools(table_pages), warnings)
    ocr_pages, ocr_warnings = _extract_pdf_ocr_pages(document, content)
    if ocr_pages:
        return TextExtractionResult(
            ocr_pages,
            "extracted",
            ["fitz", "pytesseract", "tesseract"],
            warnings + ocr_warnings,
        )
    return TextExtractionResult(
        [],
        "no_text",
        ["fitz"],
        warnings
        + ocr_warnings
        + ["PDF was readable but no selectable text/table/OCR evidence was extracted."],
    )


def _extract_pdf_table_text(content: bytes) -> tuple[list[TextPage], list[str]]:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except ImportError:
        return [], ["pdfplumber is not installed; PDF table extraction was not attempted."]
    pages: list[TextPage] = []
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                rows = []
                for table in page.extract_tables() or []:
                    for row in table:
                        rows.append(" | ".join(cell or "" for cell in row))
                if rows:
                    pages.append(
                        TextPage(
                            page=page_index,
                            text="\n".join(rows),
                            source_type="table",
                            confidence=0.82,
                        )
                    )
    except Exception:
        return [], ["pdfplumber failed to extract tables from this PDF."]
    return pages, []


def _unsupported_non_text(document: DocumentReference) -> TextExtractionResult:
    return TextExtractionResult(
        [],
        "unsupported",
        [],
        [f"{document.extension} is not handled by the text extractor."],
    )


def extract_image_ocr_result(
    document: DocumentReference,
    content: bytes,
) -> TextExtractionResult:
    if document.duplicate_of or document.extractability != "image":
        return TextExtractionResult([], "not_attempted", [], [])
    if not _should_ocr_document(document):
        return TextExtractionResult(
            [],
            "unsupported",
            [],
            ["Image OCR skipped because the file is not high/medium priority technical evidence."],
        )
    page, warning = _ocr_image_bytes(content, page=None)
    warnings = [warning] if warning else []
    if page and page.text.strip():
        return TextExtractionResult([page], "extracted", ["pytesseract", "tesseract"], warnings)
    return TextExtractionResult([], "no_text", ["pytesseract", "tesseract"], warnings)


def _pdf_tools(table_pages: list[TextPage]) -> list[str]:
    tools = ["fitz"]
    if table_pages:
        tools.append("pdfplumber")
    return tools


def _extract_pdf_ocr_pages(
    document: DocumentReference,
    content: bytes,
) -> tuple[list[TextPage], list[str]]:
    if not _should_ocr_document(document):
        return [], ["PDF OCR skipped because the document is not selected for OCR."]
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return [], ["PDF OCR unavailable because PyMuPDF/fitz is not installed."]
    pages: list[TextPage] = []
    warnings: list[str] = []
    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            for index, page in enumerate(doc, start=1):
                if index > MAX_OCR_PAGES_PER_DOCUMENT:
                    warnings.append(
                        f"OCR page limit reached at {MAX_OCR_PAGES_PER_DOCUMENT} pages."
                    )
                    break
                pixmap = page.get_pixmap(matrix=fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72))
                page_result, warning = _ocr_image_bytes(pixmap.tobytes("png"), page=index)
                if warning:
                    warnings.append(warning)
                if page_result and page_result.text.strip():
                    pages.append(page_result)
    except Exception:
        return [], ["PDF OCR rendering failed; no OCR evidence was extracted."]
    return pages, warnings


def _ocr_image_bytes(content: bytes, page: int | None) -> tuple[TextPage | None, str | None]:
    try:
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        return None, "OCR unavailable because pytesseract/Pillow is not installed."
    try:
        image = Image.open(BytesIO(content))
        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            config="--psm 6",
            timeout=OCR_TIMEOUT_S,
        )
    except Exception:
        return None, "Tesseract OCR failed on selected page/image."
    words: list[str] = []
    confidences: list[float] = []
    for raw_word, raw_confidence in zip(data.get("text", []), data.get("conf", []), strict=False):
        word = str(raw_word).strip()
        if not word:
            continue
        words.append(word)
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            continue
        if confidence >= 0:
            confidences.append(confidence)
    text = " ".join(words).strip()
    if not text:
        return None, "OCR produced no text on selected page/image."
    mean_confidence = round(sum(confidences) / len(confidences) / 100, 3) if confidences else None
    warning = None
    if mean_confidence is not None and mean_confidence < 0.55:
        warning = f"OCR confidence is low ({mean_confidence:.2f})."
    return (
        TextPage(
            page=page,
            text=text,
            source_type="ocr",
            confidence=mean_confidence,
            warnings=(warning,) if warning else (),
        ),
        warning,
    )


def _should_ocr_document(document: DocumentReference) -> bool:
    if document.priority in {"high", "medium"} and document.category in OCR_CANDIDATE_CATEGORIES:
        return True
    normalized_name = document.filename.lower()
    return any(hint in normalized_name for hint in OCR_FILENAME_HINTS)
