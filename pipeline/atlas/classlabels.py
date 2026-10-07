"""Labels and parents for the classes the candidates belong to (owner runs it; about a dozen requests).

    python -m atlas.classlabels [--raw data/raw/wikidata/2026-10-05] [--top 600] [--out data/rules/class_labels.csv]

The admission pass has to decide what kind of place each candidate is from its Wikidata classes
(`instance of`), and the class table covers only 24 of them. This tool lists the most frequent classes
among the candidates with their English label, description and parent classes (`subclass of`) so the
typing table (`data/rules/types.csv`) can be written from facts and not from memory.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from atlas.wikidata import API, http_get

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = ("class_qid", "count", "label_en", "description_en", "subclass_of")


def frequent_classes(raw: Path, top: int = 600, min_sitelinks: int = 15) -> list[tuple[str, int]]:
    """Classes of the S2 detail rows, most frequent first (one count per item)."""
    import duckdb
    con = duckdb.connect()
    f = raw / "attention.parquet"
    rows = con.execute(
        f"SELECT any_value(instance_of) FROM read_parquet('{f.as_posix()}') WHERE sitelinks >= {min_sitelinks} GROUP BY qid"
    ).fetchall()
    c = Counter(k for (inst,) in rows for k in set(inst or []))
    return c.most_common(top)


def fetch(qids: list[str], get: Callable[[str, dict], dict] = http_get) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(qids), 50):
        d = get(API, {"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]), "format": "json",
                      "props": "labels|descriptions|claims", "languages": "en", "redirects": "yes"})
        for qid, e in d.get("entities", {}).items():
            if "missing" in e:
                continue
            parents = [c["mainsnak"]["datavalue"]["value"]["id"] for c in e.get("claims", {}).get("P279", [])
                       if c.get("mainsnak", {}).get("datavalue")]
            out[qid] = {"label_en": e.get("labels", {}).get("en", {}).get("value", ""),
                        "description_en": e.get("descriptions", {}).get("en", {}).get("value", ""),
                        "subclass_of": parents}
    return out


def write(rows: list[tuple[str, int]], info: dict[str, dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLUMNS)
        for qid, n in rows:
            i = info.get(qid, {})
            w.writerow([qid, n, i.get("label_en", ""), i.get("description_en", ""), "|".join(i.get("subclass_of", []))])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1])
    ap.add_argument("--top", type=int, default=600)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "rules" / "class_labels.csv")
    a = ap.parse_args(argv)
    rows = frequent_classes(a.raw, a.top)
    info = fetch([q for q, _ in rows])
    write(rows, info, a.out)
    print(f"{len(rows)} classes, {sum(1 for q, _ in rows if q in info)} labelled -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
