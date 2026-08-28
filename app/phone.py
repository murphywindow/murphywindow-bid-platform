"""Canonical North American phone-number storage and display helpers."""
from __future__ import annotations

import re
from typing import Any


PHONE_ERROR = "Enter a ten-digit phone number, such as (123) 123-1234."
_PHONE_CHARACTERS = re.compile(r"^[0-9().\-\s]+$")


def normalize_phone_number(value: Any) -> str:
    """Return a phone as display-ready text, rejecting numeric JSON values."""
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError(PHONE_ERROR)
    raw = value.strip()
    if not raw:
        return ""
    if not _PHONE_CHARACTERS.fullmatch(raw):
        raise ValueError(PHONE_ERROR)
    digits = "".join(character for character in raw if character.isdigit())
    if len(digits) != 10:
        raise ValueError(PHONE_ERROR)
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def format_phone_if_valid(value: Any) -> Any:
    """Normalize valid legacy values without inventing digits for incomplete data."""
    try:
        return normalize_phone_number(value)
    except ValueError:
        return value
