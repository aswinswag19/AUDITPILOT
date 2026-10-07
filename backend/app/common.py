"""
Shared helpers: table lookup and strict date handling.

Dates are handled as integer keys (YYYYMMDD) so that range checks, rate look-ups and
format interpretation (DD/MM/YYYY vs MM/DD/YYYY) behave identically in every engine.
"""

from pathlib import Path
from typing import Optional, Tuple

DD_MM = "DD/MM/YYYY"
MM_DD = "MM/DD/YYYY"


def find_table(data_dir: Path, name: str) -> Optional[Path]:
    """Locate a table in the data dir, falling back to the dataset_b sub-folder."""
    if not name:
        return None
    for p in (data_dir / name, data_dir / "dataset_b" / name):
        if p.is_file():
            return p
    return None


def _valid_ymd(y: int, m: int, d: int) -> bool:
    if not (1 <= m <= 12) or y < 1 or d < 1:
        return False
    if m == 2:
        dim = 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    elif m in (4, 6, 9, 11):
        dim = 30
    else:
        dim = 31
    return d <= dim


def dkey(text, fmt: str = DD_MM) -> int:
    """'20/09/2025' -> 20250920 (0 if blank / malformed / not a real calendar date)."""
    parts = str(text).strip().split("/")
    if len(parts) != 3:
        return 0
    try:
        a, b, y = (int(x) for x in parts)
    except ValueError:
        return 0
    d, m = (a, b) if fmt == DD_MM else (b, a)
    return y * 10000 + m * 100 + d if _valid_ymd(y, m, d) else 0


def iso_to_key(text, fmt: str = DD_MM) -> int:
    """Rate effective dates: ISO 'YYYY-MM-DD' (or a slash date in `fmt`) -> key (0 if invalid)."""
    s = str(text).strip()
    if "/" in s:
        return dkey(s, fmt)
    parts = s.split("-")
    if len(parts) != 3:
        return 0
    try:
        y, m, d = (int(x) for x in parts)
    except ValueError:
        return 0
    return y * 10000 + m * 100 + d if _valid_ymd(y, m, d) else 0


def key_parts(key: int) -> Tuple[int, int, int]:
    return key // 10000, (key // 100) % 100, key % 100


def key_to_iso(key: int) -> str:
    y, m, d = key_parts(key)
    return f"{y:04d}-{m:02d}-{d:02d}"


def format_date(y: int, m: int, d: int, fmt: str = DD_MM) -> str:
    return f"{d:02d}/{m:02d}/{y:04d}" if fmt == DD_MM else f"{m:02d}/{d:02d}/{y:04d}"


def is_ambiguous_date(text) -> bool:
    """True when the text is a valid date both as DD/MM and as MM/DD but means different days."""
    a, b = dkey(text, DD_MM), dkey(text, MM_DD)
    return bool(a and b and a != b)


# ---- quarters --------------------------------------------------------------------------

def quarter_window(year: int, quarter: int, fiscal: bool = False) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """((y,m,d) start, (y,m,d) end) of a quarter.
    Calendar: Q1=Jan-Mar ... Q4=Oct-Dec.
    Fiscal (April-March year, as used in India): Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar,
    all taken in the given calendar `year`."""
    first_month = {1: 4, 2: 7, 3: 10, 4: 1}[quarter] if fiscal else 3 * (quarter - 1) + 1
    last_month = first_month + 2
    last_day = 31 if last_month in (3, 12) else 30
    return (year, first_month, 1), (year, last_month, last_day)


def calendar_quarter_of(start_key: int, end_key: int) -> Optional[Tuple[int, int]]:
    """(year, quarter) when the range is exactly one calendar quarter, else None."""
    if not start_key or not end_key:
        return None
    for q in (1, 2, 3, 4):
        (y1, m1, d1), (y2, m2, d2) = quarter_window(key_parts(start_key)[0], q)
        if start_key == y1 * 10000 + m1 * 100 + d1 and end_key == y2 * 10000 + m2 * 100 + d2:
            return key_parts(start_key)[0], q
    return None


# ---- currencies ------------------------------------------------------------------------

BLANK_CURRENCY = "(BLANK)"
TRANSACTION_DATE = "transaction_date"
LATEST = "latest"


def raw_currency(value) -> str:
    """Currency cell as found in the data, normalised: trimmed, upper-case, '(BLANK)' when empty."""
    s = "" if value is None else str(value).strip().upper()
    return s if s and s != "NAN" else BLANK_CURRENCY


def effective_currency(value, currency_map=None) -> str:
    """Currency a row is converted from, after applying the user's confirmed currency_map.
    '' means 'blank and not reassigned' (no rate can exist for it)."""
    code = raw_currency(value)
    out = (currency_map or {}).get(code, code)
    return "" if out == BLANK_CURRENCY else out
