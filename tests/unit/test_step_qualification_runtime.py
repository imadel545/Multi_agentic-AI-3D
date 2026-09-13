from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts import qualify_step_asset


def test_step_qualification_accepts_only_the_governed_blender_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        qualify_step_asset.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, "Blender 4.5.12 LTS\n", ""),
    )

    runtime = qualify_step_asset._probe_qualified_blender(
        Path("/Applications/Blender 4.5 LTS.app/Contents/MacOS/Blender"),
        Path("/tmp"),
    )

    assert runtime == {
        "version": "4.5.12 LTS",
        "version_tuple": [4, 5, 12],
        "background": True,
        "factory_startup": True,
        "binary_name": "Blender",
    }


def test_step_qualification_rejects_the_other_installed_blender(monkeypatch) -> None:
    monkeypatch.setattr(
        qualify_step_asset.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, "Blender 5.1.2\n", ""),
    )

    with pytest.raises(ValueError, match="requires Blender 4.5.12 LTS"):
        qualify_step_asset._probe_qualified_blender(Path("/usr/local/bin/blender"), Path("/tmp"))
