"""Manual-only archive ingestion. Offline preflight never imports DB settings."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.local_capture.preflight import PreflightError, preflight_archive, preflight_summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "ingest"])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--capture-id", required=True, help="Full SHA-256 of an already published capture")
    parser.add_argument("--context-file", type=Path, required=True, help="Private verified-local-capture-v1 JSON")
    parser.add_argument("--database-url-env", help="Environment variable containing the isolated target DSN")
    parser.add_argument("--expected-database", help="Exact isolated database name ending in _test")
    args = parser.parse_args(argv)
    if args.action == "ingest":
        if not args.database_url_env or not args.database_url_env.isidentifier() or not args.expected_database:
            parser.error("ingest requires --database-url-env (variable name) and --expected-database")
    elif args.database_url_env or args.expected_database:
        parser.error("preflight is offline; target selection belongs to ingest")
    try:
        result = preflight_archive(args.archive, args.capture_id, args.context_file)
        if args.action == "preflight":
            print(json.dumps(preflight_summary(result)))
            return 0
        # Deliberately after complete offline validation; malformed settings and
        # driver exceptions must never expose DSNs or private input in a traceback.
        from app.core.config import settings
        from app.db.trial import TrialDatabase
        from app.ingestion.partial_service import PartialIngestionService
        with TrialDatabase(os.environ.get(args.database_url_env), settings.database_url,
                           args.expected_database) as target:
            imported = PartialIngestionService(trial_target=target).import_batch(result)
            print(imported.model_dump_json())
        return 0
    except PreflightError as error:
        print(json.dumps(dict(status="blocked", reason=str(error))), file=sys.stderr)
        return 1
    except Exception:
        print('Manual import blocked or failed; verify context, prepared schema 006 and isolated target privately. Details withheld.', file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
