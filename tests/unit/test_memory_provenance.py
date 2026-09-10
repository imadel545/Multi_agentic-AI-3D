import sqlite3
from pathlib import Path

import pytest

from core.contracts.document_pack import (
    DocumentPackQACheck,
    DocumentPackQAReport,
    DocumentPackSummary,
    ProjectDesignSpec,
)
from core.contracts.memory import MemoryOrigin
from core.memory import MemoryService
from core.memory.provenance import MEMORY_TABLES
from tests.unit.test_memory_service import _memory_inputs, _real_generation


def _write(service: MemoryService, workflow_id: str):
    requirements, scene, report, _ = _memory_inputs(workflow_id)
    service.write_workflow_summary(
        workflow_id,
        requirements,
        scene,
        report,
        _real_generation(),
        Path("scene_spec.json"),
        Path("validation_report.json"),
    )
    return requirements


def _pack(service: MemoryService, pack_id: str):
    return service.write_document_pack_summary(
        spec=ProjectDesignSpec(pack_id=pack_id),
        summary=DocumentPackSummary(
            pack_id=pack_id,
            status="processed",
            document_count=0,
            high_priority_count=0,
            missing_blocking_count=1,
            conflict_count=0,
            can_generate_design=False,
        ),
        qa_report=DocumentPackQAReport(
            pack_id=pack_id,
            status="warning",
            score=0.5,
            checks=[
                DocumentPackQACheck(name="missing_height", passed=False, reason="Height needed")
            ],
        ),
        corrections=[],
        generated_workflow_id=None,
    )


@pytest.mark.parametrize("origin", list(MemoryOrigin))
def test_origin_is_persisted_on_every_record_and_controls_recall(tmp_path, origin):
    service = MemoryService(tmp_path / "memory.db", origin=origin, auto_reconcile=False)
    requirements = _write(service, "workflow")
    _pack(service, "pack")
    eligible = origin == MemoryOrigin.PRODUCT
    with sqlite3.connect(service.db_path) as conn:
        for table in MEMORY_TABLES:
            assert conn.execute(f"SELECT origin, recall_eligible FROM {table}").fetchall() == [
                (origin.value, int(eligible))
            ]
    recalled = service.recall(requirements)
    assert len(recalled.similar_workflows) == int(eligible)
    assert len(recalled.error_patterns) == int(eligible)
    documents, source_counts, _ = service._runtime_vector_documents()
    assert all(count == int(eligible) for count in source_counts.values())
    for collection in documents.values():
        for document in collection:
            assert document.payload["origin"] == "PRODUCT"
            assert document.payload["recall_eligible"] is True


def test_legacy_rows_are_preserved_unknown_and_ineligible_after_repeated_migration(tmp_path):
    path = tmp_path / "legacy.db"
    service = MemoryService(path, auto_reconcile=False)
    requirements = _write(service, "legacy")
    _pack(service, "legacy_pack")
    with sqlite3.connect(path) as conn:
        for table in MEMORY_TABLES:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN origin")
            conn.execute(f"ALTER TABLE {table} DROP COLUMN recall_eligible")
    for _ in range(2):
        service = MemoryService(path, auto_reconcile=False)
        with sqlite3.connect(path) as conn:
            for table in MEMORY_TABLES:
                assert conn.execute(f"SELECT origin, recall_eligible FROM {table}").fetchall() == [
                    ("UNKNOWN", 0)
                ]
        assert service.recall(requirements).memory_hits == 0
        assert all(not rows for rows in service._runtime_vector_documents()[0].values())


def test_test_record_cannot_replace_product_or_promote_itself(tmp_path):
    product = MemoryService(tmp_path / "memory.db", origin="PRODUCT", auto_reconcile=False)
    test = MemoryService(product.db_path, origin="TEST", auto_reconcile=False)
    _write(product, "product")
    _write(test, "test")
    _pack(product, "product_pack")
    for service, identity in ((test, "product"), (product, "test")):
        _write(service, identity)
        assert service.last_index_result.status == "skipped"
        assert service.last_index_result.errors == ["memory_origin_conflict"]
    assert _pack(test, "product_pack") == {
        "status": "skipped",
        "pack_id": "product_pack",
        "errors": ["memory_origin_conflict"],
    }
    documents, _, _ = product._runtime_vector_documents()
    assert documents["design_memory"][0].payload["representative_workflow_id"] == "product"
    assert documents["error_memory"][0].payload["occurrence_count"] == 1


def test_provenance_change_invalidates_projection_and_cannot_enable_test_rows(tmp_path):
    service = MemoryService(tmp_path / "memory.db", origin="TEST", auto_reconcile=False)
    requirements = _write(service, "test")
    before = service._vector_source_fingerprint()
    with sqlite3.connect(service.db_path) as conn:
        for table in MEMORY_TABLES:
            conn.execute(f"UPDATE {table} SET recall_eligible = 1")
    assert service._vector_source_fingerprint() != before
    assert service.recall(requirements).memory_hits == 0
    assert all(not rows for rows in service._runtime_vector_documents()[0].values())
