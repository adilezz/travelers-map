"""The attention signal, calibrated against bot-written Wikipedias (S1 finding of 6 October 2026).

Raw sitelink counts cannot separate a famous town from an ordinary one: every French commune has about
35 articles because bots wrote them in Cebuano, Swedish, Waray and others. The fix has two parts.

1. **Discrimination score D.** For a class with very many members (a "mass class": communes, comuni,
   municipalities, and any class with MASS_MIN or more members in a country) each Wikipedia gets the rate at
   which the class's members have it. An item's D is the sum over its Wikipedias of (1 - rate): an article in
   a wiki that nearly every commune has adds about 0, an article in a wiki few communes have adds about 1.
2. **Class-relative rank.** An item of a mass class is admitted by attention only if D puts it in the top
   TOP_SHARE of its class in its country; any other item uses the plain floors of document 1 section 5.

    python -m atlas.signal [--raw data/raw/wikidata/2026-10-05] [--report data/golden/s1_signal.md]
"""
from __future__ import annotations

import argparse
import bisect
import sys
from collections import Counter
from pathlib import Path

from atlas import golden as G

ROOT = Path(__file__).resolve().parents[2]
MASS_MIN = 1000      # members in one country that make a class "mass"
TOP_SHARE = 0.03     # share of a mass class admitted by attention (owner decision, 7 Oct 2026: a safety margin above Alberobello)
SISTER = {"commonswiki", "specieswiki", "metawiki", "mediawikiwiki", "wikidatawiki"}


def wiki_rates(profiles: list[list[str]]) -> dict[str, float]:
    """Share of the given items that have each wiki."""
    n = len(profiles) or 1
    c = Counter(w for ws in profiles for w in set(ws))
    return {w: k / n for w, k in c.items()}


def discrimination(wikis: list[str], rates: dict[str, float]) -> float:
    return sum(1.0 - rates.get(w, 0.0) for w in wikis if w not in SISTER)


def mass_classes(items: list[tuple[str, str, list[str]]], mass_min: int = MASS_MIN) -> dict[tuple[str, str], int]:
    """(country, class) -> members, for classes with at least `mass_min` in a country."""
    c = Counter((iso, k) for _q, iso, classes in items for k in set(classes))
    return {key: n for key, n in c.items() if n >= mass_min}


def assign_class(classes: list[str], iso: str, mass: dict[tuple[str, str], int]) -> str | None:
    """The biggest mass class the item belongs to in its country, if any."""
    best = max(((mass[(iso, k)], k) for k in set(classes) if (iso, k) in mass), default=None)
    return best[1] if best else None


def scores(items: list[tuple[str, str, list[str]]], profiles: dict[str, list[str]],
           mass_min: int = MASS_MIN) -> dict[str, dict]:
    """qid -> {iso, cls, D, pct}: D against the class's own baseline, pct = rank within (country, class)."""
    mass = mass_classes(items, mass_min)
    cls_of = {q: assign_class(classes, iso, mass) for q, iso, classes in items}
    iso_of = {q: iso for q, iso, _c in items}
    pooled = wiki_rates([profiles[q] for q in profiles if q in iso_of])
    rates: dict[str, dict[str, float]] = {}
    for k in {c for c in cls_of.values() if c}:
        rates[k] = wiki_rates([profiles[q] for q in profiles if cls_of.get(q) == k])
    out: dict[str, dict] = {}
    for q in iso_of:
        if q not in profiles:
            continue
        k = cls_of[q]
        out[q] = {"iso": iso_of[q], "cls": k, "D": discrimination(profiles[q], rates[k] if k else pooled)}
    groups: dict[tuple[str, str], list[float]] = {}
    for v in out.values():
        if v["cls"]:
            groups.setdefault((v["iso"], v["cls"]), []).append(v["D"])
    sorted_groups = {g: sorted(vs) for g, vs in groups.items()}
    for v in out.values():
        if v["cls"]:
            vs = sorted_groups[(v["iso"], v["cls"])]
            v["pct"] = 100.0 * (bisect.bisect_left(vs, v["D"]) + bisect.bisect_right(vs, v["D"])) / (2 * len(vs))     # mid-rank, so ties do not push a whole class under the line
    return out


def admitted_by_attention(v: dict, top_share: float = TOP_SHARE) -> bool | None:
    """True/False for mass-class items; None where the plain floors of document 1 apply."""
    if "pct" not in v:
        return None
    return v["pct"] >= 100.0 * (1.0 - top_share)


def load(raw: Path) -> tuple[list[tuple[str, str, list[str]]], dict[str, list[str]]]:
    import duckdb
    con = duckdb.connect()
    f = raw / "attention.parquet"
    items = [(q, iso, list(inst or [])) for q, iso, inst in con.execute(
        f"SELECT qid, iso3, any_value(instance_of) FROM read_parquet('{f.as_posix()}') GROUP BY qid, iso3").fetchall()]
    profiles = {q: list(w) for q, w in con.execute(
        f"SELECT qid, wikis FROM read_parquet('{(raw / 'profile.parquet').as_posix()}') WHERE wikis IS NOT NULL").fetchall()}
    return items, profiles


def report(raw: Path, golden_path: Path) -> str:
    items, profiles = load(raw)
    sc = scores(items, profiles)
    mass = mass_classes(items)
    gold = [r for r in G.load(golden_path) if r.row_kind == "positive"]
    lines = [f"# Attention signal calibration ({raw.name})", "",
             f"Mass classes (at least {MASS_MIN} members in a country): {len(mass)}; "
             f"admitted by attention if in the top {TOP_SHARE:.0%} of the class in the country.", "",
             "| Country | Class | Members | Admitted |", "|---|---|---|---|"]
    for (iso, k), n in sorted(mass.items()):
        adm = sum(1 for v in sc.values() if v["iso"] == iso and v["cls"] == k and admitted_by_attention(v))
        lines.append(f"| {iso} | {k} | {n} | {adm} |")
    inside = [(r, sc[r.qid]) for r in gold if r.qid in sc and sc[r.qid].get("pct") is not None]
    lines += ["", f"## Golden places that belong to a mass class ({len(inside)})", "",
              "| Golden | Place | Class | Percentile | Admitted |", "|---|---|---|---|---|"]
    for r, v in sorted(inside, key=lambda t: t[1]["pct"]):
        lines.append(f"| {r.golden_id} | {r.name} | {v['cls']} | {v['pct']:.1f} | {'yes' if admitted_by_attention(v) else 'NO'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1])
    ap.add_argument("--golden", type=Path, default=ROOT / "data" / "golden" / "golden.csv")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args(argv)
    text = report(a.raw, a.golden)
    print(text)
    if a.report:
        a.report.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
