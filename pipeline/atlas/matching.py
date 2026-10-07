"""Matching golden rows to bundle places: the right entity, one-to-one, with duplicates flagged."""
from __future__ import annotations

from dataclasses import dataclass, field

from atlas import golden as G
from atlas.geo import fold, haversine_km, is_number


def usable(p: object) -> bool:
    """A place the matcher can read without raising; malformed places are G-SCHEMA's business."""
    return (isinstance(p, dict) and is_number(p.get("lat")) and is_number(p.get("lon"))
            and isinstance(p.get("type"), str) and isinstance(p.get("iso3"), str)
            and isinstance(p.get("name_en"), str))


def place_names(p: dict) -> set[str]:
    names = {fold(p.get("name_en", "")), fold(p.get("name_local") or "")}
    for a in p.get("aliases") or []:
        if isinstance(a, str):
            names.add(fold(a))
        elif isinstance(a, dict) and isinstance(a.get("alias"), str):
            names.add(fold(a["alias"]))
    names.discard("")
    return names


QID_MAX_KM = 150.0   # an area or route has a footprint, not a point: with a QID its anchor may lie this far


def candidates(row: G.Row, places: list[dict], loose: bool = False) -> list[tuple[float, dict]]:
    """Places that could be this row. When the row has a QID and the place carries it (as its QID or one
    of its merged keys), that is identity: the type may differ (D33) and, for an area or route, the anchor may lie up to QID_MAX_KM
    away; a site or settlement must still lie within tol_km. Otherwise: same country (ISO3), type, within tol_km, and a listed name. `loose` also
    accepts a name match when the row has a QID, for duplicate detection (a second Florence under
    another QID is still a duplicate)."""
    out = []
    for p in places:
        if not usable(p) or p["iso3"] != row.iso3:
            continue
        if row.lat is None or row.lon is None or row.tol_km is None:
            continue
        by_qid = bool(row.qid) and (p.get("qid") == row.qid or f"qid:{row.qid}" in (p.get("keys") or ()))
        by_name = bool(row.names & place_names(p))
        d = haversine_km(row.lat, row.lon, p["lat"], p["lon"])
        if by_qid:
            if d > (max(row.tol_km, QID_MAX_KM) if row.type in ("area", "route") else row.tol_km):
                continue
        else:
            if p["type"] != row.type or d > row.tol_km:
                continue
            if row.qid and not (loose and by_name):
                continue
            if not row.qid and not by_name:
                continue
        out.append((d, p))
    return out


@dataclass
class Assignment:
    matched: dict[str, dict] = field(default_factory=dict)      # golden_id -> place
    duplicates: dict[str, list[dict]] = field(default_factory=dict)
    missed: list[G.Row] = field(default_factory=list)


def assign(rows: list[G.Row], places: list[dict]) -> Assignment:
    """One-to-one assignment, nearest pair first. A candidate that matches a row but is not
    the one assigned to it, and is assigned to no row, is a duplicate of that row."""
    positives = [r for r in rows if r.row_kind == "positive"]
    cand = {r.golden_id: candidates(r, places) for r in positives}
    pairs = sorted(((d, r.golden_id, id(p), p) for r in positives for d, p in cand[r.golden_id]),
                   key=lambda t: (t[0], t[1]))
    out = Assignment()
    used: set[int] = set()
    for _d, gid, pid, p in pairs:
        if gid not in out.matched and pid not in used:
            out.matched[gid] = p
            used.add(pid)
    for r in positives:
        if r.golden_id not in out.matched:
            out.missed.append(r)
            continue
        extra = [] if r.type == "area" else [p for _d, p in candidates(r, places, loose=True) if id(p) not in used]   # D35: an area spans several places
        if extra:
            out.duplicates[r.golden_id] = extra
    return out


def by_name_in_country(row: G.Row, places: list[dict]) -> list[dict]:
    return [p for p in places if usable(p) and p["iso3"] == row.iso3 and row.names & place_names(p)]
