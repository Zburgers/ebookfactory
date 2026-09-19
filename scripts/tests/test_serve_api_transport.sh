#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
mkdir -p "$fixture/bin"
printf 'certificate\n' >"$fixture/cert.pem"
printf 'private-key\n' >"$fixture/key.pem"

cat >"$fixture/bin/tailscale" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '100.87.104.100'
EOF
cat >"$fixture/bin/ip" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '2: eno1    inet 192.168.29.14/24 scope global eno1'
EOF
cat >"$fixture/bin/uv" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$EBOOK_FACTORY_CAPTURE"
sleep 0.1
EOF
chmod +x "$fixture/bin/tailscale" "$fixture/bin/ip" "$fixture/bin/uv"

EBOOK_FACTORY_CAPTURE="$fixture/calls.txt" \
TAILSCALE_BIN="$fixture/bin/tailscale" \
EBOOK_FACTORY_PRIVATE_INTERFACES=eno1 \
EBOOK_FACTORY_BIND_TO_LOOPBACK=true \
EBOOK_FACTORY_TLS_CERT="$fixture/cert.pem" \
EBOOK_FACTORY_TLS_KEY="$fixture/key.pem" \
PATH="$fixture/bin:$PATH" \
  "$project_root/scripts/serve-api.sh"

tail_call="$(grep -- '--host 100.87.104.100' "$fixture/calls.txt")"
private_call="$(grep -- '--host 192.168.29.14' "$fixture/calls.txt")"
loopback_call="$(grep -- '--host 127.0.0.1' "$fixture/calls.txt")"
grep -Fq -- '--ssl-certfile' <<<"$tail_call"
if grep -Fq -- '--ssl-certfile' <<<"$private_call"; then
  echo "private-LAN listener unexpectedly enables TLS" >&2
  exit 1
fi
if grep -Fq -- '--ssl-certfile' <<<"$loopback_call"; then
  echo "loopback listener unexpectedly enables TLS" >&2
  exit 1
fi

EBOOK_FACTORY_CAPTURE="$fixture/private-tls-calls.txt" \
EBOOK_FACTORY_PRIVATE_TLS=true \
EBOOK_FACTORY_BIND_TO_LOOPBACK=false \
TAILSCALE_BIN="$fixture/bin/tailscale" \
EBOOK_FACTORY_PRIVATE_INTERFACES=eno1 \
EBOOK_FACTORY_TLS_CERT="$fixture/cert.pem" \
EBOOK_FACTORY_TLS_KEY="$fixture/key.pem" \
PATH="$fixture/bin:$PATH" \
  "$project_root/scripts/serve-api.sh"
private_tls_call="$(grep -- '--host 192.168.29.14' "$fixture/private-tls-calls.txt")"
grep -Fq -- '--ssl-certfile' <<<"$private_tls_call"
echo "Tailscale HTTPS and private-LAN HTTP transport checks passed"
