#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_dir="$(mktemp -d)"
cleanup() {
  EBOOK_FACTORY_RUNTIME_DIR="$runtime_dir" "$project_root/scripts/service.sh" stop >/dev/null 2>&1 || true
  rm -rf "$runtime_dir"
}
trap cleanup EXIT

EBOOK_FACTORY_RUNTIME_DIR="$runtime_dir" EBOOK_FACTORY_PORT=18084 "$project_root/scripts/service.sh" start
EBOOK_FACTORY_RUNTIME_DIR="$runtime_dir" "$project_root/scripts/service.sh" status
curl --fail --silent --show-error http://127.0.0.1:18084/health >/dev/null
EBOOK_FACTORY_RUNTIME_DIR="$runtime_dir" "$project_root/scripts/service.sh" stop
if EBOOK_FACTORY_RUNTIME_DIR="$runtime_dir" "$project_root/scripts/service.sh" status >/dev/null 2>&1; then
  echo "service should be stopped" >&2
  exit 1
fi
echo "service lifecycle behavior test passed"
