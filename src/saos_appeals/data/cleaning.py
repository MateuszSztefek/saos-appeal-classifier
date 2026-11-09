"""Source-specific corrections applied while building derived SAOS records."""

from __future__ import annotations

from typing import Any

JUDGMENT_DATE_CORRECTIONS = {
    358516: ("0208-03-14", "2018-03-14"),
    227221: ("2101-04-14", "2016-04-14"),
    31345: ("3013-12-04", "2013-12-04"),
}


def clean_judgment_date(record: dict[str, Any]) -> str | None:
    """Correct verified source typos, rejecting changed source values."""
    date = record.get("judgmentDate")
    correction = JUDGMENT_DATE_CORRECTIONS.get(record["id"])
    if correction is None:
        return date
    expected, corrected = correction
    if date != expected:
        raise ValueError(
            f"Unexpected judgmentDate for SAOS record {record['id']}: "
            f"expected {expected!r}, got {date!r}"
        )
    return corrected
