"""S2: Wikidata details for the candidates that survive S1 (document 2 sections 2.3 and 7).

    python -m atlas.details select --raw data/raw/wikidata/2026-10-05      # which QIDs, and why
    python -m atlas.details run    --raw data/raw/wikidata/2026-10-05      # fetch, resumable
    python -m atlas.details parquet --raw data/raw/wikidata/2026-10-05
    python -m atlas.details pin     --raw data/raw/wikidata/2026-10-05

S1 says WHICH items exist near the nine countries; S2 asks what each one is: its labels and
aliases in the languages that matter, its description, what it is part of or located in, whether
it is or was a capital, its dates, its heritage designations, its official site, its Wikipedia
titles (the key to pageviews), and whether Wikidata has redirected the QID since the extraction.
Nothing is decided here; the rows are what Wikidata said, with the run date.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from atlas.extract import COUNTRIES
from atlas.wikidata import API, http_get

ROOT = Path(__file__).resolve().parents[2]
BATCH = 50
MIN_SITELINKS = 15      # below this no rule can admit an item without an institutional id, a population or an anchor
MIN_POPULATION = 100_000
LOCAL_LANGS = sorted({c["lang"] for c in COUNTRIES.values()})
PROPS = {"P31": "instance_of", "P131": "located_in", "P361": "part_of", "P1435": "heritage",
         "P1376": "capital_of", "P856": "official_url", "P571": "inception", "P576": "dissolved"}


def select(raw: Path, golden_path: Path | None = None) -> dict[str, set[str]]:
    """QID -> reasons it is fetched. Reasons: sitelinks, population, whs, wdpa, node, golden."""
    import duckdb
    con = duckdb.connect()
    chosen: dict[str, set[str]] = {}

    def add(qid: str, why: str) -> None:
        chosen.setdefault(qid, set()).add(why)

    for f in sorted(raw.glob("*.parquet")):
        if f.stem == "details":
            continue
        cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{f.as_posix()}')").fetchall()}
        q = f"SELECT qid, {'sitelinks' if 'sitelinks' in cols else 'NULL'}, {'population' if 'population' in cols else 'NULL'}, " \
            f"{'whs' if 'whs' in cols else 'NULL'}, {'wdpa' if 'wdpa' in cols else 'NULL'} FROM read_parquet('{f.as_posix()}')"
        for qid, sl, pop, whs, wdpa in con.execute(q).fetchall():
            if sl is not None and sl >= MIN_SITELINKS:
                add(qid, "sitelinks")
            if pop is not None and pop >= MIN_POPULATION:
                add(qid, "population")
            if whs:
                add(qid, "whs")
            if wdpa:
                add(qid, "wdpa")
            if f.stem == "node":
                add(qid, "node")
    if golden_path and golden_path.is_file():
        with open(golden_path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("qid"):
                    add(r["qid"], "golden")
    return chosen


def ids(claims: list[dict]) -> list[str]:
    out = []
    for c in claims:
        if c.get("rank") == "deprecated":
            continue
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            out.append(v["id"])
    return out


def year(claims: list[dict]) -> int | None:
    for c in claims:
        t = c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("time")
        if t:
            try:
                return int(t[:t.index("-", 1)])
            except ValueError:
                continue
    return None


def capital_of(claims: list[dict]) -> list[dict]:
    """Each P1376 claim with whether it has ended (a former capital carries an end time, P582)."""
    out = []
    for c in claims:
        if c.get("rank") == "deprecated":
            continue
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            out.append({"qid": v["id"], "ended": bool(c.get("qualifiers", {}).get("P582"))})
    return out


def parse_entity(requested: str, e: dict, langs: list[str]) -> dict:
    claims = e.get("claims", {})
    row: dict = {"qid": requested}
    if e.get("id") and e["id"] != requested:
        row["redirected_to"] = e["id"]                       # merged since the extraction
    labels, aliases, desc = e.get("labels", {}), e.get("aliases", {}), e.get("descriptions", {})
    for lang in langs:
        key = "en" if lang == "en" else "loc"
        if lang in labels:
            row[f"label_{key}"] = labels[lang]["value"]
        if lang in aliases:
            row[f"aliases_{key}"] = [a["value"] for a in aliases[lang]]
    if "en" in desc:
        row["description_en"] = desc["en"]["value"]
    row["instance_of"] = ids(claims.get("P31", []))
    row["located_in"] = ids(claims.get("P131", []))
    row["part_of"] = ids(claims.get("P361", []))
    row["heritage"] = ids(claims.get("P1435", []))
    row["capital_of"] = capital_of(claims.get("P1376", []))
    for prop, name in (("P571", "inception"), ("P576", "dissolved")):
        y = year(claims.get(prop, []))
        if y is not None:
            row[name] = y
    for c in claims.get("P856", []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, str):
            row["official_url"] = v
            break
    sl = e.get("sitelinks", {})
    if "enwiki" in sl:
        row["wikipedia_en"] = sl["enwiki"]["title"]
    return row


def fetch_batch(qids: list[str], langs: list[str], get: Callable[[str, dict], dict]) -> list[dict]:
    sitefilter = "|".join(f"{lang}wiki" for lang in langs)
    d = get(API, {"action": "wbgetentities", "ids": "|".join(qids), "format": "json", "redirects": "yes",
                  "props": "labels|aliases|descriptions|claims|sitelinks", "languages": "|".join(langs),
                  "sitefilter": sitefilter})
    entities = d.get("entities", {})
    by_target = {e.get("id"): e for e in entities.values() if isinstance(e, dict)}
    rows = []
    for qid in qids:
        e = entities.get(qid) or by_target.get(qid)
        if e is None or "missing" in e:
            rows.append({"qid": qid, "missing": True})
            continue
        rows.append(parse_entity(qid, e, langs))
    return rows


def run(chosen: dict[str, set[str]], out: Path, get: Callable[[str, dict], dict] = http_get,
        delay: float = 0.3, log: Callable[[str], None] = print) -> dict:
    """Fetch every chosen QID once; resumable (QIDs already in the file are skipped)."""
    import time
    path = out / "details.jsonl"
    done: set[str] = set()
    if path.is_file():
        with open(path, encoding="utf-8") as fh:
            done = {json.loads(line)["qid"] for line in fh if line.strip() and not line.startswith('{"_meta"')}
    todo = [q for q in sorted(chosen) if q not in done]
    langs = ["en", *LOCAL_LANGS]
    failed: list[str] = []
    with open(path, "a", encoding="utf-8") as fh:
        if not done:
            fh.write(json.dumps({"_meta": {"run_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                                           "endpoint": API, "languages": langs, "batch": BATCH}}) + "\n")
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            try:
                rows = fetch_batch(batch, langs, get)
            except Exception as e:                                # one bad batch must not stop the run
                failed += batch
                log(f"batch {i // BATCH + 1}: failed ({type(e).__name__}: {str(e)[:80]})")
                continue
            for r in rows:
                r["why"] = sorted(chosen[r["qid"]])
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
            if (i // BATCH) % 20 == 0:
                log(f"{min(i + BATCH, len(todo))}/{len(todo)}")
            time.sleep(delay)
    return {"selected": len(chosen), "already": len(done), "fetched": len(todo) - len(failed), "failed": failed}


def to_parquet(out: Path) -> int:
    import duckdb
    src = out / "details.jsonl"
    rows = out / "details.rows.jsonl"
    with open(src, encoding="utf-8") as fh, open(rows, "w", encoding="utf-8") as w:
        for line in fh:
            if line.strip() and not line.startswith('{"_meta"'):
                w.write(line)
    dest = out / "details.parquet"
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM read_json_auto('{rows.as_posix()}', union_by_name=true, sample_size=-1)) "
                f"TO '{dest.as_posix()}' (FORMAT PARQUET)")
    n = con.execute(f"SELECT count(*) FROM read_parquet('{dest.as_posix()}')").fetchone()[0]
    rows.unlink()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["select", "run", "parquet", "pin"])
    ap.add_argument("--raw", type=Path, default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1])
    ap.add_argument("--golden", type=Path, default=ROOT / "data" / "golden" / "golden.csv")
    ap.add_argument("--delay", type=float, default=0.3)
    a = ap.parse_args(argv)
    if a.cmd == "select":
        chosen = select(a.raw, a.golden)
        why: dict[str, int] = {}
        for rs in chosen.values():
            for r in rs:
                why[r] = why.get(r, 0) + 1
        print(f"{len(chosen)} QIDs to fetch, about {-(-len(chosen) // BATCH)} requests; by reason {why}")
        return 0
    if a.cmd == "run":
        res = run(select(a.raw, a.golden), a.raw, delay=a.delay)
        print(res["selected"], "selected,", res["already"], "already done,", res["fetched"], "fetched,", len(res["failed"]), "failed")
        return 1 if res["failed"] else 0
    if a.cmd == "parquet":
        print(to_parquet(a.raw), "rows")
        return 0
    from atlas import snapshot
    snapshot.pin("wikidata_sparql", a.raw / "details.parquet", ROOT / "data" / "raw", a.raw.name)
    print("pinned details.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
