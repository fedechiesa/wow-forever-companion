import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# partial_service -> connection -> config instantiates Settings during import.
# Keep that entire boundary protected without changing application-wide settings.
_INITIALIZATION_FAILED = False
try:
    from app.ingestion.adapters.auctionator import AuctionatorAdapter
    from app.ingestion.partial_service import PartialIngestionService
    from app.core.config import settings
    from app.db.trial import TrialDatabase, TrialSafetyError
except Exception:
    _INITIALIZATION_FAILED = True


def main(argv=None):
    if _INITIALIZATION_FAILED:
        print("CLI initialization failed; check configuration privately. Details withheld.", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description="Import literal Auctionator 340 SavedVariables")
    parser.add_argument("file", type=Path, nargs="?")
    parser.add_argument("--source-id", help="Stable account/export identity and clock context")
    parser.add_argument("--region", help="Explicit source region; not present in SavedVariables")
    parser.add_argument("--dataset", choices=["real", "simulated"])
    parser.add_argument("--market-map", type=Path, help="JSON mapping raw market keys to PvE/PvP/HC/RP")
    parser.add_argument("--scan-day-zero", help="Verified ISO timestamp of client SCAN_DAY_0; otherwise unknown")
    parser.add_argument("--allow-libcbor", action="store_true", help="Explicitly select inspected LibCBOR encoding")
    parser.add_argument("--trial", action="store_true", help="Require a verified, isolated PostgreSQL target")
    parser.add_argument("--database-url-env", help="Name of environment variable holding the private target DSN")
    parser.add_argument("--expected-database", help="Exact isolated database name, ending in _test")
    parser.add_argument("--check-target", action="store_true", help="Trial identity check only; no file parsing or writes")
    args = parser.parse_args(argv)
    if args.trial:
        if not args.database_url_env or not args.expected_database:
            parser.error("--trial requires --database-url-env and --expected-database")
        if not args.database_url_env.isidentifier():
            parser.error("--database-url-env must name an environment variable, not contain a DSN")
    elif args.database_url_env or args.expected_database or args.check_target:
        parser.error("Target selection and --check-target require --trial")
    if not args.check_target and (args.file is None or not args.source_id or not args.region or not args.dataset):
        parser.error("file, --source-id, --region and --dataset are required for import")
    try:
        if not args.trial:
            print(PartialIngestionService().import_batch(load(args)).model_dump_json())
            return 0
        with TrialDatabase(os.environ.get(args.database_url_env), settings.database_url,
                           args.expected_database) as target:
            # Safe identity only, never a DSN, user, password, or driver exception.
            print(json.dumps({"trial_target": {
                "database": target.identity.database,
                "database_oid": target.identity.database_oid,
                "system_identifier": target.identity.system_identifier,
            }}))
            if not args.check_target:
                result = load(args)
                service = PartialIngestionService(target.connection, redact_errors=True)
                print(service.import_batch(result).model_dump_json())
        return 0
    except TrialSafetyError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("Import failed; details withheld. Preserve the input and verify the selected database privately.", file=sys.stderr)
        return 1


def load(args):
    mapping = json.loads(args.market_map.read_text(encoding="utf-8")) if args.market_map else None
    return AuctionatorAdapter().load(
        args.file, source_id=args.source_id, region=args.region,
        dataset=args.dataset, market_mapping=mapping,
        scan_day_zero=args.scan_day_zero, allow_libcbor=args.allow_libcbor,
    )


if __name__ == "__main__":
    sys.exit(main())
