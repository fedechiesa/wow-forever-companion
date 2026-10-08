from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from app.ingestion.auctionator_keys import normalize_item_key
from app.ingestion.partial_contracts import PartialBatch, PartialObservation, Ruleset, MAX_OBSERVATIONS
from app.ingestion.native_exports import NativeExportEvidence, NativeFact, NativeItemShape, NativeMarketShape
from app.ingestion.saved_variables import CBORReader, FormatError, LuaReader, MAX_BYTES, ParseBudget, strip_lua_prefix


@dataclass(frozen=True)
class PartialAdapterResult:
    batch: PartialBatch
    source_hash: str
    raw_reference: str | None = None
    native: NativeExportEvidence | None = None

    @property
    def evidence_hash(self):
        payload = self.batch.model_dump(mode="json")
        payload["observations"] = sorted(payload["observations"], key=lambda o: (
            o["market_key"], o["item_key"], -1 if o["scan_day"] is None else o["scan_day"], o["statistic"],
        ))
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def table(value):
    if not isinstance(value, dict):
        raise FormatError("expected Auctionator table")
    return value


def text(value):
    if not isinstance(value, bytes):
        raise FormatError("expected string key")
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FormatError("invalid UTF-8 key") from error


class AuctionatorAdapter:
    """Transforms verified v8 evidence without a database dependency.

    Region/source identity and legacy ruleset mappings are caller context.
    Serialized input requires explicit LibCBOR selection; native codec is pending.
    """
    def load(self, source: Path, **context) -> PartialAdapterResult:
        with Path(source).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        return self.load_bytes(raw, raw_reference=str(source), **context)

    def load_bytes(self, raw: bytes, *, source_id: str, region: str,
                   dataset="real", market_mapping: dict[str, Ruleset] | None = None,
                   scan_day_zero=None, allow_libcbor=False,
                   raw_reference=None) -> PartialAdapterResult:
        marker_input = strip_lua_prefix(raw)
        if marker_input.startswith(b"-- SIMULATED prices and availability;") and dataset != "simulated":
            raise FormatError("generated simulation must be imported with dataset=simulated")
        budget = ParseBudget()
        variables = LuaReader(raw, budget=budget).parse()
        db = table(variables.get("AUCTIONATOR_PRICE_DATABASE"))
        if type(db.get(b"__dbversion")) is not int or db[b"__dbversion"] != 8:
            raise FormatError("only verified price database version 8 is supported")
        observations = []
        facts, shapes, formats = [], [], set()
        structure_count = 0

        def reserve_structure():
            nonlocal structure_count
            if structure_count >= MAX_OBSERVATIONS:
                raise FormatError("native structure construction limit exceeded")
            structure_count += 1

        def decode(value):
            if isinstance(value, bytes):
                if not allow_libcbor:
                    raise FormatError("serialized data requires explicit allow_libcbor; native CBOR is unverified")
                formats.add("libcbor")
                return table(CBORReader(value, budget=budget).parse())
            formats.add("lua_tables")
            return table(value)

        mapping = market_mapping or {}
        if set(mapping) & {"PvE", "PvP", "HC", "RP"}:
            raise FormatError("mappings may only resolve external market keys")
        for raw_market, data in db.items():
            if raw_market == b"__dbversion":
                continue
            market = text(raw_market)
            ruleset = mapping.get(market)
            if ruleset is None and market in ("PvE", "PvP", "HC", "RP"):
                ruleset = market
            if ruleset is None:
                raise FormatError(f"market {market!r} needs an explicit ruleset mapping")
            reserve_structure()
            realm = decode(data)
            item_shapes = []
            version = realm.get(b"version")
            if version is not None and (type(version) is not int or version != 2):
                raise FormatError("unsupported realm database version")
            for raw_key, raw_item in realm.items():
                if raw_key == b"version":
                    continue
                reserve_structure()
                original_key = text(raw_key)
                key, item_id, kind = normalize_item_key(original_key)
                item = decode(raw_item)
                if set(item) - {b"m", b"l", b"h", b"a"}:
                    raise FormatError("unsupported item fields or legacy pending conversion")
                highs, lows = table(item.get(b"h")), table(item.get(b"l"))
                available = table(item.get(b"a", {}))
                if set(lows) - set(highs) or set(available) - set(highs):
                    raise FormatError("orphan historical day without h evidence")

                def append(statistic, value, day=None, native_field=None, original_day=None):
                    if len(observations) >= MAX_OBSERVATIONS:
                        raise FormatError("observation construction limit exceeded")
                    if type(value) is not int:
                        raise FormatError("non-integer prices/availability are unsupported; no rounding is performed")
                    observations.append(PartialObservation(
                        market_key=market, ruleset=ruleset, item_key=key,
                        external_item_id=item_id, key_kind=kind,
                        statistic=statistic, value=value, scan_day=day,
                    ))
                    if native_field is not None:
                        if len(facts) >= MAX_OBSERVATIONS:
                            raise FormatError("native fact construction limit exceeded")
                        facts.append(NativeFact(
                            **observations[-1].model_dump(), native_field=native_field,
                            original_item_key=original_key, original_day_key=original_day,
                        ))

                for raw_day, high in highs.items():
                    day_text = text(raw_day)
                    if not day_text.isascii() or not day_text.isdigit() or len(day_text) > 10:
                        raise FormatError("invalid scan day index")
                    day = int(day_text)
                    append("daily_minimum", lows.get(raw_day, high), day,
                           "l" if raw_day in lows else None, day_text)
                    append("daily_highest_minimum", high, day, "h", day_text)
                    if raw_day in available:
                        append("daily_max_available", available[raw_day], day, "a", day_text)
                if b"m" in item:
                    append("last_minimum", item[b"m"], native_field="m")
                item_shapes.append(NativeItemShape(
                    original_item_key=original_key, item_key=key, external_item_id=item_id,
                    key_kind=kind, fields_present=sorted(text(field) for field in item),
                ))
            shapes.append(NativeMarketShape(market_key=market, ruleset=ruleset,
                                            realm_version=version, items=item_shapes))
        batch = PartialBatch(
            source_type="simulated" if dataset == "simulated" else "auctionator",
            source_id=source_id, dataset=dataset, region=region,
            scan_day_zero=scan_day_zero, observations=observations,
        )
        native = NativeExportEvidence(markets=shapes, facts=facts,
                                      input_format=next(iter(formats)) if len(formats) == 1 else "mixed")
        return PartialAdapterResult(batch, sha256(raw).hexdigest(), raw_reference, native)
