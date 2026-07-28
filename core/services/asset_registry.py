import json
from pathlib import Path

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
        return candidates[0]

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
