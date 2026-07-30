import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.contracts.identifiers import require_workflow_id


@dataclass(frozen=True)
class CleanupResult:
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    freed_bytes: int = 0


class CleanupService:
    def __init__(self, outputs_dir: Path) -> None:
        self.outputs_dir = outputs_dir

    def cleanup_old_workflows(self, ttl_seconds: int, now: float | None = None) -> CleanupResult:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        if not self.outputs_dir.exists():
            return CleanupResult()

        current_time = time.time() if now is None else now
        removed: list[str] = []
        kept: list[str] = []
        skipped: list[str] = []
        freed_bytes = 0
        root = self.outputs_dir.resolve()

        for child in sorted(self.outputs_dir.iterdir()):
            if not _is_managed_workflow_dir(child):
                skipped.append(child.name)
                continue
            if not _inside_root(root, child):
                skipped.append(child.name)
                continue
            age_seconds = current_time - child.stat().st_mtime
            if age_seconds < ttl_seconds:
                kept.append(child.name)
                continue
            freed_bytes += _directory_size(child)
            shutil.rmtree(child)
            removed.append(child.name)

        return CleanupResult(
            removed=removed,
            kept=kept,
            skipped=skipped,
            freed_bytes=freed_bytes,
        )

    def delete_workflow(self, workflow_id: str) -> bool:
        require_workflow_id(workflow_id)
        path = self.outputs_dir / workflow_id
        root = self.outputs_dir.resolve()
        if not _is_managed_workflow_dir(path) or not _inside_root(root, path):
            return False
        shutil.rmtree(path)
        return True


def _is_managed_workflow_dir(path: Path) -> bool:
    try:
        require_workflow_id(path.name)
    except ValueError:
        return False
    return path.exists() and not path.is_symlink() and path.is_dir()


def _inside_root(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def _directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_symlink() or not child.is_file():
            continue
        total += child.stat().st_size
    return total
