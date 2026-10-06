from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from app.db.connection import connect
from app.ingestion.contracts import ImportResult, NormalizedSnapshot


@dataclass(frozen=True)
class SnapshotImportInput:
    snapshot: NormalizedSnapshot
    source_hash: str
    raw_reference: str | None = None


class IngestionService:
    def import_snapshot(self, import_input: SnapshotImportInput) -> ImportResult:
        try:
            return self._import_snapshot(import_input)
        except psycopg.Error as error:
            self._record_failed_import(import_input, str(error))
            raise

    def _import_snapshot(self, import_input: SnapshotImportInput) -> ImportResult:
        snapshot = import_input.snapshot
        raw_reference = import_input.raw_reference or snapshot.raw_reference
        imported_at = snapshot.imported_at

        with connect() as connection:
            connection.row_factory = dict_row
            with connection.transaction():
                realm_id = self._get_or_create_realm(
                    connection,
                    name=snapshot.realm,
                    region=snapshot.region,
                )

                duplicate_snapshot_id = self._find_duplicate_snapshot(
                    connection,
                    realm_id=realm_id,
                    source_type=snapshot.source_type,
                    captured_at=snapshot.captured_at,
                    source_hash=import_input.source_hash,
                )
                snapshot_id = None
                if duplicate_snapshot_id is None:
                    snapshot_id = self._create_snapshot(
                        connection,
                        realm_id=realm_id,
                        source_type=snapshot.source_type,
                        source_version=snapshot.source_version,
                        captured_at=snapshot.captured_at,
                        imported_at=imported_at,
                        source_hash=import_input.source_hash,
                        raw_reference=raw_reference,
                    )
                    if snapshot_id is None:
                        # A competing insert has committed; use a fresh READ COMMITTED lookup.
                        duplicate_snapshot_id = self._find_duplicate_snapshot(
                            connection,
                            realm_id=realm_id,
                            source_type=snapshot.source_type,
                            captured_at=snapshot.captured_at,
                            source_hash=import_input.source_hash,
                        )
                if duplicate_snapshot_id is not None:
                    self._record_import_run(
                        connection,
                        source_type=snapshot.source_type,
                        source_version=snapshot.source_version,
                        raw_reference=raw_reference,
                        source_hash=import_input.source_hash,
                        status="duplicate",
                        snapshot_id=duplicate_snapshot_id,
                        items_seen=len(snapshot.items),
                        items_imported=0,
                    )
                    return ImportResult(
                        status="duplicate",
                        snapshot_id=duplicate_snapshot_id,
                        items_seen=len(snapshot.items),
                        items_imported=0,
                        message="Snapshot already imported.",
                    )

                if snapshot_id is None:
                    raise psycopg.IntegrityError("Conflicting snapshot could not be recovered")

                for item in snapshot.items:
                    item_id = self._upsert_item(
                        connection,
                        external_item_id=item.external_item_id,
                        name=item.name,
                        quality=item.quality.value,
                    )
                    self._insert_snapshot_item(
                        connection,
                        snapshot_id=snapshot_id,
                        item_id=item_id,
                        min_buyout=item.min_buyout,
                        avg_buyout=item.avg_buyout,
                        max_buyout=item.max_buyout,
                        quantity_total=item.quantity_total,
                        auction_count=item.auction_count,
                    )

                self._record_import_run(
                    connection,
                    source_type=snapshot.source_type,
                    source_version=snapshot.source_version,
                    raw_reference=raw_reference,
                    source_hash=import_input.source_hash,
                    status="completed",
                    snapshot_id=snapshot_id,
                    items_seen=len(snapshot.items),
                    items_imported=len(snapshot.items),
                )

                return ImportResult(
                    status="completed",
                    snapshot_id=snapshot_id,
                    items_seen=len(snapshot.items),
                    items_imported=len(snapshot.items),
                    message="Snapshot imported.",
                )

    def _record_failed_import(self, import_input: SnapshotImportInput, error_message: str) -> None:
        snapshot = import_input.snapshot
        raw_reference = import_input.raw_reference or snapshot.raw_reference
        try:
            with connect() as connection:
                with connection.transaction():
                    self._record_import_run(
                        connection,
                        source_type=snapshot.source_type,
                        source_version=snapshot.source_version,
                        raw_reference=raw_reference,
                        source_hash=import_input.source_hash,
                        status="failed",
                        snapshot_id=None,
                        items_seen=len(snapshot.items),
                        items_imported=0,
                        error_message=error_message,
                    )
        except psycopg.Error:
            pass

    def _get_or_create_realm(
        self,
        connection: psycopg.Connection,
        *,
        name: str,
        region: str | None,
    ) -> int:
        connection.execute(
            """
            INSERT INTO realms (name, region)
            VALUES (%s, %s)
            ON CONFLICT (name, (COALESCE(region, ''))) DO NOTHING
            """,
            (name, region),
        )
        row = connection.execute(
            """
            SELECT id
            FROM realms
            WHERE name = %s
              AND COALESCE(region, '') = COALESCE(%s, '')
            """,
            (name, region),
        ).fetchone()
        if row is None:
            raise psycopg.IntegrityError("Realm could not be recovered")
        return int(row["id"])

    def _find_duplicate_snapshot(
        self,
        connection: psycopg.Connection,
        *,
        realm_id: int,
        source_type: str,
        captured_at,
        source_hash: str,
    ) -> int | None:
        row = connection.execute(
            """
            SELECT id
            FROM auction_snapshots
            WHERE source_hash = %s
               OR (realm_id = %s AND source_type = %s AND captured_at = %s)
            ORDER BY id
            LIMIT 1
            """,
            (source_hash, realm_id, source_type, captured_at),
        ).fetchone()
        if row is None:
            return None
        return int(row["id"])

    def _create_snapshot(
        self,
        connection: psycopg.Connection,
        *,
        realm_id: int,
        source_type: str,
        source_version: str,
        captured_at,
        imported_at,
        source_hash: str,
        raw_reference: str | None,
    ) -> int | None:
        row = connection.execute(
            """
            INSERT INTO auction_snapshots (
                realm_id,
                source_type,
                source_version,
                captured_at,
                imported_at,
                source_hash,
                raw_reference
            )
            VALUES (%s, %s, %s, %s, COALESCE(%s, now()), %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                realm_id,
                source_type,
                source_version,
                captured_at,
                imported_at,
                source_hash,
                raw_reference,
            ),
        ).fetchone()
        return int(row["id"]) if row is not None else None

    def _upsert_item(
        self,
        connection: psycopg.Connection,
        *,
        external_item_id: str,
        name: str,
        quality: str,
    ) -> int:
        row = connection.execute(
            """
            INSERT INTO items (external_item_id, name, quality)
            VALUES (%s, %s, %s)
            ON CONFLICT (external_item_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                quality = EXCLUDED.quality,
                updated_at = now()
            RETURNING id
            """,
            (external_item_id, name, quality),
        ).fetchone()
        return int(row["id"])

    def _insert_snapshot_item(
        self,
        connection: psycopg.Connection,
        *,
        snapshot_id: int,
        item_id: int,
        min_buyout: int,
        avg_buyout: int,
        max_buyout: int,
        quantity_total: int,
        auction_count: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO auction_snapshot_items (
                snapshot_id,
                item_id,
                min_buyout,
                avg_buyout,
                max_buyout,
                quantity_total,
                auction_count
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                snapshot_id,
                item_id,
                min_buyout,
                avg_buyout,
                max_buyout,
                quantity_total,
                auction_count,
            ),
        )

    def _record_import_run(
        self,
        connection: psycopg.Connection,
        *,
        source_type: str,
        source_version: str | None,
        raw_reference: str | None,
        source_hash: str | None,
        status: str,
        snapshot_id: int | None,
        items_seen: int,
        items_imported: int,
        error_message: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO import_runs (
                source_type,
                source_version,
                raw_reference,
                source_hash,
                status,
                snapshot_id,
                items_seen,
                items_imported,
                error_message,
                finished_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            """,
            (
                source_type,
                source_version,
                raw_reference,
                source_hash,
                status,
                snapshot_id,
                items_seen,
                items_imported,
                error_message,
            ),
        )
