"""Tier calibration against the golden minimum and maximum tiers (document 3). Never the holdout.

    python -m atlas.tiercal [--report data/golden/tier_calibration.md]

Reads the golden set and the first bundle only to learn which place each golden row resolves to, then
re-assigns tiers for each candidate parameter setting and counts the violations of `min_tier`, `max_tier`
and the `not_above` rows. Nothing is written to the bundle or to tiers.json: a change is the owner's.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
from pathlib import Path

from atlas import admit as A
from atlas import golden as G
from atlas import matching as M
from atlas import signal as S

ROOT = Path(__file__).resolve().parents[2]
RANK = {"Local": 0, "Notable": 1, "Major": 2, "Icon": 3}


def resolve(bundle: Path, golden_path: Path) -> tuple[list[G.Row], dict[str, str]]:
    places = [p for f in sorted((bundle / "places").glob("*.json")) for p in json.loads(f.read_text(encoding="utf-8"))["places"]]
    rows = G.load(golden_path)
    return rows, {g: p["qid"] for g, p in M.assign(rows, places).matched.items()}


def violations(rows: list[G.Row], matched: dict[str, str], tier_of: dict[str, str]) -> list[str]:
    bad = []
    by_id = {r.golden_id: r for r in rows}
    for r in rows:
        if r.row_kind == "positive" and r.golden_id in matched:
            t = tier_of.get(matched[r.golden_id], "Local")
            if RANK[t] < RANK[r.min_tier]:
                bad.append(f"{r.golden_id} {r.name}: {t}, needs {r.min_tier}+")
            if r.max_tier and RANK[t] > RANK[r.max_tier]:
                bad.append(f"{r.golden_id} {r.name}: {t}, max {r.max_tier}")
    for r in rows:
        if r.row_kind == "negative" and r.relation == "not_above":
            for t in r.targets:
                if t not in matched:
                    continue
                for q in NEG.get(r.golden_id, []):
                    if RANK[tier_of.get(q, "Local")] >= RANK[tier_of[matched[t]]]:
                        bad.append(f"{r.golden_id} {r.name} not below {by_id[t].name}")
    return bad


NEG: dict[str, list[str]] = {}          # negative golden id -> qids of the places its name matches


def index_negatives(rows: list[G.Row], places: list[dict]) -> None:
    for r in rows:
        if r.row_kind == "negative" and r.relation == "not_above":
            NEG[r.golden_id] = [q["qid"] for q in M.by_name_in_country(r, [
                {"iso3": q["iso3"], "name_en": q["name_en"], "aliases": q.get("aliases", []), "qid": q["qid"], "status": "active",
                 "keys": [f"qid:{q['qid']}"], "lat": q["lat"], "lon": q["lon"], "type": "site"} for q in places])]


def shares(places: list[dict]) -> tuple[float, float, float]:
    n = len(places)
    c = {t: sum(1 for p in places if p.get("tier") == t) for t in RANK}
    return tuple(100.0 * c[t] / n for t in ("Icon", "Major", "Notable"))


def tiers_for(places: list[dict], cfg: dict) -> dict[str, str]:
    for p in places:
        p.pop("tier", None)
    A.assign_tiers(places, cfg)
    return {p["qid"]: p["tier"] for p in places}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1])
    ap.add_argument("--bundle", type=Path, default=ROOT / "build" / "first")
    ap.add_argument("--golden", type=Path, default=ROOT / "data" / "golden" / "golden.csv")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args(argv)
    rows, matched = resolve(a.bundle, a.golden)
    prep = A.prepare(a.raw, S.TOP_SHARE)
    places, base = prep["places"], prep["cfg"]
    index_negatives(rows, places)
    out = [f"# Tier calibration against the golden set\n\n{len(matched)} golden rows resolve to a place; the gate needs zero violations "
           f"of `min_tier`, `max_tier` and `not_above`. Parameters are searched on the golden set only, never on H1.\n"]
    b = violations(rows, matched, tiers_for(places, base))
    out.append(f"`tiers.json` when run: **{len(b)} violations**; tier shares {shares(places)}.\n")
    out += [f"- {x}" for x in b]
    results = []
    for prot, pvw, icon_g, major_g, icon_top, major_next, notable_g in itertools.product(
            [0.0, 0.2, 0.4], [0.5, 1.0], [99, 99.5], [90, 95], [3, 5, 8, 12], [10, 20, 30], [60, 75]):
        cfg = copy.deepcopy(base)
        cfg["notability"]["recognition"]["protected_designation"] = prot
        cfg["notability"]["pageview_weight"] = pvw
        cfg["tiers"]["icon"].update(global_percentile=icon_g, country_top=icon_top)
        cfg["tiers"]["major"].update(global_percentile=major_g, country_next=major_next)
        cfg["tiers"]["notable"]["global_percentile"] = notable_g
        for p in places:
            p["_n"] = A.notability(p, cfg)
        tiers = tiers_for(places, cfg)
        results.append((len(violations(rows, matched, tiers)), shares(places), prot, pvw, icon_g, major_g, icon_top, major_next, notable_g))
    results.sort(key=lambda r: (r[0], r[1][0] + r[1][1]))
    out.append("\n## Lowest violations (ties by the smallest Icon plus Major share)\n\n"
               "| violations | Icon % | Major % | Notable % | protected R | pageview weight | icon p | major p | icon top | major next | notable p |\n"
               "|---|---|---|---|---|---|---|---|---|---|---|")
    out += [f"| {r[0]} | {r[1][0]:.1f} | {r[1][1]:.1f} | {r[1][2]:.1f} | {' | '.join(str(x) for x in r[2:])} |" for r in results[:15]]
    best = {}
    for r in results:
        best.setdefault(r[0], r)
    out.append("\n## Violations against the cost in Icon and Major places (cheapest setting per violation count)\n\n"
               "| violations | Icon % | Major % | protected R | pageview weight | icon top | major next |\n|---|---|---|---|---|---|---|")
    out += [f"| {k} | {v[1][0]:.1f} | {v[1][1]:.1f} | {v[2]} | {v[3]} | {v[6]} | {v[7]} |" for k, v in sorted(best.items())[:14]]
    text = "\n".join(out) + "\n"
    print(text)
    if a.report:
        a.report.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
