"""Turning edited rate input into immutable, generatable versions.

Decimal in, Decimal stored, float handed to the generator. The float
conversion happens at exactly one point - right before drawing - because the
generator's number formatting is the behaviour the owner already signed off
on and must not shift.
"""

from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutils import utcnow
from app.models import RateBoard, RateItem, RateVersion, VersionStatus
from app.services.mapper import LEFT_COLUMN, RIGHT_COLUMN

# Denomination captions printed under the USD rows on the board.
USD_DENOMINATIONS = {
    "USD": "(100, 50)",
    "USD_T": "(20, 10, 5)",
    "USD_K": "(1, 2)",
}

# The exact row order the board draws, left column then right column. Derived
# from the generator's own ordering so the two can never drift apart.
LEFT_LAYOUT: List[str] = []
for _code in LEFT_COLUMN:
    LEFT_LAYOUT.append(_code)
    if _code == "USD":
        LEFT_LAYOUT.extend(["USD_T", "USD_K"])

RIGHT_LAYOUT: List[str] = list(RIGHT_COLUMN)

ALL_CURRENCIES: List[str] = LEFT_LAYOUT + RIGHT_LAYOUT

# Generous but finite: catches a stray OCR read of a whole phone number
# without rejecting a legitimate rate.
MAX_RATE = Decimal("99999999.9999")


class RateValidationError(ValueError):
    """Raised with a message that is safe to show a user."""


def parse_rate(raw) -> Optional[Decimal]:
    """Parse one incoming rate value.

    None, empty string and "-" all mean "not traded" and are stored as NULL.
    That is deliberately different from 0.
    """
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        value = raw
    else:
        text = str(raw).strip()
        if text == "" or text == "-":
            return None
        try:
            value = Decimal(text)
        except (InvalidOperation, ValueError):
            raise RateValidationError(f"Nilai rate tidak valid: {raw!r}")

    if value.is_nan() or value.is_infinite():
        raise RateValidationError("Nilai rate tidak valid.")
    if value < 0:
        raise RateValidationError("Rate tidak boleh negatif.")
    if value > MAX_RATE:
        raise RateValidationError("Nilai rate terlalu besar.")
    return value.quantize(Decimal("0.0001"))


def layout_for(currency: str) -> Tuple[str, int]:
    """Return (column_side, sort_order) for a currency code."""
    if currency in LEFT_LAYOUT:
        return "left", LEFT_LAYOUT.index(currency)
    if currency in RIGHT_LAYOUT:
        return "right", RIGHT_LAYOUT.index(currency)
    return "left", len(LEFT_LAYOUT) + 100


def build_items(version: RateVersion, rates: Dict[str, Optional[Decimal]]) -> List[RateItem]:
    """Create RateItem rows in canonical board order.

    Every currency in the layout gets a row, including the ones with no value,
    so the stored version is a complete description of what the board shows
    rather than a sparse patch.
    """
    items: List[RateItem] = []
    for currency in ALL_CURRENCIES:
        side, order = layout_for(currency)
        items.append(
            RateItem(
                version=version,
                currency=currency,
                denomination=USD_DENOMINATIONS.get(currency),
                value=rates.get(currency),
                column_side=side,
                sort_order=order,
            )
        )
    return items


def normalise_input(raw_rates: Dict[str, object]) -> Dict[str, Optional[Decimal]]:
    """Normalise arbitrary client input to known currencies and Decimals."""
    result: Dict[str, Optional[Decimal]] = {}
    for key, raw in (raw_rates or {}).items():
        code = str(key).strip().upper().replace(" ", "_")
        if code == "USDT":
            code = "USD_T"
        elif code == "USDK":
            code = "USD_K"
        if code not in ALL_CURRENCIES:
            continue
        result[code] = parse_rate(raw)
    return result


def rates_payload(items: Iterable[RateItem]) -> Dict[str, float]:
    """Shape a version's rows into the dict the generator expects.

    NULL rows are omitted entirely; the generator renders a missing key as "-".
    """
    payload: Dict[str, float] = {}
    for item in items:
        if item.value is None:
            continue
        payload[item.currency] = float(item.value)
    return payload


def rates_as_strings(items: Iterable[RateItem]) -> Dict[str, Optional[str]]:
    """JSON-safe representation that keeps decimal precision exact."""
    out: Dict[str, Optional[str]] = {}
    for item in items:
        out[item.currency] = None if item.value is None else format(item.value.normalize(), "f")
    return out


def next_version_number(db: Session, board_id: int) -> int:
    current = db.execute(
        select(func.max(RateVersion.version)).where(RateVersion.board_id == board_id)
    ).scalar()
    return int(current or 0) + 1


def get_or_create_default_board(
    db: Session, *, owner_id: Optional[int], branch_id: Optional[int], title: str
) -> RateBoard:
    """One board per branch keeps history readable without extra UI."""
    stmt = select(RateBoard).where(RateBoard.branch_id == branch_id)
    board = db.execute(stmt.order_by(RateBoard.id).limit(1)).scalar_one_or_none()
    if board is not None:
        return board

    board = RateBoard(title=title or "Rate Board", branch_id=branch_id, owner_id=owner_id)
    db.add(board)
    db.flush()
    return board


def create_version(
    db: Session,
    *,
    board: RateBoard,
    rates: Dict[str, Optional[Decimal]],
    board_title: str,
    board_subtitle: str,
    created_by: Optional[int],
    branch_id: Optional[int],
    logo_asset_id: Optional[int] = None,
    source_version_id: Optional[int] = None,
    config_snapshot: Optional[dict] = None,
) -> RateVersion:
    version = RateVersion(
        board_id=board.id,
        version=next_version_number(db, board.id),
        status=VersionStatus.DRAFT.value,
        created_by=created_by,
        branch_id=branch_id,
        source_version_id=source_version_id,
        board_title=board_title,
        board_subtitle=board_subtitle,
        logo_asset_id=logo_asset_id,
        config_snapshot=config_snapshot or {},
    )
    db.add(version)
    db.flush()

    for item in build_items(version, rates):
        db.add(item)
    db.flush()
    return version


def clone_rates(version: RateVersion) -> Dict[str, Optional[Decimal]]:
    return {item.currency: item.value for item in version.items}


def mark_failed(db: Session, version: RateVersion, message: str) -> None:
    version.status = VersionStatus.FAILED.value
    version.error_message = message[:2000]
    db.flush()


def mark_ready(db: Session, version: RateVersion) -> None:
    version.status = VersionStatus.READY.value
    version.generated_at = utcnow().replace(tzinfo=None)
    version.error_message = None
    db.flush()


def has_any_value(rates: Dict[str, Optional[Decimal]]) -> bool:
    return any(value is not None for value in rates.values())


def ensure_sequence(values: Optional[Sequence[int]]) -> List[int]:
    return list(values or [])
