#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
make -C "$project_root" verify

printf '%s\n' "PARTIAL: automated verification passed, but the >90/100 acceptance rubric and all hard gates are not satisfied."
printf '%s\n' "Blocked external gates: Telegram credentials/live loop and Codex subscription image artifact; H9 isolated restore is evidenced."
printf '%s\n' "No score or hard-gate requirement is weakened by this command."
exit 2
