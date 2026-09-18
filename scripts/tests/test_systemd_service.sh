#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
unit="$project_root/infra/systemd/ebook-factory-api.service"
installer="$project_root/scripts/install-user-service.sh"
serve="$project_root/scripts/serve-api.sh"

[[ -f "$unit" ]] || { echo "missing systemd unit: $unit" >&2; exit 1; }
[[ -x "$installer" ]] || { echo "installer must be executable: $installer" >&2; exit 1; }
[[ -x "$serve" ]] || { echo "foreground launcher must be executable: $serve" >&2; exit 1; }

grep -Fq 'Description=Ebook Factory API' "$unit"
grep -Fq 'Restart=on-failure' "$unit"
grep -Fq 'WantedBy=default.target' "$unit"
grep -Fq 'ExecStart=%h/.config/shipyard/worktrees/ebookfactory/codex-ebook-factory-v2/scripts/serve-api.sh' "$unit"
grep -Fq 'EBOOK_FACTORY_PORT=6969' "$unit"
grep -Fq 'EBOOK_FACTORY_BIND_TO_TAILSCALE=true' "$unit"
grep -Fq 'EBOOK_FACTORY_BIND_TO_PRIVATE=true' "$unit"
grep -Fq 'EBOOK_FACTORY_PRIVATE_INTERFACES=eno1' "$unit"
grep -Fq 'EBOOK_FACTORY_BIND_TO_LOOPBACK=true' "$unit"
grep -Fq 'PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin' "$unit"

bash -n "$installer" "$serve"
addresses="$(EBOOK_FACTORY_DRY_RUN=true EBOOK_FACTORY_BIND_TO_LOOPBACK=true EBOOK_FACTORY_PRIVATE_INTERFACES=eno1 "$serve")"
grep -Fxq '100.87.104.100' <<<"$addresses"
grep -Fxq '192.168.29.14' <<<"$addresses"
grep -Fxq '127.0.0.1' <<<"$addresses"
if grep -Fxq '0.0.0.0' <<<"$addresses"; then
  echo "service must not bind wildcard in production mode" >&2
  exit 1
fi
if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "$unit"
fi

echo "systemd service manifest checks passed"
