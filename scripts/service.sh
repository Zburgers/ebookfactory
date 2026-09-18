#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${EBOOK_FACTORY_RUNTIME_DIR:-$project_root/var/run}"
pid_file="$runtime_dir/api.pid"
log_file="$runtime_dir/api.log"
host="${EBOOK_FACTORY_HOST:-127.0.0.1}"
port="${EBOOK_FACTORY_PORT:-8000}"

mkdir_runtime() {
  mkdir -p "$runtime_dir"
  chmod 700 "$runtime_dir"
}

owned_pid() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || return 1
  ps -p "$pid" -o args= 2>/dev/null | grep -Fq "uvicorn app.main:app"
}

wait_for_ready() {
  for _ in {1..20}; do
    if curl --fail --silent "http://$host:$port/health" >/dev/null 2>&1; then
      return 0
    fi
    if ! owned_pid "$1"; then
      echo "ebook-factory-api exited during startup; inspect $log_file" >&2
      return 1
    fi
    sleep 0.25
  done
  echo "ebook-factory-api did not become ready; inspect $log_file" >&2
  return 1
}

read_pid() {
  [[ -s "$pid_file" ]] || return 1
  local pid
  read -r pid < "$pid_file"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "$pid"
}

start_service() {
  mkdir_runtime
  if [[ -f "$pid_file" ]]; then
    local existing_pid
    existing_pid="$(read_pid || true)"
    if [[ -n "$existing_pid" ]] && owned_pid "$existing_pid"; then
      echo "ebook-factory-api already running (pid $existing_pid)"
      return 0
    fi
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "refusing to use a live process from an unowned pid file" >&2
      return 1
    fi
    rm -f "$pid_file"
  fi

  (
    cd "$project_root"
    set -a
    [[ ! -f .env ]] || . ./.env
    set +a
    exec uv run --directory "$project_root/apps/api" uvicorn app.main:app --host "$host" --port "$port"
  ) >>"$log_file" 2>&1 &
  local pid=$!
  umask 077
  printf '%s\n' "$pid" > "$pid_file"
  echo "ebook-factory-api started (pid $pid, http://$host:$port)"
  wait_for_ready "$pid"
}

stop_service() {
  local pid
  pid="$(read_pid || true)"
  if [[ -z "$pid" ]]; then
    echo "ebook-factory-api is stopped"
    return 0
  fi
  if ! owned_pid "$pid"; then
    if kill -0 "$pid" 2>/dev/null; then
      echo "refusing to stop a live process from an unowned pid file" >&2
      return 1
    fi
    rm -f "$pid_file"
    echo "ebook-factory-api is stopped"
    return 0
  fi
  kill -TERM "$pid"
  for _ in {1..20}; do
    owned_pid "$pid" || break
    sleep 0.25
  done
  if owned_pid "$pid"; then
    kill -KILL "$pid"
  fi
  rm -f "$pid_file"
  echo "ebook-factory-api stopped"
}

status_service() {
  local pid
  pid="$(read_pid || true)"
  if [[ -n "$pid" ]] && owned_pid "$pid"; then
    echo "ebook-factory-api running (pid $pid)"
    return 0
  fi
  echo "ebook-factory-api stopped"
  return 1
}

case "${1:-}" in
  start) start_service ;;
  stop) stop_service ;;
  restart) stop_service || true; start_service ;;
  status) status_service ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
