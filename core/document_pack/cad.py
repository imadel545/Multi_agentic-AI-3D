import shutil
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from core.contracts.document_pack import CadStatus, DocumentExtractionStatus, DocumentReference
from core.document_pack.text_extractor import TextPage


@dataclass(frozen=True)
class CadExtractionResult:
    pages: list[TextPage]
    extraction_status: DocumentExtractionStatus
    cad_status: CadStatus
    tools: list[str]
    warnings: list[str]


def extract_cad_text_pages(document: DocumentReference, content: bytes) -> CadExtractionResult:
    if document.duplicate_of or document.extractability != "cad":
        return CadExtractionResult([], "not_attempted", document.cad_status, [], [])
    if document.extension == "dwg":
        converter = _local_dwg_converter()
        # DWG remains unsupported at extraction time; a local converter merely
        # signals that conversion to DXF could be attempted as a separate step.
        return CadExtractionResult(
            [],
            "unsupported",
            "unsupported",
            [converter.name] if converter else [],
            [
                "DWG requires local conversion to DXF before ezdxf parsing; "
                "no conversion was executed in this request."
            ],
        )
    if document.extension != "dxf":
        return CadExtractionResult(
            [], "unsupported", "unsupported", [], ["Unsupported CAD format."]
        )
    try:
        import ezdxf  # type: ignore[import-not-found]
    except ImportError:
        return CadExtractionResult(
            [],
            "inventory_only",
            "inventory_only",
            [],
            ["DXF recorded as inventory-only because ezdxf is not installed."],
        )
    try:
        decoded = content.decode("utf-8", errors="ignore")
        dxf = ezdxf.read(StringIO(decoded))
        pages: list[TextPage] = []
        layer_names = sorted(str(layer.dxf.name) for layer in dxf.layers)
        if layer_names:
            pages.append(
                TextPage(
                    page=None,
                    text="DXF layers: " + ", ".join(layer_names[:80]),
                    source_type="cad",
                    confidence=0.9,
                )
            )
        for entity in dxf.modelspace():
            kind = entity.dxftype()
            layer = getattr(entity.dxf, "layer", None)
            if kind == "TEXT":
                pages.append(_cad_page(f"DXF TEXT layer={layer}: {entity.dxf.text}", layer))
            elif kind == "MTEXT":
                pages.append(_cad_page(f"DXF MTEXT layer={layer}: {entity.text}", layer))
            elif kind in {"INSERT", "DIMENSION"}:
                name = getattr(entity.dxf, "name", kind)
                pages.append(_cad_page(f"DXF {kind} layer={layer}: {name}", layer))
            elif kind in {"POINT", "LINE", "LWPOLYLINE"}:
                coordinates = _entity_coordinates(entity)
                if coordinates:
                    pages.append(_cad_page(f"DXF {kind} layer={layer}: {coordinates}", layer))
        return CadExtractionResult(
            pages,
            "extracted" if pages else "no_text",
            "parsed",
            ["ezdxf"],
            [] if pages else ["DXF parsed but no text/layer/coordinate evidence was extracted."],
        )
    except Exception as exc:
        return CadExtractionResult(
            [],
            "failed",
            "inventory_only",
            ["ezdxf"],
            [f"DXF parsing failed with {type(exc).__name__}; file remains inventory-only."],
        )


def _cad_page(text: str, layer: str | None) -> TextPage:
    return TextPage(
        page=None,
        text=text,
        source_type="cad",
        confidence=0.86,
        layer=str(layer) if layer else None,
    )


def _entity_coordinates(entity) -> str:
    try:
        if entity.dxftype() == "POINT":
            point = entity.dxf.location
            return f"x={point.x:.3f}, y={point.y:.3f}, z={point.z:.3f}"
        if entity.dxftype() == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            return (
                f"start=({start.x:.3f},{start.y:.3f},{start.z:.3f}) "
                f"end=({end.x:.3f},{end.y:.3f},{end.z:.3f})"
            )
        if entity.dxftype() == "LWPOLYLINE":
            points = [f"({point[0]:.3f},{point[1]:.3f})" for point in entity.get_points()[:8]]
            return "points=" + ",".join(points)
    except Exception:
        return ""
    return ""


def _local_dwg_converter() -> Path | None:
    for command in ("ODAFileConverter", "FreeCAD", "dwg2dxf"):
        path = shutil.which(command)
        if path:
            return Path(path)
    return None
