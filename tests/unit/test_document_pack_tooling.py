from core.document_pack import tooling


def test_dwgread_alone_is_not_reported_as_a_converter(monkeypatch) -> None:
    available = {"dwgread": "/opt/homebrew/bin/dwgread"}
    monkeypatch.setattr(tooling.shutil, "which", lambda name: available.get(name))
    monkeypatch.setattr(tooling, "_module_available", lambda _name: False)

    capability = tooling.detect_document_pack_capabilities().dwg_conversion

    assert capability.status == "unsupported_without_converter"
    assert capability.command is None


def test_detected_dwg2dxf_is_import_only_until_execution_is_wired(monkeypatch) -> None:
    available = {"dwg2dxf": "/opt/homebrew/bin/dwg2dxf"}
    monkeypatch.setattr(tooling.shutil, "which", lambda name: available.get(name))
    monkeypatch.setattr(tooling, "_module_available", lambda _name: False)

    capability = tooling.detect_document_pack_capabilities().dwg_conversion

    assert capability.status == "installed_import_only"
    assert capability.command == "/opt/homebrew/bin/dwg2dxf"
    assert capability.warnings == ["dwg_converter_detected_but_execution_disabled"]
