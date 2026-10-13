"""Read-only Market Intelligence contracts; decimals serialize as JSON strings."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.ingestion.auctionator_keys import normalize_item_key
from app.ingestion.partial_contracts import BoundedInt, Ruleset

MAX_POSITIONS = 366
PositiveID = Annotated[int, Field(gt=0, le=9223372036854775807)]
Mode = Literal["accumulated", "export"]
SourceType = Literal["auctionator", "simulated"]


def canonical_basis(value: str) -> str:
    if value == "unknown":
        return value
    try:
        epoch = datetime.fromisoformat(value)
        if epoch.tzinfo is None or epoch.utcoffset() is None:
            raise ValueError("temporal_basis requires a timezone")
        return epoch.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as error:
        raise ValueError("temporal_basis must be unknown or a timezone-aware ISO datetime") from error


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ItemSelection(Contract):
    market_id: PositiveID
    item_key: str = Field(min_length=1, max_length=200)

    @field_validator("item_key")
    @classmethod
    def normalized_item(cls, value):
        if normalize_item_key(value)[0] != value:
            raise ValueError("item_key must include its complete normalized variant")
        return value


class SeriesSelector(ItemSelection):
    source_id: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    temporal_basis: str = Field(min_length=1, max_length=100)
    series_mode: Mode
    export_id: PositiveID | None = None

    @field_validator("source_id")
    @classmethod
    def source_identity(cls, value):
        if value != value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("source_id must be trimmed and contain no control characters")
        return value

    @field_validator("temporal_basis")
    @classmethod
    def time_identity(cls, value):
        return canonical_basis(value)

    @model_validator(mode="after")
    def explicit_mode(self):
        if (self.series_mode == "export") != (self.export_id is not None):
            raise ValueError("export mode requires export_id; accumulated mode forbids it")
        return self


class WindowSpec(Contract):
    window_type: Literal["observed_buckets", "index_range", "calendar_days"]
    size: Annotated[int, Field(ge=1, le=MAX_POSITIONS)] | None = None
    start_day: BoundedInt | None = None
    end_day: BoundedInt | None = None
    days: Literal[7, 14, 30] | None = None

    @model_validator(mode="after")
    def valid_combination(self):
        if self.window_type == "observed_buckets":
            if self.size is None or self.start_day is not None or self.days is not None:
                raise ValueError("observed_buckets requires size and forbids start_day/days")
        elif self.window_type == "index_range":
            if self.start_day is None or self.end_day is None or self.size is not None or self.days is not None:
                raise ValueError("index_range requires start_day/end_day and forbids size/days")
            if not 1 <= self.end_day - self.start_day + 1 <= MAX_POSITIONS:
                raise ValueError("index_range must contain 1..366 positions")
        elif self.days is None or self.size is not None or self.start_day is not None:
            raise ValueError("calendar_days requires days=7/14/30 and forbids size/start_day")
        return self


class AnalysisRequest(Contract):
    selector: SeriesSelector
    window: WindowSpec

    @model_validator(mode="after")
    def calendar_requires_epoch(self):
        if self.window.window_type == "calendar_days" and self.selector.temporal_basis == "unknown":
            raise ValueError("calendar_days requires a verified temporal_basis")
        return self


class MetricsQuery(SeriesSelector):
    window_type: Literal["observed_buckets", "index_range", "calendar_days"]
    size: Annotated[int, Field(ge=1, le=MAX_POSITIONS)] | None = None
    # Query strings are parsed here; the domain WindowSpec retains strict indices.
    start_day: Annotated[int, Field(ge=0, le=2147483647)] | None = None
    end_day: Annotated[int, Field(ge=0, le=2147483647)] | None = None
    days: Annotated[int, Field(ge=7, le=30)] | None = None

    def analysis_request(self) -> AnalysisRequest:
        data = self.model_dump()
        return AnalysisRequest(
            selector=SeriesSelector(**{k: data[k] for k in SeriesSelector.model_fields}),
            window=WindowSpec(**{k: data[k] for k in WindowSpec.model_fields}),
        )

    @model_validator(mode="after")
    def validate_window(self):
        self.analysis_request()
        return self


class DiscoveryQuery(ItemSelection):
    series_mode: Mode | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2147483647)


class SeriesContext(SeriesSelector):
    market_key: str
    ruleset: Ruleset
    region: str
    dataset: Literal["real", "simulated"]
    external_item_id: str
    key_kind: Literal["item", "gear_level", "gear_suffix", "pet"]
    source_version: Literal["340"] = "340"
    database_version: Literal[8] = 8
    value_semantics: Literal["accumulated_extreme", "export_projection"]

    @model_validator(mode="after")
    def compatible_context(self):
        if (self.source_type == "simulated") != (self.dataset == "simulated"):
            raise ValueError("source type and dataset disagree")
        if normalize_item_key(self.item_key) != (self.item_key, self.external_item_id, self.key_kind):
            raise ValueError("item identity disagrees")
        expected = "export_projection" if self.series_mode == "export" else "accumulated_extreme"
        if self.value_semantics != expected:
            raise ValueError("value semantics and mode disagree")
        return self


class EvidenceReference(Contract):
    table: Literal["partial_observations", "partial_export_facts"]
    row_id: PositiveID
    first_import_id: PositiveID | None = None
    last_import_id: PositiveID | None = None
    native_field: Literal["l", "h", "a"] | None = None
    original_item_key: str | None = None
    original_day_key: str | None = None


class BucketPoint(Contract):
    scan_day: BoundedInt
    bucket_start: datetime | None = None
    market_observed: bool
    daily_minimum: BoundedInt | None = None
    daily_highest_minimum: BoundedInt | None = None
    daily_max_available: BoundedInt | None = None
    minimum_origin: Literal["l", "h_fallback", "unknown"] | None = None
    minimum_evidence: EvidenceReference | None = None
    highest_minimum_evidence: EvidenceReference | None = None
    availability_evidence: EvidenceReference | None = None

    @model_validator(mode="after")
    def coherent_values(self):
        if (self.daily_minimum is None) != (self.minimum_origin is None):
            raise ValueError("minimum origin requires a minimum value")
        if (self.daily_minimum is not None and self.daily_highest_minimum is not None
                and self.daily_minimum > self.daily_highest_minimum):
            raise ValueError("daily minimum exceeds highest minimum")
        if not self.market_observed and any(v is not None for v in (
            self.daily_minimum, self.daily_highest_minimum, self.daily_max_available
        )):
            raise ValueError("item evidence requires an observed market bucket")
        if self.bucket_start is not None and self.bucket_start.utcoffset() is None:
            raise ValueError("bucket_start requires timezone")
        return self


class ResolvedWindow(Contract):
    spec: WindowSpec
    anchor_day: BoundedInt | None
    market_first_day: BoundedInt | None
    market_last_day: BoundedInt | None
    start_day: BoundedInt | None
    end_day: BoundedInt | None
    positions: list[BoundedInt] = Field(max_length=MAX_POSITIONS)
    requested_position_count: int
    calendar_start: datetime | None = None
    calendar_end_exclusive: datetime | None = None


class MetricValue(Contract):
    value: Decimal | None
    unit: str
    status: Literal["ok", "no_data", "insufficient_data", "undefined"]
    reason: str | None = None
    observation_count: int = Field(ge=0)
    first_day: BoundedInt | None = None
    last_day: BoundedInt | None = None

    @field_serializer("value", when_used="json")
    def fixed_decimal(self, value: Decimal | None):
        # Formatting changes notation only: no quantize, rounding or float conversion.
        return format(value, "f") if value is not None else None

    @model_validator(mode="after")
    def defined_status(self):
        if (self.value is not None) != (self.status == "ok"):
            raise ValueError("only ok metrics have a value")
        if self.status != "ok" and self.reason is None:
            raise ValueError("unavailable metrics require a reason")
        return self


class MarketMetrics(Contract):
    minimum_copper: MetricValue
    mean_daily_minimum_copper: MetricValue
    median_daily_minimum_copper: MetricValue
    first_minimum_copper: MetricValue
    last_minimum_copper: MetricValue
    price_change_copper: MetricValue
    price_change_pct: MetricValue
    minimum_stddev_copper: MetricValue
    minimum_cv_pct: MetricValue
    trend_copper_per_scan_index: MetricValue
    first_max_available: MetricValue
    last_max_available: MetricValue
    availability_change_units: MetricValue
    availability_change_pct: MetricValue


class CoverageSummary(Contract):
    selected_position_count: int
    observed_market_bucket_count: int
    price_observation_count: int
    availability_observation_count: int
    missing_price_position_count: int
    missing_availability_position_count: int
    index_span_position_count: int
    unobserved_market_position_count: int
    price_ratio: MetricValue
    availability_ratio: MetricValue


class QualityWarning(Contract):
    code: str
    message: str


class QualitySummary(Contract):
    warnings: list[QualityWarning]
    minimum_l_count: int
    minimum_h_fallback_count: int
    minimum_unknown_origin_count: int
    availability_field_presence: Literal["present", "absent", "unknown"]
    sample_warning_threshold: Literal[7] = 7


class ProvenanceSummary(Contract):
    selected_daily_row_count: int
    excluded_undated_count: int
    # A normalized state / export fact count, never a count of physical scans.
    undated_count_scope: Literal["selected_item_context_all_indices"] = "selected_item_context_all_indices"
    referenced_import_ids: list[int]
    export_state_hash: str | None = None
    first_received_at: datetime | None = None


class SeriesDescriptor(Contract):
    context: SeriesContext
    item_first_day: BoundedInt | None
    item_last_day: BoundedInt | None
    market_first_day: BoundedInt | None
    market_last_day: BoundedInt | None
    excluded_undated_count: int
    availability_field_presence: Literal["present", "absent", "unknown"]
    first_received_at: datetime | None = None


class SeriesDiscoveryResponse(Contract):
    series: list[SeriesDescriptor]
    limit: int
    offset: int
    has_more: bool
    ordering: Literal["mode_source_basis_export_id; not observation chronology"] = "mode_source_basis_export_id; not observation chronology"


class MarketMetricsResponse(Contract):
    analysis_version: Literal["3a-v1"] = "3a-v1"
    decimal_precision: Literal[40] = 40
    context: SeriesContext
    window: ResolvedWindow
    points: list[BucketPoint] = Field(max_length=MAX_POSITIONS)
    metrics: MarketMetrics
    coverage: CoverageSummary
    quality: QualitySummary
    provenance: ProvenanceSummary
