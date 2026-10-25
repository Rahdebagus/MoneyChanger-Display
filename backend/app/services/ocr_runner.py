"""Bounded OCR execution.

Two things this guards against:

* **RAM**: PaddleOCR holds its models in process memory. A semaphore caps how
  many images are in flight so N simultaneous uploads cannot multiply the
  model's working set.
* **The event loop**: the engine is synchronous C++ underneath. Routes call
  these functions from a threadpool (a plain ``def`` endpoint in FastAPI), so
  a 4-second OCR never blocks heartbeats or the websocket.

The heavy paddle import is deferred to first use, so an API process that only
serves auth, history and display traffic never pays for it.
"""

import io
import logging
from contextlib import contextmanager

from PIL import Image
import threading
from typing import Dict, List

logger = logging.getLogger(__name__)

# One engine per process, built once. PaddleOCR predictors are not documented
# as thread-safe, so a lock serialises inference rather than risking corrupt
# state across threads.
_MAX_CONCURRENT = 1
_slots = threading.Semaphore(_MAX_CONCURRENT)
_engine_lock = threading.Lock()
_warmed = False


def _ensure_engine():
    """Import and build the engine exactly once, under a lock."""
    global _warmed
    from app.services.ocr import get_ocr_engine

    with _engine_lock:
        engine = get_ocr_engine()
        _warmed = True
    return engine


def is_warm() -> bool:
    return _warmed


class OCRBusy(Exception):
    pass


def validate_image(data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 8_000_000:
                raise ValueError("Gambar maksimal 8 juta piksel. Perkecil atau crop gambar.")
            image.verify()
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("File gambar tidak valid.") from exc


@contextmanager
def _slot():
    if not _slots.acquire(timeout=1):
        raise OCRBusy("OCR sedang digunakan. Coba lagi sebentar.")
    try:
        yield
    finally:
        _slots.release()


def extract_from_image(image_bytes: bytes) -> Dict[str, float]:
    with _slot():
        _ensure_engine()
        from app.services.ocr import extract_rates_from_image
        return extract_rates_from_image(image_bytes)


def extract_from_blocks(left_bytes: bytes, middle_bytes: bytes, right_bytes: bytes) -> Dict[str, float]:
    with _slot():
        _ensure_engine()
        from app.services.ocr import extract_rates_from_blocks
        return extract_rates_from_blocks(left_bytes, middle_bytes, right_bytes)


def supported_mime_types() -> List[str]:
    return ["image/jpeg", "image/png", "image/webp", "image/bmp"]
