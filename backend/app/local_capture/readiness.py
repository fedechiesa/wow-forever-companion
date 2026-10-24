"""Pure offline checks for a future local 341 import; never a persistence entrypoint.

The caller supplies an already-read archive buffer and its immutable metadata.
No files, settings, connections, import batches or database services are created.
"""
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.ingestion.capture_provenance import CaptureProvenance, EvidenceClaim, evidence_reference
from app.local_capture.contracts import CaptureMetadata, Contract, describe
from app.local_capture.decoder import CaptureAdapter

MAX_PERSISTED_PRICE = 2**31 - 1


class MarketIdentity(Contract):
    """Operator-reviewed AH scope, independent of a raw key such as PvP.

    Unknown realm/scope stays in the archive; it cannot form an import context.
    A faction-wide AH requires a verified faction. A realm-wide AH requires
    explicit evidence that the scope spans factions, never a guessed faction.
    """
    realm: EvidenceClaim
    faction: EvidenceClaim | None
    auction_house_scope: Literal["faction", "realm"]
    scope_evidence_ref: str = Field(min_length=1, max_length=500)

    @field_validator("scope_evidence_ref")
    @classmethod
    def reviewed_scope(cls, value):
        return evidence_reference(value)

    @field_validator("realm", "faction")
    @classmethod
    def reviewed_identity(cls, value):
        if value is not None:
            evidence_reference(value.value)
        return value

    @model_validator(mode="after")
    def faction_scope(self):
        if self.auction_house_scope == "faction" and self.faction is None:
            raise ValueError("faction-scoped market requires verified faction identity")
        return self


class LocalCaptureContext(Contract):
    """Explicit private sidecar candidate; not a new CLI/API or SQL manifest.

    Kept separate from CaptureProvenance v1 so existing canonical export hashes
    and sealed 340/341 evidence do not change shape or identity.
    """
    contract: Literal["local-capture-context-v1"]
    provenance: CaptureProvenance
    serialized_codec: Literal["cbor-definite"] | None
    market_identities: dict[str, MarketIdentity] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def complete_context(self):
        if self.provenance.format_version != "341":
            raise ValueError("local readiness is scoped to explicit format 341")
        if set(self.market_identities) != set(self.provenance.market_rulesets):
            raise ValueError("identity must cover every native market exactly")
        return self


Blocker = Literal[
    "local_import_not_implemented", "receipt_persistence_requires_design",
    "market_identity_persistence_requires_design", "analytics_341_unsupported",
    "price_exceeds_persistence_int32",
]


class LocalCaptureReadiness(Contract):
    status: Literal["evidence_only"] = "evidence_only"
    import_enabled: Literal[False] = False
    analytics_enabled: Literal[False] = False
    capture: CaptureMetadata
    context: LocalCaptureContext
    numeric_persistence_compatible: bool
    out_of_range_price_fact_count: int = Field(strict=True, ge=0)
    blocking_reasons: list[Blocker]


def assess_local_capture(raw: bytes, metadata: CaptureMetadata,
                         context: LocalCaptureContext) -> LocalCaptureReadiness:
    """Recompute local hashes/shape/counts and fail closed on metadata mismatch.

    Success is an evidence-only assessment, never authorization to import. If
    any price exceeds SQL INTEGER, the entire capture remains local, including
    all otherwise compatible items. No filtering, rounding or downcasting.
    """
    # Revalidate nested models too: model_copy/model_construct and subclasses
    # must not smuggle invalid prices, identities or attestations past checks.
    metadata = CaptureMetadata.model_validate(metadata.model_dump())
    context = LocalCaptureContext.model_validate(context.model_dump())
    p = context.provenance
    if metadata.selected_source_version not in (None, p.format_version):
        raise ValueError("archive format selection and provenance disagree")
    if metadata.selected_serialized_codec != context.serialized_codec:
        raise ValueError("archive codec selection and context disagree")
    mapping = {key: rule for key, rule in p.market_rulesets.items()
               if key not in ("PvE", "PvP", "HC", "RP")}
    decoded = CaptureAdapter().decode_bytes(raw, serialized_codec=context.serialized_codec,
                                           market_mapping=mapping)
    recomputed = describe(decoded, source_bytes=len(raw), captured_at=metadata.captured_at,
                          origin=metadata.origin, source_version=metadata.selected_source_version,
                          serialized_codec=context.serialized_codec)
    if recomputed != metadata:
        raise ValueError("archive bytes and immutable metadata disagree")
    if (p.source_sha256 != decoded.source_hash
            or p.market_rulesets != {m.market_key: m.ruleset for m in decoded.native.markets}):
        raise ValueError("provenance does not match archived bytes or native markets")
    if decoded.simulated_marker and p.dataset != "simulated":
        raise ValueError("generated simulation requires simulated context")
    oversized = sum(f.value > MAX_PERSISTED_PRICE for f in decoded.native.facts
                    if f.native_field in ("l", "h", "m"))
    blockers = ["local_import_not_implemented", "receipt_persistence_requires_design",
                "market_identity_persistence_requires_design", "analytics_341_unsupported"]
    if oversized:
        blockers.append("price_exceeds_persistence_int32")
    return LocalCaptureReadiness(capture=metadata, context=context,
                                numeric_persistence_compatible=not oversized,
                                out_of_range_price_fact_count=oversized, blocking_reasons=blockers)
