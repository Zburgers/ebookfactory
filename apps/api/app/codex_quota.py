"""Bounded, redacted live quota adapter for the local codexctl binary."""

from datetime import datetime, timezone
import os
import re
import selectors
import subprocess
import time

COMMAND = ("codexctl", "status")
TIMEOUT_SECONDS = 10
MAX_OUTPUT_BYTES = 64 * 1024


class CodexQuotaError(RuntimeError):
    """Raised when live local quota status is unavailable or unsafe to parse."""


def parse_codexctl_status(output: str) -> list[dict[str, object]]:
    rows = []
    for line in output.splitlines():
        fields = [field.strip() for field in line.strip("│").split("┆")]
        if len(fields) != 7 or not fields[1].endswith("%") or not fields[3].endswith("%"):
            continue
        try:
            used_5h = int(fields[1][:-1]); used_7d = int(fields[3][:-1])
        except ValueError:
            continue
        if not 0 <= used_5h <= 100 or not 0 <= used_7d <= 100 or not fields[2].startswith("in ") or not fields[4].startswith("in "):
            continue
        rows = [
            {"window_seconds": 18000, "used": used_5h, "remaining": 100 - used_5h, "reset": fields[2]},
            {"window_seconds": 604800, "used": used_7d, "remaining": 100 - used_7d, "reset": fields[4]},
        ]
        break
    if not rows:
        raise CodexQuotaError("codexctl status output was empty or malformed")
    return rows


def fetch_live_quota() -> dict[str, object]:
    process = None
    selector = selectors.DefaultSelector()
    buffers: dict[int, bytearray] = {}
    try:
        process = subprocess.Popen(COMMAND, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdout is not None and process.stderr is not None
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
            buffers[stream.fileno()] = bytearray()
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexQuotaError("codexctl status timed out")
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if len(buffers[key.fd]) + len(chunk) > MAX_OUTPUT_BYTES:
                    raise CodexQuotaError("codexctl status output exceeded limit")
                buffers[key.fd].extend(chunk)
        if process.wait(timeout=max(0, deadline - time.monotonic())) != 0:
            raise CodexQuotaError("codexctl status failed")
        output = bytes(buffers[process.stdout.fileno()]).decode(errors="replace")
        return {"fetched_at": datetime.now(timezone.utc).isoformat(), "source": "codexctl status", "windows": parse_codexctl_status(output)}
    except CodexQuotaError:
        raise
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise CodexQuotaError("codexctl status unavailable") from exc
    finally:
        selector.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
