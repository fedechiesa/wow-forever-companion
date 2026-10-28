"""Explicit lookup of at most four item IDs; never connects to PostgreSQL."""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.catalog import AHledgerClient, CatalogCache, CatalogError, cache_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="+", type=int)
    args = parser.parse_args(argv)
    if len(args.ids) > 4 or len(set(args.ids)) != len(args.ids) or any(not 1 <= i <= 2147483647 for i in args.ids):
        parser.error("Supply 1–4 distinct positive item IDs, at most 2147483647.")
    client = AHledgerClient(CatalogCache(cache_path()))
    try:
        for index, item_id in enumerate(args.ids):
            if index:
                time.sleep(2.1)
            item = client.lookup(item_id)
            print(f"{item_id}: {item.name if item else 'not found'} — metadata from https://ahledger.com")
    except (CatalogError, OSError) as error:
        print(f"Catalog lookup stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
