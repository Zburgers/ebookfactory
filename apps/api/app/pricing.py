"""Pinned, source-attributed token price cards for usage estimates.

These rates are reference prices, not invoices. Subscription providers may
include usage in a plan allowance or apply discounts that this local service
cannot observe.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


PRICE_VERSION = "2026-09-20"
MILLION = Decimal(1_000_000)
COPILOT_AI_CREDIT_USD = Decimal("0.01")
COPILOT_PRICING_URL = "https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing"
OPENAI_PRICING_URL = "https://developers.openai.com/api/docs/pricing/"


@dataclass(frozen=True)
class TokenRates:
    input: Decimal
    cache_read: Decimal
    cache_write: Decimal | None
    output: Decimal


@dataclass(frozen=True)
class PriceCard:
    model: str
    pricing_basis: str
    source_url: str
    default_rates: TokenRates
    long_context_threshold: int | None = None
    long_context_rates: TokenRates | None = None

    def rates_for(self, input_total: int) -> tuple[str, TokenRates]:
        if self.long_context_threshold is not None and self.long_context_rates is not None and input_total > self.long_context_threshold:
            return "long_context", self.long_context_rates
        return "default", self.default_rates


@dataclass(frozen=True)
class UsageEstimate:
    reference_usd: float | None
    cache_savings_usd: float | None
    copilot_ai_credits: float | None
    complete: bool
    rate_tier: str | None
    price_version: str | None
    pricing_basis: str | None
    source_url: str | None
    model: str
    components: dict[str, float]
    unknown_reason: str | None = None

    @property
    def known(self) -> bool:
        return self.reference_usd is not None


def _rates(input_price: str, cache_read: str, cache_write: str | None, output_price: str) -> TokenRates:
    return TokenRates(
        input=Decimal(input_price),
        cache_read=Decimal(cache_read),
        cache_write=Decimal(cache_write) if cache_write is not None else None,
        output=Decimal(output_price),
    )


def _openai_card(model: str, input_price: str, cache_read: str, cache_write: str | None, output_price: str, *, threshold: int | None = None, long: TokenRates | None = None) -> PriceCard:
    return PriceCard(
        model=model,
        pricing_basis="api_equivalent",
        source_url=OPENAI_PRICING_URL,
        default_rates=_rates(input_price, cache_read, cache_write, output_price),
        long_context_threshold=threshold,
        long_context_rates=long,
    )


def _copilot_card(model: str, input_price: str, cache_read: str, cache_write: str | None, output_price: str, *, threshold: int | None = None, long: TokenRates | None = None) -> PriceCard:
    return PriceCard(
        model=model,
        pricing_basis="github_ai_credits",
        source_url=COPILOT_PRICING_URL,
        default_rates=_rates(input_price, cache_read, cache_write, output_price),
        long_context_threshold=threshold,
        long_context_rates=long,
    )


_OPENAI_CARDS = {
    card.model: card
    for card in (
        _openai_card("gpt-5.4", "2.50", "0.25", None, "15.00", threshold=272_000, long=_rates("5.00", "0.50", None, "22.50")),
        _openai_card("gpt-5.4-mini", "0.75", "0.075", None, "4.50"),
        _openai_card("gpt-5.5", "5.00", "0.50", None, "30.00", threshold=272_000, long=_rates("10.00", "1.00", None, "45.00")),
        _openai_card("gpt-5.6-luna", "0.20", "0.02", "0.25", "1.20", threshold=272_000, long=_rates("0.40", "0.04", "0.50", "1.80")),
        _openai_card("gpt-5.6-sol", "4.00", "0.40", "5.00", "20.00", threshold=272_000, long=_rates("8.00", "0.80", "10.00", "30.00")),
        _openai_card("gpt-5.6-terra", "2.00", "0.20", "2.50", "12.00", threshold=272_000, long=_rates("4.00", "0.40", "5.00", "18.00")),
        _openai_card("gpt-6-astra", "10.00", "1.00", "12.50", "50.00", threshold=272_000, long=_rates("20.00", "2.00", "25.00", "75.00")),
    )
}


_COPILOT_CARDS = {
    card.model: card
    for card in (
        _copilot_card("gpt-5-mini", "0.25", "0.025", None, "2.00"),
        _copilot_card("gpt-5.3-codex", "1.75", "0.175", None, "14.00"),
        _copilot_card("gpt-5.4", "2.50", "0.25", None, "15.00", threshold=272_000, long=_rates("5.00", "0.50", None, "22.50")),
        _copilot_card("gpt-5.4-mini", "0.75", "0.075", None, "4.50"),
        _copilot_card("gpt-5.4-nano", "0.20", "0.02", None, "1.25"),
        _copilot_card("gpt-5.5", "5.00", "0.50", None, "30.00", threshold=272_000, long=_rates("10.00", "1.00", None, "45.00")),
        _copilot_card("gpt-5.6-luna", "0.20", "0.02", "0.25", "1.20", threshold=200_000, long=_rates("0.40", "0.04", "0.50", "1.80")),
        _copilot_card("gpt-5.6-sol", "4.00", "0.40", "5.00", "20.00", threshold=272_000, long=_rates("8.00", "0.80", "10.00", "30.00")),
        _copilot_card("gpt-5.6-terra", "2.00", "0.20", "2.50", "12.00", threshold=272_000, long=_rates("4.00", "0.40", "5.00", "18.00")),
        _copilot_card("gpt-6-astra", "10.00", "1.00", "12.50", "50.00", threshold=272_000, long=_rates("20.00", "2.00", "25.00", "75.00")),
        _copilot_card("claude-haiku-4.5", "1.00", "0.10", "1.25", "5.00"),
        _copilot_card("claude-sonnet-4.6", "3.00", "0.30", "3.75", "15.00"),
        _copilot_card("claude-sonnet-5", "2.00", "0.20", "2.50", "10.00"),
        _copilot_card("claude-opus-4.7", "5.00", "0.50", "6.25", "25.00"),
        _copilot_card("claude-opus-4.8", "5.00", "0.50", "6.25", "25.00"),
        _copilot_card("claude-opus-5", "5.00", "0.50", "6.25", "25.00"),
        _copilot_card("claude-fable-5", "10.00", "1.00", "12.50", "50.00"),
        _copilot_card("claude-fable-5.1", "10.00", "0.25", "12.50", "50.00"),
        _copilot_card("gemini-3.5-flash", "1.50", "0.15", None, "9.00"),
        _copilot_card("gemini-3.6-flash", "0.75", "0.075", None, "3.75"),
        _copilot_card("gemini-3.7-flash", "0.75", "0.075", None, "3.75"),
        _copilot_card("gemini-3.8-flash", "0.75", "0.075", None, "3.75"),
        _copilot_card("mai-code-1.1-flash", "0.20", "0.02", None, "1.20"),
        _copilot_card("kimi-k2.7-code", "0.95", "0.19", None, "4.00"),
        _copilot_card("kimi-k3", "3.00", "0.30", None, "15.00"),
    )
}


def _normalized_model(provider: str, model: str) -> str:
    value = model.strip().lower()
    prefix = f"{provider.strip().lower()}/"
    if value.startswith(prefix):
        value = value[len(prefix):]
    return value


def price_card(provider: str, model: str) -> PriceCard | None:
    provider_name = provider.strip().lower()
    normalized = _normalized_model(provider_name, model)
    if provider_name == "github-copilot":
        return _COPILOT_CARDS.get(normalized)
    if provider_name in {"openai", "openai-codex"}:
        return _OPENAI_CARDS.get(normalized)
    return None


def _rounded(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))


def estimate_usage(
    *,
    provider: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
) -> UsageEstimate:
    card = price_card(provider, model)
    if card is None:
        return UsageEstimate(
            reference_usd=None,
            cache_savings_usd=None,
            copilot_ai_credits=None,
            complete=False,
            rate_tier=None,
            price_version=None,
            pricing_basis=None,
            source_url=None,
            model=model,
            components={},
            unknown_reason="no verified price card for provider/model",
        )

    input_total = sum(value or 0 for value in (input_tokens, cache_read_tokens, cache_write_tokens))
    rate_tier, rates = card.rates_for(input_total)
    token_values = {
        "input": (input_tokens, rates.input),
        "cache_read": (cache_read_tokens, rates.cache_read),
        "cache_write": (cache_write_tokens, rates.cache_write),
        "output": (output_tokens, rates.output),
    }
    components: dict[str, float] = {}
    missing_dimensions: list[str] = []
    unsupported_dimensions: list[str] = []
    total = Decimal(0)
    known_token_dimension = False
    for name, (tokens, rate) in token_values.items():
        if tokens is None:
            # A provider can publish no price for a dimension at all (for
            # example cache writes on some OpenAI cards). Missing data for
            # that unsupported dimension is not an accounting unknown.
            if rate is not None:
                missing_dimensions.append(name)
            continue
        known_token_dimension = True
        if rate is None:
            if tokens:
                unsupported_dimensions.append(name)
            continue
        component = Decimal(tokens) * rate / MILLION
        components[name] = _rounded(component)
        total += component

    if not known_token_dimension:
        return UsageEstimate(
            reference_usd=None,
            cache_savings_usd=None,
            copilot_ai_credits=None,
            complete=False,
            rate_tier=rate_tier,
            price_version=PRICE_VERSION,
            pricing_basis=card.pricing_basis,
            source_url=card.source_url,
            model=model,
            components=components,
            unknown_reason="no token dimensions were reported",
        )

    complete = not missing_dimensions and not unsupported_dimensions
    reasons = []
    if missing_dimensions:
        reasons.append("missing token dimensions: " + ", ".join(missing_dimensions))
    if unsupported_dimensions:
        reasons.append("price card has no rate for: " + ", ".join(unsupported_dimensions))
    reference_usd = _rounded(total)
    cache_savings = Decimal(0)
    if cache_read_tokens is not None and rates.input > rates.cache_read:
        cache_savings = Decimal(cache_read_tokens) * (rates.input - rates.cache_read) / MILLION
    credits = _rounded(total / COPILOT_AI_CREDIT_USD) if card.pricing_basis == "github_ai_credits" else None
    return UsageEstimate(
        reference_usd=reference_usd,
        cache_savings_usd=_rounded(cache_savings),
        copilot_ai_credits=credits,
        complete=complete,
        rate_tier=rate_tier,
        price_version=PRICE_VERSION,
        pricing_basis=card.pricing_basis,
        source_url=card.source_url,
        model=model,
        components=components,
        unknown_reason="; ".join(reasons) if reasons else None,
    )


def price_card_summary(provider: str, model: str) -> dict[str, object] | None:
    card = price_card(provider, model)
    if card is None:
        return None
    return {
        "provider": provider,
        "model": model,
        "pricing_basis": card.pricing_basis,
        "source_url": card.source_url,
        "price_version": PRICE_VERSION,
        "input_per_million": float(card.default_rates.input),
        "cache_read_per_million": float(card.default_rates.cache_read),
        "cache_write_per_million": float(card.default_rates.cache_write) if card.default_rates.cache_write is not None else None,
        "output_per_million": float(card.default_rates.output),
        "long_context_threshold": card.long_context_threshold,
    }


def pricing_catalog(provider: str | None = None) -> list[dict[str, object]]:
    """Return the pinned cards available for the requested provider family."""

    families = {
        "openai-codex": _OPENAI_CARDS,
        "openai": _OPENAI_CARDS,
        "github-copilot": _COPILOT_CARDS,
    }
    selected = [provider.strip().lower()] if provider and provider.strip().lower() in families else list(families) if provider is None else []
    cards: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for family in selected:
        for model in families[family]:
            key = (family, model)
            if key in seen:
                continue
            seen.add(key)
            summary = price_card_summary(family, model)
            if summary:
                cards.append(summary)
    return cards
