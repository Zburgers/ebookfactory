#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
grep -q 'ebook-factory-worker.service' "$root/scripts/install-user-service.sh"
grep -q 'worker.service' "$root/Makefile"
grep -q 'Restart=always' "$root/infra/systemd/ebook-factory-worker.service"
echo "worker service lifecycle wiring: ok"
