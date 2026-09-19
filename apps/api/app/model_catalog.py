"""Safe discovery of the installed Pi model catalog."""

from datetime import datetime, timezone
import os
import selectors
import subprocess
import time
import re

from app.pricing import price_card_summary

COMMAND = (
    "pi", "--no-extensions", "--no-skills", "--no-prompt-templates",
    "--no-tools", "--no-session", "--list-models",
)
TIMEOUT_SECONDS = 10
MAX_OUTPUT_BYTES = 256 * 1024


class ModelCatalogError(RuntimeError):
    """Raised when Pi cannot provide a bounded model catalog."""


def enrich_model_pricing(models: list[dict[str, object]]) -> list[dict[str, object]]:
    """Attach a source-attributed reference card without changing model identity."""

    enriched: list[dict[str, object]] = []
    for model in models:
        row = dict(model)
        row["pricing"] = price_card_summary(str(row["provider"]), str(row["model"]))
        enriched.append(row)
    return enriched


def parse_model_table(output: str) -> list[dict[str, object]]:
    models: list[dict[str, object]] = []
    header_seen = False
    size_pattern = re.compile(r"^\d+(?:\.\d+)?[KMG]$")
    for line in output.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields == ["provider", "model", "context", "max-out", "thinking", "images"]:
            header_seen = True
            continue
        if set(fields) <= {"-"}:
            continue
        if not header_seen:
            continue
        if len(fields) != 6:
            continue
        provider, model, context, max_output, thinking, images = fields[:6]
        if not provider or not model or not size_pattern.fullmatch(context) or not size_pattern.fullmatch(max_output):
            continue
        if thinking not in {"yes", "no"} or images not in {"yes", "no"}:
            continue
        models.append({
            "provider": provider,
            "model": model,
            "qualified_model": f"{provider}/{model}",
            "context": context,
            "max_output": max_output,
            "thinking": thinking.lower() == "yes",
            "images": images.lower() == "yes",
        })
    if not models:
        raise ModelCatalogError("Pi model catalog was empty or malformed")
    return models


def fetch_model_catalog() -> dict[str, object]:
    process = None
    streams: dict[int, bytearray] = { }
    selector = selectors.DefaultSelector()
    try:
        process = subprocess.Popen(COMMAND, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdout is not None and process.stderr is not None
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
            streams[stream.fileno()] = bytearray()
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(COMMAND, TIMEOUT_SECONDS)
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffer = streams[key.fd]
                if len(buffer) + len(chunk) > MAX_OUTPUT_BYTES:
                    raise ModelCatalogError("Pi model catalog output exceeded limit")
                buffer.extend(chunk)
        code = process.wait(timeout=max(0, deadline - time.monotonic()))
        if code != 0:
            raise ModelCatalogError("Pi model catalog command failed")
        stdout = bytes(streams[process.stdout.fileno()]).decode(errors="replace")
    except subprocess.TimeoutExpired as exc:
        raise ModelCatalogError("Pi model catalog timed out") from exc
    except (OSError, ValueError) as exc:
        raise ModelCatalogError("Pi model catalog command failed") from exc
    finally:
        selector.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    parsed_models = enrich_model_pricing(parse_model_table(stdout))
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "pi --list-models",
        "models": parsed_models,
    }
