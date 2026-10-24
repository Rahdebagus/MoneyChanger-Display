"""
parser.py - OCR Data Cleaning & Currency Extraction
Stable parser for Authorized Money Changer / BI rate board layout.
Supports block OCR: left, middle, right.
"""

import re
from typing import Dict, List

LEFT_CODES = ["USD", "AUD", "EUR", "GBP", "CHF", "JPY", "SGD", "CAD"]
MIDDLE_CODES = ["MYR", "NZD", "HKD", "CNY", "BND", "SAR", "AED", "THB"]
RIGHT_CODES = ["PHP", "KRW", "INR", "NTD"]

CURRENCIES = set(LEFT_CODES + MIDDLE_CODES + RIGHT_CODES)

ALIASES = {
    "EURO": "EUR",
    "EU": "EUR",
}

NOISE_PATTERNS = [
    r"RATE\s*TODAY",
    r"RATES\s*CAN\s*CHANGE",
    r"AT\s*ANYTIME",
    r"CURRENCIES",
    r"CURENCIES",
    r"MONEY\s*CHANGER",
    r"WWW",
    r"AUTHORIZED",
    r"WITA",
    r"APVA",
    r"BPD",
    r"BALI",
    r"AFILIASI",
    r"PEDAGANG",
    r"VALUTA",
    r"ASING",
    r"APRIL",
]

DATE_TIME_NOISE = {0, 11, 15, 27, 28, 2026, 1100, 1500}


def is_noise(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in NOISE_PATTERNS)


def normalize_code(token: str) -> str | None:
    token = token.upper().strip()
    token = re.sub(r"[^A-Z]", "", token)
    token = ALIASES.get(token, token)
    return token if token in CURRENCIES else None


def normalize_rate(raw: str) -> float | None:
    cleaned = re.sub(r"[^\d.,]", "", raw.strip())
    if not cleaned:
        return None

    # Indonesian decimal: 104,25 -> 104.25
    if re.fullmatch(r"\d+,\d{2}", cleaned):
        return float(cleaned.replace(",", "."))

    # Thousand separator: 16.800 / 9.850 / 12.000 -> 16800 / 9850 / 12000
    if re.fullmatch(r"\d{1,3}\.\d{3}", cleaned):
        return float(cleaned.replace(".", ""))

    # Decimal point: 10.00 -> 10
    if re.fullmatch(r"\d+\.\d{1,2}", cleaned):
        return float(cleaned)

    if re.fullmatch(r"\d+", cleaned):
        return float(cleaned)

    try:
        return float(cleaned.replace(",", "."))
    except ValueError:
        return None


def extract_numbers(text: str) -> List[float]:
    candidates = re.findall(r"\d{1,3}(?:[.,]\d{2,3})?|\d+", text)
    values: List[float] = []
    for c in candidates:
        val = normalize_rate(c)
        if val is not None and val > 0 and val not in DATE_TIME_NOISE:
            values.append(val)
    return values


def _clean_texts(raw_texts: List[str]) -> List[str]:
    return [t.strip() for t in raw_texts if t and not is_noise(t)]


def _parse_block_by_numbers(raw_texts: List[str], codes: List[str]) -> Dict[str, float]:
    """Map numbers in one cropped block to the fixed row order for that block."""
    clean_texts = _clean_texts(raw_texts)
    nums: List[float] = []
    for text in clean_texts:
        nums.extend(extract_numbers(text))

    rates: Dict[str, float] = {}
    for code, value in zip(codes, nums):
        rates[code] = value
    return rates


def parse_ocr_blocks(raw_blocks: Dict[str, List[str]]) -> Dict[str, float]:
    """
    Parse OCR text from 3 separate cropped blocks.
    Expected keys: LEFT, MIDDLE, RIGHT.
    """
    rates: Dict[str, float] = {}
    rates.update(_parse_block_by_numbers(raw_blocks.get("LEFT", []), LEFT_CODES))
    rates.update(_parse_block_by_numbers(raw_blocks.get("MIDDLE", []), MIDDLE_CODES))
    rates.update(_parse_block_by_numbers(raw_blocks.get("RIGHT", []), RIGHT_CODES))

    # keep all currencies visible in frontend
    for code in CURRENCIES:
        rates.setdefault(code, 0)
    return rates


def parse_ocr_results(raw_texts: List[str]) -> Dict[str, float]:
    """
    Fallback parser for one full image.
    It tokenizes OCR output and pairs each currency code with the next nearby number.
    For best accuracy, use parse_ocr_blocks via /upload-blocks.
    """
    clean_texts = _clean_texts(raw_texts)
    tokens: List[str] = []
    for text in clean_texts:
        tokens.extend([p for p in re.split(r"[\s\|/\\:]+", text) if p.strip()])

    rates: Dict[str, float] = {}
    i = 0
    while i < len(tokens):
        code = normalize_code(tokens[i])
        if code:
            for j in range(i + 1, min(i + 7, len(tokens))):
                if normalize_code(tokens[j]):
                    break
                value = normalize_rate(tokens[j])
                if value is not None and value > 0 and value not in DATE_TIME_NOISE:
                    rates[code] = value
                    i = j
                    break
        i += 1

    for code in CURRENCIES:
        rates.setdefault(code, 0)
    return rates
