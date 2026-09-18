#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_name="ebook-factory-api.service"
unit_source="$project_root/infra/systemd/$unit_name"
config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
unit_dir="$config_root/systemd/user"
unit_link="$unit_dir/$unit_name"
start_service=true

if [[ "${1:-}" == "--no-start" ]]; then
  start_service=false
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--no-start]" >&2
  exit 2
fi

[[ -f "$unit_source" ]] || { echo "missing unit: $unit_source" >&2; exit 1; }
mkdir -p "$unit_dir"
chmod 700 "$unit_dir"
ln -sfn "$unit_source" "$unit_link"

systemctl --user daemon-reload
systemctl --user enable "$unit_name" >/dev/null
if [[ "$start_service" == true ]]; then
  systemctl --user start "$unit_name"
fi

echo "installed $unit_name for user $(id -un)"
if [[ "$start_service" == true ]]; then
  echo "service started; inspect with: systemctl --user status $unit_name"
else
  echo "service enabled but not started; start with: systemctl --user start $unit_name"
fi
