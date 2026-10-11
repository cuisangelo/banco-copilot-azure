"""USD per 1M tokens, Azure OpenAI GlobalStandard list prices. Update with a dated commit when they change."""

PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 1.60),
    "text-embedding-3-small": (0.02, 0.0),
}


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICES_PER_MILLION[model]
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000
