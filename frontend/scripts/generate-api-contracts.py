"""Generate response types/schemas from FastAPI OpenAPI, without database access.
Run with backend Python; --check detects drift.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app

schemas = app.openapi()["components"]["schemas"]
selected = {}

def collect(name):
    if name in selected:
        return
    selected[name] = schemas[name]
    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value:
                collect(value["$ref"].split("/")[-1])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schemas[name])

def ts(schema):
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(ts(s) for s in schema["anyOf"])
    if schema.get("type") == "array":
        return f"Array<{ts(schema['items'])}>"
    return {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}[schema["type"]]

collect("MarketMetricsResponse")
collect("SeriesDiscoveryResponse")
lines = ["// Generated from FastAPI OpenAPI. Run scripts/generate-api-contracts.py; do not edit."]
for name, schema in sorted(selected.items()):
    lines.append(f"export interface {name} {{")
    for key, value in schema["properties"].items():
        optional = "" if key in schema.get("required", []) else "?"
        lines.append(f"  {key}{optional}: {ts(value)};")
    lines.append("}\n")
outputs = {
    ROOT / "frontend/src/api/generated.ts": "\n".join(lines).rstrip() + "\n",
    ROOT / "frontend/src/api/response-schemas.json": json.dumps(selected, ensure_ascii=False, indent=2) + "\n",
}
for path, content in outputs.items():
    if "--check" in sys.argv:
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"Contract drift: regenerate {path.name}")
    else:
        path.write_text(content, encoding="utf-8")
print("OpenAPI response contracts: OK")
