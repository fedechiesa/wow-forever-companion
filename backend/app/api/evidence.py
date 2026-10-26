"""Bounded, public, read-only v2 evidence. Never expose private lineage JSON."""
from typing import Annotated, Literal
import re

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
import psycopg

from app.db.connection import connect
from app.ingestion.local_readers import EvidenceSchemaUnavailable, LocalEvidenceReader
from app.ingestion.auctionator_keys import normalize_item_key

Dataset = Literal["simulated", "stress_test", "launch"]
Id = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Value = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
Selector = Annotated[int, Path(gt=0, le=9223372036854775807)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=2147483647)]


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceMarket(PublicModel):
    id: Id
    dataset: Dataset
    economy: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=100)
    native_label: str = Field(min_length=1, max_length=200)
    ruleset: Literal["PvE", "PvP", "HC", "RP"]
    auction_house_scope: Literal["shared", "faction"]
    faction: str | None

    @field_validator("economy", "region", "native_label", "faction")
    @classmethod
    def public_identity(cls, value):
        # Identity labels are operator-reviewed public market identifiers, not
        # arbitrary source/origin IDs. Fail closed on path/account-shaped labels.
        if value is not None and re.search(r"[\\/\x00-\x1f]|[A-Za-z]:|@|\b(?:WTF|Account)\b", value, re.I):
            raise ValueError("private-looking market identity")
        return value


class EvidenceState(PublicModel):
    id: Id
    state_hash: Hash
    native_label: str
    item_count: int = Field(ge=0)
    native_fact_count: int = Field(ge=0)
    receipt_count: int = Field(ge=0)
    first_acquired_at: AwareDatetime | None
    last_acquired_at: AwareDatetime | None

    _public_label = field_validator("native_label")(EvidenceMarket.public_identity.__func__)


class EvidenceFact(PublicModel):
    item_key: str
    external_item_id: str
    key_kind: Literal["item", "gear_level", "gear_suffix", "pet"]
    scan_day: Value | None
    native_l: Value | None
    native_h: Value | None
    native_a: Value | None
    native_m: Value | None
    minimum_copper: Value | None
    minimum_origin: Literal["l", "h_fallback"] | None
    native_fact_count: int = Field(ge=1, le=4)

    @model_validator(mode="after")
    def public_item(self):
        if normalize_item_key(self.item_key) != (self.item_key, self.external_item_id, self.key_kind):
            raise ValueError("invalid native item identity")
        if self.key_kind == "gear_suffix":
            EvidenceMarket.public_identity(self.item_key.split(":", 2)[2])
        return self


class EvidenceReceipt(PublicModel):
    id: Id
    acquired_at: AwareDatetime
    received_at: AwareDatetime
    status: Literal["completed", "duplicate"]
    source_sha256: Hash
    input_format: Literal["lua_tables", "cbor_definite", "mixed"]
    codec_producer: Literal["unverified", "C_EncodingUtil", "LibCBOR"]
    capture_build_known: bool


class EvidencePage(PublicModel):
    contract: Literal["5c1-v1"] = "5c1-v1"
    dataset: Dataset
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0, le=2147483647)
    has_more: bool


class EvidenceMarketsPage(EvidencePage):
    items: list[EvidenceMarket] = Field(max_length=100)


class EvidenceStatesPage(EvidencePage):
    market_id: Id
    items: list[EvidenceState] = Field(max_length=100)


class EvidenceFactsPage(EvidencePage):
    market_id: Id
    export_id: Id
    items: list[EvidenceFact] = Field(max_length=100)


class EvidenceReceiptsPage(EvidencePage):
    market_id: Id
    export_id: Id
    items: list[EvidenceReceipt] = Field(max_length=100)


def _query_fields(request: Request):
    if set(request.query_params) - {"dataset", "limit", "offset"} or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise HTTPException(422, "Unknown or repeated evidence query parameter")


router = APIRouter(prefix="/evidence/v2", tags=["Native v2 evidence (read only)"], dependencies=[Depends(_query_fields)])


def _read(operation):
    try:
        return operation(LocalEvidenceReader(connect))
    except ValidationError:
        raise HTTPException(409, "Evidence cannot be safely displayed") from None
    except EvidenceSchemaUnavailable:
        raise HTTPException(503, "Evidence schema 006 not prepared") from None
    except ValueError:
        raise HTTPException(404, "Evidence selection unavailable") from None
    except psycopg.Error:
        raise HTTPException(503, "Evidence database unavailable or schema 006 not prepared") from None


def _page(model, rows, dataset, limit, offset, **context):
    return model(dataset=dataset, limit=limit, offset=offset, has_more=len(rows)>limit,
                 items=[{**row, **({"id": str(row["id"])} if "id" in row else {})} for row in rows[:limit]], **context)


@router.get("/markets", response_model=EvidenceMarketsPage)
def markets(dataset: Dataset, limit: Limit = 50, offset: Offset = 0):
    return _read(lambda reader: _page(EvidenceMarketsPage,
        reader.web_markets(dataset, limit=limit+1, offset=offset), dataset, limit, offset))


@router.get("/markets/{market_id}/states", response_model=EvidenceStatesPage)
def states(market_id: Selector, dataset: Dataset, limit: Limit = 50, offset: Offset = 0):
    return _read(lambda reader: _page(EvidenceStatesPage,
        reader.web_states(market_id, dataset, limit=limit+1, offset=offset), dataset, limit, offset, market_id=str(market_id)))


@router.get("/markets/{market_id}/states/{export_id}/facts", response_model=EvidenceFactsPage)
def facts(market_id: Selector, export_id: Selector, dataset: Dataset, limit: Limit = 100, offset: Offset = 0):
    def operation(reader):
        rows = reader.web_facts(export_id, market_id, dataset, limit=limit+1, offset=offset)
        for row in rows:
            row["minimum_copper"] = row["native_l"] if row["native_l"] is not None else row["native_h"]
            row["minimum_origin"] = "l" if row["native_l"] is not None else "h_fallback" if row["native_h"] is not None else None
        return _page(EvidenceFactsPage, rows, dataset, limit, offset, market_id=str(market_id), export_id=str(export_id))
    return _read(operation)


@router.get("/markets/{market_id}/states/{export_id}/receipts", response_model=EvidenceReceiptsPage)
def receipts(market_id: Selector, export_id: Selector, dataset: Dataset, limit: Limit = 20, offset: Offset = 0):
    return _read(lambda reader: _page(EvidenceReceiptsPage,
        reader.web_receipts(export_id, market_id, dataset, limit=limit+1, offset=offset), dataset, limit, offset,
        market_id=str(market_id), export_id=str(export_id)))
