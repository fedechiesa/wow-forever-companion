"""Parameterized SQL only. The service supplies a READ ONLY snapshot transaction."""
from dataclasses import dataclass

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.ingestion.native_exports import NativeMarketShape
from app.ingestion.partial_contracts import MAX_OBSERVATIONS
from app.market.contracts import DiscoveryQuery, SeriesContext, SeriesSelector, WindowSpec
from app.market.errors import SeriesIntegrityError, SeriesNotFound


@dataclass
class SelectionData:
    context: SeriesContext
    item_id: int | None
    market_first_day: int | None
    market_last_day: int | None
    item_first_day: int | None
    item_last_day: int | None
    undated_count: int
    availability_presence: str
    header: dict | None = None
    original_item_key: str | None = None


class MarketRepository:
    def __init__(self, connection):
        self.connection = connection

    def market(self, market_id):
        row = self.connection.execute("SELECT * FROM partial_markets WHERE id=%s", (market_id,)).fetchone()
        if row is None:
            raise SeriesNotFound("Partial market not found")
        return row

    @staticmethod
    def _params(selector):
        return (selector.market_id, selector.source_id, selector.source_type, selector.temporal_basis)

    @staticmethod
    def _context(selector, market, item, mode):
        try:
            return SeriesContext(**selector.model_dump(), market_key=market["market_key"], ruleset=market["ruleset"],
                                 region=market["region"], dataset=market["dataset"],
                                 external_item_id=item["external_item_id"], key_kind=item["key_kind"],
                                 value_semantics="accumulated_extreme" if mode == "accumulated" else "export_projection")
        except ValidationError as error:
            raise SeriesIntegrityError("incompatible persisted series context") from error

    def selection(self, selector: SeriesSelector) -> SelectionData:
        market = self.market(selector.market_id)
        if (selector.source_type == "simulated") != (market["dataset"] == "simulated"):
            raise SeriesNotFound("Source type is not available in this market dataset")
        return (self._accumulated(selector, market) if selector.series_mode == "accumulated"
                else self._export(selector, market))

    def _accumulated(self, selector, market):
        return self._accumulated_many([selector], market)[0]

    def _accumulated_many(self, selectors, market):
        if not selectors:
            return []
        if any(s.market_id != market["id"] or s.item_key != selectors[0].item_key for s in selectors):
            raise SeriesIntegrityError("mixed market or item in accumulated batch")
        items = {row["item_key"]: row for row in self.connection.execute(
            "SELECT * FROM partial_items WHERE item_key=ANY(%s::text[])",
            (list({s.item_key for s in selectors}),),
        ).fetchall()}
        expected = []
        for ordinal, selector in enumerate(selectors):
            if selector.item_key not in items:
                raise SeriesNotFound("Partial item not found")
            if (selector.source_type == "simulated") != (market["dataset"] == "simulated"):
                raise SeriesIntegrityError("accumulated source and market dataset disagree")
            expected.append(dict(ordinal=ordinal, source_id=selector.source_id, source_type=selector.source_type,
                                 temporal_basis=selector.temporal_basis, item_id=items[selector.item_key]["id"]))
        # Both import joins target primary keys: they cannot multiply observations.
        rows = self.connection.execute(
            """WITH requested AS (
                 SELECT * FROM jsonb_to_recordset(%s::jsonb) AS q(
                   ordinal integer,source_id text,source_type text,temporal_basis text,item_id bigint))
               SELECT q.ordinal,count(o.id) AS row_count,
                 min(o.scan_day) AS market_first_day,max(o.scan_day) AS market_last_day,
                 min(o.scan_day) FILTER (WHERE o.item_id=q.item_id) AS item_first_day,
                 max(o.scan_day) FILTER (WHERE o.item_id=q.item_id) AS item_last_day,
                 count(o.id) FILTER (WHERE o.item_id=q.item_id AND o.scan_day IS NULL) AS undated_count,
                 bool_or(o.id IS NOT NULL AND (
                   ROW(f.source_id,f.source_type,f.temporal_basis,f.region,f.dataset)
                     IS DISTINCT FROM ROW(o.source_id,o.source_type,o.temporal_basis,%s::text,%s::text)
                   OR ROW(l.source_id,l.source_type,l.temporal_basis,l.region,l.dataset)
                     IS DISTINCT FROM ROW(o.source_id,o.source_type,o.temporal_basis,%s::text,%s::text)
                   OR f.source_version<>'340' OR l.source_version<>'340'
                   OR f.database_version<>8 OR l.database_version<>8
                   OR f.status='failed' OR l.status='failed')) AS invalid_provenance
               FROM requested q LEFT JOIN partial_observations o
                 ON o.market_id=%s AND o.source_id=q.source_id AND o.source_type=q.source_type
                   AND o.temporal_basis=q.temporal_basis
               LEFT JOIN partial_import_runs f ON f.id=o.first_import_id
               LEFT JOIN partial_import_runs l ON l.id=o.last_import_id
               GROUP BY q.ordinal ORDER BY q.ordinal""",
            (Jsonb(expected), market["region"], market["dataset"], market["region"], market["dataset"], market["id"]),
        ).fetchall()
        result = []
        for selector, info in zip(selectors, rows):
            if not info["row_count"]:
                raise SeriesNotFound("Accumulated source/time basis not found in this market")
            if info["invalid_provenance"]:
                raise SeriesIntegrityError("accumulated import provenance disagrees with series context")
            item = items[selector.item_key]
            result.append(SelectionData(self._context(selector, market, item, "accumulated"), item["id"],
                                        info["market_first_day"], info["market_last_day"],
                                        info["item_first_day"], info["item_last_day"], info["undated_count"], "unknown"))
        return result

    def _export(self, selector, market):
        return self._exports_many([selector], market)[0]

    @staticmethod
    def _manifest_markets(header):
        """Validate decoded structure before interpreting keys or field presence."""
        try:
            manifest = header["structure_manifest"]
            if (not isinstance(manifest, dict) or set(manifest) != {"version", "markets"}
                    or type(manifest.get("version")) is not int or manifest["version"] != 1):
                raise ValueError("unsupported manifest")
            markets = manifest["markets"]
            if not isinstance(markets, list) or len(markets) > MAX_OBSERVATIONS:
                raise ValueError("markets must be a bounded array")
            size = len(markets)
            for entry in markets:
                if not isinstance(entry, dict) or not isinstance(entry.get("items"), list):
                    raise ValueError("each market must contain an items array")
                size += len(entry["items"])
                if size > MAX_OBSERVATIONS:
                    raise ValueError("oversized manifest structure")
            shapes = [NativeMarketShape.model_validate(m) for m in markets]
            if len({m.market_key for m in shapes}) != len(shapes):
                raise ValueError("duplicate manifest markets")
            return {m.market_key: m for m in shapes}
        except (ValidationError, KeyError, TypeError, ValueError, AttributeError) as error:
            raise SeriesIntegrityError("invalid native structure manifest") from error

    def _exports_many(self, selectors, market):
        if not selectors:
            return []
        if any(s.market_id != market["id"] or s.item_key != selectors[0].item_key for s in selectors):
            raise SeriesIntegrityError("mixed market or item in export batch")
        ids = [s.export_id for s in selectors]
        headers = {row["id"]: row for row in self.connection.execute(
            """SELECT e.*,r.imported_at AS first_received_at,
                 (r.id IS NULL OR link.export_id IS DISTINCT FROM e.id OR r.status='failed'
                   OR ROW(r.source_id,r.source_type,r.temporal_basis,r.region,r.dataset,r.source_version,r.database_version)
                     IS DISTINCT FROM ROW(e.source_id,e.source_type,e.temporal_basis,e.region,e.dataset,e.source_version,e.database_version))
                   AS invalid_reception
               FROM partial_exports e LEFT JOIN partial_import_runs r ON r.id=e.first_import_id
               LEFT JOIN partial_export_imports link ON link.import_id=e.first_import_id
               WHERE e.id=ANY(%s::bigint[]) AND e.sealed""", (ids,),
        ).fetchall()}
        # Aggregate copied market identities and the market axis once per export.
        market_info = {row["export_id"]: row for row in self.connection.execute(
            """SELECT export_id,
                 jsonb_agg(DISTINCT jsonb_build_object('market_key',market_key,'ruleset',ruleset)) AS copies,
                 bool_or(item_key=%s) AS selected_item_present,
                 min(scan_day) FILTER (WHERE native_field='h') AS first_day,
                 max(scan_day) FILTER (WHERE native_field='h') AS last_day
               FROM partial_export_facts WHERE export_id=ANY(%s::bigint[]) AND market_id=%s GROUP BY export_id""",
            (selectors[0].item_key, ids, market["id"]),
        ).fetchall()}
        structures, expected = {}, []
        for selector in selectors:
            header = headers.get(selector.export_id)
            if header is None or tuple(header[k] for k in ("source_id", "source_type", "temporal_basis", "region", "dataset")) != (
                selector.source_id, selector.source_type, selector.temporal_basis, market["region"], market["dataset"]
            ):
                raise SeriesNotFound("Sealed export not found for selected context")
            if (header["source_version"], header["database_version"], header["canonical_version"]) != ("340", 8, 1):
                raise SeriesIntegrityError("unsupported export version")
            if header["invalid_reception"]:
                raise SeriesIntegrityError("export reception context disagrees")
            copies = market_info.get(header["id"], {}).get("copies", [])
            if len(copies) > 1:
                raise SeriesIntegrityError("conflicting native market identities")
            market_key = copies[0]["market_key"] if copies else market["market_key"]
            shapes = self._manifest_markets(header)
            shape = shapes.get(market_key)
            if shape is None:
                if copies:
                    raise SeriesIntegrityError("native market facts are absent from manifest")
                raise SeriesNotFound("Market is absent from this export")
            if copies and shape.ruleset != copies[0]["ruleset"]:
                raise SeriesIntegrityError("manifest and market facts disagree")
            item = next((i for i in shape.items if i.item_key == selector.item_key), None)
            if item is None:
                if market_info.get(header["id"], {}).get("selected_item_present"):
                    raise SeriesIntegrityError("native item facts are absent from manifest")
                raise SeriesNotFound("Item is absent from this export")
            structures[header["id"]] = (shape, item)
            expected.append(dict(export_id=header["id"], market_key=shape.market_key, ruleset=shape.ruleset,
                                 item_key=item.item_key, external_item_id=item.external_item_id,
                                 key_kind=item.key_kind, original_item_key=item.original_item_key))
        infos = {row["export_id"]: row for row in self.connection.execute(
            """WITH requested AS (
                 SELECT * FROM jsonb_to_recordset(%s::jsonb) AS q(export_id bigint,market_key text,ruleset text,
                   item_key text,external_item_id text,key_kind text,original_item_key text))
               SELECT q.export_id,min(f.scan_day) AS first_day,max(f.scan_day) AS last_day,
                 count(f.id) FILTER (WHERE f.scan_day IS NULL) AS undated_count,
                 array_agg(DISTINCT f.native_field) FILTER (WHERE f.id IS NOT NULL) AS populated_fields,
                 array_agg(DISTINCT f.item_id) FILTER (WHERE f.id IS NOT NULL) AS item_ids,
                 bool_or(f.id IS NOT NULL AND (f.market_key<>q.market_key OR f.ruleset<>q.ruleset
                   OR f.external_item_id<>q.external_item_id OR f.key_kind<>q.key_kind
                   OR f.original_item_key<>q.original_item_key
                   OR (f.native_field IN ('l','a') AND (h.id IS NULL OR f.original_day_key<>h.original_day_key))
                   OR (f.native_field='l' AND f.value>h.value))) AS invalid_facts
               FROM requested q LEFT JOIN partial_export_facts f
                 ON f.export_id=q.export_id AND f.market_id=%s AND f.item_key=q.item_key
               LEFT JOIN partial_export_facts h
                 ON h.export_id=f.export_id AND h.market_id=f.market_id AND h.item_id=f.item_id
                 AND h.scan_day=f.scan_day AND h.native_field='h'
               GROUP BY q.export_id""", (Jsonb(expected), market["id"]),
        ).fetchall()}
        result = []
        for selector in selectors:
            header = headers[selector.export_id]
            shape, item = structures[header["id"]]
            info = infos[header["id"]]
            populated = set(info["populated_fields"] or [])
            if not populated <= set(item.fields_present) or (("m" in populated) != ("m" in item.fields_present)):
                raise SeriesIntegrityError("native field presence disagrees with manifest")
            if len(info["item_ids"] or []) > 1:
                raise SeriesIntegrityError("conflicting native item identities")
            if info["invalid_facts"]:
                raise SeriesIntegrityError("native item facts disagree with their structure or daily h")
            bounds = market_info.get(header["id"], {})
            copied_market = {**market, "market_key": shape.market_key, "ruleset": shape.ruleset}
            result.append(SelectionData(self._context(selector, copied_market, item.model_dump(), "export"),
                                        (info["item_ids"] or [None])[0], bounds.get("first_day"), bounds.get("last_day"),
                                        info["first_day"], info["last_day"], info["undated_count"],
                                        "present" if "a" in item.fields_present else "absent", header, item.original_item_key))
        return result

    def observed_days(self, data: SelectionData, spec: WindowSpec) -> list[int]:
        selector = data.context
        if spec.window_type == "observed_buckets":
            end = spec.end_day if spec.end_day is not None else data.market_last_day
            start = 0
            limit = spec.size
        elif spec.window_type == "index_range":
            start, end, limit = spec.start_day, spec.end_day, 366
        else:
            end = spec.end_day if spec.end_day is not None else data.market_last_day
            start, limit = max(0, end - spec.days + 1) if end is not None else 0, 366
        if end is None:
            return []
        if selector.series_mode == "accumulated":
            rows = self.connection.execute(
                """SELECT DISTINCT scan_day FROM partial_observations
                   WHERE market_id=%s AND source_id=%s AND source_type=%s AND temporal_basis=%s
                     AND scan_day BETWEEN %s AND %s ORDER BY scan_day DESC LIMIT %s""",
                (*self._params(selector), start, end, limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """SELECT DISTINCT scan_day FROM partial_export_facts WHERE export_id=%s AND market_id=%s
                   AND native_field='h' AND scan_day BETWEEN %s AND %s ORDER BY scan_day DESC LIMIT %s""",
                (selector.export_id, selector.market_id, start, end, limit),
            ).fetchall()
        return sorted(row["scan_day"] for row in rows)

    def daily_rows(self, data: SelectionData, positions: list[int]) -> list[dict]:
        selector = data.context
        if not positions:
            return []
        if selector.series_mode == "accumulated":
            return self.connection.execute(
                """SELECT o.*,i.item_key FROM partial_observations o JOIN partial_items i ON i.id=o.item_id
                   WHERE o.market_id=%s AND o.source_id=%s AND o.source_type=%s AND o.temporal_basis=%s
                     AND o.item_id=%s AND o.scan_day=ANY(%s::integer[]) ORDER BY o.scan_day,o.statistic""",
                (*self._params(selector), data.item_id, positions),
            ).fetchall()
        return self.connection.execute(
            """SELECT * FROM partial_export_facts WHERE export_id=%s AND market_id=%s AND item_key=%s
               AND scan_day=ANY(%s::integer[]) ORDER BY scan_day,native_field""",
            (selector.export_id, selector.market_id, selector.item_key, positions),
        ).fetchall()

    def discover(self, query: DiscoveryQuery) -> tuple[list[SelectionData], bool]:
        market = self.market(query.market_id)
        rows = self.connection.execute(
            """WITH contexts AS (
                 SELECT DISTINCT o.source_id,o.source_type,o.temporal_basis,'accumulated'::text AS series_mode,
                        NULL::bigint AS export_id
                 FROM partial_observations o JOIN partial_items i ON i.id=o.item_id
                 WHERE o.market_id=%s AND i.item_key=%s
                 UNION ALL
                 SELECT e.source_id,e.source_type,e.temporal_basis,'export',e.id
                 FROM partial_exports e WHERE e.sealed AND e.region=%s AND e.dataset=%s AND (
                   EXISTS (SELECT 1 FROM partial_export_facts f
                           WHERE f.export_id=e.id AND f.market_id=%s AND f.item_key=%s)
                   OR EXISTS (
                     SELECT 1 FROM jsonb_array_elements(CASE
                       WHEN jsonb_typeof(e.structure_manifest->'markets')='array'
                       THEN e.structure_manifest->'markets' ELSE '[]'::jsonb END) m
                     CROSS JOIN LATERAL jsonb_array_elements(CASE
                       WHEN jsonb_typeof(m->'items')='array' THEN m->'items' ELSE '[]'::jsonb END) i
                     WHERE m->>'market_key'=%s AND i->>'item_key'=%s)))
               SELECT * FROM contexts WHERE (%s::text IS NULL OR series_mode=%s)
               ORDER BY series_mode,source_id,source_type,temporal_basis,export_id
               LIMIT %s OFFSET %s""",
            (query.market_id, query.item_key, market["region"], market["dataset"], query.market_id, query.item_key,
             market["market_key"], query.item_key, query.series_mode, query.series_mode, query.limit + 1, query.offset),
        ).fetchall()
        try:
            selectors = [SeriesSelector(market_id=query.market_id, item_key=query.item_key, **row)
                         for row in rows[:query.limit]]
            accumulated = [s for s in selectors if s.series_mode == "accumulated"]
            exports = [s for s in selectors if s.series_mode == "export"]
            accumulated_data = self._accumulated_many(accumulated, market)
            export_data = self._exports_many(exports, market)

            def identity(s):
                return s.series_mode, s.source_id, s.source_type, s.temporal_basis, s.export_id

            data = {identity(s): d for s, d in zip(accumulated + exports, accumulated_data + export_data)}
            selected = [data[identity(s)] for s in selectors]
        except ValidationError as error:
            raise SeriesIntegrityError("invalid discovered source context") from error
        return selected, len(rows) > query.limit
