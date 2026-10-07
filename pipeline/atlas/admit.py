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

from atlas import signal as S
from atlas import wdpa as W
from atlas.geo import fold, haversine_km
from atlas.minting import mint_or_reuse
from atlas.registry import Registry

ROOT = Path(__file__).resolve().parents[2]
RETRIEVED = "2026-10-05"
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


def classify(classes: list[str], types: list[dict]) -> dict | None:
    """The first row of the types table (specific before general, in file order) that the item's classes hit."""
    have = set(classes)
    for t in types:
        if t["class_qid"] in have and t["place_like"] == "yes":
            return t
    return None


def kind_hints(classes: list[str], types: list[dict]) -> list[str]:
    have = set(classes)
    seen: list[str] = []
    for t in types:
        if t["class_qid"] in have and t["kind_hint"] and t["kind_hint"] not in seen:
            seen.append(t["kind_hint"])
    return seen[:3]


def notability(c: dict, cfg: dict) -> float:
    """N without a pageview term (pageviews arrive with S4). Sitelinks enter as D, the discrimination score."""
    n = cfg["notability"]
    sl = c.get("D") if c.get("D") is not None else c.get("sitelinks", 0)
    r = 0.0
    if c.get("whs"):
        r += n["recognition"]["whs"]
    if c.get("heritage"):
        r += n["recognition"]["national_top"]
    r = min(r, n["recognition_cap"])
    pop = c.get("population") or 0
    size = 0.0
    if pop >= n["size_term_reference_population"]:
        size = min(n["size_term_cap"], n["size_term_coefficient"] * math.log10(pop / n["size_term_reference_population"]))
    return math.log10(1 + max(sl, 0)) + r + size


def assign_tiers(places: list[dict], cfg: dict) -> None:
    """Tier by the higher of a global percentile and a within-country rank (document 1 section 6.3)."""
    t = cfg["tiers"]
    ns = sorted(p["_n"] for p in places)

    def pct(n: float) -> float:
        return 100.0 * sum(1 for x in ns if x < n) / max(1, len(ns))

    by_iso: dict[str, list[dict]] = defaultdict(list)
    for p in places:
        by_iso[p["iso3"]].append(p)
    for ps in by_iso.values():
        ps.sort(key=lambda p: (-p["_n"], p["name_en"]))
        small = len(ps) < t["icon"]["small_country_below"]
        icon_top = t["icon"]["small_country_top"] if small else t["icon"]["country_top"]
        major_next = t["major"]["small_country_next"] if small else t["major"]["country_next"]
        for i, p in enumerate(ps):
            g = pct(p["_n"])
            if g >= t["icon"]["global_percentile"] or i < icon_top:
                p["tier"], p["tier_reason"] = "Icon", "global p99 or top of country"
            elif g >= t["major"]["global_percentile"] or i < icon_top + major_next:
                p["tier"], p["tier_reason"] = "Major", "global p95 or next of country"
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
        c = cands.setdefault(qid, {"qid": qid, "iso3": iso, "classes": set(), "sitelinks": 0, "heritage": []})
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
            c["whs"] = norm_whs(whs)
        if wdpa:
            c["wdpa"] = wdpa
    up: dict[str, list[str]] = {}
    for r in rows("details", "qid, aliases_en, aliases_loc, instance_of, heritage, label_en, label_loc, located_in, part_of"):
        qid, a_en, a_loc, inst, her, lab, loc, located, part = r
        up[qid] = list(dict.fromkeys([*(located or []), *(part or [])]))
        if qid in cands:
            c = cands[qid]
            c["aliases"] = list(a_en or []) + list(a_loc or [])
            c["classes"] |= set(inst or [])
            c["heritage"] = list(her or [])
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


def norm_whs(value: object) -> str:
    """'173rev' is a revised inscription of property 173 (19 such ids in the October 2026 data)."""
    return re.sub(r"rev$", "", str(value))


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
        if c.get("whs") and PROPERTY_ID.match(str(c["whs"])):
            rules.append("R1")
        elif W.strict_and_large((wdpa or {}).get(str(c.get("wdpa"))), cfg["admission"].get("r1_institutional", {}).get("iucn_min_area_km2", 100)):
            rules.append("R1")                                              # IUCN Ia, Ib or II of 100 km2 or more
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
                    a["whs"] = a.get("whs") or b.get("whs")
    return [p for p in places if p["qid"] not in drop]


COLOCATED_KM = 5.0
STUB_SITELINKS = 15                                                  # a World Heritage record this thin is a stub, not a destination
SAME_KIND_KM = 25.0


def _holds(p: dict) -> bool:
    """The place carries a whole World Heritage property: what is inside it is its asset."""
    return bool(p.get("whs")) and bool(PROPERTY_ID.match(str(p["whs"])))


def _ruins(p: dict) -> bool:
    return (p.get("_type") or {}).get("place_type") == "site" and (p.get("_type") or {}).get("kind_hint") == "ruins"


SERIAL_ID = re.compile(r"^(\d+)-")


def absorb(places: list[dict], overrides: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
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
        if m and m.group(1) in winner and p["qid"] not in gone and winner[m.group(1)]["qid"] != p["qid"]:
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
    for p in places:                                                        # 4b. a protected area and its mountain (Kilimanjaro)
        if p["qid"] in gone or p.get("whs") or (p.get("_type") or {}).get("place_type") != "area":
            continue
        for a in held:
            if (a.get("_type") or {}).get("place_type") == "area" and a["qid"] not in gone and a["iso3"] == p["iso3"] \
                    and a["sitelinks"] < p["sitelinks"] and haversine_km(a["lat"], a["lon"], p["lat"], p["lon"]) <= COLOCATED_KM:
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
        parent["whs"] = parent.get("whs") or child.get("whs")
        if q in keep_kinds:
            parent["classes"] = set(parent["classes"]) | set(child["classes"])      # a ruled merge keeps the loser's kinds (Meru on the park)
        parent.setdefault("absorbed", []).append(child.get("label_en") or q)
        ct, pt = child.get("_type") or {}, parent.get("_type") or {}
        log.append({"child": q, "child_name": child.get("label_en"), "parent": r, "parent_name": parent.get("label_en"), "reason": why,
                    "child_type": ct.get("place_type", ""), "parent_type": pt.get("place_type", ""),
                    "child_hint": ct.get("kind_hint", ""), "parent_hint": pt.get("kind_hint", "")})
    absorbed = {e["child"] for e in log}
    return [p for p in places if p["qid"] not in absorbed], log


def record(c: dict, place_id: str, types_row: dict | None, types: list[dict]) -> dict:
    qids = [c["qid"], *c.get("alt_qids", [])]
    ev = [{"asset_id": f"wd:{q}", "source": "wikidata", "url": f"https://www.wikidata.org/wiki/{q}",
           "retrieved": RETRIEVED, "source_key": f"qid:{q}"} for q in qids]
    if c.get("whs") and PROPERTY_ID.match(str(c["whs"])):
        ev.append({"asset_id": f"whs:{c['whs']}", "source": "unesco_whs", "url": f"https://whc.unesco.org/en/list/{c['whs']}",
                   "retrieved": RETRIEVED, "source_key": f"whs:{c['whs']}"})
    hints = kind_hints(sorted(c["classes"]), types)
    kinds = [{"kind": k, "rule": "class-hint", "evidence": [ev[0]["asset_id"]]} for k in hints]
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
    if not kinds:
        r["no_kind_reason"] = "kinds pending: the rule engine needs landcover, relief and WDPA facts (M2)"
    return r


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


def run(raw: Path, out: Path, top_share: float = S.TOP_SHARE) -> dict:
    cfg = json.loads((ROOT / "data" / "rules" / "tiers.json").read_text(encoding="utf-8"))
    types = load_types(ROOT / "data" / "rules" / "types.csv")
    with open(ROOT / "data" / "rules" / "country_overrides.csv", encoding="utf-8", newline="") as fh:
        overrides = {r["qid"]: r["iso3"] for r in csv.DictReader(fh)}
    cands = candidates(raw, overrides)
    items, profiles = S.load(raw)
    scores = S.scores(items, profiles)
    admitted = admit(cands, scores, types, cfg, top_share, W.load(raw.parent.parent / "wdpa" / "wdpa_reduced.csv"),
                     load_anchors(ROOT / "data" / "anchors" / "anchors.csv"))
    for c in admitted:
        c["_n"] = notability(c, cfg)
        c["name_en"] = short_name(c.get("label_en") or c.get("label_loc"), [])
    places = merge_duplicates(admitted, cfg["dedup"]["same_name_km"])
    for c in places:
        c["_n"] = notability(c, cfg)
        c["name_en"] = c.get("label_en") or c.get("label_loc")
    places, absorbed = absorb(places, load_overrides(ROOT / "data" / "anchors" / "merge_overrides.csv"))
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "absorbed.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["child", "child_name", "parent", "parent_name", "reason", "child_type", "parent_type", "child_hint", "parent_hint"], lineterminator="\n")
        w.writeheader()
        w.writerows(absorbed)
    assign_tiers(places, cfg)
    reg = Registry()
    rng = random.Random(20261007)                          # provisional ids: the registry is not committed (D21)
    recs = []
    for c in sorted(places, key=lambda c: c["qid"]):
        pid = mint_or_reuse(reg, [f"qid:{c['qid']}"], "first-pass", rng)
        recs.append(record(c, pid, c["_type"], types))
    notes = {"first_pass": True, "provisional_ids": True, "scope": "nine prototype countries",
             "missing": ["pageviews (N has no pageview term)", "WDPA categories (when data/raw/wdpa/wdpa_reduced.csv is absent) and Ramsar", "landcover and relief for kinds", "registry"],
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
