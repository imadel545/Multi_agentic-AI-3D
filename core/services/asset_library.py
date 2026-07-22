from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

CATALOG_SCHEMA_VERSION = "1.1.0"
CAD_EXTENSIONS = {"dwg", "dxf", "dwt", "dws"}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "tif", "tiff", "gif"}


class AssetLibraryError(RuntimeError):
    pass


class AssetLibraryNotFound(AssetLibraryError):
    pass


class AssetLibraryService:
    def __init__(self, library_root: Path, dwgread_binary: str | None = None) -> None:
        self.library_root = library_root
        self.raw_dir = library_root / "raw" / "maj_des_blocs"
        self.index_dir = library_root / "index"
        self.catalog_path = self.index_dir / "catalog.jsonl"
        self.summary_path = self.index_dir / "summary.json"
        self.dwgread_binary = dwgread_binary or shutil.which("dwgread")
        self._catalog_identity: tuple[int, int] | None = None
        self._entries: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}

    def summary(self) -> dict[str, Any]:
        if not self.summary_path.is_file():
            return {
                "status": "not_ingested",
                "schema_version": CATALOG_SCHEMA_VERSION,
                "raw_root_exists": self.raw_dir.is_dir(),
                "catalog_available": False,
                "generation_eligible_count": 0,
                "limitations": [
                    "La bibliothèque brute n'est pas encore cataloguée.",
                    "Aucun asset externe n'est automatiquement éligible à Blender.",
                ],
            }
        payload = json.loads(self.summary_path.read_text(encoding="utf-8"))
        payload["catalog_available"] = True
        payload["dwg_probe_available"] = bool(self.dwgread_binary)
        return payload

    def search(
        self,
        query: str,
        *,
        claimed_dimension: str | None = None,
        extension: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        entries = self._load_catalog()
        query_tokens = _tokens(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in entries:
            if claimed_dimension and entry["claimed_dimension"] != claimed_dimension:
                continue
            if extension and entry["extension"] != extension.lower().lstrip("."):
                continue
            entry_tokens = set(entry["search_tokens"])
            overlap = len(query_tokens & entry_tokens)
            phrase_bonus = 2.0 if query and _normalize(query) in entry["normalized_path"] else 0.0
            if query_tokens and overlap == 0 and phrase_bonus == 0:
                continue
            score = overlap * 3.0 + phrase_bonus
            if entry["duplicate_of"] is None:
                score += 0.25
            scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1]["relative_path"]))
        results = []
        for score, entry in scored[: max(1, min(limit, 100))]:
            public = _public_entry(entry)
            public["retrieval_score"] = round(score, 3)
            results.append(public)
        return {
            "query": query,
            "filters": {
                "claimed_dimension": claimed_dimension,
                "extension": extension,
            },
            "result_count": len(results),
            "results": results,
            "selection_policy": "metadata_retrieval_only",
            "generation_eligible": False,
            "next_action": (
                "Qualifier la licence, sonder la géométrie puis convertir et valider l'asset."
            ),
        }

    def get(self, file_id: str) -> dict[str, Any]:
        self._load_catalog()
        entry = self._by_id.get(file_id)
        if entry is None:
            raise AssetLibraryNotFound(f"unknown library file_id: {file_id}")
        return _public_entry(entry)

    def probe(self, file_id: str, timeout_s: float = 60.0) -> dict[str, Any]:
        self._load_catalog()
        entry = self._by_id.get(file_id)
        if entry is None:
            raise AssetLibraryNotFound(f"unknown library file_id: {file_id}")
        if entry["extension"] != "dwg":
            raise AssetLibraryError(
                "Le probe géométrique est actuellement limité aux fichiers DWG."
            )
        if not self.dwgread_binary:
            raise AssetLibraryError(
                "dwgread est indisponible; aucun probe DWG ne peut être exécuté."
            )
        source = (self.raw_dir / entry["relative_path"]).resolve()
        if not source.is_relative_to(self.raw_dir.resolve()) or not source.is_file():
            raise AssetLibraryError(
                "Le fichier catalogué n'est plus disponible dans la zone brute."
            )
        with tempfile.TemporaryDirectory(prefix="telecom-dwg-probe-") as temp_dir:
            output = Path(temp_dir) / "probe.min.json"
            try:
                completed = subprocess.run(
                    [self.dwgread_binary, "-O", "minJSON", "-o", str(output), str(source)],
                    capture_output=True,
                    timeout=timeout_s,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise AssetLibraryError(
                    "Le probe DWG a dépassé le délai autorisé; le fichier reste en quarantaine."
                ) from exc
            except OSError as exc:
                raise AssetLibraryError(
                    "dwgread n'a pas pu être exécuté; le fichier reste en quarantaine."
                ) from exc
            if completed.returncode != 0 or not output.is_file():
                diagnostic = _decode_process_output(completed.stderr)
                raise AssetLibraryError(
                    "Le probe DWG a échoué; le fichier reste en quarantaine. "
                    f"dwgread={diagnostic[:300]}"
                )
            try:
                payload = json.loads(output.read_bytes())
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AssetLibraryError(
                    "Le probe DWG a produit une sortie JSON illisible; "
                    "le fichier reste en quarantaine."
                ) from exc
        entity_counts: Counter[str] = Counter()
        for node in _walk_json(payload):
            entity = node.get("entity")
            if isinstance(entity, str):
                entity_counts[entity] += 1
        header = payload.get("HEADER") if isinstance(payload, dict) else {}
        file_header = payload.get("FILEHEADER") if isinstance(payload, dict) else {}
        contains_acis = entity_counts["3DSOLID"] > 0 or entity_counts["BODY"] > 0
        mesh_convertible = any(
            entity_counts[name] > 0 for name in ("3DFACE", "MESH", "POLYLINE_3D", "POLYLINE_PFACE")
        )
        if contains_acis:
            conversion_route = "requires_acis_brep_bridge"
        elif mesh_convertible:
            conversion_route = "libredwg_dxf_mesh_candidate"
        else:
            conversion_route = "reference_or_2d_candidate"
        return {
            "file": _public_entry(entry),
            "probe_status": "completed",
            "tool": "dwgread",
            "dwg_version": file_header.get("version") if isinstance(file_header, dict) else None,
            "declared_unit": header.get("unit1_name") if isinstance(header, dict) else None,
            "entity_counts": dict(sorted(entity_counts.items())),
            "contains_acis_3d_solids": contains_acis,
            "contains_mesh_convertible_geometry": mesh_convertible,
            "conversion_route": conversion_route,
            "blender_ready": False,
            "generation_eligible": False,
            "limitations": [
                "Le probe prouve les types d'entités, pas la qualité du futur maillage.",
                (
                    "Les solides ACIS exigent une passerelle CAD B-Rep avant Blender."
                    if contains_acis
                    else "Une conversion et une QA géométrique restent obligatoires."
                ),
                "La licence et les unités doivent être confirmées avant validation.",
            ],
        }

    def _load_catalog(self) -> list[dict[str, Any]]:
        if not self.catalog_path.is_file():
            raise AssetLibraryError("Le catalogue de la bibliothèque n'est pas disponible.")
        stat = self.catalog_path.stat()
        identity = (stat.st_mtime_ns, stat.st_size)
        if identity == self._catalog_identity:
            return self._entries
        entries = [
            json.loads(line)
            for line in self.catalog_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self._entries = entries
        self._by_id = {entry["file_id"]: entry for entry in entries}
        self._catalog_identity = identity
        return entries


def _decode_process_output(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return (value or "").strip()


def build_asset_library_catalog(raw_dir: Path, index_dir: Path) -> dict[str, Any]:
    if not raw_dir.is_dir():
        raise AssetLibraryError(f"raw asset library not found: {raw_dir}")
    index_dir.mkdir(parents=True, exist_ok=True)
    content_owner: dict[str, str] = {}
    extension_counts: Counter[str] = Counter()
    dimension_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    duplicate_count = 0
    total_bytes = 0
    entries: list[dict[str, Any]] = []
    for path in sorted(item for item in raw_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(raw_dir).as_posix()
        sha256 = _sha256_file(path)
        file_id = "lib_" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:20]
        duplicate_of = content_owner.get(sha256)
        if duplicate_of is None:
            content_owner[sha256] = file_id
        else:
            duplicate_count += 1
        parts = Path(relative).parts
        claimed_dimension = (
            parts[0].lower() if parts and parts[0].lower() in {"2d", "3d"} else "unspecified"
        )
        category = parts[1] if len(parts) > 1 else "uncategorized"
        extension = path.suffix.lower().lstrip(".") or "none"
        size = path.stat().st_size
        normalized_path = _normalize(relative)
        entry = {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "file_id": file_id,
            "content_sha256": sha256,
            "relative_path": relative,
            "normalized_path": normalized_path,
            "extension": extension,
            "size_bytes": size,
            "claimed_dimension": claimed_dimension,
            "category": category,
            "search_tokens": sorted(_tokens(relative)),
            "duplicate_of": duplicate_of,
            "license_status": "unknown_requires_review",
            "qualification_status": "quarantined_unverified",
            "conversion_status": "not_attempted",
            "generation_eligible": False,
            "dwg_header_version": _dwg_header(path) if extension == "dwg" else None,
        }
        entries.append(entry)
        total_bytes += size
        extension_counts[extension] += 1
        dimension_counts[claimed_dimension] += 1
        category_counts[category] += 1
    preview_link_count = _link_reference_previews(entries)
    cad_with_preview_count = sum(
        1
        for entry in entries
        if entry["extension"] in CAD_EXTENSIONS and entry["reference_preview_file_ids"]
    )
    catalog_path = index_dir / "catalog.jsonl"
    summary_path = index_dir / "summary.json"
    _atomic_write(
        catalog_path,
        "".join(
            json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n" for entry in entries
        ),
    )
    summary = {
        "status": "catalogued_quarantined",
        "schema_version": CATALOG_SCHEMA_VERSION,
        "source_name": "MAJ des Blocs",
        "file_count": len(entries),
        "unique_content_count": len(content_owner),
        "duplicate_file_count": duplicate_count,
        "total_bytes": total_bytes,
        "extension_counts": dict(extension_counts.most_common()),
        "claimed_dimension_counts": dict(dimension_counts.most_common()),
        "category_counts": dict(category_counts.most_common()),
        "license_status": "unknown_requires_review",
        "generation_eligible_count": 0,
        "cad_with_reference_preview_count": cad_with_preview_count,
        "reference_preview_link_count": preview_link_count,
        "raw_files_modified": False,
        "limitations": [
            "Aucune licence globale n'a été détectée dans la bibliothèque source.",
            "Les dossiers 2D/3D sont des classifications source non vérifiées.",
            "Les DWG 3DSOLID exigent une conversion CAD B-Rep avant Blender.",
            "Aucun fichier brut n'est automatiquement sélectionnable pour la génération.",
        ],
    }
    _atomic_write(summary_path, json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return summary


def _public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entry.items() if key != "normalized_path"}


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _normalize(value)) if len(token) > 1}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()


def _link_reference_previews(entries: list[dict[str, Any]]) -> int:
    """Link nearby preview images without treating them as geometry proof."""
    by_directory: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for entry in entries:
        directory = str(Path(entry["relative_path"]).parent)
        group = by_directory.setdefault(directory, {"cad": [], "images": []})
        if entry["extension"] in CAD_EXTENSIONS:
            group["cad"].append(entry)
        elif entry["extension"] in IMAGE_EXTENSIONS:
            group["images"].append(entry)
        entry["reference_preview_file_ids"] = []
        entry["related_cad_file_ids"] = []

    links = 0
    for group in by_directory.values():
        cad_stems = [(_normalized_stem(item["relative_path"]), item) for item in group["cad"]]
        for image_entry in group["images"]:
            image_stem = _normalized_stem(image_entry["relative_path"])
            candidates = [
                (len(cad_stem), cad_entry)
                for cad_stem, cad_entry in cad_stems
                if _is_reference_preview_stem(cad_stem, image_stem)
            ]
            if not candidates:
                continue
            _, owner = max(candidates, key=lambda item: item[0])
            owner["reference_preview_file_ids"].append(image_entry["file_id"])
            image_entry["related_cad_file_ids"].append(owner["file_id"])
            links += 1
    return links


def _normalized_stem(relative_path: str) -> str:
    stem = Path(relative_path).stem
    stem = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", stem)
    return _normalize(stem)


def _is_reference_preview_stem(cad_stem: str, image_stem: str) -> bool:
    if not cad_stem or not image_stem:
        return False
    if image_stem == cad_stem:
        return True
    if not image_stem.startswith(cad_stem + " "):
        return False
    suffix = image_stem.removeprefix(cad_stem).split()
    allowed = {"view", "vue", "preview", "render", "image", "img", "front", "rear", "side"}
    return bool(suffix) and all(token.isdigit() or token in allowed for token in suffix)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dwg_header(path: Path) -> str | None:
    try:
        header = path.open("rb").read(6).decode("ascii")
    except (OSError, UnicodeDecodeError):
        return None
    return header if re.fullmatch(r"AC10\d{2}", header) else None


def _walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=f".{path.name}."
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)
