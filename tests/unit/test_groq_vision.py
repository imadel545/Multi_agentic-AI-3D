from __future__ import annotations

import io
import json

import httpx
import pytest
from pydantic import ValidationError

from core.contracts.requirements import RequirementCandidateEvidence, RequirementFieldEvidence
from core.llm.profiles import build_groq_capability_profiles
from core.llm.transport import GroqTransport
from core.llm.vision import (
    GroqVisionClient,
    VisionCapabilityDisabledError,
    VisionConsentRequiredError,
)
from core.llm.vision_preprocessing import (
    VisionImageInput,
    VisionImagePreprocessor,
    VisionPreprocessingError,
)


def test_vision_is_opt_in_json_object_validated_and_advisory() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _chat_response(request, _valid_output())

    transport, client = _runtime(handler)
    try:
        packet = client.analyze(
            capability="asset_visual_review",
            images=[VisionImageInput(content=_png(), file_name="/private/assets/antenna.png")],
            instruction="Review the antenna preview for obvious visual defects.",
            consent_granted=True,
        )

        assert captured["model"] == "qwen/qwen3.6-27b"
        assert captured["response_format"] == {"type": "json_object"}
        assert captured["stream"] is False
        assert captured["reasoning_effort"] == "none"
        user_content = captured["messages"][1]["content"]
        image_urls = [
            part["image_url"]["url"] for part in user_content if part["type"] == "image_url"
        ]
        assert len(image_urls) == 1
        assert image_urls[0].startswith("data:image/png;base64,")

        assert packet.advisory_only is True
        assert packet.sources[0].file_name == "antenna.png"
        assert packet.invocation.response_mode == "json_object_validated"
        assert packet.invocation.attempts == 1
        assert packet.suspected_defects[0].severity == "review_required"
        assert "base64" not in packet.model_dump_json()
        assert all("/private/" not in value for value in packet.limitations)
        assert client.health("asset_visual_review").status == "operational"
    finally:
        transport.close()


def test_vision_requires_consent_before_preprocessing_or_network() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _chat_response(request, _valid_output())

    transport, client = _runtime(handler)
    try:
        with pytest.raises(VisionConsentRequiredError):
            client.analyze(
                capability="multimodal_interpretation",
                images=[VisionImageInput(content=b"not-even-decoded", file_name="plan.png")],
                instruction="Read the plan.",
                consent_granted=False,
            )
        assert calls == 0
    finally:
        transport.close()


def test_visual_design_critic_remains_disabled_for_m1() -> None:
    transport, client = _runtime(lambda request: _chat_response(request, _valid_output()))
    try:
        assert client.health("visual_design_critic").status == "disabled"
        with pytest.raises(VisionCapabilityDisabledError):
            client.analyze(
                capability="visual_design_critic",
                images=[VisionImageInput(content=_png(), file_name="scene.png")],
                instruction="Critique the complete scene.",
                consent_granted=True,
            )
    finally:
        transport.close()


def test_invalid_model_output_gets_one_bounded_repair() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                request=request,
                json={"choices": [{"message": {"content": "not-json"}}]},
            )
        return _chat_response(request, _valid_output())

    transport, client = _runtime(handler)
    try:
        packet = client.analyze(
            capability="multimodal_interpretation",
            images=[VisionImageInput(content=_png(), file_name="plan.png", page=2)],
            instruction="Extract visible objects and text without inventing measurements.",
            consent_granted=True,
        )
        assert calls == 2
        assert packet.invocation.response_mode == "json_object_repaired"
        assert packet.invocation.attempts == 2
        assert packet.sources[0].page == 2
    finally:
        transport.close()


def test_provider_json_mode_rejection_gets_one_bounded_repair() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                400,
                request=request,
                json={"error": {"code": "json_validate_failed"}},
            )
        return _chat_response(request, _valid_output())

    transport, client = _runtime(handler)
    try:
        packet = client.analyze(
            capability="multimodal_interpretation",
            images=[VisionImageInput(content=_png(), file_name="plan.png")],
            instruction="Extract visible objects and text.",
            consent_granted=True,
        )
        assert calls == 2
        assert packet.invocation.response_mode == "json_object_repaired"
        assert packet.invocation.attempts == 2
    finally:
        transport.close()


def test_preprocessor_enforces_three_image_limit_and_magic_bytes() -> None:
    preprocessor = VisionImagePreprocessor()
    with pytest.raises(VisionPreprocessingError, match="at most 3"):
        preprocessor.prepare_many(
            [VisionImageInput(content=_png(), file_name=f"{index}.png") for index in range(4)]
        )
    with pytest.raises(VisionPreprocessingError, match="corrupt or unsupported"):
        preprocessor.prepare_many(
            [VisionImageInput(content=b"fake-png", file_name="misleading.png")]
        )


def test_preprocessor_resizes_and_strips_metadata_without_mutating_source() -> None:
    source = _png(width=1200, height=800, metadata={"local_path": "/secret/path"})
    original = bytes(source)
    prepared = VisionImagePreprocessor(
        max_output_pixels=1_000_000,
        max_edge_px=800,
    ).prepare_many([VisionImageInput(content=source, file_name="C:\\secret\\plan.png")])[0]

    assert source == original
    assert prepared.evidence_source.file_name == "plan.png"
    assert prepared.evidence_source.width_px <= 800
    assert prepared.evidence_source.height_px <= 800
    assert b"/secret/path" not in prepared.content
    assert prepared.evidence_source.source_sha256 != prepared.evidence_source.prepared_sha256


def test_vision_requirement_evidence_requires_local_source_provenance() -> None:
    with pytest.raises(ValidationError, match="visual source and input hash"):
        RequirementCandidateEvidence(
            value=36,
            source="vision",
            mechanism="qwen_visual_text_observation",
            confidence=0.8,
        )

    evidence = RequirementCandidateEvidence(
        value=36,
        source="vision",
        mechanism="qwen_visual_text_observation",
        confidence=0.8,
        visual_source_id="image_1",
        visual_input_sha256="a" * 64,
        source_page=2,
        selected=True,
    )
    assert evidence.source_page == 2
    assert evidence.visual_source_id == "image_1"


def test_vision_only_requirement_never_becomes_an_exact_confirmed_value() -> None:
    candidate = RequirementCandidateEvidence(
        value=36,
        source="vision",
        mechanism="qwen_visual_text_observation",
        confidence=0.8,
        visual_source_id="image_1",
        visual_input_sha256="b" * 64,
        selected=True,
    )
    with pytest.raises(ValidationError, match="remain inferred and require confirmation"):
        RequirementFieldEvidence(
            field="tower_height_m",
            selected_value=36,
            selected_source="vision",
            confidence=0.8,
            explicit=True,
            defaulted=False,
            candidates=[candidate],
            requires_confirmation=False,
            rationale="Visible label interpreted from the supplied image.",
        )

    inferred = RequirementFieldEvidence(
        field="tower_height_m",
        selected_value=36,
        selected_source="vision",
        confidence=0.8,
        explicit=False,
        defaulted=False,
        candidates=[candidate],
        requires_confirmation=True,
        rationale="Visible label interpreted from the supplied image; confirmation required.",
    )
    assert inferred.explicit is False
    assert inferred.requires_confirmation is True


def _runtime(handler):
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_key="test-key", client=http_client, sleeper=lambda _s: None)
    profiles = build_groq_capability_profiles(
        vision_enabled=True,
        visual_design_critic_enabled=False,
    )
    return transport, GroqVisionClient(transport=transport, profiles=profiles)


def _valid_output() -> dict:
    return {
        "observed_objects": [
            {
                "object_id": "object_antenna_1",
                "source_id": "image_1",
                "label": "panel antenna",
                "semantic_role": "antenna",
                "confidence": 0.92,
                "region": {"x": 0.2, "y": 0.1, "width": 0.4, "height": 0.7},
                "attributes": {"visible": True},
            }
        ],
        "text_observations": [],
        "spatial_relations": [],
        "suspected_defects": [
            {
                "source_id": "image_1",
                "code": "DETAIL_REVIEW_REQUIRED",
                "description": "Connector detail is not clearly visible.",
                "severity": "review_required",
                "confidence": 0.75,
                "region": None,
            }
        ],
        "confidence": 0.82,
        "limitations": ["Rear connector geometry is not visible."],
    }


def _chat_response(request: httpx.Request, content: dict) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json={"choices": [{"message": {"content": json.dumps(content)}}]},
    )


def _png(
    *,
    width: int = 64,
    height: int = 64,
    metadata: dict[str, str] | None = None,
) -> bytes:
    from PIL import Image, PngImagePlugin

    output = io.BytesIO()
    info = None
    if metadata:
        info = PngImagePlugin.PngInfo()
        for key, value in metadata.items():
            info.add_text(key, value)
    Image.new("RGB", (width, height), color=(200, 210, 220)).save(
        output,
        format="PNG",
        pnginfo=info,
    )
    return output.getvalue()
