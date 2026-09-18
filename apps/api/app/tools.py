"""Short-lived capability tokens for scoped worker tool calls."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from uuid import UUID


class InvalidCapability(ValueError):
    """Raised when a capability is malformed, expired or out of scope."""


@dataclass(frozen=True)
class Capability:
    project_id: UUID
    job_id: UUID | None
    generation: int
    tool: str
    expires_at: int


def issue_capability(
    secret: str,
    *,
    project_id: UUID,
    job_id: UUID | None,
    generation: int,
    tool: str,
    ttl_seconds: int = 300,
) -> str:
    """Sign a bounded capability without persisting or returning the secret."""

    if not secret or ttl_seconds < 1 or ttl_seconds > 3600:
        raise ValueError("invalid capability settings")
    payload = {
        "project_id": str(project_id),
        "job_id": str(job_id) if job_id else None,
        "generation": generation,
        "tool": tool,
        "expires_at": int(time.time()) + ttl_seconds,
    }
    encoded = _encode(payload)
    signature = hmac.new(secret.encode(), encoded, hashlib.sha256).digest()
    return f"{_b64(encoded)}.{_b64(signature)}"


def verify_capability(
    token: str,
    secret: str,
    *,
    project_id: UUID,
    job_id: UUID | None,
    generation: int,
    tool: str,
) -> Capability:
    """Verify every scope field, including the current fencing generation."""

    try:
        encoded_part, signature_part = token.split(".", 1)
        encoded = _unb64(encoded_part)
        signature = _unb64(signature_part)
        expected = hmac.new(secret.encode(), encoded, hashlib.sha256).digest()
        payload = json.loads(encoded)
        capability = Capability(
            project_id=UUID(payload["project_id"]),
            job_id=UUID(payload["job_id"]) if payload["job_id"] else None,
            generation=int(payload["generation"]),
            tool=str(payload["tool"]),
            expires_at=int(payload["expires_at"]),
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise InvalidCapability("invalid capability") from None
    if not hmac.compare_digest(signature, expected):
        raise InvalidCapability("invalid capability")
    if capability.expires_at < int(time.time()):
        raise InvalidCapability("expired capability")
    if (
        capability.project_id != project_id
        or capability.job_id != job_id
        or capability.generation != generation
        or capability.tool != tool
    ):
        raise InvalidCapability("capability scope mismatch")
    return capability


def _encode(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
