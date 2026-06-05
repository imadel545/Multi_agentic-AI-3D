from core.contracts.assets import AssetManifest
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec, VisualElements


class ScenePlanner:
    def build_scene_spec(
        self,
        workflow_id: str,
        requirements: RequirementSpec,
        tower: AssetManifest,
        antenna: AssetManifest,
        radio: AssetManifest | None,
    ) -> SceneSpec:
        sectors = [
            SectorSpec(
                sector_id=f"S{index + 1}",
                antenna_asset_id=antenna.asset_id,
                radio_asset_id=radio.asset_id if radio else None,
                install_height_m=requirements.antenna_install_height_m,
                azimuth_deg=azimuth,
                mechanical_tilt_deg=requirements.mechanical_tilt_deg,
                electrical_tilt_deg=requirements.electrical_tilt_deg,
                beamwidth_deg=requirements.beamwidth_deg,
                include_cable=requirements.include_cables,
                include_label=requirements.include_labels,
            )
            for index, azimuth in enumerate(requirements.azimuths_deg)
        ]
        return SceneSpec(
            scene_id=workflow_id,
            network_type=requirements.network_type,
            tower=SceneAssetPlacement(
                asset_id=tower.asset_id,
                position=[0.0, 0.0, 0.0],
                rotation_deg=[0.0, 0.0, 0.0],
                scale=[1.0, 1.0, 1.0],
                height_m=requirements.tower_height_m,
            ),
            sectors=sectors,
            visual_elements=VisualElements(
                include_sector_beams=requirements.include_beams,
                include_azimuth_arrows=True,
                include_height_markers=True,
                include_labels=requirements.include_labels,
            ),
        )
