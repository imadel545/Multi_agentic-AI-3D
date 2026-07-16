import re
from pathlib import Path

PUBLIC_PATHS = [
    Path(".env.example"),
    Path("docs"),
    Path("tests"),
]

SECRET_PATTERNS = (
    re.compile(r"\b" + "gs" + r"k_[A-Za-z0-9_-]{10,}"),
    re.compile(r"\b" + "nv" + r"api-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\b" + "s" + r"k-[A-Za-z0-9_-]{10,}"),
)


def test_public_files_do_not_contain_real_secret_markers() -> None:
    offenders: list[str] = []
    for root in PUBLIC_PATHS:
        paths = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in paths:
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                offenders.append(str(path))

    assert offenders == []
