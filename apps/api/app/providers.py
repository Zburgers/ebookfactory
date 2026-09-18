"""Non-secret provider settings and connection status records."""

from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException, HTTPSConnection
import ipaddress
import json
import os
import re
import socket
import ssl
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProviderSetting


@dataclass(frozen=True)
class ProviderResult:
    setting_id: UUID
    provider: str
    scope: str
    endpoint: str | None
    protocol: str | None
    orchestration_model: str | None
    drafting_model: str | None
    review_model: str | None
    credential_configured: bool


@dataclass(frozen=True)
class ConnectionTestResult:
    provider: str
    protocol: str
    model: str | None
    outcome: str
    http_status: int | None
    response_id: str | None
    usage: dict[str, Any] | None
    error: str | None


_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROBE_TIMEOUT_SECONDS = 3
_PROBE_MAX_BYTES = 64 * 1024
_USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens", "reasoning_tokens")


class _PinnedHTTPConnection(HTTPConnection):
    def __init__(self, *args: Any, resolved_address: str, **kwargs: Any) -> None:
        self._resolved_address = resolved_address
        super().__init__(*args, **kwargs)

    def connect(self) -> None:
        self.sock = socket.create_connection((self._resolved_address, self.port), self.timeout, self.source_address)


class _PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, *args: Any, resolved_address: str, **kwargs: Any) -> None:
        self._resolved_address = resolved_address
        super().__init__(*args, **kwargs)

    def connect(self) -> None:
        self.sock = socket.create_connection((self._resolved_address, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self._tunnel_host or self.host)


def _validate_credential_ref(credential_ref: str | None) -> None:
    if credential_ref and not _ENVIRONMENT_NAME.fullmatch(credential_ref):
        raise ValueError("credential_ref must be a valid environment-variable name")


def _validate_endpoint_syntax(endpoint: str) -> None:
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError("provider endpoint must be a valid HTTP(S) URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("provider endpoint must be an HTTP(S) URL without credentials or query parameters")


def _normalize_origin(value: str, *, error_message: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError(error_message) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(error_message)
    if not 1 <= port <= 65535:
        raise ValueError(error_message)
    try:
        normalized_host = ipaddress.ip_address(hostname).compressed
    except ValueError:
        normalized_host = hostname.lower()
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    return f"{parsed.scheme.lower()}://{normalized_host}:{port}"


def _configured_allowed_origins() -> set[str]:
    return {
        _normalize_origin(configured.strip(), error_message="invalid provider origin allowlist entry")
        for configured in os.environ.get("EBOOK_FACTORY_PROVIDER_ALLOWED_ORIGINS", "").split(",")
        if configured.strip()
    }


def _validate_endpoint_destination(endpoint: str) -> tuple[str, str, int]:
    _validate_endpoint_syntax(endpoint)
    parsed = urlsplit(endpoint)
    hostname = parsed.hostname
    assert hostname is not None
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("provider endpoint must use a valid port") from exc
    if not 1 <= port <= 65535:
        raise ValueError("provider endpoint must use a valid port")
    origin_host = f"[{hostname}]" if ":" in hostname else hostname
    origin = _normalize_origin(
        f"{parsed.scheme}://{origin_host}:{port}",
        error_message="provider endpoint must be a valid origin",
    )
    allowed_origins = _configured_allowed_origins()
    try:
        addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)))
    except socket.gaierror as exc:
        raise ValueError("provider endpoint host cannot be resolved") from exc
    if not addresses:
        raise ValueError("provider endpoint host cannot be resolved")
    for address in addresses:
        parsed_address = ipaddress.ip_address(address)
        if parsed_address.is_unspecified or parsed_address.is_link_local or parsed_address.is_multicast or parsed_address.is_reserved:
            raise ValueError("provider endpoint resolves to a disallowed address")
        if (parsed_address.is_loopback or parsed_address.is_private) and origin not in allowed_origins:
            raise ValueError("private provider endpoint requires an explicit allowlist origin")
    return hostname, addresses[0], port


def _safe_usage(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    filtered = {
        field: token_count
        for field in _USAGE_FIELDS
        if isinstance(token_count := value.get(field), int)
        and not isinstance(token_count, bool)
        and 0 <= token_count <= 1_000_000_000
    }
    return filtered or None


def save_provider_setting(
    session: Session,
    *,
    provider: str,
    scope: str,
    endpoint: str | None,
    protocol: str | None,
    credential_ref: str | None,
    orchestration_model: str | None,
    drafting_model: str | None,
    review_model: str | None,
) -> ProviderResult:
    """Persist provider metadata while keeping credential bytes out of the DB."""

    if endpoint is not None:
        _validate_endpoint_syntax(endpoint)
    _validate_credential_ref(credential_ref)
    with session.begin():
        setting = session.scalar(
            select(ProviderSetting)
            .where(ProviderSetting.provider == provider, ProviderSetting.scope == scope)
            .with_for_update()
        )
        if setting is None:
            setting = ProviderSetting(provider=provider, scope=scope)
            session.add(setting)
        setting.config = {"endpoint": endpoint, "protocol": protocol}
        setting.credential_ref = credential_ref
        setting.orchestration_model = orchestration_model
        setting.drafting_model = drafting_model
        setting.review_model = review_model
        session.flush()
        return ProviderResult(
            setting_id=setting.id,
            provider=setting.provider,
            scope=setting.scope,
            endpoint=endpoint,
            protocol=protocol,
            orchestration_model=setting.orchestration_model,
            drafting_model=setting.drafting_model,
            review_model=setting.review_model,
            credential_configured=bool(setting.credential_ref),
        )


def connection_test(
    session: Session,
    *,
    provider: str,
    scope: str = "app",
) -> ConnectionTestResult:
    """Probe one saved provider without returning secrets or response bodies."""

    setting = session.scalar(
        select(ProviderSetting).where(ProviderSetting.provider == provider, ProviderSetting.scope == scope)
    )
    if setting is None:
        raise ValueError("provider setting not found")
    endpoint = setting.config.get("endpoint") if isinstance(setting.config, dict) else None
    protocol = setting.config.get("protocol") if isinstance(setting.config, dict) else None
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError("provider endpoint is required")
    if protocol not in {"openai-compatible", "health-json"}:
        raise ValueError("unsupported provider protocol")
    hostname, resolved_address, port = _validate_endpoint_destination(endpoint)

    credential = None
    if setting.credential_ref:
        _validate_credential_ref(setting.credential_ref)
        credential = os.environ.get(setting.credential_ref)
        if not credential:
            raise ValueError("credential environment variable is not configured")

    model = setting.orchestration_model or setting.drafting_model or setting.review_model
    if protocol == "openai-compatible" and not model:
        raise ValueError("provider model is required")
    headers = {"accept": "application/json"}
    if credential:
        headers["authorization"] = f"Bearer {credential}"
    if protocol == "openai-compatible":
        headers["content-type"] = "application/json"
        body: bytes | None = json.dumps(
            {"model": model, "messages": [{"role": "user", "content": "connection test"}], "max_tokens": 8}
        ).encode()
        method = "POST"
    else:
        body = None
        method = "GET"
    path = parsed_path = urlsplit(endpoint).path.rstrip("/")
    path = (parsed_path or "") + ("/chat/completions" if protocol == "openai-compatible" else "")
    if not path:
        path = "/"
    connection_type = _PinnedHTTPSConnection if urlsplit(endpoint).scheme == "https" else _PinnedHTTPConnection
    connection: HTTPConnection | HTTPSConnection = connection_type(
        hostname,
        port,
        timeout=_PROBE_TIMEOUT_SECONDS,
        resolved_address=resolved_address,
        **({"context": ssl.create_default_context()} if connection_type is _PinnedHTTPSConnection else {}),
    )
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        try:
            status = response.status
            raw = response.read(_PROBE_MAX_BYTES)
        finally:
            response.close()
    except (HTTPException, TimeoutError, OSError) as exc:
        return ConnectionTestResult(provider, protocol, model, "failed", None, None, None, type(exc).__name__)
    finally:
        connection.close()

    parsed_response: dict[str, Any] = {}
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, dict):
            parsed_response = decoded
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    response_id = parsed_response.get("id") if isinstance(parsed_response.get("id"), str) else None
    usage = _safe_usage(parsed_response.get("usage"))
    return ConnectionTestResult(
        provider,
        protocol,
        model,
        "succeeded" if 200 <= status < 300 else "failed",
        status,
        response_id,
        usage,
        None if 200 <= status < 300 else f"upstream returned HTTP {status}",
    )
