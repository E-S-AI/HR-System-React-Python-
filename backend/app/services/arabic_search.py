"""
Arabic-aware search helpers for SQLAlchemy columns.

norm_sql(col) wraps a text column in Postgres unaccent-equivalent
transformations so a query like norm_sql(col).ilike('%' + term + '%')
matches regardless of hamza, alef madda, ya/alef maqsura, ta marbuta,
or leading/trailing whitespace differences.

For multi-word Arabic name searches every word must appear anywhere in
the normalised full_name_spaced (AND semantics), which is more precise
than a single LIKE with spaces that requires exact order.
"""
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import norm_search


def norm_sql(column):
    """
    PostgreSQL expression that mirrors norm_search() done in Python:
    lower + regexp_replace to strip diacritics + translate for alef/ya/ta-marbuta.

    Requires pg_trgm or just uses standard string functions – no extensions needed.
    We rely on the same substitution table as app.core.text so Python-side
    norm_search(x) == DB-side norm_sql(col) for the same value.
    """
    # 1. Lower-case
    col = func.lower(column)
    # 2. Strip Arabic diacritics (U+064B-U+065F, U+0670) and tatweel (U+0640)
    col = func.regexp_replace(
        col,
        r"[ً-ٰٟـ]",
        "",
        "g",
    )
    # 3. Unify alef variants -> ا , ya -> ي (via translate)
    col = func.translate(
        col,
        "أإآٱىة",
        "ااااية",
    )
    # 4. Collapse multiple spaces
    col = func.regexp_replace(col, r"\s+", " ", "g")
    return col


def name_search_conditions(search: str, column):
    """
    Returns a list of SQLAlchemy conditions (AND between words) for
    multi-word Arabic name search.  Each word must appear in the
    normalised column.

    Example: "محمد علي" produces:
        norm_sql(col) LIKE '%محمد%' AND norm_sql(col) LIKE '%علي%'
    """
    words = norm_search(search).split()
    if not words:
        return []
    normed = norm_sql(column)
    conds = []
    for w in words:
        # escape SQL LIKE metacharacters in the word
        w_esc = w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conds.append(normed.ilike(f"%{w_esc}%", escape="\\"))
    return conds
