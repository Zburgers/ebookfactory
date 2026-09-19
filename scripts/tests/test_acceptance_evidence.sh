#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT

mkdir -p "$fixture/evidence/P05" "$fixture/evidence/P08" "$fixture/evidence/P09" "$fixture/evidence/P10"
touch \
  "$fixture/evidence/P05/browser-close-restart-live.md" \
  "$fixture/evidence/P05/outline-stage-live.md" \
  "$fixture/evidence/P08/art-live.md" \
  "$fixture/evidence/P10/isolated-restore.md" \
  "$fixture/evidence/P09/telegram-project-switching-live.md"

output="$("$project_root/scripts/check-acceptance-evidence.sh" "$fixture")"
grep -Fq 'all automated evidence markers present' <<<"$output"
echo "acceptance evidence marker check passed"
