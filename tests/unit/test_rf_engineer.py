import pytest

from core.agents.rf_engineer import RfEngineerAgent
from core.contracts.requirements import RequirementSpec


@pytest.fixture
def agent() -> RfEngineerAgent:
    return RfEngineerAgent()


@pytest.fixture
def valid_requirements() -> RequirementSpec:
    return RequirementSpec(
        tower_type="lattice_tower",
        tower_height_m=30,
        sector_count=3,
        antenna_install_height_m=24,
        azimuths_deg=[0, 120, 240],
        beamwidth_deg=65,
        mechanical_tilt_deg=3,
    )


def test_rf_engineer_passes_valid(agent, valid_requirements):
    report = agent.validate(valid_requirements)
    assert report.status == "passed"
    assert report.rf_score == 1.0
    assert report.min_spacing_deg == 120.0


def test_rf_engineer_warns_on_narrow_spacing(agent, valid_requirements):
    req = valid_requirements.model_copy(update={"azimuths_deg": [0, 10, 20]})
    report = agent.validate(req)
    assert any(w.code == "RF_AZIMUTH_SPACING_LOW" for w in report.warnings)


def test_rf_engineer_errors_on_overlap(agent, valid_requirements):
    req = valid_requirements.model_copy(update={"azimuths_deg": [0, 0, 120]})
    report = agent.validate(req)
    assert report.status == "failed"
    assert any(e.code == "RF_SECTOR_OVERLAP" for e in report.errors)


def test_rf_engineer_preserves_sector_identity_when_reporting_overlap(agent, valid_requirements):
    req = valid_requirements.model_copy(update={"azimuths_deg": [120, 0, 5]})
    report = agent.validate(req)
    assert report.overlap_sectors == [("S2", "S3")]


def test_rf_engineer_warns_on_high_tilt(agent, valid_requirements):
    req = valid_requirements.model_copy(update={"mechanical_tilt_deg": 20})
    report = agent.validate(req)
    assert any(w.code == "RF_TILT_HIGH" for w in report.warnings)


def test_rf_engineer_does_not_infer_coverage_from_sector_spacing(agent, valid_requirements):
    req = valid_requirements.model_copy(update={"beamwidth_deg": 30})
    report = agent.validate(req)
    assert report.checks["beamwidth_value_valid"] is True
    assert not any(w.code == "RF_BEAMWIDTH_NARROW" for w in report.warnings)


def test_rf_engineer_rejects_beamwidth_above_supported_range(agent, valid_requirements):
    req = valid_requirements.model_copy(update={"beamwidth_deg": 220})
    report = agent.validate(req)
    assert report.status == "failed"
    assert report.checks["beamwidth_value_valid"] is False
    assert any(error.code == "RF_BEAMWIDTH_INVALID" for error in report.errors)
