#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
entrypoint="$repo_root/scripts/validate-epub.sh"
package_json="$repo_root/tools/epubcheck/package.json"

test -x "$entrypoint"
grep -F 'epubcheck-standalone-cli' "$entrypoint" >/dev/null
grep -F '"epubcheck-standalone-cli": "5.4.0-build2"' "$package_json" >/dev/null
test -f "$repo_root/tools/epubcheck/package-lock.json"

if "$entrypoint" >/dev/null 2>&1; then
  echo "validate-epub.sh accepted a missing EPUB path" >&2
  exit 1
fi

echo "epubcheck entrypoint checks passed"
