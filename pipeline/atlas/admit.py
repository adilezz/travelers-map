"""First admission pass: from the extracted Wikidata subset to a bundle the gates can judge (document 1 §5-6).

    python -m atlas.admit [--raw data/raw/wikidata/2026-10-05] [--out build/first]

Rules R1 to R5 (R6 anchors are empty) run on the S1/S2 data. What this pass does NOT have yet, and says so
in the bundle manifest: pageviews (so *N* has no pageview term), WDPA and Ramsar (so IUCN-based R1 and
the R4 signal rest on heritage designations only), the kind rule engine's landcover and relief facts, and
the registry (ids are provisional and nothing is committed). Every number it produces is a first measurement
to be argued with, not a result.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import random
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from atlas import capitals as CAP
from atlas import geofacts as GF
from atlas import kindrules as KR
from atlas import kinds as K
from atlas import pageviews as PV
from atlas import signal as S
from atlas import wdpa as W
from atlas.geo import fold, haversine_km
from atlas.minting import mint_or_reuse
from atlas.registry import Registry

ROOT = Path(__file__).resolve().parents[2]
RETRIEVED = "2026-10-05"
# national parks, nature and biosphere reserves, protected areas and Natura 2000 sites: the class route to a national designation
PROTECTED = {"Q46169", "Q1316973", "Q943017", "Q20488347", "Q179049", "Q158454", "Q473972", "Q15069452"}
PROPERTY_ID = re.compile(r"^\d+(bis|ter|quater)?$")      # a whole World Heritage property; "669-612" is a component (an asset, D25)
MAX_NAME = 60


def short_name(name: str, aliases: list[str]) -> str:
    """Official World Heritage titles run to 150 characters: use a short alias, else cut at a natural break."""
    name = " ".join(name.split())
    m = re.match(r"^(.*), (The|A|An)$", name)
    if m:
        name = f"{m.group(2)} {m.group(1)}"
    if len(name) <= MAX_NAME:
        return name
    for a in sorted((" ".join(x.split()) for x in aliases), key=len):
        if 3 <= len(a) <= MAX_NAME:
            return a
    for sep in (": ", " – ", " - ", ", "):
        head = name.split(sep)[0]
        if 3 <= len(head) <= MAX_NAME:
            return head
    return name[:MAX_NAME].rsplit(" ", 1)[0]


def load_types(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# A living city that was also a polis or has an archaeological site inside it is a city, not a ruin
# (Cairo, Alexandria, Syracuse): these classes make the settlement rows win over the site rows.
LIVING_CITY = {"Q1549591", "Q5119", "Q108178728", "Q174844", "Q200250"}


def _rows(classes: list[str], types: list[dict]) -> list[dict]:
    have = set(classes)
    hit = [t for t in types if t["class_qid"] in have and t["place_like"] == "yes"]
    if have & LIVING_CITY and any(t["place_type"] == "settlement" for t in hit):
        hit = [t for t in hit if t["place_type"] == "settlement"]
    return hit


def classify(classes: list[str], types: list[dict]) -> dict | None:
    """The first row of the types table (specific before general, in file order) that the item's classes hit."""
    hit = _rows(classes, types)
    return hit[0] if hit else None


def kind_hints(classes: list[str], types: list[dict]) -> list[str]:
    have = set(classes)
    allowed = {id(t) for t in _rows(classes, types)}
    seen: list[str] = []
    for t in types:
        if t["class_qid"] in have and t["kind_hint"] and t["kind_hint"] not in seen and (id(t) in allowed or t["place_like"] != "yes"):
            seen.append(t["kind_hint"])
    return seen[:3]


def notability(c: dict, cfg: dict) -> float:
    """N = log10(1+SL) + 0.5 log10(1+PV/1000) + R + C. Sitelinks enter as D, the discrimination score; PV is absent until S4 has run."""
    n = cfg["notability"]
    sl = c.get("D") if c.get("D") is not None else c.get("sitelinks", 0)
    r = 0.0
    if c.get("whs") and PROPERTY_ID.match(str(c["whs"])):
        r += n["recognition"]["whs"]                                          # a whole property, never a serial component
    if c.get("heritage"):
        r += n["recognition"]["national_top"]
    rec = n["recognition"]
    if c.get("iucn"):
        r += rec.get("iucn_ia_ii", 0.0)                                       # WDPA category Ia, Ib or II of 100 km2 or more
    elif set(c.get("classes", ())) & PROTECTED:
        r += rec.get("protected_designation", 0.0)                            # a national park or reserve by class (a national designation)
    r = min(r, n["recognition_cap"])
    pv = c.get("pv") or 0                                                   # S4: twelve-month English pageviews, the best of the merged items
    pop = c.get("population") or 0
    size = 0.0
    if pop >= n["size_term_reference_population"]:
        size = min(n["size_term_cap"], n["size_term_coefficient"] * math.log10(pop / n["size_term_reference_population"]))
    return math.log10(1 + max(sl, 0)) + n.get("pageview_weight", 0.5) * math.log10(1 + pv / 1000.0) + r + size


def attach_pageviews(places: list[dict], pv: dict[str, int]) -> int:
    """A place carries the most-viewed article among its merged items. Returns how many places got a figure."""
    n = 0
    for c in places:
        vals = [pv[q] for q in [c["qid"], *c.get("alt_qids", [])] if q in pv]
        c["pv"] = max(vals) if vals else None
        n += bool(vals)
    return n


def whs_counts(places: list[dict]) -> dict[str, int]:
    n: dict[str, int] = defaultdict(int)
    for p in places:
        if _holds(p):
            n[p["iso3"]] += 1
    return n


def icon_count(whs: int, t: dict) -> int:
    """How many Icons a country gets: more where UNESCO inscribed more (D38)."""
    steps = t["icon"]["country_top_by_whs"]                              # [[max_whs, top], ...] in ascending order
    for limit, top in steps:
        if limit is None or whs <= limit:
            return top
    return steps[-1][1]


def assign_tiers(places: list[dict], cfg: dict) -> None:
    """Icon and Major by country rank (Icon count scaled by World Heritage properties); Notable also by global
    percentile or the top 40 % of the country (document 1 section 6.3, D38)."""
    t = cfg["tiers"]
    ns = sorted(p["_n"] for p in places)

    def pct(n: float) -> float:
        return 100.0 * bisect.bisect_left(ns, n) / max(1, len(ns))

    by_iso: dict[str, list[dict]] = defaultdict(list)
    for p in places:
        by_iso[p["iso3"]].append(p)
    counts = whs_counts(places)
    for iso, ps in by_iso.items():
        ps.sort(key=lambda p: (-p["_n"], p["name_en"]))
        small = len(ps) < t["icon"]["small_country_below"]
        icon_top = t["icon"]["small_country_top"] if small else icon_count(counts.get(iso, 0), t)
        major_next = t["major"]["small_country_next"] if small else t["major"]["country_next"]
        for i, p in enumerate(ps):
            g = pct(p["_n"])
            if i < icon_top:
                p["tier"], p["tier_reason"] = "Icon", "top of its country"
            elif g >= t["major"]["global_percentile"] or i < icon_top + major_next:
                p["tier"], p["tier_reason"] = "Major", "global p95 or next of its country"
            elif g >= t["notable"]["global_percentile"] or i < t["notable"]["country_top_share"] * len(ps):
                p["tier"], p["tier_reason"] = "Notable", "global p75 or top 40 % of country"
            else:
                p["tier"], p["tier_reason"] = "Local", "the rest"


def candidates(raw: Path, overrides: dict[str, str]) -> dict[str, dict]:
    """One record per QID from every S1/S2 file."""
    import duckdb
    con = duckdb.connect()
    cands: dict[str, dict] = {}

    def get(qid: str, iso: str) -> dict:
        iso = overrides.get(qid, iso)
        c = cands.setdefault(qid, {"qid": qid, "iso3": iso, "classes": set(), "sitelinks": 0, "heritage": [], "isos": set()})
        c["isos"].add(iso)
        if qid in overrides:
            c["iso3"] = overrides[qid]
        return c

    def rows(f: str, cols: str):
        p = raw / f"{f}.parquet"
        return con.execute(f"SELECT {cols} FROM read_parquet('{p.as_posix()}')").fetchall() if p.is_file() else []

    for qid, iso, lab, loc, lat, lon, sl, inst in rows("attention", "qid, iso3, label_en, label_loc, lat, lon, sitelinks, instance_of"):
        c = get(qid, iso)
        c.update(label_en=lab or c.get("label_en"), label_loc=loc or c.get("label_loc"), lat=lat, lon=lon)
        c["sitelinks"] = max(c["sitelinks"], sl or 0)
        c["classes"] |= set(inst or [])
    for qid, iso, lab, loc, lat, lon, sl, pop, fam in rows("class", "qid, iso3, label_en, label_loc, lat, lon, sitelinks, population, family"):
        c = get(qid, iso)
        c.update(label_en=lab or c.get("label_en"), label_loc=loc or c.get("label_loc"), lat=lat if c.get("lat") is None else c["lat"],
                 lon=lon if c.get("lon") is None else c["lon"])
        c["sitelinks"] = max(c["sitelinks"], sl or 0)
        c["population"] = max(c.get("population") or 0, pop or 0) or None
        c["classes"].add(fam.split("_")[1])                                  # class_<qid>_<band>
    for qid, iso, lab, loc, lat, lon, sl, pop in rows("popall", "qid, iso3, label_en, label_loc, lat, lon, sitelinks, population"):
        c = get(qid, iso)
        c.update(label_en=lab or c.get("label_en"), label_loc=loc or c.get("label_loc"), lat=lat, lon=lon)
        c["sitelinks"] = max(c["sitelinks"], sl or 0)
        c["population"] = max(c.get("population") or 0, pop or 0) or None
    for qid, iso, lab, loc, lat, lon, sl, whs, wdpa in rows("institutional", "qid, iso3, label_en, label_loc, lat, lon, sitelinks, whs, wdpa"):
        c = get(qid, iso)
        c.update(label_en=lab or c.get("label_en"), label_loc=loc or c.get("label_loc"))
        if c.get("lat") is None:
            c["lat"], c["lon"] = lat, lon
        c["sitelinks"] = max(c["sitelinks"], sl or 0)
        if whs:
            c["whs"] = better_whs(c.get("whs"), norm_whs(whs) or None)
        if wdpa:
            c["wdpa"] = wdpa
    up: dict[str, list[str]] = {}
    for r in rows("details", "qid, aliases_en, aliases_loc, instance_of, heritage, label_en, label_loc, located_in, part_of, capital_of"):
        qid, a_en, a_loc, inst, her, lab, loc, located, part, cap = r
        up[qid] = list(dict.fromkeys([*(located or []), *(part or [])]))
        if qid in cands:
            c = cands[qid]
            c["aliases"] = list(a_en or []) + list(a_loc or [])
            c["classes"] |= set(inst or [])
            c["heritage"] = list(her or [])
            c["capital_of"] = [dict(x) for x in (cap or [])]
            c["label_en"] = c.get("label_en") or lab
            c["label_loc"] = c.get("label_loc") or loc
    for qid, c in cands.items():                                              # ancestors up to three hops (Hagia Sophia, Fatih, Istanbul)
        seen: list[str] = []
        frontier = up.get(qid, [])
        for _ in range(3):
            seen += [q for q in frontier if q not in seen]
            frontier = [x for q in frontier for x in up.get(q, [])]
        c["parents"] = seen
    for qid, wikis in rows("profile", "qid, wikis"):
        if qid in cands and any(w.endswith("wikivoyage") for w in wikis or []):
            cands[qid]["voyage"] = True                                       # S3: a travel-guide article is an independent signal
    return cands


def load_admin_classes(path: Path) -> set[str]:
    """Classes of administrative units that are records of a place, not destinations (data/rules/admin_classes.csv)."""
    if not path.is_file():
        return set()
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["class_qid"] for r in csv.DictReader(fh) if r.get("class_qid")}


_KNOWN_WHS: set[str] | None = None


# D38: entities that are not destinations. They stay out of the bundle and are listed in context.csv.
CONTEXT_CLASSES = {"Q5107", "Q165", "Q9430", "Q4022", "Q3024240"}      # continent, sea, ocean, river, historical country
CONTEXT_POPULATION = 20_000_000                                          # a region this populous is a macro-region (Middle East)
# a wadi, a valley or a protected area is a destination even when Wikidata also calls it a river (Wadi Rum, Wadi Mujib)
DESTINATION_CLASSES = {"Q187971", "Q39816", "Q473972", "Q46169", "Q179049", "Q15069452"}
LARGE_FEATURES = {"Q8514", "Q46831", "Q2624046"}                        # desert, mountain range, mountain chain
LARGE_SITELINKS = 150
TRANSNATIONAL = 3                                                        # a desert, lake or region found in this many of the nine countries


def is_context(c: dict, types: list[dict]) -> str:
    """Why an admitted candidate is context, not a destination ('' when it is one)."""
    if c["classes"] & CONTEXT_CLASSES and not (c["classes"] & DESTINATION_CLASSES) and not c.get("whs"):
        return "continent, sea, ocean, river or historical country"
    t = c.get("_type") or {}
    if c["classes"] & LARGE_FEATURES and c["sitelinks"] >= LARGE_SITELINKS and not (c["classes"] & DESTINATION_CLASSES) and not c.get("whs"):
        return "a desert or mountain range known in 150 or more languages (Sahara, Alps, Andes)"
    if t.get("place_type") == "area" and (c.get("population") or 0) >= CONTEXT_POPULATION:
        return f"region of {c['population']:,.0f} inhabitants"
    if t.get("place_type") == "area" and len(c.get("isos", ())) >= TRANSNATIONAL and c["sitelinks"] >= 100 and "R1" not in c["rules"]:
        return f"found in {len(c['isos'])} of the nine countries"
    return ""


def better_whs(a: object, b: object) -> object:
    """Of two World Heritage ids keep a whole property over a serial component, else the first."""
    whole = lambda x: bool(x) and bool(PROPERTY_ID.match(str(x)))      # noqa: E731
    return a if whole(a) or not whole(b) and a else (b or a)


def known_whs() -> set[str]:
    """Property numbers of the UNESCO list (data/inputs/whs_properties.csv)."""
    global _KNOWN_WHS
    if _KNOWN_WHS is None:
        path = ROOT / "data" / "inputs" / "whs_properties.csv"
        with open(path, encoding="utf-8", newline="") as fh:
            _KNOWN_WHS = {r["id_number"] for r in csv.DictReader(fh)}
    return _KNOWN_WHS


def norm_whs(value: object) -> str:
    """A World Heritage id checked against the UNESCO list, or "" when it is not one (D38).

    '173rev' is a revised inscription of property 173; '1133bis' an extension; '669-612' and '874.594' are
    serial components (kept as such, never whole properties); a stray string such as the Russian wiki label
    '№395 в списке...' on Pisa holds one number, which is used when UNESCO lists it."""
    v = str(value).strip()
    v = re.sub(r"rev$", "", v)
    m = re.match(r"^(\d+)(bis|ter|quater)?$", v) or re.match(r"^(\d+)[-.]\d+$", v)
    if m:
        return v if m.group(1) in known_whs() else ""
    nums = re.findall(r"\d+", v)
    return nums[0] if len(nums) == 1 and nums[0] in known_whs() else ""


def load_overrides(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("loser_key")]


def load_anchors(path: Path) -> dict[str, str]:
    """R6: qid -> the owner's note (data/anchors/anchors.csv)."""
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["qid"]: r.get("note", "") for r in csv.DictReader(fh) if r.get("qid")}


def admit(cands: dict[str, dict], scores: dict[str, dict], types: list[dict], cfg: dict, top_share: float = S.TOP_SHARE,
          wdpa: dict | None = None, anchors: dict[str, str] | None = None) -> list[dict]:
    a = cfg["admission"]
    out: list[dict] = []
    for c in cands.values():
        if c.get("lat") is None or not (c.get("label_en") or c.get("label_loc")):
            continue
        t = classify(sorted(c["classes"]), types)
        sc = scores.get(c["qid"])
        c["D"] = sc["D"] if sc else None
        mass = admitted = None
        if sc and "pct" in sc:
            admitted = sc["pct"] >= 100.0 * (1.0 - top_share)
            mass = True
        rules: list[str] = []
        strict = W.strict_and_large((wdpa or {}).get(str(c.get("wdpa"))), cfg["admission"].get("r1_institutional", {}).get("iucn_min_area_km2", 100))
        c["iucn"] = strict                                                    # IUCN Ia, Ib or II of 100 km2 or more: also a recognition term
        if strict or (c.get("whs") and PROPERTY_ID.match(str(c["whs"]))):
            rules.append("R1")
        if t:
            if (mass is None and c["sitelinks"] >= a["r2_attention_sitelinks"]) or admitted:
                rules.append("R2")
            if (c.get("population") or 0) >= a["r3_city_population"] and t["place_type"] == "settlement":
                rules.append("R3")
            if c["sitelinks"] >= a["r4_corroborated_sitelinks"] and (c["heritage"] or c.get("wdpa") or (c.get("voyage") and t["place_type"] != "settlement")):
                rules.append("R4")
        if c["qid"] in (anchors or {}):
            rules.append("R6")                                                # the owner's anchor, labelled with its note
            c["anchor_note"] = anchors[c["qid"]]
        if not rules:
            c["_floor"] = bool(t)                                            # candidate for R5
            c["_type"] = t
            continue
        c["_type"] = t
        c["rules"] = rules
        out.append(c)
    # R5: the top five by N in each country, among place-like candidates not already admitted
    have = {c["qid"] for c in out}
    by_iso: dict[str, list[dict]] = defaultdict(list)
    for c in cands.values():
        if c["qid"] not in have and c.get("_floor"):
            by_iso[c["iso3"]].append(c)
    for cs in by_iso.values():
        cs.sort(key=lambda c: -notability(c, cfg))
        for c in cs[: a["r5_country_floor"]["sovereign"]]:
            c["rules"] = ["R5"]
            out.append(c)
    return out


_GENERIC = re.compile(r"\b(the )?(city|town|municipality|comune|commune|ciudad|ville)( of| de| di)?\b|\b(historic|historical|province|ramparts|walls)\b")


def base_name(name: str) -> str:
    """Folded name without generic words: 'Madrid city', 'City of Valencia' and 'Madrid' are one name."""
    return " ".join(_GENERIC.sub(" ", fold(name)).split()) or fold(name)


NESTED = ("located in", "ruins within", "serial component")        # absorbed as an asset, not as the same destination


def _take_members(parent: dict, child: dict, nested: bool = False) -> None:
    """Remember what the merged items were (their classes and capital-of statements) so kinds can cite them.
    A nested asset (a mosque in Cairo) can only support a kind; an identity merge (Thebes into Luxor) can create one."""
    m = parent.setdefault("members", {})
    m[child["qid"]] = {"classes": set(child.get("classes", ())), "capital_of": child.get("capital_of", []), "nested": nested,
                       "sitelinks": child.get("sitelinks", 0)}
    for q, x in (child.get("members") or {}).items():
        m[q] = {**x, "nested": x.get("nested", False) or nested}


def merge_duplicates(places: list[dict], same_name_km: float) -> list[dict]:
    """Same folded name within `same_name_km` in one country: keep the one with most sitelinks (document 1 §5.1)."""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in places:
        by_key[(p["iso3"], base_name(p["name_en"]))].append(p)
    drop: set[str] = set()
    for group in by_key.values():
        group.sort(key=lambda p: (-p.get("sitelinks", 0), p["qid"]))
        for i, a in enumerate(group):
            if a["qid"] in drop:
                continue
            for b in group[i + 1:]:
                if b["qid"] not in drop and haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) <= same_name_km:
                    drop.add(b["qid"])
                    a.setdefault("alt_qids", []).append(b["qid"])
                    _take_members(a, b)
                    a["whs"] = better_whs(a.get("whs"), b.get("whs"))
    return [p for p in places if p["qid"] not in drop]


COLOCATED_KM = 5.0
SEAT_KM = 10.0
STUB_SITELINKS = 15                                                  # a World Heritage record this thin is a stub, not a destination
SAME_KIND_KM = 25.0


_NAME_STOP = {"mount", "mt", "mountain", "monte", "mont", "jbel", "djebel", "national", "park", "parc", "parque", "parco", "reserve",
              "nature", "natural", "area", "the", "of", "de", "del", "di", "la", "le", "el", "and", "y", "et", "islands", "island"}


def _core(p: dict) -> set[str]:
    """Distinctive words of a place's name: the word that makes Kilimanjaro National Park and Mount Kilimanjaro one name."""
    return {w for w in fold(p.get("label_en") or p.get("name_en") or "").split() if w not in _NAME_STOP}


def _holds(p: dict) -> bool:
    """The place carries a whole World Heritage property: what is inside it is its asset."""
    return bool(p.get("whs")) and bool(PROPERTY_ID.match(str(p["whs"])))


def _ruins(p: dict) -> bool:
    return (p.get("_type") or {}).get("place_type") == "site" and (p.get("_type") or {}).get("kind_hint") == "ruins"


SERIAL_ID = re.compile(r"^(\d+)[-.]")


def absorb(places: list[dict], overrides: list[dict] | None = None, admin: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """D25 / document 1 section 5.2: nested monuments and same-property neighbours become assets of the parent.

    1. Items sharing one World Heritage property id: the most cited keeps the place.
    2. Serial components (id 669-612) join the place carrying the whole property (669).
    3. A site located in or part of an admitted place with more sitelinks becomes its asset (Colosseum into Rome);
       a site with more sitelinks than its parent stays (Pompeii beside the commune of Pompei, Ephesus beside Selcuk).
    Returns the kept places and the absorption log; the owner's list is data/golden/structure.csv."""
    gone: dict[str, tuple[str, str]] = {}
    keep_kinds: set[str] = set()
    for o in overrides or []:                                               # 0. the owner's rulings (merge_overrides.csv) come first
        lo = next((p for p in places if f"qid:{p['qid']}" == o["loser_key"] or o["loser_key"] in {f"qid:{q}" for q in p.get("alt_qids", [])}), None)
        hi = next((p for p in places if f"qid:{p['qid']}" == o["survivor_key"]), None)
        if lo and hi and lo is not hi:
            gone[lo["qid"]] = (hi["qid"], f"owner ruling: {o['reason']}")
            keep_kinds.add(lo["qid"])
    whole: dict[str, list[dict]] = defaultdict(list)
    for p in places:
        if p.get("whs") and PROPERTY_ID.match(str(p["whs"])):
            whole[str(p["whs"])].append(p)
    winner = {w: max(g, key=lambda p: (p["sitelinks"], p["qid"])) for w, g in whole.items()}
    for w, g in whole.items():
        for p in g:
            if p is not winner[w]:
                gone[p["qid"]] = (winner[w]["qid"], f"same World Heritage property {w}")
    for p in places:
        m = SERIAL_ID.match(str(p.get("whs") or ""))
        if m and m.group(1) in winner and p["qid"] not in gone and winner[m.group(1)]["qid"] != p["qid"] \
                and not ((p.get("_type") or {}).get("place_type") == "settlement" and winner[m.group(1)]["sitelinks"] * 3 < p["sitelinks"]):
            gone[p["qid"]] = (winner[m.group(1)]["qid"], f"serial component of property {m.group(1)}")
    held = [p for p in places if p.get("whs") and PROPERTY_ID.match(str(p["whs"])) and p["qid"] not in gone]
    for p in places:                                                        # 4. the property record and the famous item of one destination
        if p["qid"] in gone or p.get("whs") or (p.get("_type") or {}).get("place_type") == "settlement":
            continue
        for a in held:
            if a["sitelinks"] < STUB_SITELINKS <= p["sitelinks"] and a["iso3"] == p["iso3"] and a["qid"] != p["qid"] and a["qid"] not in gone and (a.get("_type") or {}).get("place_type") != "settlement" \
                    and haversine_km(a["lat"], a["lon"], p["lat"], p["lon"]) <= COLOCATED_KM:
                gone[a["qid"]] = (p["qid"], f"property record of {p['qid']} (within {COLOCATED_KM:g} km, under {STUB_SITELINKS} sitelinks)")
                p["whs"] = a["whs"]
                break
    for p in places:                                                        # 4a. a city and the record of its historic centre (Rome, Florence)
        if p["qid"] in gone or _holds(p) or (p.get("_type") or {}).get("place_type") != "settlement":
            continue
        for a in held:
            if a["sitelinks"] * 3 < p["sitelinks"] and a["iso3"] == p["iso3"] and a["qid"] not in gone \
                    and _core(a) & _core(p) and haversine_km(a["lat"], a["lon"], p["lat"], p["lon"]) <= SEAT_KM:
                gone[a["qid"]] = (p["qid"], f"property record of {p['qid']} (shared name, within {SEAT_KM:g} km, a third of its sitelinks)")
                p["whs"] = a["whs"]
                break
    for p in places:                                                        # 4b. a protected area and its mountain (Kilimanjaro)
        if p["qid"] in gone or p.get("whs") or (p.get("_type") or {}).get("place_type") != "area":
            continue
        for a in held:
            if (a.get("_type") or {}).get("place_type") == "area" and a["qid"] not in gone and a["iso3"] == p["iso3"] \
                    and _core(a) & _core(p) and a["sitelinks"] < p["sitelinks"] and haversine_km(a["lat"], a["lon"], p["lat"], p["lon"]) <= COLOCATED_KM:
                gone[a["qid"]] = (p["qid"], f"protected area of {p['qid']} (areas within {COLOCATED_KM:g} km)")
                p["whs"] = a["whs"]
                break
    held = [p for p in places if p.get("whs") and PROPERTY_ID.match(str(p["whs"])) and p["qid"] not in gone]
    for p in places:                                                        # 5. ruins within 25 km of a World Heritage ruin (Saqqara into Giza)
        if p["qid"] in gone or p.get("whs") or not _ruins(p):
            continue
        near = [a for a in held if a["iso3"] == p["iso3"] and _ruins(a) and a["sitelinks"] > p["sitelinks"]
                and haversine_km(a["lat"], a["lon"], p["lat"], p["lon"]) <= SAME_KIND_KM]
        if near:
            top = max(near, key=lambda a: (a["sitelinks"], a["qid"]))
            gone[p["qid"]] = (top["qid"], f"ruins within {SAME_KIND_KM:g} km of World Heritage ruin {top['qid']}")
    for p in places:                                                        # 6. a province record folds into its seat
        if p["qid"] in gone or not (set(p.get("classes", ())) & (admin or set())):
            continue
        seats = [a for a in places if a is not p and a["qid"] not in gone and a["iso3"] == p["iso3"] and not (set(a.get("classes", ())) & (admin or set()))
                 and (a.get("_type") or {}).get("place_type") == "settlement" and haversine_km(a["lat"], a["lon"], p["lat"], p["lon"]) <= SEAT_KM]
        if seats:
            top = max(seats, key=lambda a: (a["sitelinks"], a["qid"]))
            gone[p["qid"]] = (top["qid"], f"administrative province of its seat {top['qid']} (within {SEAT_KM:g} km)")
    index = {}
    for p in places:
        for q in [p["qid"], *p.get("alt_qids", [])]:
            index[q] = p
    for _ in range(2):                                                      # twice: a place that gained a property by absorption holds it for the second pass
        for q, (par, _why) in list(gone.items()):
            owner = index.get(par)
            child = index.get(q)
            if owner is not None and child is not None and not owner.get('whs') and child.get('whs'):
                owner['whs'] = child['whs']
        for p in places:
            t = p.get("_type") or {}
            if p["qid"] in gone or t.get("place_type") != "site":
                continue
            parents = [index[q] for q in p.get("parents", []) if q in index and index[q] is not p and (index[q]["sitelinks"] > p["sitelinks"] or _holds(index[q]) and not _holds(p))
                       and (index[q].get("_type") or {}).get("place_type") in ("settlement", "site")]
            if parents:
                top = max(parents, key=lambda a: (a["sitelinks"], a["qid"]))
                gone[p["qid"]] = (top["qid"], f"located in or part of {top['qid']}")
    by_qid = {p["qid"]: p for p in places}

    def root(q: str) -> str:
        seen = set()
        while q in gone and q not in seen:
            seen.add(q)
            q = gone[q][0]
        return q
    log = []
    for q, (_, why) in sorted(gone.items()):
        r = root(q)
        if r == q or r not in by_qid:
            continue
        child, parent = by_qid[q], by_qid[r]
        parent.setdefault("alt_qids", []).extend([q, *child.get("alt_qids", [])])
        _take_members(parent, child, why.startswith(NESTED))
        if not why.startswith("located in") and not why.startswith("administrative province"):
            parent["whs"] = better_whs(parent.get("whs"), child.get("whs"))   # a nested site does not give its city the property
        if q in keep_kinds:
            parent["classes"] = set(parent["classes"]) | set(child["classes"])      # a ruled merge keeps the loser's kinds (Meru on the park)
        parent.setdefault("absorbed", []).append(child.get("label_en") or q)
        ct, pt = child.get("_type") or {}, parent.get("_type") or {}
        log.append({"child": q, "child_name": child.get("label_en"), "parent": r, "parent_name": parent.get("label_en"), "reason": why,
                    "child_type": ct.get("place_type", ""), "parent_type": pt.get("place_type", ""),
                    "child_hint": ct.get("kind_hint", ""), "parent_hint": pt.get("kind_hint", "")})
    absorbed = {e["child"] for e in log}
    return [p for p in places if p["qid"] not in absorbed], log


def record(c: dict, place_id: str, types_row: dict | None, types: list[dict], selection=None, hits: dict | None = None) -> dict:
    qids = [c["qid"], *c.get("alt_qids", [])]
    ev = [{"asset_id": f"wd:{q}", "source": "wikidata", "url": f"https://www.wikidata.org/wiki/{q}",
           "retrieved": RETRIEVED, "source_key": f"qid:{q}"} for q in qids]
    if c.get("whs") and PROPERTY_ID.match(str(c["whs"])):
        ev.append({"asset_id": f"whs:{c['whs']}", "source": "unesco_whs", "url": f"https://whc.unesco.org/en/list/{c['whs']}",
                   "retrieved": RETRIEVED, "source_key": f"whs:{c['whs']}"})
    kinds: list[dict] = []
    have = {e["asset_id"] for e in ev}
    for ch in (selection.kept if selection else []):
        ids: list[str] = []
        for rid in ch.rule_ids:
            ids += (hits or {}).get(rid, [])
        ids = list(dict.fromkeys(ids))
        for a in ids:
            if a not in have:
                ev.append(_asset(a, c))
                have.add(a)
        kinds.append({"kind": ch.kind, "rule": "+".join(ch.rule_ids), "strength": ch.strength, "evidence": ids})
    full = " ".join((c.get("label_en") or c.get("label_loc")).split())
    name = short_name(full, [x for x in [c.get("label_loc"), *c.get("aliases", [])] if x])
    aliases = sorted({x for x in [full, c.get("label_loc"), *c.get("aliases", [])] if x and x != name})
    r = {"place_id": place_id, "type": (types_row or {"place_type": "site"})["place_type"], "name_en": name,
         "aliases": aliases, "iso3": c["iso3"], "lat": c["lat"], "lon": c["lon"], "tier": c["tier"],
         "tier_reason": c["tier_reason"], "qid": c["qid"], "keys": [f"qid:{q}" for q in qids], "status": "active",
         "evidence": ev, "kinds": kinds, "rules": c["rules"], "sitelinks": c["sitelinks"]}
    if c.get("whs") and PROPERTY_ID.match(str(c["whs"])):
        r["whs_id"] = c["whs"]
    if c.get("population"):
        r["population"] = c["population"]
    if selection is not None:
        r["cut_kinds"] = selection.cut
        r["crowded"] = selection.crowded
    if not kinds:
        r["no_kind_reason"] = "no kind rule fired on the stored facts"
    return r


def _asset(asset_id: str, c: dict) -> dict:
    """The evidence record behind a kind rule that is not a Wikidata class."""
    kind, _, key = asset_id.partition(":")
    if kind == "geo":
        return {"asset_id": asset_id, "source": "geofacts", "retrieved": RETRIEVED, "source_key": asset_id,
                "url": "https://github.com/adilezz/travelers-map/blob/main/pipeline/atlas/geofacts.py"}
    return {"asset_id": asset_id, "source": "wdpa", "retrieved": RETRIEVED, "source_key": asset_id,
            "url": f"https://www.protectedplanet.net/{key}"}


def write_bundle(places: list[dict], out: Path, build_id: str, notes: dict) -> None:
    (out / "places").mkdir(parents=True, exist_ok=True)
    by_iso: dict[str, list[dict]] = defaultdict(list)
    for p in places:
        by_iso[p["iso3"]].append(p)
    for iso, ps in by_iso.items():
        ps.sort(key=lambda p: p["place_id"])
        (out / "places" / f"{iso}.json").write_text(json.dumps({"iso3": iso, "places": ps}, ensure_ascii=False, sort_keys=True),
                                                    encoding="utf-8")
    hashes = {f.relative_to(out).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
              for f in sorted(out.rglob("*")) if f.is_file() and f.name != "manifest.json"}
    manifest = {"build_id": build_id, "hashes": hashes, "counts": {"places": len(places),
                "per_country": {k: len(v) for k, v in sorted(by_iso.items())}}, **notes}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare(raw: Path, top_share: float = S.TOP_SHARE) -> dict:
    """Everything up to the tiers: the kept places with their N, the absorption log and the inputs used."""
    cfg = json.loads((ROOT / "data" / "rules" / "tiers.json").read_text(encoding="utf-8"))
    types = load_types(ROOT / "data" / "rules" / "types.csv")
    with open(ROOT / "data" / "rules" / "country_overrides.csv", encoding="utf-8", newline="") as fh:
        overrides = {r["qid"]: r["iso3"] for r in csv.DictReader(fh)}
    cands = candidates(raw, overrides)
    items, profiles = S.load(raw)
    scores = S.scores(items, profiles)
    admitted = admit(cands, scores, types, cfg, top_share, W.load(raw.parent.parent / "wdpa" / "wdpa_reduced.csv"),
                     load_anchors(ROOT / "data" / "anchors" / "anchors.csv"))
    context = [(c, is_context(c, types)) for c in admitted]
    admitted = [c for c, why in context if not why]
    for c in admitted:
        c["_n"] = notability(c, cfg)
        c["name_en"] = short_name(c.get("label_en") or c.get("label_loc"), [])
    places = merge_duplicates(admitted, cfg["dedup"]["same_name_km"])
    for c in places:
        c["_n"] = notability(c, cfg)
        c["name_en"] = c.get("label_en") or c.get("label_loc")
    places, absorbed = absorb(places, load_overrides(ROOT / "data" / "anchors" / "merge_overrides.csv"),
                              load_admin_classes(ROOT / "data" / "rules" / "admin_classes.csv"))
    pv = PV.load(raw.parent.parent / "pageviews" / raw.name / "pageviews.parquet")
    with_pv = attach_pageviews(places, pv)
    for c in places:
        c["_n"] = notability(c, cfg)
    return {"cfg": cfg, "types": types, "cands": cands, "places": places, "absorbed": absorbed, "with_pv": with_pv,
            "context": [(c["qid"], c.get("label_en") or c.get("label_loc"), c["iso3"], why) for c, why in context if why]}


def run(raw: Path, out: Path, top_share: float = S.TOP_SHARE) -> dict:
    prep = prepare(raw, top_share)
    cfg, types, cands, places, absorbed, with_pv = (prep[k] for k in ("cfg", "types", "cands", "places", "absorbed", "with_pv"))
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "context.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["qid", "name", "iso3", "why"])
        w.writerows(sorted(prep["context"]))
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "absorbed.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["child", "child_name", "parent", "parent_name", "reason", "child_type", "parent_type", "child_hint", "parent_hint"], lineterminator="\n")
        w.writeheader()
        w.writerows(absorbed)
    assign_tiers(places, cfg)
    reg = Registry()
    rng = random.Random(20261007)                          # provisional ids: the registry is not committed (D21)
    recs = []
    ctx = KR.Context(KR.load_rules(), KR.load_class_sets(), KR.load_params(), KR.state_classes_from(raw),
                     W.load(raw.parent.parent / "wdpa" / "wdpa_reduced.csv"),
                     GF.load(raw.parent.parent / "geofacts" / raw.name / "geofacts.parquet"), KR.city_index_from(places),
                     KR.whs_titles_from(), CAP.load(raw / "capitals.parquet"))
    pairs = K.load_pairs(ROOT / "data" / "rules" / "kind_pairs.csv")
    for c in sorted(places, key=lambda c: c["qid"]):
        pid = mint_or_reuse(reg, [f"qid:{c['qid']}"], "first-pass", rng)
        selection, hits = KR.kinds_for(c, ctx, pairs)
        recs.append(record(c, pid, c["_type"], types, selection, hits))
    notes = {"first_pass": True, "provisional_ids": True, "scope": "nine prototype countries",
             "missing": ([] if with_pv else ["pageviews (N has no pageview term)"]) + ["WDPA categories (when data/raw/wdpa/wdpa_reduced.csv is absent) and Ramsar", "OSM and UNESCO criteria for the kind rules marked not evaluated", "registry"],
             "top_share": top_share, "built_utc": datetime.now(UTC).isoformat(timespec="seconds"), "raw": raw.name}
    write_bundle(recs, out, f"first-pass-{raw.name}", notes)
    return {"places": len(recs), "candidates": len(cands), "by_rule": {r: sum(1 for p in recs if r in p["rules"]) for r in ("R1", "R2", "R3", "R4", "R5", "R6")}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1])
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "first")
    a = ap.parse_args(argv)
    print(run(a.raw, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
