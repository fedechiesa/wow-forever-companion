"""Small descriptive catalog. No SQL, market data, image downloads or polling."""
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_BYTES = 65_536
MAX_ITEMS = 128
ROOT = Path(__file__).resolve().parents[2]


class CatalogError(ValueError):
    pass


class CatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product: Literal["forever"] = "forever"
    entity_kind: Literal["item"] = "item"
    item_id: int = Field(ge=1, le=2147483647)
    name: str = Field(min_length=1, max_length=256)
    language: str | None = Field(default=None, max_length=32)
    quality: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=128)
    subclass: str | None = Field(default=None, max_length=128)
    build: str | None = Field(default=None, max_length=64)
    compatibility: Literal["provider_product_only"] = "provider_product_only"
    icon_ref: str | None = None
    icon_permission: Literal["unverified", "authorized"] = "unverified"
    provider: Literal["ahledger", "foreverdb"]
    source_url: str = Field(max_length=2048)
    attribution_url: str = Field(max_length=2048)
    fetched_at: float = Field(ge=0, allow_inf_nan=False)
    expires_at: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def safe_metadata(self):
        host = {"ahledger": "ahledger.com", "foreverdb": "foreverdb.net"}[self.provider]
        for value in (self.source_url, self.attribution_url):
            url = urlsplit(value)
            if url.scheme != "https" or url.hostname not in (host, "api." + host) or url.username or url.password or url.port:
                raise ValueError("invalid provider link")
        for value in (self.name, self.language, self.quality, self.category, self.subclass, self.build):
            if value is not None and (not value.strip() or any(ord(c) < 32 for c in value)):
                raise ValueError("invalid metadata text")
        if not 0 < self.expires_at - self.fetched_at <= 300:
            raise ValueError("invalid cache lifetime")
        # Only reviewed local assets can ever reach <img>; no remote hotlinks.
        if self.icon_ref is not None and (self.icon_permission != "authorized" or not re.fullmatch(r"/assets/catalog/[a-zA-Z0-9_-]+\.(png|webp|jpg)", self.icon_ref)):
            raise ValueError("unauthorized icon")
        return self


class CatalogPage(BaseModel):
    contract: Literal["5d2-v1"] = "5d2-v1"
    items: list[CatalogItem] = Field(max_length=MAX_ITEMS)


def cache_path() -> Path:
    return Path(os.environ.get("ITEM_CATALOG_CACHE_DIR", str(ROOT / "data/imports/item-catalog")))


class CatalogCache:
    def __init__(self, path: Path, clock=time.time):
        self.path, self.clock = path, clock

    def read(self, item_id: int) -> CatalogItem | None:
        try:
            with (self.path / f"{item_id}.json").open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return None
            item = CatalogItem.model_validate_json(raw)
            if item.item_id == item_id and item.fetched_at <= self.clock() < item.expires_at:
                return item
        except (OSError, ValueError):
            pass
        return None

    def items(self) -> list[CatalogItem]:
        if not self.path.exists():
            return []
        result = []
        for i, file in enumerate(self.path.glob("*.json")):
            if i >= MAX_ITEMS:
                break
            if re.fullmatch(r"[1-9][0-9]{0,9}", file.stem):
                item = self.read(int(file.stem))
                if item:
                    result.append(item)
        return sorted(result, key=lambda item: item.item_id)

    def write(self, item: CatalogItem):
        self.path.mkdir(parents=True, exist_ok=True)
        destination = self.path / f"{item.item_id}.json"
        files = [file for file in self.path.glob("*.json") if re.fullmatch(r"[1-9][0-9]{0,9}", file.stem)]
        # Evict expired/invalid entries; never serve stale data offline.
        for file in files:
            if not self.read(int(file.stem)):
                file.unlink(missing_ok=True)
        if not destination.exists() and sum(file.exists() for file in files) >= MAX_ITEMS:
            raise CatalogError("Catalog cache is full (128 items).")
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(item.model_dump_json(), encoding="utf-8")
        temporary.replace(destination)

    @contextmanager
    def lock(self):
        self.path.mkdir(parents=True, exist_ok=True)
        path = self.path / "lookup.lock"
        try:
            stream = path.open("x")
        except FileExistsError:
            raise CatalogError("Another lookup is active; lookup.lock already exists.") from None
        try:
            with stream:
                yield
        finally:
            path.unlink(missing_ok=True)

    def cooldown(self, until=None):
        file = self.path / "retry-after.txt"
        if until is not None:
            self.path.mkdir(parents=True, exist_ok=True)
            file.write_text(str(until), encoding="ascii")
        else:
            try:
                with file.open(encoding="ascii") as stream:
                    value = float(stream.read(64))
                if not math.isfinite(value):
                    raise ValueError("invalid cooldown")
                if value > self.clock():
                    raise CatalogError("Provider cooldown active; honor Retry-After before a new lookup.")
            except FileNotFoundError:
                pass
            except ValueError:
                raise CatalogError("Invalid local provider cooldown; review retry-after.txt before lookup.") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_get(url):
    """One fixed-provider GET, 5s socket timeout, 10s read budget, 64KiB cap."""
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "WoWForeverCompanion/5D.2 (personal metadata lookup)"})
    started = time.monotonic()
    try:
        response = build_opener(NoRedirect()).open(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        status, headers = response.code, response.headers
        if status != 200:
            return status, headers, b""
        chunks, size = [], 0
        while True:
            chunk = response.read1(min(4096, MAX_BYTES + 1 - size))
            size += len(chunk)
            if size > MAX_BYTES or time.monotonic() - started > 10:
                raise CatalogError("Provider response exceeds resource budget.")
            if not chunk:
                return status, headers, b"".join(chunks)
            chunks.append(chunk)


def retry_until(value, now):
    try:
        if len(str(value)) > 128:
            return now + 60
        seconds = int(value)
        return now + max(0, seconds)
    except (ValueError, TypeError, OverflowError):
        try:
            return max(now, parsedate_to_datetime(value).timestamp())
        except (ValueError, TypeError, OverflowError):
            return now + 60


def cache_seconds(headers, now):
    directives = {}
    for directive in headers.get("Cache-Control", "").lower().split(","):
        key, _, value = directive.strip().partition("=")
        if key in directives:
            return 0
        directives[key] = value.strip('"')
    if any(key in directives for key in ("no-store", "no-cache")):
        return 0
    try:
        age = max(0, int(headers.get("Age", "0")))
        if headers.get("Date"):
            age = max(age, now - parsedate_to_datetime(headers["Date"]).timestamp())
        return max(0, min(300, int(directives["max-age"])) - age)
    except (KeyError, ValueError, TypeError, OverflowError):
        return 0


class AHledgerClient:
    def __init__(self, cache: CatalogCache, transport=http_get):
        self.cache, self.transport = cache, transport

    def lookup(self, item_id: int) -> CatalogItem | None:
        if type(item_id) is not int or not 1 <= item_id <= 2147483647:
            raise CatalogError("Invalid item ID.")
        with self.cache.lock():
            cached = self.cache.read(item_id)
            if cached and cached.provider == "ahledger":
                return cached
            self.cache.cooldown()
            now = self.cache.clock()
            self.cache.cooldown(now + 2)  # Pacing also survives separate CLI runs.
            url = f"https://api.ahledger.com/v1/items/{item_id}?game=forever"
            try:
                status, headers, body = self.transport(url)
            except (OSError, URLError, TimeoutError):
                raise CatalogError("Provider transport failed; no automatic retry.") from None
            if status in (429, 503) or (status >= 500 and headers.get("Retry-After")):
                self.cache.cooldown(retry_until(headers.get("Retry-After"), self.cache.clock()))
                raise CatalogError(f"Provider HTTP {status}; cooldown recorded, no retry.")
            if status == 404:
                return None
            if status != 200:
                raise CatalogError(f"Provider HTTP {status}; no retry.")
            if len(body) > MAX_BYTES or headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                raise CatalogError("Invalid provider content type or size.")
            ttl = cache_seconds(headers, now)
            if ttl <= 0:
                raise CatalogError("Response does not authorize a fresh local cache; nothing stored.")
            try:
                def unique(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("duplicate JSON key")
                        result[key] = value
                    return result
                data = json.loads(body, object_pairs_hook=unique)
                if type(data) is not dict or type(data.get("id")) is not int or data["id"] != item_id:
                    raise ValueError("contradictory ID")
                if data.get("game", "forever") != "forever":
                    raise ValueError("contradictory product")
                attribution = data.get("attribution") or {}
                item = CatalogItem(item_id=item_id, name=data["name"], quality=data.get("quality"),
                    category=data.get("itemClass"), subclass=data.get("itemSubclass"), provider="ahledger",
                    source_url=url, attribution_url=attribution.get("url", "https://ahledger.com"),
                    fetched_at=now, expires_at=now + ttl)
                # Locale/build fields have no verified contract. Icon permissions remain pending.
            except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
                raise CatalogError("Incomplete or contradictory provider JSON.") from None
            self.cache.write(item)
            return item
