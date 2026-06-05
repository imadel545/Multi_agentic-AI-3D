# Asset Registry

The asset registry is manifest-first. Blender assets are selected only through validated
JSON manifests in `assets/manifests`.

Manifest fields:

- `asset_id`
- `type`
- `file`
- `height_m`
- `dimensions_m`
- `compatible_networks`
- `compatible_tower_types`
- `mount_zones`
- `status`
- `version`

Only `status = validated` assets are eligible for automatic selection.
