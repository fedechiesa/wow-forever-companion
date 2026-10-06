from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.ingestion.adapters.file import FileAdapter  # noqa: E402
from app.ingestion.service import IngestionService, SnapshotImportInput  # noqa: E402


def import_file(path: Path) -> None:
    adapter_result = FileAdapter().load(path)
    result = IngestionService().import_snapshot(
        SnapshotImportInput(
            snapshot=adapter_result.snapshot,
            source_hash=adapter_result.source_hash,
            raw_reference=adapter_result.raw_reference,
        )
    )
    print(result.model_dump_json())


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/import_snapshot.py <snapshot.json>", file=sys.stderr)
        return 2

    import_file(Path(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
