"""Compatibility shims for the pre-2.0 flat API.

These keep the original paths and response shapes alive so anything still
calling /upload, /upload-blocks, /generate keeps working
while callers migrate to /api.

**One deliberate change**: they now require authentication. The originals were
open to anyone who could reach the port, and section 7 of the specification
requires authorization on every request. Leaving an unauthenticated OCR and
image-generation endpoint mounted would have contradicted that, so the shims
authenticate while keeping the request and response formats identical. Set
ENABLE_LEGACY_API=false to unmount them entirely.
"""

import io
import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.routes.ocr import _read
from app.services.direct_save import decode_logo, render_slot, SaveError

from app.api.deps import get_current_user
from app.models import User
from app.services import ocr_runner
from app.services.generator import generate_rate_image
from app.services.mapper import apply_business_rules

logger = logging.getLogger(__name__)
router = APIRouter(tags=["legacy"], include_in_schema=False)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}


def _validate_image(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only image files are accepted.")


@router.post("/upload")
def upload_rate_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    _validate_image(file)
    try:
        raw_rates = ocr_runner.extract_from_image(_read(file))
    except (ocr_runner.OCRBusy, SaveError) as exc:
        raise HTTPException(status_code=getattr(exc, "status", 503), detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Legacy single-image OCR failed")
        raise HTTPException(status_code=500, detail="OCR processing failed.")

    enriched = apply_business_rules(raw_rates)
    return {
        "success": True,
        "rates": enriched,
        "message": f"Extracted {len(raw_rates)} currencies.",
    }


@router.post("/upload-blocks")
def upload_rate_blocks(
    left: UploadFile = File(...),
    middle: UploadFile = File(...),
    right: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    for item in (left, middle, right):
        _validate_image(item)

    try:
        raw_rates = ocr_runner.extract_from_blocks(
            _read(left), _read(middle), _read(right)
        )
    except (ocr_runner.OCRBusy, SaveError) as exc:
        raise HTTPException(status_code=getattr(exc, "status", 503), detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Legacy block OCR failed")
        raise HTTPException(status_code=500, detail="Block OCR processing failed.")

    enriched = apply_business_rules(raw_rates)
    return {
        "success": True,
        "rates": enriched,
        "message": f"Extracted {len(raw_rates)} currencies from 3 blocks.",
    }


class GenerateRequest(BaseModel):
    rates: Dict[str, float]
    title: str = Field("MONEY CHANGER", max_length=120)
    subtitle: str = Field("PT. PRADNYANA ARTHA MANDIRI", max_length=200)
    logo_base64: Optional[str] = None


@router.post("/generate")
def generate_design(
    request: GenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not request.rates:
        raise HTTPException(status_code=400, detail="Rates data cannot be empty.")

    try:
        logo_bytes = decode_logo(request.logo_base64)
        enriched = apply_business_rules(request.rates)
        with render_slot(db):
            image_bytes = generate_rate_image(enriched, title=request.title,
                                              subtitle=request.subtitle, logo_bytes=logo_bytes)
    except (ocr_runner.OCRBusy, SaveError) as exc:
        raise HTTPException(status_code=getattr(exc, "status", 503), detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Legacy generate failed")
        raise HTTPException(status_code=500, detail="Image generation failed.")

    return StreamingResponse(
        io.BytesIO(image_bytes),
        media_type="image/png",
        headers={"Content-Disposition": "attachment; filename=pam_rate_board.png"},
    )
