from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from core.contracts.capabilities import (
    CapabilityDefinition,
    CapabilityInvocation,
    CapabilityObservation,
)


class CapabilityRegistryError(RuntimeError):
    """Fail-closed error raised before an unknown or forbidden tool can run."""


@dataclass(frozen=True)
class CapabilityRegistration:
    definition: CapabilityDefinition
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    executor: Callable[[BaseModel], BaseModel | dict[str, Any]]


class CapabilityRegistry:
    """Closed discovery and execution harness for deterministic capabilities."""

    def __init__(self, registrations: Iterable[CapabilityRegistration] = ()) -> None:
        items = list(registrations)
        identifiers = [item.definition.capability_id for item in items]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("capability IDs must be unique")
        self._registrations = {item.definition.capability_id: item for item in items}

    def discover(
        self,
        *,
        domain: str | None = None,
        required_tags: Iterable[str] = (),
        allowed_permissions: Iterable[str] | None = None,
    ) -> list[CapabilityDefinition]:
        tags = set(required_tags)
        permissions = set(allowed_permissions) if allowed_permissions is not None else None
        definitions = []
        for item in self._registrations.values():
            definition = item.definition
            if domain is not None and domain not in definition.compatible_domains:
                continue
            if not tags.issubset(definition.capability_tags):
                continue
            if permissions is not None and not set(definition.permissions).issubset(permissions):
                continue
            definitions.append(definition)
        return sorted(definitions, key=lambda item: item.capability_id)

    def definition(self, capability_id: str) -> CapabilityDefinition:
        registration = self._registrations.get(capability_id)
        if registration is None:
            raise CapabilityRegistryError(f"CAPABILITY_UNKNOWN:{capability_id}")
        return registration.definition

    def execute(self, invocation: CapabilityInvocation) -> CapabilityObservation:
        started = time.perf_counter()
        registration = self._registrations.get(invocation.capability_id)
        if registration is None:
            return self._error(
                invocation,
                started,
                "rejected",
                "CAPABILITY_UNKNOWN",
                "The requested capability is not registered.",
            )
        definition = registration.definition
        requested_permissions = set(invocation.requested_permissions)
        if not requested_permissions.issubset(definition.permissions):
            return self._error(
                invocation,
                started,
                "rejected",
                "CAPABILITY_PERMISSION_DENIED",
                "The invocation requests permissions not declared by the capability.",
            )
        encoded = json.dumps(invocation.arguments, separators=(",", ":")).encode("utf-8")
        if len(encoded) > definition.limits.max_input_bytes:
            return self._error(
                invocation,
                started,
                "rejected",
                "CAPABILITY_INPUT_TOO_LARGE",
                "The capability input exceeds its declared byte limit.",
            )
        try:
            validated_input = registration.input_model.model_validate(invocation.arguments)
        except ValidationError as exc:
            return self._error(
                invocation,
                started,
                "rejected",
                "CAPABILITY_ARGUMENTS_INVALID",
                str(exc)[:600],
            )

        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="capability")
        future = pool.submit(registration.executor, validated_input)
        try:
            raw_output = future.result(timeout=definition.timeout_s)
        except TimeoutError:
            future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            return self._error(
                invocation,
                started,
                "timed_out",
                "CAPABILITY_TIMEOUT",
                "The capability exceeded its declared timeout.",
            )
        except Exception as exc:
            pool.shutdown(wait=True, cancel_futures=True)
            return self._error(
                invocation,
                started,
                "failed",
                "CAPABILITY_EXECUTION_FAILED",
                f"{type(exc).__name__}: {exc}"[:600],
            )
        else:
            pool.shutdown(wait=True)
        try:
            validated_output = registration.output_model.model_validate(raw_output)
            output = validated_output.model_dump(mode="json")
        except ValidationError as exc:
            return self._error(
                invocation,
                started,
                "failed",
                "CAPABILITY_OUTPUT_INVALID",
                str(exc)[:600],
            )
        output_bytes = json.dumps(output, separators=(",", ":")).encode("utf-8")
        if len(output_bytes) > definition.limits.max_output_bytes:
            return self._error(
                invocation,
                started,
                "failed",
                "CAPABILITY_OUTPUT_TOO_LARGE",
                "The capability output exceeds its declared byte limit.",
            )
        return CapabilityObservation(
            capability_id=invocation.capability_id,
            correlation_id=invocation.correlation_id,
            status="completed",
            duration_ms=int((time.perf_counter() - started) * 1000),
            attempt=invocation.attempt,
            output=output,
            proof_refs=definition.generated_proofs,
        )

    @staticmethod
    def _error(
        invocation: CapabilityInvocation,
        started: float,
        status: str,
        code: str,
        message: str,
    ) -> CapabilityObservation:
        return CapabilityObservation(
            capability_id=invocation.capability_id,
            correlation_id=invocation.correlation_id,
            status=status,
            duration_ms=int((time.perf_counter() - started) * 1000),
            attempt=invocation.attempt,
            error_code=code,
            error_message=message,
        )
