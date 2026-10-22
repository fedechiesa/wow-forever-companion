"""Local evidence identities, independent of persistence/import context."""
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ingestion.adapters.auctionator import DecodedAuctionator
from app.ingestion.partial_contracts import Ruleset

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[int, Field(strict=True, ge=0)]
OriginId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]
CANONICAL_VERSION = "auctionator-native-market-v1"
WARNINGS = (
    "copy_time_is_not_scan_time", "native_buckets_are_not_civil_dates",
    "market_keys_do_not_confirm_full_realm_identity", "original_contains_private_savedvariables",
)
PENDING = ("region", "faction", "full_realm_identity", "capture_client_build",
           "capture_addon_version", "codec_producer", "native_scan_timestamp", "dataset", "capture_phase")


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Origin(Contract):
    kind: Literal["auctionator_savedvariables"] = "auctionator_savedvariables"
    origin_id: OriginId | None = None
    source_path_stored: Literal[False] = False


class Market(Contract):
    market_key: str = Field(min_length=1, max_length=200)
    ruleset: Ruleset
    state_sha256: Hash
    realm_database_version: Literal[2] | None
    item_count: Count
    native_fact_count: Count
    projected_statistic_count: Count
    bucket_count: Count
    first_bucket: Count | None
    last_bucket: Count | None


class Comparison(Contract):
    status: Literal["first", "equivalent", "changed"]
    equivalent_capture_id: Hash | None = None
    new_market_states: list[Hash]


class CaptureMetadata(Contract):
    schema_version: Literal[1] = 1
    capture_id: Hash
    source_sha256: Hash
    source_bytes: Count
    market_sha256: Hash
    market_hash_contract: Literal["auctionator-native-market-v1"] = CANONICAL_VERSION
    captured_at: AwareDatetime
    native_scan_timestamp: None = None
    origin: Origin
    validation_status: Literal["valid"] = "valid"
    database_version: Literal[8] = 8
    selected_source_version: Literal["340", "341"] | None
    selected_serialized_codec: Literal["cbor-definite"] | None
    input_format: Literal["lua_tables", "cbor_definite", "mixed"]
    simulated_marker: bool
    markets: list[Market]
    item_count: Count
    native_fact_count: Count
    projected_statistic_count: Count
    warnings: list[str]
    pending_metadata: list[str]

    @field_validator("captured_at")
    @classmethod
    def utc(cls, value):
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def identity(self):
        if self.capture_id != self.source_sha256:
            raise ValueError("capture identity must equal original byte hash")
        return self


class CaptureResult(Contract):
    status: Literal["archived", "duplicate"]
    metadata: CaptureMetadata
    comparison: Comparison


def describe(decoded: DecodedAuctionator, *, source_bytes: int, captured_at: datetime,
             origin: Origin, source_version, serialized_codec) -> CaptureMetadata:
    """Hash canonical *native evidence*, including empty shapes and l/h/a/m presence.

    Preserve original key spellings. Exclude receipt/import context, codec, Lua
    ordering/whitespace and all variables outside AUCTIONATOR_PRICE_DATABASE.
    This deliberately differs from the existing contextual export state hash.
    """
    structure = decoded.native.manifest()
    facts = sorted((fact.model_dump(mode="json") for fact in decoded.native.facts), key=lambda f: (
        f["market_key"], f["item_key"], -1 if f["scan_day"] is None else f["scan_day"], f["native_field"]))

    def payload(markets, selected_facts):
        return {"contract": CANONICAL_VERSION, "database_version": 8,
                "structure": {"version": 1, "markets": markets}, "facts": selected_facts}

    grouped_facts, observation_counts = defaultdict(list), defaultdict(int)
    for fact in facts:
        grouped_facts[fact["market_key"]].append(fact)
    for observation in decoded.observations:
        observation_counts[observation.market_key] += 1
    markets = []
    for shape in structure["markets"]:
        key = shape["market_key"]
        selected = grouped_facts[key]
        buckets = {f["scan_day"] for f in selected if f["scan_day"] is not None}
        markets.append(Market(
            market_key=key, ruleset=shape["ruleset"],
            state_sha256=sha256(canonical_json(payload([shape], selected))).hexdigest(),
            realm_database_version=shape["realm_version"], item_count=len(shape["items"]),
            native_fact_count=len(selected), projected_statistic_count=observation_counts[key],
            bucket_count=len(buckets), first_bucket=min(buckets) if buckets else None,
            last_bucket=max(buckets) if buckets else None,
        ))
    return CaptureMetadata(
        capture_id=decoded.source_hash, source_sha256=decoded.source_hash, source_bytes=source_bytes,
        market_sha256=sha256(canonical_json(payload(structure["markets"], facts))).hexdigest(),
        captured_at=captured_at, origin=origin, selected_source_version=source_version,
        selected_serialized_codec=serialized_codec, input_format=decoded.native.input_format,
        simulated_marker=decoded.simulated_marker, markets=markets,
        item_count=sum(m.item_count for m in markets), native_fact_count=len(facts),
        projected_statistic_count=len(decoded.observations),
        warnings=list(WARNINGS), pending_metadata=list(PENDING),
    )
