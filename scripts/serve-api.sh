#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
port="${EBOOK_FACTORY_PORT:-6969}"
graceful_shutdown_seconds="${EBOOK_FACTORY_GRACEFUL_SHUTDOWN_SECONDS:-10}"

[[ "$graceful_shutdown_seconds" =~ ^[0-9]+$ ]] || {
  echo "EBOOK_FACTORY_GRACEFUL_SHUTDOWN_SECONDS must be a non-negative integer" >&2
  exit 1
}

tls_cert="${EBOOK_FACTORY_TLS_CERT:-}"
tls_key="${EBOOK_FACTORY_TLS_KEY:-}"
tailscale_address_value=""

is_private_ipv4() {
  local address="$1"
  [[ "$address" =~ ^10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ||
     "$address" =~ ^192\.168\.[0-9]{1,3}\.[0-9]{1,3}$ ||
     "$address" =~ ^172\.(1[6-9]|2[0-9]|3[0-1])\.[0-9]{1,3}\.[0-9]{1,3}$ ]]
}

resolve_tailscale_address() {
  local tailscale_bin="${TAILSCALE_BIN:-$(command -v tailscale || true)}"
  [[ -n "$tailscale_bin" ]] || {
    echo "tailscale is required for the production API bind" >&2
    return 1
  }
  local address
  address="$($tailscale_bin ip -4 | awk 'NF { print $1; exit }')"
  [[ "$address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || {
    echo "tailscale has no usable IPv4 address; retrying through systemd" >&2
    return 1
  }
  printf '%s\n' "$address"
}

resolve_private_addresses() {
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
}

resolve_addresses() {
  if [[ "${EBOOK_FACTORY_BIND_TO_TAILSCALE:-true}" == "true" ]]; then
    printf '%s\n' "$tailscale_address_value"
  fi

  if [[ "${EBOOK_FACTORY_BIND_TO_LOOPBACK:-false}" == "true" ]]; then
    printf '%s\n' "127.0.0.1"
  fi

  if [[ "${EBOOK_FACTORY_BIND_TO_PRIVATE:-true}" == "true" ]]; then
    local private_wait_seconds="${EBOOK_FACTORY_PRIVATE_WAIT_SECONDS:-30}"
    [[ "$private_wait_seconds" =~ ^[0-9]+$ ]] || {
      echo "EBOOK_FACTORY_PRIVATE_WAIT_SECONDS must be a non-negative integer" >&2
      return 1
    }
    local attempt=0
    local private_addresses=()
    while true; do
      mapfile -t private_addresses < <(resolve_private_addresses)
      if ((${#private_addresses[@]} > 0 || attempt >= private_wait_seconds)); then
        break
      fi
      attempt=$((attempt + 1))
      sleep 1
    done
    printf '%s\n' "${private_addresses[@]}"
  fi
}

if [[ "${EBOOK_FACTORY_BIND_TO_TAILSCALE:-true}" != "true" &&
      "${EBOOK_FACTORY_BIND_TO_PRIVATE:-true}" != "true" ]]; then
  addresses=("${EBOOK_FACTORY_HOST:-127.0.0.1}")
else
  if [[ "${EBOOK_FACTORY_BIND_TO_TAILSCALE:-true}" == "true" ]]; then
    tailscale_address_value="$(resolve_tailscale_address)"
  fi
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

use_tls_for_address() {
  local address="$1"
  [[ "$address" != "127.0.0.1" && "$address" != "::1" ]] || return 1
  [[ "${EBOOK_FACTORY_PRIVATE_TLS:-false}" == "true" ]] && return 0
  [[ -n "$tailscale_address_value" && "$address" == "$tailscale_address_value" ]]
}

tls_addresses=()
for address in "${addresses[@]}"; do
  if use_tls_for_address "$address"; then
    tls_addresses+=("$address")
  fi
done

if ((${#tls_addresses[@]} > 0)); then
  if [[ -n "$tls_cert" || -n "$tls_key" ]]; then
    [[ -n "$tls_cert" && -n "$tls_key" ]] || {
      echo "EBOOK_FACTORY_TLS_CERT and EBOOK_FACTORY_TLS_KEY must be configured together" >&2
      exit 1
    }
  else
    command -v openssl >/dev/null 2>&1 || {
      echo "openssl is required for the non-loopback HTTPS listener" >&2
      exit 1
    }
    tls_dir="${EBOOK_FACTORY_TLS_DIR:-$project_root/var/tls}"
    tls_cert="$tls_dir/server.crt"
    tls_key="$tls_dir/server.key"
    mkdir -p "$tls_dir"
    chmod 700 "$tls_dir"
    san="DNS:localhost"
    for address in "${tls_addresses[@]}"; do
      san+="\nIP:$address"
    done
    cert_text=""
    if [[ -s "$tls_cert" && -s "$tls_key" ]]; then
      cert_text="$(openssl x509 -in "$tls_cert" -noout -text 2>/dev/null || true)"
    fi
    needs_new_cert=false
    [[ -n "$cert_text" ]] || needs_new_cert=true
    for address in "${tls_addresses[@]}"; do
      grep -Fq "IP Address:$address" <<<"$cert_text" || needs_new_cert=true
    done
    if [[ "$needs_new_cert" == "true" ]]; then
      umask 077
      openssl req -x509 -nodes -newkey rsa:2048 -days "${EBOOK_FACTORY_TLS_DAYS:-3650}" \
        -keyout "$tls_key" -out "$tls_cert" -subj "/CN=ebook-factory.local" \
        -addext "subjectAltName = $(printf '%b' "$san" | paste -sd, -)" >/dev/null 2>&1
    fi
  fi
  [[ -r "$tls_cert" && -r "$tls_key" ]] || {
    echo "configured TLS certificate/key is not readable" >&2
    exit 1
  }
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
    uvicorn_args=(app.main:app --host "$address" --port "$port" --timeout-graceful-shutdown "$graceful_shutdown_seconds")
    if use_tls_for_address "$address"; then
      uvicorn_args+=(--ssl-certfile "$tls_cert" --ssl-keyfile "$tls_key")
    fi
    exec uv run --directory "$project_root/apps/api" uvicorn "${uvicorn_args[@]}"
  ) &
  children+=("$!")
done

set +e
wait -n "${children[@]}"
status=$?
set -e
exit "$status"
