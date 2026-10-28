"""Read only local metadata; this endpoint never calls a provider or SQL."""
from fastapi import APIRouter, HTTPException, Request, Response
from app.catalog import CatalogCache, CatalogPage, cache_path

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/items", response_model=CatalogPage)
def items(request: Request, response: Response):
    if request.query_params:
        raise HTTPException(422, "No query parameters supported.")
    response.headers["Cache-Control"] = "no-store"
    try:
        return CatalogPage(items=CatalogCache(cache_path()).items())
    except OSError:
        raise HTTPException(503, "Local catalog unavailable.") from None
