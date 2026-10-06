from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.ingestion.adapters.base import AdapterResult
from app.ingestion.contracts import NormalizedSnapshot


class FileAdapter:
    source_type = "file_import"

    def load(self, source: Path) -> AdapterResult:
        path = Path(source)
        raw_bytes = path.read_bytes()
        payload: dict[str, Any] = json.loads(raw_bytes.decode("utf-8"))
        snapshot = NormalizedSnapshot.model_validate(payload)
        source_hash = hashlib.sha256(raw_bytes).hexdigest()
        return AdapterResult(
            snapshot=snapshot,
            source_hash=source_hash,
            raw_reference=str(path),
        )

    def load_payload(
        self,
        payload: dict[str, Any],
        *,
        raw_reference: str | None = None,
    ) -> AdapterResult:
        normalized_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        snapshot = NormalizedSnapshot.model_validate(payload)
        source_hash = hashlib.sha256(normalized_bytes).hexdigest()
        return AdapterResult(
            snapshot=snapshot,
            source_hash=source_hash,
            raw_reference=raw_reference,
        )
