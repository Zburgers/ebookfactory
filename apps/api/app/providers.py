"""Non-secret provider settings and connection status records."""

from dataclasses import dataclass
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
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError("provider endpoint must be an HTTP(S) URL without credentials")
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
