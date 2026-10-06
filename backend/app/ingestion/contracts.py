from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class ItemQuality(StrEnum):
    POOR = "poor"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    ARTIFACT = "artifact"
    HEIRLOOM = "heirloom"
    UNKNOWN = "unknown"


def require_non_empty(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("value must not be empty")
    return stripped


class NormalizedSnapshotItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    external_item_id: str
    name: str
    quality: ItemQuality
    min_buyout: int = Field(strict=True, ge=0, le=2147483647)
    avg_buyout: int = Field(strict=True, ge=0, le=2147483647)
    max_buyout: int = Field(strict=True, ge=0, le=2147483647)
    quantity_total: int = Field(strict=True, ge=0, le=2147483647)
    auction_count: int = Field(strict=True, ge=0, le=2147483647)

    @field_validator("external_item_id", "name")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        return require_non_empty(value)

    @model_validator(mode="after")
    def validate_price_order(self) -> "NormalizedSnapshotItem":
        if not self.min_buyout <= self.avg_buyout <= self.max_buyout:
            raise ValueError("prices must satisfy min_buyout <= avg_buyout <= max_buyout")
        return self


class NormalizedSnapshot(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    realm: str
    region: str | None = None
    source_type: str
    source_version: str
    captured_at: AwareDatetime
    imported_at: AwareDatetime | None = None
    raw_reference: str | None = None
    items: list[NormalizedSnapshotItem] = Field(min_length=1)

    @field_validator("captured_at", "imported_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None

    @field_validator("realm", "source_type", "source_version")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        return require_non_empty(value)

    @field_validator("region", "raw_reference")
    @classmethod
    def validate_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_unique_external_item_ids(self) -> "NormalizedSnapshot":
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item in self.items:
            if item.external_item_id in seen:
                duplicates.add(item.external_item_id)
            seen.add(item.external_item_id)

        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicated external_item_id values: {duplicate_list}")

        return self


class ImportResult(BaseModel):
    status: Literal["completed", "duplicate", "failed"]
    snapshot_id: int | None
    items_seen: int = Field(ge=0)
    items_imported: int = Field(ge=0)
    message: str | None = None
