import json
import time
from pathlib import Path

from core.contracts.events import WorkflowEvent


class EventLogService:
    def __init__(self, outputs_dir: Path) -> None:
        self.outputs_dir = outputs_dir

    def _events_path(self, workflow_id: str) -> Path:
        return self.outputs_dir / workflow_id / "workflow_events.jsonl"

    def append(self, event: WorkflowEvent) -> None:
        path = self._events_path(event.workflow_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")

    def list_events(self, workflow_id: str) -> list[WorkflowEvent]:
        path = self._events_path(workflow_id)
        if not path.exists():
            return []
        events = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(WorkflowEvent.model_validate_json(line))
                except Exception:
                    continue
        return events

    def emit(
        self,
        workflow_id: str,
        event_type: str,
        payload: dict | None = None,
    ) -> WorkflowEvent:
        event = WorkflowEvent(
            event_type=event_type,  # type: ignore[arg-type]
            workflow_id=workflow_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            payload=payload or {},
        )
        self.append(event)
        return event
