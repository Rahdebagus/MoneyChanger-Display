import io
import os
from functools import lru_cache
from typing import Dict
from PIL import Image, ImageDraw, ImageFont
from app.core.config import get_settings
from app.services.mapper import get_ordered_rates, format_rate

IMG_W = 1280
IMG_H = 720

_settings = get_settings()

# Asset and cache locations come from configuration, never from a path baked
# into this file, so the package can move without breaking the board.
ASSET_DIR = str(_settings.assets_path)
FLAG_CACHE_DIR = str(_settings.flag_cache_path)

BG_PATH = os.path.join(ASSET_DIR, "pam_bg.png")


C_HEADER = (85, 195, 225)
C_ROW1 = (207, 234, 246)
C_ROW2 = (232, 245, 251)
C_GRID = (255, 255, 255)
C_BLACK = (0, 0, 0)


# Currency flags are bundled locally; rendering never waits for a CDN.
CURRENCY_TO_CC = {
    "USD":   "us",
    "USD T": "us",
    "USD K": "us",
    "AUD":   "au",
    "EUR":   "eu",
    "GBP":   "gb",
    "CHF":   "ch",
    "JPY":   "jp",
    "SGD":   "sg",
    "CAD":   "ca",
    "MYR":   "my",
    "NZD":   "nz",
    "HKD":   "hk",
    "CNY":   "cn",
    "BND":   "bn",
    "SAR":   "sa",
    "AED":   "ae",
    "THB":   "th",
    "PHP":   "ph",
    "KRW":   "kr",
    "INR":   "in",
    "NTD":   "tw",
}

_flag_cache: Dict[str, Image.Image | None] = {}


def _fetch_flag(cc: str) -> Image.Image:
    if cc in _flag_cache:
        return _flag_cache[cc]
    candidates = [os.path.join(FLAG_CACHE_DIR, f"{cc}.png"),
                  os.path.join(ASSET_DIR, "flags", f"{cc}.png")]
    for filename in candidates:
        if os.path.isfile(filename):
            with Image.open(filename) as source:
                flag = source.convert("RGBA")
            _flag_cache[cc] = flag
            return flag
    raise FileNotFoundError(f"Missing bundled flag: {cc}.png")


@lru_cache(maxsize=48)
def _get_flag(currency_code: str, target_h: int = 32) -> Image.Image | None:
    """Return a flag image scaled to *target_h* pixels tall for *currency_code*.
    Using a higher-res CDN source (h80) ensures sharpness at the display size.
    """
    cc = CURRENCY_TO_CC.get(currency_code)
    if cc is None:
        return None
    flag = _fetch_flag(cc)
    if flag is None:
        return None
    ratio = target_h / flag.height
    new_w = max(1, int(flag.width * ratio))
    return flag.resize((new_w, target_h), Image.LANCZOS)


# -----------------------------------------------------------------------


@lru_cache(maxsize=32)
def load_font(size: int, bold: bool = False):
    paths = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


def text_center(draw, box, text, font, fill=C_BLACK):
    x1, y1, x2, y2 = box
    draw.text(
        ((x1 + x2) / 2, (y1 + y2) / 2),
        text,
        font=font,
        fill=fill,
        anchor="mm",
    )


DEFAULT_LOGO_PATH = os.path.join(ASSET_DIR, "pam_logo.png")
LOGO_W = 165        # rendered width in pixels
LOGO_PASTE_X = 60   # left edge of logo
HEADER_H = 130      # top region height


def draw_logo(img: Image.Image, logo_bytes: bytes | None = None):
    """Draw the PAM logo (or a custom one) at the top-left of the header."""
    logo_img = None

    if logo_bytes is not None:
        with Image.open(io.BytesIO(logo_bytes)) as source:
            if (source.width * source.height > 4_000_000 or max(source.size) > 4096
                    or source.height * LOGO_W / source.width > 2048):
                raise ValueError("Logo dimensions exceed rendering limits")
            logo_img = source.convert("RGBA")

    if logo_img is None and os.path.exists(DEFAULT_LOGO_PATH):
        try:
            logo_img = Image.open(DEFAULT_LOGO_PATH).convert("RGBA")
        except Exception:
            pass

    if logo_img is None:
        return

    ratio = LOGO_W / logo_img.width
    logo_h = int(logo_img.height * ratio)
    logo_img = logo_img.resize((LOGO_W, logo_h), Image.LANCZOS)

    paste_y = max(0, (HEADER_H - logo_h) // 2)
    img.paste(logo_img, (LOGO_PASTE_X, paste_y), logo_img)


def draw_title(draw, title: str = "MONEY CHANGER", subtitle: str = "PT. PRADNYANA ARTHA MANDIRI"):
    font_title = load_font(58, bold=True)
    font_sub = load_font(25, bold=True)

    draw.text((640, 55), title, font=font_title, fill=C_BLACK, anchor="mm")
    draw.text((640, 102), subtitle, font=font_sub, fill=C_BLACK, anchor="mm")


def _paste_flag(img: Image.Image, flag: Image.Image, cx: float, cy: float):
    """Paste *flag* (RGBA) centred at pixel (cx, cy) onto *img*."""
    x = int(cx - flag.width / 2)
    y = int(cy - flag.height / 2)
    img.paste(flag, (x, y), flag)


def draw_table(draw, rates: Dict[str, float], img: Image.Image | None = None):
    """Draw the exchange-rate table.

    *img* is the backing PIL Image; it is needed only to paste flag bitmaps.
    When None the table is drawn without flags (backward-compatible).
    """
    ordered = get_ordered_rates(rates)
    left_rows = ordered["left"]
    right_rows = ordered["right"]

    table_x = 160
    table_y = 130
    table_w = 950
    header_h = 44
    footer_h = 44

    half_w = table_w // 2
    code_w = 235
    rate_w = 240

    left_x = table_x
    right_x = table_x + half_w

    row_count = max(len(left_rows), len(right_rows))
    row_h = 45

    font_head = load_font(28, bold=True)
    font_code = load_font(27, bold=True)
    font_rate = load_font(27, bold=True)
    font_sub = load_font(16, bold=True)
    font_footer = load_font(27, bold=True)

    # --- Flag dimensions ---
    FLAG_H = 24          # target display height — flags scaled to this
    FLAG_SLOT_W = 44     # fixed-width container — flag centred inside, text always aligns
    FLAG_GAP = 16        # margin between slot right-edge and text (keeps them apart)

    # Header
    draw.rectangle([table_x, table_y, table_x + table_w, table_y + header_h], fill=C_HEADER)

    # Header text
    text_center(draw, [left_x, table_y, left_x + code_w, table_y + header_h], "CURRENCIES", font_head, (255, 255, 255))
    text_center(draw, [left_x + code_w, table_y, left_x + half_w, table_y + header_h], "RATE", font_head, (255, 255, 255))
    text_center(draw, [right_x, table_y, right_x + code_w, table_y + header_h], "CURRENCIES", font_head, (255, 255, 255))
    text_center(draw, [right_x + code_w, table_y, right_x + half_w, table_y + header_h], "RATE", font_head, (255, 255, 255))

    start_y = table_y + header_h

    for i in range(row_count):
        y1 = start_y + (i * row_h)
        y2 = y1 + row_h
        bg = C_ROW1 if i % 2 == 0 else C_ROW2
        row_cy = (y1 + y2) / 2          # vertical centre of row

        draw.rectangle([table_x, y1, table_x + table_w, y2], fill=bg)

        def draw_currency_cell(cell_x1, cell_x2, code, flag_img, y1, y2, row_cy, is_usd_variant=False, sub_label=None):
            """Draw flag (scaled, in fixed slot) + left-aligned label.
            Flag slot starts with a small left margin from cell_x1.
            Text always starts at cell_x1 + LEFT_PAD + FLAG_SLOT_W + FLAG_GAP
            so every row has the same left edge — true left alignment.
            """
            LEFT_PAD = 20   # margin from cell edge to flag slot

            # Flag: centred inside the fixed slot
            slot_x1 = cell_x1 + LEFT_PAD
            if flag_img is not None:
                flag_cx = slot_x1 + FLAG_SLOT_W / 2
                flag_x = int(flag_cx - flag_img.width / 2)
                flag_y = int(row_cy - flag_img.height / 2)
                img.paste(flag_img, (flag_x, flag_y), flag_img)

            # Text: fixed x for every row regardless of flag width
            text_x = slot_x1 + FLAG_SLOT_W + FLAG_GAP

            if is_usd_variant and sub_label:
                draw.text((text_x, y1 + 16), code, font=font_code, fill=C_BLACK, anchor="lm")
                draw.text((text_x, y1 + 36), sub_label, font=font_sub, fill=C_BLACK, anchor="lm")
            else:
                draw.text((text_x, row_cy), code, font=font_code, fill=C_BLACK, anchor="lm")

        # ---- LEFT column ------------------------------------------------
        if i < len(left_rows):
            code, val = left_rows[i]
            rate = format_rate(code.replace(" ", ""), val) if val is not None else "-"

            flag_img = _get_flag(code, target_h=FLAG_H) if img is not None else None
            cell_x1 = left_x
            cell_x2 = left_x + code_w

            usd_subs = {"USD": "(100, 50)", "USD T": "(20, 10, 5)", "USD K": "(1, 2)"}
            if code in usd_subs:
                draw_currency_cell(cell_x1, cell_x2, code, flag_img, y1, y2, row_cy,
                                   is_usd_variant=True, sub_label=usd_subs[code])
            else:
                draw_currency_cell(cell_x1, cell_x2, code, flag_img, y1, y2, row_cy)

            # rate
            text_center(draw, [left_x + code_w, y1, left_x + half_w, y2], rate, font_rate)

        # ---- RIGHT column -----------------------------------------------
        if i < len(right_rows):
            code, val = right_rows[i]
            rate = format_rate(code, val) if val is not None else "-"

            flag_img = _get_flag(code, target_h=FLAG_H) if img is not None else None
            cell_x1 = right_x
            cell_x2 = right_x + code_w

            draw_currency_cell(cell_x1, cell_x2, code, flag_img, y1, y2, row_cy)
            text_center(draw, [right_x + code_w, y1, right_x + half_w, y2], rate, font_rate)

        # horizontal line
        draw.line([table_x, y2, table_x + table_w, y2], fill=C_GRID, width=1)

    bottom_y = start_y + (row_count * row_h)

    # Vertical grid
    draw.line([left_x + code_w, table_y, left_x + code_w, bottom_y], fill=C_GRID, width=1)
    draw.line([right_x, table_y, right_x, bottom_y], fill=C_GRID, width=1)
    draw.line([right_x + code_w, table_y, right_x + code_w, bottom_y], fill=C_GRID, width=1)

    # Footer
    draw.rectangle([table_x, bottom_y, table_x + table_w, bottom_y + footer_h], fill=(232, 245, 251))
    text_center(
        draw,
        [table_x, bottom_y, table_x + table_w, bottom_y + footer_h],
        "RATES CAN CHANGE AT ANYTIME",
        font_footer,
    )


@lru_cache(maxsize=1)
def _background(path: str, modified_ns: int) -> Image.Image:
    with Image.open(path) as source:
        return source.convert("RGB").resize((IMG_W, IMG_H), Image.LANCZOS)


def generate_rate_image(
    rates: Dict[str, float],
    title: str = "MONEY CHANGER",
    subtitle: str = "PT. PRADNYANA ARTHA MANDIRI",
    logo_bytes: bytes | None = None,
) -> bytes:
    # Copy the cached template before drawing; never mutate the shared image.
    img = _background(BG_PATH, os.stat(BG_PATH).st_mtime_ns).copy()

    d = ImageDraw.Draw(img)

    draw_logo(img, logo_bytes=logo_bytes)
    draw_title(d, title=title, subtitle=subtitle)
    draw_table(d, rates, img=img)

    output = io.BytesIO()
    img.save(output, format="PNG", dpi=(150, 150))
    output.seek(0)

    return output.read()
