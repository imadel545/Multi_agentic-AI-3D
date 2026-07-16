from dataclasses import dataclass
from typing import Protocol

from core.contracts.common import WarningItem
from core.contracts.requirements import RequirementSpec
from core.services.requirement_parser import parse_requirements_text


class RequirementProvider(Protocol):
    def extract_requirements(
        self, requirements_text: str, detail_level: str
    ) -> RequirementSpec: ...


@dataclass(frozen=True)
class ExtractionResult:
    requirements: RequirementSpec
    provider: str
    fallback_used: bool
    error: str | None = None


class RequirementExtractor:
    def __init__(
        self,
        provider: RequirementProvider | None = None,
        provider_name: str = "deterministic",
        enabled: bool = True,
    ) -> None:
        self.provider = provider
        self.provider_name = provider_name
        self.enabled = enabled

    def extract(
        self,
        requirements_text: str,
        detail_level: str,
        enabled: bool | None = None,
    ) -> ExtractionResult:
        # A request may opt out, but it must never override the server policy and
        # re-enable a provider that an operator deliberately disabled.
        effective_enabled = self.enabled and enabled is not False
        if self.provider is None or not effective_enabled:
            return ExtractionResult(
                requirements=parse_requirements_text(requirements_text, detail_level=detail_level),
                provider="deterministic",
                fallback_used=True,
            )
        try:
            requirements = self.provider.extract_requirements(requirements_text, detail_level)
            provider_fallback = any(
                warning.code == "LLM_JSON_OBJECT_FALLBACK" for warning in requirements.warnings
            )
            return ExtractionResult(
                requirements=requirements,
                provider=self.provider_name,
                fallback_used=provider_fallback,
            )
        except Exception as exc:
            requirements = parse_requirements_text(requirements_text, detail_level=detail_level)
            requirements.warnings.append(
                WarningItem(
                    code="LLM_EXTRACTION_FALLBACK",
                    message="Structured LLM extraction failed; deterministic parser was used.",
                )
            )
            return ExtractionResult(
                requirements=requirements,
                provider="deterministic",
                fallback_used=True,
                error=f"{type(exc).__name__}: {exc}",
            )
