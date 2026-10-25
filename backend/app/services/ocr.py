"""
ocr.py - OCR Logic using PaddleOCR.
Supports full image OCR and more accurate 3-block OCR.
"""

import logging
import os

from app.core.config import get_settings

# Set before importing Paddle/BLAS, only on the first OCR request.
for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_variable] = str(get_settings().ocr_cpu_threads)

import cv2
import numpy as np
from paddleocr import PaddleOCR
from app.services.parser import parse_ocr_blocks, parse_ocr_results

cv2.setNumThreads(get_settings().ocr_cpu_threads)
logger = logging.getLogger(__name__)
_ocr_engine = None


def get_ocr_engine() -> PaddleOCR:
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False,
                               cpu_threads=get_settings().ocr_cpu_threads, enable_mkldnn=False)
    return _ocr_engine


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image. Please check the file.")

    h, w = img.shape[:2]
    if w < 1000:
        scale = min(1000 / w, (8_000_000 / (h * w)) ** 0.5)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    img = cv2.filter2D(img, -1, kernel)
    return img


def _run_ocr(img: np.ndarray, min_conf: float = 0.40) -> list[str]:
    ocr = get_ocr_engine()
    try:
        results = ocr.ocr(img, cls=True)
    except TypeError:
        results = ocr.ocr(img)

    texts: list[str] = []
    if results and results[0]:
        for line in results[0]:
            if line and len(line) >= 2:
                text = str(line[1][0]).strip()
                confidence = float(line[1][1])
                if text and confidence >= min_conf:
                    texts.append(text)
    return texts


def extract_rates_from_image(image_bytes: bytes) -> dict:
    """Fallback single image OCR."""
    img = preprocess_image(image_bytes)
    raw_texts = _run_ocr(img)
    logger.debug("OCR detected %s text rows", len(raw_texts))
    return parse_ocr_results(raw_texts)

def ocr_image_bytes(image_bytes: bytes):
    img = preprocess_image(image_bytes)
    ocr = get_ocr_engine()
    results = ocr.ocr(img)

    texts = []
    if results and results[0]:
        for line in results[0]:
            text = line[1][0]
            conf = line[1][1]
            if conf > 0.4:
                texts.append(text.strip())

    return texts


def extract_rates_from_blocks(left_bytes: bytes, middle_bytes: bytes, right_bytes: bytes) -> dict:
    """Recommended: OCR 3 cropped blocks: left, middle, right."""
    raw_blocks: dict[str, list[str]] = {}
    for name, data in (("LEFT", left_bytes), ("MIDDLE", middle_bytes), ("RIGHT", right_bytes)):
        raw_blocks[name] = _run_ocr(preprocess_image(data))
    logger.debug("OCR completed three cropped columns")
    return parse_ocr_blocks(raw_blocks)
