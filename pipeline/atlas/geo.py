"""Small geometry and statistics helpers."""
from __future__ import annotations

import math
import unicodedata


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km.

    >>> round(haversine_km(48.8566, 2.3522, 51.5074, -0.1278))
    344
    """
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval; 0.0 when n is 0.

    >>> round(wilson_lower(10, 10), 2)
    0.72
    >>> wilson_lower(0, 0)
    0.0
    """
    if n == 0:
        return 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def fold(text: str) -> str:
    """Accent- and case-insensitive key for name matching.

    >>> fold("Árgos") == fold("argos")
    True
    """
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


def is_number(x: object) -> bool:
    """True for real numbers; bool is excluded.

    >>> is_number(3.5), is_number("3.5"), is_number(True), is_number(float("nan"))
    (True, False, False, False)
    """
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
