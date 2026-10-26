"""Verified local lineage preparation for the manual archive CLI and trial service.

Economic identity excludes the observer, native label, evidence references and
acquisition time. Native labels and original keys remain in immutable facts.
"""
from dataclasses import replace
from hashlib import sha256
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.ingestion.adapters.auctionator import AuctionatorAdapter, DecodedAuctionator
from app.ingestion.capture_provenance import CaptureProvenance, EvidenceClaim, evidence_reference
from app.local_capture.contracts import CaptureMetadata, Contract, canonical_json, describe
from app.local_capture.decoder import CaptureAdapter, CaptureEvidence
from app.local_capture.readiness import MAX_PERSISTED_PRICE


class VerifiedEconomy(Contract):
    # Stable operator-reviewed technical realm/connected-economy identifier;
    # never a player ID or an inferred parsing of the native label.
    economy: EvidenceClaim
    realm: EvidenceClaim | None
    faction: EvidenceClaim | None
    auction_house_scope: Literal["shared", "faction"]
    scope_evidence_ref: str = Field(min_length=1, max_length=500)

    @field_validator("economy", "realm", "faction")
    @classmethod
    def known_identity(cls, value):
        if value is not None:
            evidence_reference(value.value)
        return value

    @field_validator("scope_evidence_ref")
    @classmethod
    def known_scope(cls, value):
        return evidence_reference(value)

    @model_validator(mode="after")
    def partition(self):
        if (self.auction_house_scope == "faction") != (self.faction is not None):
            raise ValueError("faction AH requires its economic faction; shared AH requires faction=null")
        return self

    def identity(self, provenance):
        return dict(version=1, dataset=provenance.dataset, region=provenance.region,
                    economy=self.economy.value, auction_house_scope=self.auction_house_scope,
                    faction=self.faction.value if self.faction else None)


class VerifiedLocalContext(Contract):
    contract: Literal["verified-local-capture-v1"]
    provenance: CaptureProvenance
    serialized_codec: Literal["cbor-definite"] | None
    market_identities: dict[str, VerifiedEconomy] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def complete(self):
        p = self.provenance
        if p.format_version != "341" or p.dataset not in ("simulated", "stress_test", "launch"):
            raise ValueError("verified local capture requires format 341 and an explicit lifecycle dataset")
        if set(self.market_identities) != set(p.market_rulesets):
            raise ValueError("verified identity must cover every native market exactly")
        identities = [canonical_json(m.identity(p)) for m in self.market_identities.values()]
        if len(identities) != len(set(identities)):
            raise ValueError("two native labels for one economy in a single export require explicit reconciliation")
        return self

    def identities(self):
        return {key: value.identity(self.provenance) for key, value in sorted(self.market_identities.items())}


class LocalCaptureBinding(Contract):
    metadata: CaptureMetadata
    context: VerifiedLocalContext


def _validate_decoded(decoded, metadata, context):
    p = context.provenance
    if metadata.selected_source_version not in (None, "341"):
        raise ValueError("archive format selection contradicts local context")
    if metadata.selected_serialized_codec != context.serialized_codec:
        raise ValueError("archive codec selection contradicts local context")
    expected = describe(decoded, source_bytes=metadata.source_bytes, captured_at=metadata.captured_at,
                        origin=metadata.origin, source_version=metadata.selected_source_version,
                        serialized_codec=context.serialized_codec)
    if expected != metadata or p.source_sha256 != decoded.source_hash:
        raise ValueError("archive metadata, hashes and decoded evidence disagree")
    if p.market_rulesets != {m.market_key: m.ruleset for m in decoded.native.markets}:
        raise ValueError("native markets disagree with verified context")
    if decoded.simulated_marker and p.dataset != "simulated":
        raise ValueError("simulation cannot be relabelled as authentic")
    if any(f.value > MAX_PERSISTED_PRICE for f in decoded.native.facts if f.native_field in ("l", "h", "m")):
        raise ValueError("price_exceeds_persistence_int32: entire capture remains local evidence")


def prepare_local_capture(raw: bytes, metadata: CaptureMetadata, context: VerifiedLocalContext):
    """Validate an already-read archive buffer. No file I/O, settings or SQL.

    Returned evidence can only be written through PartialIngestionService with
    a verified TrialDatabase. The manual archive CLI invokes this helper only
    after selecting and verifying a published capture. Watcher/HTTP do not.
    """
    metadata = CaptureMetadata.model_validate(metadata.model_dump())
    context = VerifiedLocalContext.model_validate(context.model_dump())
    p = context.provenance
    mapping = {key: value for key, value in p.market_rulesets.items() if key not in ("PvE", "PvP", "HC", "RP")}
    decoded = CaptureAdapter().decode_bytes(raw, serialized_codec=context.serialized_codec, market_mapping=mapping)
    if metadata.source_bytes != len(raw):
        raise ValueError("archive byte count disagrees with original buffer")
    _validate_decoded(decoded, metadata, context)
    result = AuctionatorAdapter().load_bytes(
        raw, source_id=p.source_id, region=p.region, dataset=p.dataset, source_version="341",
        serialized_codec=context.serialized_codec, market_mapping=mapping, provenance=p,
        raw_reference="local-capture:" + metadata.capture_id,
    )
    return replace(result, local_capture=LocalCaptureBinding(metadata=metadata, context=context))


def validate_local_binding(result):
    binding = LocalCaptureBinding.model_validate(result.local_capture.model_dump())
    if result.native is None or result.native.provenance is None:
        raise ValueError("local capture requires native evidence and provenance")
    if result.batch.scan_day_zero is not None:
        raise ValueError("local capture retains unknown native time; acquisition is not a scan epoch")
    if result.native.provenance != binding.context.provenance:
        raise ValueError("local receipt and export provenance disagree")
    # The adapter supplies the byte hash; independently recompute economic
    # hashes from its validated facts to detect altered bindings/model instances.
    native = CaptureEvidence.model_validate(result.native.model_dump(exclude={"provenance"}))
    decoded = DecodedAuctionator(native.projected_observations(), native, result.source_hash,
                                binding.metadata.simulated_marker)
    _validate_decoded(decoded, binding.metadata, binding.context)
    return binding


def local_export_identity(result):
    """v2 state: shared native evidence plus verified economic interpretation.

    First-observer provenance stays on the sealed header for compatibility with
    005; every observer's complete attestation is stored on its own receipt.
    """
    manifest = result.native.manifest()
    manifest["market_identities"] = result.local_capture.context.identities()
    economic_structure = {key: value for key, value in manifest.items() if key != "provenance"}
    payload = dict(contract="verified-local-export-v2", source_version=result.batch.source_version,
                   database_version=result.batch.database_version, temporal_basis="unknown",
                   structure=economic_structure, native_sha256=result.local_capture.metadata.market_sha256)
    return sha256(canonical_json(payload)).hexdigest(), manifest
