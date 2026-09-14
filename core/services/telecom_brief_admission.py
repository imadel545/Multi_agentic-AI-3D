"""Admission of extracted site requirements, independent of provider success."""

from core.contracts.requirements import RequirementSpec

TELECOM_BRIEF_REQUIRED = "TELECOM_BRIEF_REQUIRED"
TELECOM_BRIEF_MESSAGE = (
    "Aucune caractéristique du site télécom n’a été identifiée dans cette demande. "
    "Précisez le type de site, le réseau, les dimensions ou les équipements à installer. "
    "Pour concevoir un objet sans site télécom, choisissez Intention libre. "
    "Une demande d’analyse d’image ne définit pas à elle seule un design."
)

# These fields describe the site being confirmed. Display options and absent
# accessories are not design evidence, even if their boolean defaults are tagged
# as text-derived by the legacy extractor.
SITE_IDENTITY_FIELDS = (
    "network_type", "tower_type", "tower_height_m", "sector_count",
    "antenna_install_height_m", "azimuths_deg",
)


def has_site_requirement_evidence(requirements: RequirementSpec) -> bool:
    return any(
        evidence.explicit and not evidence.defaulted
        for field in SITE_IDENTITY_FIELDS
        if (evidence := requirements.field_evidence.get(field)) is not None
    )
