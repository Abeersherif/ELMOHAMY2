"""
Utility functions for the Mohamy Legal Assistant.
"""
import sqlite3
import re
from typing import Dict, List, Optional


CANCELLATION_PATTERNS = [
    re.compile(r"ملغ[اىي]ة?"),
    re.compile(r"ملغاه"),
    re.compile(r"ملغية"),
    re.compile(r"أ?ُ?لغي(?:ت)?"),
    re.compile(r"منسوخ[ةه]?"),
    re.compile(r"مستبدل[ةه]?"),
    re.compile(r"تم[\s ]+إلغاء"),
    re.compile(r"تم[\s ]+ال[إا]لغاء"),
]

REPLACEMENT_REF = re.compile(
    r"ملغ[اىيه]ة?\s+بالقانون\s+رقم\s+(\d+)\s+لسنة\s+(\d{4})"
)


def detect_cancellation(details: Optional[str], titel: Optional[str]) -> Dict[str, object]:
    """Detect whether a law article has been repealed.

    Returns dict:
      is_cancelled: True if the article text itself indicates it was repealed.
      replacement: (law_no, year) tuple if the cancellation cites a replacing law.
      signal: short Arabic note explaining what was detected.
    """
    text = (details or "").strip()
    title = (titel or "").strip()

    if not text:
        return {"is_cancelled": False, "replacement": None, "signal": ""}

    if "ديباج" in title:
        return {"is_cancelled": False, "replacement": None, "signal": ""}

    has_marker = any(p.search(text) for p in CANCELLATION_PATTERNS)
    if not has_marker:
        return {"is_cancelled": False, "replacement": None, "signal": ""}

    replacement = None
    m = REPLACEMENT_REF.search(text)
    if m:
        replacement = (m.group(1), m.group(2))

    if len(text) < 150:
        signal = "نص المادة يقتصر على الإشارة إلى الإلغاء"
        if replacement:
            signal += f" بالقانون رقم {replacement[0]} لسنة {replacement[1]}"
        return {"is_cancelled": True, "replacement": replacement, "signal": signal}

    return {
        "is_cancelled": False,
        "replacement": replacement,
        "signal": "يحتوي النص على إشارة إلى إلغاء (قد تكون تاريخية)",
    }


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_all_law_tables(db_path: str) -> List[str]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name LIKE 'قانون%';"
    )
    rows = cur.fetchall()
    conn.close()
    ignored_tables = {"قانون", "all_laws", "main_laws", "combined_laws"}
    return [row[0] for row in rows if row[0] not in ignored_tables]


_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def arabic_to_ascii_digits(text: str) -> str:
    """Convert Arabic-Indic numerals (٠-٩) and extended Persian (۰-۹) to ASCII (0-9)."""
    if not text:
        return ""
    return text.translate(_ARABIC_INDIC_DIGITS)


def normalize_arabic_simple(text: str) -> str:
    """
    Normalize Arabic text for keyword matching.
    - Arabic-Indic digits → ASCII
    - Strip diacritics (tashkeel)
    - Normalize alef / ya / taa-marbuta variants
    - Collapse whitespace
    """
    if not text:
        return ""

    text = arabic_to_ascii_digits(text)
    text = re.sub(r"[ً-ٰٟ]", "", text)
    text = re.sub(r"[أإآ]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


_ARTICLE_NUM_PATTERNS = [
    re.compile(r"(?:ال)?ماد[ةه]\s*(?:رقم\s*)?(\d{1,4})"),
    re.compile(r"\bم\s*\.?\s*(\d{1,4})\b"),
]

_LAW_REF_PATTERN = re.compile(
    r"قانون\s*(?:رقم\s*)?(\d{1,4})\s*(?:ل|لسن[ةه])\s*(\d{3,4})"
)


def extract_legal_refs(query: str) -> Dict[str, List]:
    """Pull article numbers and law (number, year) refs out of an Arabic query.

    Returns:
      { "article_numbers": [int, ...],
        "law_refs":        [(law_no:str, year:str), ...],
        "years":           [str, ...] }
    """
    if not query:
        return {"article_numbers": [], "law_refs": [], "years": []}

    norm = arabic_to_ascii_digits(query)
    norm = re.sub(r"[أإآ]", "ا", norm)
    norm = re.sub(r"ة", "ه", norm)

    nums: List[int] = []
    for pat in _ARTICLE_NUM_PATTERNS:
        for m in pat.finditer(norm):
            try:
                n = int(m.group(1))
                if 1 <= n <= 9999 and n not in nums:
                    nums.append(n)
            except (ValueError, TypeError):
                pass

    law_refs: List = []
    years: List[str] = []
    for m in _LAW_REF_PATTERN.finditer(norm):
        law_refs.append((m.group(1), m.group(2)))
        if m.group(2) not in years:
            years.append(m.group(2))

    # Also capture "لسنة 1945" / "سنة 1945" / "عام 1945" not paired with a law number
    for m in re.finditer(r"(?:لسن[ةه]|سن[ةه]|عام)\s*(\d{3,4})", norm):
        y = m.group(1)
        if y not in years:
            years.append(y)

    return {"article_numbers": nums, "law_refs": law_refs, "years": years}
