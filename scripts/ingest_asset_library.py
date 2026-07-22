from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from core.services.asset_library import build_asset_library_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a local telecom CAD asset library.")
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--library-root",
        type=Path,
        default=Path("assets/library"),
    )
    parser.add_argument("--copy", action="store_true", help="Copy the source tree before indexing.")
    args = parser.parse_args()
    raw_dir = args.library_root / "raw" / "maj_des_blocs"
    if args.copy:
        raw_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(args.source, raw_dir, dirs_exist_ok=True, copy_function=shutil.copy2)
    elif not raw_dir.is_dir():
        raise SystemExit(f"raw library missing: {raw_dir}; rerun with --copy")
    summary = build_asset_library_catalog(raw_dir, args.library_root / "index")
    print(
        f"catalogued={summary['file_count']} unique={summary['unique_content_count']} "
        f"duplicates={summary['duplicate_file_count']} eligible=0"
    )


if __name__ == "__main__":
    main()
