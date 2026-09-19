#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$#" -ne 1 ]]; then
  echo "usage: $0 PATH_TO_EPUB" >&2
  exit 2
fi

epub_path="$1"

if [[ ! -f "$epub_path" ]]; then
  echo "EPUB file does not exist: $epub_path" >&2
  exit 2
fi

validator="$repo_root/tools/epubcheck/node_modules/.bin/epubcheck-standalone-cli"
if [[ ! -x "$validator" ]]; then
  echo "EPUBCheck is not installed; run: npm ci --prefix tools/epubcheck --ignore-scripts --no-audit --fund=false" >&2
  exit 3
fi

exec "$validator" "$epub_path"
