"""Shared read-only domain service for HTTP, React and future tool callers."""
from app.db.connection import connect
from app.market.contracts import (
    AnalysisRequest, DiscoveryQuery, MarketMetricsResponse, ProvenanceSummary,
    SeriesDescriptor, SeriesDiscoveryResponse,
)
from app.market.quality import coverage, quality
from app.market.repository import MarketRepository
from app.market.series import build_points
from app.market.statistics import compute_metrics
from app.market.windows import resolve_window


class MarketAnalysisService:
    def discover(self, query: DiscoveryQuery) -> SeriesDiscoveryResponse:
        with connect() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            selections, has_more = MarketRepository(connection).discover(query)
            return SeriesDiscoveryResponse(
                series=[SeriesDescriptor(
                    context=d.context, item_first_day=d.item_first_day, item_last_day=d.item_last_day,
                    market_first_day=d.market_first_day, market_last_day=d.market_last_day,
                    excluded_undated_count=d.undated_count, availability_field_presence=d.availability_presence,
                    first_received_at=d.header["first_received_at"] if d.header else None,
                ) for d in selections], limit=query.limit, offset=query.offset, has_more=has_more,
            )

    def analyze(self, request: AnalysisRequest) -> MarketMetricsResponse:
        with connect() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            repository = MarketRepository(connection)
            data = repository.selection(request.selector)
            observed = repository.observed_days(data, request.window)
            window = resolve_window(request.window, data.context.temporal_basis,
                                    data.market_first_day, data.market_last_day, observed)
            rows = repository.daily_rows(data, window.positions)
            points = build_points(data.context, window.positions, observed, rows)
            summary = coverage(points, window)
            imports = {row[key] for row in rows for key in ("first_import_id", "last_import_id") if key in row}
            if data.header:
                imports.add(data.header["first_import_id"])
            return MarketMetricsResponse(
                context=data.context, window=window, points=points, metrics=compute_metrics(points), coverage=summary,
                quality=quality(data.context, points, window, summary, data.availability_presence, data.undated_count),
                provenance=ProvenanceSummary(
                    selected_daily_row_count=len(rows), excluded_undated_count=data.undated_count,
                    referenced_import_ids=sorted(imports),
                    export_state_hash=data.header["state_hash"] if data.header else None,
                    first_received_at=data.header["first_received_at"] if data.header else None,
                ),
            )
