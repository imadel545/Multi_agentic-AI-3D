from __future__ import annotations

from dataclasses import dataclass
from threading import Barrier

import pytest

from core.agents.specialist_router import (
    SpecialistRegistration,
    SpecialistRouter,
    SpecialistRoutingError,
)


@dataclass(frozen=True)
class Result:
    domain: str
    status: str = "passed"


def test_router_enforces_gate_then_parallel_fanout_with_stable_order() -> None:
    fanout_barrier = Barrier(2)

    def gate(context: str) -> Result:
        assert context == "context"
        return Result("gate")

    def specialist(domain: str):
        def run(context: str) -> Result:
            assert context == "context"
            fanout_barrier.wait(timeout=1)
            return Result(domain)

        return run

    router = SpecialistRouter(
        [
            SpecialistRegistration("gate", gate),
            SpecialistRegistration("rf", specialist("rf"), ("gate",)),
            SpecialistRegistration("structure", specialist("structure"), ("gate",)),
        ],
        max_workers=2,
    )

    results, waves = router.route(["gate", "rf", "structure"], "context")

    assert [result.domain for result in results] == ["gate", "rf", "structure"]
    assert waves == [["gate"], ["rf", "structure"]]


def test_router_rejects_wrong_domain_and_dependency_cycles() -> None:
    wrong_domain = SpecialistRouter(
        [SpecialistRegistration("rf", lambda _: Result("structure"))]
    )
    with pytest.raises(SpecialistRoutingError, match="returned domain"):
        wrong_domain.route(["rf"], "context")

    cycle = SpecialistRouter(
        [
            SpecialistRegistration("a", lambda _: Result("a"), ("b",)),
            SpecialistRegistration("b", lambda _: Result("b"), ("a",)),
        ]
    )
    with pytest.raises(SpecialistRoutingError, match="cycle"):
        cycle.route(["a", "b"], "context")


def test_router_fails_closed_before_dependents_after_failed_gate() -> None:
    called = False

    def dependent(_: str) -> Result:
        nonlocal called
        called = True
        return Result("dependent")

    router = SpecialistRouter(
        [
            SpecialistRegistration("gate", lambda _: Result("gate", "failed")),
            SpecialistRegistration("dependent", dependent, ("gate",)),
        ]
    )

    with pytest.raises(SpecialistRoutingError, match="decisions failed"):
        router.route(["gate", "dependent"], "context")
    assert called is False
