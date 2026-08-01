from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Protocol


class DomainResult(Protocol):
    domain: str
    status: str


@dataclass(frozen=True)
class SpecialistRegistration[ContextT, ResultT: DomainResult]:
    domain: str
    handler: Callable[[ContextT], ResultT]
    depends_on: tuple[str, ...] = ()


class SpecialistRoutingError(RuntimeError):
    """The deterministic specialist graph is invalid or failed closed."""


class SpecialistRouter[ContextT, ResultT: DomainResult]:
    """Run a small typed specialist DAG with bounded parallel fan-out.

    Routing and dependency enforcement remain deterministic. A handler may use a
    bounded model internally, but the model cannot add domains or bypass gates.
    """

    def __init__(
        self,
        registrations: Iterable[SpecialistRegistration[ContextT, ResultT]],
        *,
        max_workers: int = 4,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        items = list(registrations)
        domains = [item.domain for item in items]
        if len(domains) != len(set(domains)):
            raise ValueError("specialist domains must be unique")
        self._registrations = {item.domain: item for item in items}
        self._max_workers = max_workers

    def route(
        self,
        required_domains: list[str],
        context: ContextT,
    ) -> tuple[list[ResultT], list[list[str]]]:
        if len(required_domains) != len(set(required_domains)):
            raise SpecialistRoutingError("required specialist domains must be unique")
        required = set(required_domains)
        unknown = required - set(self._registrations)
        if unknown:
            raise SpecialistRoutingError(
                f"specialist registry is missing domains: {sorted(unknown)}"
            )
        for domain in required:
            missing_dependencies = set(self._registrations[domain].depends_on) - required
            if missing_dependencies:
                raise SpecialistRoutingError(
                    f"specialist {domain!r} requires unrouted dependencies: "
                    f"{sorted(missing_dependencies)}"
                )

        pending = set(required)
        completed: dict[str, ResultT] = {}
        waves: list[list[str]] = []
        while pending:
            ready = sorted(
                domain
                for domain in pending
                if set(self._registrations[domain].depends_on) <= set(completed)
            )
            if not ready:
                raise SpecialistRoutingError(
                    f"specialist dependency cycle detected: {sorted(pending)}"
                )
            wave_results = self._execute_wave(ready, context)
            failed = sorted(
                domain for domain, result in wave_results.items() if result.status == "failed"
            )
            if failed:
                raise SpecialistRoutingError(f"required specialist decisions failed: {failed}")
            completed.update(wave_results)
            pending.difference_update(ready)
            waves.append(ready)

        return [completed[domain] for domain in required_domains], waves

    def dependencies_for(self, domain: str) -> tuple[str, ...]:
        return self._registrations[domain].depends_on

    def _execute_wave(self, domains: list[str], context: ContextT) -> dict[str, ResultT]:
        results: dict[str, ResultT] = {}
        with ThreadPoolExecutor(
            max_workers=min(self._max_workers, len(domains)),
            thread_name_prefix="telecom-specialist",
        ) as executor:
            futures = {
                executor.submit(self._registrations[domain].handler, context): domain
                for domain in domains
            }
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    raise SpecialistRoutingError(
                        f"specialist {domain!r} raised {type(exc).__name__}"
                    ) from exc
                if result.domain != domain:
                    raise SpecialistRoutingError(
                        f"specialist route {domain!r} returned domain {result.domain!r}"
                    )
                results[domain] = result
        return results
