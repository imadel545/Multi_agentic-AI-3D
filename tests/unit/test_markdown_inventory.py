from pathlib import Path

ACTIVE_MARKDOWN_ALLOWLIST = {
    Path("AGENTS.md"),
    Path("README.md"),
    Path("docs/API_FRONTEND_CONTRACT.md"),
    Path("docs/ARCHITECTURE.md"),
    Path("docs/BACKEND_CAPABILITY_MATRIX.md"),
    Path("docs/FRONTEND_ACCEPTANCE_CRITERIA.md"),
    Path("docs/FRONTEND_PRODUCT_BLUEPRINT.md"),
    Path("docs/KNOWN_LIMITATIONS.md"),
    Path("docs/LANGGRAPH_WORKFLOW.md"),
    Path("docs/PROJECT_SOURCE_OF_TRUTH.md"),
    Path("docs/QA_STRATEGY.md"),
    Path("docs/RAG_STRATEGY.md"),
}


def test_active_root_and_docs_markdown_inventory_is_small_and_explicit() -> None:
    root = Path.cwd()
    active_markdown = [
        path.relative_to(root)
        for path in [*root.glob("*.md"), *root.glob("docs/*.md")]
        if _is_active_markdown(path.relative_to(root))
    ]

    assert set(active_markdown) == ACTIVE_MARKDOWN_ALLOWLIST
    assert len(active_markdown) <= 12


def _is_active_markdown(path: Path) -> bool:
    blocked_parts = {
        ".codex",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "data",
        "outputs",
    }
    return path.suffix == ".md" and not blocked_parts.intersection(path.parts)
