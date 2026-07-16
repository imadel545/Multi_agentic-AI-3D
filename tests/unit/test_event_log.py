import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.services.event_log import EventLogService


def test_event_log_serializes_concurrent_appends_without_corruption(tmp_path: Path) -> None:
    services = [EventLogService(tmp_path, fsync_every=25) for _ in range(4)]
    workflow_id = "wf_concurrent_events"

    def emit(index: int) -> None:
        services[index % len(services)].emit(
            workflow_id,
            "node_completed",
            {"index": index},
        )

    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(emit, range(400)))

    result = services[0].read_events(workflow_id)
    assert result.diagnostics.healthy is True
    assert result.diagnostics.total_lines == 400
    assert result.diagnostics.valid_events == 400
    assert {event.payload["index"] for event in result.events} == set(range(400))
    assert sorted(event.sequence for event in result.events) == list(range(1, 401))


def test_event_log_reports_corruption_without_breaking_legacy_list(tmp_path: Path, caplog) -> None:
    service = EventLogService(tmp_path, max_corruption_samples=1)
    workflow_id = "wf_corrupt_events"
    service.emit(workflow_id, "design_created", {"step": 1})
    path = tmp_path / workflow_id / "workflow_events.jsonl"
    with path.open("ab") as stream:
        stream.write(b"not-json\n")
        stream.write(b"\xff\xfe\n")
        stream.write(b"\n")
    service.emit(workflow_id, "workflow_failed", {"step": 2})

    events = service.list_events(workflow_id)
    diagnostics = service.diagnostics(workflow_id)

    assert [event.event_type for event in events] == ["design_created", "workflow_failed"]
    assert diagnostics.total_lines == 5
    assert diagnostics.valid_events == 2
    assert diagnostics.corrupted_lines == 2
    assert diagnostics.blank_lines == 1
    assert len(diagnostics.corruption_samples) == 1
    assert diagnostics.corruption_samples[0].line_number == 2
    assert "corrupted_lines=2" in caplog.text


def test_event_log_page_and_tail_keep_diagnostics(tmp_path: Path) -> None:
    service = EventLogService(tmp_path)
    workflow_id = "wf_event_windows"
    for index in range(8):
        service.emit(workflow_id, "node_completed", {"index": index})

    page = service.list_events_page(workflow_id, offset=2, limit=3)
    tail = service.tail_events(workflow_id, limit=2)

    assert [event.payload["index"] for event in page.events] == [2, 3, 4]
    assert page.diagnostics.valid_events == 8
    assert page.diagnostics.returned_events == 3
    assert [event.payload["index"] for event in tail.events] == [6, 7]
    assert tail.diagnostics.returned_events == 2


def test_event_log_fsyncs_first_periodic_and_terminal_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fsync_calls: list[int] = []
    monkeypatch.setattr(os, "fsync", fsync_calls.append)
    service = EventLogService(tmp_path, fsync_every=3)

    service.emit("wf_fsync", "design_created")
    service.emit("wf_fsync", "node_started")
    service.emit("wf_fsync", "node_completed")
    service.emit("wf_fsync", "workflow_completed")

    assert len(fsync_calls) == 3
    path = tmp_path / "wf_fsync" / "workflow_events.jsonl"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 4
    serialized_events = path.read_text(encoding="utf-8").splitlines()
    assert all(json.loads(line)["workflow_id"] == "wf_fsync" for line in serialized_events)
    assert [json.loads(line)["sequence"] for line in serialized_events] == [1, 2, 3, 4]


def test_event_log_assigns_sequences_after_legacy_events(tmp_path: Path) -> None:
    workflow_id = "wf_legacy_sequence"
    path = tmp_path / workflow_id / "workflow_events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "event_id": "evt_legacy",
                "event_type": "design_created",
                "workflow_id": workflow_id,
                "timestamp": "2026-07-15T10:00:00Z",
                "payload": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    service = EventLogService(tmp_path)

    created = service.emit(workflow_id, "node_started")
    events = service.list_events(workflow_id)

    assert created.sequence == 2
    assert [event.sequence for event in events] == [1, 2]
