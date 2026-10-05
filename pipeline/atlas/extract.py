"""M1 extraction: the Wikidata prototype subset for the nine countries (document 2 section 2.4).

    python -m atlas.extract plan                       # what would be asked, nothing sent
    python -m atlas.extract run   --out data/raw/wikidata/2026-10-05 [--countries ITA FRA]
    python -m atlas.extract check --out data/raw/wikidata/2026-10-05
    python -m atlas.extract pin   --out data/raw/wikidata/2026-10-05
    python -m atlas.extract parquet --out data/raw/wikidata/2026-10-05

Run it where Wikidata can be reached (the owner's laptop, or the Claude environment once
query.wikidata.org is in its allowed hosts). Every query is small and paged; each result is
written to its own JSONL file whose first line records the query text, run time and row
count, so a run is resumable and auditable. Nothing is accepted into the database here:
this stage only keeps what Wikidata said, and the pipeline decides later (rules R1-R6).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from atlas.wikidata import SPARQL, USER_AGENT, qid_of

ROOT = Path(__file__).resolve().parents[2]
PAGE = 5000

# Country QIDs are checked against their English labels in `preflight` before any query runs.
COUNTRIES: dict[str, dict] = {
    "EGY": {"name": "Egypt", "qids": ["Q79"], "lang": "ar"},
    "ESP": {"name": "Spain", "qids": ["Q29"], "lang": "es"},
    "FRA": {"name": "France", "qids": ["Q142"], "lang": "fr"},
    "ITA": {"name": "Italy", "qids": ["Q38"], "lang": "it"},
    "JOR": {"name": "Jordan", "qids": ["Q810"], "lang": "ar"},
    # Western Sahara dissolves into Morocco and carries the disputed marker (document 4 section 7).
    "MAR": {"name": "Morocco", "qids": ["Q1028", "Q6250"], "lang": "ar", "disputed": {"Q6250": "ESH"}},
    "PER": {"name": "Peru", "qids": ["Q419"], "lang": "es"},
    "TUR": {"name": "Turkey", "qids": ["Q43"], "lang": "tr"},
    "TZA": {"name": "Tanzania", "qids": ["Q924"], "lang": "sw"},
}
# Sitelink bands keep each query small; below the lowest band no rule can admit an item
# (R2 needs 40, R4 needs 15) except through an institutional id, a population or an anchor.
BANDS: list[tuple[int, int | None]] = [(40, None), (15, 39), (8, 14)]

CLASS_QUERY = """\
SELECT ?item ?coord ?sl ?pop ?country ?label_en ?label_loc WHERE {{
  VALUES ?country {{ {countries} }}
  ?item wdt:P17 ?country ; wdt:P31/wdt:P279* wd:{cls} ; wdt:P625 ?coord ; wikibase:sitelinks ?sl .
  FILTER(?sl >= {lo}{hi})
  OPTIONAL {{ ?item wdt:P1082 ?pop }}
  OPTIONAL {{ ?item rdfs:label ?label_en FILTER(lang(?label_en) = "en") }}
  OPTIONAL {{ ?item rdfs:label ?label_loc FILTER(lang(?label_loc) = "{lang}") }}
}} ORDER BY ?item LIMIT {limit} OFFSET {offset}
"""
POP_QUERY = """\
SELECT ?item ?coord ?sl ?pop ?country ?label_en ?label_loc WHERE {{
  VALUES ?country {{ {countries} }}
  ?item wdt:P17 ?country ; wdt:P625 ?coord ; wdt:P1082 ?pop ; wikibase:sitelinks ?sl .
  FILTER(?pop >= 100000)
  OPTIONAL {{ ?item rdfs:label ?label_en FILTER(lang(?label_en) = "en") }}
  OPTIONAL {{ ?item rdfs:label ?label_loc FILTER(lang(?label_loc) = "{lang}") }}
}} ORDER BY ?item LIMIT {limit} OFFSET {offset}
"""
# R2 admits on attention alone, whatever the class: municipalities, regions, valleys and oases are not all
# in the class table, so this family asks for every item with 40 or more sitelinks and keeps its classes.
ATTENTION_QUERY = """\
SELECT ?item ?coord ?sl ?country ?label_en ?label_loc
       (GROUP_CONCAT(DISTINCT STRAFTER(STR(?inst), "/entity/"); separator = "|") AS ?insts) WHERE {{
  VALUES ?country {{ {countries} }}
  ?item wdt:P17 ?country ; wdt:P625 ?coord ; wikibase:sitelinks ?sl .
  FILTER(?sl >= {lo}{hi})
  OPTIONAL {{ ?item wdt:P31 ?inst }}
  OPTIONAL {{ ?item rdfs:label ?label_en FILTER(lang(?label_en) = "en") }}
  OPTIONAL {{ ?item rdfs:label ?label_loc FILTER(lang(?label_loc) = "{lang}") }}
}} GROUP BY ?item ?coord ?sl ?country ?label_en ?label_loc ORDER BY ?item LIMIT {limit} OFFSET {offset}
"""
ATTENTION_BANDS: list[tuple[int, int | None]] = [(100, None), (60, 99), (40, 59)]
# Many sites carry no country of their own and get it only through "located in" (Kerak Castle sits in
# Al-Karak, the Sacred Valley in the Cusco Region). The first run missed about 5 % of the golden places
# for this reason, so this family asks for items with 15 or more sitelinks, no country, and an
# administrative parent (one or two hops up) that has one.
LOCATED_QUERY = """\
SELECT ?item ?coord ?sl ?country ?label_en ?label_loc
       (GROUP_CONCAT(DISTINCT STRAFTER(STR(?inst), "/entity/"); separator = "|") AS ?insts) WHERE {{
  VALUES ?country {{ {countries} }}
  ?item wdt:P625 ?coord ; wikibase:sitelinks ?sl .
  FILTER(?sl >= {lo}{hi})
  FILTER NOT EXISTS {{ ?item wdt:P17 [] }}
  ?item wdt:P131/wdt:P131? ?admin .
  ?admin wdt:P17 ?country .
  OPTIONAL {{ ?item wdt:P31 ?inst }}
  OPTIONAL {{ ?item rdfs:label ?label_en FILTER(lang(?label_en) = "en") }}
  OPTIONAL {{ ?item rdfs:label ?label_loc FILTER(lang(?label_loc) = "{lang}") }}
}} GROUP BY ?item ?coord ?sl ?country ?label_en ?label_loc ORDER BY ?item LIMIT {limit} OFFSET {offset}
"""
LOCATED_BANDS: list[tuple[int, int | None]] = [(40, None), (15, 39)]
INSTITUTIONAL_QUERY = """\
SELECT ?item ?coord ?sl ?whs ?wdpa ?country ?label_en ?label_loc WHERE {{
  VALUES ?country {{ {countries} }}
  ?item wdt:P17 ?country ; wikibase:sitelinks ?sl .
  {{ ?item wdt:P757 ?whs }} UNION {{ ?item wdt:P809 ?wdpa }}
  OPTIONAL {{ ?item wdt:P625 ?coord }}
  OPTIONAL {{ ?item rdfs:label ?label_en FILTER(lang(?label_en) = "en") }}
  OPTIONAL {{ ?item rdfs:label ?label_loc FILTER(lang(?label_loc) = "{lang}") }}
}} ORDER BY ?item LIMIT {limit} OFFSET {offset}
"""
NODE_QUERY = """\
SELECT ?item ?coord ?sl ?iata ?icao ?code ?country ?label_en WHERE {{
  VALUES ?country {{ {countries} }}
  ?item wdt:P17 ?country ; wdt:P31/wdt:P279* wd:{cls} ; wdt:P625 ?coord ; wikibase:sitelinks ?sl .
  FILTER(?sl >= {lo})
  OPTIONAL {{ ?item wdt:P238 ?iata }} OPTIONAL {{ ?item wdt:P239 ?icao }} OPTIONAL {{ ?item wdt:P296 ?code }}
  OPTIONAL {{ ?item rdfs:label ?label_en FILTER(lang(?label_en) = "en") }}
}} ORDER BY ?item LIMIT {limit} OFFSET {offset}
"""
NODE_CLASSES = {"airport": ("Q1248784", 1), "rail_station": ("Q55488", 5), "ferry_terminal": ("Q1061151", 1)}


@dataclass(frozen=True)
class Job:
    country: str
    family: str          # class:<qid>:<lo>-<hi> | pop | institutional | node:<kind>
    template: str
    params: tuple        # sorted (key, value) pairs, for the file name hash and the query

    @property
    def filename(self) -> str:
        return f"{self.country}__{self.family.replace(':', '_')}.jsonl"

    def query(self, offset: int) -> str:
        return self.template.format(**dict(self.params), limit=PAGE, offset=offset)


def classes(path: Path | None = None) -> list[str]:
    p = path or ROOT / "data" / "rules" / "classes.csv"
    with open(p, encoding="utf-8", newline="") as fh:
        return [r["class_qid"] for r in csv.DictReader(fh)]


def jobs(countries: list[str] | None = None, class_qids: list[str] | None = None) -> list[Job]:
    out: list[Job] = []
    for iso in countries or list(COUNTRIES):
        c = COUNTRIES[iso]
        base = {"countries": " ".join(f"wd:{q}" for q in c["qids"]), "lang": c["lang"]}
        for cls in class_qids if class_qids is not None else classes():
            for lo, hi in BANDS:
                p = dict(base, cls=cls, lo=lo, hi="" if hi is None else f" && ?sl <= {hi}")
                out.append(Job(iso, f"class:{cls}:{lo}-{hi or 'up'}", CLASS_QUERY, tuple(sorted(p.items()))))
        out.append(Job(iso, "popall", POP_QUERY, tuple(sorted(base.items()))))
        for lo, hi in ATTENTION_BANDS:
            p = dict(base, lo=lo, hi="" if hi is None else f" && ?sl <= {hi}")
            out.append(Job(iso, f"attention:{lo}-{hi or 'up'}", ATTENTION_QUERY, tuple(sorted(p.items()))))
        for lo, hi in LOCATED_BANDS:
            p = dict(base, lo=lo, hi="" if hi is None else f" && ?sl <= {hi}")
            out.append(Job(iso, f"locatedin:{lo}-{hi or 'up'}", LOCATED_QUERY, tuple(sorted(p.items()))))
        out.append(Job(iso, "institutional", INSTITUTIONAL_QUERY, tuple(sorted(base.items()))))
        for kind, (cls, lo) in NODE_CLASSES.items():
            out.append(Job(iso, f"node:{kind}", NODE_QUERY, tuple(sorted(dict(base, cls=cls, lo=lo).items()))))
    return out


def point(wkt: str) -> tuple[float, float] | None:
    """'Point(lon lat)' as WDQS returns it -> (lat, lon)."""
    if not wkt or not wkt.startswith("Point("):
        return None
    lon, lat = wkt[6:-1].split()
    return float(lat), float(lon)


def parse(binding: dict, disputed: dict[str, str] | None = None) -> dict:
    v = {k: x.get("value") for k, x in binding.items()}
    row: dict = {"qid": qid_of(v["item"])}
    xy = point(v.get("coord") or "")
    row["lat"], row["lon"] = xy if xy else (None, None)
    for k in ("sl", "pop"):
        if v.get(k) not in (None, ""):
            row["sitelinks" if k == "sl" else "population"] = int(float(v[k]))
    if v.get("insts"):
        row["instance_of"] = v["insts"].split("|")
    for k in ("whs", "wdpa", "iata", "icao", "code", "label_en", "label_loc"):
        if v.get(k):
            row[k] = v[k]
    if v.get("country"):
        cq = qid_of(v["country"])
        row["country_qid"] = cq
        if disputed and cq in disputed:
            row["disputed"] = disputed[cq]
    return row


def http_run(query: str, retries: int = 4) -> list[dict]:
    body = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    req = urllib.request.Request(SPARQL, data=body, headers={
        "User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))["results"]["bindings"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(float(e.headers.get("Retry-After") or 20 * (attempt + 1)))
                continue
            raise
    raise RuntimeError("unreachable")


def _write(path: Path, meta: dict, rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"_meta": meta}, ensure_ascii=False) + "\n")
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)


def read_meta(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.loads(fh.readline()).get("_meta")
    except (OSError, ValueError):
        return None


def run_job(job: Job, out: Path, run: Callable[[str], list[dict]], delay: float = 1.0) -> dict:
    """Page one job to completion and write its file; skip it when already complete."""
    path = out / job.filename
    done = read_meta(path)
    if done and done.get("complete"):
        return {"job": job.filename, "status": "skipped", "rows": done["rows"]}
    c = COUNTRIES[job.country]
    rows: list[dict] = []
    offset = 0
    while True:
        page = run(job.query(offset))
        rows += [parse(b, c.get("disputed")) for b in page]
        if len(page) < PAGE:
            break
        offset += PAGE
        time.sleep(delay)
    meta = {"country": job.country, "family": job.family, "query": job.query(0), "page": PAGE,
            "run_utc": datetime.now(UTC).isoformat(timespec="seconds"), "endpoint": SPARQL,
            "rows": len(rows), "complete": True}
    _write(path, meta, rows)
    return {"job": job.filename, "status": "ok", "rows": len(rows)}


def run_all(todo: list[Job], out: Path, run: Callable[[str], list[dict]] = http_run, delay: float = 1.0,
            log: Callable[[str], None] = print) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for i, job in enumerate(todo, 1):
        try:
            r = run_job(job, out, run, delay)
        except Exception as e:                                   # a failed query must not hide the rest
            r = {"job": job.filename, "status": "failed", "error": f"{type(e).__name__}: {e}"[:200]}
        results.append(r)
        log(f"[{i}/{len(todo)}] {r['job']}: {r['status']}" + (f" ({r['rows']} rows)" if "rows" in r else f" {r.get('error', '')}"))
        if r["status"] == "ok":
            time.sleep(delay)
    return results


def check(out: Path, todo: list[Job]) -> list[str]:
    problems = []
    for j in todo:
        m = read_meta(out / j.filename)
        if not m or not m.get("complete"):
            problems.append(f"{j.filename}: missing or incomplete")
    return problems


def preflight(labels: Callable[[list[str]], dict[str, str]]) -> list[str]:
    """Each country QID must carry the expected English label before any query runs."""
    want = {q: COUNTRIES[iso]["name"] for iso in COUNTRIES for q in COUNTRIES[iso]["qids"][:1]}
    got = labels(sorted(want))
    return [f"{q}: expected {n!r}, Wikidata says {got.get(q)!r}" for q, n in want.items() if got.get(q) != n]


def iter_rows(path: Path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            yield json.loads(line)


def to_parquet(out: Path, only: set[str] | None = None) -> dict[str, int]:
    """One Parquet file per family group (class, pop, institutional, node), via DuckDB."""
    import duckdb
    con = duckdb.connect()
    counts: dict[str, int] = {}
    groups: dict[str, list[Path]] = {}
    for f in sorted(out.glob("*__*.jsonl")):
        if only is not None and f.name not in only:
            continue
        fam = f.stem.split("__", 1)[1].split("_", 1)[0]
        groups.setdefault(fam, []).append(f)
    for fam, files in groups.items():
        tmp = out / f"{fam}.rows.jsonl"
        with open(tmp, "w", encoding="utf-8") as w:
            for f in files:
                iso = f.stem.split("__", 1)[0]
                family = f.stem.split("__", 1)[1]
                for r in iter_rows(f):
                    w.write(json.dumps({**r, "iso3": iso, "family": family}, ensure_ascii=False) + "\n")
        dest = out / f"{fam}.parquet"
        con.execute(f"COPY (SELECT * FROM read_json_auto('{tmp.as_posix()}', union_by_name=true)) "
                    f"TO '{dest.as_posix()}' (FORMAT PARQUET)")
        counts[fam] = con.execute(f"SELECT count(*) FROM read_parquet('{dest.as_posix()}')").fetchone()[0]
        tmp.unlink()
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "check", "pin", "parquet"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, default=ROOT / "data" / "raw" / "wikidata" / datetime.now(UTC).date().isoformat())
        p.add_argument("--countries", nargs="*", choices=list(COUNTRIES), default=None)
        if name == "run":
            p.add_argument("--delay", type=float, default=1.0)
    a = ap.parse_args(argv)
    todo = jobs(a.countries)
    if a.cmd == "plan":
        print(f"{len(todo)} queries for {len(a.countries or COUNTRIES)} countries, pages of {PAGE}")
        print(todo[0].query(0))
        return 0
    if a.cmd == "run":
        from atlas.wikidata import Client
        bad = preflight(Client().labels)
        if bad:
            print("country check failed:\n  " + "\n  ".join(bad))
            return 1
        res = run_all(todo, a.out, delay=a.delay)
        failed = [r for r in res if r["status"] == "failed"]
        print(f"{sum(r.get('rows', 0) for r in res)} rows, {len(failed)} failed (run again to retry only those)")
        return 1 if failed else 0
    if a.cmd == "check":
        problems = check(a.out, todo)
        print("\n".join(problems) or "all queries complete")
        return 1 if problems else 0
    if a.cmd == "pin":
        from atlas import snapshot
        snap = a.out.name
        for f in sorted(a.out.glob("*.parquet")):          # the JSONL files are local intermediates
            snapshot.pin("wikidata_sparql", f, ROOT / "data" / "raw", snap)
        print("pinned", a.out)
        return 0
    print(to_parquet(a.out, {j.filename for j in todo}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

