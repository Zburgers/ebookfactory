#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
grep -q '^acceptance:' "$project_root/Makefile"
grep -q '^restore-check:' "$project_root/Makefile"
bash -n "$project_root/scripts/acceptance.sh"
grep -q 'PARTIAL' "$project_root/scripts/acceptance.sh"
printf 'operations entrypoint behavior test passed\n'
