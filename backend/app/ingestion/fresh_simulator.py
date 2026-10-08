"""Synthetic economics and fictional catalog; never Forever price history."""
import random

PROFILES = ("abundant_leveling", "growing_demand", "scarce_supply", "early_volatility", "late_arrival", "intermittent")


def generate_fresh(*, seed=340, days=30, items=50, markets=("PvE", "PvP", "HC", "RP"), start_day=2500):
    if not 1 <= days <= 366 or not 1 <= items <= 100 or start_day < 0 or start_day + days > 2147483647:
        raise ValueError("invalid simulation size or day range")
    if not markets or len(set(markets)) != len(markets) or set(markets) - {"PvE", "PvP", "HC", "RP"}:
        raise ValueError("invalid simulation markets")
    rng = random.Random(seed)
    catalog = []
    database = {"__dbversion": 8}
    for index in range(items):
        catalog.append({"item_key": str(1900000000 + index), "name": f"FICTIONAL material {index + 1:02}",
                        "fictional": True, "profile": PROFILES[index % len(PROFILES)]})
    for market_index, market in enumerate(markets):
        realm = {"version": 2}
        database[market] = realm
        for index, item in enumerate(catalog):
            profile = item["profile"]
            entry = {"l": {}, "h": {}, "a": {}, "m": 0}
            for day in range(days):
                if profile == "late_arrival" and day < 7 + index % 5:
                    continue
                if profile == "intermittent" and (day + index) % 4 == 0:
                    continue
                base = (100 + index * 75) * (1 + market_index * .15)
                if profile == "abundant_leveling":
                    base *= max(.3, 1 - day * .015)
                elif profile == "growing_demand":
                    base *= 1 + day * .05
                elif profile == "scarce_supply":
                    base *= 5
                amplitude = .65 * (1 - day / (days + 1)) + .05
                if profile != "early_volatility":
                    amplitude *= .5
                raw_day = str(start_day + day)
                for _ in range(3):
                    price = max(1, int(base * (1 + rng.uniform(-amplitude, amplitude))))
                    availability = rng.randint(1, 8) if profile == "scarce_supply" else rng.randint(100, 500) + day * 15
                    # Match SetPrice ordering, including its sparse-l behavior.
                    entry["m"] = price
                    high = max(entry["h"].get(raw_day, price), price)
                    entry["h"][raw_day] = high
                    if price < high:
                        entry["l"][raw_day] = min(entry["l"].get(raw_day, price), price)
                    entry["a"][raw_day] = max(entry["a"].get(raw_day, 0), availability)
            if entry["h"]:
                realm[item["item_key"]] = entry
    return database, catalog


def lua_literal(value, depth=0):
    if type(value) is int:
        return str(value)
    if isinstance(value, str):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(value, dict):
        indent = "  " * (depth + 1)
        entries = [f"{indent}[{lua_literal(key)}] = {lua_literal(data, depth + 1)}," for key, data in value.items()]
        return "{\n" + "\n".join(entries) + "\n" + "  " * depth + "}"
    raise ValueError("unsupported fixture value")


def simulation_lua(database):
    return ("-- SIMULATED prices and availability; ALL item IDs/names are FICTIONAL.\n"
            "AUCTIONATOR_PRICE_DATABASE = " + lua_literal(database) + "\n").encode("utf-8")
