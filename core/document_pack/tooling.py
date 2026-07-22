import importlib.util
import shutil

from core.contracts.document_pack import DocumentPackCapabilities, DocumentToolCapability


def detect_document_pack_capabilities(
    *,
    groq_bounded_extraction_enabled: bool = False,
) -> DocumentPackCapabilities:
    fitz_available = _module_available("fitz")
    pdfplumber_available = _module_available("pdfplumber")
    docling_available = _module_available("docling")
    ezdxf_available = _module_available("ezdxf")
    pyproj_available = _module_available("pyproj")
    pytesseract_available = _module_available("pytesseract")
    pillow_available = _module_available("PIL")
    tesseract_path = shutil.which("tesseract")
    oda_path = shutil.which("ODAFileConverter")
    freecad_path = shutil.which("FreeCAD")
    dwg2dxf_path = shutil.which("dwg2dxf")
    dwg_converter = oda_path or freecad_path or dwg2dxf_path

    return DocumentPackCapabilities(
        pdf_text_extraction=DocumentToolCapability(
            name="PyMuPDF",
            status="available" if fitz_available else "unavailable",
            purpose="Extract selectable text from PDF pages.",
            module="fitz",
            fallback="PDF is classified and recorded; no text is extracted without PyMuPDF.",
            warnings=[] if fitz_available else ["python_module_missing:fitz"],
        ),
        pdf_table_extraction=DocumentToolCapability(
            name="pdfplumber",
            status="available" if pdfplumber_available else "unavailable",
            purpose="Extract textual PDF tables such as equipment lists.",
            module="pdfplumber",
            fallback="Table values are not extracted unless they also appear in plain text.",
            warnings=[] if pdfplumber_available else ["python_module_missing:pdfplumber"],
        ),
        pdf_layout_extraction=DocumentToolCapability(
            name="Docling",
            status="installed_import_only" if docling_available else "unavailable",
            purpose=(
                "Structured PDF layout/table/picture extraction when installed locally; currently "
                "detected only as an importable optional dependency."
            ),
            module="docling",
            fallback=(
                "Layout-level structure is not inferred; deterministic PyMuPDF/pdfplumber/OCR "
                "extraction remains the default path."
            ),
            warnings=[
                "docling_importable_but_conversion_disabled",
                "docling_model_downloads_disabled_in_tests",
            ]
            if docling_available
            else ["python_module_missing:docling"],
        ),
        ocr=DocumentToolCapability(
            name="Tesseract OCR",
            status="available"
            if tesseract_path and pytesseract_available and pillow_available
            else "unavailable",
            purpose="OCR selected high-priority scanned pages/images.",
            module="pytesseract",
            command=tesseract_path,
            fallback="Scanned/image-only documents are recorded without numeric extraction.",
            warnings=_ocr_warnings(tesseract_path, pytesseract_available, pillow_available),
        ),
        dxf_parsing=DocumentToolCapability(
            name="ezdxf",
            status="available" if ezdxf_available else "unavailable",
            purpose="Parse local DXF layers, text entities, blocks, and dimensions.",
            module="ezdxf",
            fallback="DXF files remain inventory-only without CAD-derived evidence.",
            warnings=[] if ezdxf_available else ["python_module_missing:ezdxf"],
        ),
        dwg_conversion=DocumentToolCapability(
            name="Local DWG converter",
            status="installed_import_only" if dwg_converter else "unsupported_without_converter",
            purpose=(
                "Detect a local DWG-to-DXF tool. Conversion is not executed by the current "
                "document-pack pipeline."
            ),
            command=dwg_converter,
            fallback=(
                "DWG files remain inventory-only until conversion, DXF parsing and evidence "
                "validation are wired into the request."
            ),
            warnings=(
                ["dwg_converter_detected_but_execution_disabled"]
                if dwg_converter
                else ["local_dwg_converter_missing"]
            ),
        ),
        coordinate_conversion=DocumentToolCapability(
            name="pyproj",
            status="available" if pyproj_available else "unavailable",
            purpose="Convert recognized projected coordinates to WGS84.",
            module="pyproj",
            fallback="Source coordinate values are preserved with conversion status unavailable.",
            warnings=[] if pyproj_available else ["python_module_missing:pyproj"],
        ),
        groq_bounded_extraction=DocumentToolCapability(
            name="Groq openai/gpt-oss-120b bounded document extraction",
            status="available" if groq_bounded_extraction_enabled else "unavailable",
            purpose=(
                "Extract structured fields from selected chunks with evidence and Pydantic "
                "validation."
            ),
            fallback=(
                "Document packs use deterministic extraction; Groq remains active for "
                "requirements/edit flows unless this pack extractor is explicitly wired."
            ),
            warnings=[]
            if groq_bounded_extraction_enabled
            else ["document_pack_groq_bounded_extraction_not_enabled"],
        ),
    )


def _module_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _ocr_warnings(
    tesseract_path: str | None,
    pytesseract_available: bool,
    pillow_available: bool,
) -> list[str]:
    warnings = []
    if not tesseract_path:
        warnings.append("command_missing:tesseract")
    if not pytesseract_available:
        warnings.append("python_module_missing:pytesseract")
    if not pillow_available:
        warnings.append("python_module_missing:PIL")
    return warnings
