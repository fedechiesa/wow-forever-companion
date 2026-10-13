from typing import Annotated

import psycopg
from fastapi import APIRouter, HTTPException, Query

from app.market.contracts import (
    DiscoveryQuery, MarketMetricsResponse, MetricsQuery, SeriesDiscoveryResponse,
)
from app.market.errors import SeriesIntegrityError, SeriesNotFound, WindowError
from app.market.service import MarketAnalysisService

router = APIRouter(prefix="/market", tags=["Market Intelligence"])


def _read(operation):
    try:
        return operation()
    except SeriesNotFound as error:
        raise HTTPException(404, str(error)) from error
    except SeriesIntegrityError as error:
        raise HTTPException(409, str(error)) from error
    except WindowError as error:
        raise HTTPException(422, str(error)) from error
    except psycopg.Error as error:
        raise HTTPException(503, "Market database unavailable") from error


@router.get("/series", response_model=SeriesDiscoveryResponse)
def discover_series(query: Annotated[DiscoveryQuery, Query()]):
    return _read(lambda: MarketAnalysisService().discover(query))


@router.get("/metrics", response_model=MarketMetricsResponse)
def market_metrics(query: Annotated[MetricsQuery, Query()]):
    return _read(lambda: MarketAnalysisService().analyze(query.analysis_request()))
