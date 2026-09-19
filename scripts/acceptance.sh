#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
make -C "$project_root" verify

remaining=()
[[ -f "$project_root/evidence/P05/browser-close-restart-live.md" ]] || remaining+=("H2 browser-close/worker-restart evidence")
[[ -f "$project_root/evidence/P05/outline-stage-live.md" ]] || remaining+=("H4 autonomous outline-to-manuscript evidence")
[[ -f "$project_root/evidence/P09/telegram-live.md" ]] || remaining+=("H5 live Telegram same-conversation message")
[[ -f "$project_root/evidence/P08/art-live.md" ]] || remaining+=("H8 Codex subscription image artifact")
[[ -f "$project_root/evidence/P10/isolated-restore.md" ]] || remaining+=("H9 isolated restore evidence")
if ((${#remaining[@]})); then
  printf '%s\n' "PARTIAL: automated verification passed, but the >90/100 acceptance rubric and all hard gates are not satisfied."
  printf 'Remaining evidence gates: %s\n' "$(IFS='; '; printf '%s' "${remaining[*]}")"
else
  printf '%s\n' "PARTIAL: automated verification passed; final score and hard-gate review still require lead/critic sign-off."
fi
printf '%s\n' "No score or hard-gate requirement is weakened by this command."
exit 2
