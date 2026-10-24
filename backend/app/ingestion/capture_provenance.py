"""Explicit operator attestations, separate from facts observed in SavedVariables."""
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ingestion.partial_contracts import Ruleset

MAX_PROVENANCE_BYTES = 65536


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=100)
    evidence_ref: str = Field(min_length=1, max_length=500)

    @field_validator("value", "evidence_ref")
    @classmethod
    def clean(cls, value, info):
        return evidence_reference(value) if info.field_name == "evidence_ref" else clean_text(value)


def clean_text(value):
    if value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("metadata must be trimmed and contain no control characters")
    return value


def evidence_reference(value):
    clean_text(value)
    if value.lower() in ("unknown", "unverified", "pending", "pendiente", "todo", "tbd", "placeholder"):
        raise ValueError("an actual evidence reference is required")
    return value


class CaptureProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    format_version: Literal["340", "341"]
    source_id: str = Field(min_length=1, max_length=200)
    region: str = Field(min_length=1, max_length=100)
    dataset: Literal["real", "simulated", "stress_test", "launch"]
    capture_phase: Literal["stress_test", "launch", "other", "simulated"]
    market_rulesets: dict[str, Ruleset] = Field(min_length=1, max_length=100)
    region_evidence_ref: str = Field(min_length=1, max_length=500)
    market_evidence_ref: str = Field(min_length=1, max_length=500)
    origin_evidence_ref: str = Field(min_length=1, max_length=500)
    # Installed now does not imply observed at capture. Each claim has its own evidence.
    installed_client_build: EvidenceClaim | None = None
    capture_client_build: EvidenceClaim | None = None
    installed_addon_version: EvidenceClaim | None = None
    capture_addon_version: EvidenceClaim | None = None
    codec_producer: Literal["unverified", "C_EncodingUtil", "LibCBOR"] = "unverified"
    codec_producer_evidence_ref: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("version", mode="before")
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("capture metadata version must be integer 1")
        return value

    @field_validator("source_id", "region_evidence_ref", "market_evidence_ref", "origin_evidence_ref",
                     "codec_producer_evidence_ref")
    @classmethod
    def clean(cls, value):
        return clean_text(value) if value is not None else None

    @field_validator("source_id")
    @classmethod
    def explicit_source(cls, value):
        return evidence_reference(value)

    @field_validator("region_evidence_ref", "market_evidence_ref", "origin_evidence_ref", "codec_producer_evidence_ref")
    @classmethod
    def reference(cls, value):
        return evidence_reference(value) if value is not None else None

    @field_validator("region")
    @classmethod
    def explicit_region(cls, value):
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", value)
                or re.search(r"unknown|unverified|pending|pendiente|placeholder", value, re.I)
                or value.lower() in ("test", "simulation", "todo", "tbd", "none", "null", "pvp", "pve", "hc", "rp")):
            raise ValueError("a verified technical region identifier is required")
        return value

    @field_validator("market_rulesets")
    @classmethod
    def clean_markets(cls, value):
        for key, ruleset in value.items():
            clean_text(key)
            if not key or len(key) > 200 or (key in ("PvE", "PvP", "HC", "RP") and key != ruleset):
                raise ValueError("invalid market attestation")
        return value

    @model_validator(mode="after")
    def consistency(self):
        if ((self.capture_phase == "stress_test") != (self.dataset == "stress_test")
                or (self.capture_phase == "simulated") != (self.dataset == "simulated")):
            raise ValueError("capture phase and dataset disagree")
        if self.dataset == "stress_test" and self.format_version != "341":
            raise ValueError("stress_test persistence requires format 341")
        if self.dataset == "launch" and (self.capture_phase != "launch" or self.format_version != "341"):
            raise ValueError("launch dataset requires launch phase and format 341")
        if (self.codec_producer != "unverified") != (self.codec_producer_evidence_ref is not None):
            raise ValueError("a known codec producer requires separate evidence; unknown has none")
        if self.capture_addon_version and self.capture_addon_version.value != self.format_version:
            raise ValueError("confirmed capture addon version disagrees with selected format")
        return self

    def validate_context(self, batch, source_hash, markets, input_format):
        if (self.source_sha256 != source_hash or self.format_version != batch.source_version
                or self.source_id != batch.source_id or self.region != batch.region or self.dataset != batch.dataset
                or self.market_rulesets != {m.market_key: m.ruleset for m in markets}):
            raise ValueError("provenance does not match the input hash or batch/market context")
        if input_format == "libcbor" and self.codec_producer != "LibCBOR":
            raise ValueError("LibCBOR provenance requires a verified LibCBOR producer")

    def stored_manifest(self):
        # The receipt already preserves the exact byte hash in partial_import_runs.
        # Exclude it here so equivalent serializations can reuse a sealed state.
        return self.model_dump(mode="json", exclude={"source_sha256"})


def load_capture_provenance(path: Path) -> CaptureProvenance:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_PROVENANCE_BYTES + 1)
    if len(raw) > MAX_PROVENANCE_BYTES:
        raise ValueError("capture provenance exceeds 64 KiB")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate capture metadata key")
            result[key] = value
        return result

    return CaptureProvenance.model_validate(json.loads(raw, object_pairs_hook=unique))
