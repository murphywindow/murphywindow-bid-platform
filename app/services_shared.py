"""Small dependency-neutral service helpers shared by calculation modules."""
from decimal import Decimal


def money_string(value: Decimal) -> str:
    """Serialize an exact Decimal without imposing display precision."""
    return format(value, "f")
