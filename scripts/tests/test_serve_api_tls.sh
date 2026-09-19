#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
serve="$project_root/scripts/serve-api.sh"

bash -n "$serve"
grep -Fq 'ssl-certfile' "$serve"
grep -Fq 'ssl-keyfile' "$serve"
grep -Fq 'openssl req -x509' "$serve"
grep -Fq '127.0.0.1' "$serve"
grep -Fq 'EBOOK_FACTORY_TLS_CERT and EBOOK_FACTORY_TLS_KEY must be configured together' "$serve"
grep -Fq 'EBOOK_FACTORY_PRIVATE_TLS:-false' "$serve"
grep -Fq 'EBOOK_FACTORY_GRACEFUL_SHUTDOWN_SECONDS:-10' "$serve"
grep -Fq -- '--timeout-graceful-shutdown' "$serve"
grep -Fq 'tailscale_address_value' "$serve"

echo "Tailscale TLS launcher checks passed"
