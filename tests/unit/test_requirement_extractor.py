from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.requirements import RequirementSpec


class RecordingRequirementProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def extract_requirements(self, requirements_text: str, detail_level: str) -> RequirementSpec:
        self.calls.append((requirements_text, detail_level))
        return RequirementSpec(
            network_type="5G",
            site_type="telecom_site",
            tower_type="lattice_tower",
            tower_height_m=30,
            sector_count=3,
            antenna_type="panel_5g",
            antenna_install_height_m=24,
            azimuths_deg=[0, 120, 240],
            mechanical_tilt_deg=3,
            electrical_tilt_deg=0,
            beamwidth_deg=65,
            include_rru=True,
            include_cables=True,
            include_beams=True,
            include_labels=True,
            detail_level=detail_level,
            warnings=[],
        )


class FailingProvider:
    def extract_requirements(self, requirements_text: str, detail_level: str) -> RequirementSpec:
        raise RuntimeError("provider down")


def test_requirement_extractor_accepts_structured_provider() -> None:
    provider = RecordingRequirementProvider()
    extractor = RequirementExtractor(
        provider=provider,
        provider_name="groq:test-provider",
        enabled=True,
    )

    result = extractor.extract("Créer un site 5G treillis 30m avec 3 secteurs.", "high")

    assert provider.calls == [("Créer un site 5G treillis 30m avec 3 secteurs.", "high")]
    assert result.provider == "groq:test-provider"
    assert result.fallback_used is False
    assert result.requirements.tower_type == "lattice_tower"


def test_requirement_extractor_disabled_does_not_call_structured_provider() -> None:
    provider = RecordingRequirementProvider()
    extractor = RequirementExtractor(
        provider=provider,
        provider_name="groq:test-provider",
        enabled=True,
    )

    result = extractor.extract(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°.",
        "high",
        enabled=False,
    )

    assert provider.calls == []
    assert result.provider == "deterministic"
    assert result.fallback_used is True


def test_requirement_extractor_falls_back_on_provider_error() -> None:
    extractor = RequirementExtractor(
        provider=FailingProvider(),
        provider_name="groq:test-provider",
        enabled=True,
    )

    result = extractor.extract(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°.",
        "high",
    )

    assert result.provider == "deterministic"
    assert result.fallback_used is True
    assert result.error
    assert any(
        warning.code == "LLM_EXTRACTION_FALLBACK" for warning in result.requirements.warnings
    )
