import re


def normalize_item_key(key: str) -> tuple[str, str, str]:
    """Verified DBKeyFromLink/DBKeyFromBrowseResult shapes; never merge variants."""
    match = re.fullmatch(r"(?:(g|gr|p):)?([0-9]{1,10})(?::(.+))?", key)
    if not match or not 0 < int(match[2]) <= 2147483647:
        raise ValueError("unsupported Auctionator item key")
    prefix, item, variant = match.groups()
    item = str(int(item))
    if prefix in (None, "p"):
        if variant is not None:
            raise ValueError("unexpected item variant")
        return (item if prefix is None else f"p:{item}", item, "item" if prefix is None else "pet")
    if prefix == "g":
        if variant is None or not re.fullmatch(r"[0-9]{1,10}", variant) or int(variant) > 2147483647:
            raise ValueError("invalid gear level")
        return f"g:{item}:{int(variant)}", item, "gear_level"
    if not variant or len(variant) > 150 or any(ord(c) < 32 for c in variant):
        raise ValueError("invalid gear suffix")
    return f"gr:{item}:{variant}", item, "gear_suffix"
