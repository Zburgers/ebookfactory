#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
port="${EBOOK_FACTORY_PORT:-6969}"

is_private_ipv4() {
  local address="$1"
  [[ "$address" =~ ^10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ||
     "$address" =~ ^192\.168\.[0-9]{1,3}\.[0-9]{1,3}$ ||
     "$address" =~ ^172\.(1[6-9]|2[0-9]|3[0-1])\.[0-9]{1,3}\.[0-9]{1,3}$ ]]
}

resolve_addresses() {
  local tailscale_bin="${TAILSCALE_BIN:-$(command -v tailscale || true)}"
  if [[ "${EBOOK_FACTORY_BIND_TO_TAILSCALE:-true}" == "true" ]]; then
    [[ -n "$tailscale_bin" ]] || {
      echo "tailscale is required for the production API bind" >&2
      return 1
    }
    local tailscale_address
    tailscale_address="$($tailscale_bin ip -4 | awk 'NF { print $1; exit }')"
    [[ "$tailscale_address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || {
      echo "tailscale has no usable IPv4 address; retrying through systemd" >&2
      return 1
    }
    printf '%s\n' "$tailscale_address"
  fi

  if [[ "${EBOOK_FACTORY_BIND_TO_LOOPBACK:-false}" == "true" ]]; then
    printf '%s\n' "127.0.0.1"
  fi

  if [[ "${EBOOK_FACTORY_BIND_TO_PRIVATE:-true}" == "true" ]]; then
    command -v ip >/dev/null 2>&1 || {
      echo "ip is required to discover private LAN addresses" >&2
      return 1
    }
    local interface_list="${EBOOK_FACTORY_PRIVATE_INTERFACES:-}"
    if [[ -n "$interface_list" ]]; then
      local interface
      IFS=',' read -r -a interfaces <<< "$interface_list"
      for interface in "${interfaces[@]}"; do
        [[ "$interface" =~ ^[[:alnum:]_.-]+$ ]] || {
          echo "invalid private interface name" >&2
          return 1
        }
        ip -4 -o addr show dev "$interface" scope global |
          awk '{ split($4, parts, "/"); print parts[1] }' |
          while read -r address; do
            if is_private_ipv4 "$address"; then
              printf '%s\n' "$address"
            fi
          done
      done
    else
      ip -4 -o addr show scope global |
        awk '$2 !~ /^(lo|tailscale0|docker[0-9]*|br-|podman|cni)/ { split($4, parts, "/"); print parts[1] }' |
        while read -r address; do
          if is_private_ipv4 "$address"; then
            printf '%s\n' "$address"
          fi
        done
    fi
  fi
}

if [[ "${EBOOK_FACTORY_BIND_TO_TAILSCALE:-true}" != "true" &&
      "${EBOOK_FACTORY_BIND_TO_PRIVATE:-true}" != "true" ]]; then
  addresses=("${EBOOK_FACTORY_HOST:-127.0.0.1}")
else
  mapfile -t discovered_addresses < <(resolve_addresses)
  addresses=()
  for address in "${discovered_addresses[@]}"; do
    [[ -n "$address" ]] || continue
    if [[ ! " ${addresses[*]} " == *" $address "* ]]; then
      addresses+=("$address")
    fi
  done
  ((${#addresses[@]} > 0)) || {
    echo "no permitted Tailscale or private LAN address is available" >&2
    exit 1
  }
fi

if [[ "${EBOOK_FACTORY_DRY_RUN:-false}" == "true" ]]; then
  printf '%s\n' "${addresses[@]}"
  exit 0
fi

children=()
cleanup() {
  local child
  for child in "${children[@]}"; do
    kill "$child" 2>/dev/null || true
  done
  for child in "${children[@]}"; do
    wait "$child" 2>/dev/null || true
  done
}
terminate() {
  trap - TERM INT
  cleanup
  exit 143
}
trap cleanup EXIT
trap terminate TERM INT

for address in "${addresses[@]}"; do
  (
    exec uv run --directory "$project_root/apps/api" uvicorn app.main:app --host "$address" --port "$port"
  ) &
  children+=("$!")
done

set +e
wait -n "${children[@]}"
status=$?
set -e
exit "$status"
