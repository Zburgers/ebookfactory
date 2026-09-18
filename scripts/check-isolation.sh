#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image="localhost/ebook-factory-job:check"
sentinel_dir="$(mktemp -d)"
workspace="$(mktemp -d)"
trap 'find "$sentinel_dir" "$workspace" -mindepth 1 -delete 2>/dev/null || true; rmdir "$sentinel_dir" "$workspace" 2>/dev/null || true' EXIT
printf 'host-only-sentinel\n' > "$sentinel_dir/sentinel"

podman build --quiet --tag "$image" --file "$project_root/infra/podman/Containerfile" "$project_root/infra/podman" >/dev/null

output="$(podman run --rm \
  --name ebook-factory-isolation-check \
  --label io.ebook-factory.install=check \
  --label io.ebook-factory.job=check \
  --label io.ebook-factory.generation=1 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m \
  --cap-drop=all \
  --security-opt=no-new-privileges \
  --network=none \
  --memory=128m \
  --cpus=1 \
  --pids-limit=64 \
  --userns=keep-id \
  --user ebook \
  --mount "type=bind,src=$workspace,dst=/workspace,rw,nodev,nosuid" \
  "$image" \
  -c 'test ! -e /host-sentinel && test ! -e /home/naki && test -r /proc/net/route && test "$(wc -l < /proc/net/route)" -le 1 && touch /workspace/job-output && test -f /workspace/job-output' \
  2>&1)"

test -z "$output"
test -f "$workspace/job-output"
test ! -e "$workspace/host-sentinel"
printf 'rootless containment check passed\n'
