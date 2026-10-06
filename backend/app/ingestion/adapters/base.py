from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.ingestion.contracts import NormalizedSnapshot


@dataclass(frozen=True)
class AdapterResult:
    snapshot: NormalizedSnapshot
    source_hash: str
    raw_reference: str | None = None


class SnapshotAdapter(Protocol):
    source_type: str

    def load(self, source: Path) -> AdapterResult:
        ...
