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

echo "non-loopback TLS launcher checks passed"
