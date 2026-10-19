"""Versioned statistical rules, independent of item names and HTTP."""
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import Field, field_serializer, field_validator, model_validator

from app.market.contracts import (
    MAX_POSITIONS, BucketPoint, Contract, CoverageSummary, MetricValue, MetricsQuery,
    ProvenanceSummary, QualitySummary, QualityWarning, ResolvedWindow, SeriesContext,
)


SIGNAL_DECIMAL_FIELDS = (
    "min_price_coverage", "min_index_coverage", "deviation_threshold_pct",
    "trend_threshold_pct", "min_trend_slope_copper_per_scan_index",
)
MAX_PARAMETER_INPUT_CHARACTERS = 128
MAX_PARAMETER_FIXED_CHARACTERS = 96
MIN_NONZERO_PARAMETER = Decimal("1e-64")
MAX_PERCENT_THRESHOLD = Decimal("1e12")
MAX_SLOPE_THRESHOLD = Decimal("2147483647")
PARAMETER_DECIMAL_DESCRIPTION = (
    "Finite Decimal; text input at most 128 characters, fixed representation at most 96 characters; "
    "nonzero magnitude at least 1e-64. No rounding or normalization."
)


def _bounded_parameter_decimal(value):
    """Inspect the compact coefficient/exponent before any fixed-point formatting.

    Decimal context precision does not bound format(..., 'f'). Keep error messages
    constant, including for zero with an enormous exponent. No normalize/quantize.
    """
    if isinstance(value, str) and len(value) > MAX_PARAMETER_INPUT_CHARACTERS:
        raise ValueError("signal Decimal text exceeds 128 characters")
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int, float)):
        return value  # Leave unsupported types to Pydantic's ordinary type validation.
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("signal parameter must be a finite Decimal") from None
    if not number.is_finite():
        raise ValueError("signal parameter must be a finite Decimal")
    sign, digits, exponent = number.as_tuple()
    count = len(digits)
    length = (count + exponent if exponent >= 0 else
              count + 1 if count + exponent > 0 else 2 - exponent) + sign
    if length > MAX_PARAMETER_FIXED_CHARACTERS:
        raise ValueError("signal Decimal fixed representation exceeds 96 characters")
    if number != 0 and number.copy_abs() < MIN_NONZERO_PARAMETER:
        raise ValueError("nonzero signal Decimal magnitude must be at least 1e-64")
    return number


class SignalParameters(Contract):
    min_history_observations: int = Field(default=7, ge=3, le=MAX_POSITIONS - 1)
    min_trend_observations: int = Field(default=7, ge=3, le=MAX_POSITIONS)
    min_price_coverage: Decimal = Field(default=Decimal("0.8"), ge=MIN_NONZERO_PARAMETER, le=1,
                                      description=PARAMETER_DECIMAL_DESCRIPTION)
    min_index_coverage: Decimal = Field(default=Decimal("0.5"), ge=MIN_NONZERO_PARAMETER, le=1,
                                      description=PARAMETER_DECIMAL_DESCRIPTION)
    deviation_threshold_pct: Decimal = Field(default=Decimal("20"), ge=MIN_NONZERO_PARAMETER, le=MAX_PERCENT_THRESHOLD,
                                            description=PARAMETER_DECIMAL_DESCRIPTION)
    trend_threshold_pct: Decimal = Field(default=Decimal("10"), ge=MIN_NONZERO_PARAMETER, le=MAX_PERCENT_THRESHOLD,
                                        description=PARAMETER_DECIMAL_DESCRIPTION)
    min_trend_slope_copper_per_scan_index: Decimal = Field(default=Decimal("0"), ge=0, le=MAX_SLOPE_THRESHOLD,
                                                         description=PARAMETER_DECIMAL_DESCRIPTION)
    max_latest_price_lag: int = Field(default=0, ge=0, le=2147483647)
    require_native_l: bool = False
    require_known_temporal_basis: bool = False

    @field_validator(*SIGNAL_DECIMAL_FIELDS, mode="before")
    @classmethod
    def bounded_decimal(cls, value):
        return _bounded_parameter_decimal(value)

    @field_serializer(*SIGNAL_DECIMAL_FIELDS, when_used="json")
    def fixed_decimal(self, value: Decimal):
        # Also guard serialization of instances built via model_construct/model_copy.
        return format(_bounded_parameter_decimal(value), "f")


class SignalsQuery(MetricsQuery, SignalParameters):
    def signal_parameters(self) -> SignalParameters:
        return SignalParameters(**{k: getattr(self, k) for k in SignalParameters.model_fields})


class EvidenceReason(Contract):
    code: Literal[
        "insufficient_observations", "insufficient_history", "insufficient_price_coverage",
        "insufficient_index_coverage", "latest_price_missing_or_stale", "native_l_required",
        "known_temporal_basis_required", "zero_reference", "zero_baseline", "unavailable_trend",
    ]
    message: str


class SignalEvidence(Contract):
    status: Literal["sufficient", "insufficient"]
    reasons: list[EvidenceReason]
    usable_observation_count: int = Field(ge=0)
    historical_observation_count: int = Field(ge=0)
    # These supplement, and deliberately do not redefine, 3A's selected-position ratio.
    requested_price_ratio: MetricValue
    index_span_price_ratio: MetricValue
    latest_price_lag: int | None = Field(default=None, ge=0)
    minimum_l_count: int = Field(ge=0)
    minimum_h_fallback_count: int = Field(ge=0)
    minimum_unknown_origin_count: int = Field(ge=0)

    @model_validator(mode="after")
    def coherent_status(self):
        if (self.status == "insufficient") != bool(self.reasons):
            raise ValueError("insufficient evidence requires reasons; sufficient evidence forbids them")
        return self


class HistoricalDeviationSignal(Contract):
    signal_type: Literal["historical_price_deviation"] = "historical_price_deviation"
    direction: Literal["below_reference", "above_reference", "no_significant_deviation", "insufficient_evidence"]
    observed_price_copper: MetricValue
    reference_price_copper: MetricValue
    reference_method: Literal["median_excluding_latest"] = "median_excluding_latest"
    signed_deviation_copper: MetricValue
    absolute_deviation_copper: MetricValue
    deviation_pct: MetricValue
    evidence: SignalEvidence
    explanation: str


class HistoricalTrendSignal(Contract):
    signal_type: Literal["historical_price_trend"] = "historical_price_trend"
    direction: Literal["ascending", "descending", "no_significant_trend", "insufficient_evidence"]
    first_price_copper: MetricValue
    last_price_copper: MetricValue
    slope_copper_per_scan_index: MetricValue
    price_change_copper: MetricValue
    price_change_pct: MetricValue
    evidence: SignalEvidence
    explanation: str


class MarketSignalsResponse(Contract):
    analysis_version: Literal["3b1-v1"] = "3b1-v1"
    metrics_analysis_version: Literal["3a-v1"] = "3a-v1"
    decimal_precision: Literal[40] = 40
    parameters: SignalParameters
    context: SeriesContext
    window: ResolvedWindow
    points: list[BucketPoint] = Field(max_length=MAX_POSITIONS)
    coverage: CoverageSummary
    quality: QualitySummary
    provenance: ProvenanceSummary
    warnings: list[QualityWarning]
    price_deviation: HistoricalDeviationSignal
    historical_trend: HistoricalTrendSignal
