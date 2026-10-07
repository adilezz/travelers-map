"""Why does a golden place not appear in the first bundle? One line per miss, grouped by cause.

    python -m atlas.diagnose [--raw data/raw/wikidata/2026-10-05] [--bundle build/first] [--report data/golden/first_pass.md]

Causes: `merged` (it is a key of a surviving place), `no candidate` (not in the extraction), `no place-like class`
(its classes are not in data/rules/types.csv), `below the floors` (the rules did not admit it, with the numbers).
A miss is a finding about a rule, a table or a source, never a reason to edit the golden row.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from atlas import admit as A
from atlas import golden as G
from atlas import signal as S

ROOT = Path(__file__).resolve().parents[2]


def diagnose(raw: Path, bundle: Path, golden_path: Path) -> list[tuple[str, str, str, str]]:
    cfg = json.loads((ROOT / "data" / "rules" / "tiers.json").read_text(encoding="utf-8"))
    types = A.load_types(ROOT / "data" / "rules" / "types.csv")
    with open(ROOT / "data" / "rules" / "country_overrides.csv", encoding="utf-8", newline="") as fh:
        overrides = {r["qid"]: r["iso3"] for r in csv.DictReader(fh)}
    cands = A.candidates(raw, overrides)
    items, profiles = S.load(raw)
    scores = S.scores(items, profiles)
    A.admit(cands, scores, types, cfg)
    keys: set[str] = set()
    for f in (bundle / "places").glob("*.json"):
        for p in json.loads(f.read_text(encoding="utf-8"))["places"]:
            keys |= set(p.get("keys", [])) | {f"qid:{p.get('qid')}"}
    out = []
    for r in G.load(golden_path):
        if r.row_kind != "positive" or f"qid:{r.qid}" in keys:
            continue
        c = cands.get(r.qid)
        if c is None:
            out.append((r.golden_id, r.name, "no candidate", "not in the extraction"))
            continue
        t = A.classify(sorted(c["classes"]), types)
        sc = scores.get(r.qid)
        if t is None:
            out.append((r.golden_id, r.name, "no place-like class", f"classes {sorted(c['classes'])[:4]}"))
        else:
            out.append((r.golden_id, r.name, "below the floors",
                        f"sitelinks {c['sitelinks']}, D {None if not sc else round(sc['D'], 1)}, heritage {bool(c['heritage'])}, wdpa {bool(c.get('wdpa'))}"))
    return out


def report(rows: list[tuple[str, str, str, str]]) -> str:
    n = Counter(r[2] for r in rows)
    lines = ["# First pass: golden places not in the bundle", "",
             "Causes: " + ", ".join(f"{k} {v}" for k, v in sorted(n.items())), "",
             "| Golden | Place | Cause | Detail |", "|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1])
    ap.add_argument("--bundle", type=Path, default=ROOT / "build" / "first")
    ap.add_argument("--golden", type=Path, default=ROOT / "data" / "golden" / "golden.csv")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args(argv)
    text = report(diagnose(a.raw, a.bundle, a.golden))
    print(text)
    if a.report:
        a.report.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
