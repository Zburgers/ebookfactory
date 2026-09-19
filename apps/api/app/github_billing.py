"""Read-only GitHub Copilot billing evidence from the official REST API.

The local usage ledger is project-scoped and durable. GitHub billing is
account-scoped and intentionally remains live: the PAT is read from process
environment, sent only to GitHub, and never persisted or returned to the UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from typing import Any, Callable

from app.settings import Settings


GITHUB_BILLING_SOURCE = "github-rest-ai-credit-usage"
GITHUB_BILLING_URL = "https://docs.github.com/en/rest/billing/usage"
GITHUB_API_ROOT = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
MAX_ITEMS = 500


def _request_json(url: str, token: str, *, timeout_seconds: float) -> Any:
    """Fetch one GitHub JSON document without exposing the authorization header."""

    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "ebook-factory-usage",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed GitHub API host only
        return json.load(response)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _number(value: Any) -> int | float | None:
    decimal = _decimal(value)
    if decimal is None:
        return None
    if decimal == decimal.to_integral_value():
        return int(decimal)
    return float(decimal)


def _first(mapping: dict[str, Any], *names: str) -> Any:
    normalized = {str(key).replace("-", "_").lower(): value for key, value in mapping.items()}
    for name in names:
        value = normalized.get(name.replace("-", "_").lower())
        if value is not None:
            return value
    return None


def _candidate_items(payload: Any) -> list[dict[str, Any]]:
    """Find the official usage-item collection across REST response wrappers."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    preferred = (
        "usageItems",
        "usage_items",
        "items",
        "data",
        "results",
    )
    for key in preferred:
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
        if isinstance(candidate, dict):
            nested = _candidate_items(candidate)
            if nested:
                return nested
    for value in payload.values():
        nested = _candidate_items(value)
        if nested:
            return nested
    return []


def _normalise_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": _first(item, "date", "day", "usage_date", "usageDate"),
        "model": _first(item, "model", "model_name", "modelName") or "unknown",
        "unit_type": _first(item, "unit_type", "unitType") or "credits",
        "quantity": _number(_first(item, "gross_quantity", "grossQuantity", "quantity", "credits_used", "creditsUsed")),
        "price_per_unit": _number(_first(item, "price_per_unit", "pricePerUnit")),
        "gross_amount": _number(_first(item, "gross_amount", "grossAmount", "amount")),
        "discount_amount": _number(_first(item, "discount_amount", "discountAmount")),
        "net_amount": _number(_first(item, "net_amount", "netAmount")),
        "input_tokens": _number(_first(item, "input_tokens", "inputTokens", "uncached_input_tokens", "uncachedInputTokens")),
        "output_tokens": _number(_first(item, "output_tokens", "outputTokens")),
        "cache_read_tokens": _number(_first(item, "cache_read_tokens", "cacheReadTokens", "cached_input_tokens", "cachedInputTokens")),
        "cache_write_tokens": _number(_first(item, "cache_write_tokens", "cacheWriteTokens")),
    }


def _sum_items(items: list[dict[str, Any]], field: str) -> int | float | None:
    values = [_decimal(item.get(field)) for item in items]
    known = [value for value in values if value is not None]
    if not known:
        return None
    total = sum(known, Decimal(0))
    return _number(total)


def _account(settings: Settings) -> tuple[str, str | None, str | None]:
    account_type = (settings.github_billing_account_type or "user").strip().lower()
    if account_type in {"organization", "org"}:
        return "organization", settings.github_billing_organization, settings.github_billing_organization
    if account_type == "enterprise":
        return "enterprise", settings.github_billing_enterprise, settings.github_billing_enterprise
    return "user", settings.github_billing_username, settings.github_billing_username


def _endpoint(account_type: str, identifier: str, now: datetime) -> str:
    path = {
        "user": f"/users/{quote(identifier, safe='')}/settings/billing/ai_credit/usage",
        "organization": f"/organizations/{quote(identifier, safe='')}/settings/billing/ai_credit/usage",
        "enterprise": f"/enterprises/{quote(identifier, safe='')}/settings/billing/ai_credit/usage",
    }[account_type]
    return f"{GITHUB_API_ROOT}{path}?{urlencode({'year': now.year, 'month': now.month})}"


def _empty_result(*, status: str, configured: bool, now: datetime, error: str | None = None, account: dict[str, Any] | None = None, http_status: int | None = None, identity_verified: bool = False) -> dict[str, Any]:
    return {
        "status": status,
        "configured": configured,
        "identity_verified": identity_verified,
        "source": GITHUB_BILLING_SOURCE,
        "source_url": GITHUB_BILLING_URL,
        "fetched_at": now.isoformat(),
        "account": account or {"type": "user", "identifier": None},
        "period": {"year": now.year, "month": now.month},
        "items": [],
        "totals": {
            "ai_credits": None,
            "gross_amount": None,
            "discount_amount": None,
            "net_amount": None,
            "input_tokens": None,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
            "output_tokens": None,
        },
        "plan_fee": None,
        "allowance": None,
        "error": error,
        "http_status": http_status,
    }


def fetch_github_billing(
    settings: Settings,
    *,
    now: datetime | None = None,
    request_json: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Fetch the configured account's current-month GitHub AI-credit usage."""

    observed_at = now or datetime.now(timezone.utc)
    request_json = request_json or _request_json
    token = settings.github_billing_token
    if not token:
        return _empty_result(
            status="not_configured",
            configured=False,
            now=observed_at,
            error="Set GITHUB_BILLING_TOKEN (or the configured alias) for live GitHub billing evidence.",
        )

    account_type, configured_identifier, _ = _account(settings)
    account: dict[str, Any] = {"type": account_type, "identifier": configured_identifier}
    identity_verified = False
    try:
        identifier = configured_identifier
        if account_type == "user" and not identifier:
            profile = request_json(f"{GITHUB_API_ROOT}/user", token, timeout_seconds=settings.github_billing_timeout_seconds)
            identifier = str(profile.get("login") or "") if isinstance(profile, dict) else ""
            identity_verified = bool(identifier)
        if not identifier:
            return _empty_result(
                status="misconfigured",
                configured=True,
                now=observed_at,
                account=account,
                error=f"A GitHub {account_type} identifier is required for live billing usage.",
                identity_verified=identity_verified,
            )
        account["identifier"] = identifier
        url = _endpoint(account_type, identifier, observed_at)
        payload = request_json(url, token, timeout_seconds=settings.github_billing_timeout_seconds)
        items = [_normalise_item(item) for item in _candidate_items(payload)][:MAX_ITEMS]
        return {
            "status": "ok",
            "configured": True,
            "identity_verified": identity_verified,
            "source": GITHUB_BILLING_SOURCE,
            "source_url": GITHUB_BILLING_URL,
            "fetched_at": observed_at.isoformat(),
            "account": account,
            "period": {"year": observed_at.year, "month": observed_at.month},
            "items": items,
            "totals": {
                "ai_credits": _sum_items(items, "quantity"),
                "gross_amount": _sum_items(items, "gross_amount"),
                "discount_amount": _sum_items(items, "discount_amount"),
                "net_amount": _sum_items(items, "net_amount"),
                "input_tokens": _sum_items(items, "input_tokens"),
                "cache_read_tokens": _sum_items(items, "cache_read_tokens"),
                "cache_write_tokens": _sum_items(items, "cache_write_tokens"),
                "output_tokens": _sum_items(items, "output_tokens"),
            },
            "plan_fee": None,
            "allowance": None,
            "error": None,
        }
    except HTTPError as exc:
        return _empty_result(status="error", configured=True, now=observed_at, account=account, http_status=exc.code, error=f"GitHub billing returned HTTP {exc.code}.", identity_verified=identity_verified)
    except (URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
        return _empty_result(status="error", configured=True, now=observed_at, account=account, error=f"GitHub billing could not be read: {type(exc).__name__}.", identity_verified=identity_verified)
