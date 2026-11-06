"""Per-provider pricing.

Cartesia bills roughly one credit per character; ElevenLabs bills credits scaled by the selected
model's ``character_cost_multiplier``. Rates therefore cannot share one formula, so each provider
has its own estimator here. Rates are stored on the provider row (``models[].unit_cost``) when an
operator has a contract rate; otherwise the list price below is used and the result is marked as
an estimate. Actual billed cost is only recorded when the provider reports it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Published list prices in USD per character (update when providers change pricing).
LIST_PRICE_PER_CHAR: dict[str, float] = {
    "cartesia": 0.000065,   # ≈1 credit/char
    "elevenlabs": 0.00012,  # standard plan, multiplier 1.0
    "mock": 0.0,
}


@dataclass(slots=True)
class CostEstimate:
    provider: str
    model: str
    characters: int
    unit_price: float
    multiplier: float
    estimated_usd: float
    source: str  # "provider_config" | "list_price" | "none"
    unit_label: str = "char"


def model_price(models: list[dict[str, Any]] | None, model_id: str) -> float | None:
    for entry in models or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") != model_id:
            continue
        for key in ("unit_cost", "cost_per_char", "unit_price"):
            value = entry.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
    return None


def estimate(
    *,
    provider: str,
    model: str,
    characters: int,
    models: list[dict[str, Any]] | None = None,
    multiplier: float = 1.0,
) -> CostEstimate:
    configured = model_price(models, model)
    if configured is not None:
        return CostEstimate(provider, model, characters, configured, 1.0,
                            round(characters * configured, 6), "provider_config")
    list_price = LIST_PRICE_PER_CHAR.get(provider)
    if list_price is None:
        return CostEstimate(provider, model, characters, 0.0, multiplier, 0.0, "none")
    total = characters * list_price * multiplier
    return CostEstimate(provider, model, characters, list_price, multiplier, round(total, 6),
                        "list_price")
