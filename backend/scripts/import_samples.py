from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ROOT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.import_snapshot import import_file  # noqa: E402


def main() -> int:
    samples_dir = REPO_DIR / "data" / "samples"
    for path in sorted(samples_dir.glob("snapshot_*.json")):
        print(f"Importing {path}")
        import_file(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
