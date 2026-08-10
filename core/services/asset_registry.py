import hashlib
import json
from pathlib import Path

from core.contracts.assembly import AssetCandidateScore, AssetManifestSnapshot, _canonical_sha256
from core.contracts.assets import AssetManifest
from core.performance import asset_manifest_hash


class AssetRegistry:
    def __init__(self, manifests_dir: Path) -> None:
        self.manifests_dir = manifests_dir
        self._assets: dict[str, AssetManifest] | None = None
        self._manifest_hash: str | None = None
        self.cache_hits = 0
        self.cache_misses = 0

    def list_assets(self) -> list[AssetManifest]:
        return sorted(self._load().values(), key=lambda asset: asset.asset_id)

    def get(self, asset_id: str) -> AssetManifest:
        assets = self._load()
        if asset_id not in assets:
            raise KeyError(f"unknown asset_id: {asset_id}")
        return assets[asset_id]

    def manifest_snapshot(
        self,
        asset_id: str,
        *,
        generation_mode: str,
    ) -> AssetManifestSnapshot:
        """Create a self-hashed immutable snapshot from the authoritative manifest file."""

        asset = self.get(asset_id)
        manifest_path = self.manifests_dir / f"{asset_id}.json"
        if not manifest_path.is_file():
            raise ValueError(f"ASSET_MANIFEST_FILE_MISSING:{asset_id}")
        try:
            source_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"ASSET_MANIFEST_FILE_INVALID:{asset_id}") from exc
        if source_payload.get("asset_id") != asset_id:
            raise ValueError(f"ASSET_MANIFEST_ID_MISMATCH:{asset_id}")
        if generation_mode not in asset.qualification.allowed_generation_modes:
            raise ValueError(f"ASSET_GENERATION_MODE_NOT_AUTHORIZED:{asset_id}:{generation_mode}")
        snapshot_payload = {
            "asset_id": asset.asset_id,
            "asset_type": asset.type,
            "manifest_version": asset.version,
            "manifest_file_name": manifest_path.name,
            "source_manifest_sha256": _sha256(manifest_path),
            "asset_file": asset.file,
            "generation_mode": generation_mode,
            "units": asset.qualification.units,
            "verified_file_sha256": asset.qualification.verified_file_sha256,
            "builder_profile_id": asset.builder_profile_id,
            "dimensions_m": asset.dimensions_m.model_dump(mode="json")
            if asset.dimensions_m
            else None,
            "anchors": [anchor.model_dump(mode="json") for anchor in asset.anchors],
            "connectors": [connector.model_dump(mode="json") for connector in asset.connectors],
            "allowed_parameters": [
                parameter.model_dump(mode="json") for parameter in asset.allowed_parameters
            ],
            "transform_permissions": asset.transform_permissions.model_dump(mode="json")
            if asset.transform_permissions
            else None,
            "import_fallback_allowed": asset.import_fallback_allowed,
        }
        snapshot_payload["snapshot_sha256"] = _canonical_sha256(snapshot_payload)
        return AssetManifestSnapshot.model_validate(snapshot_payload)

    def select_tower(
        self, tower_type: str, network_type: str, min_height_m: float
    ) -> AssetManifest:
        candidates = [
            asset
            for asset in self.list_assets()
            if asset.type == "tower"
            and asset.is_generation_eligible
            and network_type in asset.compatible_networks
            and tower_type in asset.compatible_tower_types
        ]
        if not candidates:
            raise LookupError(
                f"no validated tower asset for {tower_type}/{network_type}/{min_height_m}m"
            )
        # Prefer a tower tall enough, otherwise pick the closest height.
        tall_enough = [a for a in candidates if (a.height_m or 0) >= min_height_m]
        if tall_enough:
            return sorted(tall_enough, key=lambda asset: asset.height_m or 0)[0]
        return sorted(candidates, key=lambda asset: asset.height_m or 0, reverse=True)[0]

    def select_tower_fallback(
        self, tower_type: str, network_type: str, min_height_m: float
    ) -> AssetManifest:
        candidates = [
            asset
            for asset in self.list_assets()
            if asset.type == "tower"
            and asset.is_generation_eligible
            and network_type in asset.compatible_networks
        ]
        if not candidates:
            raise LookupError(
                f"no fallback tower asset for {tower_type}/{network_type}/{min_height_m}m"
            )
        # Prefer a tower tall enough with the right type, otherwise closest match.
        tall_enough = [
            a
            for a in candidates
            if (a.height_m or 0) >= min_height_m
            and _tower_type_distance(tower_type, a.compatible_tower_types) == 0
        ]
        if tall_enough:
            return sorted(
                tall_enough,
                key=lambda asset: (
                    _tower_type_distance(tower_type, asset.compatible_tower_types),
                    asset.height_m or 0,
                    asset.asset_id,
                ),
            )[0]
        return sorted(
            candidates,
            key=lambda asset: (
                _tower_type_distance(tower_type, asset.compatible_tower_types),
                -(asset.height_m or 0),
                asset.asset_id,
            ),
        )[0]

    def select_asset(
        self, asset_type: str, network_type: str, tower_type: str | None = None
    ) -> AssetManifest:
        candidates = [
            asset
            for asset in self.list_assets()
            if asset.type == asset_type
            and asset.is_generation_eligible
            and network_type in asset.compatible_networks
            and (
                not tower_type
                or not asset.compatible_tower_types
                or tower_type in asset.compatible_tower_types
            )
        ]
        if not candidates:
            raise LookupError(f"no validated {asset_type} asset for {network_type}")
        return self.rank_candidates(
            asset_type=asset_type,
            network_type=network_type,
            tower_type=tower_type,
        )[0][0]

    def rank_candidates(
        self,
        *,
        asset_type: str,
        network_type: str,
        tower_type: str | None = None,
        min_height_m: float | None = None,
    ) -> list[tuple[AssetManifest, AssetCandidateScore]]:
        """Return all generation-eligible candidates with reproducible scoring.

        The scorer is deliberately deterministic. A bounded LLM may choose only
        from this ordered list; it never invents an asset ID or a transform.
        """
        candidates = [
            asset
            for asset in self.list_assets()
            if asset.type == asset_type
            and asset.is_generation_eligible
            and network_type in asset.compatible_networks
            and (
                not tower_type
                or not asset.compatible_tower_types
                or tower_type in asset.compatible_tower_types
            )
        ]
        if not candidates:
            raise LookupError(f"no validated {asset_type} asset for {network_type}")
        scored = [
            (
                asset,
                _candidate_score(
                    asset,
                    network_type=network_type,
                    tower_type=tower_type,
                    min_height_m=min_height_m,
                ),
            )
            for asset in candidates
        ]
        return sorted(scored, key=lambda item: (-item[1].total_score, item[0].asset_id))

    def select_asset_fallback(
        self,
        asset_type: str,
        network_type: str,
        tower_type: str | None = None,
    ) -> AssetManifest:
        candidates = [
            asset
            for asset in self.list_assets()
            if asset.type == asset_type
            and asset.is_generation_eligible
            and network_type in asset.compatible_networks
            and (
                not tower_type
                or not asset.compatible_tower_types
                or tower_type in asset.compatible_tower_types
            )
        ]
        if not candidates and tower_type:
            candidates = [
                asset
                for asset in self.list_assets()
                if asset.type == asset_type
                and asset.is_generation_eligible
                and network_type in asset.compatible_networks
            ]
        if not candidates:
            raise LookupError(f"no fallback {asset_type} asset for {network_type}")
        return sorted(candidates, key=lambda asset: asset.asset_id)[0]

    def _load(self) -> dict[str, AssetManifest]:
        current_hash = asset_manifest_hash(self.manifests_dir)
        if self._assets is not None and self._manifest_hash == current_hash:
            self.cache_hits += 1
            return self._assets
        self.cache_misses += 1
        assets: dict[str, AssetManifest] = {}
        for manifest_path in sorted(self.manifests_dir.glob("*.json")):
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            asset = AssetManifest.model_validate(payload)
            if asset.asset_id in assets:
                raise ValueError(f"duplicate asset_id in manifests: {asset.asset_id}")
            assets[asset.asset_id] = asset
        self._assets = assets
        self._manifest_hash = current_hash
        return assets

    @property
    def manifest_hash(self) -> str:
        return asset_manifest_hash(self.manifests_dir)

    def cache_stats(self) -> dict[str, int]:
        return {
            "asset_cache_hits": self.cache_hits,
            "asset_cache_misses": self.cache_misses,
        }


def _tower_type_distance(requested: str, compatible_tower_types: list[str]) -> int:
    if requested in compatible_tower_types:
        return 0
    requested_lower = requested.lower()
    for tower_type in compatible_tower_types:
        family = tower_type.removesuffix("_tower").removesuffix("_mast")
        if family and family in requested_lower:
            return 1
    return 2


def _candidate_score(
    asset: AssetManifest,
    *,
    network_type: str,
    tower_type: str | None,
    min_height_m: float | None,
) -> AssetCandidateScore:
    compatibility = 70.0
    reasons = [f"compatible avec le réseau {network_type}"]
    if tower_type:
        if not asset.compatible_tower_types or tower_type in asset.compatible_tower_types:
            compatibility += 30.0
            reasons.append(f"compatible avec le support {tower_type}")
    if asset.allows_generation_mode("imported_glb_exact"):
        generation = 100.0
        reasons.append("import GLB exact qualifié")
    else:
        generation = 75.0
        reasons.append("génération paramétrique qualifiée")
    fidelity = {
        "schematic": 35.0,
        "technical_generic": 65.0,
        "vendor_qualified": 100.0,
    }[asset.geometry_fidelity]
    reasons.append(
        {
            "schematic": "fidélité schématique déclarée",
            "technical_generic": "fidélité technique générique déclarée",
            "vendor_qualified": "géométrie fournisseur qualifiée",
        }[asset.geometry_fidelity]
    )
    dimensional = 100.0
    if min_height_m is not None and asset.height_m is not None:
        if asset.height_m >= min_height_m:
            reasons.append("hauteur nominale suffisante")
        else:
            dimensional = max(0.0, 100.0 - ((min_height_m - asset.height_m) / min_height_m) * 100)
            reasons.append("hauteur nominale inférieure à la cible")
    total = round(
        compatibility * 0.35 + fidelity * 0.3 + generation * 0.2 + dimensional * 0.15,
        2,
    )
    return AssetCandidateScore(
        asset_id=asset.asset_id,
        total_score=total,
        compatibility_score=round(compatibility, 2),
        generation_score=generation,
        dimensional_score=round(dimensional, 2),
        fidelity_score=fidelity,
        reasons=reasons,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
