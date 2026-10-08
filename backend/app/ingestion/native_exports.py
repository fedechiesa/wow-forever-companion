"""Native price fields and their explicit GetPriceHistory projection.

This is decoded evidence, not the Lua bytes or a chronological scan snapshot.
"""
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ingestion.auctionator_keys import normalize_item_key
from app.ingestion.partial_contracts import MAX_OBSERVATIONS, PartialObservation, Ruleset

NativeField = Literal["l", "h", "a", "m"]
FIELD_STATISTIC = {"l": "daily_minimum", "h": "daily_highest_minimum",
                   "a": "daily_max_available", "m": "last_minimum"}


class NativeFact(PartialObservation):
    native_field: NativeField
    original_item_key: str = Field(min_length=1, max_length=200)
    original_day_key: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def native_identity(self):
        if FIELD_STATISTIC[self.native_field] != self.statistic:
            raise ValueError("native field and statistic disagree")
        if normalize_item_key(self.original_item_key)[0] != self.item_key:
            raise ValueError("original item key disagrees with normalized key")
        if self.scan_day is None:
            if self.original_day_key is not None:
                raise ValueError("m has no original day key")
        elif (self.original_day_key is None or not self.original_day_key.isascii()
              or not self.original_day_key.isdigit() or int(self.original_day_key) != self.scan_day):
            raise ValueError("original day key disagrees with scan day")
        return self

    def observation(self, **updates):
        fields = self.model_dump(include=set(PartialObservation.model_fields))
        fields.update(updates)
        return PartialObservation.model_validate(fields)


class NativeItemShape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_item_key: str = Field(min_length=1, max_length=200)
    item_key: str = Field(min_length=1, max_length=200)
    external_item_id: str
    key_kind: Literal["item", "gear_level", "gear_suffix", "pet"]
    fields_present: list[NativeField] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def identity(self):
        identity = normalize_item_key(self.original_item_key)
        if identity != (self.item_key, self.external_item_id, self.key_kind):
            raise ValueError("native item identity mismatch")
        if len(set(self.fields_present)) != len(self.fields_present) or not {"l", "h"} <= set(self.fields_present):
            raise ValueError("native shape requires unique l/h fields")
        return self


class NativeMarketShape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_key: str = Field(min_length=1, max_length=200)
    ruleset: Ruleset
    realm_version: Literal[2] | None = None
    items: list[NativeItemShape] = Field(max_length=MAX_OBSERVATIONS)

    @model_validator(mode="after")
    def identity(self):
        if self.market_key != self.market_key.strip() or any(ord(c) < 32 for c in self.market_key):
            raise ValueError("market key must be trimmed and contain no control characters")
        if self.market_key in ("PvE", "PvP", "HC", "RP") and self.ruleset != self.market_key:
            raise ValueError("literal market key must match its ruleset")
        keys = [i.item_key for i in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("colliding native item keys after normalization")
        return self


class NativeExportEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_version: Literal[1] = 1
    markets: list[NativeMarketShape] = Field(max_length=MAX_OBSERVATIONS)
    facts: list[NativeFact] = Field(min_length=1, max_length=MAX_OBSERVATIONS)
    input_format: Literal["lua_tables", "libcbor", "mixed"]
    decoder_version: Literal["auctionator340-v1"] = "auctionator340-v1"

    @model_validator(mode="after")
    def coherent(self):
        markets = {m.market_key: m for m in self.markets}
        if len(markets) != len(self.markets):
            raise ValueError("duplicate native market")
        if len(markets) + sum(len(m.items) for m in self.markets) > MAX_OBSERVATIONS:
            raise ValueError("native structure construction limit exceeded")
        items = {(m.market_key, i.item_key): i for m in self.markets for i in m.items}
        days, seen, populated = {}, set(), set()
        for f in self.facts:
            item = items.get((f.market_key, f.item_key))
            if item is None or markets[f.market_key].ruleset != f.ruleset:
                raise ValueError("native fact outside declared market/item")
            if (f.original_item_key, f.external_item_id, f.key_kind) != (item.original_item_key, item.external_item_id, item.key_kind):
                raise ValueError("native fact identity mismatch")
            if f.native_field not in item.fields_present:
                raise ValueError("native fact outside fields present")
            identity = (f.market_key, f.item_key, f.scan_day, f.native_field)
            if identity in seen:
                raise ValueError("duplicate native fact")
            seen.add(identity)
            populated.add((f.market_key, f.item_key, f.native_field))
            if f.scan_day is not None:
                days.setdefault(identity[:3], {})[f.native_field] = f
        for values in days.values():
            h, l = values.get("h"), values.get("l")
            if h is None:
                raise ValueError("orphan native historical day")
            if any(f.original_day_key != h.original_day_key for f in values.values()):
                raise ValueError("native day aliases disagree")
            if l is not None and l.value > h.value:
                raise ValueError("native l exceeds h")
        for identity, item in items.items():
            if ("m" in item.fields_present) != ((*identity, "m") in populated):
                raise ValueError("m presence disagrees with native fact")
        return self

    def projected_observations(self):
        lows = {(f.market_key, f.item_key, f.scan_day): f for f in self.facts if f.native_field == "l"}
        result = []
        for f in self.facts:
            if f.native_field == "l":
                continue
            if f.native_field == "h":
                low = lows.get((f.market_key, f.item_key, f.scan_day), f)
                if len(result) + 2 > MAX_OBSERVATIONS:
                    raise ValueError("projection construction limit exceeded")
                result.append(low.observation(statistic="daily_minimum"))
            elif len(result) + 1 > MAX_OBSERVATIONS:
                raise ValueError("projection construction limit exceeded")
            result.append(f.observation())
        return result

    def manifest(self):
        markets = []
        for market in sorted(self.markets, key=lambda m: m.market_key):
            data = market.model_dump(mode="json")
            data["items"] = sorted(data["items"], key=lambda i: i["item_key"])
            for item in data["items"]:
                item["fields_present"] = sorted(item["fields_present"])
            markets.append(data)
        return {"version": 1, "markets": markets}

    def state_hash(self, batch):
        payload = batch.model_dump(mode="json", exclude={"observations"})
        payload.update(canonical_version=self.canonical_version, structure=self.manifest(),
                       facts=sorted((f.model_dump(mode="json") for f in self.facts), key=lambda f: (
                           f["market_key"], f["item_key"], -1 if f["scan_day"] is None else f["scan_day"], f["native_field"])))
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
