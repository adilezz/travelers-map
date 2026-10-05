"""S1 acceptance check: how many golden places did the Wikidata extraction find?

    python -m atlas.recall [--raw data/raw/wikidata/2026-10-05] [--report data/golden/s1_recall.md]

Golden QIDs are resolved from the golden file; this tool only asks whether each QID appears
in the extracted families. It never adds a QID to the extraction: injecting the answers would
make the later landmark gate circular. A miss is a finding about the queries, not a data fix.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from atlas import golden as G

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = ("class", "popall", "pop", "attention", "locatedin", "institutional", "node")


def load_index(raw: Path) -> dict[str, dict]:
    """qid -> {families, sitelinks, instance_of} over every extracted Parquet file."""
    import duckdb
    con = duckdb.connect()
    index: dict[str, dict] = {}
    for f in sorted(raw.glob("*.parquet")):
        if f.stem not in FAMILIES:
            continue
        cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{f.as_posix()}')").fetchall()}
        inst = "instance_of" if "instance_of" in cols else "NULL"
        sl = "sitelinks" if "sitelinks" in cols else "NULL"
        for qid, sitelinks, insts in con.execute(
                f"SELECT qid, {sl}, {inst} FROM read_parquet('{f.as_posix()}')").fetchall():
            e = index.setdefault(qid, {"families": set(), "sitelinks": None, "instance_of": set()})
            e["families"].add(f.stem)
            if sitelinks is not None:
                e["sitelinks"] = max(e["sitelinks"] or 0, sitelinks)
            e["instance_of"] |= set(insts or [])
    return index


def recall(raw: Path, golden_path: Path) -> dict:
    rows = [r for r in G.load(golden_path) if r.row_kind == "positive"]
    index = load_index(raw)
    found = [r for r in rows if r.qid in index]
    missed = [r for r in rows if r.qid not in index]
    by_iso: dict[str, list[int]] = {}
    for r in rows:
        t = by_iso.setdefault(r.iso3, [0, 0])
        t[1] += 1
        t[0] += r.qid in index
    return {"n": len(rows), "found": len(found), "missed": missed, "by_iso": by_iso,
            "families": Counter(f for r in found for f in index[r.qid]["families"]), "rows": rows,
            "index": index}


def report(res: dict, raw: Path) -> str:
    pct = 100 * res["found"] / res["n"] if res["n"] else 0.0
    out = [f"# S1 recall against the golden set ({raw.name})", "",
           f"{res['found']} of {res['n']} golden QIDs appear in the extraction ({pct:.0f} %).", "",
           "| Country | Found | Golden |", "|---|---|---|"]
    out += [f"| {iso} | {a} | {b} |" for iso, (a, b) in sorted(res["by_iso"].items())]
    out += ["", "## Missed", "", "| Golden | Place | QID | Country | Note |", "|---|---|---|---|---|"]
    for r in res["missed"]:
        out.append(f"| {r.golden_id} | {r.name} | {r.qid} | {r.iso3} | {r.raw.get('evidence', '')[:60]} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1])
    ap.add_argument("--golden", type=Path, default=ROOT / "data" / "golden" / "golden.csv")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args(argv)
    res = recall(a.raw, a.golden)
    text = report(res, a.raw)
    print(text)
    if a.report:
        a.report.write_text(text, encoding="utf-8")
    return 0 if res["found"] / max(1, res["n"]) >= 0.95 else 1


if __name__ == "__main__":
    sys.exit(main())
