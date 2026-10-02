"""Printed-map tiles by recursive balanced subdivision (document 4, section 4).

Each country is a static region (its border). Inside it, tiles are separated by straight
**dynamic cuts** that run along the two axes of the printed map. A cut is placed in the gap
between two neighbouring places, so no hole lies on a tile edge, and it splits the places into
two nearly equal groups. A tile is split again until a stop rule says it is done.

This module works on points in millimetres on the wall (Equal Earth projection, 3.00 m wide).
Clipping the rectangles to the country's border is geometry work done where shapely is
available (see `pipeline/scripts/tiles_demo.py`); the decisions here depend only on the places.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

MAP_WIDTH_MM = 3000.0
_A1, _A2, _A3, _A4 = 1.340264, -0.081106, 0.000893, 0.003796
_X_MAX = 2 * math.sqrt(3) * math.pi / (3 * _A1)          # x at lon 180, lat 0
_MM_PER_UNIT = MAP_WIDTH_MM / (2 * _X_MAX)


def project_mm(lat: float, lon: float) -> tuple[float, float]:
    """Equal Earth projection scaled to a 3.00 m wide map, centred on (0, 0), y up.

    >>> x, y = project_mm(0.0, 180.0)
    >>> round(x), round(y)
    (1500, 0)
    >>> round(project_mm(90.0, 0.0)[1])
    730
    """
    phi, lam = math.radians(lat), math.radians(lon)
    th = math.asin(math.sqrt(3) / 2 * math.sin(phi))
    t2, t6, t8 = th ** 2, th ** 6, th ** 8
    x = 2 * math.sqrt(3) * lam * math.cos(th) / (3 * (9 * _A4 * t8 + 7 * _A3 * t6 + 3 * _A2 * t2 + _A1))
    y = th * (_A1 + _A2 * t2 + _A3 * t6 + _A4 * t8)
    return x * _MM_PER_UNIT, y * _MM_PER_UNIT


@dataclass(frozen=True)
class TileParams:
    max_places: int = 6              # a tile with this many places or fewer is finished
    min_places: int = 3              # each side of a cut keeps at least this many
    min_extent_mm: float = 12.0      # a tile edge is at least this long (about 160 km)
    edge_margin_mm: float = 3.0      # a hole is at least this far from a tile edge
    max_extent_mm: float | None = None   # optional ceiling on a tile's size (None: no ceiling)
    balance_slack: int = 0           # a cut may be this many places off an even split if its gap is wider


@dataclass
class Leaf:
    ids: list[str]
    bbox: tuple[float, float, float, float]              # x0, y0, x1, y1 in mm
    cuts: list[tuple[str, float]] = field(default_factory=list)   # ("x"|"y", position) from the root
    stop: str = "small_enough"                           # or "cannot_split:<why>"


def _extent(b: tuple[float, float, float, float]) -> tuple[float, float]:
    return b[2] - b[0], b[3] - b[1]


def best_cut(pts: list[tuple[str, float, float]], bbox, axis: str, p: TileParams):
    params = p
    """The best valid cut on one axis, or (None, reason). Returns (position, left, right)."""
    i = 0 if axis == "x" else 1
    lo, hi = (bbox[0], bbox[2]) if axis == "x" else (bbox[1], bbox[3])
    order = sorted(pts, key=lambda q: (q[1 + i], q[0]))
    n = len(order)
    best = None
    reason = "too_few_places"
    for k in range(p.min_places, n - p.min_places + 1):
        a, b = order[k - 1][1 + i], order[k][1 + i]
        gap = b - a
        if gap < 2 * p.edge_margin_mm:
            reason = "no_gap_wide_enough"
            continue
        pos = (a + b) / 2
        if pos - lo < p.min_extent_mm or hi - pos < p.min_extent_mm:
            reason = "tile_too_small"
            continue
        key = (max(0.0, abs(k - n / 2) - params.balance_slack), -gap, k)   # balanced within the slack, then widest gap
        if best is None or key < best[0]:
            best = (key, pos, order[:k], order[k:])
    if best is None:
        return None, reason
    return (best[1], best[2], best[3]), None


def partition(points: list[tuple[str, float, float]], bbox: tuple[float, float, float, float],
              params: TileParams | None = None) -> list[Leaf]:
    """Split `points` (id, x_mm, y_mm) inside `bbox` into tiles. Deterministic."""
    params = params or TileParams()
    out: list[Leaf] = []

    def rec(pts, box, cuts):
        w, h = _extent(box)
        too_big = params.max_extent_mm is not None and max(w, h) > params.max_extent_mm
        if len(pts) <= params.max_places and not too_big:
            out.append(Leaf([q[0] for q in pts], box, cuts))
            return
        axes = ["x", "y"] if w >= h else ["y", "x"]       # cut across the longer side first
        why = []
        for axis in axes:
            res, reason = best_cut(pts, box, axis, params)
            if res is not None:
                pos, left, right = res
                if axis == "x":
                    rec(left, (box[0], box[1], pos, box[3]), [*cuts, ("x", pos)])
                    rec(right, (pos, box[1], box[2], box[3]), [*cuts, ("x", pos)])
                else:
                    rec(left, (box[0], box[1], box[2], pos), [*cuts, ("y", pos)])
                    rec(right, (box[0], pos, box[2], box[3]), [*cuts, ("y", pos)])
                return
            why.append(reason)
        out.append(Leaf([q[0] for q in pts], box, cuts, f"cannot_split:{'/'.join(why)}"))

    rec(sorted(points), bbox, [])
    return out
