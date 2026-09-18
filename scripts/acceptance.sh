#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
make -C "$project_root" verify

printf '%s\n' "PARTIAL: automated verification passed, but the full acceptance rubric is not satisfied."
printf '%s\n' "Blocked external gates: Telegram credentials/live loop, Codex subscription image artifact, and isolated PostgreSQL restore."
printf '%s\n' "No score or hard-gate requirement is weakened by this command."
exit 2
