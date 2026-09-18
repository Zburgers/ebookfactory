#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
doctor="$project_root/scripts/doctor.sh"
temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

assert_contains() {
  local needle="$1"
  local file="$2"
  if ! grep -Fq -- "$needle" "$file"; then
    printf 'missing expected text %s in %s\n' "$needle" "$file" >&2
    exit 1
  fi
}

assert_not_contains() {
  local needle="$1"
  local file="$2"
  if grep -Fq -- "$needle" "$file"; then
    printf 'found forbidden text %s in %s\n' "$needle" "$file" >&2
    exit 1
  fi
}

report="$temp_dir/report.json"
secret_value='test-secret-value-must-not-be-written'
OPENAI_API_KEY="$secret_value" "$doctor" --output "$report"

test -s "$report"
assert_contains '"schema_version": "p00.v1"' "$report"
assert_contains '"codex"' "$report"
assert_contains '"status":"available"' "$report"
assert_contains '"OPENAI_API_KEY"' "$report"
assert_not_contains "$secret_value" "$report"

stub_bin="$temp_dir/bin"
mkdir -p "$stub_bin"
for tool_path in \
  /usr/bin/date \
  /usr/bin/sed \
  /usr/bin/printenv \
  /usr/bin/sort \
  /usr/bin/wc \
  /usr/bin/tr \
  /usr/bin/dirname \
  /usr/bin/mkdir \
  /usr/bin/cat \
  /home/naki/.npm-global/bin/codex \
  /home/linuxbrew/.linuxbrew/bin/python3 \
  /home/linuxbrew/.linuxbrew/bin/node; do
  ln -s "$tool_path" "$stub_bin/$(basename "$tool_path")"
done

if PATH="$stub_bin" /usr/bin/bash "$doctor" --strict --output "$temp_dir/strict.json"; then
  printf 'strict doctor unexpectedly passed without required capabilities\n' >&2
  exit 1
fi

ln -s /usr/bin/true "$stub_bin/pi"
ln -s /usr/bin/true "$stub_bin/podman"
PATH="$stub_bin" /usr/bin/bash "$doctor" --output "$temp_dir/all-available.json"
assert_contains '"missing": []' "$temp_dir/all-available.json"

printf 'doctor behavior tests passed\n'
