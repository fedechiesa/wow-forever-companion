import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.fresh_simulator import generate_fresh, simulation_lua


def main():
    parser = argparse.ArgumentParser(description="Generate SIMULATED Auctionator v8 evidence")
    parser.add_argument("--output", type=Path, default=ROOT.parent / "data/imports/fresh")
    parser.add_argument("--seed", type=int, default=340)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--items", type=int, default=50)
    parser.add_argument("--markets", nargs="+", default=["PvE", "PvP", "HC", "RP"])
    args = parser.parse_args()
    database, catalog = generate_fresh(seed=args.seed, days=args.days, items=args.items, markets=args.markets)
    raw = simulation_lua(database)
    context = {"source_id": f"fresh-seed-{args.seed}", "region": "simulation", "dataset": "simulated"}
    result = AuctionatorAdapter().load_bytes(raw, **context)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "Auctionator.lua").write_bytes(raw)
    (args.output / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    (args.output / "context.json").write_text(json.dumps(context, indent=2), encoding="utf-8")
    print(json.dumps({"dataset": "SIMULATED", "fictional_items": args.items, "days": args.days,
                      "markets": args.markets, "observations": len(result.batch.observations),
                      "sha256": result.source_hash, "directory": str(args.output)}))


if __name__ == "__main__":
    main()
