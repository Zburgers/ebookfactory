#!/usr/bin/env bash
set -euo pipefail

output_file=""
strict=0

usage() {
  cat <<'EOF'
Usage: scripts/doctor.sh [--output PATH] [--strict]

Collect a redacted P00 capability report. Environment values and credential
contents are never included; only selected variable names are recorded.
--strict exits non-zero when required runtime capabilities are unavailable.
EOF
}

while (($#)); do
  case "$1" in
    --output)
      (($# >= 2)) || { printf '%s\n' '--output requires a path' >&2; exit 2; }
      output_file="$2"
      shift 2
      ;;
    --strict)
      strict=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$output_file" ]]; then
  output_file="$(pwd)/evidence/P00/capabilities.json"
fi

mkdir -p "$(dirname "$output_file")"

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/[[:cntrl:]]//g'
}

command_status() {
  local name="$1"
  local found=""
  local version=""
  if found="$(command -v "$name" 2>/dev/null)"; then
    version="$($name --version 2>&1 | sed -n '1p' || true)"
    printf '{"status":"available","path":"%s","version":"%s"}' \
      "$(json_escape "$found")" "$(json_escape "$version")"
  else
    printf '{"status":"unavailable","path":null,"version":null}'
  fi
}

rootless_status() {
  if ! command -v podman >/dev/null 2>&1; then
    printf '"unavailable"'
    return
  fi
  local value
  value="$(timeout 10 podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)"
  case "$value" in
    true) printf '"verified"' ;;
    false) printf '"not_rootless"' ;;
    *) printf '"unknown"' ;;
  esac
}

environment_names() {
  local first=1
  local name
  while IFS='=' read -r name _; do
    case "$name" in
      PI_*|CODEX_*|OPENAI_*|TELEGRAM_*|POSTGRES_*|DATABASE_*|PODMAN_*|COPILOT_*|GITHUB_*)
        if ((first)); then first=0; else printf ','; fi
        printf '"%s"' "$(json_escape "$name")"
        ;;
    esac
  done < <(printenv | sort)
}

reference_status() {
  local path="$1"
  if [[ -e "$path" ]]; then
    printf '{"status":"present","path":"%s"}' "$(json_escape "$path")"
  else
    printf '{"status":"absent","path":"%s"}' "$(json_escape "$path")"
  fi
}

listener_count=0
if command -v ss >/dev/null 2>&1; then
  listener_count="$(ss -ltnH 2>/dev/null | wc -l | tr -d ' ')"
fi

required_missing=()
for required in pi podman python3 node; do
  command -v "$required" >/dev/null 2>&1 || required_missing+=("$required")
done

missing_json=""
if ((${#required_missing[@]} > 0)); then
  missing_json="$(printf '"%s",' "${required_missing[@]}" | sed 's/,$//')"
fi

cat >"$output_file" <<EOF
{
  "schema_version": "p00.v1",
  "generated_at_utc": "$(json_escape "$(date -u +%Y-%m-%dT%H:%M:%SZ)")",
  "runtime": {
    "pi": $(command_status pi),
    "codex": $(command_status codex),
    "podman": $(command_status podman),
    "docker": $(command_status docker),
    "python3": $(command_status python3),
    "node": $(command_status node),
    "npm": $(command_status npm),
    "uv": $(command_status uv),
    "pandoc": $(command_status pandoc),
    "epubcheck": $(command_status epubcheck),
    "chromium": $(command_status chromium),
    "postgres_client": $(command_status psql),
    "podman_rootless": $(rootless_status)
  },
  "references": {
    "Ebookmaker": $(reference_status /home/naki/Desktop/itsthatnewshit/isthisreal/Ebookmaker),
    "MuMuAINovel": $(reference_status /home/naki/Desktop/itsthatnewshit/isthisreal/MuMuAINovel)
  },
  "network": {"listening_tcp_socket_count": $listener_count},
  "environment_names_only": [$(environment_names)],
  "database_target": {
    "status": "owner_confirmation_required",
    "identity": null,
    "reason": "No PostgreSQL target was changed or inferred from listeners."
  },
  "telegram": {
    "status": "not_configured",
    "reason": "Token and allowed chat/sender IDs were not supplied to this checkout."
  },
  "image_capability": {
    "status": "unverified",
    "reason": "The installed Codex CLI was inspected for capabilities; no unattended image artifact route was proven."
  },
  "strict_requirements": {
    "missing": [$missing_json]
  }
}
EOF

if ((strict && ${#required_missing[@]} > 0)); then
  printf 'P00 strict check failed; missing: %s\n' "${required_missing[*]}" >&2
  exit 1
fi

printf 'P00 capability report written to %s\n' "$output_file"
