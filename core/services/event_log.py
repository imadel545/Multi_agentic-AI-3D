import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from weakref import WeakValueDictionary

from core.contracts.events import WorkflowEvent

logger = logging.getLogger(__name__)

_EVENT_LOG_LOCKS_GUARD = threading.Lock()
_EVENT_LOG_LOCKS: WeakValueDictionary[Path, threading.RLock] = WeakValueDictionary()
_EVENT_LOG_SEQUENCES: dict[Path, int] = {}
_TERMINAL_EVENT_TYPES = {
    "edit_patch_applied",
    "edit_patch_rejected",
    "workflow_completed",
    "workflow_failed",
}


@dataclass(frozen=True, slots=True)
class EventLogCorruption:
    line_number: int
    error_type: str


@dataclass(frozen=True, slots=True)
class EventLogDiagnostics:
    workflow_id: str
    total_lines: int = 0
    valid_events: int = 0
    returned_events: int = 0
    blank_lines: int = 0
    corrupted_lines: int = 0
    corruption_samples: tuple[EventLogCorruption, ...] = ()

    @property
    def healthy(self) -> bool:
        return self.corrupted_lines == 0


@dataclass(frozen=True, slots=True)
class EventLogReadResult:
    events: tuple[WorkflowEvent, ...]
    diagnostics: EventLogDiagnostics


class EventLogService:
    def __init__(
        self,
        outputs_dir: Path,
        *,
        fsync_every: int = 16,
        max_corruption_samples: int = 5,
    ) -> None:
        if fsync_every < 1:
            raise ValueError("fsync_every must be at least 1")
        if max_corruption_samples < 0:
            raise ValueError("max_corruption_samples cannot be negative")
        self.outputs_dir = outputs_dir
        self.fsync_every = fsync_every
        self.max_corruption_samples = max_corruption_samples
        self._append_counts: dict[Path, int] = {}

    def _events_path(self, workflow_id: str) -> Path:
        return self.outputs_dir / workflow_id / "workflow_events.jsonl"

    def append(self, event: WorkflowEvent) -> WorkflowEvent:
        path = self._events_path(event.workflow_id)
        with _event_log_lock(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            last_sequence = _EVENT_LOG_SEQUENCES.get(path)
            if last_sequence is None:
                last_sequence = _last_persisted_sequence(path)
            if event.sequence is None:
                event = event.model_copy(update={"sequence": last_sequence + 1})
            elif event.sequence <= last_sequence:
                raise ValueError("event sequence must be strictly monotonic")
            serialized = json.dumps(
                event.model_dump(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            with path.open("a", encoding="utf-8") as stream:
                stream.write(serialized + "\n")
                stream.flush()
                append_count = self._append_counts.get(path, 0) + 1
                self._append_counts[path] = append_count
                if self._should_fsync(event.event_type, append_count):
                    os.fsync(stream.fileno())
            _EVENT_LOG_SEQUENCES[path] = int(event.sequence)
        return event

    def read_events(
        self,
        workflow_id: str,
        *,
        offset: int = 0,
        limit: int | None = None,
        tail: int | None = None,
    ) -> EventLogReadResult:
        self._validate_read_window(offset=offset, limit=limit, tail=tail)
        path = self._events_path(workflow_id)
        selected: list[WorkflowEvent] | deque[WorkflowEvent]
        selected = deque(maxlen=tail) if tail is not None else []
        total_lines = 0
        valid_events = 0
        blank_lines = 0
        corrupted_lines = 0
        corruption_samples: list[EventLogCorruption] = []

        with _event_log_lock(path):
            if not path.exists():
                return EventLogReadResult(
                    events=(),
                    diagnostics=EventLogDiagnostics(workflow_id=workflow_id),
                )
            with path.open("rb") as stream:
                for line_number, raw_line in enumerate(stream, start=1):
                    total_lines += 1
                    line = raw_line.strip()
                    if not line:
                        blank_lines += 1
                        continue
                    try:
                        event = WorkflowEvent.model_validate_json(line)
                    except (UnicodeDecodeError, ValueError) as exc:
                        corrupted_lines += 1
                        if len(corruption_samples) < self.max_corruption_samples:
                            corruption_samples.append(
                                EventLogCorruption(
                                    line_number=line_number,
                                    error_type=type(exc).__name__,
                                )
                            )
                        continue

                    event_index = valid_events
                    if event.sequence is None:
                        event = event.model_copy(update={"sequence": event_index + 1})
                    valid_events += 1
                    if tail is not None:
                        selected.append(event)
                    elif event_index >= offset and (limit is None or len(selected) < limit):
                        selected.append(event)

        events = tuple(selected)
        diagnostics = EventLogDiagnostics(
            workflow_id=workflow_id,
            total_lines=total_lines,
            valid_events=valid_events,
            returned_events=len(events),
            blank_lines=blank_lines,
            corrupted_lines=corrupted_lines,
            corruption_samples=tuple(corruption_samples),
        )
        if corrupted_lines:
            logger.warning(
                "Workflow event log contains invalid records: workflow_id=%s "
                "corrupted_lines=%d total_lines=%d",
                workflow_id,
                corrupted_lines,
                total_lines,
            )
        return EventLogReadResult(events=events, diagnostics=diagnostics)

    def list_events(self, workflow_id: str) -> list[WorkflowEvent]:
        return list(self.read_events(workflow_id).events)

    def list_events_page(
        self,
        workflow_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> EventLogReadResult:
        return self.read_events(workflow_id, offset=offset, limit=limit)

    def tail_events(self, workflow_id: str, *, limit: int = 100) -> EventLogReadResult:
        return self.read_events(workflow_id, tail=limit)

    def diagnostics(self, workflow_id: str) -> EventLogDiagnostics:
        return self.read_events(workflow_id).diagnostics

    def forget_workflow(self, workflow_id: str) -> None:
        """Release process-local sequence/cache state after durable workflow deletion."""

        path = self._events_path(workflow_id).resolve(strict=False)
        with _EVENT_LOG_LOCKS_GUARD:
            _EVENT_LOG_SEQUENCES.pop(path, None)
        self._append_counts.pop(path, None)

    def emit(
        self,
        workflow_id: str,
        event_type: str,
        payload: dict | None = None,
    ) -> WorkflowEvent:
        event = WorkflowEvent(
            event_type=event_type,
            workflow_id=workflow_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            payload=payload or {},
        )
        return self.append(event)

    def _should_fsync(self, event_type: str, append_count: int) -> bool:
        return (
            append_count == 1
            or append_count % self.fsync_every == 0
            or event_type in _TERMINAL_EVENT_TYPES
        )

    @staticmethod
    def _validate_read_window(
        *,
        offset: int,
        limit: int | None,
        tail: int | None,
    ) -> None:
        if offset < 0:
            raise ValueError("offset cannot be negative")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        if tail is not None and tail < 1:
            raise ValueError("tail must be at least 1")
        if tail is not None and (offset != 0 or limit is not None):
            raise ValueError("tail cannot be combined with offset or limit")


def _event_log_lock(path: Path) -> threading.RLock:
    canonical_path = path.resolve(strict=False)
    with _EVENT_LOG_LOCKS_GUARD:
        return _EVENT_LOG_LOCKS.setdefault(canonical_path, threading.RLock())


def _last_persisted_sequence(path: Path) -> int:
    if not path.exists():
        return 0
    last_sequence = 0
    valid_events = 0
    with path.open("rb") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = WorkflowEvent.model_validate_json(line)
            except (UnicodeDecodeError, ValueError):
                continue
            valid_events += 1
            last_sequence = max(last_sequence, event.sequence or valid_events)
    return last_sequence
