"""Auctionator evidence, independent of full Auction House snapshots."""
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator, field_validator
from app.ingestion.auctionator_keys import normalize_item_key

Ruleset = Literal["PvE", "PvP", "HC", "RP"]
Statistic = Literal["daily_minimum", "daily_highest_minimum", "daily_max_available", "last_minimum"]
BoundedInt = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
MAX_OBSERVATIONS = 200000


class PartialObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_key: str = Field(min_length=1, max_length=200)
    ruleset: Ruleset
    item_key: str = Field(min_length=1, max_length=200)
    external_item_id: str = Field(pattern=r"^[1-9][0-9]{0,9}$")
    key_kind: Literal["item", "gear_level", "gear_suffix", "pet"]
    statistic: Statistic
    value: BoundedInt
    scan_day: BoundedInt | None = None

    @model_validator(mode="after")
    def temporal_semantics(self):
        if normalize_item_key(self.item_key) != (self.item_key, self.external_item_id, self.key_kind):
            raise ValueError("item key, ID and kind must agree and be normalized")
        if self.market_key != self.market_key.strip() or any(ord(c) < 32 for c in self.market_key):
            raise ValueError("market key must be trimmed and contain no control characters")
        if self.market_key in ("PvE", "PvP", "HC", "RP") and self.ruleset != self.market_key:
            raise ValueError("literal market key must match its ruleset")
        if (self.statistic == "last_minimum") != (self.scan_day is None):
            raise ValueError("last_minimum is undated; daily statistics require scan_day")
        return self


class PartialBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["auctionator", "simulated"]
    source_id: str = Field(min_length=1, max_length=200)
    source_version: Literal["340"] = "340"
    database_version: Literal[8] = 8
    dataset: Literal["real", "simulated"]
    region: str = Field(min_length=1, max_length=100)
    # Provided externally, never inferred from import time or the host timezone.
    scan_day_zero: AwareDatetime | None = None
    observations: list[PartialObservation] = Field(min_length=1, max_length=MAX_OBSERVATIONS)

    @field_validator("source_id", "region")
    @classmethod
    def normalized_context(cls, value):
        if value != value.strip():
            raise ValueError("context must be trimmed")
        return value

    @field_validator("scan_day_zero")
    @classmethod
    def utc_epoch(cls, value):
        return value.astimezone(timezone.utc) if value else None

    @model_validator(mode="after")
    def validate_evidence(self):
        if (self.source_type == "simulated") != (self.dataset == "simulated"):
            raise ValueError("simulated and real evidence must remain separate")
        seen = set()
        markets = {}
        daily = {}
        for o in self.observations:
            identity = (o.market_key, o.item_key, o.scan_day, o.statistic)
            if identity in seen:
                raise ValueError("duplicate observation identity in batch")
            seen.add(identity)
            previous = markets.setdefault(o.market_key, o.ruleset)
            if previous != o.ruleset:
                raise ValueError("inconsistent market ruleset")
            if o.scan_day is not None:
                daily.setdefault((o.market_key, o.item_key, o.scan_day), {})[o.statistic] = o.value
        for values in daily.values():
            low, high = values.get("daily_minimum"), values.get("daily_highest_minimum")
            if low is not None and high is not None and low > high:
                raise ValueError("daily minimum exceeds daily highest minimum")
        return self


class PartialImportResult(BaseModel):
    import_id: int
    status: Literal["completed", "duplicate", "failed"]
    observations_seen: int
    observations_changed: int
    export_id: int | None = None
    evidence_status: Literal["created", "reused", "unavailable"] = "unavailable"
    native_facts_seen: int = 0
