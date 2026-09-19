#!/usr/bin/env bash
set -euo pipefail

project_root="${1:?usage: check-acceptance-evidence.sh PROJECT_ROOT}"
remaining=()

require_file() {
  local relative_path="$1"
  local label="$2"
  [[ -f "$project_root/$relative_path" ]] || remaining+=("$label")
}

require_file "evidence/P05/browser-close-restart-live.md" "H2 browser-close/worker-restart evidence"
require_file "evidence/P05/outline-stage-live.md" "H4 autonomous outline-to-manuscript evidence"
require_file "evidence/P08/art-live.md" "H8 Codex subscription image artifact"
require_file "evidence/P10/isolated-restore.md" "H9 isolated restore evidence"

if [[ -f "$project_root/evidence/P09/telegram-project-switching-live.md" ]]; then
  :
elif [[ -f "$project_root/evidence/P09/telegram-live.md" ]]; then
  :
else
  remaining+=("H5 live Telegram same-conversation message")
fi

if ((${#remaining[@]})); then
  printf '%s\n' "${remaining[@]}"
  exit 1
fi

printf '%s\n' "all automated evidence markers present"
