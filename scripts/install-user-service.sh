#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_names=(ebook-factory-api.service ebook-factory-worker.service)
config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
unit_dir="$config_root/systemd/user"
start_service=true

if [[ "${1:-}" == "--no-start" ]]; then
  start_service=false
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--no-start]" >&2
  exit 2
fi

for unit_name in "${unit_names[@]}"; do [[ -f "$project_root/infra/systemd/$unit_name" ]] || { echo "missing unit: $project_root/infra/systemd/$unit_name" >&2; exit 1; }; done
mkdir -p "$unit_dir"
chmod 700 "$unit_dir"
for unit_name in "${unit_names[@]}"; do ln -sfn "$project_root/infra/systemd/$unit_name" "$unit_dir/$unit_name"; done

systemctl --user daemon-reload
systemctl --user enable "${unit_names[@]}" >/dev/null
if [[ "$start_service" == true ]]; then
  systemctl --user start "${unit_names[@]}"
fi

echo "installed ${unit_names[*]} for user $(id -un)"
if [[ "$start_service" == true ]]; then
  echo "services started; inspect with: systemctl --user status ${unit_names[*]}"
else
  echo "services enabled but not started; start with: systemctl --user start ${unit_names[*]}"
fi
