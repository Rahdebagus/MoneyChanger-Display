"""The board design must not drift.

This is the regression test that matters most: the owner already approved how
the board looks, so a refactor is only correct if the rendered pixels are
unchanged. The fixture is checked in next to this file and compared byte for
byte.

The PNG the generator writes is deterministic for a fixed input - no
timestamp, no random ordering - so an exact comparison is honest here rather
than a tolerance that could hide a layout shift. Flags come from the on-disk
cache, which holds exactly the bytes the CDN returned.
"""

import hashlib
import json
from pathlib import Path

import pytest

from app.services.generator import generate_rate_image
from app.services.rates import ALL_CURRENCIES, LEFT_LAYOUT, RIGHT_LAYOUT

FIXTURE_DIR = Path(__file__).parent / "fixtures"
RATES_FILE = FIXTURE_DIR / "baseline_rates.json"
BOARD_FILE = FIXTURE_DIR / "baseline_board.png"


def _load_rates():
    return json.loads(RATES_FILE.read_text(encoding="utf-8"))


@pytest.mark.skipif(not BOARD_FILE.exists(), reason="baseline board fixture missing")
def test_board_is_byte_identical_to_baseline():
    expected = BOARD_FILE.read_bytes()
    produced = generate_rate_image(_load_rates())

    assert hashlib.sha256(produced).hexdigest() == hashlib.sha256(expected).hexdigest(), (
        "Generated board differs from the approved baseline. "
        "If this change is intentional, regenerate the fixture deliberately."
    )


@pytest.mark.skipif(not BOARD_FILE.exists(), reason="baseline board fixture missing")
def test_board_generation_is_deterministic():
    rates = _load_rates()
    first = generate_rate_image(rates)
    second = generate_rate_image(rates)
    assert first == second


def test_board_dimensions_unchanged():
    """Resolution is part of the design and must not be reduced for speed."""
    import io

    from PIL import Image

    png = generate_rate_image(_load_rates())
    with Image.open(io.BytesIO(png)) as img:
        assert img.size == (1280, 720)


def test_layout_order_matches_the_board():
    """USD sub-rows sit directly under USD, in the order the board draws them."""
    assert LEFT_LAYOUT[:4] == ["USD", "USD_T", "USD_K", "AUD"]
    assert LEFT_LAYOUT[-1] == "MYR"
    assert RIGHT_LAYOUT[0] == "NZD"
    assert RIGHT_LAYOUT[-1] == "NTD"
    assert len(ALL_CURRENCIES) == 22


def test_missing_rate_renders_as_dash_not_zero():
    """A currency with no value must not silently become 0."""
    from app.services.mapper import format_rate

    assert format_rate("AUD", None) == "-"
    assert format_rate("AUD", 12050) == "12.050"


def test_jpy_and_krw_keep_their_special_formatting():
    from app.services.mapper import format_rate

    assert format_rate("JPY", 105.25) == "105.25"
    assert format_rate("KRW", 10) == "10"
    assert format_rate("THB", 475) == "475"
    assert format_rate("USD", 16950) == "16.950"
