"""
mapper.py - Currency Mapping & Business Rule Application
"""

from typing import Dict

LEFT_COLUMN = ["USD", "AUD", "EUR", "GBP", "CHF", "JPY", "SGD", "CAD", "MYR"]
RIGHT_COLUMN = ["NZD", "HKD", "CNY", "BND", "SAR", "AED", "THB", "PHP", "KRW", "INR", "NTD"]

FLAGS = {
    "USD": "🇺🇸",
    "USD T": "🇺🇸",
    "USD K": "🇺🇸",
    "AUD": "🇦🇺",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "CHF": "🇨🇭",
    "JPY": "🇯🇵",
    "SGD": "🇸🇬",
    "CAD": "🇨🇦",
    "MYR": "🇲🇾",
    "NZD": "🇳🇿",
    "HKD": "🇭🇰",
    "CNY": "🇨🇳",
    "BND": "🇧🇳",
    "SAR": "🇸🇦",
    "AED": "🇦🇪",
    "THB": "🇹🇭",
    "PHP": "🇵🇭",
    "KRW": "🇰🇷",
    "INR": "🇮🇳",
    "NTD": "🇹🇼",
}

def apply_business_rules(rates: Dict[str, float]) -> Dict[str, float]:
    normalized = {}
    for k, v in rates.items():
        try:
            normalized[k.upper()] = float(v)
        except (TypeError, ValueError):
            continue

    if "USD" in normalized and normalized["USD"] > 0:
        usd = normalized["USD"]
        # Only auto-derive if not already provided by the user (manual edit)
        if "USD_T" not in normalized or normalized["USD_T"] == 0:
            normalized["USD_T"] = round(usd - 200, 2)
        if "USD_K" not in normalized or normalized["USD_K"] == 0:
            normalized["USD_K"] = 14000

    return normalized


def get_ordered_rates(rates: Dict[str, float]) -> Dict[str, list]:
    left = []
    right = []

    for code in LEFT_COLUMN:
        left.append((code, rates.get(code, None)))
        if code == "USD":
            left.append(("USD T", rates.get("USD_T", None)))
            left.append(("USD K", rates.get("USD_K", None)))

    for code in RIGHT_COLUMN:
        right.append((code, rates.get(code, None)))

    return {"left": left, "right": right}


def format_rate(code: str, value: float | None) -> str:
    if value is None or value == 0:
        return "-"

    code = code.replace(" ", "_")

    if code == "JPY":
        return f"{value:.2f}".rstrip("0").rstrip(".")

    if code == "KRW":
        return "10" if float(value).is_integer() else f"{value:.2f}"

    if value < 500:
        return f"{int(value)}"

    return f"{int(value):,}".replace(",", ".")