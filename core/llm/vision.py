from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import Field, ValidationError

from core.contracts.common import StrictModel
from core.contracts.vision import (
    ModelInvocationEvidence,
    VisionCapability,
    VisionCapabilityHealth,
    VisualDefectObservation,
    VisualEvidencePacket,
    VisualObservedObject,
    VisualSpatialRelation,
    VisualTextObservation,
)
from core.llm.groq_policy import GroqVisionRequestPolicy
from core.llm.profiles import GroqCapabilityProfile, GroqCapabilityProfiles
from core.llm.transport import GroqTransport, GroqTransportError, chat_message_json
from core.llm.vision_preprocessing import VisionImageInput, VisionImagePreprocessor

_DETERMINISTIC_LIMITATIONS = (
    "Advisory visual interpretation only; not exact dimensional, structural, RF, "
    "licensing, manufacturer-identity, or certification evidence.",
    "Only the supplied raster pixels were analyzed; hidden geometry and source CAD "
    "semantics were not inspected.",
)


class VisionConsentRequiredError(PermissionError):
    pass


class VisionCapabilityDisabledError(RuntimeError):
    pass


class VisionModelOutputError(RuntimeError):
    pass


class _VisionModelOutput(StrictModel):
    observed_objects: list[VisualObservedObject] = Field(default_factory=list, max_length=128)
    text_observations: list[VisualTextObservation] = Field(default_factory=list, max_length=128)
    spatial_relations: list[VisualSpatialRelation] = Field(default_factory=list, max_length=128)
    suspected_defects: list[VisualDefectObservation] = Field(default_factory=list, max_length=64)
    confidence: float = Field(ge=0, le=1)
    limitations: list[str] = Field(default_factory=list, max_length=12)


class GroqVisionClient:
    """Opt-in, advisory Qwen vision client with local contract validation."""

    def __init__(
        self,
        *,
        transport: GroqTransport,
        profiles: GroqCapabilityProfiles,
        preprocessor: VisionImagePreprocessor | None = None,
    ) -> None:
        self.transport = transport
        self.profiles = profiles
        self.preprocessor = preprocessor or VisionImagePreprocessor()

    def analyze(
        self,
        *,
        capability: VisionCapability,
        images: list[VisionImageInput],
        instruction: str,
        consent_granted: bool,
    ) -> VisualEvidencePacket:
        profile = self.profiles.vision(capability)
        self._validate_request(profile, instruction, consent_granted)
        prepared = self.preprocessor.prepare_many(images)
        source_descriptors = [item.evidence_source.model_dump(mode="json") for item in prepared]
        schema = _VisionModelOutput.model_json_schema()
        system_prompt = _system_prompt(capability)
        request_text = (
            f"Task:\n{instruction.strip()}\n\n"
            "Supplied source descriptors:\n"
            f"{json.dumps(source_descriptors, ensure_ascii=False, separators=(',', ':'))}\n\n"
            "Required JSON shape:\n"
            f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}"
        )
        prompt_sha256 = hashlib.sha256(f"{system_prompt}\n{request_text}".encode()).hexdigest()
        input_sha256 = hashlib.sha256(
            "".join(item.evidence_source.source_sha256 for item in prepared).encode("ascii")
        ).hexdigest()
        policy = GroqVisionRequestPolicy(
            capability=capability,
            max_completion_tokens=profile.max_completion_tokens,
        )
        payload = policy.apply(
            {
                "model": profile.model,
                "temperature": 0.7,
                "top_p": 0.8,
                "reasoning_effort": "none",
                "messages": _messages(system_prompt, request_text, prepared),
            }
        )
        started = time.monotonic()
        total_attempts = 0
        response_mode = "json_object_validated"
        try:
            result = self.transport.request_chat_completion(
                capability=capability,
                payload=payload,
                timeout_s=profile.timeout_s,
            )
            total_attempts += result.attempts
            output = _VisionModelOutput.model_validate(chat_message_json(result.body))
            _validate_model_references(output, prepared)
        except GroqTransportError as exc:
            if not _repairable_json_rejection(exc):
                raise
            output, repair_attempts = self._repair_output(
                capability=capability,
                policy=policy,
                profile=profile,
                system_prompt=system_prompt,
                request_text=request_text,
                prepared=prepared,
            )
            total_attempts += exc.attempts + repair_attempts
            response_mode = "json_object_repaired"
        except (json.JSONDecodeError, TypeError, KeyError, ValueError, ValidationError):
            output, repair_attempts = self._repair_output(
                capability=capability,
                policy=policy,
                profile=profile,
                system_prompt=system_prompt,
                request_text=request_text,
                prepared=prepared,
            )
            total_attempts += repair_attempts
            response_mode = "json_object_repaired"

        limitations = _bounded_limitations(output.limitations)
        invocation = ModelInvocationEvidence(
            model=profile.model,
            capability=capability,
            prompt_sha256=prompt_sha256,
            input_sha256=input_sha256,
            response_mode=response_mode,
            latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            attempts=max(1, total_attempts),
            timestamp=datetime.now(UTC),
        )
        try:
            packet = VisualEvidencePacket(
                capability=capability,
                sources=[item.evidence_source for item in prepared],
                observed_objects=output.observed_objects,
                text_observations=output.text_observations,
                spatial_relations=output.spatial_relations,
                suspected_defects=output.suspected_defects,
                confidence=output.confidence,
                limitations=limitations,
                invocation=invocation,
            )
        except ValidationError as exc:
            self.transport.mark_failed(capability, "model_output_rejected")
            raise VisionModelOutputError(
                "vision evidence referenced unknown local sources or objects"
            ) from exc
        self.transport.mark_operational(capability)
        return packet

    def _repair_output(
        self,
        *,
        capability: VisionCapability,
        policy: GroqVisionRequestPolicy,
        profile: GroqCapabilityProfile,
        system_prompt: str,
        request_text: str,
        prepared,
    ) -> tuple[_VisionModelOutput, int]:
        """Make the single contract-authorized repair request."""

        repair_payload = policy.apply(
            {
                "model": profile.model,
                "temperature": 0.7,
                "top_p": 0.8,
                "reasoning_effort": "none",
                "messages": [
                    *_messages(system_prompt, request_text, prepared),
                    {
                        "role": "system",
                        "content": (
                            "The prior answer failed local schema validation. Return one "
                            "complete JSON object matching the supplied schema. Do not add "
                            "markdown, explanations, measurements, or unknown source IDs."
                        ),
                    },
                ],
            }
        )
        try:
            repaired = self.transport.request_chat_completion(
                capability=capability,
                payload=repair_payload,
                timeout_s=profile.timeout_s,
            )
            output = _VisionModelOutput.model_validate(chat_message_json(repaired.body))
            _validate_model_references(output, prepared)
            return output, repaired.attempts
        except GroqTransportError as exc:
            if not _repairable_json_rejection(exc):
                raise
            self.transport.mark_failed(capability, "model_output_rejected")
            raise VisionModelOutputError(
                "vision model output failed bounded local validation"
            ) from exc
        except (
            json.JSONDecodeError,
            TypeError,
            KeyError,
            ValueError,
            ValidationError,
        ) as exc:
            self.transport.mark_failed(capability, "model_output_rejected")
            raise VisionModelOutputError(
                "vision model output failed bounded local validation"
            ) from exc

    def health(self, capability: VisionCapability) -> VisionCapabilityHealth:
        profile = self.profiles.vision(capability)
        return self.transport.health(
            capability,
            enabled=profile.enabled,
            advisory_only=True,
        )

    @staticmethod
    def _validate_request(
        profile: GroqCapabilityProfile,
        instruction: str,
        consent_granted: bool,
    ) -> None:
        if not profile.enabled:
            raise VisionCapabilityDisabledError(
                f"vision capability {profile.capability} is disabled"
            )
        if not consent_granted:
            raise VisionConsentRequiredError(
                "explicit per-project consent is required before remote vision processing"
            )
        if not instruction.strip():
            raise ValueError("vision instruction must not be empty")
        if len(instruction) > 4000:
            raise ValueError("vision instruction exceeds the 4000-character limit")


def build_groq_vision_client(
    *,
    transport: GroqTransport,
    profiles: GroqCapabilityProfiles,
    max_images: int = 3,
    max_image_bytes: int = 20_000_000,
    max_output_pixels: int = 16_000_000,
    max_edge_px: int = 4096,
) -> GroqVisionClient:
    """Factory kept separate from transport ownership for safe shared lifecycle."""

    return GroqVisionClient(
        transport=transport,
        profiles=profiles,
        preprocessor=VisionImagePreprocessor(
            max_images=max_images,
            max_image_bytes=max_image_bytes,
            max_output_pixels=max_output_pixels,
            max_edge_px=max_edge_px,
        ),
    )


def _system_prompt(capability: VisionCapability) -> str:
    task = {
        "multimodal_interpretation": "interpret a design image, plan, diagram, or OCR target",
        "asset_visual_review": "review supplied qualified-asset preview images",
        "visual_design_critic": "review supplied scene previews as an advisory visual critic",
    }[capability]
    return (
        f"You {task}. Return a JSON object only. Use only supplied pixels and source IDs. "
        "Every object, text item, relation, and suspected defect must reference one supplied "
        "source_id. Use normalized regions when visually supportable. Do not infer exact "
        "dimensions, hidden geometry, manufacturer identity, licensing, structural or RF "
        "compliance, or certification. Treat uncertain content as uncertain and put caveats "
        "in limitations. Do not return private reasoning, Python, Blender code, markdown, "
        "URLs, local paths, or base64."
    )


def _messages(system_prompt: str, request_text: str, prepared) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": request_text}]
    content.extend({"type": "image_url", "image_url": {"url": item.data_url}} for item in prepared)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def _bounded_limitations(model_limitations: list[str]) -> list[str]:
    limitations: list[str] = []
    for value in [*model_limitations, *_DETERMINISTIC_LIMITATIONS]:
        normalized = " ".join(value.split())[:800]
        if normalized and normalized not in limitations:
            limitations.append(normalized)
    return limitations[:16]


def _validate_model_references(output: _VisionModelOutput, prepared) -> None:
    source_ids = {item.evidence_source.source_id for item in prepared}
    object_ids = {item.object_id for item in output.observed_objects}
    if len(object_ids) != len(output.observed_objects):
        raise ValueError("vision response contains duplicate object IDs")
    for collection in (
        output.observed_objects,
        output.text_observations,
        output.spatial_relations,
        output.suspected_defects,
    ):
        if any(item.source_id not in source_ids for item in collection):
            raise ValueError("vision response references an unknown source ID")
    for relation in output.spatial_relations:
        if relation.subject_object_id not in object_ids:
            raise ValueError("vision response relation references an unknown subject")
        if relation.object_object_id not in object_ids:
            raise ValueError("vision response relation references an unknown target")


def _repairable_json_rejection(exc: GroqTransportError) -> bool:
    return (
        exc.reason == "model_output_rejected"
        and exc.status_code == 400
        and exc.provider_error_code == "json_validate_failed"
    )
