"""Review lists for the owner: what absorption did and what it left alone (D25, document 1 section 5.2).

    python -m atlas.review [--bundle build/first] [--out data/review]
writes `absorption_summary.md` and `same_kind_neighbours.csv`. Nothing here changes the bundle."""
import argparse
import csv
import glob
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

from atlas.geo import haversine_km

ROOT = Path(__file__).resolve().parents[2]
NEIGHBOUR_KM = 25.0
TIERS = {"Icon", "Major", "Notable"}
MIN_SITELINKS = 80            # both places; below it the list holds thousands of pairs of ordinary towns


def load_places(bundle: Path) -> list[dict]:
    out: list[dict] = []
    for f in sorted(glob.glob(str(bundle / "places" / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        out += d if isinstance(d, list) else d.get("places", [])
    return out


def kinds(p: dict) -> set[str]:
    return {k["kind"] for k in p.get("kinds", [])}


def neighbours(places: list[dict], km: float = NEIGHBOUR_KM) -> list[tuple[dict, dict, float]]:
    """Pairs of kept places of one type and a shared kind (or both without a kind) within `km`, both Notable or above and both with at least MIN_SITELINKS."""
    by_iso: dict[str, list[dict]] = defaultdict(list)
    for p in places:
        if p["tier"] in TIERS and p["sitelinks"] >= MIN_SITELINKS:
            by_iso[p["iso3"]].append(p)
    out = []
    for ps in by_iso.values():
        for a, b in itertools.combinations(ps, 2):
            if a["type"] != b["type"] or abs(a["lat"] - b["lat"]) > km / 100.0:
                continue
            ka, kb = kinds(a), kinds(b)
            if (ka and kb and not ka & kb) or bool(ka) != bool(kb):
                continue
            d = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
            if d <= km:
                out.append((a, b, d))
    return sorted(out, key=lambda t: (-min(t[0]["sitelinks"], t[1]["sitelinks"]), t[2]))


def absorption_summary(rows: list[dict]) -> str:
    def rule(r: dict) -> str:
        return " ".join(r["reason"].split(" ")[:2])
    nested = lambda r: r["child_type"] == "site"                                   # noqa: E731  a monument or site becomes an asset
    differ = [r for r in rows if r["child_hint"] and r["parent_hint"] and r["child_hint"] != r["parent_hint"]]
    by = Counter(rule(r) for r in rows)
    lines = ["# Absorption summary", "", f"{len(rows)} places absorbed.", "",
             "| Rule | Absorbed | Child is a site (nested asset) | Different kind hint |", "|---|---|---|---|"]
    for k, n in by.most_common():
        lines.append(f"| {k} | {n} | {sum(1 for r in rows if rule(r) == k and nested(r))} | "
                     f"{sum(1 for r in differ if rule(r) == k)} |")
    lines += ["", f"Pairs whose kind hints differ (both known): {len(differ)}.", ""]
    lines += [f"- {r['child_name']} ({r['child_hint']}) into {r['parent_name']} ({r['parent_hint']}): {r['reason']}" for r in differ]
    return "\n".join(lines) + "\n"


def tier_diff(before: list[dict], after: list[dict], golden_qids: set[str]) -> str:
    """Before and after a rule change: tier shares, each country's Icons, and the non-golden places whose tier moved."""
    b = {p["qid"]: p for p in before}
    a = {p["qid"]: p for p in after}
    share = lambda ps: ", ".join(f"{t} {100 * sum(1 for p in ps if p['tier'] == t) / len(ps):.1f} %" for t in ("Icon", "Major", "Notable", "Local"))  # noqa: E731
    lines = ["# Tier changes (D38)", "", f"Before: {len(before)} places, {share(before)}.", f"After: {len(after)} places, {share(after)}.", "",
             "## Icons by country", "", "| Country | Before | After |", "|---|---|---|"]
    for iso in sorted({p["iso3"] for p in after}):
        before_icons = ", ".join(sorted(p["name_en"] for p in b.values() if p["iso3"] == iso and p["tier"] == "Icon"))
        after_icons = ", ".join(sorted(p["name_en"] for p in a.values() if p["iso3"] == iso and p["tier"] == "Icon"))
        lines.append(f"| {iso} | {before_icons} | {after_icons} |")
    rank = {"Local": 0, "Notable": 1, "Major": 2, "Icon": 3}
    moved = [(q, b[q], a[q]) for q in a if q in b and q not in golden_qids and a[q]["tier"] != b[q]["tier"]]
    gone = [b[q] for q in b if q not in a and q not in golden_qids and rank[b[q]["tier"]] >= 2]
    lines += ["", f"## Non-golden places whose tier changed: {len(moved)} ({sum(1 for _, x, y in moved if rank[y['tier']] > rank[x['tier']])} up, "
              f"{sum(1 for _, x, y in moved if rank[y['tier']] < rank[x['tier']])} down)", "",
              "Largest moves among the top of each country (Icon or Major before or after):", "", "| Place | Country | Before | After |", "|---|---|---|---|"]
    big = sorted((m for m in moved if max(rank[m[1]["tier"]], rank[m[2]["tier"]]) >= 2), key=lambda m: -abs(rank[m[2]["tier"]] - rank[m[1]["tier"]]))
    lines += [f"| {y['name_en']} | {y['iso3']} | {x['tier']} | {y['tier']} |" for _, x, y in big[:60]]
    lines += ["", f"## Major or Icon before and no longer a place (context, absorbed or merged): {len(gone)}", ""]
    lines += [f"- {p['name_en']} ({p['iso3']}, {p['tier']})" for p in gone[:80]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle", type=Path, default=ROOT / "build" / "first")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "review")
    ap.add_argument("--before", type=Path, help="an earlier bundle: also write tier_changes.md")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    with open(a.bundle / "absorbed.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    (a.out / "absorption_summary.md").write_text(absorption_summary(rows), encoding="utf-8")
    pairs = neighbours(load_places(a.bundle))
    with open(a.out / "same_kind_neighbours.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["iso3", "type", "place_a", "qid_a", "tier_a", "place_b", "qid_b", "tier_b", "km", "verdict"])
        for x, y, d in pairs:
            w.writerow([x["iso3"], x["type"], x["name_en"], x["qid"], x["tier"], y["name_en"], y["qid"], y["tier"], f"{d:.1f}", ""])
    if a.before:
        with open(ROOT / "data" / "golden" / "golden.csv", encoding="utf-8", newline="") as fh:
            gq = {r["qid"] for r in csv.DictReader(fh) if r.get("qid")}
        (a.out / "tier_changes.md").write_text(tier_diff(load_places(a.before), load_places(a.bundle), gq), encoding="utf-8")
    print(f"{len(rows)} absorbed, {len(pairs)} same-kind neighbour pairs for review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
