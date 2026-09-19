#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
epub_path="${1:-}"

if [[ -z "$epub_path" ]]; then
  echo "usage: $0 PATH_TO_EPUB" >&2
  exit 2
fi

if [[ ! -f "$epub_path" ]]; then
  echo "EPUB file does not exist: $epub_path" >&2
  exit 2
fi

exec npm --prefix "$repo_root/tools/epubcheck" exec -- epubcheck-standalone-cli "$epub_path"
