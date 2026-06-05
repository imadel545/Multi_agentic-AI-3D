import os
import time
from pathlib import Path

import pytest

from core.services.cleanup_service import CleanupService


def test_cleanup_removes_old_outputs(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    old_workflow = outputs / "wf_aaaaaaaaaaaa"
    old_workflow.mkdir(parents=True)
    (old_workflow / "artifact.txt").write_text("old", encoding="utf-8")
    old_time = time.time() - 7200
    os.utime(old_workflow, (old_time, old_time))

    result = CleanupService(outputs).cleanup_old_workflows(ttl_seconds=3600)

    assert result.removed == ["wf_aaaaaaaaaaaa"]
    assert result.freed_bytes >= 3
    assert not old_workflow.exists()


def test_cleanup_keeps_recent_outputs(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    recent_workflow = outputs / "wf_bbbbbbbbbbbb"
    recent_workflow.mkdir(parents=True)
    (recent_workflow / "artifact.txt").write_text("recent", encoding="utf-8")

    result = CleanupService(outputs).cleanup_old_workflows(ttl_seconds=3600)

    assert result.kept == ["wf_bbbbbbbbbbbb"]
    assert recent_workflow.exists()


def test_cleanup_never_deletes_outside_outputs_dir(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    outside = tmp_path / "wf_cccccccccccc"
    outside.mkdir()
    (outside / "artifact.txt").write_text("outside", encoding="utf-8")
    symlink = outputs / "wf_cccccccccccc"
    symlink.symlink_to(outside, target_is_directory=True)

    result = CleanupService(outputs).cleanup_old_workflows(ttl_seconds=0)

    assert "wf_cccccccccccc" in result.skipped
    assert outside.exists()
    assert symlink.exists()
    with pytest.raises(ValueError, match="workflow_id"):
        CleanupService(outputs).delete_workflow("../wf_cccccccccccc")
