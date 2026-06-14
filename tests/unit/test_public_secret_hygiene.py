from pathlib import Path

PUBLIC_PATHS = [
    Path(".env.example"),
    Path("docs"),
    Path("tests"),
]

FORBIDDEN_SECRET_MARKERS = ("gs" + "k_", "nv" + "api-", "s" + "k-")


def test_public_files_do_not_contain_real_secret_markers() -> None:
    offenders: list[str] = []
    for root in PUBLIC_PATHS:
        paths = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in paths:
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in FORBIDDEN_SECRET_MARKERS):
                offenders.append(str(path))

    assert offenders == []
