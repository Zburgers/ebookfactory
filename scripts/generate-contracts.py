"""Generate the checked-in OpenAPI and TypeScript wire-contract artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
CONTRACT_ROOT = PROJECT_ROOT / "packages" / "contracts"
sys.path.insert(0, str(API_ROOT))

from app.main import create_app  # noqa: E402
from app.settings import Settings  # noqa: E402


def schema_type(schema: dict[str, Any]) -> str:
    """Translate the subset of OpenAPI schema types emitted by this API."""

    if not isinstance(schema, dict):
        return "unknown"
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema:
        return " | ".join(schema_type(item) for item in schema["anyOf"])
    if schema.get("type") == "array":
        return f"Array<{schema_type(schema.get('items', {}))}>"
    if schema.get("type") == "object" and "additionalProperties" in schema:
        return f"Record<string, {schema_type(schema['additionalProperties'])}>"
    return {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}.get(
        schema.get("type", ""), "Record<string, unknown>"
    )


def render_types(schemas: dict[str, dict[str, Any]]) -> str:
    """Render named object schemas as TypeScript interfaces."""

    lines = ["// GENERATED FILE — run scripts/generate-contracts.py; do not edit manually.", ""]
    for name, schema in sorted(schemas.items()):
        if schema.get("type") != "object":
            continue
        required = set(schema.get("required", []))
        lines.append(f"export interface {name} {{")
        for prop_name, prop_schema in schema.get("properties", {}).items():
            optional = "" if prop_name in required else "?"
            lines.append(f"  {prop_name}{optional}: {schema_type(prop_schema)};")
        lines.extend(["}", ""])
    return "\n".join(lines)


def main() -> None:
    """Write OpenAPI JSON and TypeScript types derived from the API app."""

    specification = create_app(Settings(database_url=None)).openapi()
    CONTRACT_ROOT.mkdir(parents=True, exist_ok=True)
    (CONTRACT_ROOT / "openapi.json").write_text(json.dumps(specification, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    schemas = specification.get("components", {}).get("schemas", {})
    (CONTRACT_ROOT / "generated.ts").write_text(render_types(schemas), encoding="utf-8")


if __name__ == "__main__":
    main()
