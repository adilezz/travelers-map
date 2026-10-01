"""Loading and validating the golden set (document 3 section 2)."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from atlas.geo import fold
from atlas.vocab import (
    ISO3_RE,
    KINDS,
    MAX_KINDS_PER_PLACE,
    PLACE_TYPES,
    RELATIONS,
    ROW_KINDS,
    TIERS,
)

COLUMNS = (
    "golden_id", "country", "iso3", "expected_name", "aliases", "row_kind", "type", "lat", "lon",
    "tol_km", "min_tier", "max_tier", "kinds_expected", "whs_id", "qid", "qid_status",
    "relation", "target_id", "regression", "evidence", "note",
)
MAX_TOL_SITE_KM = 8.0         # sites
MAX_TOL_SETTLEMENT_KM = 12.0  # settlements: the anchor of a large city is its centre
MAX_TOL_AREA_KM = 60.0        # areas and routes


@dataclass
class Row:
    raw: dict
    golden_id: str = ""
    country: str = ""
    iso3: str = ""
    name: str = ""
    names: set[str] = field(default_factory=set)  # folded name plus aliases
    row_kind: str = "positive"
    type: str = ""
    lat: float | None = None
    lon: float | None = None
    tol_km: float | None = None
    min_tier: str = ""
    max_tier: str = ""
    kinds: tuple[str, ...] = ()
    whs_id: str = ""
    qid: str = ""
    relation: str = ""
    targets: tuple[str, ...] = ()
    regression: bool = False


def _split(value: str) -> list[str]:
    return [p for p in (value or "").split("|") if p]


def _float(value: str) -> float | None:
    try:
        return float(value) if value not in ("", None) else None
    except ValueError:
        return None


def load(path: str | Path) -> list[Row]:
    """Load rows without raising on bad values; `validate` reports them."""
    rows: list[Row] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            raw = {c: (raw.get(c) or "") for c in COLUMNS}
            r = Row(raw=raw)
            r.golden_id, r.country, r.iso3 = raw["golden_id"], raw["country"], raw["iso3"]
            r.name = raw["expected_name"]
            r.names = {fold(raw["expected_name"]), *(fold(a) for a in _split(raw["aliases"]))}
            r.row_kind, r.type = raw["row_kind"], raw["type"]
            r.lat, r.lon, r.tol_km = _float(raw["lat"]), _float(raw["lon"]), _float(raw["tol_km"])
            r.min_tier, r.max_tier = raw["min_tier"], raw["max_tier"]
            r.kinds = tuple(_split(raw["kinds_expected"]))
            r.whs_id, r.qid = raw["whs_id"], raw["qid"]
            r.relation = raw["relation"]
            r.targets = tuple(_split(raw["target_id"]))
            r.regression = raw["regression"] == "y"
            rows.append(r)
    return rows


def whs_ids(csv_path: str | Path) -> set[str]:
    with open(csv_path, encoding="utf-8", newline="") as fh:
        return {row["id_number"].strip() for row in csv.DictReader(fh)}


def validate(rows: list[Row], known_whs: set[str] | None) -> list[str]:
    """Problems found in the golden file; empty means well formed.

    `known_whs` is required: a golden file cannot be checked without the UNESCO list.
    """
    problems: list[str] = []
    if known_whs is None:
        problems.append("no UNESCO property list supplied (data/inputs/whs_properties.csv)")
    if not rows:
        problems.append("golden set is empty")
    ids = [r.golden_id for r in rows]
    if len(ids) != len(set(ids)):
        problems.append("duplicate golden_id")
    by_id = {r.golden_id: r for r in rows}
    for r in rows:
        g = r.golden_id or "<no id>"
        if r.row_kind not in ROW_KINDS:
            problems.append(f"{g}: bad row_kind {r.row_kind!r}")
        if not r.name or not r.country:
            problems.append(f"{g}: missing name or country")
        if not ISO3_RE.match(r.iso3 or ""):
            problems.append(f"{g}: bad iso3 {r.iso3!r}")
        if r.row_kind == "positive":
            if r.type not in PLACE_TYPES:
                problems.append(f"{g}: bad type {r.type!r}")
            if r.lat is None or r.lon is None or not (-90 <= r.lat <= 90 and -180 <= r.lon <= 180):
                problems.append(f"{g}: bad coordinates")
            if r.tol_km is None or r.tol_km <= 0:
                problems.append(f"{g}: missing tol_km")
            elif r.type == "site" and r.tol_km > MAX_TOL_SITE_KM:
                problems.append(f"{g}: tol_km {r.tol_km} too wide for a site")
            elif r.type == "settlement" and r.tol_km > MAX_TOL_SETTLEMENT_KM:
                problems.append(f"{g}: tol_km {r.tol_km} too wide for a settlement")
            elif r.tol_km > MAX_TOL_AREA_KM:
                problems.append(f"{g}: tol_km {r.tol_km} too wide")
            if r.min_tier not in TIERS:
                problems.append(f"{g}: bad min_tier {r.min_tier!r}")
            if r.max_tier and r.max_tier not in TIERS:
                problems.append(f"{g}: bad max_tier {r.max_tier!r}")
            if (r.min_tier in TIERS and r.max_tier in TIERS
                    and TIERS.index(r.max_tier) < TIERS.index(r.min_tier)):
                problems.append(f"{g}: max_tier below min_tier")
            if not r.kinds:
                problems.append(f"{g}: no kinds_expected (every place carries 1-3 kinds)")
            if len(r.kinds) > MAX_KINDS_PER_PLACE:
                problems.append(f"{g}: more than {MAX_KINDS_PER_PLACE} kinds")
            for k in r.kinds:
                if k not in KINDS:
                    problems.append(f"{g}: unknown kind {k!r}")
            if len(set(r.kinds)) != len(r.kinds):
                problems.append(f"{g}: repeated kind")
            if r.whs_id and known_whs is not None and r.whs_id not in known_whs:
                problems.append(f"{g}: whs_id {r.whs_id} not in the UNESCO list")
        else:
            if r.relation not in RELATIONS:
                problems.append(f"{g}: bad relation {r.relation!r}")
            if not r.targets:
                problems.append(f"{g}: relational row without target_id")
            for t in r.targets:
                tgt = by_id.get(t)
                if tgt is None:
                    problems.append(f"{g}: target {t} does not exist")
                elif tgt.row_kind != "positive":
                    problems.append(f"{g}: target {t} is not a positive row")
                elif tgt.iso3 != r.iso3:
                    problems.append(f"{g}: target {t} is in another country")
    return problems
