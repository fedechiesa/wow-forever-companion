"""Bounded native local evidence, independent of SQL INTEGER storage limits.

Authentic SavedVariables contain integer prices above 2**31-1. Keep their exact
values locally; importing still constructs the unchanged PartialBatch contract.
Availability, bucket indices and all other parser limits remain unchanged.
"""
from typing import Annotated

from pydantic import Field, model_validator

from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.native_exports import NativeExportEvidence, NativeFact
from app.ingestion.partial_contracts import MAX_OBSERVATIONS, PartialObservation

MAX_CAPTURE_PRICE = 2**63 - 1
MAX_CAPTURE_AVAILABILITY = 2**31 - 1
CaptureValue = Annotated[int, Field(strict=True, ge=0, le=MAX_CAPTURE_PRICE)]


def bounded_availability(observation):
    if observation.statistic == "daily_max_available" and observation.value > MAX_CAPTURE_AVAILABILITY:
        raise ValueError("native availability exceeds local capture limit")
    return observation


class CaptureObservation(PartialObservation):
    value: CaptureValue

    @model_validator(mode="after")
    def availability_limit(self):
        return bounded_availability(self)


class CaptureFact(NativeFact):
    value: CaptureValue

    @model_validator(mode="after")
    def availability_limit(self):
        return bounded_availability(self)

    def observation(self, **updates):
        fields = self.model_dump(include=set(PartialObservation.model_fields))
        fields.update(updates)
        return CaptureObservation.model_validate(fields)


class CaptureEvidence(NativeExportEvidence):
    facts: list[CaptureFact] = Field(min_length=1, max_length=MAX_OBSERVATIONS)


class CaptureAdapter(AuctionatorAdapter):
    """Same literal readers/validators; bounded 64-bit prices only for local evidence."""
    observation_type = CaptureObservation
    fact_type = CaptureFact
    evidence_type = CaptureEvidence
