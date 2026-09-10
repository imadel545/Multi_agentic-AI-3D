"""Compile a selected catalog asset without inventing geometry or adaptation."""

import hashlib
import json
from typing import Literal

from apps.blender_worker.exact_asset import validate_exact_program
from core.contracts.assets import AssetManifest
from core.contracts.capabilities import (
    CapabilityCost,
    CapabilityDefinition,
    CapabilityInvocation,
    CapabilityObservation,
)
from core.contracts.cognitive_design import (
    CognitiveDesignPlan,
    ComponentAssetDecision,
    ComponentNode,
)
from core.contracts.common import StrictModel
from core.contracts.geometry_program import (
    GeometryExactAssetNode,
    GeometryProgram,
    GeometryProgramVector3,
)
from core.services.asset_registry import AssetRegistry
from core.services.capability_registry import CapabilityRegistration, CapabilityRegistry


class ExactAssetAdmission(StrictModel):
    program_id: str
    source_hashes_verified: Literal[True]
    blender_executed: Literal[False] = False
    sources: list[GeometryExactAssetNode]


def observe_asset_admission(
    registry: AssetRegistry, workflow_id: str, program: GeometryProgram
) -> CapabilityObservation:
    """Execute catalog/file validation; this does not claim Blender has run."""

    def validate(value: GeometryProgram) -> ExactAssetAdmission:
        records = validate_exact_program(
            value.model_dump(mode="json"), registry.manifests_dir.resolve().parent.parent
        )
        if len(records) != 1:
            raise ValueError("EXACT_ASSET_ADMISSION_REQUIRES_ONE_SOURCE")
        return ExactAssetAdmission(
            program_id=value.program_id,
            source_hashes_verified=True,
            sources=value.nodes,
        )

    capability_id = "catalog.validate_exact_source@1.0.0"
    admission_registry = CapabilityRegistry(
        [
            CapabilityRegistration(
                definition=CapabilityDefinition(
                    capability_id=capability_id,
                    description=(
                        "Validate catalog qualification, permissions and source hashes."
                    ),
                    input_schema=GeometryProgram.model_json_schema(),
                    output_schema=ExactAssetAdmission.model_json_schema(),
                    compatible_domains=["generic"],
                    cost=CapabilityCost(
                        class_name="low", estimated_seconds=0.1, estimated_memory_mb=64
                    ),
                    permissions=["read_catalog"],
                    timeout_s=10,
                    version="1.0.0",
                    generated_proofs=["exact_source_admission"],
                ),
                input_model=GeometryProgram,
                output_model=ExactAssetAdmission,
                executor=validate,
            )
        ]
    )
    return admission_registry.execute(
        CapabilityInvocation(
            capability_id=capability_id,
            arguments=program.model_dump(mode="json"),
            requested_permissions=["read_catalog"],
            correlation_id=f"{workflow_id}:reuse:{program.program_id}"[:120],
        )
    )


def compile_asset_reuse(
    registry: AssetRegistry | None,
    plan: CognitiveDesignPlan,
    component: ComponentNode,
    decision: ComponentAssetDecision,
) -> GeometryProgram:
    if registry is None:
        raise ValueError("COGNITIVE_REUSE_REGISTRY_UNAVAILABLE")
    if component.quantity != 1 or len(decision.selected_candidate_ids) != 1:
        raise ValueError("COGNITIVE_REUSE_REQUIRES_SINGLE_COMPONENT")
    if decision.placement is None:
        raise ValueError("COGNITIVE_REUSE_REQUIRES_EXPLICIT_PLACEMENT")
    if decision.selected_parameter_values:
        raise ValueError("COGNITIVE_REUSE_DOES_NOT_ADAPT_PARAMETERS")
    if component.parent_component_id or any(
        relation.required
        and component.component_id in {relation.source_component_id, relation.target_component_id}
        for relation in plan.component_graph.relationships
    ):
        raise ValueError("COGNITIVE_REUSE_RELATION_NOT_EXECUTABLE")
    asset_id = decision.selected_candidate_ids[0]
    if asset_id != registry.get(asset_id).asset_id:
        raise ValueError("COGNITIVE_REUSE_ASSET_ID_MISMATCH")
    path = registry.manifests_dir / f"{asset_id}.json"
    raw = path.read_bytes()
    manifest = AssetManifest.model_validate(json.loads(raw))
    if (
        not manifest.cognitive_reuse_enabled
        or not manifest.is_generation_eligible
        or not manifest.allows_generation_mode("imported_glb_exact")
    ):
        raise ValueError("COGNITIVE_REUSE_NOT_AUTHORIZED")
    if component.semantic_role not in manifest.compatibility_rules.compatible_roles:
        raise ValueError("COGNITIVE_REUSE_ROLE_NOT_AUTHORIZED")
    dimensions = manifest.dimensions_m
    if dimensions is None:
        raise ValueError("COGNITIVE_REUSE_DIMENSIONS_MISSING")
    program = GeometryProgram(
        schema_version="2.0.0",
        program_id=(
            f"reuse.{component.component_id}"
            if len(component.component_id) <= 90
            else f"reuse.{hashlib.sha256(component.component_id.encode()).hexdigest()}"
        ),
        semantic_role=component.semantic_role,
        requested_quantity=1,
        authorship="deterministic_generated",
        generator_provider="qualified_asset_compiler",
        generator_model="catalog_exact_reuse",
        structured_output_mode="strict_json_schema",
        source_prompt_sha256=plan.design_intent.source_prompt_sha256,
        source_description=(
            component.description
            if len(component.description) >= 8
            else f"{component.semantic_role}: {component.description}"
        ),
        source_description_origin="user_requirement",
        maximum_dimensions_m=component.target_dimensions_m,
        nodes=[
            GeometryExactAssetNode(
                node_id="catalog_asset",
                semantic_role=component.semantic_role,
                asset_id=asset_id,
                manifest_file_name=path.name,
                manifest_sha256=hashlib.sha256(raw).hexdigest(),
                asset_file=manifest.file,
                asset_sha256=manifest.qualification.verified_file_sha256,
                source_dimensions_m=GeometryProgramVector3(
                    x=dimensions.width, y=dimensions.depth, z=dimensions.height
                ),
                transform=decision.placement,
            )
        ],
        limitations=list(
            dict.fromkeys(
                [
                    *manifest.qualification.limitations,
                    "Exact reuse refers to the qualified source file, "
                    "not manufacturer or engineering certification.",
                ]
            )
        ),
    )
    validate_exact_program(
        program.model_dump(mode="json"), registry.manifests_dir.resolve().parent.parent
    )
    return program
