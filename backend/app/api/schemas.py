from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ImportSnapshotResponse(BaseModel):
    status: str
    snapshot_id: int | None
    items_seen: int
    items_imported: int
    message: str | None = None


class ItemSummaryResponse(BaseModel):
    id: int
    external_item_id: str
    name: str
    quality: str


class ItemDetailResponse(ItemSummaryResponse):
    created_at: datetime
    updated_at: datetime


class ItemHistoryPointResponse(BaseModel):
    snapshot_id: int
    realm_id: int
    realm: str
    region: str | None
    captured_at: datetime
    min_buyout: int
    avg_buyout: int
    max_buyout: int
    quantity_total: int
    auction_count: int


class SnapshotSummaryResponse(BaseModel):
    id: int
    realm_id: int
    realm: str
    region: str | None
    source_type: str
    source_version: str
    captured_at: datetime
    imported_at: datetime
    items_count: int


class ImportRunResponse(BaseModel):
    id: int
    source_type: str
    source_version: str | None
    raw_reference: str | None
    status: str
    snapshot_id: int | None
    items_seen: int
    items_imported: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
