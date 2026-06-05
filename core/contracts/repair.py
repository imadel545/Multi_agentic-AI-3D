from pydantic import Field

from core.contracts.common import StrictModel


class RepairEvent(StrictModel):
    attempt: int = Field(ge=1)
    handler: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    warning_code: str = Field(min_length=1)
    success: bool


class RepairReport(StrictModel):
    status: str = Field(min_length=1)
    events: list[RepairEvent] = Field(default_factory=list)

    @property
    def repaired(self) -> bool:
        return any(event.success for event in self.events)
