#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHONPATH="$project_root/apps/api" uv run --directory "$project_root/apps/api" \
  python "$project_root/scripts/generate-contracts.py"

jq -e '.info.title == "Ebook Factory API" and .paths["/health"] and .paths["/ready"]' \
  "$project_root/packages/contracts/openapi.json" >/dev/null
grep -Fq '/private/worker/claim' "$project_root/packages/contracts/openapi.json"
grep -Fq 'export interface HealthResponse' "$project_root/packages/contracts/generated.ts"
grep -Fq 'export interface ReadinessResponse' "$project_root/packages/contracts/generated.ts"
grep -Fq 'reason?: string | null;' "$project_root/packages/contracts/generated.ts"
grep -Fq 'dependencies: Record<string, DependencyStatus>;' "$project_root/packages/contracts/generated.ts"

printf 'contract generation behavior test passed\n'
