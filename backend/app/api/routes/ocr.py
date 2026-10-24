"""OCR extraction endpoints.

Both routes are plain ``def``, so FastAPI runs them in a threadpool and a
multi-second OCR never blocks the event loop that serves heartbeats and
websockets. Concurrency is capped inside ocr_runner so simultaneous uploads
cannot multiply the model's memory footprint.
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models import User
from app.services import ocr_runner
from app.services.rates import ALL_CURRENCIES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr", tags=["ocr"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class OCRResponse(BaseModel):
    success: bool
    rates: Dict[str, Optional[str]]
    message: str


def _validate(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400, detail="Format harus PNG, JPG, WEBP, atau BMP."
        )


def _read(file: UploadFile) -> bytes:
    data = file.file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Ukuran gambar maksimal 10MB.")
    if not data:
        raise HTTPException(status_code=400, detail="File gambar kosong.")
    return data


def _to_strings(raw: Dict[str, float]) -> Dict[str, Optional[str]]:
    """Return every known currency, with unreadable ones as null rather than 0.

    The parser returns 0 for a currency it could not read. Zero would mean "the
    rate is zero", so it is translated to null here - the editor shows an empty
    field, and the board renders a dash.
    """
    out: Dict[str, Optional[str]] = {}
    for code in ALL_CURRENCIES:
        value = raw.get(code)
        if value is None or float(value) == 0:
            out[code] = None
        else:
            out[code] = format(float(value), "f").rstrip("0").rstrip(".")
    return out


@router.post("/upload", response_model=OCRResponse)
def upload_single(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Full-image OCR. Less accurate than the 3-block mode; kept as fallback."""
    _validate(file)
    data = _read(file)

    try:
        raw = ocr_runner.extract_from_image(data)
    except Exception:
        logger.exception("Single-image OCR failed")
        raise HTTPException(
            status_code=500,
            detail="Gagal membaca gambar. Coba gambar yang lebih jelas atau mode 3 crop.",
        )

    rates = _to_strings(raw)
    detected = sum(1 for v in rates.values() if v)
    return OCRResponse(
        success=True,
        rates=rates,
        message=f"Terbaca {detected} mata uang.",
    )


@router.post("/upload-blocks", response_model=OCRResponse)
def upload_blocks(
    left: UploadFile = File(...),
    middle: UploadFile = File(...),
    right: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Recommended path: three cropped columns, mapped to fixed row order."""
    for item in (left, middle, right):
        _validate(item)

    left_bytes = _read(left)
    middle_bytes = _read(middle)
    right_bytes = _read(right)

    try:
        raw = ocr_runner.extract_from_blocks(left_bytes, middle_bytes, right_bytes)
    except Exception:
        logger.exception("Block OCR failed")
        raise HTTPException(
            status_code=500,
            detail="Gagal membaca gambar. Pastikan crop kolom sudah benar.",
        )

    rates = _to_strings(raw)
    detected = sum(1 for v in rates.values() if v)
    return OCRResponse(
        success=True,
        rates=rates,
        message=f"Terbaca {detected} mata uang dari 3 blok.",
    )
