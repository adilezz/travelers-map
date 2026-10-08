"""The kind rules: from stored facts to the fired rules that `kinds.select_kinds` chooses among (document 1 section 7.2).

A rule reads facts about a place, never its name:
  * Wikidata classes of the place and of the items merged into it (data/rules/kind_classes.csv),
  * capital-of statements, population, World Heritage and WDPA ids,
  * geometry facts (relief, land cover, distance to the sea) from `atlas.geofacts`.
The strengths, roles and exclusions are data (data/rules/kinds.csv), the thresholds are data
(data/rules/kind_params.json); only the closed set of tests below lives in code. A rule whose source is not
ingested yet (OSM, UNESCO criteria) is not evaluated and is listed as such, never guessed.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from atlas import kinds as K

ROOT = Path(__file__).resolve().parents[2]
STATE = {"Q3624078", "Q6256"}                      # sovereign state, country
FORMER_STATE = {"Q48349", "Q3024240"}              # empire, historical country
NOT_EVALUATED = {"R04", "R06", "R08", "R09", "R11"}


def load_rules(path: Path = ROOT / "data" / "rules" / "kinds.csv") -> dict[str, dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["rule_id"]: r for r in csv.DictReader(fh)}


def load_class_sets(path: Path = ROOT / "data" / "rules" / "kind_classes.csv") -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["rule_id"]].add(r["class_qid"])
    return dict(out)


def load_params(path: Path = ROOT / "data" / "rules" / "kind_params.json") -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Context:
    """Everything the rules need that is not on the place itself."""

    def __init__(self, rules: dict, class_sets: dict, params: dict, state_classes: dict[str, set[str]],
                 wdpa: dict[str, dict], geo: dict[str, dict], city_index, whs_titles: dict[str, str] | None = None,
                 capitals: dict[str, list[dict]] | None = None):
        import re
        self.rules, self.class_sets, self.params = rules, class_sets, params
        self.state_classes, self.wdpa, self.geo, self.city_index = state_classes, wdpa, geo, city_index
        self.titles = whs_titles or {}
        self.capitals = capitals or {}
        self.old_town_re = re.compile(params.get("old_town_title", "$^"), re.I)

    def whs_title(self, whs: object) -> str:
        """The UNESCO title of a whole property id ('1133bis' -> property 1133)."""
        import re
        m = re.match(r"^(\d+)", str(whs or ""))
        return self.titles.get(m.group(1), "") if m and re.match(r"^\d+(bis|ter|quater)?$", str(whs)) else ""


def member_classes(c: dict) -> dict[str, set[str]]:
    """qid -> classes, for the place itself and every item merged or absorbed into it."""
    out = {c["qid"]: set(c.get("classes", ()))}
    for q, m in (c.get("members") or {}).items():
        out[q] = set(m.get("classes", ()))
    return out


def _hit(c: dict, ctx: Context, rule_id: str) -> tuple[list[str], list[str]]:
    """(core, support): QIDs carrying a class of the rule's set, from the place or an identity-merged item (core) and from
    items absorbed as nested assets (support: a mosque in Cairo can back a kind but not create it)."""
    want = ctx.class_sets.get(rule_id, set())
    core, support = [], []
    for q, cl in member_classes(c).items():
        if cl & want:
            m = (c.get("members") or {}).get(q, {})
            # a nested asset is core only when it carries the place (Lourdes and its sanctuary), not when it is one of many (Rome)
            nested = m.get("nested") and m.get("sitelinks", 0) < ctx.params.get("nested_core_share", 0.5) * c.get("sitelinks", 0)
            (support if nested else core).append(q)
    return core, support


def _capital(c: dict, ctx: Context) -> tuple[list[str], list[str]]:
    now, past = [], []
    items = [(c["qid"], c.get("capital_of", []))] + [(q, m.get("capital_of", [])) for q, m in (c.get("members") or {}).items()]
    for q, lst in items:
        for e in [*lst, *ctx.capitals.get(q, [])]:
            cl = set(e.get("classes") or ()) or ctx.state_classes.get(e["qid"], set())
            if not e.get("ended") and cl & STATE:
                now.append(q)
            elif e.get("ended") and cl & (FORMER_STATE | STATE):
                past.append(q)
    return now, past


def fire(c: dict, ctx: Context) -> tuple[list[K.Fired], dict[str, list[str]], dict]:
    """The rules that fire on one place: (fired, evidence ids by rule, facts for the pair conditions).
    Evidence ids are `wd:<qid>` for classes, `geo:<qid>` for geometry, `wdpa:<id>` for protected areas."""
    P, R = ctx.params, ctx.rules
    g = ctx.geo.get(c["qid"], {})
    pop = c.get("population") or 0
    ptype = (c.get("_type") or {}).get("place_type", "")
    settlement = ptype == "settlement"
    hits: dict[str, list[str]] = {}

    roles: dict[str, str] = {}

    def add(rule_id: str, evidence: list[str], role: str | None = None) -> None:
        hits[rule_id] = evidence
        if role:
            roles[rule_id] = role

    def by_class(rid: str) -> list[str]:
        """Evidence ids of a class rule; the rule is core when the place or an identity-merged item carries the class."""
        core, support = _hit(c, ctx, rid)
        return [f"wd:{q}" for q in (core or support)], ("core" if core else "support")

    classes = {rid: by_class(rid) for rid in ("R03", "R05", "R07", "R10", "R12b", "R13b", "R14b", "R15", "R17b", "R18")}
    own = c["qid"]

    now, past = _capital(c, ctx)
    if now:
        add("R01", [f"wd:{q}" for q in now])
    elif past:
        add("R02", [f"wd:{q}" for q in past])
    coast = g.get("coast_km")
    for rid in ("R03", "R07", "R10", "R13b", "R14b", "R15", "R18", "R17b"):
        ev, role = classes[rid]
        if ev and not (rid == "R17b" and not settlement):
            add(rid, ev, role)
    ev, role = classes["R05"]
    if ev and coast is not None and coast <= P["maritime_coast_km"]:
        add("R05", ev + [f"geo:{own}"], role)
    if coast is not None and coast <= P["seaside_coast_km"]:
        add("R03b", [f"geo:{own}"])
    if settlement and pop >= P["maritime_city_pop"] and coast is not None and coast <= P["maritime_coast_km"]:
        add("R05b", [f"geo:{own}"])
    wd = ctx.wdpa.get(str(c.get("wdpa") or ""))
    if wd and wd.get("iucn_cat") in P["strict_iucn"]:
        add("R12", [f"wdpa:{c['wdpa']}"])
    if classes["R12b"][0] and own in {q[3:] for q in classes["R12b"][0]}:
        add("R12b", [f"wd:{own}"])
    protected = "R12" in hits or "R12b" in hits
    bare = g.get("bare_20km")
    if bare is not None and bare >= P["bare_20km"]:
        add("R13", [f"geo:{own}"])
    if g and ((g.get("relief_10km") or 0) >= P["relief_10km_m"] or (g.get("max_elev_2km") or 0) >= P["summit_2km_m"]):
        add("R14", [f"geo:{own}"])
    if pop >= P["metropolis_pop"]:
        add("R16", [f"wd:{own}"])
    title = ctx.whs_title(c.get("whs"))
    if settlement and title and ctx.old_town_re.search(title):
        add("R17", [f"whs:{str(c['whs'])}"])
    water = (g.get("water_10km") or 0) + (g.get("wetland_10km") or 0)
    if g and water >= P["water_share"] and (coast is None or coast >= P["water_min_coast_km"]):
        add("R18b", [f"geo:{own}"])
    tree = g.get("tree_10km")
    if tree is not None and tree >= P["tree_10km"]:
        add("R19", [f"geo:{own}"])
    open_land = (g.get("crop_10km") or 0) + (g.get("grass_10km") or 0)
    if g and open_land >= P["open_land_10km"] and not ctx.city_index(c, P["big_city_km"], P["big_city_pop"]):
        add("R20", [f"geo:{own}"])
    if pop >= P["fallback_pop"]:
        add("R21", [f"wd:{own}"])

    fired = []
    for rid in hits:
        r = R[rid]
        fired.append(K.Fired(rid, r["kind"], r["source"], float(r["strength"]), roles.get(rid, r["role"]) if r["role"] == "core" else r["role"],
                             tuple(x for x in r["excludes"].split("|") if x)))
    facts = {
        "population": pop,
        "living_worship": bool(classes["R10"][0]) and not classes["R07"][0],
        "beach_within_2km": False,                       # needs OSM (S3d)
        "protected_overlap": 1.0 if protected else 0.0,
        "cropland_share": g.get("crop_10km", 0.0),
        "tree_cover": g.get("tree_10km", 0.0),
        "water_is_marine": False,
    }
    return fired, hits, facts


def kinds_for(c: dict, ctx: Context, pairs: list[K.Pair]) -> tuple[K.Selection, dict[str, list[str]]]:
    fired, hits, facts = fire(c, ctx)
    return K.select_kinds(fired, facts, pairs), hits


def city_index_from(places: list[dict]):
    """A function answering: is there another place of at least `pop` inhabitants within `km` of this one?"""
    big = [(p["lat"], p["lon"], p["qid"]) for p in places if (p.get("population") or 0) >= 50_000]
    from atlas.geo import haversine_km

    def near(c: dict, km: float, pop: int) -> bool:
        lat = c["lat"]
        for la, lo, q in big:
            if q != c["qid"] and abs(la - lat) <= km / 100.0 and haversine_km(lat, c["lon"], la, lo) <= km:
                return True
        return False
    return near


def whs_titles_from(path: Path = ROOT / "data" / "inputs" / "whs_properties.csv") -> dict[str, str]:
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["id_number"]: r["site"] for r in csv.DictReader(fh) if r.get("category") in ("Cultural", "Mixed")}


def state_classes_from(raw: Path) -> dict[str, set[str]]:
    """QID -> classes, for the states that places are or were the capital of."""
    import duckdb
    con = duckdb.connect()
    out: dict[str, set[str]] = defaultdict(set)
    for f in ("attention", "details"):
        p = raw / f"{f}.parquet"
        if p.is_file():
            for q, inst in con.execute(f"SELECT qid, instance_of FROM read_parquet('{p.as_posix()}') WHERE instance_of IS NOT NULL").fetchall():
                out[q] |= set(inst)
    return out


def summary(places: list[dict]) -> dict:
    n = len(places)
    counts = defaultdict(int)
    blank = 0
    for p in places:
        ks = p.get("kinds", [])
        blank += not ks
        for k in ks:
            counts[k["kind"]] += 1
    return {"places": n, "blank": blank, "blank_share": round(blank / max(n, 1), 4),
            "by_kind": {k: (v, round(v / max(n, 1), 3)) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])}}


__all__ = ["Context", "fire", "kinds_for", "load_rules", "load_class_sets", "load_params", "city_index_from", "state_classes_from", "summary", "math"]
