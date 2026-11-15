"""
Arabic text normalization and cleaning utilities.

All functions are pure (no DB, no I/O), so they can be unit-tested in isolation.
"""
import re
import unicodedata

# Zero-width and BiDi control chars: U+200B-200F, U+202A-202E, U+2066-2069, U+FEFF
_ZERO_WIDTH_BIDI = re.compile(r"[​-‏‪-‮⁦-⁩﻿]")
# Arabic diacritics (U+064B-U+065F, U+0670) and tatweel (U+0640)
_AR_MARKS = re.compile(r"[ً-ٰٟـ]")
_AR_MAP = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
     "ى": "ي", "ة": "ه"}
)
# Arabic-Indic (U+0660-0669) and Persian (U+06F0-06F9) digits
_DIGITS_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def clean_text(s):
    """NFKC + strip control chars. Keeps diacritics, hamza and ta-marbuta as typed."""
    if not s or not isinstance(s, str):
        return None
    s = unicodedata.normalize("NFKC", s)
    s = _ZERO_WIDTH_BIDI.sub("", s)
    s = s.replace("ـ", "")  # tatweel
    s = s.replace("\xa0", " ")  # NBSP -> space
    s = " ".join(s.split())
    return s or None


def to_ascii_digits(s):
    """Arabic-Indic and Persian digits are stored as 0-9."""
    if not s or not isinstance(s, str):
        return s
    return s.translate(_DIGITS_MAP)


def norm_search(s):
    """Comparison key: no diacritics/tatweel, unified alef/ya/ta-marbuta, lowercased."""
    if not s or not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _ZERO_WIDTH_BIDI.sub("", s)
    s = _AR_MARKS.sub("", s).translate(_AR_MAP)
    s = re.sub(r"[\W_]+", " ", s)
    return " ".join(s.split()).lower()


_GENDER_MALE = {"ذكر", "male", "m"}
_GENDER_FEMALE = {"أنثى", "انثى", "أنثي", "female", "f"}


def normalize_gender(s):
    """Returns "ذكر", "أنثى" or None when the value is not understood."""
    t = clean_text(s)
    if not t:
        return None
    t = t.lower()
    if t in _GENDER_MALE:
        return "ذكر"
    if t in _GENDER_FEMALE:
        return "أنثى"
    return None
