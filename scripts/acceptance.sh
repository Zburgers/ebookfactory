#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
make -C "$project_root" verify

remaining=()
if gate_output="$($project_root/scripts/check-acceptance-evidence.sh "$project_root")"; then
  :
else
  while IFS= read -r gate; do
    [[ -n "$gate" ]] && remaining+=("$gate")
  done <<<"$gate_output"
fi
if ((${#remaining[@]})); then
  printf '%s\n' "PARTIAL: automated verification passed, but the >90/100 acceptance rubric and all hard gates are not satisfied."
  printf 'Remaining evidence gates: %s\n' "$(IFS='; '; printf '%s' "${remaining[*]}")"
else
  printf '%s\n' "PARTIAL: automated verification passed; final score and hard-gate review still require lead/critic sign-off."
fi
printf '%s\n' "No score or hard-gate requirement is weakened by this command."
exit 2
